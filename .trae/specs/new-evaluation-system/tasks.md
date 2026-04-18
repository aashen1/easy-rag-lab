# Tasks

## Phase 1: 文档级问题生成

- [x] Task 1: 设计文档级问题生成策略
  - [x] SubTask 1.1: 分析现有问题生成代码结构和问题类型
  - [x] SubTask 1.2: 设计真实用户场景的问题类型（单知识点、多知识点、缺失知识点、无关问题、推理型、对比分析）
  - [x] SubTask 1.3: 设计文档级问题生成的提示词模板，确保问题真实、多样化
  - [x] SubTask 1.4: 设计问题难度和真实性评估机制

- [x] Task 2: 实现文档级问题生成功能
  - [x] SubTask 2.1: 在 test_generator.py 中添加 `document` 策略支持
  - [x] SubTask 2.2: 实现完整 MD 文档加载逻辑
  - [x] SubTask 2.3: 实现文档级问题生成的 LLM 调用
  - [x] SubTask 2.4: 添加问题生成结果验证逻辑

- [x] Task 3: 为旧策略添加 deprecation 警告
  - [x] SubTask 3.1: 在 test_generator.py 中为 factual、boundary、multi_hop 策略添加 deprecation 警告
  - [x] SubTask 3.2: 更新相关文档说明

## Phase 2: 检索指标改进

- [x] Task 4: 改进 NDCG 指标实现
  - [x] SubTask 4.1: 研究标准 NDCG 多级相关性计算方法
  - [x] SubTask 4.2: 设计相关性评分机制（而非简单二元相关性）
  - [x] SubTask 4.3: 更新 calculate_ndcg 函数实现
  - [x] SubTask 4.4: 添加 NDCG 改进的单元测试

- [x] Task 5: 改进 Hit Rate 指标实现
  - [x] SubTask 5.1: 研究业界标准 Hit Rate 定义
  - [x] SubTask 5.2: 分析当前实现的问题和改进方向
  - [x] SubTask 5.3: 更新 calculate_hit_rate 函数实现
  - [x] SubTask 5.4: 添加 Hit Rate 改进的单元测试

- [x] Task 6: 改进 MRR 指标实现
  - [x] SubTask 6.1: 审查当前 MRR 实现的准确性
  - [x] SubTask 6.2: 优化 MRR 计算逻辑，确保严格性
  - [x] SubTask 6.3: 更新 calculate_mrr 函数实现（如需要）
  - [x] SubTask 6.4: 添加 MRR 改进的单元测试（如需要）

## Phase 3: 生成质量指标

- [x] Task 7: 实现 Faithfulness 指标
  - [x] SubTask 7.1: 研究 Faithfulness 指标计算方法
  - [x] SubTask 7.2: 设计 Faithfulness 评估的提示词
  - [x] SubTask 7.3: 在 metrics.py 中实现 calculate_faithfulness 函数
  - [x] SubTask 7.4: 添加 Faithfulness 指标的单元测试

- [x] Task 8: 实现 Answer Relevancy 指标
  - [x] SubTask 8.1: 研究 Answer Relevancy 指标计算方法
  - [x] SubTask 8.2: 设计 Answer Relevancy 评估的提示词
  - [x] SubTask 8.3: 在 metrics.py 中实现 calculate_answer_relevancy 函数
  - [x] SubTask 8.4: 添加 Answer Relevancy 指标的单元测试

- [x] Task 9: 集成生成质量指标到评测流程
  - [x] SubTask 9.1: 更新 run_eval.py 支持生成质量指标
  - [x] SubTask 9.2: 更新实验报告格式，包含生成质量指标
  - [x] SubTask 9.3: 添加生成质量指标的集成测试

## Phase 4: 实验系统更新

- [x] Task 10: 更新实验配置格式
  - [x] SubTask 10.1: 更新 experiment.py 支持新的 metrics 配置格式
  - [x] SubTask 10.2: 更新配置验证逻辑
  - [x] SubTask 10.3: 更新实验配置示例文件

- [x] Task 11: 更新实验报告生成
  - [x] SubTask 11.1: 更新 experiment_reporter.py 支持生成质量指标
  - [x] SubTask 11.2: 更新报告模板，展示生成质量指标
  - [x] SubTask 11.3: 更新 LLM 报告生成逻辑

## Phase 5: 测试与文档

- [x] Task 12: 完善测试覆盖
  - [x] SubTask 12.1: 为文档级问题生成添加单元测试
  - [x] SubTask 12.2: 为检索指标改进添加单元测试
  - [x] SubTask 12.3: 为生成质量指标添加单元测试
  - [x] SubTask 12.4: 添加端到端集成测试
  - [x] SubTask 12.5: 运行回归测试，确保向后兼容

- [x] Task 13: 更新文档
  - [x] SubTask 13.1: 更新 docs/guides/experiment-system.md
  - [x] SubTask 13.2: 创建 docs/guides/evaluation-metrics.md
  - [x] SubTask 13.3: 更新 docs/config-reference.md
  - [x] SubTask 13.4: 更新 CLAUDE.md 中的相关说明

## Phase 6: 验证与优化

- [x] Task 14: 运行验证实验
  - [x] SubTask 14.1: 使用新系统运行基线实验
  - [x] SubTask 14.2: 对比新旧系统的评测结果
  - [x] SubTask 14.3: 验证 chunk-size 对比实验的可行性
  - [x] SubTask 14.4: 验证问题生成的真实性和多样性

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] can run in parallel with [Task 2]
- [Task 4], [Task 5], and [Task 6] can run in parallel
- [Task 7] and [Task 8] can run in parallel
- [Task 9] depends on [Task 7] and [Task 8]
- [Task 10] can run in parallel with [Task 9]
- [Task 11] depends on [Task 9] and [Task 10]
- [Task 12] depends on [Task 2], [Task 6], [Task 9], and [Task 11]
- [Task 13] can run in parallel with [Task 12]
- [Task 14] depends on [Task 12] and [Task 13]
