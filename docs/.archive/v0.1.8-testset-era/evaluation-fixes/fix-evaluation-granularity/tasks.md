# Tasks

## Phase 1: Pipeline 与数据结构准备

- [x] Task 1: Pipeline.query() 返回 chunk_ids
  - [x] SubTask 1.1: 修改 pipeline.py 的 query() 方法，从检索结果中提取 chunk_ids 列表，加入返回值
  - [x] SubTask 1.2: 确保 chunk_ids 与 sources、contexts、scores 的顺序一致
  - [x] SubTask 1.3: 添加单元测试验证返回值结构

- [x] Task 2: 文档级问题生成新增 source_chunks 定位
  - [x] SubTask 2.1: 在 test_generator.py 中实现 `_locate_answer_chunks()` 方法
  - [x] SubTask 2.2: 修改 `generate_document_based_questions()`，填充 `source_chunks` 字段
  - [x] SubTask 2.3: 对 irrelevant 类型问题设置 `source_chunks = []`
  - [x] SubTask 2.4: 对 missing 类型问题设置 `source_chunks = []`，并将 `expect_retrieval` 改为 `False`
  - [x] SubTask 2.5: 添加相邻 chunk 容错
  - [x] SubTask 2.6: 添加单元测试验证 source_chunks 定位的准确性

## Phase 2: Chunk 级检索指标

- [x] Task 3: 实现 chunk 级匹配的检索指标函数
  - [x] SubTask 3.1: 实现 `calculate_chunk_hit_rate`
  - [x] SubTask 3.2: 实现 `calculate_chunk_mrr`
  - [x] SubTask 3.3: 实现 `calculate_chunk_ndcg`
  - [x] SubTask 3.4: 添加完整的单元测试

## Phase 3: 文档去重指标

- [x] Task 4: 实现文档去重后的检索指标
  - [x] SubTask 4.1: 实现 `deduplicate_by_document`
  - [x] SubTask 4.2: 实现 `calculate_dedup_hit_rate/mrr/ndcg`
  - [x] SubTask 4.3: 添加单元测试

## Phase 4: Irrelevant 与 Missing 问题评测修复

- [x] Task 5: 实现 irrelevant 问题的误检率指标
  - [x] SubTask 5.1: 实现 `calculate_false_positive_rate`
  - [x] SubTask 5.2: 修改 run_experiment.py，对 irrelevant 类型问题计算 FPR
  - [x] SubTask 5.3: 在聚合指标中新增 `avg_false_positive_rate`
  - [x] SubTask 5.4: 添加单元测试

- [x] Task 6: 修复 missing 类型问题的评测逻辑
  - [x] SubTask 6.1: 修改 test_generator.py，将 missing 类型的 `expect_retrieval` 改为 `False`
  - [x] SubTask 6.2: 修改 run_experiment.py，对 missing 问题单独统计
  - [x] SubTask 6.3: 添加单元测试

## Phase 5: 文档版本等价组

- [x] Task 7: 实现文档版本等价组机制
  - [x] SubTask 7.1: 实现 `_infer_equivalence_groups`
  - [x] SubTask 7.2: 等价组信息存储在 meal_snapshot.json
  - [x] SubTask 7.3: 修改 metrics.py 支持等价组匹配
  - [x] SubTask 7.4: 修改 run_experiment.py 的文档级匹配逻辑
  - [x] SubTask 7.5: 添加单元测试

## Phase 6: 评测流程集成

- [x] Task 8: 更新评测流程使用新指标
  - [x] SubTask 8.1: 修改 `_evaluate_variant()` 方法
  - [x] SubTask 8.2: 修改 `compute_aggregate_metrics()`
  - [x] SubTask 8.3: 修改评测结果 JSON 格式
  - [x] SubTask 8.4: 向后兼容

- [x] Task 9: 更新实验报告生成
  - [x] SubTask 9.1: 修改 experiment_reporter.py
  - [x] SubTask 9.2: 更新 LLM 报告生成逻辑
  - [x] SubTask 9.3: 更新报告模板中的指标对比表

- [x] Task 10: 更新实验配置支持
  - [x] SubTask 10.1: 新增 `retrieval_granularity` 配置项
  - [x] SubTask 10.2: 在 VALID_METRICS 中注册新指标名
  - [x] SubTask 10.3: 更新配置验证逻辑

## Phase 7: 测试与验证

- [x] Task 11: 完善测试覆盖
  - [x] SubTask 11.1: 为 chunk 级指标添加边界条件测试
  - [x] SubTask 11.2: 为去重指标添加测试
  - [x] SubTask 11.3: 为等价组匹配添加测试
  - [x] SubTask 11.4: 为 FPR 指标添加测试
  - [x] SubTask 11.5: 运行回归测试

- [ ] Task 12: 运行验证实验
  - [ ] SubTask 12.1: 使用新评测系统重新运行 baseline 实验
  - [ ] SubTask 12.2: 对比新旧系统的评测结果
  - [ ] SubTask 12.3: 验证去重指标、FPR 指标的合理性
  - [ ] SubTask 12.4: 验证等价组匹配是否修复了误判案例

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] can run in parallel with [Task 1] and [Task 2]
- [Task 4] depends on [Task 1]
- [Task 5] and [Task 6] can run in parallel with each other and with [Task 3]
- [Task 7] can run in parallel with [Task 3], [Task 5], [Task 6]
- [Task 8] depends on [Task 1], [Task 2], [Task 3], [Task 4], [Task 5], [Task 6], [Task 7]
- [Task 9] depends on [Task 8]
- [Task 10] depends on [Task 8]
- [Task 11] depends on [Task 8]
- [Task 12] depends on [Task 11]
