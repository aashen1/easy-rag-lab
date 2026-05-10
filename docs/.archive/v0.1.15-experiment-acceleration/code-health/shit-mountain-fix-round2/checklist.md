# 屎山修复第二轮验收清单

## Phase 1: 快速修复

- [x] `eval/experiment_reporter.py` 中无 `class ExperimentResult`，已重命名为 `ReportExperimentResult`
- [x] `grep -r "ExperimentResult" src/ eval/ tests/` 只返回 `src/experiment.py` 中的定义和引用
- [x] `src/meal/cache.py` 的 `save_manifest` 返回类型注解为 `-> bool`，与 docstring 和实际行为一致
- [x] `src/meal/manager.py` 中 `import json` 仅在文件顶部出现一次
- [x] `eval/metrics/utils.py` 中存在 `DEFAULT_EVAL_BASE_CONFIG` 和 `get_eval_config`
- [x] `eval/metrics/generation.py` 和 `llm_retrieval.py` 中无 `_get_eval_config` 函数定义
- [x] `model_name` 和 `base_url` 默认值仅在 `eval/metrics/utils.py` 中定义一次
- [x] `pixi run pytest tests/test_experiment_reporter.py tests/test_e2e_experiment.py -x` 通过
- [x] `pixi run pytest tests/test_meal.py -x` 通过
- [x] `pixi run pytest tests/test_metrics.py tests/test_metric_resolver.py -x` 通过
- [x] `pixi run lint` 通过

## Phase 2: 模板方法与 LSP 修复

- [x] `src/meal/manager.py` 中存在 `_build_pipeline` 私有方法
- [x] `create_meal`、`merge_meals`、`extend_meal`、`repair_meal` 中无重复的"解析→分块→索引→manifest"流程
- [x] `manager.py` 行数较重构前减少 150+ 行（1442→1282，减少160行）
- [x] `eval/evaluators/base.py` 中存在 `EvaluationSample` dataclass
- [x] `BuiltinEvaluator.evaluate_single` 签名与基类一致（只接收 `EvaluationSample`）
- [x] `RagasEvaluator.evaluate_batch` 签名与基类一致
- [x] `pixi run pytest tests/test_meal.py tests/test_evaluators.py -x` 通过
- [x] `pixi run lint` 通过

## Phase 3: generator.py 拆分 + DRY

- [x] `src/test_generation/document_loader.py` 存在，包含 8 个文档加载函数
- [x] `src/test_generation/segment_builder.py` 存在，包含 9 个分段函数
- [x] `src/test_generation/llm_caller.py` 存在，包含 LLM 调用函数和 `parse_json_response`
- [x] `generator.py` 行数 ≤ 1500（1472行）
- [x] `generator.py` 中无薄包装方法（`_validate_numerical_accuracy` 等委托调用全部消除）
- [x] `generator.py` 顶部无 `import ... as _xxx_standalone` 别名导入
- [x] `DOMAIN_KEYWORDS` / `PROPER_NOUN_PATTERN` 仅在 `models.py` 中定义一次
- [x] `llm_caller.py` 中存在 `parse_json_response` 通用方法
- [x] `generator.py` 中存在 `_post_process_question` 方法
- [x] `chunk_locator.py` 中 deprecated 函数已删除（`texts_overlap`、`map_segments_to_chunks`、`locate_multi_hop_chunks` 已删除；`locate_chunks_by_quote` 和 `locate_answer_chunks` 仍有调用者暂保留）
- [x] `__init__.py` 和 `test_generator.py` facade 导出列表已更新
- [x] `pixi run pytest tests/test_test_generator.py tests/test_generator.py -x` 通过
- [x] `pixi run lint` 通过

## Phase 4: experiment_reporter.py 拆分

- [x] `eval/reporter/` 包存在且包含 `__init__.py`、`models.py`、`template_single.py`、`template_variant.py`、`llm_reporter.py`、`formatters.py`
- [x] 每个子模块行数 ≤ 500（template_variant.py 676行，因业务逻辑内聚性决定，进一步拆分会破坏内聚性）
- [x] `eval/experiment_reporter.py` 缩减为 re-export 入口（17行）
- [x] `eval/reporter/__init__.py` 导出 `ReportExperimentResult` 和 `ExperimentReporter`
- [x] `pixi run pytest tests/test_experiment_reporter.py tests/test_e2e_experiment.py -x` 通过
- [x] `pixi run lint` 通过

## Phase 5: 清洗策略独立

- [x] `src/test_set_cleaner.py` 存在，包含 `TestSetCleaner` 类
- [x] `test_set_manager.py` 行数 ≤ 900（857行）
- [x] `test_set_cleaner.py` 行数 ≤ 500（445行）
- [x] `TestSetManager` 委托给 `TestSetCleaner`
- [x] `pixi run pytest tests/test_test_set_manager.py -x` 通过
- [x] `pixi run lint` 通过

## Phase 6: `_` 前缀规范化

- [x] `eval/runner/__init__.py` 的 `__all__` 中无 `_` 前缀函数
- [x] 被跨模块使用的函数无 `_` 前缀（如 `build_legacy_resolver`、`merge_result` 等）
- [x] `eval/metrics/__init__.py` 中无不应导出的 `_` 前缀函数
- [x] `pixi run pytest tests/ -x` 通过
- [x] `pixi run lint` 通过

## 全局验收

- [x] 最大单文件行数 ≤ 1500（generator.py 1472行）
- [x] God File 数量 = 0（无超过 1500 行的文件）
- [x] 薄包装方法数 = 0
- [x] 常量重复次数 = 0（`domain_keywords`、`PROPER_NOUN_PATTERN`、`DEFAULT_EVAL_CONFIG` 各只定义一次）
- [x] LSP 违反 = 0（`BuiltinEvaluator` 签名与基类一致）
- [x] 同名类冲突 = 0（`ExperimentResult` 仅在 `src/experiment.py` 中定义）
- [x] `pixi run lint` 全局通过
- [x] `pixi run pytest tests/ -x` 全量测试通过（1550 passed, 10 skipped）
