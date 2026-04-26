# 修复计划：quick_verify_metrics 实验异常

## 异常总览与根因分析

### 🔴 P0：问题类型分布严重偏离配置（根因：算法缺陷）

**现象**：配置 adversarial=7%，实际生成 4/6=67% 对抗性问题；reasoning/comparative/missing/irrelevant 四种类型零生成。

**根因**：`_calculate_question_distribution`（[test_generator.py:3344-3373](file:///b:/project/w0-easy-rag/src/test_generator.py#L3344-L3373)）存在两个缺陷：

1. **整数截断 + 末位兜底**：用 `int(num_questions * proportion)` 截断分配，所有余量给排序最后的类型（比例最小的），导致最小比例类型获得全部剩余问题。
   - 例：6 题时 `single_fact(0.30)→1, multi_fact(0.25)→1, reasoning(0.17)→0, comparative(0.17)→0, missing(0.15)→0, irrelevant(0.10)→0, adversarial(0.07)→4(兜底)`
2. **补充循环忽略比例**：[test_generator.py:1674](file:///b:/project/w0-easy-rag/src/test_generator.py#L1674) 补充生成时用 `self.TYPE_DISTRIBUTION` 均匀轮询，完全忽略自定义 `type_distribution`。

**影响**：级联导致 FPR/hallucination_rate 无法计算（无 irrelevant 问题），chunk_retrieval 覆盖不足。

**修复方案**：
- 用最大余数法（Largest Remainder Method）替代简单截断：先按 floor 分配，再将余数从大到小依次分配 1 个名额给余数最大的类型
- 补充循环改用传入的 `type_distribution` 参数，并按比例轮询而非均匀轮询

---

### 🔴 P1：LLM 增强报告虚构数据（根因：Prompt 硬编码）

**现象**：LLM 报告 §3.1 表格声称 7 种类型各 1 题，但实际只有 3 种类型。

**根因**：[experiment_reporter.py:1736-1739](file:///b:/project/w0-easy-rag/eval/experiment_reporter.py#L1736-L1739) 的 variant comparison LLM prompt 硬编码了全部 6 种问题类型（`single_fact、multi_fact、reasoning、comparative、missing、irrelevant`），指示 LLM 分析所有类型，即使数据中不存在。

**修复方案**：动态从 `by_question_type` 数据生成问题类型列表，替换硬编码列表；在 prompt 中明确要求"仅分析数据中实际存在的类型"

---

### 🟡 P2：q005 context_recall=0.0 但 hit_rate=1.0（需确认是否为 bug）

**现象**：q005（工行存款问题）hit_rate=1.0（正确文档被检索到），但 context_recall=0.0（0/1 句子可推断）。

**分析**：这两个指标衡量不同维度——hit_rate 检查文档级匹配，context_recall 检查 ground_truth 句子能否从检索上下文语义推断。可能原因：
1. 检索到正确文档但错误 chunk（不同页面/段落）
2. 对抗性问题的 ground_truth 表述与上下文差异大
3. LLM judge 解析失败或误判

**修复方案**：增加 context_recall=0.0 时的诊断日志（记录 ground_truth 句子和 LLM 判断结果），便于定位具体原因。当前不修改算法逻辑。

---

### 🟢 P3：Builtin 与 RAGAS 指标差异大（已知差异，暂不修复）

**现象**：answer_relevancy 差异最大 ~0.40（builtin 0.97 vs ragas 0.57）。

**分析**：两个后端使用完全不同的评估算法和 prompt，差异属于预期行为。comparison 策略下两者并行计算正是为了对比。这不是 bug。

---

### 🟢 P4：chunk_retrieval 为 null（预期行为）

**现象**：6 题中 2 题 chunk_retrieval=null。

**分析**：当 `expected_chunks` 未定义时（hybrid 策略生成的测试集可能不含 chunk 级 ground truth），BuiltinEvaluator 跳过 chunk 指标计算。这是设计行为，不是 bug。

---

## 修复步骤

### Step 1：修复 `_calculate_question_distribution` 算法（P0）

**文件**：`src/test_generator.py`

1. 将 `_calculate_question_distribution` 方法改为最大余数法：
   - 第一轮：每个类型分配 `floor(num_questions * proportion)` 个名额
   - 计算每个类型的余数 `remainder = num_questions * proportion - floor_count`
   - 按余数从大到小排序，依次给余数最大的类型 +1，直到分配完所有名额
   - 确保总分配数 = num_questions

2. 添加边界处理：
   - 若 type_distribution 为空或全零，回退到均匀分配
   - 若某类型分配数为 0 但 proportion > 0，在余数分配阶段优先考虑

### Step 2：修复补充循环的比例遵循（P0）

**文件**：`src/test_generator.py`

1. `generate_hybrid_questions` 的补充循环（约 L1674）：
   - 将 `all_types = list(self.TYPE_DISTRIBUTION.keys())` 改为使用传入的 `type_distribution` 参数
   - 将均匀轮询 `extra_attempt % len(all_types)` 改为按比例加权轮询

2. `generate_golden_testset` 的补充循环（约 L2040）同理修改

### Step 3：添加 `_calculate_question_distribution` 单元测试（P0）

**文件**：`tests/test_test_generator.py`（如不存在则新建）

测试用例：
- 小规模（6 题）+ 7 种类型 → 验证不再出现末位兜底问题
- 大规模（100 题）+ 均匀分布 → 验证分配接近比例
- 边界：1 题 + 多类型 → 至少 1 种类型获得 1 题
- 边界：某类型 proportion=0 → 该类型不分配
- 验证总分配数 = num_questions

### Step 4：修复 LLM 报告 Prompt 硬编码（P1）

**文件**：`eval/experiment_reporter.py`

1. 在 `_build_variant_comparison_llm_prompt` 方法中（约 L1736）：
   - 从实际数据中提取 `by_question_type` 的键列表
   - 动态生成问题类型描述，替换硬编码的 `single_fact、multi_fact、reasoning、comparative、missing、irrelevant`
   - 添加指令："仅分析数据中实际存在的问题类型，不要为不存在的类型编造数据"

2. 同步检查 `LLM_REPORT_PROMPT_TEMPLATE`（单实验报告模板），确保其也不硬编码类型列表

### Step 5：增加 context_recall 诊断日志（P2）

**文件**：`eval/metrics/llm_retrieval.py`

1. 在 `calculate_context_recall` 中，当最终 score=0.0 时，记录 WARNING 日志：
   - 输出 ground_truth 原文
   - 输出分割后的句子列表
   - 输出每个句子的 LLM 判断结果（是/否）
   - 输出检索上下文的摘要（前 200 字）

### Step 6：运行 lint + 测试验证

1. `pixi run lint`
2. `pixi run pytest tests/test_test_generator.py tests/test_experiment.py -x -q`
3. 重新运行 `pixi run exp quick_verify_metrics` 验证类型分布

### Step 7：提交代码

按逻辑单元原子提交：
- `fix: use largest remainder method for question type distribution`
- `fix: respect type_distribution proportions in supplemental generation loop`
- `test: add unit tests for _calculate_question_distribution`
- `fix: dynamically generate question type list in LLM report prompt`
- `feat: add diagnostic logging for zero context_recall`

---

## 不修复项

| 项目 | 原因 |
|------|------|
| Builtin vs RAGAS 指标差异 | 评估算法本质不同，comparison 策略下差异是预期行为 |
| chunk_retrieval 为 null | expected_chunks 未定义时的设计行为 |
