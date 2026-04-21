# 配置文件参考手册

<!-- status: active -->

> 最后更新: 2026-04-19

本文档说明 `config.yaml` 中所有配置项的含义和默认值。

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
  output_dir: "data/parsed"  # 解析输出目录
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

### 基础参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_dir` | `"data/raw"` | PDF 文件输入目录 |
| `output_dir` | `"data/parsed"` | 解析结果输出目录 |
| `algorithm` | `"pymupdf4llm"` | PDF 解析算法，目前仅支持 `pymupdf4llm` |

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
> 详细参数说明和最佳实践请参阅 [PDF 解析指南](guides/pdf-parsing.md)。

---

## Chunker 配置

```yaml
chunker:
  input_dir: "data/parsed"   # Markdown 输入目录
  output_dir: "data/chunks"  # JSONL 输出目录
  strategy: "fixed"          # 分块策略: "fixed" 或 "semantic"
  chunk_size: 512            # 每块最大 token 数
  chunk_overlap: 0           # 相邻块重叠 token 数（fixed 策略）
  semantic:                  # 语义分块参数（semantic 策略）
    similarity_threshold: 0.5    # 断点相似度阈值
    breakpoint_percentile: null  # 百分位阈值（null = 禁用）
    min_chunk_size: 100          # 最小 chunk token 数
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `strategy` | `"fixed"` | 分块策略。`"fixed"` 为固定 token 数分块，`"semantic"` 为基于语义相似度的断点分块 |
| `chunk_size` | `512` | 每块最大 token 数 |
| `chunk_overlap` | `0` | 相邻块重叠 token 数（仅 fixed 策略生效） |
| `semantic.similarity_threshold` | `0.5` | 语义断点的余弦相似度阈值（仅 semantic 策略生效） |
| `semantic.breakpoint_percentile` | `null` | 取相似度分布的百分位作为阈值，设置后覆盖 similarity_threshold |
| `semantic.min_chunk_size` | `100` | 低于此 token 数的 chunk 会与相邻 chunk 合并 |

> 详细参数说明请参阅 [RAG 泛超参数使用指南](guides/hyperparameter-guide.md)。

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

> 详细参数说明和使用建议请参阅 [RAG 泛超参数使用指南](guides/hyperparameter-guide.md)。

---

## Evaluation 配置

```yaml
evaluation:
  test_data_path: "eval/test_data.json"  # 测试数据路径
  results_dir: "eval/results"            # 结果输出目录
  backends: ["builtin"]                  # 评测后端列表
  metrics:
    retrieval:                           # 检索指标
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:                          # 生成质量指标
      - "faithfulness"
      - "answer_relevancy"
  ragas:                                 # RAGAS 专用配置
    enabled: false
    llm_backend: "anthropic"
    embeddings_backend: "local"
    run_config:
      max_workers: 5
      timeout: 60
      max_retries: 3
```

### 检索指标

| 指标 | 说明 |
|------|------|
| `hit_rate` | 命中率，检索结果中是否包含相关文档 |
| `mrr` | 平均倒数排名，第一个相关文档的排名 |
| `ndcg` | 归一化折损累积增益，综合排序质量 |

### 生成质量指标

| 指标 | 说明 | 注意事项 |
|------|------|---------|
| `faithfulness` | 忠实度，回答是否可从上下文推导 | 需要额外 LLM 调用 |
| `answer_relevancy` | 回答相关性，回答与问题的相关程度 | 需要额外 LLM 调用 |

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

### RAGAS 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ragas.enabled` | `false` | 是否启用 RAGAS 评测 |
| `ragas.llm_backend` | `"anthropic"` | LLM 接口类型。`"anthropic"` 使用 LangChain Anthropic 接口连接 LongCat API |
| `ragas.embeddings_backend` | `"local"` | Embeddings 接口。`"local"` 使用本地 BGE 模型，`"openai"` 使用 OpenAI 兼容接口 |
| `ragas.run_config.max_workers` | `5` | RAGAS 批量评测的并行度 |
| `ragas.run_config.timeout` | `60` | 单次评测超时时间（秒） |
| `ragas.run_config.max_retries` | `3` | 评测失败时的重试次数 |

### RAGAS 生成指标

| 指标 | 说明 | 注意事项 |
|------|------|---------|
| `faithfulness` | 忠实度（RAGAS 实现） | 需要额外 LLM 调用 |
| `answer_relevancy` | 回答相关性（RAGAS 实现） | 需要额外 LLM 调用 |
| `context_precision` | 上下文精确度，相关文档排名质量 | 需要 reference |
| `context_recall` | 上下文召回率，检索覆盖度 | 需要 reference |
| `answer_correctness` | 答案正确性（事实重叠 + 语义相似度） | 需要 reference |
| `semantic_similarity` | 语义相似度 | 需要 reference |

> 详细指标说明请参阅 [评测指标详解](guides/evaluation-metrics.md)，RAGAS 使用方法请参阅 [RAGAS 评测系统指南](guides/ragas-evaluation.md)。

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
  default_strategy: "factual"   # 默认问题策略
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
