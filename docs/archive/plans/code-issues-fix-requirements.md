# Code Issues & Fix Requirements

> Generated: 2026-04-17
> Source: Project survey conducted on 2026-04-17

---

## Issue 1: Generator system_prompt Not Using Anthropic API `system` Parameter

### Severity: Medium

### Location

- [src/generator.py](../../src/generator.py) L54-L87

### Current Behavior

`Generator.generate()` concatenates `system_prompt` and `context_text` and `query` into a single `user_message` string, then passes it as a user role message:

```python
user_message = f"""{system_prompt}

{context_text}

用户问题：{query}

请提供回答："""

message = self.client.messages.create(
    model=self.model_name,
    max_tokens=self.max_tokens,
    temperature=self.temperature,
    messages=[
        {
            "role": "user",
            "content": user_message,
        }
    ],
)
```

### Problem

1. The Anthropic Messages API has a dedicated `system` parameter for system prompts. Putting system prompts in the user message is not the intended usage pattern and may cause the model to not follow instructions as reliably.
2. The model may treat the system prompt as part of the user's question rather than as system-level instructions, reducing instruction-following quality.
3. This also makes it impossible to use the system prompt for its intended purpose of controlling model behavior (e.g., tone, format constraints).

### Expected Behavior

Use the `system` parameter of the Anthropic Messages API:

```python
message = self.client.messages.create(
    model=self.model_name,
    max_tokens=self.max_tokens,
    temperature=self.temperature,
    system=system_prompt,
    messages=[
        {
            "role": "user",
            "content": f"""{context_text}

用户问题：{query}

请提供回答：""",
        }
    ],
)
```

### Fix Requirements

1. Move `system_prompt` to the `system` parameter of `client.messages.create()`
2. Keep `context_text` and `query` in the user message
3. Ensure backward compatibility - if `system_prompt` is `None`, use the default prompt as the system parameter
4. Add unit test to verify the API call structure

### Test Verification

- Write a unit test that mocks `client.messages.create` and verifies that:
  - The `system` parameter is set to the expected system prompt
  - The user message only contains context and query (not system prompt)
  - When `system_prompt=None`, the default system prompt is used

---

## Issue 2: Invalid Strategy Name `"complex"` in chunk_comparison.yaml

### Severity: High (will cause runtime crash)

### Location

- [exp_configs/chunk_comparison.yaml](../../exp_configs/chunk_comparison.yaml) L17

### Current Behavior

```yaml
test_sets:
  - strategy: "complex"
    num_questions: 15
    seed: 202
```

### Problem

`test_generator.py` only supports three strategies: `factual`, `boundary`, `multi_hop`. The `_select_chunks()` method raises `ValueError` when an unknown strategy is encountered. Running the chunk_comparison experiment will crash at test set generation.

### Expected Behavior

The strategy should be one of the supported values. Based on the intent (testing complex/cross-boundary questions), `"multi_hop"` is the appropriate replacement.

### Fix Requirements

1. Change `"complex"` to `"multi_hop"` in `chunk_comparison.yaml` L17
2. Optionally: add input validation in the experiment runner to catch invalid strategy names early with a clear error message, rather than letting it crash deep in test_generator

### Test Verification

- Run `pixi run python eval/run_experiment.py --config exp_configs/chunk_comparison.yaml` and verify it no longer crashes at test set generation
- Add a validation test that checks all strategy names in experiment configs are valid

---

## Issue 3: Meal total_chunks Count Off-by-One per File

### Severity: Low (cosmetic, affects stats display only)

### Location

- [src/meal.py](../../src/meal.py) L450-L457

### Current Behavior

```python
total_chunks = len(source_filter_jsonl)  # This is the number of JSONL FILES
for jsonl_rel in source_filter_jsonl:
    jsonl_path = chunks_dir / jsonl_rel
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            total_chunks += sum(1 for _ in f)  # Adds line count per file
    except Exception:
        pass
```

### Problem

`total_chunks` is initialized to `len(source_filter_jsonl)` (the number of JSONL files), then the actual chunk count (line count) from each file is added. This results in `total_chunks = file_count + actual_chunk_count`, which is inflated by the number of files.

For example, if there are 5 JSONL files with 100, 200, 150, 80, 120 chunks respectively:
- Expected: `total_chunks = 650`
- Actual: `total_chunks = 5 + 650 = 655`

### Expected Behavior

```python
total_chunks = 0
for jsonl_rel in source_filter_jsonl:
    jsonl_path = chunks_dir / jsonl_rel
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            total_chunks += sum(1 for _ in f)
    except Exception:
        pass
```

### Fix Requirements

1. Change `total_chunks = len(source_filter_jsonl)` to `total_chunks = 0`
2. Verify that `artifact_manifest["chunk_count"]` is used only for display/stats and not for any logic that would break with the corrected value

### Test Verification

- Add a unit test for Meal creation that verifies `chunk_count` matches the actual number of chunks in the JSONL files

---

## Issue 4: Source Path Format Mismatch in Retrieval Metrics

### Severity: High (causes metrics to always return 0)

### Location

- [eval/metrics.py](../../eval/metrics.py) - all three metric functions
- [eval/run_eval.py](../../eval/run_eval.py) L60-L68
- [eval/run_experiment.py](../../eval/run_experiment.py) L512-L529
- [eval/test_data.json](../../eval/test_data.json) - `expected_sources` fields

### Current Behavior

**Retrieved sources** come from chunk metadata, which stores `source` as a relative path to the parsed markdown file:

```python
# chunker.py L141
"source": str(relative_path),  # e.g., "annual_report/贵州茅台2023年年度报告.md"
```

**Expected sources** in test data use PDF filenames:

```json
"expected_sources": ["贵州茅台2023年年度报告.pdf", "贵州茅台2023年年度报告_英文版_.pdf"]
```

The metrics functions do exact string matching via set intersection:

```python
retrieved_set = set(retrieved_sources)  # {"annual_report/贵州茅台2023年年度报告.md", ...}
expected_set = set(expected_sources)     # {"贵州茅台2023年年度报告.pdf", ...}
hits = len(retrieved_set & expected_set)  # Always 0 - no overlap!
```

### Problem

The format mismatch means **all retrieval metrics (Hit Rate, MRR, NDCG) will always be 0** because the set intersection will always be empty. This makes the entire evaluation system non-functional for source-based metrics.

### Expected Behavior

Either:
1. **Normalize source paths** before comparison - extract the base filename and strip the extension, so both sides become comparable (e.g., `"贵州茅台2023年年度报告"`)
2. **Store PDF source in chunk metadata** - add the original PDF filename as a separate metadata field during parsing/chunking
3. **Update test data** to use the same format as stored in chunk metadata

Option 1 is the simplest and least invasive. Option 2 is more robust for future changes.

### Fix Requirements

1. Implement a source normalization function in `eval/metrics.py`:

```python
def normalize_source(source: str) -> str:
    """Normalize source path to a comparable form.

    Extracts the filename stem (without extension and directory),
    e.g., "annual_report/贵州茅台2023年年度报告.md" -> "贵州茅台2023年年度报告"
          "贵州茅台2023年年度报告.pdf" -> "贵州茅台2023年年度报告"
    """
    from pathlib import Path
    return Path(source).stem
```

2. Apply normalization in all three metric functions before set operations
3. Also apply normalization in `run_eval.py` and `run_experiment.py` where sources are collected
4. Verify with actual test data that metrics now return non-zero values

### Test Verification

- Write unit tests for `normalize_source()` covering various path formats
- Write integration test that verifies metrics return non-zero values with normalized sources
- Run `pixi run python eval/run_eval.py` and verify metrics are no longer all zeros

---

## Issue 5: Indexer Resource Not Automatically Released

### Severity: Low (potential resource leak)

### Location

- [src/indexer.py](../../src/indexer.py) L211-L217 - `close()` method
- [src/pipeline.py](../../src/pipeline.py) - `RAGPipeline` class

### Current Behavior

`VectorIndexer` has a `close()` method that properly closes the Qdrant client, but `RAGPipeline` never calls it. The pipeline creates an indexer in `__init__` and may create additional indexers in `use_meal()`, but never releases them.

Additionally, in [eval/run_experiment.py](../../eval/run_experiment.py) L647-L658, the variant evaluation creates a pipeline, closes its indexer, replaces it with a new one, but the new indexer is also never closed.

### Problem

Qdrant client holds file handles and resources. Not closing them may lead to:
- Resource leaks in long-running processes
- File locking issues on Windows (Qdrant uses WAL files)
- Potential data corruption if the process is killed while Qdrant is writing

### Expected Behavior

`RAGPipeline` should implement a context manager protocol (`__enter__`/`__exit__`) or at minimum a `close()` method that properly releases the indexer.

### Fix Requirements

1. Add `__enter__` and `__exit__` methods to `RAGPipeline`:

```python
def __enter__(self):
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()
    return False

def close(self):
    if hasattr(self, 'indexer') and self.indexer is not None:
        self.indexer.close()
```

2. Update `use_meal()` to close the old indexer before creating a new one:

```python
def use_meal(self, meal_name: str):
    if hasattr(self, 'indexer') and self.indexer is not None:
        self.indexer.close()
    # ... create new indexer
```

3. Update `run_experiment.py` to use the pipeline as a context manager or call `close()` explicitly

### Test Verification

- Add unit test verifying `RAGPipeline.close()` calls `indexer.close()`
- Add unit test verifying context manager protocol works
- Verify no resource leaks in variant evaluation

---

## Issue 6: Test Data Contains Placeholder Values

### Severity: Low (affects evaluation quality, not functionality)

### Location

- [eval/test_data.json](../../eval/test_data.json) - multiple `expected_answer` fields

### Current Behavior

Several test questions have placeholder values in `expected_answer`:

| Question ID | Placeholder |
|-------------|-------------|
| q002 | "XXX亿元" |
| q003 | "XXX亿元" |
| q006 | "XXX亿元" (x2) |
| q007 | "XXX万亿元" |
| q009 | "XX%" |

### Problem

While `expected_answer` is not currently used by the automated metrics (only `expected_sources` is used), these placeholders:
1. Make the test data look incomplete and unprofessional
2. Will cause issues when generation quality metrics (Faithfulness, Answer Relevancy) are implemented, as they compare against expected answers
3. Mislead anyone reviewing the test data about what the correct answers should be

### Fix Requirements

1. Fill in the actual values from the corresponding PDF documents
2. If the actual values cannot be determined (e.g., the PDF is not available), mark the field with a clear indicator like `null` or add a `"placeholder": true` flag
3. When implementing generation quality metrics, skip questions with placeholder expected answers

### Test Verification

- Verify no `expected_answer` contains "XXX" or "XX" after fix
- Ensure generation quality metric implementation handles `null` expected answers gracefully

---

## Priority Summary

| Priority | Issue | Impact |
|----------|-------|--------|
| **P0 - Critical** | Issue 4: Source path format mismatch | Evaluation metrics always return 0 |
| **P1 - High** | Issue 2: Invalid strategy name | chunk_comparison experiment crashes |
| **P2 - Medium** | Issue 1: Generator system_prompt | Suboptimal LLM instruction following |
| **P3 - Low** | Issue 5: Indexer resource leak | Potential resource issues on Windows |
| **P3 - Low** | Issue 3: total_chunks off-by-one | Inaccurate stats display |
| **P4 - Cosmetic** | Issue 6: Test data placeholders | Incomplete test data |

### Recommended Fix Order

1. Issue 4 (source path mismatch) - makes evaluation functional
2. Issue 2 (invalid strategy) - unblocks chunk_comparison experiment
3. Issue 1 (system_prompt) - improves LLM response quality
4. Issue 5 (resource leak) - prevents potential issues
5. Issue 3 (total_chunks) - cosmetic fix
6. Issue 6 (test data) - can be done alongside generation metrics implementation
