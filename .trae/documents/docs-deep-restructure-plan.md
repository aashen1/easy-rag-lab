# 文档深度重构计划（v2 — 全面按版本重组）

> 目标：提升文档条理性与叙事性，打造"项目博物馆"效果，满足开源与简历展示需求

---

## 一、现状诊断

### 1.1 核心问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **77 处失效链接** | 🔴 | README.md 有 25 处，遍及 15+ 文件 |
| **README.md 完全过时** | 🔴 | 仍指向旧 `guides/operations/` 结构 |
| **归档目录物理结构杂乱** | 🔴 | `uncatogarized/` 拼写错误+100+ 文件堆叠，plan/spec 人为割裂 |
| **部分文档分类不当** | 🟡 | dev 向文档在 user-guides/，聊天记录在 dev-guides/ |
| **缺少"博物馆导览"** | 🟡 | 有丰富历史素材，缺少叙事性索引 |

### 1.2 用户决策

- ✅ 归档目录做**全面按版本/叙事主题的物理重组**，不做轻量索引
- ✅ plan 和 spec 不再分开，按功能主题聚合
- ✅ `uncatogarized/` 文件夹全部清空并移除
- ✅ 活跃文档分类调整（rag-optimization-implementation → dev-guides 等）
- ✅ 先移动文件，再根据语义修复链接
- ✅ 失效链接尽量找到目标，找不到的说明情况

---

## 二、重构方案

### Phase 1：活跃文档分类调整

| 操作 | 文件 | 原因 |
|------|------|------|
| user-guides/ → dev-guides/ | `rag-optimization-implementation.md` | 自称"面向开发者"，实现细节+测试策略 |
| user-guides/ → dev-guides/ | `profiling-configuration.md` | 性能调优配置，开发场景 |
| dev-guides/ → .archive/ | `test-layering-and-time-budgets-chat-log.md` | AI 聊天记录，非指南 |
| 评估是否归档 | `ruff-usage-guide.md` | 检查与 `lint-and-precommit.md` 是否重复 |

调整后：

```
user-guides/  (15 篇，纯用户向)
├── cli-reference.md
├── config-reference.md
├── pdf-parsing.md
├── question-generation.md
├── evaluation-metrics.md
├── ragas-evaluation.md
├── experiment-system.md
├── hyperparameter-guide.md
├── golden-testset-generation.md
├── golden-test-review.md
├── test-set-management.md
├── meal-system.md
├── streamlit-web-demo.md
├── token-tracking.md
└── issue-system.md

dev-guides/  (7~8 篇，纯开发向)
├── architecture.md
├── testing.md
├── test-layering-and-time-budgets.md
├── rag-optimization-implementation.md    ← 从 user-guides 移入
├── profiling-configuration.md            ← 从 user-guides 移入
├── lint-and-precommit.md
├── commit-conventions.md
└── release-cadence.md
```

### Phase 2：归档目录全面重组

**核心原则**：按"版本+叙事主题"组织，plan 和 spec 合并到同一主题目录下。

#### 2.2.1 新目录结构

```
.archive/
├── README.md                    # 博物馆指南（重写）
├── timeline.md                  # 时间线导览（新增）
├── archive-log.md               # 归档日志（保留）
│
├── v0.1.0-v0.1.5-mvp-era/       # MVP 时代
│   ├── mvp-pipeline/            # 初始 RAG 链路搭建
│   ├── meal-system/             # Meal 数据管理系统
│   ├── testset-generation/      # 测试集生成器
│   ├── experiment-framework/    # 自动化评测系统
│   ├── token-tracking/          # Token 追踪
│   ├── code-quality/            # 代码质量修复
│   ├── dependency-fixes/        # 依赖兼容性修复
│   └── release/                 # 版本验收报告
│
├── v0.1.6-hygiene-era/          # 项目卫生时代
│   ├── doc-system/              # 文档系统重构
│   ├── code-quality/            # 代码质量
│   └── release/                 # 版本验收报告
│
├── v0.1.7-evaluation-era/       # 评测增强时代
│   ├── evaluation-enhancement/  # 评测系统增强
│   ├── evaluation-fixes/        # 评测 Bug 修复
│   └── release/                 # 版本验收报告
│
├── v0.1.8-testset-era/          # TestSet 管理时代
│   ├── testset-management/      # TestSet 独立管理
│   ├── meal-system/             # Meal 扩展与测试集合并
│   ├── evaluation-fixes/        # 评测粒度修复
│   ├── project-hygiene/         # 项目卫生
│   └── release/                 # 版本验收报告
│
├── v0.1.9-dual-eval-era/        # 评测双引擎时代
│   ├── ragas-integration/       # RAGAS 集成（7 篇 plan + 相关 spec）
│   ├── evaluation-fixes/        # 评测链路修复（15+ 篇 plan + 相关 spec）
│   ├── experiment-framework/    # 实验框架优化
│   ├── testset-generation/      # 测试集生成优化
│   ├── parsing-pipeline/        # 解析管线初探
│   ├── project-hygiene/         # 项目卫生
│   ├── code-quality/            # 代码质量
│   └── release/                 # 版本验收报告
│
├── v0.1.10-parsing-era/         # 解析新纪元
│   ├── parsing-pipeline/        # 多解析器框架 + Artifact 体系
│   ├── doc-system/              # 文档更新
│   └── release/                 # 版本验收报告
│
├── v0.1.11-unification-era/     # 链路统一时代
│   ├── testset-generation/      # Golden 链路统一 + 150 题
│   ├── evaluation-fixes/        # irrelevant 指标修复
│   ├── artifact-migration/      # Artifact 路径迁移
│   ├── project-hygiene/         # 项目卫生
│   └── release/                 # 版本验收报告
│
├── v0.1.12-governance-era/      # 项目治理时代
│   ├── issue-system/            # Issue 管理系统
│   ├── project-governance/      # 异常体系 + ruff + 配置验证
│   ├── code-quality/            # 代码健康度重构
│   ├── project-hygiene/         # 项目卫生
│   ├── project-memory/          # 跨 session 记忆
│   └── release/                 # 版本验收报告
│
├── v0.1.13-visualization-era/   # RAG 可视化时代
│   ├── visualization/           # Streamlit Web Demo
│   ├── experiment-framework/    # 实验框架
│   └── release/                 # 版本验收报告
│
└── cross-version/               # 跨版本主题
    ├── general-research/        # 通用调研
    └── project-hygiene/         # 跨版本卫生工作
```

#### 2.2.2 详细文件映射

以下列出每个文件从旧位置到新位置的映射。格式：`旧路径 → 新路径`

##### v0.1.0-v0.1.5 MVP 时代

**mvp-pipeline/**
- `specs/uncatogarized/start/` → `v0.1.0-v0.1.5-mvp-era/mvp-pipeline/start/`

**meal-system/**
- `specs/uncatogarized/meal/` → `v0.1.0-v0.1.5-mvp-era/meal-system/meal/`
- `plans/uncatogarized/implement-sampling-feature.md` → `v0.1.0-v0.1.5-mvp-era/meal-system/implement-sampling-feature.md`

**testset-generation/**
- `plans/uncatogarized/testset-design-plan.md` → `v0.1.0-v0.1.5-mvp-era/testset-generation/testset-design-plan.md`
- `plans/uncatogarized/testset_generator_update_plan.md` → `v0.1.0-v0.1.5-mvp-era/testset-generation/testset_generator_update_plan.md`

**experiment-framework/**
- `specs/uncatogarized/automate-evaluation/` → `v0.1.0-v0.1.5-mvp-era/experiment-framework/automate-evaluation/`

**token-tracking/**
- `plans/uncatogarized/token-tracking-feature.md` → `v0.1.0-v0.1.5-mvp-era/token-tracking/token-tracking-feature.md`

**code-quality/**
- `plans/uncatogarized/code-issues-fix-requirements.md` → `v0.1.0-v0.1.5-mvp-era/code-quality/code-issues-fix-requirements.md`
- `specs/uncatogarized/test-suite-analysis/` → `v0.1.0-v0.1.5-mvp-era/code-quality/test-suite-analysis/`
- `specs/uncatogarized/test-suite-redesign/` → `v0.1.0-v0.1.5-mvp-era/code-quality/test-suite-redesign/`
- `specs/uncatogarized/known-bugs-fixup/` → `v0.1.0-v0.1.5-mvp-era/code-quality/known-bugs-fixup/`
- `specs/uncatogarized/test-review-fixup/` → `v0.1.0-v0.1.5-mvp-era/code-quality/test-review-fixup/`

**dependency-fixes/**
- `specs/uncatogarized/flagembedding-to-transformers/` → `v0.1.0-v0.1.5-mvp-era/dependency-fixes/flagembedding-to-transformers/`

**release/**
- `reviews/v0.1.5/` → `v0.1.0-v0.1.5-mvp-era/release/v0.1.5/`

##### v0.1.6 项目卫生时代

**doc-system/**
- `plans/uncatogarized/archive-reorganization-plan.md` → `v0.1.6-hygiene-era/doc-system/archive-reorganization-plan.md`
- `plans/uncatogarized/backlog-system-improvement-plan.md` → `v0.1.6-hygiene-era/doc-system/backlog-system-improvement-plan.md`
- `plans/uncatogarized/todo-archiver-mechanism-plan.md` → `v0.1.6-hygiene-era/doc-system/todo-archiver-mechanism-plan.md`
- `specs/uncatogarized/document-system-refactor/` → `v0.1.6-hygiene-era/doc-system/document-system-refactor/`
- `.archive/inbox-log.md` → `v0.1.6-hygiene-era/doc-system/inbox-log.md`
- `.archive/idea-ai-era-git-practice.md` → `v0.1.6-hygiene-era/doc-system/idea-ai-era-git-practice.md`

**code-quality/**
- `specs/uncatogarized/code-quality-fixup/` → `v0.1.6-hygiene-era/code-quality/code-quality-fixup/`
- `troubleshooting/resolved/ghost-folder-mkdir.md` → `v0.1.6-hygiene-era/code-quality/ghost-folder-mkdir.md`

**release/**
- `reviews/v0.1.6/` → `v0.1.6-hygiene-era/release/v0.1.6/`

##### v0.1.7 评测增强时代

**evaluation-enhancement/**
- `specs/uncatogarized/new-evaluation-system/` → `v0.1.7-evaluation-era/evaluation-enhancement/new-evaluation-system/`
- `plans/uncatogarized/rag-eval-metrics-optimization-plan.md` → `v0.1.7-evaluation-era/evaluation-enhancement/rag-eval-metrics-optimization-plan.md`
- `plans/uncatogarized/question-generation-quality-fix-plan.md` → `v0.1.7-evaluation-era/evaluation-enhancement/question-generation-quality-fix-plan.md`

**evaluation-fixes/**
- `plans/uncatogarized/eval-system-acceptance-fix.md` → `v0.1.7-evaluation-era/evaluation-fixes/eval-system-acceptance-fix.md`
- `troubleshooting/eval-metrics-bugfix.md` → `v0.1.7-evaluation-era/evaluation-fixes/eval-metrics-bugfix.md`
- `troubleshooting/eval-system-acceptance-fix.md` → `v0.1.7-evaluation-era/evaluation-fixes/eval-system-acceptance-fix.md`
- `troubleshooting/a-bug-about-FPR.md` → `v0.1.7-evaluation-era/evaluation-fixes/a-bug-about-FPR.md`

**release/**
- `reviews/v0.1.7/` → `v0.1.7-evaluation-era/release/v0.1.7/`

##### v0.1.8 TestSet 管理时代

**testset-management/**
- `specs/uncatogarized/v0.1.8/v0.1.8-merge-and-release-plan.md` → `v0.1.8-testset-era/testset-management/v0.1.8-merge-and-release-plan.md`
- `specs/uncatogarized/v0.1.8/v0.1.8-release-plan-rag-enhancement-verification.md` → `v0.1.8-testset-era/testset-management/v0.1.8-release-plan-rag-enhancement-verification.md`

**meal-system/**
- `specs/uncatogarized/meal-extension-and-testset-merge/` → `v0.1.8-testset-era/meal-system/meal-extension-and-testset-merge/`

**evaluation-fixes/**
- `specs/uncatogarized/fix-evaluation-granularity/` → `v0.1.8-testset-era/evaluation-fixes/fix-evaluation-granularity/`
- `specs/uncatogarized/fix-eval-try-round-2/` → `v0.1.8-testset-era/evaluation-fixes/fix-eval-try-round-2/`

**project-hygiene/**
- `plans/uncatogarized/cleanup-and-backlog-review-plan.md` → `v0.1.8-testset-era/project-hygiene/cleanup-and-backlog-review-plan.md`
- `plans/uncatogarized/housekeeping-and-backlog-review-plan.md` → `v0.1.8-testset-era/project-hygiene/housekeeping-and-backlog-review-plan.md`
- `plans/uncatogarized/backlog-cleanup-plan.md` → `v0.1.8-testset-era/project-hygiene/backlog-cleanup-plan.md`
- `plans/uncatogarized/backlog-issue-assessment-and-fix-plan.md` → `v0.1.8-testset-era/project-hygiene/backlog-issue-assessment-and-fix-plan.md`
- `plans/uncatogarized/compare-discussion-with-implementation.md` → `v0.1.8-testset-era/project-hygiene/compare-discussion-with-implementation.md`
- `troubleshooting/resolved/pytest-basetemp-fileexistserror.md` → `v0.1.8-testset-era/project-hygiene/pytest-basetemp-fileexistserror.md`

**release/**
- `reviews/v0.1.8/` → `v0.1.8-testset-era/release/v0.1.8/`

##### v0.1.9 评测双引擎时代

**ragas-integration/**
- `plans/uncatogarized/ragas-integration-plan.md` → `v0.1.9-dual-eval-era/ragas-integration/ragas-integration-plan.md`
- `plans/uncatogarized/ragas-integration-analysis.md` → `v0.1.9-dual-eval-era/ragas-integration/ragas-integration-analysis.md`
- `plans/uncatogarized/ragas-integration-implementation-plan.md` → `v0.1.9-dual-eval-era/ragas-integration/ragas-integration-implementation-plan.md`
- `plans/uncatogarized/ragas-metrics-improvement-plan.md` → `v0.1.9-dual-eval-era/ragas-integration/ragas-metrics-improvement-plan.md`
- `plans/uncatogarized/ragas-metrics-review-plan.md` → `v0.1.9-dual-eval-era/ragas-integration/ragas-metrics-review-plan.md`
- `plans/uncatogarized/ragas-baseline-acceptance-plan.md` → `v0.1.9-dual-eval-era/ragas-integration/ragas-baseline-acceptance-plan.md`
- `plans/uncatogarized/replace-deprecated-ragas-api.md` → `v0.1.9-dual-eval-era/ragas-integration/replace-deprecated-ragas-api.md`

**evaluation-fixes/**
- `plans/uncatogarized/eval-system-merge-cleanup-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/eval-system-merge-cleanup-plan.md`
- `plans/uncatogarized/evaluation-system-integration-analysis-and-cleanup-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/evaluation-system-integration-analysis-and-cleanup-plan.md`
- `plans/uncatogarized/merge-conflict-resolution-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/merge-conflict-resolution-plan.md`
- `plans/uncatogarized/project-status-after-merge.md` → `v0.1.9-dual-eval-era/evaluation-fixes/project-status-after-merge.md`
- `plans/uncatogarized/eval-metrics-issues-fix-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/eval-metrics-issues-fix-plan.md`
- `plans/uncatogarized/experiment-metrics-bug-fix-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/experiment-metrics-bug-fix-plan.md`
- `plans/uncatogarized/experiment-report-accuracy-improvement-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/experiment-report-accuracy-improvement-plan.md`
- `plans/uncatogarized/experiment-report-issues-fix-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/experiment-report-issues-fix-plan.md`
- `plans/uncatogarized/fix-evaluation-remaining-issues.md` → `v0.1.9-dual-eval-era/evaluation-fixes/fix-evaluation-remaining-issues.md`
- `plans/uncatogarized/fix-quick-verify-metrics-anomalies.md` → `v0.1.9-dual-eval-era/evaluation-fixes/fix-quick-verify-metrics-anomalies.md`
- `plans/uncatogarized/stream2-chunking-metrics-fixes.md` → `v0.1.9-dual-eval-era/evaluation-fixes/stream2-chunking-metrics-fixes.md`
- `plans/uncatogarized/refactor-text-hierarchy-fix-segment-mapping.md` → `v0.1.9-dual-eval-era/evaluation-fixes/refactor-text-hierarchy-fix-segment-mapping.md`
- `plans/uncatogarized/feat-023-context-length-control.md` → `v0.1.9-dual-eval-era/evaluation-fixes/feat-023-context-length-control.md`
- `plans/uncatogarized/v0.1.9/bug-024-chunk-encoding-fix.md` → `v0.1.9-dual-eval-era/evaluation-fixes/bug-024-chunk-encoding-fix.md`
- `plans/uncatogarized/v0.1.9/eval-metrics-fix-and-enhancement.md` → `v0.1.9-dual-eval-era/evaluation-fixes/eval-metrics-fix-and-enhancement.md`
- `plans/uncatogarized/v0.1.9/experiment-report-metrics-fix-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/experiment-report-metrics-fix-plan.md`
- `plans/uncatogarized/v0.1.9/fix-evaluation-bugs.md` → `v0.1.9-dual-eval-era/evaluation-fixes/fix-evaluation-bugs.md`
- `plans/uncatogarized/v0.1.9/issue-fix-plan.md` → `v0.1.9-dual-eval-era/evaluation-fixes/issue-fix-plan.md`
- `specs/uncatogarized/eval-system-cleanup/` → `v0.1.9-dual-eval-era/evaluation-fixes/eval-system-cleanup/`
- `specs/uncatogarized/fix-baseline-evaluation-issues/` → `v0.1.9-dual-eval-era/evaluation-fixes/fix-baseline-evaluation-issues/`
- `specs/uncatogarized/fix-pipeline-audit-issues/` → `v0.1.9-dual-eval-era/evaluation-fixes/fix-pipeline-audit-issues/`
- `specs/uncatogarized/stream2-chunking-metrics-fixes/` → `v0.1.9-dual-eval-era/evaluation-fixes/stream2-chunking-metrics-fixes/`
- `specs/uncatogarized/fix-eval-pipeline-reliability/` → `v0.1.9-dual-eval-era/evaluation-fixes/fix-eval-pipeline-reliability/`
- `reviews/investigations/baseline-evaluation-deep-inspection-report.md` → `v0.1.9-dual-eval-era/evaluation-fixes/baseline-evaluation-deep-inspection-report.md`
- `reviews/investigations/pipeline-deep-audit.md` → `v0.1.9-dual-eval-era/evaluation-fixes/pipeline-deep-audit.md`
- `reviews/issues/bug-024-chunk-encoding-and-page-info.md` → `v0.1.9-dual-eval-era/evaluation-fixes/bug-024-chunk-encoding-and-page-info.md`
- `reviews/issues/bug-025-source-chunks-empty.md` → `v0.1.9-dual-eval-era/evaluation-fixes/bug-025-source-chunks-empty.md`
- `reviews/sessions/baseline-evaluation-fix-record.md` → `v0.1.9-dual-eval-era/evaluation-fixes/baseline-evaluation-fix-record.md`
- `troubleshooting/merge-conflict-analysis-2026-04-23.md` → `v0.1.9-dual-eval-era/evaluation-fixes/merge-conflict-analysis-2026-04-23.md`

**experiment-framework/**
- `plans/uncatogarized/exp-configs-analysis-and-improvement-plan.md` → `v0.1.9-dual-eval-era/experiment-framework/exp-configs-analysis-and-improvement-plan.md`
- `plans/uncatogarized/exp-configs-review-against-new-pipeline.md` → `v0.1.9-dual-eval-era/experiment-framework/exp-configs-review-against-new-pipeline.md`
- `plans/uncatogarized/exp-configs-review-plan.md` → `v0.1.9-dual-eval-era/experiment-framework/exp-configs-review-plan.md`
- `plans/uncatogarized/high-priority-dev-directions.md` → `v0.1.9-dual-eval-era/experiment-framework/high-priority-dev-directions.md`

**testset-generation/**
- `plans/uncatogarized/rag-testset-system-review-and-optimization.md` → `v0.1.9-dual-eval-era/testset-generation/rag-testset-system-review-and-optimization.md`
- `plans/uncatogarized/optimize-golden-testset-generation.md` → `v0.1.9-dual-eval-era/testset-generation/optimize-golden-testset-generation.md`
- `plans/uncatogarized/v0.1.9/fix-golden-testset-generation.md` → `v0.1.9-dual-eval-era/testset-generation/fix-golden-testset-generation.md`
- `plans/uncatogarized/v0.1.9/fix-hybrid-ground-truth-excerpt.md` → `v0.1.9-dual-eval-era/testset-generation/fix-hybrid-ground-truth-excerpt.md`
- `plans/uncatogarized/v0.1.9/golden-test-set-150.md` → `v0.1.9-dual-eval-era/testset-generation/golden-test-set-150.md`
- `plans/uncatogarized/v0.1.9/unify-golden-testset-generation.md` → `v0.1.9-dual-eval-era/testset-generation/unify-golden-testset-generation.md`
- `specs/uncatogarized/v0.1.9/hybrid-question-generation-strategy/` → `v0.1.9-dual-eval-era/testset-generation/hybrid-question-generation-strategy/`

**parsing-pipeline/**
- `plans/uncatogarized/downstream-pipeline-adaptation-plan.md` → `v0.1.9-dual-eval-era/parsing-pipeline/downstream-pipeline-adaptation-plan.md`
- `plans/uncatogarized/pdf2md-optimize-with-4llm-params.md` → `v0.1.9-dual-eval-era/parsing-pipeline/pdf2md-optimize-with-4llm-params.md`
- `plans/uncatogarized/pdf2md-stay-on-4llm-plan.md` → `v0.1.9-dual-eval-era/parsing-pipeline/pdf2md-stay-on-4llm-plan.md`
- `plans/uncatogarized/pdf2md-switch-to-fitz-plan.md` → `v0.1.9-dual-eval-era/parsing-pipeline/pdf2md-switch-to-fitz-plan.md`
- `specs/uncatogarized/v0.1.9/fix-cache-pollution-risks/` → `v0.1.9-dual-eval-era/parsing-pipeline/fix-cache-pollution-risks/`

**project-hygiene/**
- `plans/uncatogarized/independent-issues-for-current-tasks.md` → `v0.1.9-dual-eval-era/project-hygiene/independent-issues-for-current-tasks.md`
- `plans/uncatogarized/plan-fix-independent-issues.md` → `v0.1.9-dual-eval-era/project-hygiene/plan-fix-independent-issues.md`
- `plans/uncatogarized/cicd-integration-plan.md` → `v0.1.9-dual-eval-era/project-hygiene/cicd-integration-plan.md`
- `plans/uncatogarized/v0.1.9/safe-issue-cleanup-plan.md` → `v0.1.9-dual-eval-era/project-hygiene/safe-issue-cleanup-plan.md`
- `reviews/sessions/independent-issues-batch-session.md` → `v0.1.9-dual-eval-era/project-hygiene/independent-issues-batch-session.md`
- `reviews/v019-priority-issues-deep-analysis.md` → `v0.1.9-dual-eval-era/project-hygiene/v019-priority-issues-deep-analysis.md`

**code-quality/**
- `plans/uncatogarized/v0.1.9/test-coverage-enhancement-plan.md` → `v0.1.9-dual-eval-era/code-quality/test-coverage-enhancement-plan.md`

**release/**
- (v0.1.9 无独立验收报告目录，相关内容在 evaluation-fixes/ 中)

##### v0.1.10 解析新纪元

**parsing-pipeline/**
- `plans/uncatogarized/unify-parsing-pipeline.md` → `v0.1.10-parsing-era/parsing-pipeline/unify-parsing-pipeline.md`
- `plans/uncatogarized/unify-parsing-pipeline-full-support-plan.md` → `v0.1.10-parsing-era/parsing-pipeline/unify-parsing-pipeline-full-support-plan.md`
- `plans/uncatogarized/pipeline-performance-profiling-plan.md` → `v0.1.10-parsing-era/parsing-pipeline/pipeline-performance-profiling-plan.md`
- `plans/uncatogarized/ocr-comparison-experiment.md` → `v0.1.10-parsing-era/parsing-pipeline/ocr-comparison-experiment.md`
- `plans/uncatogarized/fix-profiling-accuracy.md` → `v0.1.10-parsing-era/parsing-pipeline/fix-profiling-accuracy.md`
- `plans/uncatogarized/fix-document-loader-multi-format.md` → `v0.1.10-parsing-era/parsing-pipeline/fix-document-loader-multi-format.md`
- `specs/uncatogarized/add-fitz-pdfplumber-parser-pipeline/` → `v0.1.10-parsing-era/parsing-pipeline/add-fitz-pdfplumber-parser-pipeline/`
- `specs/uncatogarized/add-unified-document-loader/` → `v0.1.10-parsing-era/parsing-pipeline/add-unified-document-loader/`
- `specs/uncatogarized/optimize-pymupdf4llm-params/` → `v0.1.10-parsing-era/parsing-pipeline/optimize-pymupdf4llm-params/`
- `troubleshooting/cache-analysis.md` → `v0.1.10-parsing-era/parsing-pipeline/cache-analysis.md`
- `troubleshooting/merge-conflict-analysis.md` → `v0.1.10-parsing-era/parsing-pipeline/merge-conflict-analysis.md`

**doc-system/**
- `plans/uncatogarized/rf-015-update-hyperparameter-guide.md` → `v0.1.10-parsing-era/doc-system/rf-015-update-hyperparameter-guide.md`

**release/**
- (v0.1.10 无独立验收报告目录)

##### v0.1.11 链路统一时代

**testset-generation/**
- `specs/uncatogarized/fix-golden-test-generation-quality/` → `v0.1.11-unification-era/testset-generation/fix-golden-test-generation-quality/`
- `plans/uncatogarized/golden-test-review-optimization.md` → `v0.1.11-unification-era/testset-generation/golden-test-review-optimization.md`
- `reviews/investigations/rf-012-chunk-vs-document-strategy-analysis.md` → `v0.1.11-unification-era/testset-generation/rf-012-chunk-vs-document-strategy-analysis.md`
- `reviews/sessions/golden-testset-150-session.md` → `v0.1.11-unification-era/testset-generation/golden-testset-150-session.md`
- `reviews/sessions/issue-fix-batch-2026-04-26.md` → `v0.1.11-unification-era/testset-generation/issue-fix-batch-2026-04-26.md`

**evaluation-fixes/**
- `troubleshooting/irrelevant-question-metrics-fix.md` → `v0.1.11-unification-era/evaluation-fixes/irrelevant-question-metrics-fix.md`
- `.archive/hybrid-metrics-fix.md` → `v0.1.11-unification-era/evaluation-fixes/hybrid-metrics-fix.md`

**artifact-migration/**
- `plans/uncatogarized/v0.1.9/artifact-path-migration-plan.md` → `v0.1.11-unification-era/artifact-migration/artifact-path-migration-plan.md`
- `reviews/artifact-path-migration.md` → `v0.1.11-unification-era/artifact-migration/artifact-path-migration.md`

**project-hygiene/**
- `plans/uncatogarized/cleaning-branch-independent-issues-plan.md` → `v0.1.11-unification-era/project-hygiene/cleaning-branch-independent-issues-plan.md`
- `specs/uncatogarized/independent-issues-batch/` → `v0.1.11-unification-era/project-hygiene/independent-issues-batch/`
- `reviews/three-way-merge-analysis.md` → `v0.1.11-unification-era/project-hygiene/three-way-merge-analysis.md`

**release/**
- `reviews/v0.1.11/` → `v0.1.11-unification-era/release/v0.1.11/`

##### v0.1.12 项目治理时代

**issue-system/**
- `plans/uncatogarized/issue-system-refactor-plan.md` → `v0.1.12-governance-era/issue-system/issue-system-refactor-plan.md`
- `plans/uncatogarized/issue_system_design.md` → `v0.1.12-governance-era/issue-system/issue_system_design.md`
- `specs/uncatogarized/implement-issue-system/` → `v0.1.12-governance-era/issue-system/implement-issue-system/`
- `.archive/issue-system-dev-notes.md` → `v0.1.12-governance-era/issue-system/issue-system-dev-notes.md`

**project-governance/**
- `specs/uncatogarized/define-custom-exceptions/` → `v0.1.12-governance-era/project-governance/define-custom-exceptions/`
- `specs/uncatogarized/todo-backlog-cleanup/` → `v0.1.12-governance-era/project-governance/todo-backlog-cleanup/`
- `specs/uncatogarized/refactor-codebase-health/` → `v0.1.12-governance-era/project-governance/refactor-codebase-health/`
- `plans/uncatogarized/rf009-progressive-disclosure-plan.md` → `v0.1.12-governance-era/project-governance/rf009-progressive-disclosure-plan.md`
- `reviews/investigations/ruff-experience-and-best-practices.md` → `v0.1.12-governance-era/project-governance/ruff-experience-and-best-practices.md`
- `reviews/investigations/rf-002-project-structure.md` → `v0.1.12-governance-era/project-governance/rf-002-project-structure.md`
- `reviews/investigations/inv-021-file-path-security.md` → `v0.1.12-governance-era/project-governance/inv-021-file-path-security.md`
- `reviews/issues/feat-028-config-validation.md` → `v0.1.12-governance-era/project-governance/feat-028-config-validation.md`
- `.archive/backlog-2026-04-28.md` → `v0.1.12-governance-era/project-governance/backlog-2026-04-28.md`

**code-quality/**
- `reviews/investigations/inv-017-boundary-condition-test-coverage.md` → `v0.1.12-governance-era/code-quality/inv-017-boundary-condition-test-coverage.md`
- `reviews/investigations/inv-018-exception-path-test-coverage.md` → `v0.1.12-governance-era/code-quality/inv-018-exception-path-test-coverage.md`
- `reviews/investigations/inv-019-test-parallelization.md` → `v0.1.12-governance-era/code-quality/inv-019-test-parallelization.md`

**project-memory/**
- `plans/uncatogarized/v0.1.9/plan-project-memory-skill.md` → `v0.1.12-governance-era/project-memory/plan-project-memory-skill.md`

**release/**
- (v0.1.12 无独立验收报告目录)

##### v0.1.13 RAG 可视化时代

**visualization/**
- `plans/uncatogarized/streamlit-web-demo-plan.md` → `v0.1.13-visualization-era/visualization/streamlit-web-demo-plan.md`
- `specs/uncatogarized/streamlit-web-demo/` → `v0.1.13-visualization-era/visualization/streamlit-web-demo/`
- `.archive/pdf-preview-lightweight-plan.md` → `v0.1.13-visualization-era/visualization/pdf-preview-lightweight-plan.md`
- `reviews/sessions/streamlit-web-demo-session.md` → `v0.1.13-visualization-era/visualization/streamlit-web-demo-session.md`

**experiment-framework/**
- `plans/uncatogarized/solid-rag-baseline-optimization-plan.md` → `v0.1.13-visualization-era/experiment-framework/solid-rag-baseline-optimization-plan.md`
- `reviews/issues/feat-014-transparent-report.md` → `v0.1.13-visualization-era/experiment-framework/feat-014-transparent-report.md`

**release/**
- (v0.1.13 无独立验收报告目录)

##### cross-version/ 跨版本

**general-research/**
- `reviews/rag-pipeline-research.md` → `cross-version/general-research/rag-pipeline-research.md`

##### 保留原位

- `.archive/README.md` — 重写
- `.archive/archive-log.md` — 保留
- `.archive/timeline.md` — 新增

##### 清空的旧目录

移动完成后，以下目录将被清空并删除：
- `plans/uncatogarized/`（含 `v0.1.9/` 子目录）
- `specs/uncatogarized/`（含 `v0.1.9/` 和 `v0.1.8/` 子目录）
- `reviews/`（所有子目录和文件已移入版本目录）
- `troubleshooting/`（所有文件已移入版本目录）

#### 2.2.3 新增 timeline.md

创建 `.archive/timeline.md`，作为归档区的叙事导览：

```markdown
# 项目演进时间线

> 每个版本都是一圈"年轮"。这里是项目博物馆的导览图。

## 时间线总览

| 版本 | 日期 | 主题 | 一句话叙事 | 关键目录 |
|------|------|------|-----------|---------|
| v0.1.0 | 04-15 | MVP 基础链路 | 从零到一 | mvp-era/mvp-pipeline/ |
| v0.1.1~5 | 04-16 | MVP+评测+自动化 | 有了能跑的系统 | mvp-era/ |
| v0.1.6 | 04-18 | 项目卫生 | 有了规矩 | hygiene-era/ |
| v0.1.7 | 04-19 | 评测增强 | 有了更准的尺子 | evaluation-era/ |
| v0.1.8 | 04-20 | TestSet 管理 | 有了独立的测试集 | testset-era/ |
| v0.1.9 | 04-21 | 评测双引擎 | 有了可信的尺子 | dual-eval-era/ |
| v0.1.10 | 04-22 | 解析新纪元 | 有了自由的源头 | parsing-era/ |
| v0.1.11 | 04-26 | 链路统一 | 有了统一的基准 | unification-era/ |
| v0.1.12 | 04-28 | 项目治理 | 有了可持续的节奏 | governance-era/ |
| v0.1.13 | 04-28 | RAG 可视化 | 有了可展示的产品 | visualization-era/ |

## 各版本详情

### v0.1.0~v0.1.5 — MVP 时代
> 从一个空 repo 到能跑的 RAG 系统

**核心叙事**：...

**主题目录**：
- [mvp-pipeline/](v0.1.0-v0.1.5-mvp-era/mvp-pipeline/) — 初始 RAG 链路
- [meal-system/](v0.1.0-v0.1.5-mvp-era/meal-system/) — 数据管理
- ...

### v0.1.9 — 评测双引擎
> 你没法改进你量不准的东西

**核心叙事**：...

**主题目录**：
- [ragas-integration/](v0.1.9-dual-eval-era/ragas-integration/) — RAGAS 框架集成
- [evaluation-fixes/](v0.1.9-dual-eval-era/evaluation-fixes/) — 评测链路修复
- ...
```

#### 2.2.4 重写 .archive/README.md

```markdown
# 项目博物馆

这里存放着项目从 git init 以来的所有开发痕迹——计划、规范、验收、调研、故障排查。

## 如何浏览

1. **时间线导览**：[timeline.md](timeline.md) — 按版本浏览项目演进
2. **按版本浏览**：每个 `v0.1.X-xxx-era/` 目录对应一个版本的开发痕迹
3. **按主题浏览**：每个版本目录下按功能主题分组（如 ragas-integration/、parsing-pipeline/）

## 目录结构

每个版本目录下的主题子目录可能包含：
- 计划文档（原 TRAE /plan 模式产出）
- 规范文档（原 TRAE /spec 模式产出，含 spec.md + tasks.md + checklist.md）
- 验收报告（code-review、outcome、next-direction）
- 调研报告、会话记录、故障排查

不再区分 plan 和 spec，同一功能的文档放在一起。
```

### Phase 3：docs 根目录文档调整

| 文件 | 操作 | 说明 |
|------|------|------|
| `README.md` | **完全重写** | 三通道导航门面 |
| `getting-started.md` | 修复链接 | 4 处失效链接 |
| `version-history.md` | 修复链接 | 6 处失效链接 |
| `methodology.md` | 修复链接+更新引用 | 4 处失效链接 + backlog.md → .issues/ |
| `dev-story.md` | 保持不变 | 高质量内容 |

#### README.md 重写要点

1. **项目一句话介绍** — 金融研报 RAG 问答系统
2. **三通道导航**
   - 👤 用户通道 → user-guides/
   - 🔧 开发者通道 → dev-guides/
   - 🏛️ 项目博物馆 → .archive/timeline.md
3. **亮点文档推荐** — dev-story.md、version-history.md
4. **目录结构图** — 反映真实当前结构
5. **文档规范** — 命名规范和状态标签

### Phase 4：全面修复失效链接

**策略**：先完成所有文件移动，再根据语义逐一修复链接。

#### 修复规则

| 场景 | 修复方式 |
|------|---------|
| 目标在 user-guides/ | 同目录用 `filename.md`，跨目录用 `../user-guides/filename.md` |
| 目标在 dev-guides/ | 同目录用 `filename.md`，跨目录用 `../dev-guides/filename.md` |
| 目标在 docs/ 根目录 | 从子目录用 `../filename.md` |
| 目标已归档 | 指向 `.archive/v0.1.X-xxx-era/topic/` 新路径 |
| 目标不存在（如 backlog.md） | 保留文字，删除链接语法，加注释说明变迁 |
| 目标不存在（如 .trae/specs/） | 在 .archive/ 中查找对应 spec，指向新路径 |

#### 修复批次

1. **README.md** — 完全重写，所有链接自然正确
2. **根目录文档** — getting-started.md、version-history.md、methodology.md
3. **user-guides/** — config-reference.md（5处）、evaluation-metrics.md（3处）、question-generation.md（2处）、pdf-parsing.md（2处）、其他各1~2处
4. **dev-guides/** — testing.md（2处）、architecture.md（2处）、release-cadence.md（1处）、其他
5. **.archive/ 内部** — 归档文档交叉引用

### Phase 5：验证与收尾

1. **链接验证**：脚本扫描所有 markdown，确认零失效链接
2. **目录结构验证**：确认 README.md 目录树与实际一致
3. **CLAUDE.md 同步**：更新 CLAUDE.md 中引用的文档路径
4. **内容抽检**：抽查 5+ 文档，确认链接可点击

---

## 三、执行顺序与提交策略

```
Phase 1: 活跃文档分类调整
  → commit: "refactor: reclassify docs between user-guides and dev-guides"

Phase 2: 归档目录全面重组（最大工作量）
  Step 2a: 创建版本目录结构
  Step 2b: 移动 plans/uncatogarized/ 文件到版本目录
  Step 2c: 移动 specs/uncatogarized/ 文件到版本目录
  Step 2d: 移动 reviews/ 文件到版本目录
  Step 2e: 移动 troubleshooting/ 文件到版本目录
  Step 2f: 移动散落文件到版本目录
  Step 2g: 删除空目录（uncatogarized/、旧的 reviews/、troubleshooting/）
  Step 2h: 创建 timeline.md
  Step 2i: 重写 README.md
  → commit: "docs: restructure archive by version and narrative theme"

Phase 3: 根目录文档
  → commit: "docs: rewrite README and fix root-level doc links"

Phase 4: 链接修复
  → commit: "docs: fix all broken links in user-guides"
  → commit: "docs: fix all broken links in dev-guides"
  → commit: "docs: fix broken links in archive docs"

Phase 5: 验证
  → commit: "docs: verify and finalize documentation restructure"
```

---

## 四、风险与注意事项

1. **git mv**：使用 `git mv` 保留文件历史追踪
2. **归档内部链接**：归档文档之间可能有交叉引用，移动后需修复
3. **CLAUDE.md 同步**：CLAUDE.md 引用了 `docs/guides/<feature>.md` 和 `docs/troubleshooting/`，需更新
4. **跨版本文件归属**：部分文件跨越多个版本（如 golden-test-set-150.md 从 v0.1.9 规划到 v0.1.11 交付），按"主要贡献版本"归属
5. **.archive 隐藏属性**：以 `.` 开头，GitHub 默认不显眼，适合"博物馆"定位

---

## 五、预期成果

```
docs/
├── README.md                    # 🚪 门面 — 三通道导航
├── getting-started.md           # ⚡ 快速上手
├── version-history.md           # 📜 版本年轮
├── methodology.md               # 🧠 方法论
├── dev-story.md                 # ✍️ 开发随笔
│
├── user-guides/                 # 👤 用户通道（15 篇）
├── dev-guides/                  # 🔧 开发者通道（7~8 篇）
│
└── .archive/                    # 🏛️ 项目博物馆
    ├── README.md                # 博物馆指南
    ├── timeline.md              # 时间线导览
    ├── archive-log.md
    │
    ├── v0.1.0-v0.1.5-mvp-era/
    │   ├── mvp-pipeline/
    │   ├── meal-system/
    │   ├── testset-generation/
    │   ├── experiment-framework/
    │   ├── token-tracking/
    │   ├── code-quality/
    │   ├── dependency-fixes/
    │   └── release/
    │
    ├── v0.1.6-hygiene-era/
    ├── v0.1.7-evaluation-era/
    ├── v0.1.8-testset-era/
    ├── v0.1.9-dual-eval-era/
    ├── v0.1.10-parsing-era/
    ├── v0.1.11-unification-era/
    ├── v0.1.12-governance-era/
    ├── v0.1.13-visualization-era/
    └── cross-version/
```

**不同受众的体验**：

| 受众 | 入口 | 体验 |
|------|------|------|
| 普通用户 | README → user-guides/ | 15 篇精选指南，零噪音 |
| 开发者 | README → dev-guides/ | 架构、测试、规范，直入技术 |
| 项目历史爱好者 | README → .archive/timeline.md | 按版本浏览，每版有故事、有文档 |
| 面试官/简历审阅者 | README → dev-story.md + version-history.md | 人文+技术双线叙事 |
