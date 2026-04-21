# 下游链路适配意见：页感知解析后的 RAG 全链路升级方案

> **目的**：本文档为 v0.1.9+ 的 RAG 链路升级提供可操作的指导。PDF→MD 环节已完成页感知重构（`page_chunks=True`、`.pages.json` 格式、`ignore_code`/`force_text`/`ocr_language` 精调），下游各环节应针对性修改以充分消化这些改进，实现 RAG 效果的总体提升。
>
> **使用方式**：开新对话时直接引用本文档，按优先级逐步实施。
>
> **版本**：v0.1.9 前置

***

## 0. 现状诊断：页感知解析提供了什么新能力

| 新能力 | 来源 | 当前下游利用情况 |
|--------|------|-----------------|
| **页码元数据** | `page_chunks=True` → chunk metadata 含 `page_number` | ❌ 仅存入 Qdrant payload，检索/生成/评估环节均未使用 |
| **TOC 条目** | `.pages.json` 每页含 `toc_items` | ❌ 完全未利用 |
| **表格数据** | `.pages.json` 每页含 `tables` | ❌ 完全未利用 |
| **更干净的文本** | `ignore_code=True` + `header: false`/`footer: false` | ✅ 自动生效，下游无需修改 |
| **OCR 中英文** | `ocr_language: "chi_sim+eng"` | ✅ 自动生效 |
| **页级独立分块** | `chunk_text_page_aware()` | ✅ 已实现，但分块策略仍为固定长度 |

**核心发现**：页感知解析的"硬能力"（页码、TOC、表格）已经就绪，但下游链路仍在按旧的"无页码"模式运行，新能力被浪费。

***

## 1. 升级层次与优先级

```
层次 0（紧急）：修复 config.yaml 策略名不一致 → chunker.strategy 应反映实际使用 page_aware_fixed
层次 1（高优）：页码元数据贯通 → 检索结果携带页码，生成时引用页码
层次 2（高优）：分块策略增强 → TOC 感知分块 + 表格保护分块
层次 3（中优）：检索增强 → 页码过滤 + 邻页扩展 + 元数据加权
层次 4（中优）：评估体系适配 → 页码引用准确率指标
层次 5（低优）：Embedding 增强 → 上下文注入 + 表格独立嵌入
```

***

## 2. 层次 0：修复 config.yaml 策略名不一致

### 问题

[config.yaml:87](file:///b:/project/ash-easy-rag/config.yaml#L87) 中 `chunker.strategy` 仍为 `"fixed"`，但实际在 `page_chunks=True` 时使用的是 `page_aware_fixed` 策略。这会导致：
- 实验配置中 `strategy` 字段与实际行为不符
- 评估报告中策略标识不准确
- 用户误解当前分块方式

### 修改

```yaml
chunker:
  strategy: "page_aware_fixed"   # 当 page_chunks=True 时自动使用
```

或者在代码层面让 `build_chunks_if_needed()` 忽略 config 中的 `strategy`，根据 `page_chunks` 自动选择。**推荐后者**，避免用户手动维护两个配置的一致性。

### 验证

- 确认 Meal 的 config_snapshot 中 `chunker.strategy` 与实际分块函数一致
- 确认评估报告中策略标识正确

***

## 3. 层次 1：页码元数据贯通（P0）

这是最关键、收益最直接的改进。当前页码数据已存在于 chunk metadata 中，但从未被下游消费。

### 3.1 检索结果携带页码

**当前代码**：[pipeline.py:452-455](file:///b:/project/ash-easy-rag/src/pipeline.py#L452-L455)

```python
sources = [
    result["metadata"].get("source", "Unknown") for result in results
]
chunk_ids = [result.get("chunk_id", "") for result in results]
```

**问题**：`page_number` 在 metadata 中但未被提取到顶层。

**修改**：在 `pipeline.query()` 返回的 response 中新增 `page_numbers` 字段：

```python
page_numbers = [
    result["metadata"].get("page_number") for result in results
]
response["page_numbers"] = page_numbers
```

同步在 multi-query 分支（约 L414-427）做相同修改。

### 3.2 生成时引用页码

**当前代码**：[generator.py:121-127](file:///b:/project/ash-easy-rag/src/generator.py#L121-L127)

```python
if sources:
    context_text = "\n\n".join([
        f"参考资料 {i+1}（来源：{Path(sources[i]).stem}）:\n{ctx}"
        for i, ctx in enumerate(contexts)
    ])
```

**修改**：当 `page_numbers` 可用时，在来源标注中加入页码：

```python
if sources and page_numbers:
    context_text = "\n\n".join([
        f"参考资料 {i+1}（来源：{Path(sources[i]).stem}，第{page_numbers[i]}页）:\n{ctx}"
        for i, ctx in enumerate(contexts)
    ])
elif sources:
    context_text = "\n\n".join([
        f"参考资料 {i+1}（来源：{Path(sources[i]).stem}）:\n{ctx}"
        for i, ctx in enumerate(contexts)
    ])
```

同时更新 `Generator.generate()` 的签名，新增 `page_numbers: list[int | None] | None = None` 参数。

**更新 system prompt**：在 `DEFAULT_SYSTEM_PROMPT` 中增加页码引用指导：

```
4. 回答时请引用具体的来源和页码（如"根据贵州茅台2023年年度报告第15页..."）
```

### 3.3 BM25 检索结果携带页码

**当前代码**：[bm25_retriever.py](file:///b:/project/ash-easy-rag/src/bm25_retriever.py) 的 `retrieve()` 返回结果中已包含 `metadata`（含 `page_number`），无需修改。

### 3.4 预期收益

| 环节 | 收益 |
|------|------|
| 生成 | LLM 可引用具体页码，回答可信度提升 |
| 用户体验 | 用户可定位到原文具体页，溯源效率提升 |
| 评估 | 可量化"页码引用准确率"指标 |

***

## 4. 层次 2：分块策略增强（P1）

当前页感知分块是"固定长度 + 页边界切断"，未利用 `.pages.json` 中的 TOC 和表格结构信息。

### 4.1 TOC 感知分块

**原理**：`.pages.json` 中每页的 `toc_items` 包含文档目录结构（标题层级）。利用这些信息可以在标题边界处分块，而非在固定 token 数处切断。

**设计**：

```python
def chunk_text_toc_aware(
    page_chunks: list[dict],
    source_name: str,
    chunk_size: int = 512,
    max_chunk_size: int = 1024,
    encoding_name: str = "cl100k_base",
) -> list[dict[str, Any]]:
    """Split page-level parsed results at TOC heading boundaries.

    Chunks are split at heading boundaries when possible. If a section
    exceeds max_chunk_size, it falls back to fixed-size splitting.
    """
```

**关键逻辑**：
1. 提取每页的 `toc_items`，构建标题位置索引
2. 在 Markdown 文本中匹配标题行，确定标题位置
3. 以标题为分块边界，同一标题下的内容尽量在同一 chunk
4. 超过 `max_chunk_size` 的段落回退到固定分块

**优先级**：中。实现复杂度较高，但收益显著——标题级分块比固定长度分块更符合语义边界。

### 4.2 表格保护分块

**原理**：金融研报中的财务表格是高价值信息，当前固定长度分块可能在表格中间切断，破坏表格结构。

**设计**：在 `chunk_text_page_aware()` 中增加表格保护逻辑：

1. 检测 Markdown 表格（以 `|` 开头的连续行）
2. 将完整表格视为不可分割单元
3. 如果表格 + 前文超过 `chunk_size`，将表格整体移到下一个 chunk
4. 如果表格本身超过 `chunk_size`，允许在表格行之间切断（次优选择）

```python
def _find_table_boundaries(text: str) -> list[tuple[int, int]]:
    """Find start and end line indices of Markdown tables in text."""
    lines = text.split("\n")
    boundaries = []
    in_table = False
    start = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and not in_table:
            in_table = True
            start = i
        elif not line.strip().startswith("|") and in_table:
            in_table = False
            boundaries.append((start, i - 1))
    if in_table:
        boundaries.append((start, len(lines) - 1))
    return boundaries
```

**优先级**：高。金融研报的财务表格是 RAG 检索的核心目标，保护表格完整性直接影响检索质量。

### 4.3 页间 Overlap

**原理**：当前页感知分块在页边界处强制切断，可能导致跨页内容被拆分（如一段文字跨越第 5 页末尾和第 6 页开头）。

**设计**：在页边界处设置小 overlap（如 1-2 个句子），将上一页末尾的少量内容复制到下一页 chunk 的开头。

```python
def chunk_text_page_aware(
    page_chunks: list[dict],
    source_name: str,
    chunk_size: int = 512,
    overlap: int = 0,
    cross_page_overlap_sentences: int = 1,  # 新增参数
    encoding_name: str = "cl100k_base",
) -> list[dict[str, Any]]:
```

**注意**：cross-page overlap 的 chunk 应标注其 `page_number` 为主要页码（即内容主体所在页），避免页码归属歧义。

**优先级**：低。跨页内容在金融研报中不常见，且 overlap 可能引入重复信息。

***

## 5. 层次 3：检索增强（P1）

### 5.1 邻页扩展（Neighbor Page Expansion）

**原理**：金融研报中，一个完整的信息单元可能跨越 2-3 页（如一张大表格、一段分析文字配图表）。当检索命中某页的 chunk 时，自动扩展到相邻页。

**设计**：

```python
def expand_with_neighbor_pages(
    results: list[dict],
    indexer: VectorIndexer,
    expand_pages: int = 1,
) -> list[dict]:
    """Expand retrieval results with neighbor page chunks.

    For each result, also include chunks from the same source document
    on adjacent pages (expand_pages before and after).
    """
```

**实现要点**：
- 从检索结果的 `metadata.source` 和 `metadata.page_number` 提取文档和页码
- 在 Qdrant 中按 `metadata.source` + `metadata.page_number` 范围过滤查询
- 去重（避免重复 chunk）
- 邻页 chunk 的 score 可设为命中 chunk score 的衰减值（如 0.8x）

**优先级**：中。实现需要 Qdrant 的 payload 过滤查询能力，但收益明显——跨页信息不再遗漏。

### 5.2 页码范围过滤

**原理**：当用户问题明确提到页码或章节时（如"第15页的财务数据"），可直接过滤到对应页码范围。

**设计**：
- 在 `Retriever.retrieve()` 中增加 `page_filter: dict[str, int] | None = None` 参数
- `page_filter` 格式：`{"source": "report.pdf", "page_number": 15}` 或 `{"source": "report.pdf", "page_gte": 10, "page_lte": 20}`
- 使用 Qdrant 的 `Filter` + `FieldCondition` 实现 payload 过滤

**优先级**：低。需要查询理解能力来提取页码意图，实现成本较高。

### 5.3 元数据加权

**原理**：某些元数据特征可暗示 chunk 的重要性，如：
- 包含表格的 chunk 可能比纯文本 chunk 更重要
- 某些章节（如"财务摘要"）比其他章节更重要
- TOC 中的标题层级可反映信息密度

**设计**：在检索后对 score 进行元数据加权调整：

```python
def apply_metadata_boost(
    results: list[dict],
    boost_factors: dict[str, float] | None = None,
) -> list[dict]:
    """Adjust retrieval scores based on chunk metadata.

    boost_factors example:
        {"has_table": 1.2, "heading_level_1": 1.1, "heading_level_2": 1.05}
    """
```

**优先级**：低。需要实验验证哪些元数据特征确实影响检索质量。

***

## 6. 层次 4：评估体系适配（P1）

### 6.1 页码引用准确率指标

**新增评估指标**：`page_citation_accuracy`

**定义**：LLM 回答中引用的页码与 ground truth 页码的一致率。

**实现**：
1. 在 test set 的 ground truth 中新增 `expected_pages: list[int]` 字段
2. 从 LLM 回答中提取页码引用（正则匹配"第N页"）
3. 计算引用页码与期望页码的交集比例

```python
def compute_page_citation_accuracy(
    answer: str,
    expected_pages: list[int],
) -> float:
    """Compute page citation accuracy from answer text."""
    cited_pages = set()
    for match in re.finditer(r"第(\d+)页", answer):
        cited_pages.add(int(match.group(1)))
    if not expected_pages:
        return 1.0 if not cited_pages else 0.0
    overlap = cited_pages & set(expected_pages)
    return len(overlap) / len(set(expected_pages))
```

### 6.2 更新评估框架

**修改**：[eval/evaluators/](file:///b:/project/ash-easy-rag/eval/evaluators/) 中的评估器需适配：
- `retrieval_evaluator`：检索结果中 `page_number` 的命中率
- `generation_evaluator`：生成回答中页码引用的准确率
- `builtin_evaluator`：在现有指标基础上新增 `page_citation_accuracy`

### 6.3 Test Set 扩展

**修改**：在 test set 的 question 中标注 `expected_pages`，便于评估页码引用。

**优先级**：中。评估体系是验证改进效果的基础，但需要先完成层次 1（页码贯通）才能评估。

***

## 7. 层次 5：Embedding 增强（P2）

### 7.1 上下文注入（Context Prefix）

**原理**：当前 embedding 仅基于 chunk 文本本身。如果在 chunk 文本前注入其所属的标题层级信息，embedding 向量将包含更多语义上下文，提升检索精度。

**设计**：

```python
def build_context_prefix(
    toc_items: list[dict],
    page_number: int,
) -> str:
    """Build a context prefix from TOC items for the given page.

    Example output: "第一章 公司概况 > 1.1 业务概述 | 第5页"
    """
```

在 `process_parsed_files_page_aware()` 中，为每个 chunk 的文本添加上下文前缀后再 embedding：

```python
context_prefix = build_context_prefix(page.get("toc_items", []), page_number)
embedding_text = f"{context_prefix}\n{chunk['text']}" if context_prefix else chunk['text']
```

**注意**：
- 上下文前缀仅用于 embedding，不存入 chunk 的 `text` 字段（避免生成时出现冗余信息）
- 需要在 indexer 中区分 `embedding_text` 和 `display_text`
- BGE 模型的 max_length=512，前缀会占用 token 空间，需控制前缀长度

**优先级**：低。需要实验验证上下文前缀对检索质量的实际影响。

### 7.2 表格独立嵌入

**原理**：金融研报中的财务表格是高价值检索目标，但表格文本与正文混合嵌入时，表格的语义可能被正文稀释。

**设计**：
1. 从 `.pages.json` 的 `tables` 字段提取表格数据
2. 为每个表格生成独立的 chunk 和 embedding
3. 表格 chunk 的 metadata 标注 `"chunk_type": "table"`
4. 检索时表格 chunk 可获得独立的 score

**优先级**：低。需要先验证表格提取质量是否足够好。

***

## 8. 实施路线图

### Phase 1：页码贯通（1-2 天）

| 任务 | 优先级 | 依赖 | 规模 |
|------|--------|------|------|
| 修复 config.yaml strategy 不一致 | P0 | 无 | 小 |
| pipeline.query() 返回 page_numbers | P0 | 无 | 小 |
| generator.generate() 接受 page_numbers 参数 | P0 | 上项 | 小 |
| 更新 system prompt 引导页码引用 | P0 | 上项 | 小 |
| 编写测试验证页码贯通 | P0 | 上项 | 中 |

### Phase 2：分块增强（2-3 天）

| 任务 | 优先级 | 依赖 | 规模 |
|------|--------|------|------|
| 表格保护分块 | P1 | 无 | 中 |
| TOC 感知分块 | P1 | 无 | 大 |
| 分块策略自动选择逻辑 | P1 | 上两项 | 小 |
| 编写测试验证分块增强 | P1 | 上项 | 中 |

### Phase 3：检索增强（2-3 天）

| 任务 | 优先级 | 依赖 | 规模 |
|------|--------|------|------|
| 邻页扩展 | P1 | Phase 1 | 中 |
| Qdrant payload 过滤查询 | P1 | Phase 1 | 中 |
| 元数据加权（实验性） | P2 | Phase 2 | 中 |

### Phase 4：评估适配（1-2 天）

| 任务 | 优先级 | 依赖 | 规模 |
|------|--------|------|------|
| page_citation_accuracy 指标 | P1 | Phase 1 | 小 |
| test set 扩展 expected_pages | P1 | Phase 1 | 中 |
| 评估器适配 | P1 | 上两项 | 中 |

### Phase 5：Embedding 增强（实验性，2-3 天）

| 任务 | 优先级 | 依赖 | 规模 |
|------|--------|------|------|
| 上下文前缀注入 | P2 | Phase 2 | 中 |
| 表格独立嵌入 | P2 | Phase 2 | 大 |
| A/B 测试验证效果 | P2 | 上两项 | 中 |

***

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 页码引用幻觉：LLM 可能引用不存在的页码 | 中 | 在 system prompt 中强调"仅引用参考资料中标注的页码"；评估时用 `page_citation_accuracy` 指标监控 |
| 表格保护分块导致 chunk 大小不均 | 低 | 设置 `max_chunk_size` 上限，超限时回退到固定分块 |
| 邻页扩展增加检索噪声 | 中 | 邻页 chunk 使用衰减 score；可配置 `expand_pages=0` 关闭 |
| TOC 感知分块依赖 toc_items 质量 | 中 | pymupdf4llm 的 toc_items 可能为空或不完整，需回退到固定分块 |
| 上下文前缀占用 embedding token 空间 | 低 | 控制前缀长度在 50 token 以内；实验验证效果 |

***

## 10. 与已有 backlog 条目的关联

| Backlog ID | 描述 | 本方案如何推进 |
|------------|------|---------------|
| INV-010 | 元数据增强改善 chunk 命中 | ✅ **直接解决**：page_number 元数据已入库，层次 1 贯通后即可利用 |
| INV-016 | PDF 表格解析质量评估 | ⚠️ **部分缓解**：`ignore_code: true` 减少代码块误标；表格保护分块（层次 2）保护表格完整性 |
| FEAT-024 | 页眉页脚清洗 | ✅ **已解决**：`header: false`/`footer: false` 在 Layout 模式下生效 |
| INV-015 | tiktoken 与 BGE tokenizer 差异 | ⚠️ **仍需关注**：页感知分块未改变 token 计数方式，BGE 512 限制仍可能截断 |

***

## 11. 决策总结

| 问题 | 决策 | 理由 |
|------|------|------|
| 是否立即实施页码贯通？ | ✅ **是** | 成本最低（1-2 天），收益最直接（生成引用页码） |
| 是否实施表格保护分块？ | ✅ **是** | 金融研报核心需求，表格完整性直接影响检索质量 |
| 是否实施 TOC 感知分块？ | ⚠️ **Phase 2** | 收益大但实现复杂，需验证 toc_items 质量 |
| 是否实施邻页扩展？ | ⚠️ **Phase 3** | 需先完成页码贯通，且需实验验证效果 |
| 是否实施上下文前缀注入？ | ❌ **暂缓** | 需要实验验证，且可能占用 embedding token 空间 |
| 是否实施表格独立嵌入？ | ❌ **暂缓** | 依赖表格提取质量，当前 pymupdf4llm 的 tables 字段质量待验证 |
