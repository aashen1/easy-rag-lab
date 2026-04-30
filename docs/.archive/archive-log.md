## 2026-04-21 — Archive 4 files
- housekeeping-and-backlog-review-plan.md
- independent-issues-for-current-tasks.md
- ragas-metrics-review-plan.md
- v019-priority-issues-deep-analysis.md

## 2026-04-24 — Archive .trae documents and specs

### Plans (docs/archive/trae-plans/)
- backlog-cleanup-plan.md
- downstream-pipeline-adaptation-plan.md
- experiment-report-accuracy-improvement-plan.md
- feat-023-context-length-control.md
- fix-document-loader-multi-format.md
- housekeeping-and-backlog-review-plan.md
- independent-issues-for-current-tasks.md
- pdf2md-optimize-with-4llm-params.md
- pdf2md-stay-on-4llm-plan.md
- pdf2md-switch-to-fitz-plan.md
- plan-fix-independent-issues.md
- ragas-baseline-acceptance-plan.md
- ragas-metrics-review-plan.md
- rf009-progressive-disclosure-plan.md
- rf-015-update-hyperparameter-guide.md
- solid-rag-baseline-optimization-plan.md
- stream2-chunking-metrics-fixes.md
- testset-design-plan.md
- backlog-issue-assessment-and-fix-plan.md

### Reports (docs/archive/trae-reports/)
- baseline-evaluation-deep-inspection-report.md
- merge-conflict-analysis-2026-04-23.md
- three-way-merge-analysis.md
- v019-priority-issues-deep-analysis.md

### Specs (docs/archive/trae-specs/)
- add-fitz-pdfplumber-parser-pipeline/
- define-custom-exceptions/
- fix-baseline-evaluation-issues/
- fix-pipeline-audit-issues/
- independent-issues-batch/
- meal-extension-and-testset-merge/
- optimize-pymupdf4llm-params/
- stream2-chunking-metrics-fixes/

## 2026-04-27 — Archive v0.1.9 completed plans and specs

### Plans (docs/archive/trae-documents/v0.1.9-completed-plans/)
- artifact-path-migration-plan.md (RF-020)
- bug-024-chunk-encoding-fix.md (BUG-024)
- golden-test-set-150.md (FEAT-031)
- issue-fix-plan.md (multiple issues)
- plan-project-memory-skill.md (FEAT-029)
- safe-issue-cleanup-plan.md (multiple issues)
- unify-golden-testset-generation.md (FEAT-031)
- test-coverage-enhancement-plan.md (TEST-001~008)
- eval-metrics-fix-and-enhancement.md
- experiment-report-metrics-fix-plan.md
- fix-evaluation-bugs.md (BUG-029/030/031)
- fix-golden-testset-generation.md
- fix-hybrid-ground-truth-excerpt.md

### Specs (docs/archive/trae-specs/v0.1.9-completed-specs/)
- add-unified-document-loader/
- fix-cache-pollution-risks/
- hybrid-question-generation-strategy/

## 2026-04-27 — Archive reorganization

### Summary
Reorganized archive directory from fragmented structure (6+ top-level directories with overlapping content) into 3 clean categories: `plans/`, `reports/`, `specs/`.

### Deleted (moved to .trashbin)
- `.trae-docs/` — 4 files duplicated in trae-plans/ and trae-reports/
- `测试覆盖增强计划.md` — already renamed to English version

### Renamed (Chinese → English, underscore → hyphen)
| Old name | New name |
|----------|----------|
| 评估积压 Issue 及修复计划.md | backlog-issue-assessment-and-fix-plan.md |
| v0.1.8 Release Plan - RAG 增强功能全链路验证.md | v0.1.8-release-plan-rag-enhancement-verification.md |
| RAG评测系统修复-spec.md | spec.md |
| RAG评测系统修复-checklist.md | checklist.md |
| RAG评测系统修复-tasks.md | tasks.md |
| RAG评测系统问题分析.md | problem-analysis.md |
| 文档管理重构计划.md | docs-management-refactoring-plan.md |
| 文档管理重构需求文档.md | docs-management-refactoring-requirements.md |
| Evaluation_System_Integration_Analysis_and_Cleanup_Plan.md | evaluation-system-integration-analysis-and-cleanup-plan.md |
| exp_configs_analysis_and_improvement_plan.md | exp-configs-analysis-and-improvement-plan.md |
| fix_hybrid_ground_truth_excerpt.md | fix-hybrid-ground-truth-excerpt.md |
| experiment_report_accuracy_improvement_plan.md | experiment-report-accuracy-improvement-plan.md |
| testset_design_plan.md | testset-design-plan.md |
| flagembedding_to_transformers/ | flagembedding-to-transformers/ |
| transformers_compatibility_issue.md | transformers-compatibility-issue.md |
| transformers_compatibility_issue_reply.md | transformers-compatibility-issue-reply.md |
| merge-conflict-analysis-2026-04-23-23-52.md | merge-conflict-analysis-2026-04-23.md |

### Directory merges
- `trae-plans/` + `trae-documents/` + root plans → `plans/`
  - v0.1.8 plans → `plans/v0.1.8/`
  - v0.1.9 plans → `plans/v0.1.9/`
  - documents-refactor → `plans/documents-refactor/`
- `trae-reports/` + research docs → `reports/`
- `trae-specs/` + `specs/` + `trae-documents/specs/` → `specs/`
  - v0.1.9 specs → `specs/v0.1.9/`

### Removed empty directories (moved to .trashbin)
- `trae-plans/`
- `trae-reports/`
- `trae-specs/`
- `trae-documents/`

### New directory structure
```

## 2026-05-01 — Archive v0.1.15 documents

### v0.1.15-experiment-acceleration-era/

#### release/
- v0.1.15/v0.1.15-release-verification-and-next-version-plan.md

#### experiment-runner/
- experiment-speed-optimization-and-checkpoint.md
- verify-baseline-code-health-fixes.md

#### webui-upgrade/
- fix-webui-controls/ (spec triplet + acceptance-report + fix-streamlit-ui-controls.md)

#### pipeline-refactor/
- config-hot-swap-architecture.md
- fix-dead-code-hybrid-topk-bm25-signature.md
- fix-query-rewrite-api-key-issue.md

#### evaluation-enhancement/
- golden-test-quality-polish.md
- reduce-proper-noun-false-positives.md
- evidence-validation-analysis.md

#### code-health/
- shit-mountain-fix-round2/ (spec triplet + shit-mountain-fix-plan.md)
- claude-md-length-optimization.md
- docs-deep-restructure-plan.md

### v0.1.14 补充
- v0.1.14-code-health-era/release/v0.1.14/v0.1.14-release-plan.md (原属 v0.1.14，误放在 .trae/documents/)
docs/archive/
├── archive-log.md
├── idea-ai-era-git-practice.md
├── plans/
│   ├── v0.1.8/
│   ├── v0.1.9/
│   └── documents-refactor/
├── reports/
├── specs/
│   └── v0.1.9/
├── flagembedding-to-transformers/
├── meal/
└── test-suite-analysis/
```
