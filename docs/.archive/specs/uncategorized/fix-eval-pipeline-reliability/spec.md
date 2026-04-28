# 实验评测链路可靠性修复 Spec

## Why

实验 `exp_20260427_003843_baseline_1kpage` 的结果暴露了多条评测链路 bug：测试集生成存在重复问题、FPR 指标在样本量不足时产生误导性结论、chunk 级指标样本数未在报告中体现、报告对 FPR 的评估阈值与实际行为脱节。这些问题导致实验报告的可靠性下降，可能误导后续优化方向。

## What Changes

- 在测试集生成流程（主循环 + 补充循环）中增加问题文本去重检查
- FPR 报告展示增加样本量标注，并在样本量不足时添加警告
- 报告中 chunk 级指标增加 `retrieval_applicable_questions` 展示
- FPR 评估阈值和说明文案适配向量检索系统的实际行为特征
- 为测试集生成去重逻辑添加单元测试

## Impact

- Affected specs: 测试集生成、评测指标计算、实验报告展示
- Affected code:
  - `src/test_generator.py` — 增加去重逻辑
  - `eval/metrics/fpr.py` — 无变更（计算逻辑正确）
  - `eval/run_experiment.py` — 无变更（已记录 `irrelevant_questions_count` 和 `retrieval_applicable_questions`）
  - `eval/experiment_reporter.py` — 报告展示增强
  - `tests/test_test_generator.py` — 新增去重测试

## ADDED Requirements

### Requirement: 测试集生成去重

测试集生成流程 SHALL 在将新问题加入列表前检查该问题文本是否与已有问题重复（精确匹配），重复问题 SHALL 被跳过并记录日志。

#### Scenario: 主循环生成重复问题
- **WHEN** `generate_hybrid_questions` 主循环中 LLM 返回的问题文本与已有问题完全相同
- **THEN** 该问题被跳过，不加入 questions 列表，loguru 记录 DEBUG 级别日志

#### Scenario: 补充循环生成重复问题
- **WHEN** 补充循环中 LLM 返回的问题文本与已有问题完全相同
- **THEN** 该问题被跳过，不加入 questions 列表，loguru 记录 DEBUG 级别日志

#### Scenario: Golden 测试集生成重复问题
- **WHEN** `generate_golden_testset` 中 LLM 返回的问题文本与已有问题完全相同
- **THEN** 该问题被跳过，不加入 questions 列表，loguru 记录 DEBUG 级别日志

### Requirement: FPR 报告样本量标注

实验报告 SHALL 在展示 FPR 数值时同时标注样本量（irrelevant 问题数量），当样本量 < 3 时 SHALL 添加"样本量不足，统计意义有限"的警告。

#### Scenario: FPR 样本量充足
- **WHEN** FPR 基于 3 个及以上 irrelevant 问题计算
- **THEN** 报告展示 `False Positive Rate: 0.8000 (n=5)`

#### Scenario: FPR 样本量不足
- **WHEN** FPR 基于 1-2 个 irrelevant 问题计算
- **THEN** 报告展示 `False Positive Rate: 1.0000 (n=1, ⚠ 样本量不足，统计意义有限)`

#### Scenario: 无 irrelevant 问题
- **WHEN** 测试集中没有 irrelevant 问题
- **THEN** 报告展示 `False Positive Rate: N/A (no irrelevant questions)`

### Requirement: Chunk 级指标样本数展示

实验报告 SHALL 在展示 chunk 级检索指标时标注实际有效样本数（`retrieval_applicable_questions`），避免读者误以为指标基于全部问题计算。

#### Scenario: Chunk 指标样本数与总问题数不同
- **WHEN** chunk 级指标的 `retrieval_applicable_questions` < `total_questions`
- **THEN** 报告在 chunk 级指标区域展示 `Applicable Questions: 17/20`

#### Scenario: Chunk 指标样本数与总问题数相同
- **WHEN** chunk 级指标的 `retrieval_applicable_questions` == `total_questions`
- **THEN** 报告不额外标注（避免信息冗余）

### Requirement: FPR 评估阈值与说明适配

FPR 的评估阈值和说明文案 SHALL 适配向量检索系统的实际行为特征：标准向量检索系统对任何查询都会返回 top-k 结果，因此 FPR 接近 1.0 是预期行为而非异常。

#### Scenario: FPR 评估文案调整
- **WHEN** 报告生成 FPR 评估文案
- **THEN** 使用适配向量检索的评估标准：
  - FPR > 0.3 且 n >= 3: "High retrieval occupancy for irrelevant questions — standard vector retrieval typically returns top-k results regardless of relevance; consider adding a rejection mechanism if needed."
  - FPR > 0.3 且 n < 3: "High retrieval occupancy (⚠ insufficient sample) — FPR near 1.0 is expected for vector retrieval; sample too small for reliable assessment."
  - FPR <= 0.3: "Low retrieval occupancy — system effectively filters irrelevant queries."

## MODIFIED Requirements

### Requirement: 实验报告对比表 FPR 列

对比表中的 FPR 列 SHALL 在数值后附加样本量标注 `(n=X)`，当 n < 3 时附加 `⚠` 标记。

原行为：`1.0000`
新行为：`1.0000 (n=1⚠)` 或 `0.8000 (n=5)`

### Requirement: 实验报告 Best Variant 区块 FPR 展示

Best Variant 区块的 FPR 展示 SHALL 包含样本量标注和不足警告。

原行为：`- False Positive Rate: 1.0000`
新行为：`- False Positive Rate: 1.0000 (n=1, ⚠ 样本量不足，统计意义有限)`

## REMOVED Requirements

无移除的需求。
