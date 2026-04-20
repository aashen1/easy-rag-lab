# Tasks

## Phase 1: 正确性修复（高优先级）

- [x] Task 1: 移除 `_evaluate_test_set_legacy()` 及其调用路径
  - [x] 1.1: 在 `evaluate_test_set()` 中移除对 `_evaluate_test_set_legacy()` 的调用分支，改为当 exp_config/system_config 为 None 时抛出 ValueError
  - [x] 1.2: 删除 `_evaluate_test_set_legacy()` 函数定义（L1046-1248）
  - [x] 1.3: 检查是否有其他代码引用该函数，确保无残留
  - [x] 1.4: 更新 test_run_experiment.py 中相关测试（如有）

- [x] Task 2: 统一指标命名空间，区分 builtin 与 ragas 同名指标
  - [x] 2.1: 在 `evaluate_test_set()` 中，当使用多后端时为结果指标添加来源前缀（如 `builtin_faithfulness`、`ragas_faithfulness`）
  - [x] 2.2: 当仅使用单后端时，指标名保持原样不加前缀
  - [x] 2.3: 更新 `compute_aggregate_metrics()` 以正确处理带前缀的指标名
  - [x] 2.4: 更新 `ExperimentReporter` 以正确展示带前缀的指标
  - [x] 2.5: 编写测试验证双后端指标命名空间行为

- [x] Task 3: 修复 RagasEvaluator 配置读取
  - [x] 3.1: 修改 `RagasEvaluator.__init__()` 从 config 中读取 `evaluation.ragas` 配置节
  - [x] 3.2: 将 `run_config`（max_workers, timeout, max_retries）传递给 `ragas.evaluate()` 调用
  - [x] 3.3: 将 `embedding_model`、`device` 等参数从硬编码改为读取配置（保留默认值 fallback）
  - [x] 3.4: 编写测试验证配置读取逻辑

- [x] Task 4: 更新 RAGAS 示例配置为新格式
  - [x] 4.1: 更新 `exp_configs/ragas_evaluation/ragas_quick.yaml` 使用新格式 test_sets
  - [x] 4.2: 更新 `exp_configs/ragas_evaluation/ragas_only.yaml` 使用新格式 test_sets
  - [x] 4.3: 更新 `exp_configs/ragas_evaluation/ragas_builtin.yaml` 使用新格式 test_sets

## Phase 2: 架构重构（中优先级）

- [x] Task 5: 提取 LLM 客户端创建为统一工厂函数
  - [x] 5.1: 在 `src/utils.py` 中创建 `create_llm_client(llm_config, mode="sdk")` 工厂函数，支持 "sdk" 和 "langchain" 两种模式
  - [x] 5.2: 重构 `eval/metrics.py` 中的 `_create_llm_client()` 使用新工厂函数
  - [x] 5.3: 重构 `eval/evaluators/ragas_evaluator.py` 中的 `_create_llm()` 使用新工厂函数
  - [x] 5.4: 重构 `eval/experiment_reporter.py` 中的 `_init_llm_client()` 使用新工厂函数
  - [x] 5.5: 编写工厂函数的单元测试

- [x] Task 6: 拆分 metrics.py 为子模块
  - [x] 6.1: 创建 `eval/metrics/` 目录结构
  - [x] 6.2: 创建 `eval/metrics/retrieval.py` — hit_rate, mrr, ndcg
  - [x] 6.3: 创建 `eval/metrics/chunk.py` — chunk_hit_rate, chunk_mrr, chunk_ndcg
  - [x] 6.4: 创建 `eval/metrics/dedup.py` — deduplicate_by_document, dedup_hit_rate, dedup_mrr, dedup_ndcg
  - [x] 6.5: 创建 `eval/metrics/fpr.py` — calculate_false_positive_rate
  - [x] 6.6: 创建 `eval/metrics/generation.py` — faithfulness, answer_relevancy
  - [x] 6.7: 创建 `eval/metrics/llm_retrieval.py` — context_precision, context_recall
  - [x] 6.8: 创建 `eval/metrics/utils.py` — normalize_source, normalize_source_with_equivalence, _create_llm_client 及辅助函数
  - [x] 6.9: 创建 `eval/metrics/__init__.py` — 统一导出所有公共函数，保持向后兼容
  - [x] 6.10: 删除原 `eval/metrics.py` 单文件
  - [x] 6.11: 全局搜索并更新所有 import 路径（如有必要，__init__.py 已处理兼容性则无需更新）
  - [x] 6.12: 运行 test_metrics.py 确保所有测试通过

- [x] Task 7: 扩展 BuiltinEvaluator 支持全部已有指标
  - [x] 7.1: 在 `supported_retrieval_metrics` 中添加 chunk_hit_rate, chunk_mrr, chunk_ndcg, dedup_hit_rate, dedup_mrr, dedup_ndcg, false_positive_rate, context_precision, context_recall
  - [x] 7.2: 在 `evaluate_single()` 中实现 chunk 级指标计算逻辑（需要 chunk_ids 信息）
  - [x] 7.3: 在 `evaluate_single()` 中实现 dedup 指标计算逻辑
  - [x] 7.4: 在 `evaluate_single()` 中实现 FPR 指标计算逻辑
  - [x] 7.5: 在 `evaluate_single()` 中实现 context_precision/context_recall 计算逻辑（需要 llm_config）
  - [x] 7.6: 更新 `evaluate_single()` 签名，接受 `equivalence_groups` 和 `llm_config` 等可选参数
  - [x] 7.7: 编写测试验证新增指标

- [x] Task 8: 废弃标记 run_eval.py
  - [x] 8.1: 在 run_eval.py 文件头部添加 DeprecationWarning
  - [x] 8.2: 在 CLI 入口（`__main__` 块）运行时输出废弃警告
  - [x] 8.3: 搜索项目中是否有脚本或文档引用 run_eval.py，更新引用

## Phase 3: 测试与文档完善（低优先级）

- [x] Task 9: 补充 RAGAS 集成测试
  - [x] 9.1: 在 test_evaluators.py 中添加 RagasEvaluator 的 mock 测试（mock LLM 和 embedding 调用）
  - [x] 9.2: 在 test_run_experiment.py 中添加双后端并行执行测试
  - [x] 9.3: 添加结果合并逻辑测试（验证 builtin + ragas 结果正确合并）
  - [x] 9.4: 添加 RAGAS 独占指标验证测试

- [x] Task 10: 更新文档
  - [x] 10.1: 更新 docs/guides/ragas-evaluation.md 中配置说明，与实际代码行为一致
  - [x] 10.2: 确认 config.yaml 中 evaluation.ragas 配置节与代码一致

# Task Dependencies

- Task 2 依赖 Task 1（移除 legacy 后才能安全修改 evaluate_test_set 的指标合并逻辑）
- Task 5 依赖 Task 6 的子模块拆分完成后再统一修改（否则 metrics.py 拆分后 import 路径变化会导致重复修改）
  - 修正：Task 5 和 Task 6 可并行，Task 5 修改的是调用方，Task 6 修改的是模块结构，但 Task 5 应在 Task 6 完成后再做最终验证
- Task 7 依赖 Task 6（BuiltinEvaluator 需要从新的子模块 import 指标函数）
- Task 9 依赖 Task 2, Task 3, Task 7（测试需要基于修复后的行为编写）
- Task 10 依赖 Task 3（文档需与代码行为一致）
