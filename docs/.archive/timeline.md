# 项目演进时间线

> 每个版本都是一圈"年轮"。这里是项目博物馆的导览图。

---

## 时间线总览

| 版本 | 日期 | 主题 | 一句话叙事 | 关键目录 |
|------|------|------|-----------|---------|
| v0.1.0 | 04-15 | MVP 基础链路 | 从零到一 | [mvp-era/mvp-pipeline/](v0.1.0-v0.1.5-mvp-era/mvp-pipeline/) |
| v0.1.1~5 | 04-16 | MVP+评测+自动化 | 有了能跑的系统 | [mvp-era/](v0.1.0-v0.1.5-mvp-era/) |
| v0.1.6 | 04-18 | 项目卫生 | 有了规矩 | [hygiene-era/](v0.1.6-hygiene-era/) |
| v0.1.7 | 04-19 | 评测增强 | 有了更准的尺子 | [evaluation-era/](v0.1.7-evaluation-era/) |
| v0.1.8 | 04-20 | TestSet 管理 | 有了独立的测试集 | [testset-era/](v0.1.8-testset-era/) |
| v0.1.9 | 04-21 | 评测双引擎 | 有了可信的尺子 | [dual-eval-era/](v0.1.9-dual-eval-era/) |
| v0.1.10 | 04-22 | 解析新纪元 | 有了自由的源头 | [parsing-era/](v0.1.10-parsing) |
| v0.1.11 | 04-26 | 链路统一 | 有了统一的基准 | [unification-era/](v0.1.11-unification-era/) |
| v0.1.12 | 04-28 | 项目治理 | 有了可持续的节奏 | [governance-era/](v0.1.12-governance-era/) |
| v0.1.13 | 04-28 | RAG 可视化 | 有了可展示的产品 | [visualization-era/](v0.1.13-visualization) |

---

## 各版本详情

### v0.1.0~v0.1.5 — MVP 时代

> 从一个空 repo 到能跑的 RAG 系统

**核心叙事**：项目从一个空仓库开始，搭建了基础的 RAG 链路——PDF 解析、向量索引、检索生成。然后加入了评测系统、Meal 数据管理、Token 追踪等基础设施。这是"从零到一"的阶段。

**主题目录**：

- [mvp-pipeline/](v0.1.0-v0.1.5-mvp-era/mvp-pipeline/) — 初始 RAG 链路搭建
- [meal-system/](v0.1.0-v0.1.5-mvp-era/meal-system/) — Meal 数据管理系统
- [testset-generation/](v0.1.0-v0.1.5-mvp-era/testset-generation/) — 测试集生成器
- [experiment-framework/](v0.1.0-v0.1.5-mvp-era/experiment-framework/) — 自动化评测系统
- [token-tracking/](v0.1.0-v0.1.5-mvp-era/token-tracking/) — Token 消耗追踪
- [code-quality/](v0.1.0-v0.1.5-mvp-era/code-quality/) — 代码质量修复
- [dependency-fixes/](v0.1.0-v0.1.5-mvp-era/dependency-fixes/) — 依赖兼容性修复
- [release/](v0.1.0-v0.1.5-mvp-era/release/) — 版本验收报告

### v0.1.6 — 项目卫生时代

> 没有规矩不成方圆

**核心叙事**：系统跑起来了，但代码和文档一团糟。这个版本专注于建立秩序——文档系统重构、代码质量修复、归档机制建立。

**主题目录**：

- [doc-system/](v0.1.6-hygiene-era/doc-system/) — 文档系统重构
- [code-quality/](v0.1.6-hygiene-era/code-quality/) — 代码质量修复
- [release/](v0.1.6-hygiene-era/release/) — 版本验收报告

### v0.1.7 — 评测增强时代

> 有了更准的尺子

**核心叙事**：原有的评测指标不够精细，无法区分文档级问题和片段级问题。引入 Faithfulness、Answer Relevancy 等新指标，修复 FPR 等评测 Bug。

**主题目录**：

- [evaluation-enhancement/](v0.1.7-evaluation-era/evaluation-enhancement/) — 评测系统增强
- [evaluation-fixes/](v0.1.7-evaluation-era/evaluation-fixes/) — 评测 Bug 修复
- [release/](v0.1.7-evaluation-era/release/) — 版本验收报告

### v0.1.8 — TestSet 管理时代

> 有了独立的测试集

**核心叙事**：测试集从评测脚本中独立出来，成为一等公民。Meal 系统扩展与测试集合并，评测粒度从粗到细。

**主题目录**：

- [testset-management/](v0.1.8-testset-era/testset-management/) — TestSet 独立管理
- [meal-system/](v0.1.8-testset-era/meal-system/) — Meal 扩展与测试集合并
- [evaluation-fixes/](v0.1.8-testset-era/evaluation-fixes/) — 评测粒度修复
- [project-hygiene/](v0.1.8-testset-era/project-hygiene/) — 项目卫生
- [release/](v0.1.8-testset-era/release/) — 版本验收报告

### v0.1.9 — 评测双引擎时代

> 你没法改进你量不准的东西

**核心叙事**：这是项目最密集的版本之一。RAGAS 框架集成带来了五大新指标，与原有评测形成双引擎。但集成过程充满坎坷——deprecated API、虚高基线、合并冲突……这个版本的 evaluation-fixes/ 目录最能体现"修 Bug 的修 Bug"的挣扎。

**主题目录**：

- [ragas-integration/](v0.1.9-dual-eval-era/ragas-integration/) — RAGAS 框架集成（7 篇计划文档）
- [evaluation-fixes/](v0.1.9-dual-eval-era/evaluation-fixes/) — 评测链路修复（最大目录，20+ 文件）
- [experiment-framework/](v0.1.9-dual-eval-era/experiment-framework/) — 实验框架优化
- [testset-generation/](v0.1.9-dual-eval-era/testset-generation/) — 测试集生成优化
- [parsing-pipeline/](v0.1.9-dual-eval-era/parsing-pipeline/) — 解析管线初探
- [project-hygiene/](v0.1.9-dual-eval-era/project-hygiene/) — 项目卫生
- [code-quality/](v0.1.9-dual-eval-era/code-quality/) — 代码质量

### v0.1.10 — 解析新纪元时代

> 有了自由的源头

**核心叙事**：PDF 解析从单一方案扩展为多解析器框架——PyMuPDF、pdfplumber、pymupdf4llm。引入 Artifact 体系管理解析产物，page-aware 分块让检索更精准。

**主题目录**：

- [parsing-pipeline/](v0.1.10-parsing/parsing-pipeline) — 多解析器框架 + Artifact 体系
- [doc-system/](v0.1.10-parsing/doc-system) — 文档更新

### v0.1.11 — 链路统一时代

> 有了统一的基准

**核心叙事**：Golden 测试集生成链路统一，150 题标准测试集建立。Artifact 路径迁移完成，irrelevant 问题指标修复。

**主题目录**：

- [testset-generation/](v0.1.11-unification-era/testset-generation/) — Golden 链路统一 + 150 题
- [evaluation-fixes/](v0.1.11-unification-era/evaluation-fixes/) — irrelevant 指标修复
- [artifact-migration/](v0.1.11-unification-era/artifact-migration/) — Artifact 路径迁移
- [project-hygiene/](v0.1.11-unification-era/project-hygiene/) — 项目卫生
- [release/](v0.1.11-unification-era/release/) — 版本验收报告

### v0.1.12 — 项目治理时代

> 有了可持续的节奏

**核心叙事**：Issue 管理系统替代了 TODO.md，自定义异常体系让错误不再沉默，ruff 规范统一代码风格，project-memory skill 让 AI 跨 session 记住项目上下文。

**主题目录**：

- [issue-system/](v0.1.12-governance-era/issue-system/) — Issue 管理系统
- [project-governance/](v0.1.12-governance-era/project-governance/) — 异常体系 + ruff + 配置验证
- [code-quality/](v0.1.12-governance-era/code-quality/) — 代码健康度重构
- [project-memory/](v0.1.12-governance-era/project-memory/) — 跨 session 记忆

### v0.1.13 — RAG 可视化时代

> 看不见的系统只能靠信仰，看得见的系统才能靠判断

**核心叙事**：RAG 从命令行黑盒变成了可视化的 Web 应用。Streamlit Web Demo 让用户能看见检索过程、预览 PDF、和系统对话。

**主题目录**：

- [visualization/](v0.1.13-visualization/visualization) — Streamlit Web Demo
- [experiment-framework/](v0.1.13-visualization/experiment-framework) — 实验框架

### 跨版本

- [general-research/](cross-version/general-research/) — 通用调研

---

## 版本叙事总览

```
量得准 → 解得开 → 合得拢 → 管得住 → 看得见
  v0.1.9   v0.1.10   v0.1.11   v0.1.12   v0.1.13
```

| 版本 | 主题 | 一句话 |
|------|------|--------|
| v0.1.9 | 评测双引擎 | 有了可信的尺子 |
| v0.1.10 | 解析新纪元 | 有了自由的源头 |
| v0.1.11 | 链路统一 | 有了统一的基准 |
| v0.1.12 | 项目治理 | 有了可持续的节奏 |
| v0.1.13 | RAG 可视化 | 有了可展示的产品 |
