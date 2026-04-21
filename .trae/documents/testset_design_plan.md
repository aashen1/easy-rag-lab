# 50题精调测试集设计计划书

## 一、当前系统状态分析

### 1.1 Chunk 元数据结构（已验证）

| 字段 | 状态 | 说明 |
|------|------|------|
| `chunk_id` | ✅ 有 | 如 `中芯国际2025年年度报告_000` |
| `source` | ✅ 有 | 源文件相对路径 |
| `category` | ✅ 有 | `annual_report` 或 `research_report` |
| `chunk_index` | ✅ 有 | chunk 序号 |
| `text` | ✅ 有 | chunk 正文内容 |
| `token_count` | ✅ 有 | token 数量 |
| **PDF页码** | ❌ **无** | chunk 基于 token 切分，未保存 PDF 页码 |
| **MD章节标题** | ⚠️ 部分 | text 内容中包含 `## 第一节 释义` 等标题，但非结构化字段 |

**结论**：当前 chunk 缺少 PDF 页码信息，如果需要按页码定位问题，需要从 text 内容中解析。

---

### 1.2 现有指标计算逻辑

| 指标类型 | 字段 | 计算逻辑 | 是否需要手工修正 |
|-----------|------|----------|------------------|
| **Retrieval (builtin)** | `hit_rate`, `mrr`, `ndcg` | 基于 `expected_sources` 与 `retrieved_sources` 的 chunk ID 匹配 | ⚠️ 需要确保 `expected_sources` 准确 |
| **LLM Retrieval** | `context_precision`, `context_recall` | LLM 评估上下文质量 | ✅ 已修复 skip 逻辑 |
| **Generation** | `faithfulness`, `answer_relevancy`, `answer_correctness` | LLM 评估回答质量 | ⚠️ 依赖 LLM 能力 |

---

### 1.3 问题类型与分布（当前配置）

| 问题类型 | 占比 | 含义 |
|----------|------|------|
| `single_fact` | 30% | 单知识点查询（简单事实） |
| `multi_fact` | 25% | 多知识点综合 |
| `reasoning` | 15% | 推理型问题 |
| `comparative` | 15% | 对比分析 |
| `missing` | 10% | 缺失知识点（文档中没有答案） |
| `irrelevant` | 5% | 无关问题（文档不相关） |

**问题**：当前 `irrelevant` 仅有 5%，可能不足以测试 RAG 系统的"拒答"能力。

---

### 1.4 是否值得手工调整？

**核心问题**：AI 生成的问题集是否存在根本性缺陷？

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 问题类型覆盖 | ✅ 充分 | 6 种类型已覆盖 |
| ground truth 准确性 | ⚠️ 已修复 | 收紧 source_chunks 后大幅改善 |
| 特殊问题处理 | ✅ 已修复 | expect_retrieval=False 跳过 LLM retrieval |
| 问题质量 | ❓ 待验证 | 需人工审核判断 |

**结论**：
- ✅ **系统层面的问题已基本修复**（source_chunks 过宽、special question 跳过逻辑）
- ⚠️ **问题质量需要手工审核**：AI 生成的问题可能：
  - 太简单（无需深入理解文档）
  - 太机械（格式固定，缺乏灵活性）
  - 分布不合理（占比随意设定）

---

## 二、50题测试集设计建议

### 2.1 目标

获得一份**有说服力的研究报告**，能够：
1. 暴露 RAG 系统的真实短板
2. 区分不同检索/生成策略的优劣
3. 统计显著（50 题提供足够样本）

### 2.2 问题类型与占比设计

| 类型 | 数量 | 占比 | 设计理由 |
|------|------|------|----------|
| `single_fact` | 15 | 30% | 基础能力测试，区分"能回答"vs"不能回答" |
| `multi_fact` | 10 | 20% | 测试多chunk检索与信息整合能力 |
| `reasoning` | 8 | 16% | 测试推理能力（因果、归纳、演绎） |
| `comparative` | 5 | 10% | 测试跨段落对比能力 |
| `reasoning_hard` | 5 | 10% | 需要多步推理的困难问题 |
| `missing` | 4 | 8% | 测试"不知道"的能力（拒答正确性） |
| `irrelevant` | 3 | 6% | 测试无关问题的正确拒绝 |

**调整理由**：
- 增加 `reasoning_hard`（困难推理）：当前只有一种 reasoning，无法区分难度
- 增加 `missing` 和 `irrelevant`：更充分测试系统的"知之为知之"

### 2.3 手工 vs 自动化分工

| 项目 | 手工（你） | 自动化（我） |
|------|-----------|--------------|
| **问题撰写** | ✅ 50 题 | - |
| **答案撰写** | ✅ 50 题 | - |
| **source_chunks 标注** | - | ✅ 预跑检索自动匹配 |
| **question_type 标注** | ✅ 最终审核 | ✅ 可预设模板 |
| **difficulty 标注** | ✅ 最终审核 | ⚠️ 可预设 |
| **expect_retrieval 标注** | ✅ 特殊问题必填 | ⚠️ 可预设 |
| **ground truth 验证** | ✅ 抽查 | ✅ 自动计算指标 |

---

## 三、实施步骤

### 步骤 1：我预跑一遍检索（自动化）

运行一次"只检索不评估"的实验，获取每个问题的：
- top-5 检索结果
- 匹配的 source_chunks

### 步骤 2：你手工准备问题集（手工）

基于预跑结果，你手工准备：
- 50 个问题 + 答案
- 标注 `question_type`、`difficulty`
- 标注 `expect_retrieval`（对 missing/irrelevant）

### 步骤 3：我自动匹配 ground truth（自动化）

基于你标注的问题，运行检索，自动：
- 匹配 `expected_sources`（从预跑结果中选取）
- 生成最终测试集

### 步骤 4：正式实验（自动化）

运行完整实验，生成报告

---

## 四、你需要手工做的事情

1. **准备 50 个问题 + 答案**（可以用模板参考 `config.yaml` 中的 type_distribution）
2. **标注每个问题的**：
   - `question_type`
   - `difficulty`  
   - `expect_retrieval`（missing/irrelevant 类型必填）
   - `source_document`（来源文档）
3. **可选**：对 `expected_sources` 进行最终审核

---

## 五、我的工作量（自动化）

| 任务 | 输入 | 输出 |
|------|------|------|
| 预跑检索 | 测试集（只需问题） | 每个问题的 top-5 检索结果 |
| 自动匹配 ground truth | 你的问题 + 预跑结果 | 完整的测试集 JSON |
| 运行实验 | 完整测试集 | 实验报告 |

---

## 待你确认

1. **是否认可这个分工方式？**
2. **问题类型占比是否需要调整？**
3. **你希望从哪个文档开始准备问题？**（我可以先跑一遍预检索给你参考）
