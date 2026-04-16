# Test Suite Redesign Checklist

## Phase 1: 基础设施与关键缺失模块

- [x] `conftest.py` 不再包含 `sys.modules["transformers"]` 全局 mock
- [x] `conftest.py` 提供 `mock_embedder` fixture，返回预配置的 Embedder mock
- [x] `conftest.py` 提供 `mock_qdrant_client` fixture，返回预配置的 QdrantClient mock
- [x] `conftest.py` 提供 `mock_anthropic_client` fixture，返回预配置的 Anthropic client mock
- [x] `conftest.py` 提供 `temp_project_dir` fixture，自动创建和清理临时目录
- [x] `pytest.ini` 包含 `unit` marker 定义
- [x] `test_metrics.py` 覆盖 `calculate_hit_rate` 的 6 个场景
- [x] `test_metrics.py` 覆盖 `calculate_mrr` 的 5 个场景
- [x] `test_metrics.py` 覆盖 `calculate_ndcg` 的 6 个场景
- [x] `test_retriever.py` 覆盖成功检索、输入校验、错误处理、结果转换
- [x] `test_generator.py` 覆盖成功生成、输入校验、空 contexts、API 错误、自定义 prompt、token tracking
- [x] `test_indexer.py` 覆盖集合创建（新建/已存在/重建）、索引（成功/空/不匹配）、build_index（目录不存在/source_filter）、辅助方法

## Phase 2: 已有测试简化与重构

- [x] `test_embedder.py` 中无重复的 mock 设置代码（每个测试方法 <5 行 mock 配置）
- [x] `test_experiment_reporter.py` 不包含私有方法测试，仅测试 `generate_markdown_report()` 和 `generate_variant_comparison_report()` 公共 API
- [x] `test_e2e_experiment.py` 不包含与 `test_experiment.py` 或 `test_experiment_reporter.py` 重复的测试
- [x] `test_e2e_experiment.py` 中 mock 测试不标记 `@pytest.mark.integration`
- [x] `test_run_eval.py` 不包含 argparse 标准库测试
- [x] `test_experiment.py` 中 `TestExperimentConfig` 验证测试 ≤3 个

## Phase 3: 扩展覆盖与回归测试

- [x] `test_pipeline.py` 覆盖初始化（有/无 meal）、query 流程、use_meal 切换、输入校验
- [x] `test_utils.py` 覆盖 load_config、get_llm_config、get_env_var、ensure_dir
- [x] `exp_configs/golden_test.yaml` 存在且配置正确（3 个 test_sets: factual(5)+boundary(3)+multi_hop(2)）
- [ ] `golden_test` Meal 已创建（ratio: 0.03, seed: 42, 约 3-4 个 PDF）— 需用户配合运行环境
- [ ] 自动生成的 10 个问题已通过 AI 质量评估 — 需用户配合运行环境
- [ ] `tests/fixtures/golden_qa_review.md` 评估文档存在 — 需用户配合运行环境
- [x] `tests/fixtures/golden_qa.json` 存在且格式正确（每条记录含 id、category、question、expected_sources、expected_keywords、description）
- [x] `test_regression.py` 使用 `@pytest.mark.parametrize` 对 golden_qa.json 参数化
- [x] 回归测试 Mock LLM 模式验证 expected_sources 命中率
- [x] 回归测试 integration 模式验证 expected_keywords 覆盖率（占位实现，需运行环境才能实际验证）

## Phase 4: 全量验证

- [x] `pixi run pytest tests/ -v` 全部通过（356 passed, 2 skipped）
- [x] `pixi run pytest tests/ -m "not integration"` 全部通过（356 passed, 2 deselected）
- [x] 源模块测试覆盖率达到 17/17（所有 src/ 和 eval/ 模块均有对应测试文件）
- [x] 核心 RAG 模块测试覆盖率达到 6/6 (100%)（metrics、retriever、generator、indexer、pipeline、embedder）
- [x] 测试总行数合理（新增测试精简，已有测试适当精简）
