# Plan: Golden Test Set (150题) — 高质量人工校验问题集

## 问题分析

### 当前机器生成测试集的核心缺陷

1. **答案虚高**：LLM 生成问题时，会"偷看"文档内容，导致问题过于简单、过于直接匹配文档措辞，检索和生成指标虚高
2. **ground truth 定位不准**：`_locate_answer_chunks()` 使用关键词/子串启发式匹配，经常定位到错误的 chunk，导致 chunk 级指标不可靠
3. **问题同质化**：6 种类型中，single_fact 占 30%，且 LLM 倾向生成"XX是多少？"式的简单数据查询，缺乏真正考验 RAG 能力的复杂问题
4. **缺少 answer 字段**：现有 `golden_qa.json` 没有 `answer` 字段，只有 `expected_keywords`，无法用于 faithfulness/answer_relevancy 等生成指标
5. **schema 不兼容**：`golden_qa.json` 用 `category`/`expected_sources`/`expected_keywords`，机器生成集用 `question_type`/`source_files`/`source_chunks`，两套体系互不兼容

### 设计目标

制作一个 **~150 题的高质量 golden test set**，核心特征：
- **三要素完备**：问题 + 精确答案 + ground truth 精确定位（文档 + chunk）
- **能测出真问题**：问题设计针对 RAG 系统的典型失败模式
- **兼容现有评测管线**：schema 与机器生成集一致，可直接被 `evaluate_test_set()` 消费
- **人工校验**：LLM 辅助生成初稿 + 人工审核修正，确保质量

---

## 实施方案

### Step 1: 设计 Golden Test Set Schema

在机器生成集 schema 基础上，增加 golden 专属字段：

```json
{
  "id": "golden_001",
  "question": "问题文本",
  "answer": "精确答案（人工校验）",
  "question_type": "single_fact|multi_fact|reasoning|comparative|missing|irrelevant",
  "difficulty": "easy|medium|hard",
  "source_files": ["research_reports/xxx.md"],
  "source_chunks": ["chunk_001", "chunk_002"],
  "ground_truth_excerpt": "答案所在原文片段（50-200字），用于精确定位和验证",
  "expect_retrieval": true,
  "expect_no_answer": false,
  "metadata": {
    "author": "human|llm_assisted",
    "reviewed": true,
    "review_notes": "审核备注",
    "target_failure_mode": "该题针对的RAG失败模式"
  }
}
```

**关键新增字段**：
- `ground_truth_excerpt`：答案所在原文片段，解决"ground truth 在哪"的精确定位问题。比 `source_chunks`（chunk ID）更直观，且不依赖特定分块策略
- `metadata.target_failure_mode`：标注该题针对的 RAG 失败模式，确保题目设计有针对性
- `metadata.reviewed`：标记是否经过人工审核

### Step 2: 设计问题分布（~150题）

针对 RAG 系统的典型失败模式设计问题分布：

| 问题类型 | 数量 | 占比 | 针对的失败模式 |
|---------|------|------|--------------|
| single_fact | 25 | 17% | 基础检索能力：精确数据/事实能否被找到 |
| multi_fact | 30 | 20% | 多跳检索：需要整合多个信息点 |
| reasoning | 25 | 17% | 推理能力：需要基于信息进行逻辑推断 |
| comparative | 25 | 17% | 对比分析：需要跨段落/跨文档对比 |
| missing | 20 | 13% | 拒答能力：文档中没有的信息能否正确识别 |
| irrelevant | 10 | 7% | 幻觉控制：无关问题是否产生幻觉 |
| adversarial | 15 | 10% | 对抗性问题：易混淆/易幻觉的边界场景 |

**adversarial 类型说明**（新增）：
- 数字近似陷阱：问"营收增长15%"但文档是"12.5%"
- 跨文档混淆：问A公司数据但易与B公司混淆
- 时序陷阱：问2024年数据但文档只有2023年
- 否定问题："以下哪个不是..."
- 部分匹配陷阱：答案跨 chunk 边界

### Step 3: 编写 Golden Test Set 生成脚本

创建 `scripts/generate_golden_testset.py`，实现以下流程：

1. **加载文档**：读取 `data/parsed/` 下所有 MD 文件
2. **LLM 辅助生成初稿**：
   - 对每个文档，按问题类型分配生成任务
   - 使用改进的 prompt，要求 LLM 输出 `ground_truth_excerpt`（原文片段）
   - 对 adversarial 类型，使用专门的对抗性 prompt
3. **自动定位 source_chunks**：基于 `ground_truth_excerpt` 精确匹配 chunk（比现有启发式方法更准确）
4. **质量预检**：
   - 答案非空、问题长度合理
   - `ground_truth_excerpt` 能在原文中找到
   - `source_chunks` 定位成功
   - 问题去重（与现有 golden_qa.json 和机器生成集去重）
5. **输出 JSON**：按新 schema 格式化输出

### Step 4: 人工审核工具

创建 `scripts/review_golden_testset.py`，交互式审核工具：

1. 逐题展示：问题 + 答案 + 原文片段 + 定位信息
2. 审核员可修改：问题措辞、答案准确性、ground truth 定位
3. 标记审核状态：approved / needs_revision / rejected
4. 支持断点续审

### Step 5: 集成到评测管线

1. 将 golden test set 保存为 `data/golden_testset/golden_150.json`
2. 在 `TestSetManager` 中增加对 golden test set 的支持：
   - `user_defined: True` + `invalid_policy: "immutable"`
   - 加载时从固定路径读取，不依赖 meal
3. 创建实验配置 `exp_configs/golden_tests/golden_150.yaml`
4. 确保评测管线能正确消费新字段（`ground_truth_excerpt` 用于 context_precision/context_recall 的 ground_truth）

### Step 6: 测试与验证

1. 编写 pytest 测试：
   - Schema 验证：所有字段完整、类型正确
   - 唯一性验证：问题文本不重复
   - 定位验证：`ground_truth_excerpt` 能在对应文档中找到
   - 评测管线集成测试：golden test set 能被正确加载和评测
2. 运行冒烟测试确认管线通畅

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `scripts/generate_golden_testset.py` | Golden test set 生成脚本 |
| 新建 | `scripts/review_golden_testset.py` | 人工审核交互工具 |
| 新建 | `data/golden_testset/golden_150.json` | 最终 golden test set 数据 |
| 新建 | `exp_configs/golden_tests/golden_150.yaml` | Golden 150 实验配置 |
| 修改 | `src/test_set_manager.py` | 增加从固定路径加载 golden test set 的支持 |
| 修改 | `eval/run_experiment.py` | 支持 `ground_truth_excerpt` 字段用于评测 |
| 新建 | `tests/test_golden_testset.py` | Golden test set 验证测试 |

---

## 关键设计决策

1. **为什么用 `ground_truth_excerpt` 而非仅用 `source_chunks`？**
   - chunk ID 依赖分块策略（chunk_size、overlap 变化后 ID 全变）
   - 原文片段是策略无关的，任何分块策略都能从中重新定位
   - 人工审核时，原文片段比 chunk ID 更直观

2. **为什么增加 adversarial 类型？**
   - 现有 6 种类型都是"正常使用"场景，缺少"故意找茬"场景
   - 实际 RAG 系统最容易在边界场景翻车（数字近似、跨文档混淆等）
   - adversarial 题是区分"真好"和"虚高"的关键

3. **为什么用 LLM 辅助 + 人工审核而非纯人工编写？**
   - 150 题纯人工编写工作量巨大（估计 20-30 小时）
   - LLM 生成初稿 + 人工审核修正，可将工作量降至 5-8 小时
   - LLM 生成的答案和 ground_truth_excerpt 需要人工核对，但比从零编写快得多

4. **golden test set 为什么不放在 `data/meals/` 下？**
   - meals 目录下的 test set 绑定 meal_id，golden set 应跨 meal 可用
   - golden set 是项目级资产，不应随 meal 变化而失效
   - 放在 `data/golden_testset/` 作为独立数据集，通过实验配置引用
