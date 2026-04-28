* [x] 测试集生成主循环在 append 前执行精确文本去重，重复问题被跳过并记录日志

* [x] 测试集生成补充循环在 append 前执行精确文本去重，重复问题被跳过并记录日志

* [x] Golden 测试集生成在 append 前执行精确文本去重

* [x] supplement\_document\_based\_questions 在 append 前执行精确文本去重

* [x] 去重逻辑有对应单元测试覆盖

* [x] 实验报告对比表 FPR 列展示样本量 `(n=X)`，n<3 时附加 `⚠`

* [x] Best Variant 区块 FPR 展示包含样本量标注和不足警告

* [x] Recommendations 区块 FPR 评估文案适配向量检索实际行为

* [x] LLM 报告模板 FPR 说明文案适配向量检索实际行为

* [x] Chunk 级指标区域在样本数 < 总问题数时展示 `Applicable Questions: X/Y`

* [x] 所有现有测试通过（test\_test\_generator.py, test\_experiment\_reporter.py）

* [x] `pixi run lint` 通过
