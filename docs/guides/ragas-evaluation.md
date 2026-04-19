# RAGAS 评测系统使用指南

<!-- status: active -->

> 最后更新: 2026-04-20

本文档介绍如何使用 RAGAS 评测后端进行 RAG 系统评测，以及如何与自研评测系统并行使用。

---

## 概述

RAGAS（Retrieval Augmented Generation Assessment）是一个主流的开源 RAG 评测框架，提供了丰富的生成质量指标。本项目已集成 RAGAS 作为可选评测后端，与现有自研评测系统并行存在。

### 评测后端对比

| 特性 | 自研（builtin） | RAGAS |
|------|----------------|-------|
| **检索指标** | hit_rate, mrr, ndcg | 无 |
| **生成指标** | faithfulness, answer_relevancy | faithfulness, answer_relevancy, context_precision, context_recall, factual_correctness, semantic_similarity |
| **LLM 调用方式** | Anthropic SDK 直连 | LangChain Anthropic 接口 |
| **评测模式** | 逐条串行 | 批量并行（推荐） |
| **额外依赖** | 无 | ragas, langchain-anthropic, langchain-community |

### RAGAS 特有指标

| 指标 | 所需输入 | 说明 |
|------|---------|------|
| **context_precision** | question, contexts, reference | 检索结果中相关文档是否排在前面 |
| **context_recall** | question, contexts, reference | 检索结果是否覆盖了回答所需的信息 |
| **factual_correctness** | response, reference | 回答与参考答案的事实一致性 |
| **semantic_similarity** | response, reference | 回答与参考答案的语义相似度 |

> **注意**：`context_precision`、`context_recall`、`factual_correctness`、`semantic_similarity` 需要 `reference`（参考答案）才能计算。测试数据中的 `expected_answer` 字段将自动映射为 `reference`。

---

## 快速开始

### 1. 安装依赖

RAGAS 评测需要额外的 Python 包。使用 pixi 安装：

```bash
pixi add langchain-anthropic langchain-community
```

> `ragas` 已在 `pixi.toml` 中声明，无需额外安装。

### 2. 启用 RAGAS 后端

在 `config.yaml` 中配置评测后端：

```yaml
evaluation:
  backends: ["ragas"]       # 仅使用 RAGAS
  ragas:
    enabled: true
    llm_backend: "anthropic"
    embeddings_backend: "local"
    run_config:
      max_workers: 5
      timeout: 60
      max_retries: 3
```

### 3. 在实验配置中指定 RAGAS 指标

```yaml
evaluation:
  backends: ["ragas"]
  metrics:
    retrieval:
      - "hit_rate"          # RAGAS 不提供检索指标，此处无效
      - "mrr"
    generation:
      - "faithfulness"
      - "answer_relevancy"
      - "context_precision"
      - "context_recall"
```

### 4. 运行实验

```bash
pixi run exp your_experiment.yaml
```

---

## 配置详解

### config.yaml 中的 RAGAS 配置

```yaml
evaluation:
  # 评测后端列表：支持 "builtin"、"ragas" 或两者兼有
  backends: ["builtin"]

  # RAGAS 专用配置
  ragas:
    enabled: false                    # 是否启用 RAGAS
    llm_backend: "anthropic"          # LLM 后端：推荐 "anthropic"（兼容 LongCat API）
    embeddings_backend: "local"       # Embeddings 后端："local"（BGE）或 "openai"
    run_config:
      max_workers: 5                  # 并行评测的最大工作线程数
      timeout: 60                     # 单次评测超时时间（秒）
      max_retries: 3                  # 失败重试次数
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ragas.enabled` | `false` | 是否启用 RAGAS 评测 |
| `ragas.llm_backend` | `"anthropic"` | LLM 接口类型。`"anthropic"` 使用 LangChain Anthropic 接口连接 LongCat API |
| `ragas.embeddings_backend` | `"local"` | Embeddings 接口。`"local"` 使用本地 BGE 模型，`"openai"` 使用 OpenAI 兼容接口 |
| `ragas.run_config.max_workers` | `5` | RAGAS 批量评测的并行度 |
| `ragas.run_config.timeout` | `60` | 单次评测超时时间（秒） |
| `ragas.run_config.max_retries` | `3` | 评测失败时的重试次数 |

### 实验配置中的评测后端

实验配置 YAML 中的 `evaluation.backends` 字段控制使用哪些评测后端：

```yaml
evaluation:
  backends: ["builtin"]    # 仅自研评测
```

```yaml
evaluation:
  backends: ["ragas"]      # 仅 RAGAS 评测
```

```yaml
evaluation:
  backends: ["builtin", "ragas"]  # 同时使用两个评测系统
```

> 当 `backends` 中包含 `"ragas"` 时，`config.yaml` 中的 `ragas.enabled` 应设为 `true`。

---

## 后端选择指南

### 仅使用自研评测

适用于：快速评测、仅关注检索指标、无需额外依赖。

```yaml
evaluation:
  backends: ["builtin"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

### 仅使用 RAGAS 评测

适用于：需要更丰富的生成质量指标、需要与业界标准对齐。

```yaml
evaluation:
  backends: ["ragas"]
  metrics:
    retrieval:
      - "hit_rate"        # RAGAS 不提供检索指标，将被忽略
      - "mrr"
    generation:
      - "faithfulness"
      - "answer_relevancy"
      - "context_precision"
      - "context_recall"
      - "factual_correctness"
      - "semantic_similarity"
```

> **注意**：RAGAS 不提供检索指标（hit_rate, mrr, ndcg）。如果需要检索指标，请同时启用 builtin 后端。

### 双后端并行评测（推荐）

适用于：全面评测、对比两套指标结果。

```yaml
evaluation:
  backends: ["builtin", "ragas"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
      - "context_precision"
      - "context_recall"
```

此模式下：
- **检索指标**（hit_rate, mrr, ndcg）由 builtin 后端计算
- **faithfulness, answer_relevancy** 由两个后端分别计算，可对比结果差异
- **context_precision, context_recall** 由 RAGAS 后端计算

---

## RAGAS 指标详解

### Faithfulness（忠实度）

回答中的事实陈述是否可以从检索到的上下文中推导出来。

- **所需输入**：question, answer, contexts
- **取值范围**：0.0 - 1.0
- **与自研指标的关系**：语义相同，计算方式不同（RAGAS 使用自己的 prompt 和评分逻辑）

### Answer Relevancy（回答相关性）

回答与问题的相关程度。

- **所需输入**：question, answer
- **取值范围**：0.0 - 1.0
- **与自研指标的关系**：语义相似，但 RAGAS 的计算方式基于生成反向问题并计算相似度

### Context Precision（上下文精确度）

检索结果中，相关文档是否排在靠前的位置。

- **所需输入**：question, contexts, **reference**
- **取值范围**：0.0 - 1.0
- **自研系统无此指标**

**解读**：
- **0.8+**：相关文档排名靠前，检索排序质量优秀
- **0.5-0.8**：部分相关文档排名靠后，可优化
- **< 0.5**：相关文档排名靠后，需要改进检索或添加重排序

**改进建议**：
- 启用 Reranker 重排序
- 优化 Embedding 模型
- 调整 `top_k` 参数

### Context Recall（上下文召回率）

检索结果是否覆盖了回答所需的所有信息。

- **所需输入**：question, contexts, **reference**
- **取值范围**：0.0 - 1.0
- **自研系统无此指标**

**解读**：
- **0.8+**：检索结果信息覆盖充分
- **0.5-0.8**：部分关键信息未被检索到
- **< 0.5**：大量关键信息缺失

**改进建议**：
- 增加 `top_k` 值
- 调整 `chunk_size` 和 `chunk_overlap`
- 考虑混合检索（BM25 + 向量）

### Factual Correctness（事实正确性）

回答与参考答案的事实一致性，使用 NLG 评估中的 claim-level 对比。

- **所需输入**：response, **reference**
- **取值范围**：0.0 - 1.0
- **自研系统无此指标**

> 此指标高度依赖参考答案的质量。如果 `expected_answer` 不够准确，此指标可能不可靠。

### Semantic Similarity（语义相似度）

回答与参考答案的语义相似度，基于 Embedding 向量的余弦相似度。

- **所需输入**：response, **reference**
- **取值范围**：0.0 - 1.0
- **自研系统无此指标**

---

## LongCat API 适配

RAGAS 评测器通过 LangChain Anthropic 接口连接 LongCat API，适配方式如下：

1. **接口选择**：使用 `langchain-anthropic` 的 `ChatAnthropic` 类
2. **URL 适配**：自动在 `base_url` 后追加 `/anthropic` 路径
3. **认证方式**：通过 `default_headers` 传递 Bearer Token 认证
4. **LLM 包装**：使用 `LangchainLLMWrapper` 将 LangChain LLM 包装为 RAGAS 兼容格式

```python
# 内部实现逻辑（无需手动配置）
ChatAnthropic(
    model=llm_config["model_name"],
    temperature=0.0,
    base_url=f"{llm_config['base_url']}/anthropic",
    api_key="dummy",
    default_headers={
        "Authorization": f"Bearer {llm_config['api_key']}",
        "Content-Type": "application/json",
    },
)
```

> 环境变量 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_ID` 的配置方式与自研评测系统完全一致，无需额外设置。

---

## 编程接口

### 直接使用评测器

如果需要在代码中直接使用评测器：

```python
from eval.evaluators import BuiltinEvaluator, RagasEvaluator

# 创建自研评测器
builtin = BuiltinEvaluator()
result = builtin.evaluate_single(
    question_id="q001",
    question="贵州茅台2023年营收是多少？",
    answer="贵州茅台2023年实现营业收入1505.60亿元。",
    contexts=["贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元。"],
    expected_sources=["贵州茅台2023年年报.pdf"],
    llm_config={
        "api_key": "your-api-key",
        "base_url": "https://your-api-endpoint",
        "model_name": "your-model-id",
    },
)

# 创建 RAGAS 评测器
ragas = RagasEvaluator(config={"embedding": {"model_name": "BAAI/bge-large-zh-v1.5"}})
result = ragas.evaluate_single(
    question_id="q001",
    question="贵州茅台2023年营收是多少？",
    answer="贵州茅台2023年实现营业收入1505.60亿元。",
    contexts=["贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元。"],
    expected_answer="1505.60亿元",
    llm_config={
        "api_key": "your-api-key",
        "base_url": "https://your-api-endpoint",
        "model_name": "your-model-id",
    },
    generation_metrics=["faithfulness", "context_precision"],
)
```

### 批量评测

RAGAS 推荐使用批量评测以获得更好的性能：

```python
ragas = RagasEvaluator()

samples = [
    {
        "question_id": "q001",
        "question": "问题1",
        "answer": "回答1",
        "contexts": ["上下文1"],
        "expected_answer": "参考答案1",
    },
    {
        "question_id": "q002",
        "question": "问题2",
        "answer": "回答2",
        "contexts": ["上下文2"],
        "expected_answer": "参考答案2",
    },
]

results = ragas.evaluate_batch(
    samples=samples,
    llm_config={
        "api_key": "your-api-key",
        "base_url": "https://your-api-endpoint",
        "model_name": "your-model-id",
    },
    generation_metrics=["faithfulness", "answer_relevancy", "context_precision"],
)
```

### 工厂模式

根据配置动态创建评测器：

```python
from eval.evaluators import BuiltinEvaluator, RagasEvaluator

def create_evaluators(backends: list) -> list:
    evaluators = []
    for backend in backends:
        if backend == "builtin":
            evaluators.append(BuiltinEvaluator())
        elif backend == "ragas":
            evaluators.append(RagasEvaluator())
    return evaluators

evaluators = create_evaluators(["builtin", "ragas"])
```

---

## 常见问题

### Q: RAGAS 评测报 ImportError 怎么办？

A: RAGAS 需要额外的依赖包。运行以下命令安装：

```bash
pixi add langchain-anthropic langchain-community
```

### Q: RAGAS 指标需要参考答案（reference），但测试数据没有怎么办？

A: `context_precision`、`context_recall`、`factual_correctness`、`semantic_similarity` 需要 `reference` 才能计算。如果测试数据中没有 `expected_answer` 字段，这些指标将被跳过或返回空值。建议：
- 使用 `document` 策略生成测试集，会自动包含 `expected_answer`
- 手动标注关键测试数据的参考答案

### Q: 自研和 RAGAS 的 faithfulness 结果为什么不同？

A: 两者的计算方式不同：
- **自研**：使用自定义 prompt，通过 LLM 判断每个陈述是否可从上下文推导
- **RAGAS**：使用 RAGAS 框架自带的 prompt 和评分逻辑

两者都是有效的评测方式，差异反映了不同评估策略的特点。双后端并行评测可以提供更全面的视角。

### Q: RAGAS 评测速度慢怎么办？

A: 尝试以下优化：
- 增大 `ragas.run_config.max_workers`（默认 5）
- 减少评测指标数量
- 使用批量评测而非逐条评测
- 检查 API 调用的速率限制

### Q: 如何只使用 RAGAS 的特有指标？

A: 在实验配置中只指定 RAGAS 特有的指标，并将 `backends` 设为 `["ragas"]`：

```yaml
evaluation:
  backends: ["ragas"]
  metrics:
    retrieval:
      - "hit_rate"        # RAGAS 不支持，将被忽略
    generation:
      - "context_precision"
      - "context_recall"
```

---

## 相关文档

- [评测指标详解](evaluation-metrics.md)
- [实验系统指南](experiment-system.md)
- [配置参考](../config-reference.md)
- [系统架构](../architecture.md)
