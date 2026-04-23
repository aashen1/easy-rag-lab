# PDF 预处理链路优化计划

> **计划目标**：解决当前 pymupdf4llm 转换金融研报/年报 PDF 时产生的结构混乱、内容解析错误问题，建立 chunk 与页码的可靠关联机制，为高质量基线测试数据集和准确系统评估奠定基础。
>
> **关联 backlog 项**：INV-016（PDF 表格解析质量评估与替代方案调研）、FEAT-024（页眉页脚清洗）、INV-010（元数据增强改善 chunk 命中）
>
> **版本**：v0.1.9 前置调研与规划

---

## 1. 现状诊断

### 1.1 当前处理链路

```
PDF (data/raw/)
  ↓ pymupdf4llm.to_markdown(pdf_path)   # 默认参数，无自定义
Markdown (data/parsed/ 或 data/artifacts/{data_id}/parsed/)
  ↓ tiktoken encode → 按 512 token 切片 → decode
Chunk JSONL (data/chunks/ 或 data/artifacts/{data_id}/chunks_{hash}/)
  ↓ 向量化 → Qdrant 索引
```

### 1.2 核心问题清单

| ID | 问题 | 严重度 | 根因 | 影响 |
|----|------|--------|------|------|
| P1-1 | **表格解析质量差** | 高 | `to_markdown()` 默认参数对复杂表格（合并单元格、多级表头）处理不佳 | 金融研报财务数据丢失/错乱 |
| P1-2 | **页眉页脚污染** | 中 | 未启用 `header=False, footer=False` | 页码、logo 文字混入正文，影响检索 |
| P1-3 | **无页码元数据** | 高 | 当前链路"PDF → 整篇 MD → token 级切块"，页码信息在 MD 化后丢失 | 无法定位 chunk 所属页码，测试集标注困难 |
| P1-4 | **解析参数未调优** | 中 | 仅使用默认参数，未探索 `table_strategy`, `margins`, `hdr_info` 等参数 | 输出质量未达库本身可达到的上限 |
| P1-5 | **chunk 边界语义断裂** | 高 | token 级硬切，不考虑句子/段落/表格边界 | 跨边界信息丢失，检索质量下降 |

### 1.3 关键代码定位

- **PDF 解析入口**：[src/parser.py](file:///b:/project/w0-easy-rag/src/parser.py#L35-L37) —— `pymupdf4llm.to_markdown(str(pdf_file))` 无参数调用
- **分块入口**：[src/chunker.py](file:///b:/project/w0-easy-rag/src/chunker.py#L11-L97) —— `chunk_text()` 纯 tiktoken 固定长度切割
- **语义分块**：[src/semantic_chunker.py](file:///b:/project/w0-easy-rag/src/semantic_chunker.py#L103-L290) —— 已实现但未在基线使用
- **Meal 管线**：[src/meal.py](file:///b:/project/w0-easy-rag/src/meal.py#L252-L285) —— `build_chunks_if_needed()` 调用固定分块

---

## 2. 技术评估：pymupdf4llm vs PyMuPDF(fitz)

### 2.1 能力对比矩阵

| 能力维度 | pymupdf4llm (当前) | PyMuPDF (fitz) 原生 | 评估结论 |
|----------|-------------------|---------------------|----------|
| **Markdown 转换** | ✅ 内置，单函数调用 | ⚠️ 需自行组装 | pymupdf4llm 更方便，但需调参 |
| **页级输出** | ✅ `page_chunks=True` 返回每页 dict | ✅ `page.get_text()` 逐页提取 | **两者都支持**，pymupdf4llm 更封装 |
| **页码元数据** | ✅ 返回 dict 含 `page_number` | ✅ `page.number` 直接获取 | **两者都支持** |
| **页眉页脚控制** | ✅ `header=False, footer=False` | ⚠️ 需通过 `clip` 区域手动裁剪 | pymupdf4llm 更优 |
| **表格策略** | ✅ `table_strategy` 参数 | ⚠️ 无内置表格识别，需自行处理 | pymupdf4llm 更优 |
| **多栏检测** | ✅ 自动布局分析 | ⚠️ 需自行实现 | pymupdf4llm 更优 |
| **OCR 兜底** | ✅ 自动触发 | ✅ 需手动调用 | pymupdf4llm 更优 |
| **自定义 hdr_info** | ✅ 支持传入 callable | N/A | pymupdf4llm 独有 |
| **精细文本控制** | ⚠️ 封装层限制 | ✅ `get_text("dict")`/`get_text("html")` 等 | fitz 更灵活，但工作量大 |
| **金融文档适配** | ⚠️ 默认参数对复杂表格不佳 | ⚠️ 需大量自定义代码 | **调参优先于替换** |

### 2.2 关键发现：pymupdf4llm 已具备所需能力

根据 [PyMuPDF4LLM 官方 API 文档](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html)，`to_markdown()` 已支持以下关键参数：

```python
# 页级分块模式 —— 解决页码关联问题
pymupdf4llm.to_markdown(doc, page_chunks=True)
# 返回: list[dict]，每个 dict 包含:
#   - "text": 该页 Markdown 文本
#   - "metadata": {"page_number": 1-based, "page_count": N, "file_path": ...}

# 页眉页脚过滤 —— 解决噪声问题
pymupdf4llm.to_markdown(doc, header=False, footer=False)

# 表格策略调优 —— 解决表格解析问题
pymupdf4llm.to_markdown(doc, table_strategy="lines_strict")  # 当前默认
# 可选: "lines", "text", "explicit"

# 边距裁剪 —— 去除边缘噪声
pymupdf4llm.to_markdown(doc, margins=10)  # 裁剪页面边缘 10pt

# 自定义标题检测 —— 改善金融文档结构识别
pymupdf4llm.to_markdown(doc, hdr_info=custom_header_detector)
```

### 2.3 结论：无需替换库，优先调参与重构处理流程

- **不替换为纯 fitz**：pymupdf4llm 的封装价值（布局分析、表格识别、多栏处理、OCR）对金融文档至关重要，自行用 fitz 重建等价功能成本极高
- **优先策略**：深度调优 `to_markdown()` 参数 + 启用 `page_chunks=True` 重构"PDF → 页级 MD → 带页码元数据的 chunk"流程
- **备选策略**：若调优后仍不满足需求，再考虑引入 `marker`/`pdfplumber` 等替代方案做 A/B 对比

---

## 3. Chunk 与页码关联：技术方案决策

### 3.1 方案对比

| 方案 | 描述 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| **A. AI 启发式提取** | 让 LLM 从 MD 文本中搜索 "1/232" 等页码格式 | 无需改动现有链路 | 极不可靠：页码格式不统一、可能被分块截断、幻觉风险 | ❌ 不推荐 |
| **B. 重构为页级处理** | `page_chunks=True` → 每页单独 MD → 页内分块 → chunk 继承页码 | **页码 100% 准确**、结构清晰、支持页级元数据 | 需修改 parser/chunker/meal 管线 | ✅ **推荐** |
| **C. 混合方案** | 先用 fitz 提取每页文本 → 再用 pymupdf4llm 转 MD | 页码直接从 fitz 获取 | 重复解析、性能差、两份文本可能对不齐 | ⚠️ 备选 |

### 3.2 推荐方案 B 的详细设计

```
PDF
  ↓ pymupdf4llm.to_markdown(page_chunks=True)
List[PageChunk]  —— 每个元素: {"text": "该页MD", "metadata": {"page_number": N}}
  ↓ 逐页处理（保持页边界）
每页内分块（token 级或语义级，不跨页）
  ↓ 组装 chunk 元数据
Chunk 元数据包含: page_number, page_start, page_end（支持跨页 chunk 时）
  ↓ 输出 JSONL
```

**关键设计决策**：

1. **分块不跨页**：每页独立分块，确保每个 chunk 的 `page_number` 唯一且精确
2. **页内保留语义分块**：在单页范围内可使用语义分块（基于句子相似度），避免 token 级硬切
3. **元数据结构**：
   ```json
   {
     "chunk_id": "filename_001_p12",
     "text": "...",
     "metadata": {
       "source": "reports/2026光伏.md",
       "page_number": 12,
       "category": "research_report",
       "chunk_index": 1,
       "token_count": 498,
       "strategy": "page_aware_semantic"
     }
   }
   ```

---

## 4. 实施计划

### Phase 1: 解析器增强（Parser Enhancement）

**目标**：让 `parse_pdf()` 支持页级输出和参数自定义

**步骤**：

1. **扩展 `parse_pdf()` 函数签名**
   - 添加 `page_chunks: bool = False` 参数
   - 添加 `parser_options: dict | None = None` 参数（透传 `to_markdown()` 参数）
   - 保持向后兼容：默认行为不变

2. **实现页级 Markdown 输出**
   - 当 `page_chunks=True` 时，调用 `to_markdown(page_chunks=True)`
   - 返回 `list[dict]` 而非 `str`，每个元素包含 `text` 和 `metadata`（含 `page_number`）

3. **配置化解析参数**
   - 在 `config.yaml` 的 `parser` 段添加：
     ```yaml
     parser:
       input_dir: "data/raw"
       output_dir: "data/parsed"
       algorithm: "pymupdf4llm"
       options:
         header: false          # 过滤页眉
         footer: false          # 过滤页脚
         table_strategy: "lines_strict"  # 表格检测策略
         margins: 10            # 裁剪边缘 10pt
         page_chunks: true      # 启用页级输出（新）
     ```

4. **更新 `parse_all_pdfs()`**
   - 支持页级输出时的文件命名：`{filename}_p{page:03d}.md`
   - 或统一存为 JSON：`{filename}.pages.json`

5. **测试**
   - 验证页级输出时 `page_number` 正确性
   - 验证 `header=False, footer=False` 确实过滤噪声
   - 验证不同 `table_strategy` 对金融表格的影响

---

### Phase 2: 分块器重构（Chunker Refactoring）

**目标**：支持页感知的分块，chunk 元数据携带页码

**步骤**：

1. **新增 `chunk_text_page_aware()` 函数**
   - 输入：`list[PageChunk]`（每页文本 + 页码）
   - 处理：逐页独立分块，不跨页
   - 输出：chunk 列表，每个 chunk 的 `metadata` 包含 `page_number`

2. **新增 `process_parsed_files_page_aware()` 函数**
   - 读取页级解析结果（JSON 格式）
   - 调用 `chunk_text_page_aware()`
   - 输出标准 JSONL 格式（与现有格式兼容，仅增加 `page_number` 字段）

3. **语义分块页感知适配**
   - 修改 `semantic_chunker.py`，新增 `chunk_text_semantic_page_aware()`
   - 在单页范围内进行语义边界检测，避免跨页

4. **更新 `meal.py` 的 `build_chunks_if_needed()`**
   - 检测解析结果格式：若存在 `.pages.json` 则使用页感知的分块流程
   - 否则回退到现有流程（向后兼容）

5. **测试**
   - 验证 chunk 的 `page_number` 与实际 PDF 页码一致
   - 验证分块不跨页
   - 验证与现有索引/检索流程兼容

---

### Phase 3: 索引与检索适配（Indexer & Retriever Adaptation）

**目标**：确保新增 `page_number` 元数据在索引和检索中可用

**步骤**：

1. **验证索引流程**
   - `VectorIndexer.index_chunks()` 已支持任意 `metadata`，无需修改
   - 确认 `page_number` 会随 `metadata` 存入 Qdrant payload

2. **验证检索流程**
   - `Retriever.retrieve()` 返回的 `metadata` 已包含 `page_number`
   - 在 RAGPipeline 中可利用 `page_number` 做来源引用

3. **测试**
   - 端到端验证：检索结果的 `metadata.page_number` 可正确读取

---

### Phase 4: 质量评估与对比实验（Quality Evaluation）

**目标**：量化解析优化前后的效果差异

**步骤**：

1. **建立解析质量评估集**
   - 选取 3-5 份代表性金融 PDF（年报、研报各覆盖）
   - 人工标注关键信息点（财务数据、表格内容、章节标题）

2. **A/B 对比实验**
   - A 组：默认参数 `to_markdown()`（当前基线）
   - B 组：调优参数（`header=False, footer=False, margins=10, table_strategy=...`）
   - C 组：页级输出 + 页感知分块
   - 评估指标：
     - 表格结构保留率（人工检查）
     - 页眉页脚噪声出现次数
     - chunk 页码准确率
     - 下游检索 hit_rate / faithfulness

3. **决策是否全量切换**
   - 若 B/C 组显著优于 A 组 → 更新默认配置
   - 若提升有限 → 保留为可选实验配置

---

## 5. 配置变更清单

### 5.1 config.yaml 变更

```yaml
# 当前配置
parser:
  input_dir: "data/raw"
  output_dir: "data/parsed"

# 目标配置
parser:
  input_dir: "data/raw"
  output_dir: "data/parsed"
  algorithm: "pymupdf4llm"
  options:
    header: false
    footer: false
    table_strategy: "lines_strict"
    margins: 10
    page_chunks: true
```

### 5.2 parser 配置 hash 更新

`meal.py` 中的 `compute_parser_config_hash()` 当前仅 hash `algorithm`：

```python
relevant = {"algorithm": parser_config.get("algorithm", "pymupdf4llm")}
```

**需扩展为包含 `options`**，使不同解析参数产生不同的 parser hash，触发重新解析：

```python
relevant = {
    "algorithm": parser_config.get("algorithm", "pymupdf4llm"),
    "options": parser_config.get("options", {}),
}
```

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| `page_chunks=True` 改变输出格式，破坏现有缓存逻辑 | 中 | 新格式使用不同文件扩展名（`.pages.json`），与旧 `.md` 共存；`ArtifactCache` 按 parser hash 隔离 |
| `header=False, footer=False` 误过滤正文内容 | 低 | 抽样检查：对比过滤前后的文本差异，确认仅去除页眉页脚 |
| `table_strategy` 调优效果不确定 | 中 | 先在小样本上 A/B 测试，再决定默认策略 |
| 页感知分块导致 chunk 数量增加（每页边界强制切断） | 低 | 可在页边界处设置小 overlap（如 20 token）缓解 |
| 配置 hash 扩展导致现有 meal 缓存失效 | 低 | 预期行为：配置变更应触发重新构建 |

---

## 7. 任务分解与优先级

| 任务 | 所属 Phase | 优先级 | 依赖 | 预估规模 |
|------|-----------|--------|------|----------|
| T1: 扩展 `parse_pdf()` 支持页级输出和自定义参数 | Phase 1 | P0 | 无 | 中 |
| T2: 更新 `config.yaml` 解析器配置结构 | Phase 1 | P0 | T1 | 小 |
| T3: 更新 `parse_all_pdfs()` 处理页级输出 | Phase 1 | P0 | T1 | 中 |
| T4: 扩展 parser config hash 包含 options | Phase 1 | P0 | T2 | 小 |
| T5: 实现 `chunk_text_page_aware()` | Phase 2 | P0 | T3 | 中 |
| T6: 实现 `process_parsed_files_page_aware()` | Phase 2 | P0 | T5 | 中 |
| T7: 语义分块页感知适配 | Phase 2 | P1 | T5 | 中 |
| T8: 更新 `meal.py` 支持页感知分块 | Phase 2 | P0 | T6 | 中 |
| T9: 端到端测试（索引/检索） | Phase 3 | P0 | T8 | 小 |
| T10: 建立解析质量评估集 | Phase 4 | P1 | 无 | 小 |
| T11: A/B 对比实验 | Phase 4 | P1 | T10 | 中 |
| T12: 更新单元测试 | 贯穿 | P0 | 各任务 | 中 |
| T13: 更新文档（pipeline-deep-audit.md 等） | 贯穿 | P1 | 各任务 | 小 |

---

## 8. 决策总结

| 问题 | 决策 | 理由 |
|------|------|------|
| 是否优先优化预处理链路？ | ✅ **是** | PDF→MD 是整个 RAG 链路的信息源头，源头质量差则后续优化收益被抵消 |
| 是否临时采用 AI 提取页码？ | ❌ **否** | 启发式方法不可靠，应直接重构流程使页码成为一等公民 |
| 是否替换 pymupdf4llm 为 fitz？ | ❌ **否** | pymupdf4llm 已具备所需能力（页级输出、页眉页脚过滤、表格策略），调参即可；fitz 原生重建等价功能成本过高 |
| 默认启用页级输出？ | ✅ **是**（实验验证后） | 页级输出是页码关联的唯一可靠方式，且对下游分块质量有正面影响 |
| 分块是否允许跨页？ | ❌ **否** | 禁止跨页可确保每个 chunk 的页码精确唯一，简化测试集标注和来源追溯 |

---

*计划完成时间：待用户确认后开始实施*
