# v0.1.14 Acceptance Report

<!-- status: active -->

> Date: 2026-04-29
> Version: v0.1.14
> Theme: Code Health Governance

---

## Version Summary

v0.1.14 is a code health governance release. The primary goal was to decompose four "god files" (5000, 3000, 1800, 1500 lines) into well-structured packages, while also adding strategy pattern to pipeline and Pydantic validation to experiment configuration.

## Commit Statistics

| Metric | Value |
|--------|-------|
| Commits since v0.1.13 | 73 |
| Files changed | 373 |
| Lines added | +19,780 |
| Lines deleted | -13,600 |

By type:

| Type | Count |
|------|-------|
| refactor | 32 |
| docs | 19 |
| feat | 7 |
| fix | 7 |
| style | 3 |
| chore | 3 |
| test | 2 |

## Key Deliverables

### 1. God File Decomposition (32 refactor commits)

| Original File | Lines | Package | Sub-modules |
|---------------|-------|---------|-------------|
| `src/test_generator.py` | ~5000 | `src/test_generation/` | 9 (generator, llm_caller, document_loader, segment_builder, models, validators, supplement, prompts, chunk_locator) |
| `src/meal.py` | ~1500 | `src/meal/` | 6 (manager, builders, cache, hashes, models, utils) |
| `eval/run_experiment.py` | ~3000 | `eval/runner/` | 8 (core, evaluation, metrics, preparation, comparison, reporting, reproduction, asset_verifier) |
| `eval/experiment_reporter.py` | ~1800 | `eval/reporter/` | 5 (models, formatters, llm_reporter, template_single, template_variant) |

### 2. New Features (7 feat commits)

- Pipeline strategy pattern (`query_rewrite_strategies.py` + `retrieval_strategies.py`)
- ExperimentConfig Pydantic models (`experiment_schemas.py`)
- Golden testset generation quality improvements (5 targeted fixes)
- Generator per-call `max_tokens` override
- Meal file list company name tag
- `create_artifact_cache` factory function
- `EvaluationSample` dataclass

### 3. Bug Fixes (7 fix commits)

- `is_genuine_proper_noun` filter for false positive reduction
- `save_manifest` return type annotation correction
- Missing `SummaryConfig` fields
- Hardcoded API URL and model name removal
- Test reference updates after extraction
- Mock evidence quote validation fix

### 4. Documentation Restructuring (19 docs commits)

- `docs/guides/` → `docs/user-guides/` + `docs/dev-guides/`
- Archive restructured by version narrative theme
- All broken links fixed
- README rewritten
- `dev-story.md` developer essay added
- `release-cadence.md` version rhythm guide added

## Quality Verification

| Check | Result |
|-------|--------|
| Lint (ruff) | All checks passed, 134 files unchanged |
| Unit tests | 1561 passed, 10 deselected |
| Test duration | 47.72s |

## Known Issues (Carried Forward)

- `source_chunks` field still empty for document-level strategy (BUG-025)
- LLM report opening "好的" issue may recur (BUG-032)
- Streamlit page graying during chat loading (BUG-068)
- Hardcoded API key pattern `api_key="dummy"` for LongCat compatibility (BUG-001, new)

## Version Narrative

> 看得见的产品有了，看不见的骨架也得撑得住。

The narrative arc continues: v0.1.13 gave us a visible product, v0.1.14 gives it a maintainable skeleton. The four god files that were the biggest code health risk have been decomposed into focused packages, making future development and debugging significantly easier.

---

## Next Version Direction (v0.1.15)

- Transparent full experiment report (FEAT-010)
- "Bells and whistles" effect verification with comparison report
- Metric score upper/lower bound confirmation
