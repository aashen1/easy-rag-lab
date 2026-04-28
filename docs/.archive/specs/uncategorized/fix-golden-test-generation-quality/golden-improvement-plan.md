好，我先深入看一下代码里的关键逻辑，搞清楚哪些是能动手改的，再给你一条一条说清楚。



现在我已经获取了所有关键代码段。下面是详细分析。

---

## 详细逻辑分析：`src/test_generator.py` 关键代码

### 一、答案-证据一致性验证 `_validate_answer_evidence_consistency`

**位置**: [test_generator.py:2928-3051](file:///b:/project/w0-easy-rag/src/test_generator.py#L2928-L3051)

**核心目的**: 检测 LLM 生成的答案中是否存在"幻觉"——即答案中的关键信息（数值、专有名词）在证据引用中找不到支撑。

**逻辑流程**:

1. **前置检查**: 如果 answer 为空或 evidence_text 为空，直接返回 `(True, [])`，视为一致。

2. **数值提取与比对** (第2965-3041行):
   - 通过 `extract_numbers_with_units()` 从答案和证据中提取带单位的数值，支持的模式包括：`亿元`、`万元`、`元`、`%`、`％`、`个百分点`、`个`、以及无单位的纯数字。
   - 返回格式为 `(数值, 单位, 原始文本)` 的元组列表。

3. **单位换算与匹配** (第2992-3041行):
   - `convert_to_base_unit()` 将所有数值统一换算到基础单位（元/个），支持 `亿 -> 1e8`、`万 -> 1e4` 的换算。
   - 对答案中的每个数值（>=10 才检查，过滤小数字），在证据数值中寻找匹配，匹配规则按优先级排列：
     - **精确换算匹配**: 基础单位换算后相对误差 < 1%（`abs(ans_base - ev_base) / max(ev_base, 1) < 0.01`）
     - **亿-元换算**: 答案单位为"亿"，证据单位为"元"，且 `abs(ans_val - ev_val / 1e8) < 0.01`
     - **万-元换算**: 答案单位为"万"，证据单位为"元"，且 `abs(ans_val - ev_val / 1e4) < 0.01`
     - **近似匹配**: 相对误差 < 5%（`abs(ans_val - ev_val) / max(ev_val, 1) < 0.05`）
   - 如果四种匹配都不满足，记录问题：`"数值 'xxx' 未在证据中找到"`

4. **专有名词比对** (第3043-3049行):
   - 用正则 `[\u4e00-\u9fff]{2,8}(?:股份|集团|公司|行业|市场|技术|产品|业务)` 从答案中提取专有名词。
   - 检查每个专有名词是否出现在证据文本中，不在则记录：`"专有名词 'xxx' 未在证据中找到"`

5. **返回值**: `(len(issues) == 0, issues)` — 如果所有数值和专有名词都有证据支撑则一致。

**关键设计思想**: 这是一种"反向验证"策略——不是验证证据是否正确，而是验证答案中的关键声明是否被证据覆盖。数值验证支持单位换算是为了处理金融文档中常见的"元/万元/亿元"混用场景。

---

### 二、证据验证逻辑 `_validate_evidence`

**位置**: [test_generator.py:4915-5097](file:///b:/project/w0-easy-rag/src/test_generator.py#L4915-L5097)

**核心目的**: 验证 LLM 返回的每条 evidence 引用是否真实存在于文档片段中，防止 LLM 编造引用。

**逻辑流程**:

1. **前置检查**: 空证据列表直接返回 `valid=True`。

2. **构建 segment_map**: 以 `segment_index` 为键建立片段索引映射。

3. **逐条验证 evidence**，对每条执行以下检查：

   **a) segment_index 缺失** (第2965-2973行):
   - 如果 `segment_index` 为 None，标记为 `verified=False`，记录原因 `"Missing segment_index"`。

   **b) 引用过短检查** (第2975-2988行):
   - 去除空白后，引用长度 < `MIN_QUOTE_LENGTH`(30字符)，标记为 `verified=False`，记录原因 `"Quote too short"`。
   - 设计意图：过短的引用往往是标题或短语，不具备证据价值。

   **c) segment_index 无效** (第2990-3015行):
   - 如果 `segment_index` 不在 segment_map 中：
     - 尝试在全文档 `doc_content` 中用 `_verify_excerpt_in_document()` 做模糊匹配。
     - 如果在文档中找到，标记为 `verified=True, match_type="document_fuzzy"`。
     - 否则标记为 `verified=False`，记录原因 `"Invalid segment_index"`。

   **d) 在指定片段中验证** (第3017-3089行):
   - 先用 `_verify_quote_in_segment()` 在指定片段中查找引用。
   - 如果找到，标记为 `verified=True`，附带 `match_type`（"exact" 或 "fuzzy"）和 `position`。
   - 如果未找到，进入**多级回退**：
     - **同页片段回退**: 查找与当前片段共享页码的其他片段，在其中搜索引用。
     - **全文档回退**: 如果同页片段也没找到，且提供了 `doc_content`，用 `_verify_excerpt_in_document()` 在全文档中搜索。
     - 如果都未找到，标记为 `verified=False`，记录原因 `"Quote not found in segment"`，并输出警告 `"Potential hallucination detected"`。

4. **返回值**: `{"valid": all_valid, "verified_evidence": [...], "invalid_quotes": [...]}`

**关键设计**: 三级回退机制（指定片段 -> 同页片段 -> 全文档），兼顾严格性和容错性。`match_type` 字段记录匹配方式，便于后续质量分析。

---

### 三、不同问题类型的差异化生成逻辑

**位置**: [test_generator.py:2573-2771](file:///b:/project/w0-easy-rag/src/test_generator.py#L2573-L2771) (`_generate_hybrid_question`) + 各 Supplement 常量

#### 3.1 片段选择策略差异

```python
multi_hop_types = {"multi_fact", "reasoning", "comparative"}
compact_types = {"single_fact", "missing", "adversarial"}
```

- **多跳类型** (`multi_fact`/`reasoning`/`comparative`): 使用 `_select_candidate_segments()` 选择更多候选片段（`multi_hop_candidate_count` 个），因为需要跨片段综合信息。
- **单跳类型** (`single_fact`/`missing`/`adversarial`): 使用 `_select_segments_for_question_type()` 选择少量片段，并对选中片段做 `_compact_segments()` 压缩（上限 `compact_segment_max_chars=6000` 字符），减少 token 消耗。
- **无关类型** (`irrelevant`): 完全不走片段选择，直接调用 `_generate_irrelevant_question()`。

#### 3.2 Prompt 差异

所有非 irrelevant 类型共用 `EVIDENCE_AWARE_PROMPT` 基础模板，但通过 `EVIDENCE_QUESTION_TYPE_SUPPLEMENTS` 追加类型专属指令：

| 类型            | Supplement 关键差异                                          |
| --------------- | ------------------------------------------------------------ |
| **single_fact** | 只需1条证据，引用直接包含答案数据/事实                       |
| **multi_fact**  | 必须2条以上证据，来自不同片段，必须填 `selected_segments`，答案需综合多片段 |
| **reasoning**   | 证据需支撑推理过程，relevance 字段说明推理链条，答案必须展示推理步骤 |
| **comparative** | 为对比的每个对象提供对应引用，客观呈现对比，信息不足需如实说明 |
| **missing**     | evidence 可为空或部分相关，答案需明确"文档未提及"，不可编造  |
| **irrelevant**  | 单独使用 `IRRELEVANT_QUESTION_PROMPT`，evidence 必须为空数组 |
| **adversarial** | 四种对抗策略（数字近似/时序/否定/部分匹配），必须包含"诱饵"信息，反驳必须针对核心主张 |

#### 3.3 生成后验证差异

在 `_generate_hybrid_question` 中：

- **irrelevant**: 不走证据验证流程，且要求 evidence 必须为空，有 evidence 则重试。
- **missing**:
  - 如果 LLM 返回了 evidence，则重试（因为 missing 类型本就不应有证据）。
  - 如果 LLM 没返回 evidence，直接设置 `ground_truth_excerpt=""` 并返回，跳过证据验证。
- **其他类型**: 必须通过 `_validate_evidence()` 验证，验证失败则重试（最多 `max_retries` 次）。

#### 3.4 source_chunks 定位差异

- **多跳类型**: 收集所有选中片段的页码 + 所有验证通过的引用，对每个引用调用 `_locate_source_chunks()`，合并所有 chunk_id。
- **单跳类型**: 只用第一条验证通过的 evidence 的引用 + 第一个片段的页码来定位 source_chunks。

#### 3.5 Golden 测试集的元数据差异

在 `generate_golden_testset` 中，不同类型设置不同的元数据：

```python
if q_type == "irrelevant":
    qa["source_files"] = []
    qa["source_chunks"] = []
    qa["expect_retrieval"] = False
elif q_type == "missing":
    qa["source_files"] = [source_path]
    qa["source_chunks"] = []
    qa["expect_no_answer"] = True
    qa["expect_retrieval"] = False
else:
    qa["source_files"] = [source_path]
```

- **irrelevant**: 无源文件，不应触发检索。
- **missing**: 有源文件但无 chunks，不应有答案，不应触发检索。
- **其他**: 正常关联源文件。

---

### 四、LLM 响应的 JSON 解析 `_parse_evidence_question_response`

**位置**: [test_generator.py:3238-3277](file:///b:/project/w0-easy-rag/src/test_generator.py#L3238-L3277)

**逻辑流程**:

1. **去除 Markdown 代码块包裹**: 如果响应以 ` ``` ` 开头，移除所有 ` ``` ` 行。
2. **提取 JSON**: 用 `response.find("{")` 和 `response.rfind("}")` 定位最外层花括号，提取中间的子串。这能处理 LLM 在 JSON 前后添加说明文字的情况。
3. **JSON 解析**: `json.loads(json_str)`。
4. **必填字段检查**: 验证 `question`、`answer`、`question_type` 三个字段存在且非空，缺失则返回 None。
5. **默认值填充**:
   - `difficulty` 默认 `"medium"`
   - `evidence` 默认 `[]`
   - `selected_segments` 默认 `[]`
6. **异常处理**: 捕获 `json.JSONDecodeError` 和 `KeyError`，返回 None。

**关键设计**: 容错性很强——能处理代码块包裹、前后多余文字、缺少可选字段等情况，但严格要求三个核心字段必须存在。

---

### 五、补充生成逻辑 (Supplement Generation)

**位置**: [test_generator.py:2267-2455](file:///b:/project/w0-easy-rag/src/test_generator.py#L2267-L2455)

**触发条件**: 主循环结束后，如果生成的问题数 < 目标数 `num_questions`，进入补充生成阶段。

**逻辑流程**:

1. **计算类型缺口** (第2274-2289行):
   - 统计已生成问题中各类型的实际数量（通过 `_chinese_to_type_key()` 将中文类型名映射回英文键）。
   - 对每个类型计算 `target - actual`，得到 `type_deficits` 字典。

2. **构建加权随机选择器** (第2291-2303行):
   - 基于 `type_distribution` 的权重构建累积分布函数 `weighted_types`。
   - 当 `type_deficits` 为空时，按权重随机选择类型。

3. **补充循环** (第2307-2455行):
   - 最大尝试次数 = `deficit * 3`（3倍冗余）。
   - **文档轮转**: `doc_name = doc_names[extra_attempt % len(doc_names)]`，轮询文档。
   - **类型选择策略**:
     - 优先填补缺口最大的类型（`type_deficits` 中值最大的键）。
     - 如果有多个类型缺口相同，轮询选择。
     - 如果所有缺口已填满（`type_deficits` 为空），按权重随机选择。
   - **生成与验证**: 与主循环完全相同的流程——调用 `_generate_hybrid_question()`，然后执行数值精度验证、答案一致性验证、摘录验证、答案-证据一致性验证。
   - **缺口更新**: 成功生成后，对应类型的 `type_deficits` 减1，减到0则从字典中删除。

4. **去重**: 使用 `seen_questions` 集合，跳过重复问题。

**关键设计**: 补充阶段不是简单随机，而是优先填补数量不足的类型，确保最终分布尽量接近目标。3倍冗余的尝试上限防止无限循环。

---

### 六、辅助验证方法

#### `_verify_quote_in_segment` (第4800-4833行)

两级匹配：先精确匹配 (`str.find()`)，失败后模糊匹配 (`_fuzzy_match_quote`)。返回 `match_type` 为 `"exact"` 或 `"fuzzy"`。

#### `_fuzzy_match_quote` (第4835-4911行)

使用 `difflib.SequenceMatcher` 计算相似度：
- 粗扫描：步长为 `quote_len // 10`，在 segment_text 上滑动窗口。
- 精细扫描：当粗扫描发现相似度 >= threshold 的位置时，在其附近 ±step 范围内逐字符扫描，寻找最佳匹配位置。
- 默认阈值 `0.85`。

#### `_verify_excerpt_in_document` (第3053-3086行)

模糊匹配摘录是否存在于全文档：
- 先去空白后精确匹配。
- 失败后用滑动窗口（步长 `min_overlap // 2`，窗口大小 `min_overlap=15`）检查是否有至少15个连续字符匹配。

---

### 总结：整体质量保障流水线

`generate_golden_testset` 对每个生成的问题执行以下验证链：

```
_generate_hybrid_question()
  ├── 片段选择（多跳/单跳/无关）
  ├── Prompt 组装（基础模板 + 类型专属补充）
  ├── LLM 调用 + JSON 解析
  ├── 证据验证 _validate_evidence()（三级回退）
  └── source_chunks 定位

后验证链：
  1. _validate_numerical_accuracy() → 数值精度自动修正
  2. _validate_answer_consistency() → 答案内部一致性检查
  3. _verify_excerpt_in_document() → 摘录可追溯性验证
  4. _validate_answer_evidence_consistency() → 答案-证据一致性（反幻觉）
  5. 去重检查
  6. 元数据标注（author/reviewed/target_failure_mode）
```

补充生成阶段复用完全相同的验证链，并额外通过 `type_deficits` 机制优先填补数量不足的类型，确保最终测试集的类型分布符合 `GOLDEN_TYPE_DISTRIBUTION` 的设计目标（其中 adversarial 占比最高 20%，因为边界场景是 RAG 系统最容易出错的领域）。


好，我仔细看了代码和生成结果，给你直说，一条一条来。

---

## 现在能修的、值得修的，一共 7 条

### ① JSON 截断导致整题报废 —— **修 max_tokens 策略**

**现象**：golden_013（中国医疗健康行业，12K+ tokens 文档）连续 3 次 JSON 解析失败，最终这道 comparative 题彻底没生成，靠 missing 类型替补。

**根因**：LLM 的 `max_tokens` 是 1024，但 comparative/reasoning 类型需要输出多段 evidence + 长答案，1024 不够用，输出被截断，JSON 不闭合，解析失败。

**修法**：在 `_generate_hybrid_question` 里，根据问题类型动态调整 max_tokens：
- `comparative` / `reasoning` / `multi_fact`：用 2048
- 其他类型：保持 1024

**预期效果**：长文档的 comparative/reasoning 题不再因截断报废，一次生成成功率从约 85% 提升到 95%+。

---

### ② 答案里塞了证据没覆盖的数字 —— **修 evidence 覆盖逻辑**

**现象**：golden_004 答案里有 4,996.81亿/3,384.79亿/6,764.47亿，但 evidence 里没有这些数字。golden_005 答案里有 19.4%/38.6%/76%/202/841，evidence 里也没有。

**根因**：LLM 从**整篇文档**里读到了这些数字写进答案，但 evidence 只引用了部分片段。答案的信息量 > 证据的信息量，这是幻觉的温床。

**修法**：在答案-证据一致性校验之后，如果发现答案中有未覆盖的数值，**不是只打 warning，而是自动回溯文档补齐 evidence**——找到包含这些数值的片段，追加为 evidence quote。

**预期效果**：答案中的关键数值 100% 有 evidence 支撑，answer_evidence_issues 大幅减少，答案置信度从 86% 提升到 95%+。

---

### ③ 专有名词匹配太死板 —— **修匹配算法**

**现象**：golden_012 答案写"电子行业以10.9%涨幅领涨"，但 evidence 原文是"电子（+10.9%）"，检查器报"专有名词'电子行业'未在证据中找到"。这是**误报**——"电子行业"和"电子"明明是同一个东西。

**根因**：`_validate_answer_evidence_consistency` 用的是**精确子串匹配**——`if noun not in evidence_text`。这种匹配对改写措辞零容忍。

**修法**：把专有名词匹配从精确子串改为**模糊匹配**：
- 先精确匹配，命中就过
- 未命中时，用 `difflib.SequenceMatcher` 算相似度，阈值 0.8 以上算通过
- 或者更简单：对专有名词做**去后缀匹配**（去掉"行业/市场/公司"等后缀后再匹配）

**预期效果**：专有名词误报率从约 60% 降到 10% 以下，warning 的信噪比大幅提升，真正的问题不再被淹没。

---

### ④ 对抗性题不该受答案-证据一致性检查 —— **修校验策略**

**现象**：golden_019 答案计算了"15.5百分点差值"，这个数字不在原文里，被报了 6 个 issues。但对抗性题的答案**本来就需要推理和计算**——"你说的数字是反的，实际差了 15.5 个百分点"这种反驳本身就是答案的核心价值。

**根因**：所有类型共用同一套 `_validate_answer_evidence_consistency`，没有区分对抗性题的特殊性。

**修法**：对 `adversarial` 类型，**跳过答案-证据一致性检查**，或者只检查"诱饵数字是否在证据中"（正向验证），不检查"反驳推理是否在证据中"。

**预期效果**：对抗性题不再被误报，4 道对抗性题的 answer_evidence_issues 从平均 4 条降到 0-1 条。

---

### ⑤ missing 类型生成太费劲 —— **修 prompt 策略**

**现象**：2 道 missing 题都经历了多次重试——LLM 先生成了有 evidence 的问题（如"2026年新房开工和竣工计划的同比降幅分别是多少？"），系统检测到有 evidence 后要求重试，浪费了 API 调用。

**根因**：missing 类型和其他类型共用 `EVIDENCE_AWARE_PROMPT`，只是追加了 `MISSING_SUPPLEMENT`。LLM 的本能是从文档里找答案，你让它"问一个文档没有的"，它还是忍不住找。

**修法**：给 missing 类型写一个**独立的 prompt**，核心指令改为：
- "先浏览文档列出了哪些主题/数据维度"
- "然后选一个文档**明显没有覆盖**的维度来提问"
- "不要试图从文档中找到答案"

**预期效果**：missing 类型一次生成成功率从约 33%（当前需要 2-3 次重试）提升到 70%+，节省 API 调用。

---

### ⑥ 引用过短被拒但其实是有效引用 —— **修 MIN_QUOTE_LENGTH 策略**

**现象**：golden_011 的 comparative 题两次因为"Quote too short"被拒——"即时型消费成为增量引擎..."（11 字符）和"Z 世代成为核心增长力量..."（24 字符）。这些确实是文档中的有效论点，只是中文表达紧凑，30 字符的阈值对中文偏严。

**根因**：`MIN_QUOTE_LENGTH = 30` 是按字符数算的，但中文字符信息密度远高于英文。30 个中文字符已经是一句完整的话了，而 11 个中文字符（如"即时型消费成为增量引擎"）也是有效论点。

**修法**：把 `MIN_QUOTE_LENGTH` 从固定 30 改为**按语言自适应**：
- 检测文本是否主要是中文（`中文字符占比 > 50%`）
- 中文：阈值降为 15
- 英文/混合：保持 30

**预期效果**：comparative 类型的证据验证通过率提升，减少无效重试。

---

### ⑦ 答案太长导致信息膨胀 —— **加答案长度约束**

**现象**：golden_004 的答案有 400+ 字，golden_005 有 600+ 字，golden_007 有 500+ 字。答案越长，包含未引用信息的概率越高——LLM 写嗨了就把文档里看到但没引用的也写进去了。

**根因**：prompt 里没有答案长度约束，LLM 倾向于写"全面"的答案。

**修法**：在 prompt 中加一条硬约束：
- single_fact/missing/irrelevant/adversarial：答案不超过 150 字
- multi_fact/comparative：答案不超过 250 字
- reasoning：答案不超过 300 字

同时在生成后做截断检查，超长的答案截断到限制并标记。

**预期效果**：答案更精炼，未引用信息的比例下降，answer_evidence_issues 减少 30-50%。

---

## 总结：7 条修复的优先级和预期收益

| #    | 修复项                      | 难度 | 预期收益                            |
| ---- | --------------------------- | ---- | ----------------------------------- |
| ①    | max_tokens 按类型动态调整   | 低   | 消除 JSON 截断报废，一次成功率 +10% |
| ②    | 未覆盖数值自动回补 evidence | 中   | 答案置信度 86% → 95%+               |
| ③    | 专有名词模糊匹配            | 低   | 误报率 60% → 10%                    |
| ④    | 对抗性题跳过一致性检查      | 低   | 对抗题 issues 4条 → 0-1条           |
| ⑤    | missing 类型独立 prompt     | 中   | 一次成功率 33% → 70%+               |
| ⑥    | MIN_QUOTE_LENGTH 中文自适应 | 低   | 减少证据验证无效重试                |
| ⑦    | 答案长度约束                | 低   | 未引用信息比例 -30~50%              |

**①③④⑥⑦ 是低难度快速修复**，改几行代码就能出效果，可以先做。
**②⑤ 是中等难度**，需要写新逻辑，但收益也最大。

你觉得哪些先做？还是全部一起上？
