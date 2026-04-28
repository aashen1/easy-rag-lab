# Test Suite Analysis & Improvement Plan

> Date: 2026-04-17
> Scope: Software engineering test quality (pytest), not RAG evaluation metrics

---

## 1. Current Test Inventory

| Test File | Lines | Source Module | Test Count (approx) | Focus |
|-----------|-------|-------------|---------------------|-------|
| `conftest.py` | 27 | Global | N/A | Module-level mock of `transformers` |
| `test_parser.py` | 222 | `src/parser.py` | 12 | PDF parsing, category detection, skip/force |
| `test_chunker.py` | 280 | `src/chunker.py` | 15 | Chunking logic, overlap, source filter |
| `test_embedder.py` | 277 | `src/embedder.py` | 12 | Embedding init, embed_texts, embed_query |
| `test_meal.py` | 606 | `src/meal.py` | 28 | MealConfig, data_id, hashes, MealManager CRUD |
| `test_sampler.py` | 180 | `src/sampler.py` | 18 | SamplingConfig validation, determine_sample |
| `test_test_generator.py` | 256 | `src/test_generator.py` | 13 | Chunk grouping, selection, LLM response parsing |
| `test_experiment.py` | 900 | `src/experiment.py` | 30+ | ExperimentConfig, deep_merge, ExperimentManager |
| `test_experiment_reporter.py` | 816 | `eval/experiment_reporter.py` | 25+ | Reporter sections, multi-variant, LLM report |
| `test_run_eval.py` | 347 | `eval/run_eval.py` | 11 | CLI args, experiment config loading |
| `test_run_experiment.py` | 555 | `eval/run_experiment.py` | 15 | Asset verification, comparison data, category metrics |
| `test_e2e_experiment.py` | 1402 | Multiple | 15 | Integration tests (all marked `@pytest.mark.integration`) |

**Total: ~12 test files, ~5,878 lines, ~195 test cases**

---

## 2. Critical Gaps: Modules with ZERO Tests

These are the most dangerous gaps. Entire core modules have no test coverage whatsoever.

### 2.1 `eval/metrics.py` -- CRITICAL

**Risk: HIGH** -- This is the core evaluation logic. If Hit Rate / MRR / NDCG calculations are wrong, ALL experiment results are unreliable.

- `calculate_hit_rate()` -- No test for: empty lists, partial hits, exact match, no match
- `calculate_mrr()` -- No test for: first position hit, last position hit, no hit, multiple expected sources
- `calculate_ndcg()` -- No test for: perfect ranking, reverse ranking, partial ranking, k parameter

**Why this is the #1 priority:** Every experiment report depends on these functions. A bug here silently corrupts all evaluation data. The functions are pure (no I/O, no mocking needed) and trivially testable.

### 2.2 `src/retriever.py` -- HIGH

**Risk: HIGH** -- The Retriever is the bridge between embedding and Qdrant search. No tests for:
- Input validation (empty query, non-string query)
- Search result transformation (payload extraction)
- Error handling when Qdrant is unavailable

### 2.3 `src/generator.py` -- HIGH

**Risk: HIGH** -- The Generator wraps the Anthropic client for LLM calls. No tests for:
- Input validation (empty query, no contexts)
- Prompt construction (system prompt, context formatting)
- Error handling when API call fails
- Client initialization failure

### 2.4 `src/indexer.py` -- HIGH

**Risk: HIGH** -- VectorIndexer manages Qdrant collections. No tests for:
- Collection creation (new, existing, recreate)
- Chunk indexing (empty, mismatched lengths, batch processing)
- `build_index()` with source_filter
- `get_collection_info()`, `delete_collection()`, `close()`
- Error handling throughout

### 2.5 `src/pipeline.py` -- MEDIUM

**Risk: MEDIUM** -- RAGPipeline orchestrates the full chain. No tests for:
- Initialization with/without meal
- `build_index()` with sampling
- `query()` happy path and error paths
- `use_meal()` switching

### 2.6 `src/utils.py` -- MEDIUM

**Risk: MEDIUM** -- Utility functions used everywhere. No tests for:
- `load_config()` -- file not found, invalid YAML, missing fields
- `get_llm_config()` -- preset resolution, env var fallback, required vars
- `get_env_var()` -- missing vars, default values, required flag
- `ensure_dir()` -- already exists, creates parents
- `setup_logger()` -- config-driven logger setup

### 2.7 `main.py` -- LOW

**Risk: LOW** -- CLI entry point. Testing argparse is low value, but the orchestration logic (sampling mode validation, meal commands) could benefit from targeted tests.

---

## 3. Over-Engineering: Tests That Should Be Simplified

### 3.1 `test_embedder.py` -- Massive Mock Setup Duplication

**Problem:** Every single test method repeats 10-15 lines of identical mock setup for `AutoModel`, `AutoTokenizer`, and `torch.cuda.is_available`. This is ~150 lines of pure duplication.

**Example (repeated 12 times):**
```python
@patch("src.embedder.AutoTokenizer")
@patch("src.embedder.AutoModel")
@patch("src.embedder.torch.cuda.is_available")
def test_XXX(self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer):
    mock_cuda_available.return_value = True
    mock_model = MagicMock()
    mock_model.config.hidden_size = 1024
    mock_model.to.return_value = mock_model
    mock_model.half.return_value = mock_model
    mock_auto_model.from_pretrained.return_value = mock_model
    mock_auto_tokenizer.from_pretrained.return_value = MagicMock()
    # ... actual test
```

**Recommendation:** Extract a `@pytest.fixture` that returns a pre-configured Embedder with mocked internals. Each test only needs to override what's different.

### 3.2 `test_experiment_reporter.py` -- Testing Private Methods

**Problem:** Tests like `test_generate_overview_section`, `test_generate_data_section`, `test_generate_config_section`, `test_generate_test_set_section`, `test_generate_results_section`, `test_generate_comparison_table`, `test_generate_conclusion_section`, `test_generate_assets_section` all test private `_generate_*_section` methods. This tests implementation details rather than behavior.

**Why it's a problem:** If the report format changes (e.g., sections are renamed or merged), all these tests break even though the output is still correct. The public API is `generate_markdown_report()` and `generate_variant_comparison_report()` -- that's what should be tested.

**Recommendation:** Replace 8 private-method tests with 2-3 tests on the public API that verify the complete output contains expected content. Keep private method tests only if they contain complex logic worth isolating.

### 3.3 `test_e2e_experiment.py` -- "E2E" Tests That Aren't E2E

**Problem:** This 1,400-line file is labeled "end-to-end" but mocks everything (Embedder, VectorIndexer, Generator, TestSetGenerator, RAGPipeline). The tests don't actually test end-to-end behavior -- they test the same ExperimentManager and ExperimentReporter logic already covered by `test_experiment.py` and `test_experiment_reporter.py`.

Additionally, the fixture setup is extremely heavy (8 fixtures, ~200 lines) creating a full project directory structure that most tests don't need.

**Recommendation:**
- Remove tests that duplicate coverage from `test_experiment.py` and `test_experiment_reporter.py`
- Keep only genuinely unique integration scenarios (e.g., asset verification with real PDF files)
- Reduce fixture complexity -- most tests only need 2-3 of the 8 fixtures

### 3.4 `test_run_eval.py` -- Testing Python's argparse

**Problem:** `TestRunEvalIntegration` contains 3 tests that just verify `argparse.ArgumentParser` parses arguments correctly. This is testing Python's standard library, not project logic.

**Recommendation:** Remove these tests. If there's custom argument validation logic, test that instead.

### 3.5 `test_experiment.py` -- Excessive Data Structure Testing

**Problem:** `TestExperimentConfig` has 12 tests for validation (empty name, empty description, missing meal, empty test_sets, missing strategy, missing num_questions, empty variants, missing variant name, missing metrics). `TestExperimentResult` has 5 tests for serialization. These are testing data class boilerplate rather than behavior.

**Recommendation:** Consolidate validation tests into 2-3 tests (valid config, invalid config with multiple errors, roundtrip serialization). The current 12 separate tests don't add proportional value.

---

## 4. Infrastructure Issues

### 4.1 `conftest.py` -- Global Module-Level Mock

**Problem:** The conftest.py does `sys.modules["transformers"] = MagicMock()` at import time. This:
- Affects ALL tests globally, even those that don't use transformers
- Makes test dependencies invisible -- you can't tell from reading a test file that transformers is mocked
- Can cause subtle issues if a test accidentally imports something that depends on the real transformers
- Is a fragile pattern that breaks if the import path changes

**Recommendation:** Remove the global mock from conftest.py. Instead, use `@patch` decorators or fixtures in the specific test files that need them (`test_embedder.py`). This makes dependencies explicit and scoped.

### 4.2 Inconsistent Use of Markers

**Problem:** `pytest.ini` defines `integration` and `slow` markers, but:
- `test_e2e_experiment.py` marks everything as `@pytest.mark.integration` but the tests are mocked unit tests
- No test uses `@pytest.mark.slow`
- There's no convention for when to use markers
- Running `pytest -m "not integration"` would skip the "e2e" tests, but they're actually fast mocked tests

**Recommendation:**
- Reserve `@pytest.mark.integration` for tests that actually touch external systems (Qdrant, LLM API, real PDF files)
- Reserve `@pytest.mark.slow` for tests that take >5 seconds
- Remove `@pytest.mark.integration` from mocked tests in `test_e2e_experiment.py`
- Add a `@pytest.mark.unit` marker for pure unit tests if desired

### 4.3 No Test Isolation Strategy

**Problem:** Tests share state through:
- Global `sys.modules` manipulation in conftest.py
- No cleanup of Qdrant data between tests
- No explicit test ordering or dependency management

**Recommendation:** Each test should be independently runnable. Use fixtures with proper scope and cleanup.

---

## 5. Missing Test Patterns

### 5.1 No Error Path Testing for Core Modules

The untested modules (retriever, generator, indexer, pipeline) all have error handling code that's never exercised:
- What happens when Qdrant is down?
- What happens when the LLM API returns an error?
- What happens when the config file is malformed?
- What happens when a PDF is corrupted mid-parse?

### 5.2 No Property-Based Testing

Pure functions like `calculate_hit_rate`, `calculate_mrr`, `calculate_ndcg`, `compute_data_id`, `deep_merge` are excellent candidates for property-based testing (e.g., using `hypothesis`). For example:
- `calculate_mrr` should always return a value in [0, 1]
- `compute_data_id` should be deterministic and order-independent
- `deep_merge` should be idempotent when override == base

### 5.3 No Test for Configuration Edge Cases

`get_llm_config()` has complex fallback logic (preset not found -> default, env var not set -> fallback, base_url normalization). None of this is tested.

### 5.4 No Performance/Regression Tests

For a RAG system, it would be valuable to have:
- A test that verifies chunk_size=512 produces the expected number of chunks for a known document
- A test that verifies embedding dimension matches the model config
- A test that verifies retrieval results are deterministic for a given query

---

## 6. Prioritized Improvement Plan

### Phase 1: Critical Fixes (Immediate)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1 | Add tests for `eval/metrics.py` (Hit Rate, MRR, NDCG) | Low | **Critical** -- validates all experiment results |
| 2 | Add tests for `src/retriever.py` | Medium | High -- core RAG component |
| 3 | Add tests for `src/generator.py` | Medium | High -- core RAG component |
| 4 | Add tests for `src/indexer.py` | Medium | High -- core RAG component |
| 5 | Remove global `sys.modules` mock from `conftest.py` | Low | Medium -- removes hidden dependency |

### Phase 2: Simplification (Short-term)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 6 | Extract Embedder mock fixture in `test_embedder.py` | Low | Medium -- reduces ~150 lines of duplication |
| 7 | Consolidate `test_experiment_reporter.py` private method tests | Medium | Medium -- tests behavior not implementation |
| 8 | Remove argparse tests from `test_run_eval.py` | Low | Low -- removes useless tests |
| 9 | Trim `test_e2e_experiment.py` -- remove duplicates, reduce fixtures | Medium | Medium -- removes ~800 lines of redundant tests |
| 10 | Consolidate `test_experiment.py` validation tests | Low | Low -- reduces test count without losing coverage |

### Phase 3: Coverage Expansion (Medium-term)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 11 | Add tests for `src/pipeline.py` | Medium | Medium -- integration logic |
| 12 | Add tests for `src/utils.py` | Low | Medium -- config/env handling |
| 13 | Add error path tests for all core modules | Medium | High -- resilience |
| 14 | Fix `@pytest.mark.integration` usage | Low | Low -- clarity |
| 15 | Add property-based tests for pure functions | Medium | Medium -- mathematical correctness |

---

## 7. Recommended New Test Files

### `tests/test_metrics.py` (Priority: CRITICAL)

```python
class TestCalculateHitRate:
    def test_perfect_hit
    def test_partial_hit
    def test_no_hit
    def test_empty_expected
    def test_empty_retrieved
    def test_duplicate_sources

class TestCalculateMRR:
    def test_first_position_hit
    def test_last_position_hit
    def test_no_hit
    def test_empty_expected
    def test_multiple_expected

class TestCalculateNDCG:
    def test_perfect_ranking
    def test_reverse_ranking
    def test_partial_ranking
    def test_k_parameter
    def test_empty_expected
    def test_ideal_dcg_single_doc
```

### `tests/test_retriever.py` (Priority: HIGH)

```python
class TestRetriever:
    def test_retrieve_success  # mock indexer + embedder
    def test_retrieve_empty_query
    def test_retrieve_non_string_query
    def test_retrieve_qdrant_error
    def test_retrieve_result_transformation
```

### `tests/test_generator.py` (Priority: HIGH)

```python
class TestGenerator:
    def test_generate_success  # mock Anthropic client
    def test_generate_empty_query
    def test_generate_no_contexts
    def test_generate_api_error
    def test_generate_custom_system_prompt
    def test_init_client_failure
```

### `tests/test_indexer.py` (Priority: HIGH)

```python
class TestVectorIndexer:
    def test_create_collection_new  # mock QdrantClient
    def test_create_collection_existing
    def test_create_collection_recreate
    def test_index_chunks_success
    def test_index_chunks_empty
    def test_index_chunks_mismatched_lengths
    def test_build_index_dir_not_found
    def test_build_index_with_source_filter
    def test_get_collection_info
    def test_delete_collection
```

### `tests/test_utils.py` (Priority: MEDIUM)

```python
class TestLoadConfig:
    def test_load_valid_config
    def test_load_file_not_found
    def test_load_invalid_yaml

class TestGetLlmConfig:
    def test_default_preset
    def test_named_preset
    def test_preset_not_found_fallback
    def test_env_var_resolution

class TestGetEnvVar:
    def test_existing_var
    def test_missing_var_with_default
    def test_required_var_missing

class TestEnsureDir:
    def test_creates_new_dir
    def test_existing_dir
    def test_nested_dir
```

---

## 8. Summary Statistics

| Category | Current | After Improvement |
|----------|---------|-------------------|
| Source modules with tests | 8 / 14 (57%) | 14 / 14 (100%) |
| Core RAG modules with tests | 2 / 6 (33%) | 6 / 6 (100%) |
| Lines of duplicate mock setup | ~150 | ~30 |
| Tests testing implementation details | ~20 | ~5 |
| Tests testing stdlib behavior | 3 | 0 |
| Pure function modules untested | 1 (metrics) | 0 |
| Estimated total test lines | ~5,878 | ~4,500 (net reduction despite new tests) |

The net reduction comes from eliminating duplication and over-testing, while adding high-value tests for currently untested core modules.
