# Tasks

- [x] Task 1: 按类型动态调整 max_tokens
  - [x] 1.1: 在 `_generate_question_with_evidence` 方法中，根据 question_type 选择 max_tokens（comparative/reasoning/multi_fact 用 2048，其他用 self.test_gen_max_tokens）
  - [x] 1.2: 将 max_tokens 传入 `generator.generate()` 调用
  - [x] 1.3: 编写测试验证不同类型使用不同 max_tokens

- [x] Task 2: 专有名词去后缀模糊匹配
  - [x] 2.1: 在 `_validate_answer_evidence_consistency` 中，专有名词精确匹配失败后，去除后缀（行业/市场/公司/集团/股份/技术/产品/业务）再匹配
  - [x] 2.2: 编写测试覆盖"电子行业"→"电子"匹配、"量子计算行业"→不匹配等场景

- [x] Task 3: 对抗性题一致性检查豁免
  - [x] 3.1: 在 `generate_golden_testset` 的答案-证据一致性校验处，对 adversarial 类型仅检查诱饵数字（答案中引用的文档原始数据），跳过推理产生的数值和推断性专有名词
  - [x] 3.2: 编写测试验证 adversarial 题的推理计算不报 issue

- [x] Task 4: MIN_QUOTE_LENGTH 中文自适应
  - [x] 4.1: 在 `_validate_evidence` 中，计算引用文本的中文字符占比，占比 > 50% 时阈值降为 15，否则保持 30
  - [x] 4.2: 编写测试覆盖中文引用（>=15 通过）和英文引用（>=30 通过）场景

- [x] Task 5: missing 类型独立 prompt
  - [x] 5.1: 创建 `MISSING_INDEPENDENT_PROMPT` 常量，核心指令为"先列出文档已覆盖主题，再选未覆盖维度提问"
  - [x] 5.2: 在 `_generate_hybrid_question` 中，missing 类型使用独立 prompt 而非 EVIDENCE_AWARE_PROMPT + supplement
  - [x] 5.3: 编写测试验证 missing 类型使用独立 prompt

- [x] Task 6: 答案长度约束
  - [x] 6.1: 定义 `ANSWER_LENGTH_LIMITS` 类常量，按类型设置字数上限
  - [x] 6.2: 在 `_generate_question_with_evidence` 的 prompt 中追加答案字数约束指令
  - [x] 6.3: 在 `generate_golden_testset` 的后验证链中，检查答案长度，超长则在最后一个句号处截断并标记 `answer_truncated=True`
  - [x] 6.4: 编写测试验证截断逻辑

- [x] Task 7: 未覆盖数值自动回补 evidence
  - [x] 7.1: 新增 `_supplement_evidence_for_uncovered_numbers` 方法，接收答案、evidence_list、doc_content，在文档中搜索未覆盖数值的上下文，追加为 evidence
  - [x] 7.2: 在 `generate_golden_testset` 的答案-证据一致性校验后，对有 issues 的问题调用回补方法
  - [x] 7.3: 回补的 evidence 标记 `match_type="auto_supplemented"` 和 `segment_index=-1`
  - [x] 7.4: 编写测试验证回补逻辑

- [x] Task 8: 端到端验证
  - [x] 8.1: 运行 `pixi run python scripts/generate_golden_testset.py --num-questions 20 --name golden_20_verify --seed 42` 生成新测试集
  - [x] 8.2: 对比新旧测试集的质量指标（format_correct_rate / quote_verification_rate / ground_truth_confidence / answer_evidence_issues 数量）
  - [x] 8.3: 运行 `pixi run lint` 确保代码质量
  - [x] 8.4: 运行 `pixi run python -m pytest tests/test_golden_testset.py -v` 确保所有测试通过

# Task Dependencies

- Task 7 依赖 Task 2（专有名词匹配改进后，数值回补逻辑才能准确判断哪些 issues 是数值相关的）
- Task 8 依赖 Task 1-7 全部完成
- Task 1/2/3/4/5/6 相互独立，可并行执行
