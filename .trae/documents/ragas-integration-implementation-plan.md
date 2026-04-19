# RAGAS 评测系统集成计划

## 一、背景与目标

### 当前状态

* 项目已有自研评测系统，位于 `eval/` 目录

* 检索指标：hit\_rate, mrr, ndcg（纯数学计算）

* 生成指标：faithfulness, answer\_relevancy（LLM-based，使用 Anthropic SDK）

* 评测流程在 `run_eval.py` 中实现

### 目标

1. 添加 RAGAS 作为并行评测系统
2. 支持在配置文件中灵活指定评测后端（自研、RAGAS 或两者）
3. 为将来纳入更多评测系统预留扩展空间
4. 尽量独立实现，避免与正在修复 bug 的分支产生冲突

***

## 二、架构设计

### 2.1 评测器抽象层

创建统一的评测器接口，支持多种评测后端：

```
eval/
├── evaluators/                    # 新建目录：评测器抽象层
│   ├── __init__.py
│   ├── base.py                    # 评测器抽象基类
│   ├── builtin_evaluator.py       # 自研评测器封装
│   └── ragas_evaluator.py         # RAGAS 评测器实现
├── metrics.py                     # 保持不变（自研指标实现）
├── run_eval.py                    # 修改：集成评测器选择逻辑
└── ...
```

### 2.2 评测器接口设计

```python
# eval/evaluators/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class EvaluationResult:
    """统一的评测结果格式"""
    question_id: str
    question: str
    answer: str
    contexts: List[str]
    retrieval_metrics: Dict[str, float]
    generation_metrics: Dict[str, float]
    error: Optional[str] = None

class BaseEvaluator(ABC):
    """评测器抽象基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """评测器名称"""
        pass
    
    @property
    @abstractmethod
    def supported_retrieval_metrics(self) -> List[str]:
        """支持的检索指标"""
        pass
    
    @property
    @abstractmethod
    def supported_generation_metrics(self) -> List[str]:
        """支持的生成指标"""
        pass
    
    @abstractmethod
    def evaluate_single(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        expected_sources: Optional[List[str]] = None,
        expected_answer: Optional[str] = None,
    ) -> EvaluationResult:
        """评测单个样本"""
        pass
    
    @abstractmethod
    def evaluate_batch(
        self,
        samples: List[Dict[str, Any]],
        llm_config: Optional[Dict[str, str]] = None,
    ) -> List[EvaluationResult]:
        """批量评测"""
        pass
```

### 2.3 配置系统扩展

#### 2.3.1 config.yaml 新增配置

```yaml
# 评测系统配置
evaluation:
  # 评测后端选择：["builtin"], ["ragas"], 或 ["builtin", "ragas"]
  backends: ["builtin"]
  
  # RAGAS 专用配置
  ragas:
    enabled: false
    llm_backend: "anthropic"        # 使用 LangChain Anthropic 接口（推荐）
    embeddings_backend: "local"     # 使用本地 BGE 或 "openai"
    run_config:
      max_workers: 5
      timeout: 60
      max_retries: 3
```

**说明**：

* `llm_backend: "anthropic"` 是推荐配置，因为 LangChain Anthropic 接口完全兼容 LongCat API

* 不使用 `openai_compatible`，因为 LangChain OpenAI 的结构化输出存在问题

#### 2.3.2 实验配置 YAML 扩展

```yaml
evaluation:
  backends: ["builtin", "ragas"]  # 同时使用两个评测系统
  
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
      # RAGAS 特有指标（当 backends 包含 "ragas" 时可用）
      - "context_precision"
      - "context_recall"
      - "factual_correctness"
```

***

## 三、实施步骤

### Step 1: 创建评测器抽象层

**文件**: `eval/evaluators/base.py`（新建）

1. 定义 `EvaluationResult` 数据类
2. 定义 `BaseEvaluator` 抽象基类
3. 定义评测器工厂函数

**设计原则**:

* 独立于现有代码，不修改 `eval/metrics.py`

* 为未来扩展预留接口

### Step 2: 封装自研评测器

**文件**: `eval/evaluators/builtin_evaluator.py`（新建）

1. 实现 `BuiltinEvaluator` 类，继承 `BaseEvaluator`
2. 内部调用现有的 `eval/metrics.py` 函数
3. 保持与现有评测逻辑完全一致

**优势**:

* 不修改现有 `metrics.py`，避免冲突

* 提供统一接口，便于与其他评测器对比

### Step 3: 实现 RAGAS 评测器

**文件**: `eval/evaluators/ragas_evaluator.py`（新建）

#### 3.1 LLM 适配器

**重要说明**：根据 `plgd/LongCat-API适配性分析.md` 文档的测试结果：

* ❌ **LangChain OpenAI** 的结构化输出存在问题（ValidationError）

* ✅ **LangChain Anthropic** 完全兼容，所有功能正常

* RAGAS 的评测指标需要结构化输出（如 Faithfulness 需要提取 statements）

因此，我们使用 **LangChain Anthropic** 接口连接 LongCat API。

```python
def create_ragas_llm(llm_config: Dict[str, str]) -> BaseRagasLLM:
    """
    创建 RAGAS 兼容的 LLM
    
    使用 ChatAnthropic 连接 LongCat API（推荐方案）
    
    根据 LongCat API 适配性分析：
    - LangChain Anthropic 接口完全兼容
    - 结构化输出功能稳定可靠
    - 响应速度快
    
    Args:
        llm_config: 包含 api_key, base_url, model_name 的配置字典
    
    Returns:
        RAGAS 兼容的 LLM 实例
    """
    from langchain_anthropic import ChatAnthropic
    from ragas.llms import LangchainLLMWrapper
    
    base_url = llm_config["base_url"].rstrip("/")
    if not base_url.endswith("/anthropic"):
        base_url = f"{base_url}/anthropic"
    
    lc_llm = ChatAnthropic(
        model=llm_config["model_name"],
        temperature=0.0,
        base_url=base_url,
        api_key="dummy",
        default_headers={
            "Authorization": f"Bearer {llm_config['api_key']}",
            "Content-Type": "application/json"
        }
    )
    return LangchainLLMWrapper(llm=lc_llm)
```

**认证配置说明**：

* `api_key` 参数需要设置为占位符（如 "dummy"）

* 真实的 API Key 必须在 `default_headers` 中传递

* `base_url` 应为 `https://api.longcat.chat/anthropic`，不要加 `/v1`

#### 3.2 Embeddings 适配器

```python
def create_ragas_embeddings(config: Dict[str, Any]) -> BaseRagasEmbeddings:
    """
    创建 RAGAS 兼容的 Embeddings
    
    复用项目现有的 BGE 模型
    """
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    
    embeddings = HuggingFaceEmbeddings(
        model_name=config["embedding"]["model_name"],
        model_kwargs={"device": config["embedding"]["device"]},
    )
    return LangchainEmbeddingsWrapper(embeddings=embeddings)
```

#### 3.3 数据转换

```python
def build_ragas_dataset(
    samples: List[Dict[str, Any]]
) -> EvaluationDataset:
    """
    将项目评测数据格式转换为 RAGAS 格式
    """
    from ragas import SingleTurnSample, EvaluationDataset
    
    ragas_samples = []
    for sample in samples:
        ragas_samples.append(
            SingleTurnSample(
                user_input=sample["question"],
                response=sample["answer"],
                retrieved_contexts=sample["contexts"],
                reference=sample.get("expected_answer"),
            )
        )
    return EvaluationDataset(samples=ragas_samples)
```

#### 3.4 指标工厂

```python
def create_ragas_metrics(
    metric_names: List[str],
    llm: BaseRagasLLM,
    embeddings: BaseRagasEmbeddings,
) -> List[Metric]:
    """
    根据配置创建 RAGAS 指标实例
    """
    from ragas.metrics import (
        Faithfulness,
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        FactualCorrectness,
        SemanticSimilarity,
    )
    
    metric_map = {
        "faithfulness": Faithfulness,
        "answer_relevancy": AnswerRelevancy,
        "context_precision": ContextPrecision,
        "context_recall": ContextRecall,
        "factual_correctness": FactualCorrectness,
        "semantic_similarity": SemanticSimilarity,
    }
    
    metrics = []
    for name in metric_names:
        if name in metric_map:
            metric = metric_map[name]()
            metric.llm = llm
            if hasattr(metric, "embeddings"):
                metric.embeddings = embeddings
            metrics.append(metric)
    
    return metrics
```

### Step 4: 扩展配置验证

**文件**: `src/experiment.py`（修改）

1. 新增 `VALID_EVALUATION_BACKENDS` 常量
2. 扩展 `ExperimentConfig.validate()` 方法
3. 新增 RAGAS 指标验证

```python
VALID_EVALUATION_BACKENDS = {"builtin", "ragas"}
VALID_RAGAS_METRICS = {
    "faithfulness", "answer_relevancy",
    "context_precision", "context_recall",
    "factual_correctness", "semantic_similarity",
}
```

### Step 5: 集成到评测流程

**文件**: `eval/run_eval.py`（修改）

#### 5.1 评测器选择逻辑

```python
def get_evaluators(
    config: Dict[str, Any],
    evaluation_config: Dict[str, Any],
) -> List[BaseEvaluator]:
    """
    根据配置创建评测器实例
    """
    from eval.evaluators import BuiltinEvaluator, RagasEvaluator
    
    backends = evaluation_config.get("backends", ["builtin"])
    evaluators = []
    
    if "builtin" in backends:
        evaluators.append(BuiltinEvaluator())
    
    if "ragas" in backends:
        ragas_config = config.get("evaluation", {}).get("ragas", {})
        if ragas_config.get("enabled", False):
            evaluators.append(RagasEvaluator(config))
    
    return evaluators
```

#### 5.2 混合评测流程

```python
def run_evaluation(
    pipeline: RAGPipeline,
    test_data_path: str,
    output_dir: str,
    evaluators: List[BaseEvaluator],
    llm_config: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    使用多个评测器执行评测
    """
    # 1. 加载测试数据
    test_cases = load_test_data(test_data_path)
    
    # 2. 执行 RAG 查询，收集结果
    samples = []
    for test_case in test_cases:
        response = pipeline.query(test_case["question"])
        samples.append({
            "question": test_case["question"],
            "answer": response["answer"],
            "contexts": response["contexts"],
            "expected_sources": test_case.get("expected_sources"),
            "expected_answer": test_case.get("expected_answer"),
        })
    
    # 3. 使用各评测器评测
    all_results = {}
    for evaluator in evaluators:
        results = evaluator.evaluate_batch(samples, llm_config)
        all_results[evaluator.name] = results
    
    # 4. 汇总报告
    return aggregate_results(all_results)
```

### Step 6: 报告系统扩展

**文件**: `eval/experiment_reporter.py`（修改）

1. 报告模板增加 RAGAS 指标列
2. 支持多评测器结果对比
3. 输出格式保持向后兼容

### Step 7: 依赖安装

**文件**: `pixi.toml`（修改）

```toml
[dependencies]
# 现有依赖保持不变
ragas = ">=0.4.3,<0.5"

# 新增依赖
langchain-anthropic = ">=0.2.0"     # LangChain Anthropic 接口（推荐）
langchain-community = ">=0.3.0"     # HuggingFace Embeddings
```

**说明**：

* 使用 `langchain-anthropic` 而非 `langchain-openai`，因为 Anthropic 接口完全兼容 LongCat API

* `langchain-community` 用于 HuggingFace Embeddings 封装

### Step 8: 测试

#### 8.1 单元测试

**文件**: `tests/test_evaluators.py`（新建）

* 测试评测器基类

* 测试自研评测器封装

* 测试 RAGAS 评测器

* 测试数据转换

#### 8.2 集成测试

**文件**: `tests/test_run_eval.py`（扩展）

* 测试多评测器配置加载

* 测试混合评测流程

* 测试报告生成

***

## 四、文件变更清单

| 文件                                     | 变更类型   | 说明                        |
| -------------------------------------- | ------ | ------------------------- |
| `eval/evaluators/__init__.py`          | **新建** | 评测器模块初始化                  |
| `eval/evaluators/base.py`              | **新建** | 评测器抽象基类                   |
| `eval/evaluators/builtin_evaluator.py` | **新建** | 自研评测器封装                   |
| `eval/evaluators/ragas_evaluator.py`   | **新建** | RAGAS 评测器实现               |
| `eval/run_eval.py`                     | 修改     | 集成评测器选择逻辑                 |
| `eval/run_experiment.py`               | 修改     | 集成 RAGAS 到实验流程            |
| `eval/experiment_reporter.py`          | 修改     | 报告增加 RAGAS 指标             |
| `src/experiment.py`                    | 修改     | 扩展配置验证                    |
| `config.yaml`                          | 修改     | 新增 RAGAS 配置段              |
| `pixi.toml`                            | 修改     | 新增 langchain-anthropic 依赖 |
| `tests/test_evaluators.py`             | **新建** | 评测器单元测试                   |
| `tests/test_run_eval.py`               | 修改     | 扩展评测流程测试                  |

***

## 五、设计原则

### 5.1 渐进式集成

* RAGAS 作为可选评测后端，不替换现有自研系统

* 通过配置开关灵活选择

* 初期用于对比实验，验证评测准确性

### 5.2 配置驱动

* 所有 RAGAS 参数通过 `config.yaml` 控制

* 实验配置支持指定评测后端

* 支持混合评测模式

### 5.3 向后兼容

* 现有评测流程和结果格式不受影响

* 默认使用自研评测器

* 报告格式保持兼容

### 5.4 独立性设计

* 新建 `eval/evaluators/` 目录，不修改现有 `eval/metrics.py`

* 减少与正在修复 bug 的分支冲突风险

* 评测器接口独立，便于扩展

### 5.5 LLM 复用

* RAGAS 评估 LLM 复用项目已有的 LLM 预设配置

* 使用 LangChain Anthropic 接口连接 LongCat API（推荐方案）

* Anthropic 接口完全兼容 LongCat API，结构化输出稳定可靠

* Embeddings 复用项目现有的 BGE 模型

***

## 六、风险评估

| 风险                  | 概率 | 影响 | 缓解措施                           |
| ------------------- | -- | -- | ------------------------------ |
| RAGAS 0.4.x API 不稳定 | 中  | 中  | 锁定版本 `>=0.4.3,<0.5`，封装隔离       |
| 中文评测效果不佳            | 高  | 高  | 保留自研实现，支持对比实验                  |
| LLM 适配复杂            | 低  | 中  | 使用 LangChain Anthropic 接口，完全兼容 |
| 与修复分支冲突             | 低  | 高  | 新建独立目录，最小化修改现有文件               |
| 评测结果不一致             | 高  | 低  | 这正是对比实验的目的                     |

***

## 七、实施优先级

### Phase 1: 核心实现（高优先级）

1. 创建评测器抽象层（`eval/evaluators/base.py`）
2. 封装自研评测器（`eval/evaluators/builtin_evaluator.py`）
3. 实现 RAGAS 评测器（`eval/evaluators/ragas_evaluator.py`）

### Phase 2: 集成与配置（中优先级）

1. 扩展配置验证（`src/experiment.py`）
2. 集成到评测流程（`eval/run_eval.py`）
3. 扩展报告系统（`eval/experiment_reporter.py`）

### Phase 3: 测试与验证（中优先级）

1. 编写单元测试
2. 编写集成测试
3. 运行对比实验

***

## 八、预期成果

1. **可扩展的评测系统架构**：支持多种评测后端并存
2. **RAGAS 集成**：提供业界标准的评测指标
3. **灵活的配置系统**：通过配置文件选择评测后端
4. **对比实验能力**：支持自研与 RAGAS 结果对比
5. **向后兼容**：现有评测流程不受影响

***

## 九、后续优化方向

1. **自定义 Prompt**：为 RAGAS 指标定制中文 Prompt
2. **性能优化**：支持并行评测，减少评测时间
3. **可视化对比**：提供评测结果对比图表
4. **更多指标**：集成 RAGAS 的更多评测指标
5. **评测器注册机制**：支持动态注册新的评测器

---

## 十、实施注意事项

### 10.1 官方文档参考

**重要**：在实现过程中，对 RAGAS 的使用方式和 API 有疑问时，请及时查阅官方文档：

- **官方文档**：https://docs.ragas.io/en/stable/
- **核心概念**：https://docs.ragas.io/en/stable/concepts/
- **API 参考**：https://docs.ragas.io/en/stable/references/
- **指标文档**：https://docs.ragas.io/en/stable/concepts/metrics/overview/

### 10.2 关键 API 变更

RAGAS 0.4.x 版本进行了重大 API 重构：
- `evaluate()` 函数已被标记为 deprecated，但仍可用
- 推荐使用新的 `EvaluationDataset` 和 `SingleTurnSample` 抽象
- LLM 和 Embeddings 需要通过 `LangchainLLMWrapper` 和 `LangchainEmbeddingsWrapper` 包装

### 10.3 LongCat API 兼容性

根据 `plgd/LongCat-API适配性分析.md` 文档：
- ✅ 使用 LangChain Anthropic 接口（推荐）
- ❌ 避免使用 LangChain OpenAI 的结构化输出功能
- 认证配置需要使用 `default_headers` 传递 API Key

### 10.4 实施检查清单

在每个实施步骤完成后，请检查：
- [ ] 是否查阅了相关的 RAGAS 官方文档
- [ ] 是否参考了 LongCat API 适配性分析文档
- [ ] 是否编写了对应的单元测试
- [ ] 是否验证了与现有系统的兼容性

