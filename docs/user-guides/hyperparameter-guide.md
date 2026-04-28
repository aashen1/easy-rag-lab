# RAG 泛超参数使用指南

<!-- status: needs-update -->

> ⚠️ **文档状态**：本文档声称介绍 "v0.2.0 新增"参数，但实际这些参数（BM25、混合检索、Reranker、查询改写、语义分块）已在 v0.1.8 实现并交付。文档中的版本引用和实现状态描述需要修正。

> 最后更新: 2026-04-19

本文档面向用户，介绍 `config.yaml` 中新增的 RAG 泛超参数的含义、推荐值和使用方法。

---

## 概述

RAG 系统的问答质量受多个"泛超参数"影响——它们不是模型训练时的参数，而是系统设计和运行时的配置选择。本系统支持 7 大类泛超参数的调节：

| 类别 | 影响阶段 | 核心参数 |
|------|---------|---------|
| PDF 解析 | 文档处理 | `parser.algorithm`, `parser.pymupdf4llm.*`, `parser.fitz_pdfplumber.*` |
| 分块策略 | 文档处理 | `chunker.strategy`, `chunker.semantic.*` |
| 分块参数 | 文档处理 | `chunker.chunk_size`, `chunker.chunk_overlap` |
| 检索方式 | 语义检索 | `retrieval.method`, `retrieval.bm25.*`, `retrieval.hybrid.*` |
| 重排序 | 检索精排 | `retrieval.reranker.*` |
| 查询改写 | 查询预处理 | `retrieval.query_rewrite.*` |
| 检索数量 | 语义检索 | `retrieval.top_k` |

---

## 0. PDF 解析策略

### 参数位置

```yaml
parser:
  algorithm: "pymupdf4llm"   # "pymupdf4llm" 或 "fitz_pdfplumber"
```

### 解析器对比

| 解析器 | 优势 | 劣势 | 适用场景 |
|--------|------|------|---------|
| `pymupdf4llm` | 多栏检测、LLM 友好输出、OCR 兜底、表格识别 | Layout 模式下部分参数不可用 | 金融研报（双栏排版普遍） |
| `fitz_pdfplumber` | 精确表格提取、完全参数控制、多栏检测 | 需额外依赖 pdfplumber、无 OCR 兜底 | 表格密集型文档、需要精细控制 |

### pymupdf4llm 关键参数

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false            # 过滤页眉噪声
    footer: false            # 过滤页脚噪声
    page_chunks: true        # 启用页级输出（含页码元数据）
    force_text: true         # 保留图表上的数据标注
    ignore_code: true        # 避免财务数据被标记为代码块
    use_ocr: true            # OCR 兜底
    ocr_language: "chi_sim+eng"  # 中英文 OCR
```

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `header` | `false` | - | 是否提取页眉。金融研报建议关闭 |
| `footer` | `false` | - | 是否提取页脚。金融研报建议关闭 |
| `page_chunks` | `true` | - | 启用页级输出，输出 `.pages.json` 格式 |
| `force_text` | `true` | - | 保留叠加在图表上的文本 |
| `ignore_code` | `true` | - | 避免财务表格被误标为代码块 |
| `use_ocr` | `true` | - | 启用 OCR 兜底（扫描件自动触发） |
| `ocr_language` | `"chi_sim+eng"` | - | OCR 语言包 |

> **详细参数说明和最佳实践**请参阅 [PDF 解析指南](pdf-parsing.md)。

### fitz_pdfplumber 关键参数

```yaml
parser:
  algorithm: "fitz_pdfplumber"
  fitz_pdfplumber:
    header_filter: true      # 过滤页眉区域
    footer_filter: true      # 过滤页脚区域
    header_zone_ratio: 0.10  # 页眉区域占比
    footer_zone_ratio: 0.10  # 页脚区域占比
    table_strategy: "lines"  # 表格检测策略
    column_detection: true   # 启用多栏检测
```

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `header_filter` | `true` | - | 是否过滤页眉区域 |
| `footer_filter` | `true` | - | 是否过滤页脚区域 |
| `header_zone_ratio` | `0.10` | 0.05 - 0.15 | 页眉区域占页面高度的比例 |
| `footer_zone_ratio` | `0.10` | 0.05 - 0.15 | 页脚区域占页面高度的比例 |
| `table_strategy` | `"lines"` | `"lines"`, `"text"` | pdfplumber 表格检测策略 |
| `column_detection` | `true` | - | 是否启用多栏检测 |

### 使用建议

| 场景 | 推荐解析器 | 关键配置 |
|------|-----------|---------|
| 金融年报/研报（双栏排版） | `pymupdf4llm` | `page_chunks: true`, `ignore_code: true` |
| 表格密集型文档 | `fitz_pdfplumber` | `table_strategy: "lines"` |
| 扫描件 PDF | `pymupdf4llm` | `use_ocr: true`, `ocr_language: "chi_sim+eng"` |
| 技术报告（含代码） | `pymupdf4llm` | `ignore_code: false` |

---

## 1. 分块策略

### 参数位置

```yaml
chunker:
  strategy: "fixed"          # "fixed" 或 "semantic"
```

### 选项说明

| 值 | 说明 | 适用场景 |
|----|------|---------|
| `fixed` | 固定 token 数分块，按 tiktoken 编码切分 | 通用场景，参数可控性强 |
| `semantic` | 语义分块，按语义相似度断点切分 | 需要保持语义完整性的场景 |

### 固定分块参数

```yaml
chunker:
  strategy: "fixed"
  chunk_size: 512            # 每块最大 token 数
  chunk_overlap: 0           # 相邻块重叠 token 数
```

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `chunk_size` | 512 | 256 - 1024 | 太小丢失上下文，太大引入噪声 |
| `chunk_overlap` | 0 | 0 - 256 | 增大 overlap 可减少边界信息丢失，但增加存储和计算量 |

**经验法则**：
- `chunk_size=256`：适合精确匹配型查询（如数字、专有名词）
- `chunk_size=512`：通用场景的平衡选择
- `chunk_size=1024`：适合需要长上下文的推理型问题
- `overlap` 建议设为 `chunk_size` 的 10%-25%

### 语义分块参数

```yaml
chunker:
  strategy: "semantic"
  chunk_size: 512
  semantic:
    similarity_threshold: 0.5     # 断点相似度阈值
    breakpoint_percentile: null   # 百分位阈值（null = 禁用）
    min_chunk_size: 100           # 最小 chunk token 数
```

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `similarity_threshold` | 0.5 | 0.3 - 0.7 | 越低产生越少断点（更大的 chunk），越高产生越多断点（更小的 chunk） |
| `breakpoint_percentile` | null | 10 - 50 | 取相似度分布的百分位作为阈值。设置后覆盖 `similarity_threshold` |
| `min_chunk_size` | 100 | 50 - 200 | 低于此值的 chunk 会与相邻 chunk 合并 |

**阈值选择指南**：

| 阈值 | 效果 | 适用场景 |
|------|------|---------|
| 0.3 | 较少断点，chunk 较大 | 文档主题连贯，需要保留长上下文 |
| 0.5 | 平衡 | 通用场景 |
| 0.7 | 较多断点，chunk 较小 | 文档主题切换频繁，需要精确匹配 |

**百分位模式**：当文档的相似度分布差异较大时，使用百分位模式可以自适应地选择断点。例如 `breakpoint_percentile: 25` 表示在相似度最低的 25% 位置插入断点。

---

## 2. 检索方式

### 参数位置

```yaml
retrieval:
  method: "vector"           # "vector", "bm25", 或 "hybrid"
  top_k: 5
```

### 选项说明

| 值 | 说明 | 优势 | 劣势 |
|----|------|------|------|
| `vector` | 纯向量语义检索 | 语义理解强，同义词/近义词匹配好 | 对关键词精确匹配较弱 |
| `bm25` | 纯 BM25 稀疏检索 | 关键词精确匹配好，速度快 | 无法理解语义相似性 |
| `hybrid` | 混合检索（BM25 + 向量） | 兼顾语义和关键词，效果最好 | 计算量稍大 |

### BM25 参数

```yaml
retrieval:
  method: "bm25"             # 或 "hybrid"
  bm25:
    k1: 1.5                  # 词频饱和参数
    b: 0.75                  # 长度归一化参数
```

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `k1` | 1.5 | 1.2 - 2.0 | 控制词频的饱和速度。k1 越大，高频词的边际收益越大 |
| `b` | 0.75 | 0.0 - 1.0 | 控制文档长度归一化。b=0 不归一化，b=1 完全归一化 |

**参数影响**：

- `k1` 较小（如 1.2）：词频影响被抑制，更关注文档是否包含关键词
- `k1` 较大（如 2.0）：词频影响放大，关键词多次出现的文档排名更高
- `b` 较小（如 0.3）：长文档不受惩罚，适合内容丰富的文档
- `b` 较大（如 0.9）：长文档被惩罚，适合短查询场景

### 混合检索参数

```yaml
retrieval:
  method: "hybrid"
  hybrid:
    fusion: "rrf"            # "rrf" 或 "weighted"
    rrf_k: 60                # RRF 常数
    vector_weight: 0.7       # 向量检索权重（weighted 模式）
    bm25_weight: 0.3         # BM25 检索权重（weighted 模式）
```

#### 融合策略

| 策略 | 说明 | 推荐场景 |
|------|------|---------|
| `rrf` | Reciprocal Rank Fusion，基于排名位置融合 | 通用推荐，对分数尺度不敏感 |
| `weighted` | 加权融合，先归一化再加权 | 需要精确控制两种检索的权重比例 |

#### RRF 参数

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `rrf_k` | 60 | 10 - 100 | 常数 k。k 越大，排名差异的影响越小，结果越平滑 |

**RRF 评分公式**：`score = 1 / (k + rank)`，每个文档的最终分数是两个检索器分数之和。

#### 加权融合参数

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `vector_weight` | 0.7 | 0.3 - 0.8 | 向量检索的权重 |
| `bm25_weight` | 0.3 | 0.2 - 0.7 | BM25 检索的权重 |

**权重选择指南**：

| 权重组合 | 效果 | 适用场景 |
|---------|------|---------|
| vector=0.7, bm25=0.3 | 偏向语义匹配 | 查询偏口语化、需要同义词理解 |
| vector=0.5, bm25=0.5 | 均衡 | 通用场景 |
| vector=0.3, bm25=0.7 | 偏向关键词匹配 | 查询包含专业术语、精确关键词 |

---

## 3. 重排序

### 参数位置

```yaml
retrieval:
  reranker:
    enabled: false
    model_name: "BAAI/bge-reranker-large"
    device: "cuda"
    top_n: 3
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | false | 是否启用 Cross-Encoder 重排序 |
| `model_name` | `BAAI/bge-reranker-large` | Cross-Encoder 模型名称 |
| `device` | `cuda` | 推理设备，无 GPU 时自动回退到 CPU |
| `top_n` | 3 | 重排后保留的文档数量 |

### 使用建议

**何时启用 Reranker**：

- 检索结果中相关文档排名不理想时（MRR 较低）
- 需要精确的文档排序时
- 检索候选集较大（top_k ≥ 5）时

**top_n 的选择**：

| top_k | 推荐 top_n | 说明 |
|-------|-----------|------|
| 5 | 3 | 精选 3 篇送入 LLM |
| 10 | 3-5 | 从 10 篇中精选 |
| 3 | 3 | 与 top_k 相同时相当于只重排不筛选 |

**模型选择**：

| 模型 | 大小 | 速度 | 精度 |
|------|------|------|------|
| `BAAI/bge-reranker-base` | ~280MB | 快 | 中 |
| `BAAI/bge-reranker-large` | ~1.3GB | 中 | 高 |
| `BAAI/bge-reranker-v2-m3` | ~560MB | 中 | 高（多语言） |

**注意**：首次使用时需要下载模型，请确保网络畅通。模型会自动缓存到 Hugging Face 缓存目录。

---

## 4. 查询改写

### 参数位置

```yaml
retrieval:
  query_rewrite:
    enabled: false
    strategy: "hyde"         # "hyde" 或 "multi_query"
    num_queries: 3           # Multi-Query 的子查询数量
```

### 策略说明

#### HyDE（假设性文档嵌入）

**原理**：先让 LLM 生成一个"假设性回答"，再用这个回答的 embedding 去检索文档。假设性回答在语义空间中更接近真实文档，从而弥合短查询与长文档之间的语义鸿沟。

**适用场景**：
- 查询简短但需要深入理解
- 查询与文档的表述差异较大
- 需要语义推理的复杂问题

**示例**：

```
原始查询: "茅台营收增长原因"
假设回答: "贵州茅台2023年营业收入达到1500亿元，同比增长16.5%。
          增长主要得益于高端白酒需求旺盛、直销渠道占比提升
          以及系列酒结构升级..."
→ 用假设回答的 embedding 检索 → 找到更相关的文档
```

#### Multi-Query（多查询改写）

**原理**：将原始查询改写为多个不同角度的子查询，分别检索后合并去重。增加召回的覆盖面。

**适用场景**：
- 查询模糊，可能有多种理解
- 需要从不同角度获取信息
- 单一查询召回不足

**示例**：

```
原始查询: "茅台营收增长原因"
子查询1: "贵州茅台营业收入增长的主要驱动因素"
子查询2: "茅台股份收入结构变化分析"
子查询3: "茅台集团业绩增长与行业趋势关系"
→ 分别检索 → 合并去重 → 更全面的召回
```

### 参数说明

| 参数 | 默认值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| `enabled` | false | - | 是否启用查询改写 |
| `strategy` | `hyde` | - | 改写策略选择 |
| `num_queries` | 3 | 2 - 5 | Multi-Query 的子查询数量（仅 multi_query 策略生效） |

**额外成本**：查询改写需要额外的 LLM 调用，每次查询增加约 100-300 tokens 的消耗。

---

## 5. 检索数量

### 参数位置

```yaml
retrieval:
  top_k: 5
```

### 选择指南

| top_k | 效果 | 适用场景 |
|-------|------|---------|
| 3 | 精准，上下文少 | 简单事实查询，LLM 上下文窗口有限 |
| 5 | 平衡 | 通用场景（默认值） |
| 10 | 召回高，上下文多 | 复杂推理问题，需要多角度信息 |

**注意**：top_k 增大会带来边际收益递减，同时增加 LLM 的输入 token 数和推理时间。建议配合 Reranker 使用：先检索较多候选（如 top_k=10），再用 Reranker 精选（如 top_n=3）。

---

## 配置示例

### 最小配置（纯向量检索）

```yaml
chunker:
  strategy: "fixed"
  chunk_size: 512
  chunk_overlap: 0

retrieval:
  method: "vector"
  top_k: 5
```

### 推荐配置（混合检索 + 重排序）

```yaml
chunker:
  strategy: "fixed"
  chunk_size: 512
  chunk_overlap: 50

retrieval:
  method: "hybrid"
  top_k: 10
  hybrid:
    fusion: "rrf"
    rrf_k: 60
  reranker:
    enabled: true
    model_name: "BAAI/bge-reranker-large"
    top_n: 3
```

### 高级配置（语义分块 + HyDE + 混合检索 + 重排序）

```yaml
chunker:
  strategy: "semantic"
  chunk_size: 512
  semantic:
    similarity_threshold: 0.5
    min_chunk_size: 100

retrieval:
  method: "hybrid"
  top_k: 10
  hybrid:
    fusion: "rrf"
    rrf_k: 60
  reranker:
    enabled: true
    model_name: "BAAI/bge-reranker-large"
    top_n: 3
  query_rewrite:
    enabled: true
    strategy: "hyde"
```

### 关键词精确匹配场景

```yaml
chunker:
  strategy: "fixed"
  chunk_size: 256
  chunk_overlap: 0

retrieval:
  method: "hybrid"
  top_k: 5
  hybrid:
    fusion: "weighted"
    vector_weight: 0.3
    bm25_weight: 0.7
```

---

## 实验中覆盖参数

在实验配置的 `variants[].config_overrides` 中，可以覆盖任何上述参数。示例：

```yaml
variants:
  - name: "hyde_hybrid_rerank"
    description: "HyDE + 混合检索 + 重排序"
    config_overrides:
      chunker:
        strategy: "semantic"
        chunk_size: 512
        semantic:
          similarity_threshold: 0.5
      retrieval:
        method: "hybrid"
        top_k: 10
        hybrid:
          fusion: "rrf"
        reranker:
          enabled: true
          top_n: 3
        query_rewrite:
          enabled: true
          strategy: "hyde"
```

> 更多实验配置示例见 `exp_configs/` 目录。

---

## 参数影响速查表

| 想改善的问题 | 调整方向 |
|-------------|---------|
| 检索不到相关文档 | 增大 `top_k`；启用混合检索；启用 HyDE |
| 检索到了但排名靠后 | 启用 Reranker；调整 `rrf_k` |
| 回答包含无关信息 | 减小 `top_k`；启用 Reranker 减小 `top_n`；减小 `chunk_size` |
| 回答缺少关键信息 | 增大 `chunk_size`；增大 `top_k`；启用 Multi-Query |
| 关键词精确匹配差 | 启用混合检索；增大 `bm25_weight` |
| 语义理解差 | 增大 `vector_weight`；启用 HyDE |
| 推理型问题效果差 | 增大 `chunk_size`；使用语义分块；启用 HyDE |
| 回答不够忠实 | 减小 `top_k`；启用 Reranker；减小 `chunk_size` |

---

## 相关文档

- [RAG 优化实现详解](rag-optimization-implementation.md) — 面向开发者的技术文档
- [配置参考](../config-reference.md) — config.yaml 完整说明
- [实验评测系统](experiment-system.md) — 如何运行对比实验
