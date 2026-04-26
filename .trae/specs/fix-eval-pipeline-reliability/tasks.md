# Tasks

- [x] Task 1: 测试集生成去重 — 在 `src/test_generator.py` 的三个生成方法中添加问题文本精确去重检查
  - [x] SubTask 1.1: 在 `generate_hybrid_questions` 主循环中添加去重检查（append 前检查 `question_text in seen_questions`）
  - [x] SubTask 1.2: 在 `generate_hybrid_questions` 补充循环中添加去重检查
  - [x] SubTask 1.3: 在 `generate_golden_testset` 主循环和补充循环中添加去重检查
  - [x] SubTask 1.4: 在 `supplement_document_based_questions` 中添加去重检查
  - [x] SubTask 1.5: 为去重逻辑添加单元测试（`tests/test_test_generator.py`）

- [x] Task 2: FPR 报告样本量标注 — 在 `eval/experiment_reporter.py` 中增强 FPR 展示
  - [x] SubTask 2.1: 修改对比表 FPR 列，附加 `(n=X)` 标注，n<3 时附加 `⚠`
  - [x] SubTask 2.2: 修改 Best Variant 区块 FPR 展示，附加样本量和不足警告
  - [x] SubTask 2.3: 修改 Recommendations 区块 FPR 评估文案，适配向量检索实际行为
  - [x] SubTask 2.4: 修改 LLM 报告模板中 FPR 说明文案

- [x] Task 3: Chunk 级指标样本数展示 — 在 `eval/experiment_reporter.py` 中增加 chunk 级指标的有效样本数展示
  - [x] SubTask 3.1: 在 Best Variant 区块的 chunk-level 指标区域展示 `Applicable Questions: X/Y`（仅当 X<Y 时）
  - [x] SubTask 3.2: 在 Variant Details 区块同样展示 chunk 级指标样本数

- [x] Task 4: 测试验证 — 运行现有测试确保无回归
  - [x] SubTask 4.1: 运行 `pixi run pytest tests/test_test_generator.py -v` 确认去重测试通过
  - [x] SubTask 4.2: 运行 `pixi run pytest tests/test_experiment_reporter.py -v` 确认报告测试通过
  - [x] SubTask 4.3: 运行 `pixi run lint` 确认代码质量

# Task Dependencies

- Task 2 和 Task 3 可并行执行（均修改 experiment_reporter.py 但不同区块）
- Task 4 依赖 Task 1-3 全部完成
- SubTask 1.5 依赖 SubTask 1.1-1.4
