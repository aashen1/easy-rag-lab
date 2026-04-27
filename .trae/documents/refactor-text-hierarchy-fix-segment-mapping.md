# 计划书：重构文本层级，修复 Segment-Chunk 映射错配

## 一、问题背景

### 1.1 现象

Golden test 生成后，20/20 题的 `source_chunks` 全部为空列表，导致评测时 Hit Rate / MRR / NDCG 等检索指标无法计算。

### 1.2 根因

项目中存在 4 种文本尺度（PDF → Page → Chunk / Segment），但 Segment 和 Chunk 来自**两条不兼容的文本管线**：

```
Segment 文本 ← .pages.json 各页 text 拼接 → 原始 Markdown 格式（"## 太阳能"）
Chunk 文本   ← chunker 用 BGE tokenizer 分词后重建 → token 碎片化格式（"# # 太 阳 能"）
```

两条管线在字符级别无法对齐，导致：
1. 位置映射失败（chunk 没有 `start_index/end_index`，只有 `start_token/end_token` 且是页内偏移）
2. 文本匹配失败（`_texts_overlap()` 的归一化不够强，30 字符窗口永远匹配不上）
3. 更严重的是：all_meal 的 chunks 是 BUG-024 旧版产物，文本碎片化，和 Segment 文本完全不同

### 1.3 设计缺陷

Segment 是快速开发中引入的"补丁概念"，没有融入已有的 Page→Chunk 层级体系。它从原始文档重新切分，和 Chunk 无关联，映射全靠文本匹配——这在架构上就是脆弱的。

---

## 二、目标

建立以 **Page 为锚点** 的文本层级体系，让 Segment 从 Page 聚合而非从全文重新切分，使 Segment→Chunk 映射通过 `page_number` 天然完成，彻底消除文本匹配的脆弱性。

---

## 三、新的文本层级设计

```
PDF（原始文件）
  │
  ▼ parser (pymupdf4llm)
  │
Page (.pages.json) ★ 锚点层 ★
  │  每页一段 Markdown，含 page_number
  │  不可变，是所有上层概念的唯一数据源
  │
  ├── 向上聚合 ──→ Segment（Page 聚合，给 LLM 吃的）
  │                  ≈8000 字符
  │                  含 page_numbers=[3,4,5]
  │                  映射：segment.page_numbers ∩ chunk.page_number → source_chunks
  │
  └── 向下细分 ──→ Chunk（Page 细分，给检索用的）
                     ≈512 token，多种策略可并存
                     含 page_number
                     映射：chunk.page_number ∈ segment.page_numbers → 属于该 segment
```

**核心原则**：
1. Page 是唯一数据源，Segment 和 Chunk 都从 Page 派生
2. Segment 是 chunk-strategy-agnostic 的——不管用什么 chunk 策略，Segment 都一样
3. 映射永远通过 page_number，简单可靠

---

## 四、具体改动步骤

### Step 1：新增 `_build_segments_from_pages()` 方法

**文件**：`src/test_generator.py`

替换现有的 `_segment_document()` 方法。新方法从 Page 列表聚合 Segment，而非从全文重新切分。

**新方法签名**：
```python
def _build_segments_from_pages(
    self,
    pages: list[dict[str, Any]],
    target_chars: int = 8000,
) -> list[dict[str, Any]]:
```

**输入**：pages 列表，每个 page 含 `page_number` 和 `text`

**输出**：segment 列表，每个 segment 含：
- `text`: 拼接后的文本（`"\n\n".join(page.text for page in included_pages)`）
- `segment_index`: 从 0 开始的序号
- `page_numbers`: 包含的页码列表（如 `[3, 4, 5]`）
- `start_char`: 在拼接文本中的起始字符位置（第一个 page 的起始位置）
- `end_char`: 在拼接文本中的结束字符位置

**聚合算法**：
1. 按 page_number 排序
2. 逐页累加字符数
3. 当累计字符数 ≥ target_chars 时，当前批次成为一个 segment
4. 尾部不足 target_chars 的也成一个 segment
5. 在 page 边界处切分（不在句子中间切），保证文本完整性

**保留 `_segment_document()` 不删除**，标记为 deprecated，供非 pages.json 格式文档回退使用。

### Step 2：新增 `_get_source_chunks_by_pages()` 方法

**文件**：`src/test_generator.py`

替换现有的 `_locate_chunks_by_quote()` 和 `_locate_multi_hop_chunks()` 中的映射逻辑。

**新方法签名**：
```python
def _get_source_chunks_by_pages(
    self,
    page_numbers: list[int],
    doc_chunks: list[dict[str, Any]],
) -> list[str]:
```

**逻辑**：
```python
return [
    chunk["chunk_id"]
    for chunk in doc_chunks
    if chunk.get("metadata", {}).get("page_number") in page_numbers
]
```

**一行列表推导，零文本匹配，零位置计算。**

### Step 3：新增 `_load_document_pages()` 方法

**文件**：`src/test_generator.py`

从 `.pages.json` 文件加载原始页面数据，供 `_build_segments_from_pages()` 使用。

**新方法签名**：
```python
def _load_document_pages(
    self,
    meal_config: MealConfig,
) -> dict[str, list[dict[str, Any]]]:
```

**返回**：`{doc_name: [{"page_number": 1, "text": "..."}, ...]}`

**逻辑**：
1. 通过 `_resolve_parsed_dir()` 找到 parsed 目录
2. 扫描所有 `.pages.json` 文件
3. 按 meal_config.pdf_files 过滤
4. 解析 JSON，返回每页的 page_number 和 text

### Step 4：修改 `_generate_hybrid_question()` 的签名和逻辑

**文件**：`src/test_generator.py`

**改动**：
1. 移除 `segment_chunk_map` 参数
2. 在 source_chunks 定位逻辑中，用 `_get_source_chunks_by_pages(segment.page_numbers, doc_chunks)` 替代 `_locate_chunks_by_quote()`
3. 对于多跳问题，合并所有 evidence 涉及的 segment 的 page_numbers，再调用 `_get_source_chunks_by_pages()`

**旧逻辑**（删除）：
```python
source_chunks = self._locate_chunks_by_quote(
    quote, selected_segments, segment_chunk_map, doc_chunks
)
```

**新逻辑**：
```python
all_page_numbers = set()
for seg in selected_segments:
    all_page_numbers.update(seg.get("page_numbers", []))
source_chunks = self._get_source_chunks_by_pages(
    sorted(all_page_numbers), doc_chunks
)
```

### Step 5：修改所有调用 `_segment_document` + `_map_segments_to_chunks` 的地方

**文件**：`src/test_generator.py`

项目中有 4 处调用（document 策略、hybrid 策略、golden 策略的主循环和补充循环），全部改为：

**旧代码**：
```python
segments = self._segment_document(doc_content, self.segment_size)
segment_chunk_map = self._map_segments_to_chunks(segments, doc_chunks)
```

**新代码**：
```python
pages = doc_pages_map.get(doc_name, [])
if pages:
    segments = self._build_segments_from_pages(pages, self.segment_size)
else:
    segments = self._segment_document(doc_content, self.segment_size)
```

同时移除 `segment_chunk_map` 的生成和传递。

需要在 `generate_golden_testset()`、`generate_document_testset()`、`generate_hybrid_testset()` 等方法中：
1. 调用 `_load_document_pages()` 获取 pages 数据
2. 将 `doc_pages_map` 传入主循环

### Step 6：修改 `_validate_evidence()` 中的 segment_index 验证

**文件**：`src/test_generator.py`

当前 `_validate_evidence()` 用 `segment_index` 查找 segment，验证 quote 是否在 segment 中。新架构下 segment 仍有 `segment_index`，所以这部分逻辑**不需要大改**。

但需要增加一个优化：当 quote 在 segment 中找不到时，可以通过 `page_numbers` 扩大搜索范围——查找同一 page 的其他 segment。

### Step 7：更新测试

**文件**：`tests/test_test_generator.py`

1. 新增 `_build_segments_from_pages()` 的测试：
   - 短文档（1-2 页）返回单个 segment
   - 长文档（多页）返回多个 segment
   - 每个 segment 包含正确的 `page_numbers`
   - 空文档返回空列表
   - 单页超长文档（>8000 字符）返回单个 segment

2. 新增 `_get_source_chunks_by_pages()` 的测试：
   - 正常映射：给定 page_numbers，返回对应的 chunk_id 列表
   - 空页码列表返回空
   - 无匹配页码返回空
   - 跨页 chunk（`cross_page=True`）正确映射

3. 修改现有 `_segment_document()` 测试：保留，标记为 deprecated 测试

4. 修改 `_map_segments_to_chunks()` 测试：标记为 deprecated

5. 修改 `_locate_chunks_by_quote()` 测试：标记为 deprecated

### Step 8：标记废弃方法

以下方法标记为 `@deprecated`，不删除（避免破坏其他可能的调用者）：

- `_segment_document()` — 保留供非 pages.json 格式回退
- `_map_segments_to_chunks()` — 不再需要
- `_texts_overlap()` — 不再需要
- `_locate_chunks_by_quote()` — 不再需要
- `_locate_multi_hop_chunks()` — 不再需要
- `_locate_answer_chunks()` — 已标记 deprecated

### Step 9：端到端验证

1. 重新生成 20 题 golden test：`pixi run python scripts/generate_golden_testset.py --num-questions 20 --name golden_20_v2 --seed 42`
2. 检查 `source_chunks` 不再全空
3. 运行 `pixi run pytest tests/test_test_generator.py -v` 确保测试通过
4. 运行 `pixi run pytest tests/test_golden_testset.py -v` 确保 golden 测试通过
5. 运行 `pixi run lint` 确保代码质量

---

## 五、改动范围汇总

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `src/test_generator.py` | 新增方法 | `_build_segments_from_pages()`, `_get_source_chunks_by_pages()`, `_load_document_pages()` |
| `src/test_generator.py` | 修改方法 | `_generate_hybrid_question()` — 移除 segment_chunk_map 参数 |
| `src/test_generator.py` | 修改方法 | `generate_golden_testset()` — 加载 pages 数据，替换 segment 生成 |
| `src/test_generator.py` | 修改方法 | `generate_document_testset()` — 同上 |
| `src/test_generator.py` | 修改方法 | `generate_hybrid_testset()` — 同上 |
| `src/test_generator.py` | 标记废弃 | `_map_segments_to_chunks()`, `_texts_overlap()`, `_locate_chunks_by_quote()`, `_locate_multi_hop_chunks()` |
| `tests/test_test_generator.py` | 新增测试 | `_build_segments_from_pages()`, `_get_source_chunks_by_pages()` |
| `tests/test_test_generator.py` | 修改测试 | 适配新签名 |

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| `_generate_hybrid_question` 签名变更影响其他调用者 | 低 | 中 | 全局搜索确认所有调用点 |
| Page 聚合的 segment 边界不够自然（在页中间截断语义） | 低 | 低 | Page 边界本身就是天然语义边界，比字符切分更好 |
| 非 pages.json 格式文档（.md）无法使用新方法 | 低 | 低 | 保留 `_segment_document()` 作为回退 |
| source_chunks 粒度变粗（整个 page 的 chunk 都算） | 中 | 低 | 这是合理的——检索评测本身就按 page 级别评估也说得通；后续可以加 quote→chunk 精细匹配作为优化 |

---

## 七、不在本次范围内的事项

- 数值幻觉问题（第二个问题）
- 专有名词误报问题（第三个问题）
- Missing 类型生成困难问题（第四个问题）
- `_validate_answer_evidence_consistency()` 的优化
- Chunk 策略扩展（语义分块、父子块等）
