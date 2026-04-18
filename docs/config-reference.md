# 配置文件参考手册

<!-- status: active -->

> 最后更新: 2026-04-18

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
  output_dir: "data/parsed"  # Markdown 输出目录
```

---

## Chunker 配置

```yaml
chunker:
  input_dir: "data/parsed"   # Markdown 输入目录
  output_dir: "data/chunks"  # JSONL 输出目录
  chunk_size: 512            # 每块最大 token 数
  chunk_overlap: 0           # 相邻块重叠 token 数
```

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
  top_k: 5    # 检索返回的文档块数量
```

---

## Evaluation 配置

```yaml
evaluation:
  test_data_path: "eval/test_data.json"  # 测试数据路径
  results_dir: "eval/results"            # 结果输出目录
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
```

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
```

---

## Token Cost 配置

```yaml
token_cost:
  models:
    LongCat-Flash-Lite:
      input_price: 0.000001     # 每千 token 输入价格
      output_price: 0.000002    # 每千 token 输出价格
    claude-3-opus-20240229:
      input_price: 0.015
      output_price: 0.075
    claude-3-5-sonnet-20241022:
      input_price: 0.003
      output_price: 0.015
    claude-3-haiku-20240307:
      input_price: 0.00025
      output_price: 0.00125
```

---

## Logging 配置

```yaml
logging:
  level: "INFO"                 # 日志级别
  format: "{time} | {level} | {message}"  # 日志格式
  file: "logs/app.log"          # 日志文件路径
```

---

## 环境变量

配置文件中以下值从环境变量读取：

| 环境变量 | 说明 |
|---------|------|
| `LLM_API_KEY` | LLM API Key |
| `LLM_BASE_URL` | LLM API Base URL |
| `LLM_MODEL_ID` | 默认 LLM 模型名称 |

参考 `.env.example` 文件。
