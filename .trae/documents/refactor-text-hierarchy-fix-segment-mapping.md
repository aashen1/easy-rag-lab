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
3. 更严重的是：all\_meal 的 chunks 是 BUG-024 旧版产物，文本碎片化，和 Segment 文本完全不同

### 1.3 设计缺陷

Segment 是快速开发中引入的"补丁概念"，没有融入已有的 Page→Chunk 层级体系。它从原始文档重新切分，和 Chunk 无关联，映射全靠文本匹配——这在架构上就是脆弱的。

***

## 二、目标

1. 建立 **Parser 无关** 的文本层级体系，Segment 从 Parser 输出的逻辑片段聚合，而非从全文重新切分
2. Segment→Chunk 映射采用**两阶段策略**：先通过 `page_numbers` 缩小范围，再通过 quote 精确匹配到 chunk 级别
3. `source_chunks` 精确到 **chunk 级别**（行业标准），而非 page 级别

***

## 三、设计调研

### 3.1 主流 PDF 解析工具的输出格式

| 工具                  | 输出格式                                 | 页码信息                     | 结构信息（标题层级）                        |
| ------------------- | ------------------------------------ | ------------------------ | --------------------------------- |
| **pymupdf4llm**（当前） | Markdown（按页 `page_chunks=True`）      | ✅ `page_number`          | ❌ 无                               |
| **MinerU**          | Markdown + JSON（`content_list.json`） | ✅ `page_idx`             | ✅ `text_level`（H1/H2/H3）          |
| **Docling**         | DoclingDocument（JSON）→ Markdown/HTML | ✅ `page_number` + 坐标     | ✅ 完整标题层级 + 表格/图片/公式               |
| **Unstructured**    | 混合格式（元素列表）                           | ✅ `metadata.page_number` | ✅ 元素类型（Title/NarrativeText/Table） |
| **纯 Markdown**      | 单个 .md 文件                            | ❌ 无页码                    | ✅ 标题层级（##/###）                    |

**关键发现**：

* 所有主流 PDF 解析工具**都保留页码信息**，唯一没有页码的是非 PDF 来源的纯 Markdown

* MinerU 和 Docling 额外提供**结构化信息**（标题层级），这是比 Page 更好的语义锚点

* 未来切换解析器时，`page_numbers` 仍然可用；纯 Markdown 场景需要回退到标题切分

### 3.2 检索命中粒度的行业标准

| 指标                       | 粒度          | 定义                          |
| ------------------------ | ----------- | --------------------------- |
| Hit Rate                 | **Chunk 级** | "正确的 chunk 是否出现在 top-K 结果中" |
| MRR                      | **Chunk 级** | "第一个正确 chunk 的排名倒数"         |
| NDCG                     | **Chunk 级** | "所有正确 chunk 的排序质量"          |
| Context Precision（RAGAS） | **Chunk 级** | "检索到的 chunk 中有多少是真正相关的"     |
| Context Recall（RAGAS）    | **Chunk 级** | "答案需要的 chunk 有多少被检索到了"      |

**结论：行业标准统一是 Chunk 级别。** `source_chunks` 必须精确到 chunk，不能是 page 级别。

***

## 四、新的文本层级设计

### 4.1 层级图

```
PDF（原始文件）
  │
  ▼ parser (pymupdf4llm / MinerU / Docling / ...)
  │
Parser 输出 ★ 锚点层 ★
  │  可能是 .pages.json（按页）、.md（按章节）、DoclingDocument（按结构）
  │  不可变，是所有上层概念的唯一数据源
  │
  ├── 向上聚合 ──→ LogicalSegment（逻辑片段，给 LLM 吃的）
  │                  ≈8000 字符
  │                  含 page_numbers=[3,4,5]（来自 pages.json）
  │                  或 section_path="2.1 行业概况"（来自 Markdown 标题）
  │                  或两者都有（来自 Docling）
  │
  └── 向下细分 ──→ Chunk（检索单元）
                     ≈512 token，多种策略可并存
                     含 page_number
```

### 4.2 LogicalSegment 数据结构

```python
@dataclass
class LogicalSegment:
    text: str                           # 片段文本
    segment_index: int                  # 从 0 开始的序号
    page_numbers: list[int]             # 包含的页码（来自 pages.json / Docling）
    section_path: str | None = None     # 章节路径（来自 Markdown H1/H2/H3 / Docling）
    source_type: str = "pages_json"     # "pages_json" | "markdown" | "docling"
```

### 4.3 两阶段映射策略

```
阶段 1：Page 缩范围
  LogicalSegment.page_numbers → 候选 chunks（page_number ∈ page_numbers）
  从几百个 chunk 缩小到十几个

阶段 2：Quote 精确定位
  在候选 chunks 中，用 quote 文本做精确匹配
  因为候选 chunk 和 segment 来自同一份 Page 文本，格式一致，匹配成功率极高
  → source_chunks（精确到 chunk 级别）
```

**为什么两阶段可行？**

* 阶段 1 消除了旧方案"全量文本匹配"的规模问题

* 阶段 2 的候选集很小（十几 vs 几百），且文本格式一致（都是 chunker 从同一份 Page 切出来的），所以匹配不会失败

* 即使阶段 2 匹配失败，回退到 page 级别的 chunk 列表也比空列表好得多

### 4.4 核心原则

1. **Parser 无关**：LogicalSegment 是 Parser 输出的抽象，不绑定 `.pages.json`
2. **Segment 是 chunk-strategy-agnostic 的**：不管用什么 chunk 策略，Segment 都一样
3. **映射优先用 page\_numbers，回退用 section\_path，兜底用文本匹配**
4. **source\_chunks 精确到 chunk 级别**（行业标准）

***

## 五、具体改动步骤

### Step 1：新增 `_build_segments_from_pages()` 方法

**文件**：`src/test_generator.py`

从 Page 列表聚合 Segment。

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

* `text`: 拼接后的文本

* `segment_index`: 从 0 开始的序号

* `page_numbers`: 包含的页码列表（如 `[3, 4, 5]`）

* `start_char`: 在拼接文本中的起始字符位置

* `end_char`: 在拼接文本中的结束字符位置

* `source_type`: `"pages_json"`

**聚合算法**：

1. 按 page\_number 排序
2. 逐页累加字符数
3. 当累计字符数 ≥ target\_chars 时，当前批次成为一个 segment
4. 尾部不足 target\_chars 的也成一个 segment
5. 在 page 边界处切分，保证文本完整性

**保留** **`_segment_document()`** **不删除**，标记为 deprecated，供非 pages.json 格式文档回退使用。

### Step 2：新增 `_locate_source_chunks()` 方法（两阶段映射）

**文件**：`src/test_generator.py`

替换现有的 `_locate_chunks_by_quote()` 和 `_locate_multi_hop_chunks()`。

**新方法签名**：

```python
def _locate_source_chunks(
    self,
    page_numbers: list[int],
    quote: str,
    doc_chunks: list[dict[str, Any]],
) -> list[str]:
```

**两阶段逻辑**：

```python
# 阶段 1：通过 page_numbers 缩小候选范围
candidate_chunks = [
    chunk for chunk in doc_chunks
    if chunk.get("metadata", {}).get("page_number") in set(page_numbers)
]

if not candidate_chunks:
    return []

# 阶段 2：在候选 chunks 中用 quote 精确匹配
matching_chunk_ids = []
for chunk in candidate_chunks:
    chunk_text = chunk.get("text", "")
    if quote in chunk_text:
        matching_chunk_ids.append(chunk["chunk_id"])
    else:
        verification = self._verify_quote_in_segment(quote, chunk_text)
        if verification["found"]:
            matching_chunk_ids.append(chunk["chunk_id"])

# 阶段 2 匹配失败时，回退到 page 级别（返回候选范围内所有 chunks）
if not matching_chunk_ids:
    logger.debug(
        f"Quote not found in candidate chunks, "
        f"falling back to page-level mapping for pages {page_numbers}"
    )
    return [chunk["chunk_id"] for chunk in candidate_chunks]

return matching_chunk_ids
```

**关键改进**：

* 候选集从全量 chunks 缩小到 page 范围内的 chunks

* 精确匹配在候选集内进行，格式一致，成功率高

* 匹配失败时回退到 page 级别，不会返回空列表

### Step 3：新增 `_load_document_pages()` 方法

**文件**：`src/test_generator.py`

从 `.pages.json` 文件加载原始页面数据。

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
3. 按 meal\_config.pdf\_files 过滤
4. 解析 JSON，返回每页的 page\_number 和 text

### Step 4：修改 `_generate_hybrid_question()` 的签名和逻辑

**文件**：`src/test_generator.py`

**改动**：

1. 移除 `segment_chunk_map` 参数
2. source\_chunks 定位改用两阶段映射：

**旧逻辑**：

```python
source_chunks = self._locate_chunks_by_quote(
    quote, selected_segments, segment_chunk_map, doc_chunks
)
```

**新逻辑**（单跳）：

```python
page_numbers = selected_segments[0].get("page_numbers", [])
quote = first_evidence.get("quote", "")
source_chunks = self._locate_source_chunks(
    page_numbers, quote, doc_chunks
)
```

**新逻辑**（多跳）：

```python
all_page_numbers = set()
all_quotes = []
for seg in selected_segments:
    all_page_numbers.update(seg.get("page_numbers", []))
for ev in validation["verified_evidence"]:
    if ev.get("quote"):
        all_quotes.append(ev["quote"])

chunk_id_set = set()
for quote in all_quotes:
    chunk_ids = self._locate_source_chunks(
        sorted(all_page_numbers), quote, doc_chunks
    )
    chunk_id_set.update(chunk_ids)
source_chunks = sorted(chunk_id_set)
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
    for seg in segments:
        seg["page_numbers"] = []
        seg["source_type"] = "fallback"
```

同时移除 `segment_chunk_map` 的生成和传递。

需要在 `generate_golden_testset()`、`generate_document_testset()`、`generate_hybrid_testset()` 等方法中：

1. 调用 `_load_document_pages()` 获取 pages 数据
2. 将 `doc_pages_map` 传入主循环

### Step 6：修改 `_validate_evidence()` 中的 segment\_index 验证

**文件**：`src/test_generator.py`

当前 `_validate_evidence()` 用 `segment_index` 查找 segment，验证 quote 是否在 segment 中。新架构下 segment 仍有 `segment_index`，所以这部分逻辑**不需要大改**。

但需要增加一个优化：当 quote 在 segment 中找不到时，可以通过 `page_numbers` 扩大搜索范围——查找同一 page 的其他 segment。

### Step 7：更新测试

**文件**：`tests/test_test_generator.py`

1. 新增 `_build_segments_from_pages()` 的测试：

   * 短文档（1-2 页）返回单个 segment

   * 长文档（多页）返回多个 segment

   * 每个 segment 包含正确的 `page_numbers`

   * 空文档返回空列表

   * 单页超长文档（>8000 字符）返回单个 segment

   * 每个 segment 包含 `source_type = "pages_json"`

2. 新增 `_locate_source_chunks()` 的测试：

   * 正常两阶段映射：page 缩范围 + quote 精确匹配

   * quote 在候选 chunk 中精确匹配成功

   * quote 需要模糊匹配才成功

   * quote 匹配失败时回退到 page 级别

   * 空页码列表返回空

   * 无匹配页码返回空

   * 跨页 chunk（`cross_page=True`）正确映射

3. 保留现有 `_segment_document()` 测试，标记为 deprecated 测试

4. 修改 `_map_segments_to_chunks()` 测试：标记为 deprecated

5. 修改 `_locate_chunks_by_quote()` 测试：标记为 deprecated

### Step 8：标记废弃方法

以下方法标记为 `@deprecated`，不删除（避免破坏其他可能的调用者）：

* `_segment_document()` — 保留供非 pages.json 格式回退

* `_map_segments_to_chunks()` — 不再需要

* `_texts_overlap()` — 不再需要

* `_locate_chunks_by_quote()` — 不再需要

* `_locate_multi_hop_chunks()` — 不再需要

* `_locate_answer_chunks()` — 已标记 deprecated

### Step 9：端到端验证

1. 重新生成 20 题 golden test：`pixi run python scripts/generate_golden_testset.py --num-questions 20 --name golden_20_v2 --seed 42`
2. 检查 `source_chunks` 不再全空
3. 验证 `source_chunks` 精确到 chunk 级别（不是 page 级别的所有 chunks）
4. 运行 `pixi run pytest tests/test_test_generator.py -v` 确保测试通过
5. 运行 `pixi run pytest tests/test_golden_testset.py -v` 确保 golden 测试通过
6. 运行 `pixi run lint` 确保代码质量

***

## 六、改动范围汇总

| 文件                             | 改动类型 | 说明                                                                                                         |
| ------------------------------ | ---- | ---------------------------------------------------------------------------------------------------------- |
| `src/test_generator.py`        | 新增方法 | `_build_segments_from_pages()`, `_locate_source_chunks()`, `_load_document_pages()`                        |
| `src/test_generator.py`        | 修改方法 | `_generate_hybrid_question()` — 移除 segment\_chunk\_map，改用两阶段映射                                             |
| `src/test_generator.py`        | 修改方法 | `generate_golden_testset()` — 加载 pages 数据，替换 segment 生成                                                    |
| `src/test_generator.py`        | 修改方法 | `generate_document_testset()` — 同上                                                                         |
| `src/test_generator.py`        | 修改方法 | `generate_hybrid_testset()` — 同上                                                                           |
| `src/test_generator.py`        | 标记废弃 | `_map_segments_to_chunks()`, `_texts_overlap()`, `_locate_chunks_by_quote()`, `_locate_multi_hop_chunks()` |
| `tests/test_test_generator.py` | 新增测试 | `_build_segments_from_pages()`, `_locate_source_chunks()`                                                  |
| `tests/test_test_generator.py` | 修改测试 | 适配新签名                                                                                                      |

***

## 七、风险评估

| 风险                                      | 概率 | 影响 | 缓解措施                                                                         |
| --------------------------------------- | -- | -- | ---------------------------------------------------------------------------- |
| `_generate_hybrid_question` 签名变更影响其他调用者 | 低  | 中  | 全局搜索确认所有调用点                                                                  |
| Page 聚合的 segment 边界不够自然                 | 低  | 低  | Page 边界本身就是天然语义边界，比字符切分更好                                                    |
| 非 pages.json 格式文档（.md）无法使用新方法           | 低  | 低  | 保留 `_segment_document()` 作为回退，segment 标记 `source_type="fallback"`            |
| 两阶段映射中 quote 在候选 chunk 中仍然匹配失败          | 低  | 中  | 回退到 page 级别映射，不会返回空列表；且因为候选 chunk 和 segment 来自同一份 Page 文本，格式一致，匹配成功率应远高于旧方案  |
| 未来切换 Parser 后 page\_numbers 不可用         | 低  | 低  | 所有主流 PDF 解析器都保留页码；纯 Markdown 场景回退到 `_segment_document()` + `section_path` 映射 |

***

## 八、不在本次范围内的事项

* 数值幻觉问题（第二个问题）

* 专有名词误报问题（第三个问题）

* Missing 类型生成困难问题（第四个问题）

* `_validate_answer_evidence_consistency()` 的优化

* Chunk 策略扩展（语义分块、父子块等）

* Markdown 标题切分策略（`section_path` 字段预留，但本次不实现）

* Docling / MinerU 解析器适配

