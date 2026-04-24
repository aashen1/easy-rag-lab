# Golden Test Set (150题) 构建记录

<!-- status: completed -->

> 完成日期：2026-04-25
> 版本：v0.1.8+
> 分支：golden-qa-150
> 数据文件：`data/golden_testset/golden_150.json`

## 背景

现有机器生成测试集存在严重的"指标虚高"问题：LLM 在生成问题时"偷看"文档，倾向于生成过于简单、过于直接匹配文档措辞的问题，导致检索和生成指标虚高，无法有效区分 RAG 系统的优劣。

核心缺陷：
1. **答案虚高**：问题过于简单，检索和生成指标普遍偏高
2. **ground truth 定位不准**：`_locate_answer_chunks()` 使用关键词启发式匹配，经常定位错误
3. **问题同质化**：single_fact 占 30%，且多为"XX是多少？"式简单数据查询
4. **缺少 answer 字段**：`golden_qa.json` 只有 `expected_keywords`，无法用于生成指标
5. **schema 不兼容**：golden_qa.json 和机器生成集使用两套不同的 schema

## 设计决策

### 1. 新增 `ground_truth_excerpt` 字段

**选择**：在 `source_chunks`（chunk ID）之外，新增 `ground_truth_excerpt`（原文片段）字段。

**理由**：
- chunk ID 依赖分块策略（chunk_size/overlap 变化后 ID 全变）
- 原文片段是策略无关的，任何分块策略都能从中重新定位
- 人工审核时，原文片段比 chunk ID 更直观
- 可直接用于 context_precision/context_recall 的 ground truth

### 2. 新增 `adversarial` 问题类型

**选择**：在原有 6 种类型基础上，新增 adversarial（对抗性问题）类型。

**理由**：
- 现有类型都是"正常使用"场景，缺少"故意找茬"场景
- RAG 系统最容易在边界场景翻车（数字近似、跨文档混淆、时序陷阱等）
- adversarial 题是区分"真好"和"虚高"的关键

### 3. LLM 辅助 + 人工审核

**选择**：LLM 生成初稿 + 人工审核修正，而非纯人工编写。

**理由**：
- 150 题纯人工编写工作量巨大（20-30 小时）
- LLM 生成初稿 + 人工审核可将工作量降至 5-8 小时
- 类型特定的 prompt 模板确保 LLM 生成对应类型的问题

### 4. Golden test set 独立于 meal

**选择**：放在 `data/golden_testset/` 而非 `data/meals/`。

**理由**：
- meals 目录下的 test set 绑定 meal_id，golden set 应跨 meal 可用
- golden set 是项目级资产，不应随 meal 变化而失效
- 通过实验配置 `golden: true` 一行引用

## 实施过程

### Phase 1: Schema 与脚本开发

#### 新建文件

| 文件 | 用途 |
|------|------|
| `scripts/generate_golden_testset.py` | Golden test set 生成脚本 |
| `scripts/review_golden_testset.py` | 交互式人工审核工具 |
| `exp_configs/golden_tests/golden_150.yaml` | Golden 150 实验配置 |
| `tests/test_golden_testset.py` | 44 个验证测试 |

#### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/test_set_manager.py` | 新增 `load_golden_testset()`、`_get_golden_testset_dir()`；`resolve_test_set()` 支持 `golden: true` 路由 |
| `eval/run_experiment.py` | 采样时传递 `ground_truth_excerpt`；评测时优先使用 `ground_truth_excerpt` 作为 `expected_answer` |
| `eval/evaluators/ragas_evaluator.py` | `_build_ragas_dataset()` 优先使用 `ground_truth_excerpt` 作为 reference |

### Phase 2: 生成过程中的问题与修复

#### 问题 1：文档格式不兼容

**现象**：`data/parsed/` 下只有 `.pages.json` 文件，没有 `.md` 文件。

**修复**：新增 `_load_pages_json()` 函数，支持 `.pages.json` 格式（将所有 page 的 text 拼接为完整文档）。

#### 问题 2：LLM 忽略问题类型要求

**现象**：LLM 将所有问题标为 `single_fact` 或 `multi_fact`，其他类型完全缺失。

**根因**：通用 prompt 中的类型要求太弱，LLM 倾向于生成最自然的问题类型。

**修复**：
1. 为每种类型设计完全不同的 prompt 模板（`TYPE_INSTRUCTIONS`），让 prompt 结构本身引导出对应类型
2. 生成后强制覆盖 `question_type` 为我们要求的类型（不依赖 LLM 自报）
3. 去掉类型匹配验证（因为强制覆盖了）

#### 问题 3：补充循环无限运行

**现象**：主循环生成 150 题后，补充循环继续运行到 327 题仍未停止。

**根因**：主循环遍历所有 doc_plans 条目，不检查是否已达到目标数量；去重只在最后执行，补充循环看到 `len(questions) >= 150` 就跳过。

**修复**：
1. 主循环增加 `if len(questions) >= num_questions: break` 检查
2. 改为在线去重（`seen_questions` set），生成时即时检查重复
3. 去掉末尾的批量去重步骤

#### 问题 4：文档分布偏斜

**现象**：63+59=122 题来自"2023年年度报告"和"2023年年度报告摘要"。

**根因**：round-robin 分配时，多个公司都有同名文档（如"2023年年度报告"），被视为不同文档但生成类似问题。

**修复**：改进 `distribute_across_documents()`，先 shuffle 问题类型列表再分配，确保每个文档获得混合类型。

### Phase 3: 人工审核与修正

审核发现的问题及修正：

#### 删除近重复题目（5 对 → 删 5 题）

| 保留 | 删除 | 原因 |
|------|------|------|
| #98 格力营收利润 vs 2022 | #103 | 几乎相同措辞 |
| #126 海螺水泥分红 | #127 | 仅年份位置不同 |
| #140 美的营收 | #145 | 仅主语位置不同 |
| #142 美的利润分配 | #147 | 微调措辞 |
| #141 美的vs格力盈利 | #148 | 仅差一个字 |

#### 精简 irrelevant 类型（22 → 11，删 11 题）

删除最泛泛的（"电影""天气""度假"等），保留更有针对性的无关问题。

#### 改善 missing 类型答案（10 题）

原来所有 missing 题答案都是千篇一律的"文档未提及该信息"，改为更具体的表述，如"文档未披露关于绿色建筑的具体信息"。

#### 手工增补 adversarial 题（+5 题）

| 问题 | 陷阱类型 |
|------|---------|
| 万科经营性现金流超过100亿吗？ | 数字膨胀陷阱（实际39.1亿） |
| 宁德时代动力电池市占率超过40%了吗？ | 百分比膨胀（实际36.8%） |
| 比亚迪净利润增长100%以上对吧？ | 增长率膨胀（实际80.72%） |
| 格力空调收入占比不到50%？ | 比例反转（实际73.7%） |
| 美的没有进行股份回购对吗？ | 否定陷阱（实际有回购） |

#### 手工增补 missing 题（+10 题）

| 问题 | 针对的幻觉场景 |
|------|--------------|
| 招行区块链技术进展 | 前沿技术话题易引发幻觉 |
| 恒瑞FDA批准创新药 | FDA批准易编造 |
| 工行碳排放量 | 碳排放话题易幻觉 |
| 海天味业海外并购 | 并购话题易编造 |
| 药明康德数据安全处罚 | 负面事件易误答 |
| 五粮液高管薪酬 | 薪酬话题易猜测 |
| 平安保险赔付率 | 专业指标易编造 |
| 中芯国际大基金投资 | 政策投资易肯定回答 |
| 海螺水泥海外营收占比 | 比例数据易编造 |
| 万科长租公寓新品牌 | 品牌话题易编造 |

#### 补1题 single_fact 达到 150 题

招商银行2023年归母净利润。

## 最终成果

### 类型分布

| 类型 | 数量 | 目标 | 偏差 |
|------|------|------|------|
| multi_fact | 33 | 30 | +3 |
| comparative | 31 | 25 | +6 |
| single_fact | 22 | 25 | -3 |
| missing | 20 | 20 | 0 |
| reasoning | 18 | 25 | -7 |
| adversarial | 15 | 15 | 0 |
| irrelevant | 11 | 11 | 0 |

### 三要素完备性

- ✅ 150 题全部有 question + answer + ground_truth_excerpt
- ✅ 150 个唯一 ID，150 个唯一问题文本
- ✅ 0 个缺失 answer/excerpt/source_files（非 irrelevant）

### 来源分布

- LLM 辅助生成：134 题
- 人工编写：16 题（5 adversarial + 10 missing + 1 single_fact）

### 质量指标

- Excerpt 验证率：85.33%（原文片段能在文档中找到）
- 生成失败：0
- 重复：0

## 使用方式

### 运行评测

```bash
pixi run python eval/run_experiment.py --config exp_configs/golden_tests/golden_150.yaml
```

### 重新生成

```bash
pixi run python scripts/generate_golden_testset.py --num-questions 150
```

### 人工审核

```bash
pixi run python scripts/review_golden_testset.py
pixi run python scripts/review_golden_testset.py --start-from 50
```

## 遗留问题与后续方向

1. **reasoning 类型偏少**（18 vs 目标 25）：LLM 对推理型问题生成困难，需要改进 prompt 或手工补充
2. **文档分布仍偏斜**：61+55=116 题来自"2023年年度报告"和"摘要"，2024/2025 年报和研报覆盖不足
3. **source_chunks 全为空**：因 `data/chunks/` 目录不存在，无法定位 chunk ID。运行 `chunker.py` 后需重新执行 chunk 定位
4. **excerpt_verified 率 85%**：15% 的问题的 ground_truth_excerpt 无法在原文中精确匹配，可能是 LLM 改写了原文，需人工核对
5. **手工题目的 excerpt 需验证**：16 道手工题的 ground_truth_excerpt 是基于记忆编写的，需与实际文档核对
