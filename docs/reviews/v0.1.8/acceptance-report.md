# v0.1.8 Acceptance Report

> Date: 2026-04-20
> Version: v0.1.8
> Branch: dev (merged from fix-eval)

---

## Summary

v0.1.8 has been successfully merged and is ready for release. This version focuses on evaluation system reliability improvements and introduces the TestSetManager architecture.

---

## Acceptance Criteria

### Core Functionality

| Criterion | Status | Notes |
|-----------|--------|-------|
| All new metrics implemented | PASS | Context Precision, Context Recall, Chunk-level, Dedup, FPR |
| TestSetManager functional | PASS | 911 lines, complete test coverage |
| New config format working | PASS | With backward compatibility |
| Experiment config structure | PASS | Organized into subdirectories |
| Question validity check | PASS | Integrated into pipeline |
| Equivalence group support | PASS | Meal building and metrics |

### Bug Fixes

| Bug | Status | Notes |
|-----|--------|-------|
| NDCG out of [0,1] range | FIXED | Deduplication added |
| source_files for irrelevant/missing | FIXED | Corrected assignment |
| Chunker config hash | FIXED | Includes strategy/semantic params |
| Question generation shortfall | FIXED | Incremental distribution |

### Code Quality

| Criterion | Status | Notes |
|-----------|--------|-------|
| Test coverage | PASS | ~3,000 new test lines |
| Type annotations | PASS | All public functions annotated |
| Docstrings | PASS | Added to new modules |
| Error handling | PASS | try/except for IO operations |
| No hardcoded values | PASS | All in config.yaml |

### Documentation

| Document | Status | Notes |
|----------|--------|-------|
| CHANGELOG.md | UPDATED | v0.1.8 entry added |
| release-summary.md | CREATED | Version overview |
| changelog-detailed.md | CREATED | Detailed change log |
| migration-guide.md | CREATED | User migration guide |
| acceptance-report.md | CREATED | This document |
| evaluation-metrics.md | UPDATED | New metrics documented |
| test-set-management.md | CREATED | TestSetManager guide |
| config-reference.md | UPDATED | New structure documented |
| backlog.md | UPDATED | Task status updated |

---

## Statistics

| Metric | Value |
|--------|-------|
| Total commits in fix-eval | 47 |
| Files added | 12 |
| Files modified | 46 |
| Lines added | +10,736 |
| Lines removed | -475 |
| New test cases | ~3,000 |
| New metrics | 5 |
| New modules | 1 (TestSetManager) |
| New documentation files | 5 |

---

## Risk Assessment

### Low Risk

- New metrics are opt-in via configuration
- TestSetManager has comprehensive test coverage
- Backward compatibility maintained for old formats
- Documentation updated

### Medium Risk

- Configuration path changes may break automation scripts
- NDCG value changes may affect historical comparisons

### Mitigations

- Migration guide provided
- Deprecation warnings for old formats
- Detailed changelog for reference

---

## Known Issues

None at time of release.

---

## Recommendations

1. **Re-run critical experiments** after upgrade to get accurate NDCG values
2. **Update automation scripts** that reference old exp_configs paths
3. **Migrate to new test_sets format** at your convenience (old format still works)
4. **Review new metrics** and consider adding them to your evaluation pipeline

---

## Sign-off

- [x] Code review complete
- [x] Tests passing
- [x] Documentation updated
- [x] CHANGELOG updated
- [x] Migration guide created
- [x] Ready for tag and release
