# 屎山修复第二轮 Spec

## Why

第一轮重构（refactor-codebase-health）完成了大文件拆分和设计模式改进，但遗留了 12 个问题：同名类冲突、God File 残留（generator.py 3617 行、experiment_reporter.py 1779 行）、21 个薄包装方法、常量重复 6 处、LSP 违反、`_` 前缀混乱等。综合屎山指数仍为 2/10。需要第二轮修复将指数降至 1/10。

## What Changes

- **SM-01**：将 `eval/experiment_reporter.py` 中的 `ExperimentResult` 重命名为 `ReportExperimentResult`，消除与 `src/experiment.py` 的同名冲突
- **SM-02**：将 `test_generation/generator.py`（3617 行）进一步拆分为 4 个子模块 + 瘦身后的 generator.py，删除 21 个薄包装方法，统一常量定义，提取通用 JSON 解析和验证后处理方法
- **SM-03**：将 `experiment_reporter.py`（1779 行）拆分为 `eval/reporter/` 包，每子模块 ≤ 500 行
- **SM-04**：从 `meal/manager.py` 的 4 个方法中抽取 `_build_pipeline` 模板方法，消除 150-200 行重复流程
- **SM-05**：引入 `EvaluationSample` dataclass 统一评测签名，修复 `BuiltinEvaluator` 的 LSP 违反
- **SM-06**：与 SM-02 合并执行（test_generation/ 内部 DRY）
- **SM-07**：从 `test_set_manager.py` 抽取 `TestSetCleaner` 类，策略模式封装三种清洗策略
- **SM-08**：将 `DEFAULT_EVAL_CONFIG` 和 `_get_eval_config` 的公共部分提取到 `eval/metrics/utils.py`
- **SM-09**：规范化 `_` 前缀函数命名，去掉跨模块使用的 `_` 前缀，从 `__all__` 移除内部函数
- **SM-10**：修复 `cache.py` 的 `save_manifest` 返回类型注解 `-> None` → `-> bool`
- **SM-11**：删除 `manager.py:1380` 的冗余 `import json`
- **SM-12**：删除 `chunk_locator.py` 中 5 个 deprecated 函数（约 250 行）

## Impact

- Affected code: `eval/experiment_reporter.py`、`src/test_generation/generator.py`、`src/test_generation/models.py`、`src/test_generation/chunk_locator.py`、`src/meal/manager.py`、`src/meal/cache.py`、`eval/evaluators/base.py`、`eval/metrics/generation.py`、`eval/metrics/llm_retrieval.py`、`eval/runner/__init__.py`、`eval/metrics/__init__.py`、`src/test_set_manager.py`
- Affected tests: `test_experiment_reporter.py`、`test_e2e_experiment.py`、`test_test_generator.py`、`test_generator.py`、`test_meal.py`、`test_evaluators.py`、`test_test_set_manager.py`、`test_metrics.py`、`test_metric_resolver.py`
- **BREAKING**: `eval/experiment_reporter.py` 中的 `ExperimentResult` 重命名为 `ReportExperimentResult`（外部直接导入需更新）

## ADDED Requirements

### Requirement: SM-01 — ExperimentResult 同名冲突消除

系统 SHALL 将 `eval/experiment_reporter.py` 中的 `ExperimentResult` 重命名为 `ReportExperimentResult`，所有引用点同步更新。

#### Scenario: 无同名类冲突
- **WHEN** 在 `src/` 和 `eval/` 目录中搜索 `class ExperimentResult`
- **THEN** 仅 `src/experiment.py` 中存在定义

#### Scenario: 向后兼容
- **WHEN** 外部代码执行 `from eval.experiment_reporter import ReportExperimentResult`
- **THEN** 导入成功，行为与重命名前完全一致

### Requirement: SM-02 — generator.py 进一步拆分与 DRY

系统 SHALL 将 `src/test_generation/generator.py`（3617 行）拆分为以下结构：

```
src/test_generation/
  generator.py          ← 核心编排逻辑（≤ 1500 行）
  document_loader.py    ← 文档加载逻辑（~400 行）
  segment_builder.py    ← 文档分段逻辑（~450 行）
  llm_caller.py         ← LLM 调用与响应解析（~350 行）
  models.py             ← 增加 DOMAIN_KEYWORDS / PROPER_NOUN_SUFFIXES / PROPER_NOUN_PATTERN
  prompts.py            ← 不变
  chunk_locator.py      ← 删除 deprecated 函数
  validators.py         ← 不变
```

#### Scenario: 文件行数控制
- **WHEN** 查看 `generator.py` 行数
- **THEN** 不超过 1500 行

#### Scenario: 无薄包装方法
- **WHEN** 搜索 `generator.py` 中的薄包装方法（如 `self._validate_numerical_accuracy` 委托调用）
- **THEN** 无匹配结果

#### Scenario: 常量唯一定义
- **WHEN** 搜索 `domain_keywords` 或 `PROPER_NOUN_PATTERN` 的定义
- **THEN** 仅在 `models.py` 中出现一次

#### Scenario: 通用 JSON 解析
- **WHEN** 查看 `llm_caller.py` 中的 JSON 解析逻辑
- **THEN** 存在 `parse_json_response` 通用方法，替代三个 `_parse_*_response` 的重复逻辑

#### Scenario: 验证后处理提取
- **WHEN** 查看 `generator.py` 中的验证代码块
- **THEN** 存在 `_post_process_question` 方法，替代 4 处重复的验证代码块

### Requirement: SM-03 — experiment_reporter.py 拆分

系统 SHALL 将 `eval/experiment_reporter.py`（1779 行）拆分为 `eval/reporter/` 包：

```
eval/reporter/
  __init__.py            ← 统一导出
  models.py              ← TestCaseResult, VariantResult, ReportExperimentResult
  template_single.py     ← 单变体模板报告生成
  template_variant.py    ← 多变体对比模板报告生成
  llm_reporter.py        ← LLM 增强报告 + 客户端管理
  formatters.py          ← _dict_to_yaml_lines, _generate_tech_summary, metric 辅助
```

#### Scenario: 子模块行数控制
- **WHEN** 查看 `eval/reporter/` 下各子模块行数
- **THEN** 每个子模块不超过 500 行

#### Scenario: 原文件缩减
- **WHEN** 查看 `eval/experiment_reporter.py`
- **THEN** 缩减为 re-export 入口（≤ 30 行）或已删除

### Requirement: SM-04 — meal/manager.py 模板方法提取

系统 SHALL 从 `MealManager` 的 `create_meal`、`merge_meals`、`extend_meal`、`repair_meal` 四个方法中抽取 `_build_pipeline` 私有方法，封装共享的"解析→分块→索引→统计→manifest→等价组→MealConfig→目录创建→manifest保存"流程。

#### Scenario: 重复代码消除
- **WHEN** 查看 `manager.py` 中四个方法的实现
- **THEN** 不再有重复的"解析→分块→索引→manifest"流程代码

#### Scenario: 行数减少
- **WHEN** 查看 `manager.py` 行数
- **THEN** 较重构前减少 150+ 行

### Requirement: SM-05 — BuiltinEvaluator LSP 修复

系统 SHALL 在 `eval/evaluators/base.py` 中引入 `EvaluationSample` dataclass，统一 `evaluate_single` 和 `evaluate_batch` 的签名。

#### Scenario: 签名一致性
- **WHEN** 查看 `BuiltinEvaluator.evaluate_single` 的签名
- **THEN** 与基类签名一致（只接收 `EvaluationSample` 参数）

#### Scenario: RagasEvaluator 签名一致
- **WHEN** 查看 `RagasEvaluator.evaluate_batch` 的签名
- **THEN** 与基类签名一致

### Requirement: SM-07 — test_set_manager.py 清洗策略独立

系统 SHALL 从 `TestSetManager` 中抽取 `TestSetCleaner` 类，使用策略模式封装三种清洗策略（immutable、trim、regenerate）。

#### Scenario: 行数控制
- **WHEN** 查看 `test_set_manager.py` 行数
- **THEN** 不超过 900 行

#### Scenario: 清洗器独立
- **WHEN** 查看 `test_set_cleaner.py` 行数
- **THEN** 不超过 500 行

### Requirement: SM-08 — DEFAULT_EVAL_CONFIG 统一

系统 SHALL 将 `eval/metrics/generation.py` 和 `eval/metrics/llm_retrieval.py` 中重复的 `DEFAULT_EVAL_CONFIG` 和 `_get_eval_config` 的公共部分提取到 `eval/metrics/utils.py`。

#### Scenario: 配置唯一定义
- **WHEN** 搜索 `model_name` 和 `base_url` 的默认值定义
- **THEN** 仅在 `eval/metrics/utils.py` 中出现一次

#### Scenario: 辅助函数统一
- **WHEN** 搜索 `_get_eval_config` 函数定义
- **THEN** 仅在 `eval/metrics/utils.py` 中存在 `get_eval_config`

### Requirement: SM-09 — `_` 前缀规范化

系统 SHALL 对被跨模块使用的 `_` 前缀函数去掉下划线，对仅内部使用的函数从 `__all__` 中移除。

#### Scenario: __all__ 无下划线前缀
- **WHEN** 查看 `eval/runner/__init__.py` 的 `__all__`
- **THEN** 无 `_` 前缀函数

#### Scenario: 跨模块函数无下划线前缀
- **WHEN** 查看被 `eval/runner/evaluation.py` 或 `core.py` 直接导入使用的函数名
- **THEN** 无 `_` 前缀

### Requirement: SM-10 — cache.py 返回值修复

系统 SHALL 将 `src/meal/cache.py` 的 `save_manifest` 方法返回类型注解从 `-> None` 改为 `-> bool`，与实际行为和 docstring 一致。

#### Scenario: 类型注解一致性
- **WHEN** 查看 `save_manifest` 的签名、docstring、实际代码
- **THEN** 三者均声明返回 `bool`

### Requirement: SM-11 — manager.py 冗余 import json 删除

系统 SHALL 删除 `src/meal/manager.py` 中方法内部的冗余 `import json`（L1380），保留文件顶部的 `import json`。

#### Scenario: 无方法内 import json
- **WHEN** 搜索 `manager.py` 中的 `import json`
- **THEN** 仅在文件顶部出现一次

### Requirement: SM-12 — chunk_locator.py deprecated 函数删除

系统 SHALL 删除 `src/test_generation/chunk_locator.py` 中 5 个已标记 deprecated 的函数：`texts_overlap`、`map_segments_to_chunks`、`locate_chunks_by_quote`、`locate_multi_hop_chunks`、`locate_answer_chunks`。

#### Scenario: 无 deprecated 函数
- **WHEN** 搜索 `chunk_locator.py` 中的 `deprecated` 标记
- **THEN** 无匹配结果

#### Scenario: 无调用点
- **WHEN** 全局搜索被删除的 5 个函数名
- **THEN** 除 `chunk_locator.py` 本身外无其他调用点

## MODIFIED Requirements

无。所有修改保持行为不变。

## REMOVED Requirements

无。
