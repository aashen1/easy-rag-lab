# docs/archive 目录整理计划

> 这个其实应该没有那么早，从内容能看出是新 issue 系统引入之后的一次重构，大概是.11和.12版本左右的。不过AI放这了，也就放这吧。

## 问题诊断

当前 `docs/archive/` 存在 **95 个 .md 文件**，分布在 **20+ 个子目录**中，核心问题：

| # | 问题 | 严重度 |
|---|------|--------|
| 1 | **内容重复**：`.trae-docs/` 4 个文件与 `trae-plans/`/`trae-reports/` 完全重复；`测试覆盖增强计划.md` 与 `test-coverage-enhancement-plan.md` 重复 | 高 |
| 2 | **中文文件名**：9 个文件使用中文命名，违反项目规范 | 高 |
| 3 | **同类内容分散**：`specs/` 和 `trae-specs/` 是同一类内容；`trae-documents/` 和 `trae-plans/` 都是计划类文档 | 中 |
| 4 | **来源痕迹残留**：`.trae-docs/` 是首批归档未清理的残留；`trae-documents/` 与 `trae-plans/` 边界模糊 | 中 |
| 5 | **spec 嵌套混乱**：`trae-documents/specs/` 内嵌套了 spec 三件套，与 `specs/` 和 `trae-specs/` 同类 | 低 |

## 目标结构

```
docs/archive/
├── archive-log.md                       ← 保留根目录
├── idea-ai-era-git-practice.md          ← 理念文档，保留根目录
│
├── plans/                               ← 合并 trae-documents/ + trae-plans/ + 根目录散落计划
│   ├── v0.1.8/                          ← v0.1.8 相关计划
│   │   ├── v0.1.8-merge-and-release-plan.md
│   │   └── v0.1.8-release-plan-rag-enhancement-verification.md
│   ├── v0.1.9/                          ← v0.1.9 相关已完成计划
│   │   ├── artifact-path-migration-plan.md
│   │   ├── bug-024-chunk-encoding-fix.md
│   │   ├── eval-metrics-fix-and-enhancement.md
│   │   ├── experiment-report-metrics-fix-plan.md
│   │   ├── fix-evaluation-bugs.md
│   │   ├── fix-golden-testset-generation.md
│   │   ├── fix-hybrid-ground-truth-excerpt.md
│   │   ├── golden-test-set-150.md
│   │   ├── issue-fix-plan.md
│   │   ├── plan-project-memory-skill.md
│   │   ├── safe-issue-cleanup-plan.md
│   │   ├── test-coverage-enhancement-plan.md
│   │   └── unify-golden-testset-generation.md
│   ├── documents-refactor/              ← 文档管理重构
│   │   ├── docs-management-plan.md
│   │   ├── docs-management-refactoring-plan.md
│   │   └── docs-management-refactoring-requirements.md
│   ├── backlog-cleanup-plan.md
│   ├── cleanup-and-backlog-review-plan.md
│   ├── downstream-pipeline-adaptation-plan.md
│   ├── eval-system-acceptance-fix.md
│   ├── eval-system-merge-cleanup-plan.md
│   ├── evaluation-system-integration-analysis-and-cleanup-plan.md
│   ├── experiment-metrics-bug-fix-plan.md
│   ├── experiment-report-accuracy-improvement-plan.md
│   ├── feat-023-context-length-control.md
│   ├── fix-document-loader-multi-format.md
│   ├── housekeeping-and-backlog-review-plan.md
│   ├── independent-issues-for-current-tasks.md
│   ├── pdf2md-optimize-with-4llm-params.md
│   ├── pdf2md-stay-on-4llm-plan.md
│   ├── pdf2md-switch-to-fitz-plan.md
│   ├── plan-fix-independent-issues.md
│   ├── rag-eval-metrics-optimization-plan.md
│   ├── ragas-baseline-acceptance-plan.md
│   ├── ragas-integration-analysis.md
│   ├── ragas-integration-implementation-plan.md
│   ├── ragas-integration-plan.md
│   ├── ragas-metrics-improvement-plan.md
│   ├── ragas-metrics-review-plan.md
│   ├── rf-015-update-hyperparameter-guide.md
│   ├── rf009-progressive-disclosure-plan.md
│   ├── solid-rag-baseline-optimization-plan.md
│   ├── stream2-chunking-metrics-fixes.md
│   ├── testset-design-plan.md
│   ├── backlog-issue-assessment-and-fix-plan.md
│   ├── code-issues-fix-requirements.md
│   ├── exp-configs-analysis-and-improvement-plan.md
│   ├── high-priority-dev-directions.md
│   ├── implement-sampling-feature.md
│   ├── merge-conflict-resolution-plan.md
│   ├── project-status-after-merge.md
│   ├── replace-deprecated-ragas-api.md
│   ├── todo-archiver-mechanism-plan.md
│   └── token-tracking-feature.md
│
├── reports/                             ← 合并 trae-reports/ + 调研文档
│   ├── baseline-evaluation-deep-inspection-report.md
│   ├── merge-conflict-analysis-2026-04-23.md
│   ├── merge-conflict-analysis.md
│   ├── three-way-merge-analysis.md
│   ├── v019-priority-issues-deep-analysis.md
│   └── rag-pipeline-research.md
│
├── specs/                               ← 合并 specs/ + trae-specs/ + trae-documents/specs/
│   ├── v0.1.9/                          ← v0.1.9 已完成 spec
│   │   ├── add-unified-document-loader/
│   │   ├── fix-cache-pollution-risks/
│   │   └── hybrid-question-generation-strategy/
│   ├── add-fitz-pdfplumber-parser-pipeline/
│   ├── automate-evaluation/
│   ├── code-quality-fixup/
│   ├── define-custom-exceptions/
│   ├── eval-system-cleanup/
│   ├── fix-baseline-evaluation-issues/
│   ├── fix-eval-try-round-2/
│   ├── fix-evaluation-granularity/
│   ├── fix-pipeline-audit-issues/
│   ├── independent-issues-batch/
│   ├── known-bugs-fixup/
│   ├── meal-extension-and-testset-merge/
│   ├── new-evaluation-system/
│   ├── optimize-pymupdf4llm-params/
│   ├── start/
│   ├── stream2-chunking-metrics-fixes/
│   ├── test-review-fixup/
│   ├── test-suite-redesign/
│   └── todo-backlog-cleanup/
│
├── flagembedding-to-transformers/       ← 保留，主题独立
│   ├── transformers-compatibility-issue.md
│   └── transformers-compatibility-issue-reply.md
│
├── meal/                                ← 保留，主题独立
│   ├── meal-feature-plan.md
│   └── meal-identity-refactoring-plan.md
│
└── test-suite-analysis/                 ← 保留，主题独立
    ├── test-coverage-guide.md
    ├── test-future-directions.md
    ├── test-review-suggestions.md
    ├── test-suite-analysis.md
    ├── test-suite-design.md
    └── test-suite-redesign-response.md
```

## 执行步骤

### Step 1: 创建目标目录结构

创建 `plans/`、`plans/v0.1.8/`、`plans/v0.1.9/`、`plans/documents-refactor/`、`reports/` 目录。

### Step 2: 删除重复文件

移入 `.trashbin/`：
- `.trae-docs/` 整个目录（4 个文件与 `trae-plans/`/`trae-reports/` 重复）
- `trae-documents/v0.1.9-completed-plans/测试覆盖增强计划.md`（与英文版重复）

### Step 3: 中文文件名重命名为英文

| 当前路径 | 新文件名 |
|---------|---------|
| `trae-plans/评估积压 Issue 及修复计划.md` | `backlog-issue-assessment-and-fix-plan.md` |
| `trae-documents/v0.1.8 Release Plan - RAG 增强功能全链路验证.md` | `v0.1.8-release-plan-rag-enhancement-verification.md` |
| `specs/fix-eval-try-round-2/RAG评测系统修复-spec.md` | `spec.md` |
| `specs/fix-eval-try-round-2/RAG评测系统修复-checklist.md` | `checklist.md` |
| `specs/fix-eval-try-round-2/RAG评测系统修复-tasks.md` | `tasks.md` |
| `specs/fix-eval-try-round-2/RAG评测系统问题分析.md` | `problem-analysis.md` |
| `trae-documents/documents-refactor/文档管理重构计划.md` | `docs-management-refactoring-plan.md` |
| `trae-documents/documents-refactor/文档管理重构需求文档.md` | `docs-management-refactoring-requirements.md` |
| `trae-documents/Evaluation_System_Integration_Analysis_and_Cleanup_Plan.md` | `evaluation-system-integration-analysis-and-cleanup-plan.md` |
| `trae-documents/exp_configs_analysis_and_improvement_plan.md` | `exp-configs-analysis-and-improvement-plan.md` |
| `trae-documents/fix_hybrid_ground_truth_excerpt.md` | `fix-hybrid-ground-truth-excerpt.md` |

### Step 4: 合并 plans — 移动 trae-plans/ 文件到 plans/

将 `trae-plans/` 下所有文件移动到 `plans/` 对应位置：
- 19 个文件移入 `plans/` 根级
- 其中 v0.1.8 相关的 2 个文件移入 `plans/v0.1.8/`

### Step 5: 合并 plans — 移动 trae-documents/ 文件到 plans/

将 `trae-documents/` 下的计划文件移动到 `plans/` 对应位置：
- 顶层 19 个 .md 文件移入 `plans/` 根级（排除已在 v0.1.9 子目录中的）
- `v0.1.9-completed-plans/` 下 13 个文件移入 `plans/v0.1.9/`
- `documents-refactor/` 下 3 个文件移入 `plans/documents-refactor/`

### Step 6: 移动根目录散落计划文件到 plans/

- `code-issues-fix-requirements.md` → `plans/`
- `implement-sampling-feature.md` → `plans/`
- `token-tracking-feature.md` → `plans/`

### Step 7: 合并 reports — 移动 trae-reports/ + 调研文档到 reports/

- `trae-reports/` 下 4 个文件移入 `reports/`
- `trae-documents/merge-conflict-analysis.md` 移入 `reports/`
- 根目录 `rag-pipeline-research.md` 移入 `reports/`

### Step 8: 合并 specs — 移动 trae-specs/ 和 trae-documents/specs/ 到 specs/

- `trae-specs/` 下 8 个子目录移入 `specs/`
- `trae-specs/v0.1.9-completed-specs/` 下 3 个子目录移入 `specs/v0.1.9/`
- `trae-documents/specs/eval-system-cleanup/` 移入 `specs/`

### Step 9: 重命名 flagembedding_to_transformers/ 目录

`flagembedding_to_transformers/` → `flagembedding-to-transformers/`（连字符风格统一）

### Step 10: 清理空目录

移入 `.trashbin/`：
- `trae-plans/`（已搬空）
- `trae-reports/`（已搬空）
- `trae-specs/`（已搬空）
- `trae-documents/`（已搬空）

### Step 11: 更新 archive-log.md

在 archive-log.md 末尾追加本次整理记录，包括：
- 整理日期
- 目录结构变更说明
- 删除的重复文件列表
- 重命名的文件列表

### Step 12: 更新 docs/README.md

更新 README.md 中 archive 部分的目录结构描述，使其与新的目录结构一致。

## 文件操作汇总

| 操作类型 | 数量 |
|---------|------|
| 移动文件 | ~70 |
| 重命名文件 | ~11 |
| 删除重复（移入 .trashbin） | ~5 |
| 创建目录 | ~5 |
| 更新文档 | 2 |

## 风险与注意事项

1. **git 历史**：文件移动后 git 会丢失跟踪，但 archive 目录是历史归档，不需要频繁 diff，可接受
2. **内部链接**：archive 内的 .md 文件可能互相引用，移动后链接会失效。但 archive 是只读历史，链接失效影响有限
3. **外部引用**：`docs/README.md` 引用了 archive 目录结构，需要同步更新
4. **逐步提交**：每个 Step 完成后立即 commit，确保原子性
