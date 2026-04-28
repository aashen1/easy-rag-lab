# Checklist

## Phase 1: Pipeline 与数据结构

- [x] pipeline.query() 返回值包含 chunk_ids 字段，且与 sources/contexts/scores 顺序一致
- [x] 文档级问题生成后，single_fact/multi_fact/reasoning/comparative 类型问题包含 source_chunks 字段
- [x] irrelevant 类型问题的 source_chunks 为空列表
- [x] missing 类型问题的 source_chunks 为空列表，且 expect_retrieval=False
- [x] source_chunks 定位支持相邻 chunk 容错（chunk_index 差值 ≤ 1）

## Phase 2: Chunk 级检索指标

- [x] calculate_chunk_hit_rate 实现正确，支持相邻容错匹配
- [x] calculate_chunk_mrr 实现正确，返回第一个命中 chunk 的 1/rank
- [x] calculate_chunk_ndcg 实现正确，精确匹配相关性=2，相邻容错匹配相关性=1
- [x] chunk 级指标的单元测试覆盖：精确匹配、相邻容错、未命中、空列表

## Phase 3: 文档去重指标

- [x] deduplicate_by_document 正确去重，每个文档只保留排名最高的 chunk
- [x] calculate_dedup_hit_rate/mrr/ndcg 基于去重结果正确计算
- [x] 去重指标的单元测试通过

## Phase 4: Irrelevant 与 Missing 评测修复

- [x] irrelevant 问题计算误检率（FPR），FPR = len(retrieved[:k]) / k
- [x] FPR 聚合指标 avg_false_positive_rate 正确计算
- [x] missing 问题不参与 Hit Rate/MRR/NDCG 计算
- [x] missing 问题单独统计检索命中率和回答正确率

## Phase 5: 文档版本等价组

- [x] meal 构建时自动推断等价组（同一公司+同一年份的不同版本）
- [x] 等价组信息存储在 meal_snapshot.json 的 equivalence_groups 字段中
- [x] 文档级匹配先精确匹配再等价组匹配
- [x] "年报全文 vs 摘要"、"中文版 vs 英文版" 等场景正确匹配

## Phase 6: 评测流程集成

- [x] run_experiment.py 同时计算 chunk 级、文档级（含去重）指标
- [x] 聚合指标包含 chunk_level_metrics、dedup_metrics、false_positive_rate
- [x] 评测结果 JSON 包含所有新指标字段
- [x] 向后兼容：测试集缺少 source_chunks 时 chunk 级指标返回 None
- [x] 实验报告同时展示 chunk 级和文档级指标
- [x] LLM 报告包含对新指标的分析
- [x] retrieval_granularity 配置项支持 chunk/document/both

## Phase 7: 测试与验证

- [x] 所有新增代码有完整的类型标注
- [x] 所有公共函数有完整的 docstring
- [x] 回归测试全部通过（706 passed，8 个 Qdrant 锁冲突为预存问题，1 个已修复）
- [ ] 使用新系统重新运行 baseline 实验成功
- [ ] chunk 级 Hit Rate 显著低于文档级 Hit Rate（预期 0.5-0.7 vs 0.93）
- [ ] 去重指标介于 chunk 级和文档级之间
- [ ] FPR 指标值合理（irrelevant 问题应有一定误检率）
- [ ] 等价组匹配修复了 q084/q086 等误判案例
