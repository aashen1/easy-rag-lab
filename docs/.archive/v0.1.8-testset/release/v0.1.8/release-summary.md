# v0.1.8 Release Summary

<!-- status: active -->

> Release date: 2026-04-20
> Branch merged: `fix-eval` -> `dev`

---

## Version Theme

Evaluation system reliability improvements and TestSetManager architecture.

---

## Key Changes

### 1. New Evaluation Metrics

- **Context Precision**: Measures how well the retrieved context supports the answer
- **Context Recall**: Measures how much of the ground truth is covered by retrieved context
- **Chunk-level Retrieval Metrics**: Fine-grained evaluation at chunk granularity
- **Dedup Metrics**: Measures retrieval deduplication effectiveness
- **False Positive Rate (FPR)**: Tracks incorrect retrieval hits
- **NDCG Deduplication Fix**: Ensures NDCG values stay within [0,1] range

### 2. Equivalence Group Support

- Automatic equivalence group inference during meal building
- Query method now returns `chunk_ids` for equivalence tracking
- Metric normalization with equivalence group awareness
- Supports semantic equivalence in test set evaluation

### 3. TestSetManager System

- **New Module**: `src/test_set_manager.py` (911 lines)
- **TestSetMetadata**: Structured metadata for test sets
- **New Configuration Format**: `test_sets` section with automatic migration
- **Lifecycle Management**: Validation, cleaning, and resolution methods
- **Backward Compatibility**: Old format supported with deprecation warning
- **Complete Test Coverage**: 1825 lines of unit tests

### 4. Experiment Configuration Restructure

- **New Structure**:
  - `exp_configs/baseline/` - Baseline configurations
  - `exp_configs/experiments/` - Comparison experiment configurations
  - `exp_configs/golden_tests/` - Golden test configurations
  - `exp_configs/smoke_tests/` - Smoke test configurations
  - `exp_configs/templates/` - Template configurations (_complete, _minimal, _preset_*)
- **Template System**: Reusable configuration presets for chunk, reranker, and retrieval

### 5. Experiment Report Enhancements

- Technology summary in generated reports
- Improved YAML rendering
- Full merged config saved in experiment snapshots
- LLM-based retrieval metrics displayed in reports

### 6. Question Generation Improvements

- `source_chunks` field added to document-level questions
- Incremental test set generation to reach target count
- Question validity checking functionality
- Fixed source_files for irrelevant/missing question types

---

## Statistics

| Metric | Value |
|--------|-------|
| New files | 12 |
| Modified files | 46 |
| Lines added | +10,736 |
| Lines removed | -475 |
| New test cases | ~3,000 |
| New metrics | 5 (Context Precision, Context Recall, Chunk-level, Dedup, FPR) |
| New modules | 1 (TestSetManager) |

---

## Bug Fixes

1. **NDCG out of [0,1] range**: Added deduplication to NDCG calculation
2. **source_files error**: Fixed for irrelevant/missing question types in test generator
3. **Chunker config hash**: Now includes strategy and semantic parameters
4. **Question generation shortfall**: Ensures generation reaches target num_questions

---

## Migration Notes

### Configuration Changes

- `exp_configs/` directory structure has been reorganized
- Old configuration paths may need updating:
  - `exp_configs/baseline.yaml` -> `exp_configs/baseline/baseline_10percent.yaml`
  - `exp_configs/chunk_smoke_test.yaml` -> `exp_configs/smoke_tests/smoke_full.yaml`
  - `exp_configs/golden_test.yaml` -> `exp_configs/golden_tests/golden_test.yaml`
  - `exp_configs/strategy_comparison.yaml` -> `exp_configs/experiments/strategy_comparison.yaml`

### Test Set Configuration

- New `test_sets` format is now preferred
- Old format still works but shows deprecation warning
- See [Test Set Management Guide](../../guides/test-set-management.md) for migration instructions

---

## Detailed Documentation

- [Detailed Changelog](./changelog-detailed.md)
- [Migration Guide](./migration-guide.md)
- [Acceptance Report](./acceptance-report.md)

---

## Related Troubleshooting

- [Evaluation Metrics Bugfix](../../troubleshooting/eval-metrics-bugfix.md)
- [Evaluation System Acceptance Fix](../../troubleshooting/eval-system-acceptance-fix.md)
