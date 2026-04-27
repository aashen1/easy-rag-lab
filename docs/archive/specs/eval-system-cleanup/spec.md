# 评测系统合并后清洗 Spec

## Why

fix-eval 和 add-ragas 两个分支合并到 dev 后，虽然架构层面的 Evaluator 抽象层设计合理，但存在遗留代码崩溃风险、同名指标跨后端语义不一致、配置与代码脱节、LLM 客户端重复创建等问题。需要系统性清洗以确保评测系统的正确性、一致性和可维护性。

## What Changes

- **移除** `_evaluate_test_set_legacy()` 函数及其调用路径，消除运行时 NameError 风险
- **统一** 同名指标在结果中的命名空间，区分 builtin 与 ragas 来源
- **修复** RagasEvaluator 使其真正读取 config.yaml 中的 `evaluation.ragas` 配置
- **更新** RAGAS 示例配置为新格式 test_sets
- **提取** LLM 客户端创建为统一工厂函数，消除三处重复
- **拆分** metrics.py 为子模块，解决 1334 行上帝模块问题
- **扩展** BuiltinEvaluator 支持全部已有指标（chunk/dedup/FPR/context_precision/context_recall）
- **废弃** run_eval.py，统一评测入口为 run_experiment.py
- **补充** RAGAS 集成测试

## Impact

- Affected specs: 评测系统全部功能
- Affected code:
  - `eval/metrics.py` → 拆分为 `eval/metrics/` 子模块
  - `eval/run_experiment.py` → 移除 legacy 路径
  - `eval/run_eval.py` → 废弃标记
  - `eval/evaluators/builtin_evaluator.py` → 扩展指标支持
  - `eval/evaluators/ragas_evaluator.py` → 配置读取修复
  - `eval/evaluators/base.py` → 可能调整接口
  - `config.yaml` → 评估配置节调整
  - `exp_configs/ragas_evaluation/*.yaml` → 格式更新
  - `docs/guides/ragas-evaluation.md` → 同步更新
  - `tests/test_evaluators.py` → 补充测试
  - `tests/test_metrics.py` → import 路径更新

## ADDED Requirements

### Requirement: 评测结果指标命名空间

评测结果中的指标 SHALL 包含来源前缀，以区分不同后端的同名指标。

#### Scenario: 双后端评测结果包含命名空间前缀
- **WHEN** 用户使用 `backends: ["builtin", "ragas"]` 运行评测
- **THEN** 结果中 builtin 的 faithfulness 标记为 `builtin_faithfulness`，ragas 的标记为 `ragas_faithfulness`
- **AND** 仅使用单后端时，指标名保持原样（如 `faithfulness`），不添加前缀

#### Scenario: 单后端评测结果保持简洁
- **WHEN** 用户仅使用 `backends: ["builtin"]` 运行评测
- **THEN** 结果中指标名为 `faithfulness`，不添加前缀

### Requirement: BuiltinEvaluator 支持全部已有指标

BuiltinEvaluator SHALL 支持所有 metrics.py 中已实现的指标，包括 chunk 级、dedup、FPR、context_precision、context_recall。

#### Scenario: BuiltinEvaluator 计算 chunk 级指标
- **WHEN** 评测样本包含 chunk_ids 信息
- **AND** 用户配置了 chunk 级指标
- **THEN** BuiltinEvaluator 返回 chunk_hit_rate、chunk_mrr、chunk_ndcg 指标

#### Scenario: BuiltinEvaluator 计算 context_precision
- **WHEN** 用户配置了 context_precision 指标
- **THEN** BuiltinEvaluator 调用 metrics.py 中的 calculate_context_precision 计算

### Requirement: RagasEvaluator 读取配置

RagasEvaluator SHALL 从 config.yaml 的 evaluation.ragas 节读取配置参数。

#### Scenario: RagasEvaluator 使用配置中的 run_config
- **WHEN** config.yaml 中配置了 `evaluation.ragas.run_config.max_workers: 5`
- **THEN** RagasEvaluator 在批量评估时使用 max_workers=5

#### Scenario: RagasEvaluator 使用配置中的 embedding 参数
- **WHEN** config.yaml 中配置了 `evaluation.ragas.embedding_model`
- **THEN** RagasEvaluator 使用指定的 embedding 模型

#### Scenario: 无配置时使用默认值
- **WHEN** config.yaml 中没有 evaluation.ragas 节
- **THEN** RagasEvaluator 使用硬编码的默认值，不报错

### Requirement: 统一 LLM 客户端工厂

项目 SHALL 提供统一的 LLM 客户端创建工厂函数，支持 Anthropic SDK 和 LangChain 两种模式。

#### Scenario: 创建 Anthropic SDK 客户端
- **WHEN** 调用工厂函数请求 SDK 模式
- **THEN** 返回配置好 LongCat 适配的 Anthropic 客户端实例

#### Scenario: 创建 LangChain 客户端
- **WHEN** 调用工厂函数请求 LangChain 模式
- **THEN** 返回配置好 LongCat 适配的 ChatAnthropic 客户端实例

### Requirement: metrics.py 拆分为子模块

metrics.py SHALL 拆分为按功能分类的子模块，同时保持向后兼容的 import 路径。

#### Scenario: 旧代码 import 仍然可用
- **WHEN** 代码中使用 `from eval.metrics import calculate_hit_rate`
- **THEN** import 正常工作，不报错

#### Scenario: 子模块独立 import
- **WHEN** 代码中使用 `from eval.metrics.retrieval import calculate_hit_rate`
- **THEN** import 正常工作

### Requirement: RAGAS 示例配置使用新格式

exp_configs/ragas_evaluation/ 下的 YAML 配置 SHALL 使用新格式 test_sets（含 name 和 on_missing 字段）。

#### Scenario: RAGAS 配置使用新格式
- **WHEN** 用户查看 ragas_only.yaml 或 ragas_builtin.yaml
- **THEN** test_sets 配置包含 name、on_missing、generation 字段

## MODIFIED Requirements

### Requirement: 评测流程入口统一

评测流程 SHALL 统一通过 run_experiment.py 的 Evaluator 架构进行，不再支持直接调用 metrics 函数的旧路径。

**变更**: 移除 `_evaluate_test_set_legacy()` 函数，`evaluate_test_set()` 不再兼容旧路径。当 exp_config 或 system_config 为 None 时抛出明确错误而非回退到 legacy。

#### Scenario: 缺少配置时给出明确错误
- **WHEN** 调用 evaluate_test_set() 时 exp_config 为 None
- **THEN** 抛出 ValueError，提示用户必须提供实验配置

### Requirement: run_eval.py 标记为废弃

run_eval.py SHALL 标记为废弃（deprecated），在文件头部和 CLI 运行时输出废弃警告。

**变更**: 不删除文件，但添加废弃警告，引导用户使用 run_experiment.py。

#### Scenario: 运行 run_eval.py 时显示废弃警告
- **WHEN** 用户运行 `pixi run python eval/run_eval.py`
- **THEN** 输出 DeprecationWarning，提示使用 run_experiment.py

## REMOVED Requirements

### Requirement: Legacy 评测路径兼容

**Reason**: `_evaluate_test_set_legacy()` 存在未定义变量导致运行时崩溃，且与 Evaluator 架构重复，维护成本高。

**Migration**: 所有需要评测的场景应通过 run_experiment.py + ExperimentConfig 进行。如有旧脚本依赖 run_eval.py，需迁移到 run_experiment.py。
