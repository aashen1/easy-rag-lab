# RAGAS 评测系统使用指南

<!-- status: active -->

> 最后更新: 2026-04-21

本文档介绍如何使用 RAGAS 评测后端进行 RAG 系统评测，以及如何与自研评测系统并行使用。

---

## 概述

RAGAS（Retrieval Augmented Generation Assessment）是一个主流的开源 RAG 评测框架，提供了丰富的生成质量指标。本项目已集成 RAGAS 作为可选评测后端，与现有自研评测系统并行存在。

### 评测后端对比

| 特性 | 自研（builtin） | RAGAS |
|------|----------------|-------|
| **检索指标** | hit_rate, mrr, ndcg, chunk_*, dedup_*, false_positive_rate, context_precision, context_recall | 无 |
| **生成指标** | faithfulness, answer_relevancy | faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness, semantic_similarity |
| **LLM 调用方式** | 统一 LLM 客户端工厂（`create_llm_client`） | 统一 LLM 客户端工厂（`create_llm_client`，langchain 模式） |
| **评测模式** | 逐条串行 | 批量并行（推荐） |
| **额外依赖** | 无 | ragas, langchain-anthropic, langchain-community |

### RAGAS 特有指标

| 指标 | 所需输入 | 说明 |
|------|---------|------|
| **context_precision** | question, contexts, reference | 检索结果中相关文档是否排在前面（builtin 也支持此指标） |
| **context_recall** | question, contexts, reference | 检索结果是否覆盖了回答所需的信息（builtin 也支持此指标） |
| **answer_correctness** | response, reference | 答案正确性（事实重叠 + 语义相似度加权） |
| **semantic_similarity** | response, reference | 回答与参考答案的语义相似度 |

> **注意**：`context_precision`、`context_recall`、`answer_correctness`、`semantic_similarity` 需要 `reference`（参考答案）才能计算。测试数据中的 `expected_answer` 字段将自动映射为 `reference`。其中 `context_precision` 和 `context_recall` 两个后端均支持，但计算方式不同。

---

## 快速开始

### 1. 安装依赖

RAGAS 评测需要额外的 Python 包。使用 pixi 安装：

```bash
pixi add --pypi ragas langchain-anthropic langchain-community
```

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
    embedding:                        # Embeddings 模型配置（可选，覆盖全局 embedding 配置）
      model_name: "BAAI/bge-large-zh-v1.5"  # RAGAS 使用的 Embeddings 模型
      device: "cuda"                  # 运行设备："cuda" 或 "cpu"
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ragas.enabled` | `false` | 是否启用 RAGAS 评测 |
| `ragas.llm_backend` | `"anthropic"` | LLM 接口类型。`"anthropic"` 使用 LangChain Anthropic 接口连接 LongCat API |
| `ragas.embeddings_backend` | `"local"` | Embeddings 接口。`"local"` 使用本地 BGE 模型，`"openai"` 使用 OpenAI 兼容接口 |
| `ragas.run_config.max_workers` | `5` | RAGAS 批量评测的并行度 |
| `ragas.run_config.timeout` | `60` | 单次评测超时时间（秒） |
| `ragas.run_config.max_retries` | `3` | 评测失败时的重试次数 |
| `ragas.embedding.model_name` | `"BAAI/bge-large-zh-v1.5"` | RAGAS 使用的 Embeddings 模型名称 |
| `ragas.embedding.device` | `"cuda"` | Embeddings 模型运行设备 |

> **配置读取优先级**：`ragas.embedding.model_name` 优先于 `ragas.embedding_model`（旧字段），两者均未设置时回退到全局 `embedding.model_name`。`ragas.embedding.device` 未设置时回退到全局 `embedding.device`。

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

适用于：快速评测、关注检索指标与生成指标、无需额外依赖。

```yaml
evaluation:
  backends: ["builtin"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
      - "chunk_hit_rate"
      - "chunk_mrr"
      - "chunk_ndcg"
      - "dedup_hit_rate"
      - "dedup_mrr"
      - "dedup_ndcg"
      - "false_positive_rate"
      - "context_precision"
      - "context_recall"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

> **builtin 检索指标说明**：
> - **基础指标**：`hit_rate`、`mrr`、`ndcg` — 基于文档级别的检索评估
> - **chunk 级别指标**：`chunk_hit_rate`、`chunk_mrr`、`chunk_ndcg` — 基于切块级别的检索评估
> - **去重指标**：`dedup_hit_rate`、`dedup_mrr`、`dedup_ndcg` — 去除同一文档重复结果后的检索评估
> - **FPR**：`false_positive_rate` — 针对无关问题的误检率
> - **LLM 检索指标**：`context_precision`、`context_recall` — 需要调用 LLM，需提供 `llm_config`

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
      - "answer_correctness"
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
- **context_precision, context_recall** 由两个后端分别计算（计算方式不同）
- **answer_correctness, semantic_similarity** 仅由 RAGAS 后端计算

### 指标命名空间前缀

当使用双后端（`["builtin", "ragas"]`）时，生成指标会自动添加后端名称前缀以区分来源：

| 原始指标名 | builtin 结果键名 | RAGAS 结果键名 |
|-----------|----------------|---------------|
| `faithfulness` | `builtin_faithfulness` | `ragas_faithfulness` |
| `answer_relevancy` | `builtin_answer_relevancy` | `ragas_answer_relevancy` |
| `context_precision` | `builtin_context_precision` | `ragas_context_precision` |
| `context_recall` | `builtin_context_recall` | `ragas_context_recall` |

当仅使用单个后端时，不添加前缀，指标键名保持原始名称（如 `faithfulness`、`answer_relevancy`）。

> **注意**：检索指标不受前缀影响，始终由 builtin 后端计算，保持原始名称。

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
- **两个后端均支持**：builtin 使用自定义 prompt 逐条判断上下文相关性；RAGAS 使用框架自带逻辑

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
- **两个后端均支持**：builtin 使用自定义 prompt 逐句判断信息覆盖度；RAGAS 使用框架自带逻辑

**解读**：
- **0.8+**：检索结果信息覆盖充分
- **0.5-0.8**：部分关键信息未被检索到
- **< 0.5**：大量关键信息缺失

**改进建议**：
- 增加 `top_k` 值
- 调整 `chunk_size` 和 `chunk_overlap`
- 考虑混合检索（BM25 + 向量）

### Answer Correctness（答案正确性）

答案正确性综合评估生成答案与参考答案的匹配程度，包含两个关键方面：
- **事实相似性**：使用 claim-level 对比，计算 TP/FP/FN，得出 F1 分数
- **语义相似度**：基于 Embedding 向量的余弦相似度

最终分数是两者的加权平均（默认权重各 0.5）。

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

两个评测后端均通过统一的 LLM 客户端工厂 `create_llm_client()`（位于 `src/utils.py`）连接 LongCat API，适配方式如下：

1. **统一工厂**：`create_llm_client(llm_config, mode)` 支持两种模式
   - `mode="sdk"`：返回 Anthropic SDK 客户端（builtin 后端使用）
   - `mode="langchain"`：返回 `LangchainLLMWrapper(ChatAnthropic)` （RAGAS 后端使用）
2. **URL 适配**：自动在 `base_url` 后追加 `/anthropic` 路径
3. **认证方式**：通过 `default_headers` 传递 Bearer Token 认证（`api_key="dummy"` + 真实 key 在 Header 中）
4. **LLM 包装**：RAGAS 模式下使用 `LangchainLLMWrapper` 将 LangChain LLM 包装为 RAGAS 兼容格式

```python
# 内部实现逻辑（无需手动配置）
# SDK 模式（builtin）
Anthropic(
    api_key="dummy",
    base_url=base_url,
    default_headers={
        "Authorization": f"Bearer {llm_config['api_key']}",
        "Content-Type": "application/json",
    },
)

# LangChain 模式（RAGAS）
ChatAnthropic(
    model=llm_config["model_name"],
    api_key="dummy",
    base_url=base_url,
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

# 创建 RAGAS 评测器（config 参数中的 ragas 子键会被读取）
ragas = RagasEvaluator(config={
    "ragas": {
        "run_config": {"max_workers": 5, "timeout": 60, "max_retries": 3},
        "embedding": {"model_name": "BAAI/bge-large-zh-v1.5", "device": "cuda"},
    }
})
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

根据配置动态创建评测器（与 `run_experiment.py` 中的 `_create_evaluators` 一致）：

```python
from eval.evaluators import BuiltinEvaluator, RagasEvaluator

def create_evaluators(backends: list, system_config: dict) -> dict:
    evaluators = {}
    for backend in backends:
        if backend == "builtin":
            evaluators["builtin"] = BuiltinEvaluator(config=system_config)
        elif backend == "ragas":
            ragas_config = system_config.get("evaluation", {}).get("ragas", {})
            evaluators["ragas"] = RagasEvaluator(config={**system_config, "ragas": ragas_config})
    return evaluators

evaluators = create_evaluators(["builtin", "ragas"], system_config)
```

---

## 架构变更记录

### run_eval.py 已废弃

`eval/run_eval.py` 已废弃，将在未来版本中移除。请使用 `eval/run_experiment.py` 配合实验配置 YAML 文件：

```bash
# 旧方式（已废弃）
pixi run python eval/run_eval.py --test-data eval/test_data.json

# 新方式（推荐）
pixi run python eval/run_experiment.py --config exp_configs/your_experiment.yaml
```

### 旧版评测路径已移除

`_evaluate_test_set_legacy()` 函数已被移除。所有评测现在通过 Evaluator 抽象层（`BuiltinEvaluator` / `RagasEvaluator`）进行，必须提供 `exp_config` 和 `system_config`。

### metrics.py 拆分为子模块

`eval/metrics.py` 已拆分为 `eval/metrics/` 目录下的子模块：

| 子模块 | 内容 |
|--------|------|
| `retrieval.py` | `calculate_hit_rate`, `calculate_mrr`, `calculate_ndcg` |
| `chunk.py` | `calculate_chunk_hit_rate`, `calculate_chunk_mrr`, `calculate_chunk_ndcg` |
| `dedup.py` | `deduplicate_by_document`, `calculate_dedup_hit_rate`, `calculate_dedup_mrr`, `calculate_dedup_ndcg` |
| `fpr.py` | `calculate_false_positive_rate` |
| `generation.py` | `calculate_faithfulness`, `calculate_answer_relevancy` |
| `llm_retrieval.py` | `calculate_context_precision`, `calculate_context_recall` |
| `utils.py` | `normalize_source`, `normalize_source_with_equivalence` 等工具函数 |

> **向后兼容**：`eval/metrics/__init__.py` 重新导出了所有公共函数，原有 `from eval.metrics import calculate_hit_rate` 等导入方式仍然有效。

---

## 常见问题

### Q: RAGAS 评测报 ImportError 怎么办？

A: RAGAS 需要额外的依赖包。运行以下命令安装：

```bash
pixi add langchain-anthropic langchain-community
```

### Q: RAGAS 指标需要参考答案（reference），但测试数据没有怎么办？

A: `context_precision`、`context_recall`、`answer_correctness`、`semantic_similarity` 需要 `reference` 才能计算。如果测试数据中没有 `expected_answer` 字段，这些指标将被跳过或返回空值。建议：
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
