# Tasks

执行顺序按依赖关系和风险递增排列，遵循原计划建议：1 → 10 → 11 → 8 → 4 → 5 → 2 → 3 → 7 → 9

## Phase 1: 快速修复（低风险，无依赖）

- [x] Task 1: SM-01 — ExperimentResult 重命名为 ReportExperimentResult
  - [x] 1.1: 在 `eval/experiment_reporter.py` 中将 `class ExperimentResult` 重命名为 `class ReportExperimentResult`，更新 `from_dict` 返回类型注解，更新所有 `result: ExperimentResult` 参数类型
  - [x] 1.2: 更新 `tests/test_experiment_reporter.py` 中所有 `ExperimentResult` 引用为 `ReportExperimentResult`
  - [x] 1.3: 更新 `tests/test_e2e_experiment.py` 中 `ExperimentResult` 的导入和使用
  - [x] 1.4: 检查 `src/test_generator.py` facade 是否导出了 `ExperimentResult`，如有则同步更新
  - [x] 1.5: 运行 `pixi run pytest tests/test_experiment_reporter.py tests/test_e2e_experiment.py -x` 确认测试通过
  - [x] 1.6: 运行 `pixi run lint` 确认无问题
  - [x] 1.7: 提交

- [x] Task 2: SM-10 — cache.py save_manifest 返回类型修复
  - [x] 2.1: 修改 `src/meal/cache.py` 中 `save_manifest` 的返回类型注解 `-> None` → `-> bool`
  - [x] 2.2: 运行 `pixi run pytest tests/test_meal.py -x` 确认测试通过
  - [x] 2.3: 运行 `pixi run lint` 确认无问题
  - [x] 2.4: 提交

- [x] Task 3: SM-11 — manager.py 冗余 import json 删除
  - [x] 3.1: 删除 `src/meal/manager.py:1380` 的 `import json` 行
  - [x] 3.2: 运行 `pixi run pytest tests/test_meal.py -x` 确认测试通过
  - [x] 3.3: 运行 `pixi run lint` 确认无问题
  - [x] 3.4: 提交

- [x] Task 4: SM-08 — DEFAULT_EVAL_CONFIG 统一
  - [x] 4.1: 在 `eval/metrics/utils.py` 中新增 `DEFAULT_EVAL_BASE_CONFIG` 和 `get_eval_config` 函数
  - [x] 4.2: 修改 `eval/metrics/generation.py`，删除 `DEFAULT_EVAL_CONFIG` 和 `_get_eval_config`，从 `utils.py` 导入
  - [x] 4.3: 修改 `eval/metrics/llm_retrieval.py`，删除 `DEFAULT_EVAL_CONFIG` 和 `_get_eval_config`，从 `utils.py` 导入
  - [x] 4.4: 运行 `pixi run pytest tests/test_metrics.py tests/test_metric_resolver.py -x` 确认测试通过
  - [x] 4.5: 运行 `pixi run lint` 确认无问题
  - [x] 4.6: 提交

## Phase 2: 模板方法与 LSP 修复（中等风险）

- [x] Task 5: SM-04 — meal/manager.py 抽取 _build_pipeline 模板方法
  - [x] 5.1: 在 `MealManager` 中新增 `_build_pipeline` 私有方法，封装共享的"解析→分块→索引→统计→manifest→等价组→MealConfig→目录创建→manifest保存"流程
  - [x] 5.2: 重构 `create_meal`，保留采样逻辑，调用 `_build_pipeline`
  - [x] 5.3: 重构 `merge_meals`，保留合并逻辑，调用 `_build_pipeline`
  - [x] 5.4: 重构 `extend_meal`，保留扩展逻辑，调用 `_build_pipeline`
  - [x] 5.5: 重构 `repair_meal`，保留替换逻辑，调用 `_build_pipeline`
  - [x] 5.6: 运行 `pixi run pytest tests/test_meal.py -x` 确认测试通过
  - [x] 5.7: 运行 `pixi run lint` 确认无问题
  - [x] 5.8: 提交

- [x] Task 6: SM-05 — BuiltinEvaluator LSP 修复
  - [x] 6.1: 在 `eval/evaluators/base.py` 中新增 `EvaluationSample` dataclass
  - [x] 6.2: 修改基类 `evaluate_single` 签名为 `(self, sample: EvaluationSample) -> EvaluationResult`
  - [x] 6.3: 修改基类 `evaluate_batch` 签名，接收 `list[EvaluationSample]`
  - [x] 6.4: 修改 `BuiltinEvaluator.evaluate_single` 改为从 `EvaluationSample` 提取字段
  - [x] 6.5: 修改 `RagasEvaluator.evaluate_single` 和 `evaluate_batch`
  - [x] 6.6: 更新所有调用点（`eval/runner/evaluation.py`、`tests/test_evaluators.py` 等）
  - [x] 6.7: 运行 `pixi run pytest tests/test_evaluators.py -x` 确认测试通过
  - [x] 6.8: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 6.9: 运行 `pixi run lint` 确认无问题
  - [x] 6.10: 提交

## Phase 3: generator.py 拆分 + DRY（高风险，最大工作量）

- [x] Task 7: SM-02 — test_generation/generator.py 进一步拆分
  - [x] 7a: 提取常量到 `models.py`：在 `models.py` 中新增 `DOMAIN_KEYWORDS`、`PROPER_NOUN_SUFFIXES`、`PROPER_NOUN_PATTERN`，删除 `generator.py`、`chunk_locator.py`、`validators.py` 中的重复定义
  - [x] 7b: 新建 `document_loader.py`：从 `generator.py` 提取 8 个文档加载方法为独立函数
  - [x] 7c: 新建 `segment_builder.py`：从 `generator.py` 提取 9 个分段方法为独立函数
  - [x] 7d: 新建 `llm_caller.py`：从 `generator.py` 提取 8 个 LLM 调用方法为独立函数，同时提取 `parse_json_response` 通用方法
  - [x] 7e: 删除薄包装方法：将 `generator.py` 中所有薄包装委托调用改为直接使用子模块函数
  - [x] 7f: 提取 `_post_process_question` 方法：替换 4 处重复验证代码块
  - [x] 7g: 更新 `__init__.py` 和 `test_generator.py` facade 的导出列表
  - [x] 7h: 删除 `chunk_locator.py` 中 deprecated 函数（`texts_overlap`、`map_segments_to_chunks`、`locate_multi_hop_chunks` 已删除；`locate_chunks_by_quote` 和 `locate_answer_chunks` 仍有调用者暂保留）
  - [x] 7i: 新建 `supplement.py`：提取 `supplement_document_based_questions` 和 `generate_document_based_questions`，将 generator.py 降至 1472 行
  - [x] 7j: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 7k: 运行 `pixi run lint` 确认无问题
  - [x] 7l: 提交

## Phase 4: experiment_reporter.py 拆分（高风险）

- [x] Task 8: SM-03 — experiment_reporter.py 拆分为 eval/reporter/ 包
  - [x] 8a: 新建 `eval/reporter/models.py`：提取 `TestCaseResult`、`VariantResult`、`ReportExperimentResult` 三个数据类
  - [x] 8b: 新建 `eval/reporter/formatters.py`：提取 `_dict_to_yaml_lines`、`_generate_tech_summary`、`_get_generation_metric` 及指标描述/解读共享逻辑
  - [x] 8c: 新建 `eval/reporter/template_single.py`：提取单变体模板报告生成，封装为 `TemplateSingleReporter` 类
  - [x] 8d: 新建 `eval/reporter/template_variant.py`：提取多变体对比模板报告生成，封装为 `TemplateVariantReporter` 类
  - [x] 8e: 新建 `eval/reporter/llm_reporter.py`：提取 LLM 增强报告，封装为 `LLMReporter` 类
  - [x] 8f: 新建 `eval/reporter/__init__.py`：统一导出 `ReportExperimentResult` 和 `ExperimentReporter`（Facade）
  - [x] 8g: 将 `eval/experiment_reporter.py` 改为 re-export 入口（17行）
  - [x] 8h: 更新 `tests/test_experiment_reporter.py` 的 import 路径
  - [x] 8i: 运行 `pixi run pytest tests/test_experiment_reporter.py tests/test_e2e_experiment.py -x` 确认测试通过
  - [x] 8j: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 8k: 运行 `pixi run lint` 确认无问题
  - [x] 8l: 提交

## Phase 5: 清洗策略独立（中等风险）

- [x] Task 9: SM-07 — test_set_manager.py 清洗策略独立
  - [x] 9.1: 新建 `src/test_set_cleaner.py`，提取 `TestSetCleaner` 类，封装三种清洗策略
  - [x] 9.2: 修改 `TestSetManager`，删除移出的方法，委托给 `TestSetCleaner`
  - [x] 9.3: 运行 `pixi run pytest tests/test_test_set_manager.py -x` 确认测试通过
  - [x] 9.4: 运行 `pixi run lint` 确认无问题
  - [x] 9.5: 提交

## Phase 6: `_` 前缀规范化（低风险但范围广）

- [x] Task 10: SM-09 — `_` 前缀规范化
  - [x] 10a: `eval/runner/` 中 12 个跨模块使用的 `_` 前缀函数重命名，同步修改函数定义、`__init__.py` 导入和 `__all__`、所有调用点
  - [x] 10b: `eval/metrics/__init__.py` 中 8 个 `_` 前缀函数重命名并加入 `__all__`
  - [x] 10c: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 10d: 运行 `pixi run lint` 确认无问题
  - [x] 10e: 提交

## Task Dependencies

- Task 5 依赖 Task 3（SM-04 需要 SM-11 先完成，避免在冗余 import 上做重构）
- Task 7 依赖无（但建议在 Task 6 之后执行，避免 LSP 修复和 generator 拆分同时进行）
- Task 8 依赖 Task 1（SM-03 需要 SM-01 先完成，确保 `ReportExperimentResult` 名称已就绪）
- Task 10 依赖 Task 8 和 Task 6（SM-09 需要步骤 3 和 5 先完成，避免重命名冲突）
- Task 1、2、3、4 互相独立，可并行执行
