# Golden Testset 交互式审核工具指南

<!-- status: active -->

> 创建日期：2026-04-27
> 最后更新：2026-04-27
> 版本：v0.2.0
> 核心模块: [`scripts/review_golden_testset.py`](../../scripts/review_golden_testset.py)
> AI审核: [`scripts/ai_reviewer.py`](../../scripts/ai_reviewer.py)
> PDF查看: [`scripts/pdf_viewer.py`](../../scripts/pdf_viewer.py)

---

## 概述

本文档介绍 Golden Testset 交互式审核工具的完整使用方式与实现细节。该工具在 v0.2.0 中进行了全面升级，新增三大核心能力：

| 能力 | 效果 | 预期收益 |
|------|------|---------|
| **AI 预审核** | LLM 自动评分 + 三级分类 | 减少 40-60% 人工审核量 |
| **PDF 自动定位** | 一键打开 PDF 到对应页面 | 无需手动翻页找信源 |
| **Chunk 内嵌展示** | 审核界面直接显示相关 chunk | 无需切换窗口对照原文 |

核心思路：**AI 先审 → 自动过滤 → 人工精审存疑题**，将"150 题逐个看"优化为"只看 AI 拿不准的 60-90 题"。

---

## 快速开始

### 最推荐：分级审核模式

一条命令完成 AI 预审 + 人工精审：

```bash
pixi run python scripts/review_golden_testset.py --tiered-review
```

这个命令会：
1. 调用 LLM 对所有题目进行质量评分
2. A 级题目自动通过（约 40-60%）
3. B/C 级题目进入交互式审核（约 40-60 题）

### 传统模式（增强版）

```bash
pixi run python scripts/review_golden_testset.py
```

与旧版兼容，但增加了 chunk 上下文展示、PDF 打开、进度条等增强功能。

---

## 运行模式详解

### 模式一：交互式审核（默认）

逐题审核，支持通过/编辑/拒绝/跳过，自动保存进度。

```bash
# 基本用法
pixi run python scripts/review_golden_testset.py

# 指定输入文件
pixi run python scripts/review_golden_testset.py \
  --input data/golden_testset/golden_150.json

# 从第 50 题开始
pixi run python scripts/review_golden_testset.py --start-from 50

# 记录审核人身份
pixi run python scripts/review_golden_testset.py --reviewer "张三"
```

#### 交互界面

```
================================================================================
  #042/150  │  golden_042  │  single_fact  │  easy  │  ⚠ AI: B(3.2)
================================================================================

  Q: 该公司2024年营收增长率是多少？

  A: 该公司2024年营收同比增长15%。

  EXCERPT: "公司2024年营收达到100亿元，同比增长15%"
     ✓ Excerpt verified  ✗ Numerical auto-corrected

  ┌─ CHUNK [p3_002] Page 3 | 512 tokens ──────────────────────────┐
  │ 公司2024年营收达到100亿元，同比增长15%。其中主营业务收入...     │
  │ 净利润为50亿元，较上年增长8%...                                 │
  └────────────────────────────────────────────────────────────────┘

  PDF: annual_report.pdf → Page 3  [p] Open (sumatra)

  ──────────────────────────────────────────────────────────────────
  [a]Approve  [e]Edit  [r]Reject  [s]Skip  [q]Quit  [p]PDF  [c]Chunks  [i]AI detail
================================================================================
```

#### 快捷键说明

| 按键 | 动作 | 说明 |
|------|------|------|
| `a` | Approve | 通过该题，标记为 `approved` |
| `e` | Edit | 编辑题目（问题/答案/摘录/类型/难度） |
| `r` | Reject | 拒绝该题，需输入拒绝理由 |
| `s` | Skip | 跳过，不做任何修改 |
| `q` | Quit | 保存进度并退出 |
| `p` | **PDF** | 打开 PDF 到对应页面（新增） |
| `c` | **Chunks** | 切换 chunk 上下文显示/隐藏（新增） |
| `i` | **AI Detail** | 查看 AI 审核详情（新增） |

#### 退出时的会话摘要

```
================================================================================
  Review Session Summary
  [████████████████░░░░] 120/150 (80%)
  Total: 150 | Approved: 110 | Rejected: 10 | Pending: 30
  This session: 45 approved, 5 rejected, 3 skipped
  Avg time per decision: 8.3s
  Duration: 441s
  Saved to: data/golden_testset/golden_150.json
================================================================================
```

---

### 模式二：AI 预审核

仅运行 AI 评分，不进入交互式审核。适合先了解整体质量分布。

```bash
# 运行 AI 预审核
pixi run python scripts/review_golden_testset.py --ai-review

# 预览模式（不保存结果）
pixi run python scripts/review_golden_testset.py --ai-review --dry-run

# 指定 LLM 模型
pixi run python scripts/review_golden_testset.py --ai-review --llm-preset opus
```

#### AI 评分维度

每个维度 1-5 分，综合评分 = 四维加权平均：

| 维度 | 评估内容 | 权重 |
|------|---------|------|
| `question_clarity` | 问题是否清晰、无歧义、可独立理解 | 25% |
| `answer_accuracy` | 答案是否与 ground_truth_excerpt 一致 | 25% |
| `answer_completeness` | 答案是否充分回答了问题 | 25% |
| `source_consistency` | 原文片段是否真正支撑了答案 | 25% |

#### 三级分类

| 等级 | 综合评分 | 建议操作 | 预期占比 |
|------|---------|---------|---------|
| **A 级** | ≥ 4.0 | 自动通过 | 40-60% |
| **B 级** | 3.0 - 3.9 | 需人工审核 | 25-35% |
| **C 级** | < 3.0 | 建议拒绝或重点审核 | 10-20% |

#### AI 审核输出示例

```
================================================================================
  AI Pre-Review
  Model: LongCat-Flash-Lite
  Questions: 150
================================================================================
  [1/150] Reviewing golden_001...
  [5/150] Progress: 5/150 reviewed (3%)
  ...
================================================================================
  AI Review Results
================================================================================
  Tier A (auto-approve): 72 questions
  Tier B (needs review): 53 questions
  Tier C (likely reject): 25 questions
  Total: 150

  Tier C questions (first 10):
    golden_023: 答案与原文片段不一致
    golden_045: 问题表述模糊，存在歧义
    ...
================================================================================
```

---

### 模式三：分级审核（推荐）

AI 预审核 + 人工精审的组合模式，最高效的审核方式。

```bash
# 标准分级审核
pixi run python scripts/review_golden_testset.py --tiered-review

# 指定 LLM 和审核人
pixi run python scripts/review_golden_testset.py \
  --tiered-review \
  --llm-preset default \
  --reviewer "张三"
```

#### 分级审核流程

```
150 道题
    ↓
Step 1: AI 预审核
    ├── A 级 (72题) → 自动标记 auto_approved ✓
    ├── B 级 (53题) → 进入人工审核
    └── C 级 (25题) → 进入人工审核（高亮标记 ⚠）
    ↓
Step 2: 人工审核 B/C 级（78 题）
    ├── 逐题交互式审核
    ├── AI 评分作为参考信息展示
    ├── PDF 自动打开 + Chunk 内嵌展示
    └── 审核结果持久化
    ↓
完成！人工只需审核 78 题而非 150 题
```

#### 分级审核完成摘要

```
================================================================================
  Tiered Review Complete
  [████████████████████] 150/150 (100%)
  Total: 150 | Approved: 130 | Rejected: 15 | Pending: 5
  Human session: 58 approved, 15 rejected
  Duration: 520s
================================================================================
```

---

### 模式四：按 AI 评分排序审核

先审最低分的题，确保最差的问题优先被发现。

```bash
# 先运行 AI 预审核（如果还没运行过）
pixi run python scripts/review_golden_testset.py --ai-review

# 按评分从低到高审核
pixi run python scripts/review_golden_testset.py --sort-by-score
```

---

### 模式五：审计报告

生成结构化质量报告，不修改任何数据。

```bash
pixi run python scripts/review_golden_testset.py --audit
```

审计维度详见 [Golden Testset 生成操作指南](golden-testset-generation.md) 第三步。

---

### 模式六：自动审批

基于规则的质量检查，自动通过/拒绝符合条件的题目。

```bash
# 预览模式
pixi run python scripts/review_golden_testset.py --auto-approve --dry-run

# 实际执行
pixi run python scripts/review_golden_testset.py --auto-approve
```

自动通过条件：excerpt 已验证 + 无数值修正 + 未被审计标记 + 长度合理。

---

## CLI 参数完整参考

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | `data/golden_testset/golden_150.json` | 测试集 JSON 文件路径 |
| `--start-from` | 1 | 起始题号（1-based），默认从上次中断处继续 |
| `--audit` | - | 生成审计报告 |
| `--auto-approve` | - | 自动审批符合条件的题目 |
| `--dry-run` | - | 预览模式，不修改文件（配合 `--auto-approve` 或 `--ai-review`） |
| `--include-auto-approved` | - | 交互审核时也显示已自动通过的题目 |
| `--reviewer` | None | 审核人标识，记录到 metadata |
| `--ai-review` | - | 运行 AI 预审核 |
| `--tiered-review` | - | 分级审核模式（AI + 人工） |
| `--llm-preset` | None | AI 审核使用的 LLM 预设名称 |
| `--sort-by-score` | - | 按 AI 评分排序审核（最低分优先） |
| `--no-chunks` | - | 禁用 chunk 上下文展示 |
| `--no-pdf` | - | 禁用 PDF 查看器集成 |

---

## PDF 查看器集成

### 支持的查看器

| 查看器 | 优先级 | 页面跳转方式 | 说明 |
|--------|--------|-------------|------|
| **SumatraPDF** | 首选 | `-reuse-instance -page N` | 轻量、命令行友好，推荐安装 |
| **Edge** | 备选 | `file:///path#page=N` | Windows 10 自带 |
| **纯文本** | 兜底 | 直接展示页面文本 | 无需外部查看器 |

### 安装 SumatraPDF（推荐）

1. 从 [SumatraPDF 官网](https://www.sumatrapdfreader.org/free-pdf-reader) 下载安装
2. 安装到默认路径即可，工具会自动检测
3. `-reuse-instance` 参数确保同一窗口切换页面，不会每次新开窗口

### 页面定位逻辑

审核时按 `p` 键，工具自动定位 PDF 页面：

```
question.source_chunks → chunk.metadata.page_number → 直接跳转
         ↓ (无 chunk 页码)
question.ground_truth_excerpt → .pages.json 模糊匹配 → 定位页面
         ↓ (无 parsed 数据)
展示 chunk 文本作为替代
```

### Chunk 内嵌展示

审核界面自动展示与题目相关的 chunk 文本：

```
┌─ CHUNK [p3_002] Page 3 | 512 tokens ──────────────────────────┐
│ 公司2024年营收达到100亿元，同比增长15%。其中主营业务收入...     │
│ 净利润为50亿元，较上年增长8%...                                 │
└────────────────────────────────────────────────────────────────┘
```

Chunk 查找逻辑：
1. 优先按 `source_chunks` 中的 chunk_id 精确查找
2. 若无 chunk_id，用 `ground_truth_excerpt` 在 chunk 文本中模糊匹配
3. 匹配算法：先尝试子串包含，再使用最长公共子序列覆盖率

---

## AI 审核实现细节

### LLM 调用架构

AI 审核复用项目已有的 LLM 基础设施：

```
config.yaml → get_llm_config() → create_llm_client(mode="sdk") → Anthropic SDK
```

- 默认使用 `test_generation` 配置的模型（LongCat-Flash-Lite），兼顾质量与成本
- 可通过 `--llm-preset` 指定其他预设（如 `opus` 获取更高质量评分）
- 每题一次 API 调用，5 题一组打印进度

### 评分缓存机制

AI 审核结果写入 `question.metadata.ai_review`，避免重复调用：

```json
{
  "metadata": {
    "ai_review": {
      "dimensions": {
        "question_clarity": {"score": 4, "reason": "清晰明确"},
        "answer_accuracy": {"score": 5, "reason": "与原文一致"},
        "answer_completeness": {"score": 4, "reason": "充分回答"},
        "source_consistency": {"score": 5, "reason": "原文支撑答案"}
      },
      "overall_score": 4.5,
      "tier": "A",
      "overall_comment": "高质量问答对",
      "suggested_action": "approve",
      "reviewed_at": "2026-04-27T10:30:00"
    }
  }
}
```

- 已有 `ai_review` 的题目会被跳过，不会重复调用 API
- 如需重新评分，先用 `reset_review_status.py` 清除

### Prompt 设计

AI 审核使用结构化 Prompt，要求 LLM 返回 JSON 格式的评分：

- 四维评分（1-5 分）+ 每维理由
- 一句话总结
- 建议操作（approve / review / reject）

返回的 JSON 经过容错解析：
1. 优先提取 markdown 代码块中的 JSON
2. 其次提取裸 JSON 对象
3. 解析失败时返回默认值（3.0 分，B 级，建议 review）

---

## 数据流与文件结构

### 审核状态流转

```
pending → approved / auto_approved / needs_revision / rejected
```

| 状态 | 含义 | 设置方式 |
|------|------|---------|
| `pending` | 未审核 | 默认状态 |
| `approved` | 人工通过 | 交互审核按 `a` |
| `auto_approved` | 自动通过 | auto-approve 或 AI A 级 |
| `needs_revision` | 需修改 | 交互审核按 `e` |
| `rejected` | 已拒绝 | 交互审核按 `r` |

### 审核元数据

每次审核操作都会在题目 metadata 中记录：

```json
{
  "metadata": {
    "reviewed": true,
    "review_status": "approved",
    "reviewed_at": "2026-04-27T10:30:00",
    "reviewer": "张三",
    "review_notes": "数值已核对",
    "ai_review": { ... }
  }
}
```

### 审计日志

测试集级别的操作记录保存在 `metadata.audit_log`：

```json
{
  "audit_log": [
    {
      "event": "ai_review",
      "timestamp": "2026-04-27T10:00:00",
      "llm_preset": "default",
      "tier_a": 72,
      "tier_b": 53,
      "tier_c": 25
    },
    {
      "event": "tiered_review_human_phase",
      "timestamp": "2026-04-27T10:30:00",
      "reviewer": "张三",
      "session_approved": 58,
      "session_rejected": 15,
      "session_duration_sec": 520
    }
  ]
}
```

### 自动保存与恢复

- 每 5 题自动保存一次
- 退出时记录 `last_reviewed_index`
- 下次启动自动从上次位置继续
- 每次修改前自动创建带时间戳的备份文件

---

## 推荐工作流

### 最佳实践：分级审核 + PDF 对照

```bash
# Step 1: 生成测试集（如果还没有）
pixi run python scripts/generate_golden_testset.py --num-questions 150 --seed 42

# Step 2: 运行审计报告，了解整体质量
pixi run python scripts/review_golden_testset.py --audit

# Step 3: 分级审核（核心步骤）
pixi run python scripts/review_golden_testset.py --tiered-review --reviewer "你的名字"

# Step 4: （可选）对跳过的题目补充审核
pixi run python scripts/review_golden_testset.py --sort-by-score

# Step 5: 重置（如果需要重来）
pixi run python scripts/reset_review_status.py data/golden_testset/golden_150.json
```

### 效率对比

| 方式 | 人工审核量 | 预估时间 | 说明 |
|------|-----------|---------|------|
| 旧版逐题审核 | 150 题 | ~60 分钟 | 每题需手动找 PDF |
| AI 预审 + 人工 | 60-90 题 | ~25 分钟 | AI 过滤 A 级，人工只看 B/C |
| 分级审核 + PDF | 60-90 题 | ~15 分钟 | PDF 自动定位，chunk 内嵌 |

---

## 常见问题

### Q: AI 预审核的 API 成本大约多少？

150 题约需 150 次 API 调用，使用 LongCat-Flash-Lite 模型，总成本约 ¥1-3。如需更高质量评分，可用 `--llm-preset opus`，成本约 ¥10-20。

### Q: AI 评分不准确怎么办？

AI 评分是辅助参考，不替代人工判断。B 级题目的 AI 评分会作为参考信息展示，但最终决定权在审核人。C 级题目如果人工判断实际合格，也可以通过。

### Q: PDF 打不开怎么办？

1. 确认已安装 SumatraPDF 或 Edge
2. SumatraPDF 需安装到默认路径，或加入 PATH 环境变量
3. 如果无法安装 PDF 查看器，工具会自动回退到纯文本展示模式
4. 使用 `--no-pdf` 参数可完全禁用 PDF 集成

### Q: Chunk 内容为空怎么办？

可能原因：
- Artifact 缓存中无对应的 chunks 数据（需先运行 chunker）
- `source_files` 路径与 chunks 中的 `source` 不匹配
- `ground_truth_excerpt` 与所有 chunk 文本的相似度都低于阈值

解决：确认 `data/artifacts/_pointers/full_chunks.pointer` 指向正确的 chunks 目录。

### Q: 如何重新运行 AI 审核？

先用重置脚本清除 AI 审核结果：

```bash
pixi run python scripts/reset_review_status.py data/golden_testset/golden_150.json
```

然后重新运行 `--ai-review` 或 `--tiered-review`。

### Q: 审核到一半退出，进度会丢失吗？

不会。工具每 5 题自动保存，退出时也会保存当前位置。下次启动自动从上次位置继续。

---

## 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| AI 评分模型 | test_generation 默认模型 | 兼顾质量与成本，避免审核成本超过生成成本 |
| 三级分类阈值 | A≥4.0, B≥3.0, C<3.0 | 经验值，4.0 以上基本可靠，3.0 以下明显有问题 |
| PDF 查看器优先级 | SumatraPDF > Edge > 纯文本 | SumatraPDF 命令行友好，支持 `-reuse-instance` |
| 页面定位策略 | chunk page_number > excerpt 模糊匹配 | chunk 元数据精确，模糊匹配作为兜底 |
| Chunk 匹配算法 | 子串包含 > 最长公共子序列覆盖率 | `SequenceMatcher.ratio()` 对中文文本评分偏低 |
| 评分缓存位置 | question.metadata.ai_review | 与现有 metadata 结构一致，无需额外文件 |
| 向后兼容 | 所有新功能通过 CLI 参数启用 | 不影响已有审核流程 |

---

## 相关文档

- [Golden Testset 生成操作指南](golden-testset-generation.md) — 生成流程与参数说明
- [TestSet 管理系统](test-set-management.md) — 测试集生命周期管理
- [评测指标详解](evaluation-metrics.md) — 各指标的含义和计算方式
- [Artifact 系统指南](meal-system.md) — ArtifactCache 与 Pointer 机制
