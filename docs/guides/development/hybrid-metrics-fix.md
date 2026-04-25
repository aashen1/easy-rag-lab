# Hybrid 策略评测指标全链路修复记录

> 日期：2026-04-26
> 关联 Commits: `9de13f0`, `c7e29a4`, `5f10ca0`, `da63276`

---

## 1. 问题背景

Hybrid 策略是 v0.1.8 引入的新版问题生成策略，通过"文档级分段 + chunk 级证据验证"生成测试集。但经分析发现，生成的测试集缺少 `ground_truth_excerpt` 字段，导致两条评测链路（Builtin + RAGAS）中 4 个指标无法严格计算：

| 指标 | 链路 | 问题 |
|------|------|------|
| context_precision | Builtin + RAGAS | 缺少原文摘录作为 expected_output/reference |
| context_recall | Builtin + RAGAS | 缺少原文句子作为 ground truth |
| answer_correctness | RAGAS | 缺少客观参考答案，用 LLM 答案做 reference 是循环论证 |
| semantic_similarity | RAGAS | 同上 |

此外，在修复过程中还发现了 segment-chunk 映射和 chunk 定位两个关联 bug。

---

## 2. 修复一：生成 `ground_truth_excerpt` 字段

### 根因

Hybrid 策略的 `_generate_hybrid_question` 方法在生成问题时，LLM 会返回 `evidence` 列表（包含 `quote` 字段），但代码从未将验证通过的 quote 提取为 `ground_truth_excerpt` 字段。

而评测管线的数据流中，`ground_truth_excerpt` 是多个指标的关键输入：

```
question_data["ground_truth_excerpt"]  →  sample["ground_truth_excerpt"]
    ↓ (优先级高于 answer)
expected_answer (Builtin) / reference (RAGAS)
    ↓
context_precision / context_recall / answer_correctness / semantic_similarity
```

当 `ground_truth_excerpt` 缺失时，系统回退到 `question_data["answer"]`（LLM 生成的答案），这不是原文摘录，无法满足上述指标的严格定义。

### 修复方案

在 `_generate_hybrid_question` 方法中，证据验证通过后，从 evidence 的 quote 字段拼接生成 `ground_truth_excerpt`：

```python
all_quotes = [
    e["quote"]
    for e in validation["verified_evidence"]
    if e.get("quote", "").strip()
]
qa["ground_truth_excerpt"] = "\n".join(all_quotes) if all_quotes else ""
```

对不同问题类型的处理：
- **single_fact/multi_fact/reasoning/comparative**：使用 evidence quote 拼接
- **missing**：`ground_truth_excerpt = ""`（文档确实不包含答案）
- **irrelevant**：`ground_truth_excerpt = ""`（与文档无关）

### 设计决策：为什么使用所有 quote 而非仅 verified=True 的

初始实现只使用 `verified=True` 的 quote，但实验发现 LLM 生成的 quote 经常无法在 segment 文本中精确匹配（`verified=False`），原因包括：
- OCR 处理后的文本与原文有细微差异
- LLM 可能对原文做轻微改写

然而，即使 quote 未通过精确/模糊验证，它仍然是 LLM 对原文的最佳近似，比回退到 LLM 生成的 `answer`（包含推理、概括、改写）更接近原文。因此改为使用所有 quote。

---

## 3. 修复二：Segment-Chunk 映射从位置匹配改为文本重叠匹配

### 根因

`_map_segments_to_chunks` 方法原本基于字符位置重叠判断 chunk 属于哪个 segment：

```python
# 旧逻辑
chunk_start = metadata.get("start_index", 0)  # 实际不存在！
chunk_end = metadata.get("end_index", 0)       # 实际不存在！
if chunk_start < seg_end and chunk_end > seg_start:
    overlapping_chunks.append(chunk_id)
```

问题在于 chunk 元数据中没有 `start_index`/`end_index` 字段（只有 `start_token`/`end_token`），导致所有 chunk 的 `chunk_start`/`chunk_end` 都默认为 0，映射结果全部为空。

第一次修复尝试使用累积 `char_count` 估算字符位置，但发现 segment 和 chunk 的坐标系完全不同：
- **Segment**：从原始 markdown 文档内容切分，字符位置基于原始文本
- **Chunk**：从 OCR 处理后的 JSONL 文件加载，字符计数基于 OCR 文本

两套文本的字符数不一致（OCR 会添加空格、改变格式），累积 `char_count` 无法准确映射。

### 修复方案

彻底放弃位置匹配，改用文本内容重叠匹配：

```python
def _map_segments_to_chunks(self, segments, doc_chunks):
    for segment in segments:
        seg_text = segment.get("text", "")
        for chunk_id, chunk_text in chunk_texts:
            if self._texts_overlap(seg_text, chunk_text):
                overlapping_chunks.append(chunk_id)
```

`_texts_overlap` 使用滑动窗口 + 文本归一化（`" ".join(t.split())`）检测两个文本是否有 30 字符以上的连续重叠子串，能处理 OCR 引入的空格差异。

---

## 4. 修复三：Chunk 定位添加模糊匹配和全 chunk 回退

### 根因

`_locate_chunks_by_quote` 方法使用精确子串匹配 `if quote in chunk_text` 来判断 quote 是否出现在 chunk 文本中。但 chunk 文本经过 OCR 处理，中文字符之间可能被插入空格（如 `"C - R E I T s"` vs `"C-REITs"`），导致精确匹配失败。

### 修复方案

两层回退机制：

1. **精确匹配优先**：`if quote in chunk_text` — 快速路径
2. **模糊匹配回退**：调用 `_verify_quote_in_segment(quote, chunk_text)` — 使用 `difflib.SequenceMatcher`，阈值 0.85
3. **全 chunk 搜索回退**：当 `segment_chunk_map` 为空或 quote 未在任何 segment 中找到时，直接搜索所有 doc_chunks

```python
# 回退逻辑
if containing_segment_index is None:
    # quote 未在任何 segment 中找到，搜索所有 chunk
    chunk_ids = [c.get("chunk_id", "") for c in doc_chunks if c.get("chunk_id")]
else:
    chunk_ids = segment_chunk_map.get(containing_segment_index, [])
    if not chunk_ids:
        # segment 没有映射到任何 chunk，搜索所有 chunk
        chunk_ids = [c.get("chunk_id", "") for c in doc_chunks if c.get("chunk_id")]
```

---

## 5. 修复四：实验配置调整

### 问题

初始实验配置 `baseline_500page.yaml` 包含了 `retrieval_diversity` 指标，但该指标不在实验框架的有效检索指标列表中，导致配置验证失败。

### 修复

移除 `retrieval_diversity`，并创建小规模快速验证配置 `quick_verify_metrics.yaml`（50 页 PDF、6 个问题），加速开发迭代。

---

## 6. 已修复问题：Chunk JSONL 文本编码损坏（BUG-024）

### 现象

Chunk JSONL 文件中的 `text` 字段存在编码损坏，中文字符显示为乱码（如 `鍦 浜` 而非 `地产`），导致所有基于文本匹配的 chunk 定位逻辑无法工作，`source_chunks` 始终为空，chunk-level 指标（chunk_hit_rate/chunk_mrr/chunk_ndcg）无法计算。

### 排查过程

1. 发现 `source_chunks` 始终为空
2. 检查 `_locate_chunks_by_quote` — 逻辑正确
3. 检查 `segment_chunk_map` — 映射为空
4. 检查 `_map_segments_to_chunks` — 位置匹配失败
5. 改为文本重叠匹配 — 仍然失败
6. 直接读取 chunk JSONL 文件 — 发现文本是乱码
7. 对比 parsed JSON 文件 — 原文可读，问题出在 chunker 输出

### 根因

`chunk_text()` 中 `encoding.encode(text)` → 切片 → `encoding.decode(chunk_tokens)` 的往返过程中，当 chunk 边界恰好切在多字节 UTF-8 字符的 token 中间时，`decode()` 会产生乱码。tiktoken 官方文档明确警告："decode() can be lossy for tokens that aren't on utf-8 boundaries"。

### 修复方案

新增 `_build_token_char_offsets()` 函数，构建 token 索引到原始文本字符偏移的映射。`chunk_text()` 改用 `text[char_start:char_end]` 原文切片替代 `encoding.decode(chunk_tokens)`，彻底避免编码/解码问题。`chunk_text_page_aware()` 的 cross_page_overlap 逻辑同步修复。

### 验证结果

使用 `quick_verify_metrics` 配置重新运行实验，chunk-level 指标恢复正常：
- chunk_hit_rate: 1.0（之前 null）
- chunk_mrr: 0.29（之前 null）
- chunk_ndcg: 0.45（之前 null）
- 其他所有指标未受影响

---

## 7. 验证结果

使用 `quick_verify_metrics` 配置（50 页 PDF、6 个问题）运行实验，确认所有非 chunk-level 指标均能正常计算：

### Builtin 链路

| 指标 | 修复前 | 修复后 | 示例值 |
|------|--------|--------|--------|
| hit_rate | ✅ | ✅ | 1.0 |
| mrr | ✅ | ✅ | 1.0 |
| ndcg | ✅ | ✅ | 1.0 |
| dedup_hit_rate/mrr/ndcg | ✅ | ✅ | 1.0 |
| false_positive_rate | ✅ | ✅ | 1.0 |
| **context_precision** | **⚠️ 偏差** | **✅** | **0.0-1.0** |
| **context_recall** | **⚠️ 偏差** | **✅** | **0.5-1.0** |
| faithfulness | ✅ | ✅ | 0.75-1.0 |
| answer_relevancy | ✅ | ✅ | 0.33-0.97 |
| chunk_hit_rate/mrr/ndcg | ✅ | ⚠️ 数据层 | null |

### RAGAS 链路

| 指标 | 修复前 | 修复后 | 示例值 |
|------|--------|--------|--------|
| faithfulness | ✅ | ✅ | 0.83-1.0 |
| answer_relevancy | ✅ | ✅ | 0.0-0.71 |
| **context_precision** | **⚠️ 偏差** | **✅** | **0.58-1.0** |
| **context_recall** | **⚠️ 偏差** | **✅** | **1.0** |
| **answer_correctness** | **❌ 循环论证** | **✅** | **0.64-0.98** |
| **semantic_similarity** | **❌ 循环论证** | **✅** | **0.58-0.93** |

---

## 8. 数据流全景

修复后的完整数据流：

```
[Hybrid 问题生成]
    │  _generate_hybrid_question()
    │  ├── evidence quote → ground_truth_excerpt (新增)
    │  ├── evidence quote → source_chunks (via _locate_chunks_by_quote)
    │  └── question_type → expect_retrieval / expect_no_answer
    ▼
[test_set JSON]
    │  question_data["ground_truth_excerpt"]  ← 新增字段
    │  question_data["source_chunks"]
    │  question_data["answer"]
    │  question_data["source_files"]
    ▼
[run_experiment.py: _collect_rag_samples]
    │  sample["ground_truth_excerpt"] = question_data.get("ground_truth_excerpt")
    │  sample["expected_chunks"] = question_data.get("source_chunks")
    ▼
[BuiltinEvaluator.evaluate_single]
    │  expected_answer = sample.get("ground_truth_excerpt") or sample.get("expected_answer")
    │  → context_precision(expected_output=expected_answer)  ← 现在用原文摘录
    │  → context_recall(ground_truth=expected_answer)         ← 现在用原文摘录
    │  → chunk_hit_rate(expected_chunks=expected_chunks)      ← 待修复数据层
    ▼
[RagasEvaluator.evaluate_batch]
    │  reference = sample.get("ground_truth_excerpt") or sample.get("expected_answer")
    │  → SingleTurnSample(reference=reference)               ← 现在用原文摘录
    │  → answer_correctness(response vs reference)            ← 不再循环论证
    │  → semantic_similarity(response vs reference)           ← 不再循环论证
```
