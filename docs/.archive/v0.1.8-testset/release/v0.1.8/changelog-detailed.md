# v0.1.8 Detailed Changelog

> This document provides comprehensive details of all changes in v0.1.8.
> For a concise summary, see [release-summary.md](./release-summary.md).

---

## New Evaluation Metrics

### Context Precision

- **File**: `eval/metrics.py`
- **Description**: Measures how well the retrieved context supports the generated answer
- **Implementation**: Uses LLM to evaluate each retrieved chunk's relevance to the ground truth answer
- **Test Coverage**: `tests/test_metrics.py` (+845 lines total for all new metrics)
- **Integration**: Added to `eval/run_eval.py` and experiment pipeline

### Context Recall

- **File**: `eval/metrics.py`
- **Description**: Measures how much of the ground truth answer is covered by the retrieved context
- **Implementation**: Uses LLM to verify if ground truth statements can be derived from context
- **Test Coverage**: Included in `tests/test_metrics.py`
- **Integration**: Added to evaluation pipeline and experiment reporter

### Chunk-level Retrieval Metrics

- **File**: `eval/metrics.py`, `eval/run_experiment.py`
- **Description**: Evaluates retrieval at chunk granularity instead of document level
- **Use Case**: Fine-grained analysis of retrieval quality
- **Integration**: Added to experiment report configuration and output

### Dedup Metrics

- **File**: `eval/metrics.py`
- **Description**: Measures how well the system avoids retrieving duplicate or near-duplicate chunks
- **Use Case**: Evaluating deduplication effectiveness in retrieval pipeline

### False Positive Rate (FPR)

- **File**: `eval/metrics.py`
- **Description**: Tracks the rate of incorrectly retrieved chunks
- **Use Case**: Identifying over-retrieval or irrelevant retrievals

### NDCG Deduplication Fix

- **File**: `eval/metrics.py`
- **Bug**: NDCG calculation did not account for duplicate sources, causing values to exceed [0,1]
- **Fix**: Added deduplication logic before NDCG computation
- **Test**: Added test cases in `tests/test_metrics.py` to verify [0,1] constraint

---

## Equivalence Group Support

### Meal Building Enhancement

- **File**: `src/meal.py`
- **Change**: Added equivalence group inference during meal building
- **Purpose**: Groups semantically equivalent chunks for more accurate evaluation

### Query Method Update

- **File**: `src/pipeline.py`
- **Change**: Query method now returns `chunk_ids` field
- **Purpose**: Enables tracking of which specific chunks were retrieved

### Metric Normalization

- **File**: `eval/metrics.py`
- **New Function**: `normalize_source_with_equivalence()`
- **Purpose**: Normalizes retrieved sources using equivalence groups
- **Use Case**: Prevents penalizing systems that retrieve equivalent but differently-worded chunks

### Experiment Runner Integration

- **File**: `eval/run_experiment.py`
- **Change**: `evaluate_test_set()` now supports equivalence group awareness
- **Test**: Added unit tests for equivalence group support in `tests/test_metrics.py`

---

## TestSetManager System

### New Module: src/test_set_manager.py

**TestSetMetadata Dataclass**:
- `name`: Test set identifier
- `meal_id`: Associated meal ID
- `question_count`: Number of questions
- `question_types`: Distribution of question types
- `created_at`: Creation timestamp
- `source_documents`: Source document references

**TestSetManager Class**:
- `validate_test_set()`: Validates test set structure and content
- `_update_meal_id()`: Updates meal ID association
- `resolve_test_set()`: Resolves test set with on_missing routing logic
- `_clean_user_test_set()`: Cleans user-defined test sets
- `_clean_machine_test_set()`: Cleans machine-generated test sets

**Configuration Support**:
- New `test_sets` configuration format in `config.yaml`
- Deprecation warning for old format
- Automatic migration logic

### Test Coverage: tests/test_test_set_manager.py

- 1825 lines of comprehensive unit tests
- Covers all public methods and edge cases
- Tests configuration parsing and validation
- Tests migration from old format

### Integration

- **File**: `eval/run_experiment.py`
- **Change**: Refactored to use TestSetManager for test set lifecycle
- **Benefit**: Better separation of concerns, cleaner code

---

## Experiment Configuration Restructure

### New Directory Structure

```
exp_configs/
├── baseline/
│   ├── baseline_10percent.yaml    (renamed from baseline.yaml)
│   └── baseline_5kpage.yaml       (new)
├── experiments/
│   ├── chunk_comparison.yaml      (moved)
│   ├── chunking_strategy_comparison.yaml  (moved)
│   ├── query_rewrite_comparison.yaml      (moved)
│   ├── reranker_comparison.yaml           (moved)
│   ├── retrieval_comparison.yaml          (moved)
│   └── strategy_comparison.yaml           (moved, updated)
├── golden_tests/
│   └── golden_test.yaml           (moved)
├── smoke_tests/
│   ├── smoke_full.yaml            (moved from chunk_smoke_test.yaml)
│   └── smoke_quick.yaml           (moved)
└── templates/
    ├── _complete.yaml             (new - full configuration template)
    ├── _minimal.yaml              (updated - minimal template)
    ├── _preset_chunk.yaml         (new - chunking presets)
    ├── _preset_reranker.yaml      (new - reranker presets)
    └── _preset_retrieval.yaml     (new - retrieval presets)
```

### File Mapping Table

| Old Path | New Path | Notes |
|----------|----------|-------|
| `exp_configs/baseline.yaml` | `exp_configs/baseline/baseline_10percent.yaml` | Renamed |
| `exp_configs/chunk_smoke_test.yaml` | `exp_configs/smoke_tests/smoke_full.yaml` | Moved + renamed |
| `exp_configs/golden_test.yaml` | `exp_configs/golden_tests/golden_test.yaml` | Moved |
| `exp_configs/strategy_comparison.yaml` | `exp_configs/experiments/strategy_comparison.yaml` | Moved |
| `exp_configs/chunk_comparison.yaml` | `exp_configs/experiments/chunk_comparison.yaml` | Moved |
| `exp_configs/reranker_comparison.yaml` | `exp_configs/experiments/reranker_comparison.yaml` | Moved |
| `exp_configs/retrieval_comparison.yaml` | `exp_configs/experiments/retrieval_comparison.yaml` | Moved |
| `exp_configs/quicktest111_v01x.yaml` | *(deleted)* | Removed obsolete file |

---

## Experiment Report Enhancements

### Technology Summary

- **File**: `eval/experiment_reporter.py`
- **Change**: Added technology summary section to generated reports
- **Content**: Lists technologies and configurations used in experiment

### YAML Rendering

- **File**: `eval/experiment_reporter.py`
- **Change**: Improved YAML rendering for better readability
- **Benefit**: Clearer configuration display in reports

### Full Config Snapshot

- **File**: `eval/run_experiment.py`
- **Change**: Saves complete merged configuration to experiment snapshots
- **Benefit**: Full reproducibility of experiment conditions

### LLM Retrieval Metrics

- **File**: `eval/experiment_reporter.py`
- **Change**: Reporter now displays LLM-based retrieval metrics
- **Metrics**: Context Precision, Context Recall

---

## Question Generation Improvements

### source_chunks Field

- **File**: `src/test_generator.py`
- **Change**: Added `source_chunks` field to document-level question generation
- **Purpose**: Tracks which chunks were used to generate each question

### Incremental Generation

- **File**: `src/test_generator.py`
- **Bug**: Question generation did not reach target num_questions
- **Fix**: Distributes questions across documents and supplements existing test sets
- **Benefit**: Ensures target question count is met

### Question Validity Check

- **File**: `eval/metrics.py`, `src/test_generator.py`
- **New Feature**: Question validity checking functionality
- **Purpose**: Filters out unanswerable or poorly-formed questions
- **Refactor**: Removed old `validate_question` and `filter_valid_questions` functions

### source_files Fix

- **File**: `src/test_generator.py`
- **Bug**: irrelevant/missing question types had incorrect source_files
- **Fix**: Corrected source_files assignment for these question types

---

## Bug Fixes

### NDCG Out of Range

- **Severity**: High
- **Root Cause**: Duplicate sources in retrieval not accounted for
- **Fix**: Added deduplication before NDCG calculation
- **Impact**: NDCG values now correctly bounded to [0,1]
- **Test**: Added test cases in `tests/test_metrics.py`

### Chunker Config Hash Missing Parameters

- **Severity**: Medium
- **Root Cause**: `strategy` and `semantic` parameters not included in config hash
- **Impact**: Different chunking strategies could produce cache collisions
- **Fix**: Updated hash computation to include all relevant parameters
- **File**: `src/experiment.py`

### Question Generation Shortfall

- **Severity**: Medium
- **Root Cause**: Questions distributed per-document instead of across all documents
- **Impact**: Total question count could be less than target
- **Fix**: Changed distribution logic to aggregate across documents
- **File**: `src/test_generator.py`

---

## Documentation Updates

### New Documentation

- `docs/guides/test-set-management.md` - Test set management guide
- `docs/troubleshooting/eval-metrics-bugfix.md` - Evaluation metrics bugfix documentation
- `docs/troubleshooting/eval-system-acceptance-fix.md` - Evaluation system acceptance fix guide

### Updated Documentation

- `docs/guides/evaluation-metrics.md` - Added new metrics documentation
- `docs/config-reference.md` - Updated for new configuration structure
- `docs/version-history.md` - Updated with v0.1.8 summary
- `docs/backlog.md` - Updated task status
- `exp_configs/README.md` - Updated for new directory structure
