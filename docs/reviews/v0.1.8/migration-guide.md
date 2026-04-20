# v0.1.8 Migration Guide

> This guide helps you migrate from v0.1.7 to v0.1.8.

---

## Overview

v0.1.8 introduces several structural changes to improve the evaluation system and test set management. Most changes are backward compatible, but some require attention.

---

## 1. Experiment Configuration Paths

### What Changed

The `exp_configs/` directory has been reorganized into subdirectories for better categorization.

### Migration Steps

**Step 1**: Update any hardcoded paths in your scripts or documentation.

| Old Path | New Path |
|----------|----------|
| `exp_configs/baseline.yaml` | `exp_configs/baseline/baseline_10percent.yaml` |
| `exp_configs/chunk_smoke_test.yaml` | `exp_configs/smoke_tests/smoke_full.yaml` |
| `exp_configs/golden_test.yaml` | `exp_configs/golden_tests/golden_test.yaml` |
| `exp_configs/strategy_comparison.yaml` | `exp_configs/experiments/strategy_comparison.yaml` |

**Step 2**: If you have custom configuration files, move them to the appropriate subdirectory:

- Baseline configurations -> `exp_configs/baseline/`
- Comparison experiments -> `exp_configs/experiments/`
- Golden tests -> `exp_configs/golden_tests/`
- Smoke tests -> `exp_configs/smoke_tests/`

**Step 3**: Update any CI/CD or automation scripts that reference old paths.

---

## 2. Test Set Configuration Format

### What Changed

A new `test_sets` configuration format has been introduced with structured metadata.

### Old Format (Deprecated but Still Supported)

```yaml
test_sets:
  - name: my_test_set
    questions: [...]
```

### New Format (Recommended)

```yaml
test_sets:
  my_test_set:
    path: path/to/test_set.json
    on_missing: generate
    meal_id: auto
```

### Migration Steps

**Step 1**: Run your existing configuration. You will see a deprecation warning.

**Step 2**: Update to the new format at your convenience. The system will automatically:

- Parse the new format
- Validate test set structure
- Resolve test sets with on_missing routing

**Step 3**: Use the TestSetManager API for programmatic access:

```python
from src.test_set_manager import TestSetManager

manager = TestSetManager(config)
test_set = manager.resolve_test_set("my_test_set")
```

---

## 3. New Evaluation Metrics

### What Changed

Five new metrics have been added to the evaluation pipeline:

- Context Precision
- Context Recall
- Chunk-level retrieval metrics
- Dedup metrics
- False Positive Rate (FPR)

### Migration Steps

**Step 1**: These metrics are opt-in. Add them to your experiment configuration to use:

```yaml
metrics:
  retrieval:
    - hit_rate
    - mrr
    - ndcg
    - chunk_level
    - dedup
    - fpr
  generation:
    - faithfulness
    - answer_relevancy
    - context_precision
    - context_recall
```

**Step 2**: Update your analysis scripts if they parse evaluation output, as new metric columns will appear.

---

## 4. NDCG Calculation Fix

### What Changed

NDCG calculation now includes deduplication to ensure values stay within [0,1].

### Impact

- **If you used NDCG in v0.1.7**: Your values may have been slightly inflated due to duplicate sources
- **In v0.1.8**: Values will be more accurate and correctly bounded
- **Recommendation**: Re-run critical experiments to get accurate NDCG values

---

## 5. Question Generation Changes

### What Changed

- `source_chunks` field added to document-level questions
- Incremental generation ensures target question count is met
- Question validity checking is available

### Impact

- Existing test sets remain valid
- New test sets will include `source_chunks` field
- Generation will now reach target num_questions reliably

---

## 6. Experiment Configuration Templates

### What's New

Template files are now available in `exp_configs/templates/`:

- `_complete.yaml` - Full configuration with all options
- `_minimal.yaml` - Minimal configuration for quick testing
- `_preset_chunk.yaml` - Predefined chunking strategies
- `_preset_reranker.yaml` - Predefined reranker configurations
- `_preset_retrieval.yaml` - Predefined retrieval configurations

### Usage

Use these templates as starting points for new experiments:

```bash
cp exp_configs/templates/_minimal.yaml exp_configs/experiments/my_experiment.yaml
# Edit my_experiment.yaml as needed
```

---

## Backward Compatibility

### What Still Works

- All v0.1.7 experiment configurations (with updated paths)
- Old test set format (with deprecation warning)
- Existing meals and test sets
- All evaluation metrics from v0.1.7

### What May Need Attention

- Hardcoded paths to `exp_configs/` files
- Scripts that parse evaluation output (new metrics columns)
- Custom TestSetManager integration (new module)

---

## Troubleshooting

### "Cannot find configuration file"

**Solution**: Check the new directory structure. Files have been moved to subdirectories.

### Deprecation warning for test_sets format

**Solution**: This is informational only. Your configuration still works. Update to the new format when convenient.

### NDCG values different from v0.1.7

**Solution**: This is expected. The fix ensures correct [0,1] bounding. Re-run experiments for accurate values.

---

## Need Help?

- See [release-summary.md](./release-summary.md) for an overview
- See [changelog-detailed.md](./changelog-detailed.md) for complete details
- See [test-set-management.md](../../guides/test-set-management.md) for TestSetManager usage
