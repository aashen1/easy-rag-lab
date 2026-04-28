# 配置文件参考手册

> 最后更新: 2026-04-27

本文档说明 `config.yaml` 中所有配置项的含义和默认值。具体配置可参看`exp_configs/templates/_complete.yaml`

---

## 配置文件结构

```yaml
# 激活的 LLM preset
active_mode: "default"

# LLM preset 定义
llm_presets:
  default: { ... }
  opus: { ... }
  sonnet: { ... }
  haiku: { ... }

# PDF 解析配置
parser: { ... }

# 分块配置
chunker: { ... }

# Embedding 配置
embedding: { ... }

# 向量存储配置
vector_store: { ... }

# 检索配置
retrieval: { ... }

# 评测配置
evaluation: { ... }

# Meal 配置
meals: { ... }

# 实验配置
experiments: { ... }

# 测试生成配置
test_generation: { ... }

# Token 成本配置
token_cost: { ... }

# 日志配置
logging: { ... }
```

---

## LLM Presets

```yaml
llm_presets:
  default:
    model_name: "LLM_MODEL_ID"    # 模型名称（从环境变量读取）
    temperature: 0.0              # 温度参数
    max_tokens: 1024              # 最大输出 token 数
    api_key: "LLM_API_KEY"        # API Key（从环境变量读取）
    base_url: "LLM_BASE_URL"      # API Base URL（从环境变量读取）

  opus:
    model_name: "claude-3-opus-20240229"
    temperature: 0.0
    max_tokens: 4096
    # ...

  sonnet:
    model_name: "claude-3-5-sonnet-20241022"
    # ...

  haiku:
    model_name: "claude-3-haiku-20240307"
    # ...
```

---

## Parser 配置

```yaml
parser:
  input_dir: "data/raw"      # PDF 输入目录
  algorithm: "pymupdf4llm"   # 解析算法
  pymupdf4llm:               # pymupdf4llm 专用参数
    header: false            # 不提取页眉
    footer: false            # 不提取页脚
    page_separators: false   # 不插入页分隔符（page_chunks=True 时冗余）
    write_images: false      # 不写出图片文件
    page_chunks: true        # 启用页级输出（每页独立 dict，含页码元数据）
    force_text: true         # 保留叠加在图表上的文本
    ignore_code: true        # 避免财务数据被标记为代码块
    use_ocr: true            # 启用 OCR 兜底
    ocr_language: "chi_sim+eng"  # 中英文 OCR
    show_progress: true      # 显示解析进度
```

> **注意**：解析产物不再输出到固定目录，而是由 Artifact 系统自动管理至
> `data/artifacts/{data_id[:16]}/parsed_{hash}/`。`parser.output_dir` 配置项已移除。

### 基础参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_dir` | `"data/raw"` | PDF 文件输入目录 |
| `algorithm` | `"pymupdf4llm"` | PDF 解析算法。支持 `pymupdf4llm`（推荐）或 `fitz_pdfplumber` |

### pymupdf4llm 参数

以下参数对应 `pymupdf4llm.to_markdown()` 的关键字参数。系统默认使用 Layout 模式（`use_layout(True)`），该模式自动处理多栏布局检测和图片分类。

| 参数 | 默认值 | Layout 模式生效 | 说明 |
|------|--------|----------------|------|
| `header` | `false` | ✅ | 是否提取页眉。金融研报建议关闭，避免页眉噪声 |
| `footer` | `false` | ✅ | 是否提取页脚。金融研报建议关闭，避免页码噪声 |
| `page_separators` | `false` | ✅ | 是否在每页末尾插入分隔符。`page_chunks=True` 时建议关闭（冗余） |
| `write_images` | `false` | ✅ | 是否写出图片文件。Layout 模式自动分类图片，此参数控制是否将图片保存到磁盘 |
| `page_chunks` | `true` | ✅ | 是否启用页级输出。`true` 时每个 PDF 页面返回独立 dict（含 `text`、`metadata`、`toc_items`、`tables`），输出为 `.pages.json` 格式；`false` 时输出为单一 `.md` 文件 |
| `force_text` | `true` | ✅ | 是否强制提取文本（即使与图片/图形重叠）。金融研报中图表上的数据标注建议保留 |
| `ignore_code` | `true` | ✅ | 是否忽略等宽文本的代码块格式化。金融研报中财务数据表格常被误识别为代码块，建议开启 |
| `use_ocr` | `true` | ✅ | 是否启用 OCR 兜底。扫描件 PDF 自动触发 OCR 识别 |
| `ocr_language` | `"chi_sim+eng"` | ✅ | OCR 语言包。`chi_sim` 为简体中文，`eng` 为英文。需安装 Tesseract 中文语言包 |
| `show_progress` | `true` | ✅ | 是否显示解析进度条 |

> ⚠️ `ignore_images` 参数在 Layout 模式下**不生效**，已从配置中移除。Layout 模式由模块自行分类处理图片，`write_images: false` 已足够控制不写出图片文件。
>
> 详细参数说明和最佳实践请参阅 [PDF 解析指南](pdf-parsing.md)。

### fitz_pdfplumber 参数

以下参数用于 `fitz_pdfplumber` 解析器，该解析器结合 fitz (PyMuPDF) 进行文本提取和 pdfplumber 进行精确表格提取。

```yaml
parser:
  algorithm: "fitz_pdfplumber"
  fitz_pdfplumber:
    header_filter: true
    footer_filter: true
    header_zone_ratio: 0.10
    footer_zone_ratio: 0.10
    table_strategy: "lines"
    table_settings:
      snap_tolerance: 5
      join_tolerance: 5
      edge_min_length: 10
      intersection_x_tolerance: 5
      intersection_y_tolerance: 5
    column_detection: true
    noise_patterns:
      - "请务必阅读.{0,20}声明"
      - "^\\s*\\d+\\s*$"
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `header_filter` | `true` | 是否过滤页眉区域 |
| `footer_filter` | `true` | 是否过滤页脚区域 |
| `header_zone_ratio` | `0.10` | 页眉区域占页面高度的比例 |
| `footer_zone_ratio` | `0.10` | 页脚区域占页面高度的比例 |
| `table_strategy` | `"lines"` | pdfplumber 表格检测策略。`"lines"` 基于线条，`"text"` 基于文本 |
| `table_settings` | 见上 | pdfplumber `find_tables()` 的详细设置 |
| `column_detection` | `true` | 是否启用多栏检测 |
| `noise_patterns` | 见上 | 噪声文本的正则表达式列表 |

---

## Chunker 配置

```yaml
chunker:
  strategy: "fixed"          # 分块策略: "fixed" 或 "semantic"
  chunk_size: 512            # 每块最大 token 数
  chunk_overlap: 0           # 相邻块重叠 token 数（fixed 策略）
  semantic:                  # 语义分块参数（semantic 策略）
    similarity_threshold: 0.5    # 断点相似度阈值
    breakpoint_percentile: null  # 百分位阈值（null = 禁用）
    min_chunk_size: 100          # 最小 chunk token 数
```

> **注意**：分块产物不再输出到固定目录，而是由 Artifact 系统自动管理至
> `data/artifacts/{data_id[:16]}/chunks_{hash}/`。`chunker.input_dir` 和
> `chunker.output_dir` 配置项已移除。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `strategy` | `"fixed"` | 分块策略。`"fixed"` 为固定 token 数分块，`"semantic"` 为基于语义相似度的断点分块 |
| `chunk_size` | `512` | 每块最大 token 数 |
| `chunk_overlap` | `0` | 相邻块重叠 token 数（仅 fixed 策略生效） |
| `semantic.similarity_threshold` | `0.5` | 语义断点的余弦相似度阈值（仅 semantic 策略生效） |
| `semantic.breakpoint_percentile` | `null` | 取相似度分布的百分位作为阈值，设置后覆盖 similarity_threshold |
| `semantic.min_chunk_size` | `100` | 低于此 token 数的 chunk 会与相邻 chunk 合并 |

> 详细参数说明请参阅 [RAG 泛超参数使用指南](hyperparameter-guide.md)。

---

## Embedding 配置

```yaml
embedding:
  model_name: "BAAI/bge-large-zh-v1.5"  # Embedding 模型名称
  device: "cuda"                        # 设备（cuda 或 cpu）
  batch_size: 32                        # 批处理大小
```

---

## Vector Store 配置

```yaml
vector_store:
  type: "qdrant"                        # 向量存储类型
  collection_name: "financial_reports"  # 集合名称
  persist_dir: "data/vector_store"      # 持久化目录
  distance: "Cosine"                    # 距离度量
```

---

## Retrieval 配置

```yaml
retrieval:
  method: "vector"           # 检索方式: "vector", "bm25", 或 "hybrid"
  top_k: 5                   # 检索返回的文档块数量
  bm25:                      # BM25 参数（method 为 bm25 或 hybrid 时生效）
    k1: 1.5                  # 词频饱和参数
    b: 0.75                  # 长度归一化参数
  hybrid:                    # 混合检索参数（method 为 hybrid 时生效）
    fusion: "rrf"            # 融合策略: "rrf" 或 "weighted"
    rrf_k: 60                # RRF 常数
    vector_weight: 0.7       # 向量检索权重（weighted 模式）
    bm25_weight: 0.3         # BM25 检索权重（weighted 模式）
  reranker:                  # 重排序配置
    enabled: false           # 是否启用 Cross-Encoder 重排序
    model_name: "BAAI/bge-reranker-large"  # Cross-Encoder 模型
    device: "cuda"           # 推理设备
    top_n: 3                 # 重排后保留的文档数量
  query_rewrite:             # 查询改写配置
    enabled: false           # 是否启用查询改写
    strategy: "hyde"         # 改写策略: "hyde" 或 "multi_query"
    num_queries: 3           # Multi-Query 的子查询数量
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `method` | `"vector"` | 检索方式。`"vector"` 纯向量检索，`"bm25"` 纯稀疏检索，`"hybrid"` 混合检索 |
| `top_k` | `5` | 检索返回的文档块数量 |
| `bm25.k1` | `1.5` | BM25 词频饱和参数，控制词频对分数的影响程度 |
| `bm25.b` | `0.75` | BM25 长度归一化参数，控制文档长度对分数的影响 |
| `hybrid.fusion` | `"rrf"` | 混合检索的融合策略。`"rrf"` 基于排名融合，`"weighted"` 基于分数加权 |
| `hybrid.rrf_k` | `60` | RRF 常数，值越大排名差异的影响越小 |
| `hybrid.vector_weight` | `0.7` | 向量检索在加权融合中的权重 |
| `hybrid.bm25_weight` | `0.3` | BM25 检索在加权融合中的权重 |
| `reranker.enabled` | `false` | 是否启用 Cross-Encoder 重排序 |
| `reranker.model_name` | `"BAAI/bge-reranker-large"` | Cross-Encoder 模型名称 |
| `reranker.device` | `"cuda"` | 重排序模型推理设备 |
| `reranker.top_n` | `3` | 重排后保留的文档数量 |
| `query_rewrite.enabled` | `false` | 是否启用查询改写 |
| `query_rewrite.strategy` | `"hyde"` | 改写策略。`"hyde"` 假设性文档嵌入，`"multi_query"` 多查询改写 |
| `query_rewrite.num_queries` | `3` | Multi-Query 策略生成的子查询数量 |

> 详细参数说明和使用建议请参阅 [RAG 泛超参数使用指南](hyperparameter-guide.md)。

---

## Evaluation 配置

```yaml
evaluation:
  backends: ["builtin"]                  # 评测后端列表
  normalize_source_include_parent: true  # 归一化来源时是否包含父路径

  # 指标解析策略
  resolution_strategy: "priority_fallback"  # priority_fallback / comparison
  backend_priority: ["builtin", "ragas"]    # priority_fallback 模式的后端优先级

  # 指标预设
  metrics_preset: "core"  # core / extended / full / custom

  # 自定义指标（仅 metrics_preset: "custom" 时生效）
  # custom_metrics:
  #   retrieval: [hit_rate, mrr, ndcg]
  #   generation: [faithfulness, answer_correctness]

  # RAGAS 专用配置
  ragas:
    enabled: false
    llm_backend: "anthropic"
    embeddings_backend: "local"
    max_tokens: 4096
    run_config:
      max_workers: 5
      timeout: 120
      max_retries: 3
```

### 核心概念：指标预设 + 解析策略

评测系统采用 **指标预设 + 解析策略** 的两层架构：

1. **指标预设**（`metrics_preset`）决定"计算哪些指标"
2. **解析策略**（`resolution_strategy`）决定"每个指标由哪个后端计算"

用户只需选择预设和策略，无需手动列举指标列表。如需精细控制，可使用 `custom` 预设自行指定。

### 指标预设

| 预设 | retrieval 指标 | generation 指标 | LLM 调用/题 | 适用场景 |
|------|---------------|----------------|------------|---------|
| **core** | hit_rate, mrr, ndcg, recall_3, recall_5, recall_10 | faithfulness, answer_relevancy | ~3 次 | 日常实验 |
| **extended** | core 全部 + chunk_hit_rate/mrr/ndcg, dedup_hit_rate/mrr/ndcg, context_precision, context_recall | faithfulness, answer_relevancy | ~11 次 | 深度诊断 |
| **full** | extended 全部 + false_positive_rate, retrieval_diversity | faithfulness, answer_relevancy, answer_correctness, semantic_similarity | ~15+ 次 | 版本发布 |
| **custom** | 由 `custom_metrics.retrieval` 指定 | 由 `custom_metrics.generation` 指定 | 取决于选择 | 精细化需求 |

> **层级关系**：core ⊂ extended ⊂ full，每层严格包含上层的所有指标。

### 解析策略

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| `priority_fallback` | 每个指标只由最高优先级后端计算，避免重复 | 日常实验（默认，节省 token） |
| `comparison` | 所有后端都计算各自支持的指标，结果加前缀区分 | 版本发布前的对标验证 |

**priority_fallback 示例**（`backend_priority: ["builtin", "ragas"]`）：

| 指标 | 分配后端 | 理由 |
|------|---------|------|
| hit_rate, mrr, ndcg, recall_*, chunk_*, dedup_*, fpr, diversity | builtin | 仅 builtin 支持 |
| faithfulness, answer_relevancy | builtin | builtin 优先级更高 |
| context_precision, context_recall | builtin | builtin 优先级更高 |
| answer_correctness, semantic_similarity | ragas | builtin 不支持，降级到 ragas |

**comparison 示例**（`backends: ["builtin", "ragas"]`）：

| 指标 | builtin 结果 | ragas 结果 |
|------|-------------|-----------|
| faithfulness | builtin_faithfulness=0.85 | ragas_faithfulness=0.72 |
| answer_relevancy | builtin_answer_relevancy=0.90 | ragas_answer_relevancy=0.88 |
| hit_rate | builtin_hit_rate=0.80 | — |
| answer_correctness | — | ragas_answer_correctness=0.75 |

### 自定义指标

当 `metrics_preset: "custom"` 时，必须提供 `custom_metrics` 字段：

```yaml
evaluation:
  backends: ["builtin", "ragas"]
  metrics_preset: "custom"
  custom_metrics:
    retrieval: [hit_rate, mrr, ndcg, recall_3, recall_5, recall_10]
    generation: [faithfulness, answer_correctness, semantic_similarity]
  resolution_strategy: "priority_fallback"
  backend_priority: ["ragas", "builtin"]
```

> **提示**：`custom_metrics` 中的指标名必须与系统支持的指标名完全匹配。如果某个指标没有后端可以计算，系统会记录 warning 并跳过。

### 评测后端

| 后端 | 说明 |
|------|------|
| `builtin` | 自研评测系统，支持检索指标和生成指标 |
| `ragas` | RAGAS 评测框架，支持更丰富的生成质量指标 |

`backends` 为列表格式，支持同时启用多个后端：

```yaml
evaluation:
  backends: ["builtin"]              # 仅自研
  backends: ["ragas"]                # 仅 RAGAS
  backends: ["builtin", "ragas"]     # 同时使用
```

### 双后端指标能力矩阵

| 分类 | 指标 | Builtin | RAGAS | 需要 LLM | 需要 Embedding | 需要 Reference |
|------|------|:-------:|:-----:|:--------:|:-------------:|:-------------:|
| **仅 Builtin** | hit_rate, mrr, ndcg | ✅ | — | 否 | 否 | expected_sources |
| **仅 Builtin** | chunk_hit_rate/mrr/ndcg | ✅ | — | 否 | 否 | expected_chunks |
| **仅 Builtin** | dedup_hit_rate/mrr/ndcg | ✅ | — | 否 | 否 | expected_sources |
| **仅 Builtin** | false_positive_rate | ✅ | — | 否 | 否 | 否 |
| **仅 Builtin** | retrieval_diversity | ✅ | — | 否 | 否 | 否 |
| **仅 Builtin** | recall_3, recall_5, recall_10 | ✅ | — | 否 | 否 | expected_sources |
| **两者重叠** | faithfulness | ✅ | ✅ | 是 | 否 | 否 |
| **两者重叠** | answer_relevancy | ✅ | ✅ | 是 | RAGAS需 | 否 |
| **两者重叠** | context_precision | ✅ | ✅ | 是 | 否 | 是 |
| **两者重叠** | context_recall | ✅ | ✅ | 是 | 否 | 是 |
| **仅 RAGAS** | answer_correctness | — | ✅ | 是 | 是 | 是 |
| **仅 RAGAS** | semantic_similarity | — | ✅ | 否 | 是 | 是 |

### RAGAS 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ragas.enabled` | `false` | 是否启用 RAGAS 评测 |
| `ragas.llm_backend` | `"anthropic"` | LLM 接口类型。`"anthropic"` 使用 LangChain Anthropic 接口连接 LongCat API |
| `ragas.embeddings_backend` | `"local"` | Embeddings 接口。`"local"` 使用本地 BGE 模型，`"openai"` 使用 OpenAI 兼容接口 |
| `ragas.max_tokens` | `4096` | RAGAS LLM 调用的最大输出 token 数 |
| `ragas.run_config.max_workers` | `5` | RAGAS 批量评测的并行度 |
| `ragas.run_config.timeout` | `120` | 单次评测超时时间（秒） |
| `ragas.run_config.max_retries` | `3` | 评测失败时的重试次数 |

> 详细指标说明请参阅 [评测指标详解](evaluation-metrics.md)，RAGAS 使用方法请参阅 [RAGAS 评测系统指南](ragas-evaluation.md)。

---

## Meals 配置

```yaml
meals:
  dir: "data/meals"  # Meal 存储目录
```

---

## Experiments 配置

```yaml
experiments:
  dir: "data/exp_reports"  # 实验报告存储目录
```

---

## Artifacts 配置

```yaml
artifacts:
  dir: "data/artifacts"  # 中间产物存储目录
```

---

## Test Generation 配置

```yaml
test_generation:
  default_strategy: "document"  # 默认问题策略
  default_num_questions: 20     # 默认问题数量
  max_retries: 3                # 最大重试次数

  # 文档级问题生成配置
  document_level:
    enabled: true               # 是否启用文档级问题生成
    default_num_questions: 20   # 默认问题数量
    type_distribution:          # 问题类型分布
      single_fact: 0.30         # 单知识点查询
      multi_fact: 0.25          # 多知识点综合
      reasoning: 0.15           # 推理型问题
      comparative: 0.15         # 对比分析
      missing: 0.10             # 缺失知识点
      irrelevant: 0.05          # 无关问题
    quality_control:            # 质量控制
      enable_authenticity_check: true   # 启用真实性检查
      enable_llm_evaluation: false      # 启用 LLM 质量评估
      min_authenticity_score: 12        # 最低真实性分数
    max_retries: 3              # 最大重试次数
```

### 文档级问题生成配置说明

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `enabled` | 是否启用文档级问题生成 | `true` |
| `default_num_questions` | 默认生成问题数量 | `20` |
| `type_distribution` | 问题类型分布比例 | 见上表 |
| `quality_control.enable_authenticity_check` | 启用真实性检查 | `true` |
| `quality_control.enable_llm_evaluation` | 启用 LLM 质量评估 | `false` |
| `quality_control.min_authenticity_score` | 最低真实性分数阈值 | `12` |
| `max_retries` | 生成失败时的最大重试次数 | `3` |

### 问题类型说明

| 类型 | 说明 | 典型问题示例 |
|------|------|-------------|
| `single_fact` | 单知识点查询 | "2024年光模块市场规模多少？" |
| `multi_fact` | 多知识点综合 | "光模块行业未来几年的增长点主要在哪里？" |
| `reasoning` | 推理型问题 | "为什么CPO能降低功耗？" |
| `comparative` | 对比分析 | "中际旭创和新易盛哪个更值得投资？" |
| `missing` | 缺失知识点 | "光模块行业的ESG评级情况怎么样？" |
| `irrelevant` | 无关问题 | "新能源汽车的电池技术发展怎么样？" |

---

## Token Cost 配置

```yaml
token_cost:
  models:
    LongCat-Flash-Lite:
      input_price_per_1k: 0.001     # 每千 token 输入价格
      output_price_per_1k: 0.002    # 每千 token 输出价格
      conversion_factor: 1.0        # 价格折算系数
    claude-3-opus-20240229:
      input_price_per_1k: 0.015
      output_price_per_1k: 0.075
      conversion_factor: 15.0
    claude-3-5-sonnet-20241022:
      input_price_per_1k: 0.003
      output_price_per_1k: 0.015
      conversion_factor: 3.0
    claude-3-haiku-20240307:
      input_price_per_1k: 0.00025
      output_price_per_1k: 0.00125
      conversion_factor: 0.25
```

| 参数 | 说明 |
|------|------|
| `input_price_per_1k` | 每千 token 输入价格（美元） |
| `output_price_per_1k` | 每千 token 输出价格（美元） |
| `conversion_factor` | 价格折算系数，用于计算等效成本 |

---

## Logging 配置

```yaml
logging:
  level: "INFO"                 # 日志级别
  format: "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
  log_dir: "logs"               # 日志文件目录
  rotation: "10 MB"             # 日志轮转大小
  retention: "7 days"           # 日志保留时间
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `level` | `"INFO"` | 日志级别（DEBUG, INFO, WARNING, ERROR） |
| `format` | 见上 | 日志格式（loguru 格式） |
| `log_dir` | `"logs"` | 日志文件存储目录 |
| `rotation` | `"10 MB"` | 日志文件轮转大小，超过后创建新文件 |
| `retention` | `"7 days"` | 日志文件保留时间，过期自动删除 |

---

## 环境变量

配置文件中以下值从环境变量读取：

| 环境变量 | 说明 |
|---------|------|
| `LLM_API_KEY` | LLM API Key |
| `LLM_BASE_URL` | LLM API Base URL |
| `LLM_MODEL_ID` | 默认 LLM 模型名称 |

参考 `.env.example` 文件。
