# Golden Test 生成质量提升 Spec

## Why

20 题沙箱测试暴露了 golden test 生成流程的 7 个系统性问题：JSON 截断导致整题报废、答案包含未引用的数值、专有名词匹配误报率高、对抗性题被一致性检查误伤、missing 类型生成效率低、中文引用过短被拒、答案过长导致信息膨胀。这些问题导致一次生成成功率约 85%、答案置信度仅 86%、20 题中 4 题需要人工修正。

## What Changes

- 根据问题类型动态调整 LLM 输出的 max_tokens，comparative/reasoning/multi_fact 使用 2048
- 答案中未覆盖的数值自动回溯文档补齐 evidence quote
- 专有名词匹配从精确子串改为去后缀模糊匹配
- 对抗性题跳过答案-证据一致性检查中的推理类 issues
- missing 类型使用独立 prompt，先列文档已覆盖主题再选未覆盖维度提问
- MIN_QUOTE_LENGTH 按中文字符占比自适应（中文 15 / 英文 30）
- 在 prompt 中增加答案字数约束，生成后超长答案截断并标记

## Impact

- Affected code:
  - `src/test_generator.py` — 核心变更文件，涉及 7 处修改
  - `tests/test_golden_testset.py` — 新增/修改测试用例
- Affected configs:
  - `config.yaml` — 新增 `test_generation.evidence_max_tokens` 配置项

## ADDED Requirements

### Requirement: 按类型动态调整 max_tokens

系统 SHALL 根据问题类型为 LLM 输出设置不同的 max_tokens：
- `comparative` / `reasoning` / `multi_fact`：2048
- 其他类型：保持 1024

#### Scenario: comparative 类型不再截断
- **WHEN** 生成 comparative 类型问题时
- **THEN** LLM 的 max_tokens 设为 2048，JSON 输出不被截断

#### Scenario: single_fact 类型保持默认
- **WHEN** 生成 single_fact 类型问题时
- **THEN** LLM 的 max_tokens 保持 1024

### Requirement: 未覆盖数值自动回补 evidence

系统 SHALL 在答案-证据一致性校验发现未覆盖数值时，自动回溯文档查找包含该数值的片段，将匹配到的原文追加为 evidence quote。

#### Scenario: 答案数值在文档中找到
- **WHEN** 答案中存在 evidence 未覆盖的数值，且该数值在文档其他位置存在
- **THEN** 系统自动从文档中提取包含该数值的上下文片段，追加为 evidence 条目，标记 `match_type="auto_supplemented"`

#### Scenario: 答案数值在文档中找不到
- **WHEN** 答案中存在 evidence 未覆盖的数值，且该数值在文档中不存在
- **THEN** 系统保留该 issue 在 `answer_evidence_issues` 中，不追加 evidence

### Requirement: 专有名词去后缀模糊匹配

系统 SHALL 在专有名词匹配时先尝试精确匹配，失败后去除常见后缀（行业/市场/公司/集团/股份/技术/产品/业务）再匹配。

#### Scenario: 改写后的专有名词匹配成功
- **WHEN** 答案中包含"电子行业"，evidence 中包含"电子"
- **THEN** 去除后缀"行业"后"电子"在 evidence 中找到，视为匹配成功

#### Scenario: 完全不匹配的专有名词
- **WHEN** 答案中包含"量子计算行业"，evidence 中不包含"量子计算"
- **THEN** 去除后缀后仍无法匹配，记录 issue

### Requirement: 对抗性题一致性检查豁免

系统 SHALL 对 adversarial 类型的问题在答案-证据一致性检查中豁免推理类 issues（数值计算、推断性专有名词），仅保留"诱饵数字是否在证据中"的正向验证。

#### Scenario: 对抗性题的推理计算不报 issue
- **WHEN** adversarial 类型答案中包含 LLM 推理产生的数值（如差值计算）
- **THEN** 该数值不触发"未在证据中找到"的 issue

#### Scenario: 对抗性题的诱饵数字仍需验证
- **WHEN** adversarial 类型答案中引用了文档中的原始数据
- **THEN** 该数据仍需在 evidence 中找到，找不到则记录 issue

### Requirement: missing 类型独立 prompt

系统 SHALL 为 missing 类型使用独立的 prompt 模板，核心指令为"先列出文档已覆盖的主题和数据维度，然后选择一个文档明显未覆盖的维度提问"。

#### Scenario: missing 类型一次生成成功
- **WHEN** 使用独立 prompt 生成 missing 类型问题
- **THEN** LLM 输出的问题不包含 evidence，`expect_no_answer=True`，无需重试

### Requirement: MIN_QUOTE_LENGTH 中文自适应

系统 SHALL 根据引用文本的中文字符占比动态调整最小引用长度阈值：中文占比 > 50% 时阈值为 15，否则为 30。

#### Scenario: 中文引用使用较低阈值
- **WHEN** 引用文本中文字符占比 > 50%，且引用长度 >= 15 字符
- **THEN** 引用通过长度检查

#### Scenario: 英文/混合引用使用标准阈值
- **WHEN** 引用文本中文字符占比 <= 50%，且引用长度 >= 30 字符
- **THEN** 引用通过长度检查

### Requirement: 答案长度约束

系统 SHALL 在 prompt 中为不同问题类型设置答案字数上限，并在生成后检查答案长度，超长答案截断到限制并标记。

字数限制：
- single_fact / missing / irrelevant / adversarial：200 字
- multi_fact / comparative：300 字
- reasoning：350 字

#### Scenario: 答案在限制内
- **WHEN** 生成的答案字数在类型限制内
- **THEN** 答案原样保留

#### Scenario: 答案超长截断
- **WHEN** 生成的答案字数超过类型限制
- **THEN** 答案在最后一个完整句号处截断，metadata 中标记 `answer_truncated=True`

## MODIFIED Requirements

### Requirement: 答案-证据一致性校验

原有逻辑：对所有非 irrelevant/missing 类型统一执行数值和专有名词的精确匹配检查。

修改后：
1. 专有名词匹配增加去后缀模糊匹配作为精确匹配的 fallback
2. adversarial 类型豁免推理类 issues，仅保留诱饵数字的正向验证
3. 未覆盖数值触发自动回补 evidence 逻辑（新增）
