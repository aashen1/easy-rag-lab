# 按需解析与延迟索引（Lazy Loading RAG）计划

## 背景与痛点

当前 RAG 冷启动流程为：

```
全部 PDF → Parse（逐文件，慢） → Chunk（逐文件） → Embed（批量，慢） → Index（Qdrant）
```

当 `data/raw/` 中有几百个 PDF（尤其是几百页的行业研报）时，第一步 Parse 和第三步 Embed 非常耗时，在个人电脑上可能需要数小时。用户第一次提问前必须等待全部完成。

## 核心洞察

用户提问通常只涉及**特定行业/主题**（如"煤炭行业最近怎么样"），而语料库中可能包含医药、食品、金融等大量无关文档。如果能在查询时**只解析和索引与查询相关的文档**，就能大幅减少冷启动时间。

## 方案概述：两阶段检索 + 按需解析

### 阶段一：轻量预索引（秒级完成）

对全部 PDF 只做**极轻量的预处理**，不 Parse 全文、不 Embed、不构建向量索引：

1. **文件名/路径索引**：提取文件名、目录结构中的行业关键词（如 `煤炭/`、`医药/`、`年报_煤炭_xxx.pdf`）
2. **PDF 元数据索引**：读取 PDF 的标题、作者、主题等元数据（PyMuPDF 可快速读取，无需渲染页面）
3. **封面/首页文本提取**：只提取 PDF 的前 1-2 页文本（通常包含摘要、目录、标题），作为文档的"摘要"
4. **构建轻量 BM25 索引**：基于上述轻量文本构建内存中的 BM25 索引（jieba 分词，无 embedding 模型）

> 这一步的总耗时：几百个 PDF 的元数据+首页提取通常在 **秒级到分钟级**（远低于全文解析+向量化）。

### 阶段二：查询时按需解析（Lazy Parse + Lazy Embed）

当用户提问时：

1. **粗排召回（BM25）**：用轻量 BM25 索引召回 Top-N 候选文档（如 N=20）
2. **相关性过滤**：基于文件名/路径关键词做二次过滤（如查询"煤炭"时，排除路径中不含煤炭关键词的文档）
3. **按需全文解析**：只对候选文档执行完整的 PDF Parse
4. **按需切块**：对解析后的候选文档执行 Chunk
5. **按需向量化**：对候选 chunks 执行 Embed（embedding 模型此时才加载）
6. **精排召回（向量检索）**：在候选文档的 chunks 上执行向量检索，返回最终结果

```
用户提问
  │
  ▼
[轻量 BM25 索引] ──► 粗排 Top-N 候选文档（秒级）
  │
  ▼
[按需全文 Parse] ──► 只 Parse N 个候选文档（分钟级 → 秒级）
  │
  ▼
[按需 Chunk]
  │
  ▼
[按需 Embed] ──► 只 Embed 候选 chunks（加载 embedding 模型）
  │
  ▼
[向量检索精排] ──► 返回 Top-K 结果
```

## 关键设计决策

### 1. 轻量预索引的数据结构

```python
@dataclass
class DocPreview:
    """PDF 的轻量预览，用于粗排召回"""
    source: str                    # 相对路径，如 "煤炭/2024Q1_煤炭行业研报.pdf"
    file_name: str                 # 文件名
    file_path: Path                # 绝对路径
    pdf_metadata: dict             # PDF 元数据（标题、作者等）
    cover_text: str                # 前 1-2 页文本（摘要/目录）
    category: str                  # 从路径推断的类别（annual_report / research_report）
    page_count: int | None         # 总页数（可选，快速获取）
    sha256: str                    # 文件哈希，用于缓存校验
```

### 2. 轻量 BM25 索引

* 基于 `jieba` 分词（已有依赖）

* 索引字段：`file_name + cover_text + pdf_metadata.get("title", "")`

* 内存中存储，无需持久化（重建成本极低）

* 支持按 `category` 或路径前缀过滤

### 3. 按需解析的缓存机制

* 解析结果仍然使用现有的 `ArtifactCache` 落盘

* 按需解析的文档写入 `data/artifacts/{data_id}/parsed_{parser_hash}/`

* 已解析的文档下次查询时直接读取缓存，无需重复 Parse

* 随着查询次数增加，缓存命中率上升，体验逐渐接近全量索引

### 4. 向量索引的按需构建

* 不预建全量 Qdrant collection

* 查询时为候选文档创建一个**临时 collection**（或复用现有 collection 做增量 upsert）

* 使用 `VectorIndexer.upsert_chunks()`（UUID-based，支持增量）

* 可选：维护一个"已索引文档集合"，避免重复 embed

### 5. 召回质量保证

* **粗排召回数可配置**：`lazy.top_n_candidates`（默认 20，保守场景可调大）

* **混合策略**：粗排可用 BM25 + 路径关键词过滤双重保险

* **兜底机制**：如果粗排召回数 < top\_k，自动扩大候选范围或降级为全量解析

* **用户确认**：UI 上可显示"本次查询涉及 X 个文档"，让用户感知范围

## 配置设计（config.yaml 新增）

```yaml
lazy_loading:
  enabled: false              # 默认关闭，保持现有行为
  strategy: "bm25_coarse"     # 粗排策略：bm25_coarse / filename_only / hybrid
  top_n_candidates: 20        # 粗排召回文档数
  cover_pages: 2              # 预索引时提取的封面页数
  build_bm25_on_startup: true # 启动时是否构建轻量 BM25 索引
  
  # 路径关键词映射（用于二次过滤和粗排加权）
  path_keywords:
    煤炭: ["煤炭", "煤企", "焦煤", "动力煤"]
    医药: ["医药", "生物", "医疗器械", "创新药"]
    金融: ["金融", "银行", "保险", "证券"]
    # ... 可扩展
  
  # 兜底策略
  fallback:
    min_candidates: 5         # 粗排结果少于此数时，扩大搜索范围
    auto_expand_factor: 2     # 扩大倍数
    enable_full_index_fallback: true  # 是否允许降级为全量索引
```

## 模块设计

### 新增模块

1. **`src/lazy/preview_indexer.py`**

   * `PreviewIndexer`：构建和维护轻量预索引

   * 方法：`build_preview_index(raw_dir) -> list[DocPreview]`

   * 方法：`search_candidates(query: str, top_n: int) -> list[DocPreview]`

2. **`src/lazy/lazy_pipeline.py`**

   * `LazyRAGPipeline`：按需解析的 RAG Pipeline

   * 继承或组合现有 `RAGPipeline`

   * 核心方法：`query(query: str) -> list[dict]`（内部实现两阶段检索）

3. **`src/lazy/path_matcher.py`**

   * 路径关键词匹配和类别推断

   * 支持从配置读取 `path_keywords`

### 修改现有模块（最小侵入）

1. **`src/pipeline.py`**

   * `RAGPipeline` 增加 `lazy_loading` 分支

   * 若 `config["lazy_loading"]["enabled"]` 为 true，使用 `LazyRAGPipeline` 逻辑

2. **`src/parser.py`**

   * `parse_all_pdfs_unified` 增加 `source_filter` 参数（已有类似逻辑，可复用）

   * 或新增 `parse_selected_pdfs()` 方法

3. **`src/indexer.py`**

   * `VectorIndexer` 已支持 `upsert_chunks()`（UUID-based），无需修改

   * 可选：增加 `upsert_chunks_incremental()` 的便捷封装

## 实施步骤

### Phase 1：轻量预索引（MVP）

1. 实现 `PreviewIndexer`：

   * 遍历 `data/raw/` 所有 PDF

   * 用 PyMuPDF 快速读取元数据和前 N 页文本（不渲染，只提取 text）

   * 构建内存 BM25 索引

   * 持久化 `preview_index.json` 到 `data/artifacts/_preview/`

2. 实现 `LazyRAGPipeline.query()` 的粗排逻辑：

   * BM25 召回 Top-N 候选

   * 路径关键词过滤

3. 单元测试：

   * 测试 `PreviewIndexer` 的构建和搜索

   * 测试路径关键词匹配

### Phase 2：按需解析与索引

1. 实现按需 Parse：

   * 对候选文档调用 `parse_pdf()`（单个文件）

   * 结果写入 `ArtifactCache`

2. 实现按需 Chunk + Embed：

   * 对候选文档的解析结果执行 chunk

   * 加载 embedding 模型，embed 候选 chunks

   * upsert 到 Qdrant（复用现有 collection 或创建临时 collection）

3. 实现精排检索：

   * 在已索引的候选 chunks 上执行向量检索

   * 返回 Top-K 结果

4. 集成到 `RAGPipeline`：

   * 根据配置切换全量模式 / Lazy 模式

5. 单元测试 + 集成测试：

   * 测试端到端 Lazy Query 流程

   * 测试缓存命中/未命中场景

### Phase 3：优化与兜底

1. 实现兜底策略：

   * 粗排结果不足时自动扩大范围

   * 支持降级为全量索引

2. UI/CLI 集成：

   * Streamlit 界面显示"本次查询涉及文档数"

   * CLI 支持 `--lazy` 参数

3. 性能基准测试：

   * 对比全量索引 vs Lazy 模式的冷启动时间

   * 对比召回质量（Hit Rate、Recall）

## 风险评估与缓解

| 风险                    | 影响         | 缓解措施                                 |
| --------------------- | ---------- | ------------------------------------ |
| 粗排漏掉相关文档              | 召回率下降      | 调大 `top_n_candidates`；路径关键词补全；兜底扩大范围 |
| 封面/首页信息不足             | BM25 召回质量差 | 提取前 2-3 页；结合文件名和目录结构                 |
| 首次查询仍需加载 embedding 模型 | 首次查询仍有延迟   | 模型加载不可避免，但只 embed 少量 chunks，远快于全量    |
| 多次查询重复解析同一文档          | 浪费资源       | `ArtifactCache` 缓存已解析结果              |
| 代码复杂度增加               | 维护成本       | 新增模块独立，不修改现有核心逻辑；配置默认关闭              |

## 预期收益

* **冷启动时间**：从数小时 → 秒级（轻量预索引）+ 首次查询分钟级（按需解析）

* **首次查询等待**：从"必须先等全部完成" → "提问后立即得到回答"

* **资源占用**：embedding 模型只在需要时加载，内存占用更友好

* **渐进式体验**：随着查询次数增加，缓存积累，体验逐渐接近全量索引

## 与现有架构的兼容性

* 默认关闭（`lazy_loading.enabled: false`），不影响现有用户

* 全量索引模式（`build_index()`）完全保留，可作为 fallback

* 复用现有的 `ArtifactCache`、`Embedder`、`VectorIndexer`、`BM25Retriever`

* 新增模块位于 `src/lazy/` 目录，与现有代码解耦

