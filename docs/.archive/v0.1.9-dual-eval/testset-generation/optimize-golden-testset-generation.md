# Golden Test Set 生成逻辑优化计划

## 问题总览

基于 `golden_test_q20.json` 的数据质量审查，发现 6 个问题，归纳为 4 个根因，对应 4 组修复。

---

## 根因分析与修复方案

### 根因 1：补充生成不追踪类型缺口，导致缺失知识点严重不足

**现象**：缺失知识点目标 3 题，实际仅 1 题（偏差 -2）

**根因**：
- 主循环按 `_calculate_question_distribution` 分配类型，但 LLM 生成失败时仅 `failed_count += 1`，不记录哪个类型缺了多少
- 补充循环使用原始分布权重的随机采样（`type_distribution` 权重），不感知各类型的实际缺口
- `missing` 类型本身生成难度高（LLM 倾向于从文档中找到答案而非承认信息缺失），主循环失败率高
- 补充循环以 13% 权重随机选 `missing`，概率低，且 `max_extra_attempts = deficit * 3` 限制总尝试次数

**修复**：在 `generate_golden_testset` 中引入类型缺口追踪

1. 主循环结束后，计算每个类型的实际生成数 vs 目标数，得到 `type_deficits: dict[str, int]`
2. 补充循环优先从 `type_deficits` 中选取缺口最大的类型，而非随机采样
3. 当所有类型缺口填满后再用随机采样补足剩余

**修改文件**：`src/test_generator.py` — `generate_golden_testset()` 方法（约 2049-2168 行的补充循环部分）

---

### 根因 2：evidence quote 验证逻辑过于严格且不回退，导致验证率低

**现象**：`quote_verification_rate = 0.7`，4 题完全无验证通过的 evidence

**根因**（多因素叠加）：

1. **LLM 改写 quote**：尽管 prompt 要求"必须与选段原文完全一致"，LLM 仍会改写/压缩/合并引用，导致 fuzzy match（阈值 0.85）也失败
2. **碎片化引用**：LLM 产出极短的标题式引用（如"即时型消费成为增量引擎"、"传统增长模式难以为继"），这些不是原文完整句子，无法通过验证
3. **segment_index 越界**：LLM 有时返回不在 `selected_segments` 中的 segment_index（如 golden_010 返回 segment_index=8，但 selected_segments=[4,6]），直接判定为 Invalid
4. **验证只对 selected_segments 做**：当 quote 实际来自文档其他段落时，即使内容正确也无法验证

**修复**（4 个子改动）：

2a. **添加 quote 最小长度校验**：在 `_validate_evidence` 中，过滤掉长度 < 20 字符的 quote，标记为 `verified: False, reason: "Quote too short (< 20 chars)"`

2b. **segment_index 越界时回退到全文档搜索**：当 segment_index 不在 segment_map 中时，不直接判 Invalid，而是尝试在**全文档内容**中搜索该 quote（复用 `_verify_quote_in_document` 的 fuzzy 逻辑），如果找到则标记为 `verified: True, match_type: "document_fuzzy"`

2c. **部分验证通过时仍接受题目**：当前逻辑在 `validation["valid"] == False` 时会 retry（最多 max_retries 次），最后一次仍失败则返回 None 丢弃整个题目。改为：最后一次尝试时，只要有至少 1 条 evidence 验证通过，就接受该题目（将未验证的 evidence 保留但标记清晰）

2d. **强化 prompt 中的逐字引用要求**：在 `EVIDENCE_AWARE_PROMPT` 中增加反面示例和更明确的约束

**修改文件**：
- `src/test_generator.py` — `_validate_evidence()`, `_generate_hybrid_question()`, prompt 常量
- 需要在 `_generate_hybrid_question` 中传入 `doc_content` 参数以支持全文档回退搜索

---

### 根因 3：缺少答案一致性校验，导致数值正负矛盾

**现象**：golden_006 答案同时说"778.37倍"和"为负值"，自相矛盾

**根因**：
- `_validate_numerical_accuracy` 只检测 10 倍换算错误，不检测正负号矛盾
- 原文"均为负值，其中酒鬼酒 778.37 倍"本身就省略了负号，LLM 照搬后产生矛盾

**修复**：新增 `_validate_answer_consistency` 方法

1. 检测 answer 中同时出现正数和"负值/为负/负数"描述的矛盾
2. 检测 answer 中数值与 ground_truth_excerpt 中对应数值的正负号不一致
3. 发现矛盾时记录 warning 并在 metadata 中标记 `answer_consistency_warning`

**修改文件**：`src/test_generator.py` — 新增方法 + 在 `generate_golden_testset` 主循环和补充循环中调用

---

### 根因 4：对抗性问题的 prompt 未要求反驳必须针对问题中的具体主张

**现象**：golden_013 问"腾讯QClaw公测是否意味着国内大模型商业化赶上海外？"，但反驳用"资本开支投入节奏比海外慢1-1.5年"，与 QClaw 产品能力无关

**根因**：`EVIDENCE_ADVERSARIAL_SUPPLEMENT` 只要求"答案必须指出文档中的正确信息，并说明问题中的诱饵"，但未要求反驳必须**直接针对问题中的具体主张**

**修复**：增强 `EVIDENCE_ADVERSARIAL_SUPPLEMENT` prompt

1. 添加要求："反驳必须直接针对问题中的核心主张，不能用泛泛的行业数据代替对具体主张的回应"
2. 添加反面示例："问：X产品是否意味着Y已实现？→ 不好的反驳：行业整体落后（太泛）；好的反驳：X产品在Z维度上仍落后于竞品A（直接针对）"

**修改文件**：`src/test_generator.py` — `EVIDENCE_ADVERSARIAL_SUPPLEMENT` 常量

---

## 实施步骤

### Step 1：类型缺口追踪（根因 1）
- 修改 `generate_golden_testset()` 补充循环
- 主循环结束后计算 `type_deficits`
- 补充循环优先填补缺口最大的类型
- 编写测试

### Step 2：evidence 验证增强（根因 2）
- 2a: `_validate_evidence` 添加 quote 最小长度校验
- 2b: segment_index 越界时回退全文档搜索（需传入 doc_content）
- 2c: `_generate_hybrid_question` 最后一次尝试时接受部分验证通过
- 2d: 强化 prompt 逐字引用要求
- 编写测试

### Step 3：答案一致性校验（根因 3）
- 新增 `_validate_answer_consistency` 方法
- 在主循环和补充循环中调用
- 编写测试

### Step 4：对抗性 prompt 增强（根因 4）
- 修改 `EVIDENCE_ADVERSARIAL_SUPPLEMENT`
- 编写测试

### Step 5：集成验证
- 运行 `pixi run lint` 确保代码质量
- 运行 `pixi run test` 确保所有测试通过
- 重新生成 golden_test_q20.json 验证改进效果

---

## 不修改的项

- **行业偏重（光伏 4/20）**：这是文档语料库本身的特征，非算法问题，暂不处理
- **GOLDEN_TYPE_DISTRIBUTION 比例**：当前分布设计合理，不调整
- **_calculate_question_distribution 算法**：最大余额法本身正确，问题出在补充循环不追踪缺口
