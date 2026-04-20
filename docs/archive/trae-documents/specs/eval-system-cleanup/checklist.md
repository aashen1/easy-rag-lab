# Eval System Cleanup Checklist

## Phase 1: 正确性修复

- [x] `_evaluate_test_set_legacy()` 函数已被完全移除，无残留引用
- [x] `evaluate_test_set()` 在缺少 exp_config/system_config 时抛出 ValueError 而非回退到 legacy
- [x] 双后端评测结果中同名指标带有来源前缀（如 `builtin_faithfulness`、`ragas_faithfulness`）
- [x] 单后端评测结果中指标名保持原样（如 `faithfulness`），不添加前缀
- [x] `compute_aggregate_metrics()` 能正确处理带前缀的指标名
- [x] `ExperimentReporter` 能正确展示带前缀的指标
- [x] RagasEvaluator 从 config 中读取 `evaluation.ragas.run_config` 并传递给 `ragas.evaluate()`
- [x] RagasEvaluator 从 config 中读取 embedding_model 和 device 参数
- [x] RagasEvaluator 在无配置时使用默认值，不报错
- [x] `exp_configs/ragas_evaluation/ragas_quick.yaml` 使用新格式 test_sets
- [x] `exp_configs/ragas_evaluation/ragas_only.yaml` 使用新格式 test_sets
- [x] `exp_configs/ragas_evaluation/ragas_builtin.yaml` 使用新格式 test_sets

## Phase 2: 架构重构

- [x] `src/utils.py` 中存在 `create_llm_client()` 工厂函数，支持 "sdk" 和 "langchain" 模式
- [x] `eval/metrics.py`（或拆分后的子模块）使用统一工厂函数创建 LLM 客户端
- [x] `eval/evaluators/ragas_evaluator.py` 使用统一工厂函数创建 LLM 客户端
- [x] `eval/experiment_reporter.py` 使用统一工厂函数创建 LLM 客户端
- [x] 原有三处独立的 LLM 客户端创建代码已移除
- [x] `eval/metrics/` 子模块目录结构已创建，包含 retrieval.py, chunk.py, dedup.py, fpr.py, generation.py, llm_retrieval.py, utils.py
- [x] `eval/metrics/__init__.py` 统一导出所有公共函数
- [x] 旧路径 `from eval.metrics import calculate_hit_rate` 仍然可用
- [x] 新路径 `from eval.metrics.retrieval import calculate_hit_rate` 也可用
- [x] 原 `eval/metrics.py` 单文件已删除
- [x] `test_metrics.py` 全部测试通过
- [x] BuiltinEvaluator.supported_retrieval_metrics 包含 chunk/dedup/FPR/context_precision/context_recall
- [x] BuiltinEvaluator.evaluate_single() 能计算 chunk 级指标（当样本含 chunk_ids 时）
- [x] BuiltinEvaluator.evaluate_single() 能计算 dedup 指标
- [x] BuiltinEvaluator.evaluate_single() 能计算 FPR 指标
- [x] BuiltinEvaluator.evaluate_single() 能计算 context_precision/context_recall（当提供 llm_config 时）
- [x] run_eval.py 文件头部包含 DeprecationWarning
- [x] 运行 run_eval.py 时 CLI 输出废弃警告
- [x] 项目中无脚本或文档仍引用 run_eval.py 作为推荐用法

## Phase 3: 测试与文档

- [x] test_evaluators.py 中有 RagasEvaluator 的 mock 测试
- [x] test_run_experiment.py 中有双后端并行执行测试
- [x] 有结果合并逻辑的测试（builtin + ragas 结果正确合并）
- [x] 有 RAGAS 独占指标验证测试
- [x] docs/guides/ragas-evaluation.md 配置说明与代码行为一致
- [x] config.yaml 中 evaluation.ragas 配置节与代码一致

## 全局验证

- [x] `pixi run pytest tests/test_evaluators.py -v` 全部通过
- [x] `pixi run pytest tests/test_run_experiment.py -v` 全部通过
- [x] `pixi run pytest tests/test_metrics.py -v` 全部通过
- [x] 全项目无 import 错误
