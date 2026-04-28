# Known Bugs & Functional Issues Fixup Spec

## Why

The review document `.trae/code_reviews/v0.1.5/04-known-bugs-functional-issues.md` lists 13 known issues. Several are already fixed in code but not reflected in the document, while others remain unfixed. This spec covers verifying each issue, fixing what's reasonable, updating the review document, and marking the TODO item complete.

## What Changes

- Update issue #1 status to ✅ in review doc (code already has `normalize_source`)
- Update issue #13 status in review doc (test files now exist for all listed modules)
- **Fix issue #10**: Make `run_evaluation` dynamically apply metrics from experiment config instead of hardcoding hit_rate/mrr/ndcg
- **Fix issue #11**: Extract duplicated category detection logic from `parser.py` and `chunker.py` into a shared utility function
- **Fix issue #12**: Implement `show_progress` parameter in `Embedder.embed_texts()` using `tqdm`
- Update review document to reflect all fix decisions and current status
- Mark TODO.md line 77 as completed with timestamp

## Impact

- Affected code: `eval/run_eval.py`, `src/parser.py`, `src/chunker.py`, `src/embedder.py`, `src/utils.py`
- Affected docs: `.trae/code_reviews/v0.1.5/04-known-bugs-functional-issues.md`, `TODO.md`
- No breaking changes

## Won't Fix (with reasons)

### Issue #6: 测试数据占位符未填充
**Reason**: Requires manual data entry from actual PDF files. The placeholder values like "XXX亿元" need real financial data that can only be obtained by reading the source PDFs. Not automatable in this task.

### Issue #7: 生成质量指标未实现
**Reason**: Implementing Faithfulness and Answer Relevancy with ragas is a substantial feature addition requiring significant new code, integration, and testing. Scope is too large for this fixup task. Should be a separate spec.

### Issue #8: NDCG 简化实现
**Reason**: Binary relevance is sufficient for baseline evaluation. Implementing graded relevance would require defining relevance grades for each document-query pair, which adds complexity without clear benefit at the current stage. Over-engineering for MVP.

### Issue #9: Hit Rate 定义非标准
**Reason**: The current implementation computes Recall@K (proportion of expected documents found), which is actually more informative than the standard Hit Rate@K (binary: at least one hit or not). Renaming would break existing baseline comparisons. The naming discrepancy should be documented but the implementation kept as-is.

## ADDED Requirements

### Requirement: Dynamic Metric Configuration
The evaluation system SHALL dynamically apply retrieval metrics based on the experiment configuration's `evaluation.metrics.retrieval` list, rather than hardcoding the three metrics.

#### Scenario: Config specifies subset of metrics
- **WHEN** an experiment config specifies only `["hit_rate", "mrr"]` in `evaluation.metrics.retrieval`
- **THEN** only hit_rate and mrr are calculated and included in the evaluation report

#### Scenario: Config specifies all metrics
- **WHEN** an experiment config specifies `["hit_rate", "mrr", "ndcg"]`
- **THEN** all three metrics are calculated (same as current behavior)

#### Scenario: No config specified (backward compatibility)
- **WHEN** no metrics config is provided
- **THEN** all three default metrics are calculated (backward compatible)

### Requirement: Shared Category Detection Utility
The document category detection logic SHALL be extracted into a single shared function in `src/utils.py`, eliminating duplication between `parser.py` and `chunker.py`.

#### Scenario: Category detection from path
- **WHEN** a file path contains "annual_report" or "年报"
- **THEN** the function returns "annual_report"

#### Scenario: Research report detection
- **WHEN** a file path contains "research_report" or "研报"
- **THEN** the function returns "research_report"

#### Scenario: Unknown category
- **WHEN** a file path matches no known patterns
- **THEN** the function returns "unknown"

### Requirement: Embedder Progress Display
The `Embedder.embed_texts()` method SHALL display a progress bar when `show_progress=True` using the `tqdm` library.

#### Scenario: Progress display enabled
- **WHEN** `embed_texts(texts, show_progress=True)` is called with a large batch
- **THEN** a tqdm progress bar is displayed showing batch progress

#### Scenario: Progress display disabled (default)
- **WHEN** `embed_texts(texts)` is called without show_progress
- **THEN** no progress bar is displayed (current behavior preserved)

## MODIFIED Requirements

### Requirement: Review Document Status Accuracy
The review document `.trae/code_reviews/v0.1.5/04-known-bugs-functional-issues.md` SHALL accurately reflect the current fix status of all 13 issues, including:
- Issue #1: Mark as ✅ 已修复 (normalize_source already implemented)
- Issue #10: Mark as ✅ 已修复 (after dynamic metric fix)
- Issue #11: Mark as ✅ 已修复 (after utility extraction)
- Issue #12: Mark as ✅ 已修复 (after tqdm implementation)
- Issue #13: Update status to reflect test files now exist
- Issues #6, #7, #8, #9: Add "不修" status with reasons
