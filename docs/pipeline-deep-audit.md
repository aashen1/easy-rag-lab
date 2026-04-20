# RAG 系统基线链路深度勘察报告

> **勘察目标**：以冒烟测试 `exp_20260421_015659_smoke_quick` 为例，从 PDF 到 AI 给出答案，逐阶段打开黑盒，记录每个环节的**实际行为、数据流、潜在问题**。
>
> **勘察范围**：仅覆盖基线链路（纯向量检索，无 BM25/重排序/查询改写），暂不涉及 RAGAS 评测。
>
> **维护方式**：随对话持续更新，最终作为后续重构的依据。

---

## 0. 冒烟测试概况

| 项目 | 值 |
|------|-----|
| 实验配置 | `exp_configs/smoke_tests/smoke_quick.yaml` |
| Meal 名称 | `smoke_quick`（3% 采样，seed=42） |
| 测试集 | 1 个问题，document 策略 |
| 变体 | 仅 baseline（无 config_overrides） |
| 评测指标 | 检索: hit_rate, mrr, ndcg / 生成: faithfulness, answer_relevancy |
| 基线配置 | 固定切块 512 token / 无重叠 / BAAI/bge-large-zh-v1.5 / top_k=5 / Cosine / 纯向量检索 |

---

## 1. Stage 1: PDF 解析

### 1.1 入口与调用链

```
run_experiment()
  → prepare_meal()  # 确认/创建 meal
  → run_variant_evaluation()
    → prepare_index_for_variant()
      → build_chunks_if_needed()
        → parse_all_pdfs()  # 实际解析
```

### 1.2 核心实现

- **文件**: [parser.py](../src/parser.py)
- **方法**: `parse_pdf()` → `pymupdf4llm.to_markdown(pdf_path)`
- **输出**: 每个 PDF → 同目录结构的 `.md` 文件，存于 `data/parsed/`

### 1.3 实际行为分析

1. **解析引擎**: 使用 `pymupdf4llm`（PyMuPDF 的 LLM 友好封装），将 PDF 页面转为 Markdown
2. **输出格式**: 纯 Markdown 文本，保留标题层级、表格（以文本形式）、列表等
3. **增量机制**: 若 `.md` 文件已存在且 `force=False`，则跳过解析
4. **分类标注**: 通过 `detect_document_category()` 根据路径关键词推断文档类别

### 1.4 潜在问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| P1-1 | **表格解析质量** | 高 | pymupdf4llm 对复杂表格（合并单元格、多级表头）的 Markdown 转换经常错乱，金融研报中大量财务数据表格可能丢失结构 |
| P1-2 | **图表信息丢失** | 中 | PDF 中的图表仅能提取文字标签，图形本身的信息（趋势、对比关系）完全丢失 |
| P1-3 | **页眉页脚污染** | 中 | 页码、公司 logo 文字、水印等会被混入正文，影响后续分块和检索质量 |
| P1-4 | **无 OCR 兜底** | 低 | 扫描件 PDF 无法处理（当前数据源为电子版研报，暂无影响） |

---

## 2. Stage 2: 文本分块 (Chunking)

### 2.1 入口与调用链

```
build_chunks_if_needed()
  → process_parsed_files()  # 固定分块
  或 process_parsed_files_semantic()  # 语义分块（基线不使用）
```

### 2.2 核心实现

- **文件**: [chunker.py](../src/chunker.py)
- **基线策略**: `fixed` — 基于 tiktoken token 计数的固定长度分块
- **关键参数**: `chunk_size=512`, `chunk_overlap=0`

### 2.3 分块算法详解

```python
# chunk_text() 核心逻辑
encoding = tiktoken.get_encoding("cl100k_base")
tokens = encoding.encode(text)

while start < total_tokens:
    end = min(start + chunk_size, total_tokens)
    chunk_tokens = tokens[start:end]
    chunk_text_decoded = encoding.decode(chunk_tokens)
    # → 产出 chunk
    start = end - overlap if overlap > 0 else end  # 基线: overlap=0, 直接跳到 end
```

### 2.4 Chunk 元数据

每个 chunk 写入 JSONL 文件，格式：

```json
{
  "chunk_id": "文件名_ chunk序号(3位)",
  "text": "解码后的文本",
  "metadata": {
    "source": "相对路径.md",
    "category": "文档类别",
    "chunk_index": 0,
    "char_count": 1234,
    "token_count": 512,
    "start_token": 0,
    "end_token": 512
  }
}
```

### 2.5 潜在问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| P2-1 | **无重叠导致边界信息丢失** | 高 | `chunk_overlap=0` 意味着跨 chunk 边界的信息完全断裂。例如一个完整句子被切成两半，两半都不完整 |
| P2-2 | **token 级切割不考虑语义边界** | 高 | 在 token 序列中间硬切，可能在句子中间、甚至词语中间断开（虽然 decode 会尽量恢复，但语义连贯性已破坏） |
| P2-3 | **chunk_id 命名脆弱** | 中 | `chunk_id = f"{source_name}_{chunk_index:03d}"` 依赖文件名，若文件名含下划线则解析 `_parse_chunk_id()` 可能出错 |
| P2-4 | **无段落感知** | 中 | 不识别 Markdown 标题层级（`#`, `##`），可能在标题和正文之间切断 |
| P2-5 | **长表格可能被切碎** | 中 | 一个完整表格可能跨越多个 chunk，导致检索时只能看到部分数据 |

---

## 3. Stage 3: 向量化与索引构建

### 3.1 入口与调用链

```
prepare_index_for_variant()
  → build_index_from_chunks()
    → VectorIndexer.build_index()
      → Embedder.embed_texts()  # 批量向量化
      → VectorIndexer.create_collection()
      → VectorIndexer.index_chunks()  # 写入 Qdrant
```

### 3.2 核心实现

- **Embedder**: [embedder.py](../src/embedder.py) — BAAI/bge-large-zh-v1.5
- **Indexer**: [indexer.py](../src/indexer.py) — Qdrant 本地模式

### 3.3 向量化细节

1. **模型**: `BAAI/bge-large-zh-v1.5`（1024 维）
2. **编码方式**: CLS token 表示 + L2 归一化
3. **截断**: `max_length=512`（tokenizer 层面截断，超过 512 token 的 chunk 会被截断）
4. **批处理**: `batch_size=32`
5. **精度**: CUDA 上使用 FP16

### 3.4 索引构建细节

1. **存储**: Qdrant 本地文件模式，持久化到 `data/vector_store/`
2. **距离度量**: Cosine（因向量已 L2 归一化，Cosine 等价于点积）
3. **Payload**: 每个 point 存储 `chunk_id`, `text`, `metadata`
4. **Upsert**: 批量 100 条

### 3.5 潜在问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| P3-1 | **512 token 截断与 chunk_size=512 冲突** | 高 | chunk 本身就是 512 token，但 embedder 的 `max_length=512` 会在 tokenizer 层面再次截断。由于 tiktoken 的 cl100k_base 和 BGE 的 tokenizer 不同，实际 token 数可能超过 512 BGE tokens，导致 chunk 尾部信息在向量化时被丢弃 |
| P3-2 | **无索引配置缓存** | 低 | 每次实验都重新检查/构建索引，虽有 meal 机制但首次构建较慢 |

---

## 4. Stage 4: 检索 (Retrieval)

### 4.1 入口与调用链

```
RAGPipeline.query(question)
  → Retriever.retrieve(query)
    → Embedder.embed_query(query)  # 查询向量化
    → QdrantClient.query_points()  # 向量相似度搜索
```

### 4.2 核心实现

- **文件**: [retriever.py](../src/retriever.py)
- **基线方法**: 纯向量检索（`method="vector"`）
- **top_k**: 5

### 4.3 检索流程

1. 将用户问题通过同一个 Embedder 向量化
2. 在 Qdrant 中搜索 Cosine 相似度最高的 top_k 个向量
3. 返回结果包含 `chunk_id`, `text`, `metadata`, `score`

### 4.4 检索结果的数据流

```
retriever.retrieve() → List[Dict]
  ↓
pipeline.query() 提取:
  - contexts = [r["text"] for r in results]       # 文本内容列表
  - scores = [r["score"] for r in results]         # 相似度分数列表
  - sources = [r["metadata"]["source"] for r in results]  # 来源路径列表
  - chunk_ids = [r["chunk_id"] for r in results]   # chunk ID 列表
```

### 4.5 潜在问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| P4-1 | **查询未加指令前缀** | 中 | BGE 模型官方推荐对查询添加指令前缀 "为这个句子生成表示以用于检索相关文章："，当前代码直接使用原始查询，可能降低检索效果 |
| P4-2 | **无分数过滤** | 高 | 返回 top_k 结果时不设最低相似度阈值，低质量匹配也会返回，可能导致"看似命中实则无关" |
| P4-3 | **单一检索策略** | 中 | 基线仅用向量检索，对关键词精确匹配（如公司代码、特定数字）效果差 |

---

## 5. Stage 5: Prompt 构建与 LLM 生成

### 5.1 入口与调用链

```
RAGPipeline.query()
  → Generator.generate(question, contexts)
    → Anthropic.messages.create()  # API 调用
```

### 5.2 核心实现

- **文件**: [generator.py](../src/generator.py)
- **LLM**: 通过 Anthropic SDK 兼容接口调用（实际模型由配置决定）

### 5.3 Prompt 构建详解

**System Prompt**（硬编码）:

```
你是一个金融研报分析助手。请基于以下参考资料回答用户问题。

要求：
1. 回答要准确、简洁、专业
2. 如果参考资料中有相关信息，请基于资料回答
3. 如果参考资料中没有相关信息，请明确说明"根据提供的参考资料，我无法回答这个问题"
4. 回答时请引用具体的来源（如"根据贵州茅台2023年年度报告..."）
5. 直接以回答内容开头，禁止使用"好的"、"当然"、"我来"等对话性用语开头
```

**User Message**（动态拼接）:

```
参考资料 1:
{context_1}

参考资料 2:
{context_2}
...

用户问题：{query}

请基于参考资料回答上述问题：
```

### 5.4 潜在问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| P5-1 | **System Prompt 硬编码** | 高 | system_prompt 在 Generator 中硬编码，无法通过配置调整，不同实验变体无法使用不同的 prompt 策略 |
| P5-2 | **Context 拼接无排序** | 中 | 检索结果按相似度排序传入，但 prompt 中未体现优先级，LLM 可能被排在后面的低质量 context 误导 |
| P5-3 | **无 Context 长度控制** | 高 | 5 个 512 token 的 chunk 约 2560 token，加上 system prompt 和 query，可能接近或超过模型的 context window 限制（取决于具体模型），且无截断保护 |
| P5-4 | **引用来源要求模糊** | 中 | prompt 要求"引用具体来源"，但传入的 context 只有编号（参考资料1/2/3），没有文档名，LLM 无法真正引用来源 |

---

## 6. Stage 6: 评估指标计算

### 6.1 评估流程

```
evaluate_test_set()
  → _collect_rag_samples()  # 对每个问题执行 pipeline.query()
  → _evaluate_with_builtin()
    → BuiltinEvaluator.evaluate_single()
      → calculate_hit_rate() / calculate_mrr() / calculate_ndcg()  # 检索指标
        → calculate_faithfulness() / calculate_answer_relevancy()    # 生成指标
```

### 6.2 🔴 已确认的严重 Bug: BuiltinEvaluator contexts/sources 混淆

**数据流追踪**:

```
_collect_rag_samples():
  sample = {
      "contexts": response.get("contexts", []),        # ← chunk 文本内容列表
      "retrieved_sources": response.get("sources", []), # ← 来源路径列表
  }

_evaluate_with_builtin():
  evaluator.evaluate_single(
      contexts=sample.get("retrieved_sources", []),  # ← 传的是来源路径！不是文本内容！
      ...
  )

BuiltinEvaluator.evaluate_single(contexts=...):
  # 检索指标: retrieved_sources=contexts → 传的是路径 → ✅ 正确
  calculate_hit_rate(retrieved_sources=contexts, expected_sources=expected_sources)

  # 生成指标: contexts=contexts → 传的是路径 → ❌ BUG！应该是文本内容！
  calculate_faithfulness(answer=answer, contexts=contexts, ...)
```

**影响**: Faithfulness 指标收到的是文件路径（如 `research_reports\\2026年光伏行业分析.md`）而非 chunk 文本内容。LLM 被要求判断"答案中的陈述是否能从这些文件路径推导出来"，这完全失去了评估意义。

**实际数据佐证**:
- q005 faithfulness=0.0：答案"秦港Q5500动力煤平仓价为754元/吨"无法从文件路径推导 → 合理
- q001 faithfulness=1.0：答案关于光伏行业，文件路径含"光伏行业分析"，LLM 可能从路径名推断相关性 → 不合理但可解释
- 整体 avg_faithfulness=0.628：这个数字完全不可信

### 6.3 🔴 已确认的严重问题: 检索结果全部来自同一文档

**实际数据** (baseline.json):

| 问题ID | 检索到的5个来源 | 是否全部相同文档 |
|--------|----------------|-----------------|
| q001 | 5× 2026年光伏行业分析.md | ✅ 全部相同 |
| q002 | 5× 2026年光伏行业分析.md | ✅ 全部相同 |
| q003 | 5× 光模块设备行业深度.md | ✅ 全部相同 |
| q004 | 5× 光模块设备行业深度.md | ✅ 全部相同 |
| q005 | 3× 煤炭周报(油价) + 2× 煤炭周报(中东) | 近乎相同 |
| q007 | 3× 煤炭周报(油价) + 2× 煤炭周报(中东) | 近乎相同 |
| q008 | 5× 电子行业周报Samsung.md | ✅ 全部相同 |
| q009 | 5× 格力电器2024年年度报告.md | ✅ 全部相同 |

**根因**: 纯向量检索 + 无文档级去重 = top 5 结果必然集中在最相似的文档。这导致：
1. **检索多样性为零**：5 个 slot 全被同一文档占据
2. **Hit Rate 虚高**：只要该文档有一个相关 chunk，5 个 slot 全部"命中"
3. **多文档问题必然失败**：需要跨文档信息的问题只能看到一个文档

### 6.4 🔴 已确认的问题: 测试集 expected_sources 标注错误

**实际数据**: q010 问"中际旭创和新易盛哪家更值得投资"，expected_sources 指向 `annual_reports/2025/中芯国际/港股公告_2025年年报.md`。

中芯国际是半导体代工厂，与光模块公司中际旭创/新易盛完全无关。实际检索到的是光模块行业研报，反而是正确的。但 hit_rate=0.0 因为路径不匹配。

**根因**: `generate_document_based_questions()` 中，问题基于整篇文档生成，`source_files` 直接设为该文档路径。但 LLM 生成的问题可能涉及文档中提到的其他公司/行业，导致 expected_sources 与实际应检索的文档不匹配。

### 6.5 检索指标详解

#### 6.5.1 Hit Rate

```python
# 标准模式 (mode='standard')
top_k_set = set(normalize_source(s) for s in retrieved_sources[:k])
expected_set = set(normalize_source(s) for s in expected_sources)
return 1.0 if top_k_set & expected_set else 0.0
```

**normalize_source()**: 取文件路径的 stem（去掉目录和扩展名），如 `annual_report/贵州茅台2023年年度报告.md` → `贵州茅台2023年年度报告`

#### 6.5.2 MRR (Mean Reciprocal Rank)

```python
for i, source in enumerate(retrieved_sources):
    if normalize_source(source) in expected_set:
        return 1.0 / (i + 1)
return 0.0
```

#### 6.5.3 NDCG

标准 DCG/IDCG 公式，支持多级相关性评分，内置去重。

### 6.6 生成指标详解

#### 6.6.1 Faithfulness (忠实度) — ⚠️ 当前结果不可信

两步 LLM 评估：
1. **提取陈述**: 从 answer 中提取所有事实性陈述
2. **验证陈述**: 逐条判断陈述是否能从 contexts 中推导

```python
faithfulness = supported_statements / total_statements
```

**当前 Bug**: contexts 收到的是文件路径而非文本内容（见 6.2），所有 faithfulness 数值不可信。

#### 6.6.2 Answer Relevancy (答案相关性)

单步 LLM 评估，3 个维度各 1-5 分：
- 直接相关性
- 信息充分性
- 简洁聚焦性

最终取 LLM 输出的 `overall_score`（0-1），或回退计算 `(d+s+c)/15`。

### 6.7 潜在问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| P6-1 | **Hit Rate 的 normalize_source 过于宽松** | 高 | 仅比较文件名 stem，不区分同一文件的不同版本/摘要 |
| P6-2 | **检索指标基于文档级而非 chunk 级** | 高 | hit_rate/mrr/ndcg 只看"是否命中了正确的文档"，同文档不相关 chunk 也算"命中"，数值虚高 |
| P6-3 | **🔴 BuiltinEvaluator contexts/sources 混淆** | 致命 | `evaluate_single()` 的 `contexts` 参数收到的是 source 路径而非文本内容，导致 faithfulness 评估完全失效 |
| P6-4 | **检索结果无文档级去重** | 高 | top 5 结果全部来自同一文档，检索多样性为零，hit_rate 虚高 |
| P6-5 | **测试集 expected_sources 标注错误** | 高 | LLM 生成的问题可能涉及文档中提到的其他实体，但 expected_sources 只指向生成问题时的源文档 |
| P6-6 | **Faithfulness 评估依赖同一 LLM** | 中 | 用同一个 LLM 既生成答案又评估忠实度，存在"自我评价"偏差 |
| P6-7 | **Answer Relevancy 的 overall_score 由 LLM 自主决定** | 中 | LLM 输出的 overall_score 可能不够稳定 |
| P6-8 | **Chunk-level 指标的 expected_chunks 定位粗糙** | 高 | `_locate_answer_chunks()` 使用关键词+子串重叠的启发式方法，可能遗漏或误匹配 |

---

## 7. 端到端数据流追踪（冒烟测试实例）

以冒烟测试为例，一个完整查询的端到端流程：

```
1. PDF 文件 (data/raw/)
   ↓ pymupdf4llm.to_markdown()
2. Markdown 文本 (data/parsed/)
   ↓ tiktoken encode → 按 512 token 切片 → decode
3. Chunk JSONL (data/chunks/ 或 data/artifacts/)
   ↓ BAAI/bge-large-zh-v1.5 embed (CLS + L2-norm)
4. 向量索引 (Qdrant, data/vector_store/)
   ↓ query embed → cosine search top_k=5
5. 检索结果: 5 个 (chunk_id, text, metadata, score)
   ↓ 拼接为 "参考资料 1/2/3/4/5: {text}"
6. LLM Prompt: system_prompt + user_message
   ↓ Anthropic API call
7. LLM 回答: 纯文本
   ↓
8. 评估: hit_rate/mrr/ndcg + faithfulness/answer_relevancy
```

---

## 8. 问题汇总与优先级

### 🔴 致命级（评估结果完全不可信）

| ID | 阶段 | 问题 | 实际证据 |
|----|------|------|----------|
| P6-3 | 评估 | **BuiltinEvaluator contexts/sources 混淆** | faithfulness 收到文件路径而非文本内容，avg_faithfulness=0.628 完全不可信 |

### 高优先级（直接影响评测结果准确性）

| ID | 阶段 | 问题 | 实际证据 |
|----|------|------|----------|
| P6-4 | 检索 | **检索结果无文档级去重** | 8/10 问题的 top 5 全部来自同一文档 |
| P6-5 | 测试集 | **expected_sources 标注错误** | q010 问光模块公司但 expected 指向中芯国际年报 |
| P6-2 | 评估 | **检索指标基于文档级** | 同文档不相关 chunk 也算命中，hit_rate=0.875 虚高 |
| P2-1 | 分块 | **无重叠导致边界信息丢失** | overlap=0，跨边界信息完全断裂 |
| P2-2 | 分块 | **token 级切割不考虑语义边界** | 可能在句子/段落中间硬切 |
| P3-1 | 向量化 | **512 token 截断冲突** | tiktoken 512 token 可能超过 BGE 512 token 限制 |
| P5-1 | 生成 | **System Prompt 硬编码** | 无法通过实验配置调整 |
| P5-3 | 生成 | **无 Context 长度控制** | 可能超出模型 context window |
| P6-1 | 评估 | **normalize_source 过于宽松** | 仅比较文件名 stem |

### 中优先级（影响效果但非致命）

| ID | 阶段 | 问题 | 影响 |
|----|------|------|------|
| P1-1 | 解析 | 表格解析质量差 | 财务数据丢失/错乱 |
| P1-3 | 解析 | 页眉页脚污染 | 噪声进入检索 |
| P2-3 | 分块 | chunk_id 命名脆弱 | 解析可能出错 |
| P2-4 | 分块 | 无段落感知 | 标题与正文分离 |
| P2-5 | 分块 | 长表格被切碎 | 表格数据不完整 |
| P4-1 | 检索 | 查询未加 BGE 指令前缀 | 检索效果未达最优 |
| P4-2 | 检索 | 无分数过滤 | 低质量匹配也返回 |
| P5-2 | 生成 | Context 拼接无排序提示 | LLM 可能被低质量 context 误导 |
| P5-4 | 生成 | 引用来源要求模糊 | LLM 无法真正引用来源 |
| P6-6 | 评估 | Faithfulness 自评偏差 | 评估不够客观 |
| P6-7 | 评估 | Answer Relevancy 分数不稳定 | 评估结果波动 |
| P6-8 | 评估 | expected_chunks 定位粗糙 | chunk-level 指标虚高 |

---

## 9. 待深入分析项

以下问题需要进一步验证或需要用户确认：

1. **P3-1 量化**: tiktoken cl100k_base 与 BGE tokenizer 的 token 数差异到底有多大？需要实际数据验证
2. **P4-1 验证**: BGE 指令前缀对中文金融领域查询的实际影响
3. **P6-8 量化**: `_locate_answer_chunks()` 的实际准确率，需要人工标注对比
4. **PDF 解析质量抽检**: 随机抽取几个解析后的 Markdown 文件，检查表格和关键数据的完整性
5. **Chunk 边界抽检**: 随机查看几个 chunk，确认语义断裂的严重程度
6. **检索分数分布**: 分析 top_k=5 的实际 cosine score 分布，确定合理的分数阈值

---

*报告持续更新中，随对话深入补充更多细节。*
