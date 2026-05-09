# 代码质量审查报告

> 审查日期：2026-05-09 | 版本：v0.1.16 | 审查范围：全量 Python 代码（~88K 行）

---

## 目录

1. [总览：代码量与分布](#1-总览代码量与分布)
2. [P0 — 严重问题：God 文件与 God 函数](#2-p0--严重问题god-文件与-god-函数)
3. [P1 — 臃肿与屎山：大量重复代码](#3-p1--臃肿与屎山大量重复代码)
4. [P2 — 过度设计：不该存在的抽象层](#4-p2--过度设计不该存在的抽象层)
5. [P3 — Pydantic 瞎写的地方](#5-p3--pydantic-瞎写的地方)
6. [P4 — 伪需求与根本没必要写的代码](#6-p4--伪需求与根本没必要写的代码)
7. [P5 — 测试覆盖不足与测试没测到点上](#7-p5--测试覆盖不足与测试没测到点上)
8. [P6 — 其他代码异味](#8-p6--其他代码异味)
9. [修复优先级路线图](#9-修复优先级路线图)

---

## 1. 总览：代码量与分布

| 目录 | 文件数 | 行数 | 占比 |
|------|--------|------|------|
| `src/` | 113 | 35,714 | 40.6% |
| `tests/` | 72 | 38,727 | 44.0% |
| `eval/` | 42 | 12,284 | 14.0% |
| `main.py` | 1 | 1,212 | 1.4% |
| **总计** | **228** | **87,937** | **100%** |

**核心发现**：测试代码比业务代码多，但测试质量堪忧——大量测试在测框架/库行为而非业务逻辑，存在假测试（`pass`），过度 mock 导致测试失去意义。

---

## 2. P0 — 严重问题：God 文件与 God 函数

### 2.1 `src/test_generation/generator.py` — 1563 行 God 类

**这是整个代码库问题最严重的文件。**

`TestSetGenerator` 一个类承担了 10+ 种职责：

| 方法 | 行数 | 职责 |
|------|------|------|
| `generate_test_set` | ~120 | 编排入口 |
| `generate_hybrid_questions` | ~380 | 混合策略生成 |
| `generate_golden_testset` | ~370 | 黄金测试集生成 |
| `generate_document_based_questions` | ~150 | 文档级问题生成 |
| `supplement_document_based_questions` | ~100 | 补充问题生成 |
| `_post_process_question` | ~120 | 后处理 |
| `_generate_hybrid_question` | ~170 | 单个混合问题生成 |

**核心问题**：`generate_hybrid_questions` 和 `generate_golden_testset` 中有大量完全相同的逻辑（补充问题循环、source_files 赋值、segment 构建），估计有 200+ 行重复代码。

**建议**：拆分为 `QuestionGenerator`（核心生成逻辑）+ `TestSetOrchestrator`（编排逻辑），提取公共方法消除重复。

---

### 2.2 `eval/runner/core.py` — `run_experiment()` 690 行 God 函数

一个函数承担了 8 种职责：加载配置、解析 resume/reuse 参数、创建实验目录（含 3 种分支）、初始化 profiler、准备 meal/chunks/test set、遍历 variant 执行评估、生成报告、保存 token 摘要和 profiling 数据。

**这是不可测试、不可复用的典型反例。**

---

### 2.3 `src/app_pages/maintenance.py` — 1160 行 God 文件

`render_maintenance()` 函数长达 ~630 行，同时处理 15+ 个 session state 变量初始化、侧边栏渲染、聊天消息渲染、中断处理、经验扫描、报告下载、Agent 架构图渲染。

---

### 2.4 `src/agent/tools.py` — 1033 行 God 文件

20+ 个 `@tool` 装饰的函数，每个都重复相同的模式：

```python
@tool
def xxx_tool(...) -> str:
    try:
        from src.utils import load_config
        config = load_config()
        # ... 业务逻辑 ...
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"xxx_tool failed: {e}")
        return f"Error: {e}"
```

`load_config()` 调用重复 9+ 次，`json.dumps` 返回模式重复 15+ 次，`try/except` 错误处理模式重复 20 次。

---

### 2.5 `src/agent/cli.py` — 330+ 行 God 函数

`run_agent()` 函数同时处理 CLI 参数解析、数据库连接初始化、会话管理、交互式输入循环、CLI 命令分发、Agent 调用与结果处理、中断处理。

---

### 2.6 `eval/runner/metrics.py` — `compute_aggregate_metrics()` 226 行 God 函数

混合了 9 种聚合逻辑：文档级检索指标、生成指标、chunk 级指标、dedup 指标、FPR、多样性、幻觉率、按问题类型分组、LLM 检索指标。

---

### 2.7 `eval/evaluators/builtin_evaluator.py` — `evaluate_single()` 200 行 God Method

200 行 if-chain，每个 metric 是一个 if 判断 + 函数调用。应使用注册表/策略模式替代。

---

## 3. P1 — 臃肿与屎山：大量重复代码

### 3.1 token tracker 重建逻辑完全重复

`eval/runner/core.py` 第 829-852 行和第 909-926 行是**完全相同的两段代码**，从 `variant_result["token_usage"]["records"]` 反序列化为 `DetailedTokenUsage` 并 merge 到 `experiment_tracker`。

### 3.2 serial/concurrent 采样逻辑重复

`eval/runner/evaluation.py` 中 `_collect_rag_samples_serial()` 和 `_query_single_question()` 存在 ~120 行重复代码，sample 构建逻辑几乎完全相同。

### 3.3 RAGAS evaluator ref/no-ref 分支重复

`eval/evaluators/ragas_evaluator.py` 第 551-599 行 vs 第 601-649 行，`samples_with_ref` 和 `samples_without_ref` 两个分支的 RAGAS evaluate + 结果解析逻辑几乎完全相同。

### 3.4 LLM 调用 + JSON 解析重复模式

`eval/metrics/llm_retrieval.py` 和 `eval/metrics/generation.py` 中 4+ 处完全相同的模式：创建 client → 构建 prompt → call_with_retry → 正则提取 JSON → 判断 verdict。应提取为通用的 `_llm_judge()` 辅助函数。

### 3.5 chunk 匹配逻辑重复

`eval/metrics/chunk.py` 中 `calculate_chunk_hit_rate()`、`calculate_chunk_mrr()`、`calculate_chunk_ndcg()` 的匹配逻辑（exact match + adjacent tolerance）完全重复。

### 3.6 推荐逻辑重复

`eval/reporter/template_single.py` 和 `eval/reporter/template_variant.py` 中的阈值判断 + 建议文本逻辑几乎完全相同。

### 3.7 `_resolve_db_path` 函数重复

`src/agent/checkpoint.py:15-28` 和 `src/agent/session_manager.py:11-24` 包含完全相同的 `_resolve_db_path` 函数实现。

### 3.8 Reporter save 方法重复

`src/agent/reporters/comparison_report.py:142-178` 和 `src/agent/reporters/maintenance_report.py:120-157` 的 `save` 方法几乎完全相同。

### 3.9 Agent state 字典构造重复

维护 agent 所需的 state 字典在 `src/agent/cli.py`（3 处）和 `src/app_pages/maintenance.py`（3 处）被手动构造，每次 12+ 个字段。

### 3.10 流式处理逻辑重复

`src/app_pages/maintenance.py` 中 `_render_streaming_agent` 和 `_resume_interrupt_streaming` 共享几乎完全相同的事件处理代码。

---

## 4. P2 — 过度设计：不该存在的抽象层

### 4.1 `ExperimentReporter` 无用委托方法

`eval/reporter/__init__.py` 第 118-173 行有 6 个 static 方法，每个都是一行委托：

```python
@staticmethod
def _get_generation_metric(metric_name, metrics_data):
    return get_generation_metric(metric_name, metrics_data)

@staticmethod
def _get_all_generation_metrics(metrics_data):
    return get_all_generation_metrics(metrics_data)
```

这些方法完全没有存在的必要，调用方应直接使用 `formatters.py` 中的函数。

### 4.2 `eval/metrics/utils.py` — 不必要的间接层

`create_llm_client()` 只是 `src.utils.create_llm_client` 的薄包装，增加了不必要的间接层。

### 4.3 `eval/experiment_reporter.py` — 纯转发模块

17 行文件，只是从 `eval.reporter` 重新导出符号。兼容性垫片，如无旧依赖方可移除。

### 4.4 `src/testset_review/pdf_viewer.py` — 死代码

```python
from scripts.pdf_viewer import PDFViewer
__all__ = ["PDFViewer"]
```

仅仅是从 `scripts.pdf_viewer` 重新导出，没有任何附加价值。

### 4.5 `src/issue/migrate.py` — 630 行一次性代码驻留生产代码库

从 `backlog.md` 迁移到 issue 文件的一次性工具，不应长期驻留在生产代码中。

### 4.6 `ExperimentConfigSchema` — Pydantic 模型所有字段都是 `Any`

`src/experiment_schemas.py` 中的 `ExperimentConfigSchema` 所有字段类型都是 `Any`，完全放弃了 Pydantic 的类型检查能力。这个模型本质上只是一个手动验证的容器，Pydantic 在这里形同虚设。详见第 5 节。

### 4.7 `ExperimentFingerprint` 过度抽象

`src/experiment_reuse.py` 中的 `ExperimentFingerprint` 有 `matches()`、`diff()`、`compute_hash()` 三个方法，但 `matches()` 只检查 5 个字段，`diff()` 检查 9 个字段，`compute_hash()` 又用全部 9 个字段——三者的字段集合不一致，容易引发混淆。

### 4.8 `ResumeConfig` + `ReportReuseConfig` + `ExperimentConfig` — dataclass 与 Pydantic 混用

项目同时使用 `@dataclass`（`ExperimentConfig`、`ResumeConfig`、`ReportReuseConfig`）和 Pydantic `BaseModel`（`AppConfig`、`ExperimentConfigSchema`）来定义配置模型。两套序列化/反序列化逻辑并存，增加了认知负担和维护成本。

---

## 5. P3 — Pydantic 瞎写的地方

### 5.1 `ExperimentConfigSchema` — 全 `Any` 字段，Pydantic 形同虚设

```python
class ExperimentConfigSchema(BaseModel):
    model_config = {"extra": "allow"}

    name: Any
    description: Any
    data: Any
    test_sets: Any
    variants: Any
    evaluation: Any
    force_overwrite: Any = []
```

**所有字段都是 `Any`**，Pydantic 的类型检查、自动转换、验证能力全部被放弃。验证逻辑全部手动写在 `model_validator` 中的十几个 `_validate_*` 方法里。这等于用 Pydantic 写了一个手动的验证框架，完全背离了 Pydantic 的设计理念。

**正确做法**：为每个字段定义具体的类型（`str`、`list[dict[str, Any]]` 等），用 `Field` 约束和 `model_validator` 做跨字段校验。

### 5.2 `model_config = {"extra": "allow"}` 泛滥

`config_schema.py` 中 **每一个 Pydantic 模型** 都设置了 `extra = "allow"`。这意味着任何拼写错误的配置键都会被静默接受而非报错，完全丧失了配置验证的意义。

例如，用户在 `config.yaml` 中写了 `topp_k: 5`（拼写错误），Pydantic 不会报错，而是默默忽略。对于一个配置驱动的系统，这是危险的。

**建议**：根模型 `AppConfig` 可以 `extra = "allow"` 以支持扩展，但子模型（如 `RetrievalConfig`、`ChunkerConfig`）应使用 `extra = "forbid"` 来严格校验。

### 5.3 `LLMEvaluatorConfig` — 7 个子指标各自一个字段，过度展开

```python
class LLMEvaluatorConfig(BaseModel):
    extract_statements: LLMEvaluatorSubConfig = ...
    verify_statements: LLMEvaluatorSubConfig = ...
    faithfulness: LLMEvaluatorSubConfig = ...
    answer_relevancy: LLMEvaluatorSubConfig = ...
    context_precision: LLMEvaluatorSubConfig = ...
    context_recall: LLMEvaluatorSubConfig = ...
    context_relevance: LLMEvaluatorSubConfig = ...
    infer_check: LLMEvaluatorSubConfig = ...
```

8 个字段类型完全相同（`LLMEvaluatorSubConfig`），只是默认值不同。这应该用 `dict[str, LLMEvaluatorSubConfig]` 来表达，更灵活且避免每新增一个指标就要改模型定义。

### 5.4 `EvaluationRagasConfig.run_config` — `dict` 类型放弃验证

```python
run_config: dict = Field(
    default_factory=lambda: {
        "max_workers": 10,
        "timeout": 180,
        "max_retries": 3,
    }
)
```

用 `dict` 类型意味着 `max_workers: "hello"` 也会通过验证。应定义 `RunConfigConfig` Pydantic 模型。

### 5.5 `TestGenerationConfig.validation` — `dict` 类型放弃验证

```python
validation: dict = Field(default_factory=lambda: {"check_proper_nouns": False})
```

同上，应定义具体的 Pydantic 模型。

### 5.6 `AgentConfig.checkpoint` — `dict` 类型放弃验证

```python
checkpoint: dict = Field(
    default_factory=lambda: {"db_path": "data/agent_checkpoints.db"}
)
```

同上。

---

## 6. P4 — 伪需求与根本没必要写的代码

### 6.1 `eval/evaluators/error_handler.py` — `safe_metric_calculation()` 死代码

`safe_metric_calculation()` 装饰器（第 28-49 行）在整个项目中**没有任何调用点**。写了装饰器却从没用过。

### 6.2 `eval/parser_benchmark/runner.py` — `_compute_config_hash()` 死代码

static method 从未被调用。

### 6.3 `eval/visualize.py` — `extract_metrics()` 可能死代码

查找 `result.get("aggregated_metrics", {})` 这个 key，但整个项目中没有任何地方生成 `aggregated_metrics` 字段。这个函数很可能是过时数据格式的遗留。

### 6.4 `src/agent/memory/experience_store.py` — 遗留方法

`_save_experience_legacy` 方法仅为了向后兼容而存在。如果迁移已完成，应删除。

### 6.5 `eval/runner/preparation.py` — `prepare_legacy_test_set()` 遗留代码

150 行处理已废弃的配置格式。整个函数应标记为待移除。

### 6.6 `src/testset_review/pdf_viewer.py` — 不必要的间接层

2 行文件，仅重新导出。没有附加价值。

### 6.7 `eval/runner/core.py` — `del pipeline` + `gc.collect()` 反模式

```python
del pipeline
gc.collect()
```

Python 的 GC 不需要手动干预。`del` 只减少引用计数，`gc.collect()` 在正常场景下是多余的。

### 6.8 `eval/runner/asset_verifier.py` — 使用已废弃的 `pkg_resources`

`collect_environment_info()` 使用 `pkg_resources`（已废弃），应改用 `importlib.metadata`。另外 `key_packages` 列表中有拼写错误：`"pymupdf4llllm"` 多了一个 `l`。

### 6.9 `src/issue/migrate.py` — 630 行一次性迁移工具

从 `backlog.md` 迁移到 issue 文件是一次性操作，不应长期驻留在生产代码库中。

---

## 7. P5 — 测试覆盖不足与测试没测到点上

### 7.1 假测试（永远通过的测试）

`tests/test_run_experiment.py` 第 1130-1132 行：

```python
def test_dual_backend_results_have_namespace_prefix(self):
    """Test that dual-backend results have namespace prefixes on generation metrics."""
    pass
```

方法体只有 `pass`，什么都不测试。**必须删除或替换。**

### 7.2 没有测试正确的东西

`tests/test_agent.py` 的 `TestToolFunctions` 类中 7 个测试全部是：

```python
def test_list_meals_tool_exists(self):
    from src.agent.tools import list_meals
    assert list_meals.name == "list_meals"
    assert "List all available meals" in list_meals.description
```

这些测试验证的是"对象存在且有 name 属性"，而非"工具行为正确"。即使工具完全损坏，只要 `.name` 属性存在，测试仍然通过。

### 7.3 平凡测试

`tests/test_agent.py` 的 `TestMaintenanceState` 测试 Python TypedDict 的赋值和取值行为：

```python
state: MaintenanceState = {"messages": [], "current_meal": "", ...}
assert state["messages"] == []
assert state["current_meal"] == "test_meal"
```

这是 Python 语言本身的保证，不是项目代码的逻辑。

### 7.4 测试框架而非项目代码

| 文件 | 测试内容 | 问题 |
|------|----------|------|
| `test_agent.py` | `TestLLMClientCaching` | 测试 `functools.lru_cache` 的缓存行为 |
| `test_agent.py` | `TestMaintenanceStateNewFields` | 测试 TypedDict 能否存储新字段 |
| `test_experiment.py` | `test_to_dict` | 测试 dict 的赋值行为 |
| `test_meal.py` | `test_to_dict` | 测试 dataclass 的序列化行为 |
| `test_run_experiment.py` | `test_result_merging_builtin_and_ragas` | 测试 `dict.update()` 的行为 |
| `test_evaluators.py` | `TestEvaluationResult` | 测试 dataclass 的创建和 `to_dict` |

这些测试验证的是 Python 标准库/语言本身的行为，不是项目逻辑。删除它们不会降低任何有效覆盖率。

### 7.5 过度 Mock

**`tests/test_pipeline.py` 是最严重的案例**：每个测试方法都有 6 个 `@patch` 装饰器（`Generator`、`Retriever`、`VectorIndexer`、`Embedder`、`get_llm_config`、`load_config`），20+ 个测试方法全部如此。所有测试都在验证 mock 之间的交互，而非真实的 RAG 流程。

更糟糕的是，测试断言了构造函数的精确参数：

```python
mock_embedder.assert_called_once_with(
    model_name="test-model", device="cpu", query_instruction=None
)
```

如果 `Embedder` 的构造函数签名发生任何变化，测试就会失败，即使功能完全正确。

### 7.6 应 parametrize 的复制粘贴测试

| 文件 | 类 | 测试数 | 问题 |
|------|-----|--------|------|
| `test_metrics.py` | `TestNormalizeSource` | 16 | 全部模式相同：输入路径 → 断言归一化结果 |
| `test_agent.py` | `TestToolFunctions` + `TestNewTools` | 15 | 全部是 `.name` 断言 |
| `test_agent.py` | `TestBuildSystemPrompt` | 6 | 全部是字符串包含测试 |
| `test_agent.py` | `TestCLICommands` | 8 | 全部是命令存在性测试 |
| `test_chunker.py` | `TestChunkTextChineseRoundtrip` | 7 | 全部模式相同 |
| `test_evaluators.py` | `TestRagasEvaluatorConfigReading` | 4 | 全部模式相同 |

### 7.7 缺少关键测试用例

| 模块 | 缺失测试 |
|------|----------|
| `pipeline.py` | query 错误处理（retriever 失败、generator 超时）、`build_index` 文件系统操作、并发 query 线程安全 |
| `generator.py` | LLM 调用失败/超时/重试机制、生成问题质量校验 |
| `experiment.py` | `ExperimentManager` 核心流程（创建/运行/列出实验）、`deep_merge` 边界情况 |
| `test_set_manager.py` | test set 合并冲突、失效策略、审计日志 |
| `metrics.py` | `calculate_faithfulness`、`calculate_answer_relevancy`、`calculate_hallucination_rate` |
| `agent` | 完整对话流程端到端测试、工具调用结果正确性 |

---

## 8. P6 — 其他代码异味

### 8.1 `eval/runner/core.py` — `print()` 违反项目规范

`list_experiments()` 和 `show_experiment_info()` 使用 `print()` 输出，项目规范要求使用 `loguru`。

### 8.2 `eval/runner/preparation.py` — `shutil.rmtree()` 违反 trashbin 规则

第 128 行直接删除目录，违反项目的 trashbin 规则（应移入 `.trashbin/`）。

### 8.3 `src/agent/tools.py` — 函数属性作为全局状态

```python
save_experience_tool._store = None
```

使用函数属性作为全局状态是代码异味，应改用闭包或类。

### 8.4 `eval/metrics/generation.py` — JSON 提取正则不一致

`parse_relevancy_response()` 中的 JSON 提取正则 `r"\{[^{}]*\}"` 与其他文件中的 `r"\{[\s\S]*\}"` 不一致，可能导致嵌套 JSON 解析失败。

### 8.5 `eval/runner/comparison.py` — "best variant" 选择逻辑过于简化

仅基于 `hit_rate` 选择最佳变体，且与 `template_variant.py` 中的 `_find_best_variant()` 重复。

### 8.6 `eval/pipeline_profiler.py` — 编号逻辑 bug

`suggestions` 列表中的条目已经以 `"1. "` 开头，但后面又用 `enumerate(suggestions, 1)` 重新编号并 `s[3:]` 截取前缀，逻辑脆弱。

### 8.7 `src/experiment.py` — `ExperimentManager` 中重复的 manifest 读写模式

`update_manifest_status()`、`mark_variant_completed()`、`update_manifest_field()`、`mark_resumed()`、`invalidate_variant()` 五个方法都遵循完全相同的模式：

```python
manifest_path = exp_dir / "manifest.json"
if not manifest_path.exists():
    logger.warning(...)
    return
try:
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    # ... 修改 manifest ...
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
except (json.JSONDecodeError, OSError) as e:
    logger.error(...)
```

应提取为 `_update_manifest(exp_dir, updater_fn)` 辅助方法。

### 8.8 `src/experiment.py` — `ExperimentConfig` 和 `ExperimentResult` 的 `to_dict`/`from_dict` 手写序列化

两个 dataclass 都手写了 `to_dict()` 和 `from_dict()` 方法，但 Python 的 `dataclasses.asdict()` 和 `dacite.from_dict()` 可以自动完成。手写序列化容易遗漏字段或引入 bug。

### 8.9 `src/pipeline.py` — `build_index()` 方法过长且职责混杂

`build_index()` 方法（225-466 行，约 240 行）混合了 meal 文件扫描、hash 计算、缓存路径解析、PDF 解析、分块、索引构建、BM25 索引构建等多种职责。

### 8.10 `src/pipeline.py` — `use_meal()` 中重复的配置读取

`use_meal()` 方法中 `HybridRetriever` 的配置读取（615-626 行）与 `_setup_retrievers()` 中的（189-199 行）完全重复，都是逐层 `.get()` 取值。

---

## 9. 修复优先级路线图

### Phase 1：止血（1-2 天）

| 优先级 | 任务 | 预期收益 |
|--------|------|----------|
| P0 | 删除假测试（`test_run_experiment.py:1130-1132`） | 消除误导性绿色勾 |
| P0 | 删除死代码（`error_handler.py`、`_compute_config_hash`、`pdf_viewer.py`） | 减少认知负担 |
| P0 | 修复 `asset_verifier.py` 拼写错误 `pymupdf4llllm` | 修复 bug |
| P1 | 提取 `ExperimentManager._update_manifest()` 辅助方法 | 消除 5 处重复 |
| P1 | 提取 `token_tracker` 重建逻辑为独立函数 | 消除完全相同的两段代码 |

### Phase 2：瘦身（3-5 天）

| 优先级 | 任务 | 预期收益 |
|--------|------|----------|
| P1 | 拆分 `run_experiment()` God 函数为 5-8 个子函数 | 可测试、可复用 |
| P1 | 拆分 `TestSetGenerator` 为 `QuestionGenerator` + `TestSetOrchestrator` | 消除 200+ 行重复 |
| P1 | 提取 `src/agent/tools.py` 公共模式为装饰器/基类 | 消除 20 处重复 |
| P1 | 提取 LLM 调用+JSON 解析为 `_llm_judge()` 辅助函数 | 消除 4+ 处重复 |
| P2 | 合并 `_resolve_db_path` 到共享模块 | 消除重复函数 |
| P2 | 提取 Reporter `save` 方法到基类 | 消除重复 |

### Phase 3：治本（1-2 周）

| 优先级 | 任务 | 预期收益 |
|--------|------|----------|
| P2 | 重构 `ExperimentConfigSchema`：为字段定义具体类型 | Pydantic 真正发挥作用 |
| P2 | 子模型 `extra = "forbid"` | 捕获配置拼写错误 |
| P2 | 统一 dataclass/Pydantic 使用策略 | 减少认知负担 |
| P2 | `LLMEvaluatorConfig` 改为 `dict[str, LLMEvaluatorSubConfig]` | 更灵活 |
| P2 | 为裸 `dict` 字段定义 Pydantic 模型 | 类型安全 |
| P2 | 移除 `src/issue/migrate.py` 到 scripts/ | 生产代码库瘦身 |

### Phase 4：测试质量（1-2 周）

| 优先级 | 任务 | 预期收益 |
|--------|------|----------|
| P1 | 批量 parametrize 重构（优先 `TestNormalizeSource` 16→1） | 测试行数减少 50%+ |
| P1 | 删除框架测试（TypedDict、dict.update、lru_cache） | 测试更聚焦 |
| P2 | 补充关键缺失测试（错误处理路径、并发安全） | 真正的覆盖率提升 |
| P2 | 减少 `test_pipeline.py` 的 mock 层数 | 测试更有意义 |
| P2 | 为 `test_agent.py` 的工具函数添加行为测试 | 测正确的东西 |

---

## 附录：代码行数 Top 20 文件

| 排名 | 文件 | 行数 | 问题标签 |
|------|------|------|----------|
| 1 | `src/test_generation/generator.py` | 1,563 | God 类、大量重复 |
| 2 | `src/app_pages/maintenance.py` | 1,160 | God 文件、God 函数 |
| 3 | `eval/runner/core.py` | 1,163 | God 函数、重复代码 |
| 4 | `src/agent/tools.py` | 1,033 | God 文件、模式重复 |
| 5 | `src/experiment.py` | 1,171 | 重复的 manifest 读写 |
| 6 | `src/pipeline.py` | 1,059 | 方法过长、职责混杂 |
| 7 | `eval/evaluators/ragas_evaluator.py` | 677 | 重复分支 |
| 8 | `eval/reporter/template_variant.py` | 676 | 重复推荐逻辑 |
| 9 | `src/issue/migrate.py` | 630 | 一次性代码 |
| 10 | `eval/runner/evaluation.py` | 1,034 | 重复采样逻辑 |
| 11 | `src/agent/cli.py` | 461 | God 函数 |
| 12 | `eval/runner/preparation.py` | 618 | 遗留代码 |
| 13 | `eval/reporter/template_single.py` | 440 | 重复推荐逻辑 |
| 14 | `eval/runner/comparison.py` | 447 | 重复格式化逻辑 |
| 15 | `eval/evaluators/builtin_evaluator.py` | 418 | God Method |
| 16 | `src/test_set_manager.py` | 947 | — |
| 17 | `src/experiment_reuse.py` | 927 | 过度抽象 |
| 18 | `src/config_schema.py` | 896 | Pydantic 问题 |
| 19 | `src/chunker.py` | 734 | — |
| 20 | `src/agent/graph.py` | 538 | 重复日志构造 |

---

> **总结**：这个项目有 88K 行代码，其中估计有 15-20% 是重复代码或不应存在的代码。最严重的问题是 God 文件/God 函数（6 个文件超过 1000 行）和 Pydantic 模型的滥用（全 `Any` 字段 + 全 `extra="allow"`）。测试虽然行数多，但质量堪忧——存在假测试、框架测试、过度 mock 等问题。建议按 Phase 1-4 路线图逐步修复。
