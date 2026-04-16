# Tasks

## Phase 1: 基础设施与关键缺失模块

- [ ] Task 1: 重构 `tests/conftest.py` — 移除全局 `sys.modules["transformers"]` mock，新增共享 fixture
  - [ ] SubTask 1.1: 删除 `sys.modules["transformers"] = MagicMock()` 及相关全局变量
  - [ ] SubTask 1.2: 新增 `mock_embedder` fixture（返回预配置的 Embedder mock 实例）
  - [ ] SubTask 1.3: 新增 `mock_qdrant_client` fixture（返回预配置的 QdrantClient mock）
  - [ ] SubTask 1.4: 新增 `mock_anthropic_client` fixture（返回预配置的 Anthropic client mock）
  - [ ] SubTask 1.5: 新增 `temp_project_dir` fixture（创建临时项目目录结构，自动清理）
  - [ ] SubTask 1.6: 更新 `pytest.ini`，新增 `unit` marker 定义

- [ ] Task 2: 创建 `tests/test_metrics.py` — 为 `eval/metrics.py` 添加完整测试
  - [ ] SubTask 2.1: `TestCalculateHitRate` — 完全命中、部分命中、无命中、空 expected、空 retrieved、重复 source
  - [ ] SubTask 2.2: `TestCalculateMRR` — 第一位命中、末位命中、无命中、空 expected、多个 expected
  - [ ] SubTask 2.3: `TestCalculateNDCG` — 完美排序、逆序排序、部分排序、k 参数截断、空 expected、单文档 ideal DCG

- [ ] Task 3: 创建 `tests/test_retriever.py` — 为 `src/retriever.py` 添加测试
  - [ ] SubTask 3.1: 成功检索（mock indexer + embedder，验证返回结构）
  - [ ] SubTask 3.2: 空 query / 非 string query 输入校验
  - [ ] SubTask 3.3: Qdrant 异常时的错误处理
  - [ ] SubTask 3.4: 检索结果 payload 提取转换逻辑

- [ ] Task 4: 创建 `tests/test_generator.py` — 为 `src/generator.py` 添加测试
  - [ ] SubTask 4.1: 成功生成回答（mock Anthropic client）
  - [ ] SubTask 4.2: 空 query / 非 string query 输入校验
  - [ ] SubTask 4.3: 空 contexts 列表（不抛异常，记录 warning）
  - [ ] SubTask 4.4: API 调用失败时的错误处理
  - [ ] SubTask 4.5: 自定义 system_prompt 传递验证
  - [ ] SubTask 4.6: token_tracker 记录验证

- [ ] Task 5: 创建 `tests/test_indexer.py` — 为 `src/indexer.py` 添加测试
  - [ ] SubTask 5.1: 创建新集合（mock QdrantClient，验证 VectorParams）
  - [ ] SubTask 5.2: 集合已存在且不重建
  - [ ] SubTask 5.3: 集合已存在且重建（recreate=True）
  - [ ] SubTask 5.4: 成功索引 chunks
  - [ ] SubTask 5.5: 空 chunks 和空 embeddings
  - [ ] SubTask 5.6: chunks 与 embeddings 长度不匹配
  - [ ] SubTask 5.7: build_index 目录不存在
  - [ ] SubTask 5.8: build_index source_filter 过滤
  - [ ] SubTask 5.9: get_collection_info / delete_collection / close

## Phase 2: 已有测试简化与重构

- [ ] Task 6: 重构 `tests/test_embedder.py` — 使用 conftest fixture 消除重复
  - [ ] SubTask 6.1: 将所有测试方法中的重复 mock 设置替换为 `mock_embedder` fixture
  - [ ] SubTask 6.2: 保留各测试中独特的 mock 行为覆盖（如 cuda fallback、init failure）
  - [ ] SubTask 6.3: 验证所有 embedder 测试通过

- [ ] Task 7: 重构 `tests/test_experiment_reporter.py` — 测试公共 API 而非私有方法
  - [ ] SubTask 7.1: 将 8 个私有 `_generate_*_section` 测试合并为 2-3 个公共 API 测试
  - [ ] SubTask 7.2: 测试 `generate_markdown_report()` 输出包含各 section 预期内容
  - [ ] SubTask 7.3: 测试 `generate_variant_comparison_report()` 输出包含对比信息
  - [ ] SubTask 7.4: 移除旧的私有方法测试

- [ ] Task 8: 精简 `tests/test_e2e_experiment.py`
  - [ ] SubTask 8.1: 识别并移除与 `test_experiment.py` 重复的测试
  - [ ] SubTask 8.2: 识别并移除与 `test_experiment_reporter.py` 重复的测试
  - [ ] SubTask 8.3: 精简 fixture，移除多数测试不需要的目录结构
  - [ ] SubTask 8.4: 移除 mock 测试上的 `@pytest.mark.integration` 标记

- [ ] Task 9: 精简 `tests/test_run_eval.py` — 移除 argparse 测试
  - [ ] SubTask 9.1: 移除 3 个测试 argparse 行为的测试方法
  - [ ] SubTask 9.2: 保留有项目逻辑价值的测试

- [ ] Task 10: 合并 `tests/test_experiment.py` 验证测试
  - [ ] SubTask 10.1: 将 `TestExperimentConfig` 的 12 个验证测试合并为 2-3 个综合测试
  - [ ] SubTask 10.2: 将 `TestExperimentResult` 的 5 个序列化测试合并为 1-2 个综合测试

## Phase 3: 扩展覆盖与回归测试

- [ ] Task 11: 创建 `tests/test_pipeline.py` — 为 `src/pipeline.py` 添加测试
  - [ ] SubTask 11.1: 初始化（无 meal / 有 meal）
  - [ ] SubTask 11.2: query 完整流程（mock retriever + generator）
  - [ ] SubTask 11.3: use_meal 切换
  - [ ] SubTask 11.4: 无效 query 输入校验

- [ ] Task 12: 创建 `tests/test_utils.py` — 为 `src/utils.py` 添加测试
  - [ ] SubTask 12.1: `TestLoadConfig` — 有效配置、文件不存在、无效 YAML
  - [ ] SubTask 12.2: `TestGetLlmConfig` — default preset、命名 preset、preset 不存在回退、环境变量解析
  - [ ] SubTask 12.3: `TestGetEnvVar` — 存在的变量、缺失变量有默认值、required 变量缺失
  - [ ] SubTask 12.4: `TestEnsureDir` — 新建目录、已存在目录、嵌套目录

- [ ] Task 13: 建立黄金测试集（Golden Test Suite）
  - [ ] SubTask 13.1: 创建 `exp_configs/golden_test.yaml` 实验配置（meal: golden_test, test_sets: factual(5)+boundary(3)+multi_hop(2)）
  - [ ] SubTask 13.2: 创建 `golden_test` Meal（ratio: 0.03, seed: 42），运行预处理链路
  - [ ] SubTask 13.3: 运行实验配置自动生成 10 个问题
  - [ ] SubTask 13.4: 对生成的问题进行 AI 质量评估，输出 `tests/fixtures/golden_qa_review.md` 评估文档
  - [ ] SubTask 13.5: 基于评估结果优化问题，生成 `tests/fixtures/golden_qa.json` 黄金数据集
  - [ ] SubTask 13.6: 创建 `tests/test_regression.py`，参数化回归测试驱动器（Mock LLM 测检索 + integration 标记测完整链路）
  - [ ] SubTask 13.7: 验证回归测试通过

## Phase 4: 验证与清理

- [ ] Task 14: 全量测试运行与修复
  - [ ] SubTask 14.1: 运行 `pixi run pytest tests/ -v` 确保所有测试通过
  - [ ] SubTask 14.2: 运行 `pixi run pytest tests/ -m "not integration"` 确保单元测试独立通过
  - [ ] SubTask 14.3: 修复任何失败的测试

# Task Dependencies

- Task 1 是所有后续 Task 的前置依赖（conftest fixture 被所有新测试使用）
- Task 6 依赖 Task 1（需要 conftest 中的 mock_embedder fixture）
- Task 8 依赖 Task 7（e2e 去重需要先确定 reporter 测试的最终形态）
- Task 13 依赖 Task 1（回归测试需要 mock fixture）和 Task 2（metrics 测试验证评估指标正确性）
- Task 13 SubTask 13.2-13.3 需要运行环境（pixi + API key），可能需要用户配合
- Task 14 依赖所有其他 Task
- Task 2, 3, 4, 5 可并行执行（均依赖 Task 1 但彼此独立）
- Task 9, 10, 11, 12 可并行执行
