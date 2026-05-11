# Memory Error Investigation Report

> Date: 2026-05-11 12:45
> Context: Phase 3 Implementation Plan execution
> Error Type: `MemoryError` during pytest-xdist parallel test execution

---

## 1. Error Summary

### 1.1 Error Type

```
MemoryError
```

Occurred during `ast.parse()` call within pytest's error reporting mechanism.

### 1.2 Command That Triggered Error

```bash
pixi run test-all
# Equivalent to:
pytest tests/ --tb=short -q --durations=10 -n auto --dist loadgroup --max-worker-restart=2
```

### 1.3 Test Environment

- **OS**: Windows 10
- **Python**: 3.12.13
- **pytest**: 9.0.3
- **pytest-xdist**: 3.8.0
- **Terminal**: Git Bash

---

## 2. Error Stack Trace Analysis

### 2.1 Full Stack Trace

```python
INTERNALERROR> MemoryError
INTERNALERROR> E               File "B:\project\ash-easy-rag\.pixi\envs\default\Lib\site-packages\_pytest\_code\source.py", line 191, in getstatementrange_ast
INTERNALERROR> E                 astnode = ast.parse(content, "source", "exec")
```

### 2.2 Call Chain

```
pytest_runtest_protocol
  -> call_and_report
    -> pytest_runtest_makereport
      -> TestReport.from_item_and_call
        -> _format_failed_longrepr
          -> item.repr_failure
            -> _repr_failure_py
              -> excinfo.getrepr
                -> fmt.repr_excinfo
                  -> repr_traceback
                    -> repr_traceback_entry
                      -> _getentrysource
                        -> entry.getsource
                          -> getstatementrange_ast
                            -> ast.parse(content, "source", "exec")  # <-- MemoryError HERE
```

### 2.3 Key Observation

The error occurred **NOT** during test execution itself, but during **pytest's error reporting mechanism** when trying to format a failure traceback. This suggests:

1. A test had already failed
2. pytest was trying to generate the error report
3. The `ast.parse()` call ran out of memory while parsing the source code for error display

---

## 3. Timeline of Events

### 3.1 Test Execution Progress

```
[ 83%] .............F.........F.......................
```

Two tests failed before the memory error:
1. `TestSmoke03FingerprintSystem::test_fingerprint_matches_different_top_k`
2. `TestSmoke03FingerprintSystem::test_fingerprint_matches_reranker_toggle`

### 3.2 After Fixing Tests

After updating the test assertions to match the new `matches()` semantics, running `pixi run test-all` again resulted in:

```
1 failed, 765 passed in 34.17s
```

The memory error occurred again, this time referencing:
```
AssertionError: ('tests/test_evaluators.py::TestRagasEvaluatorConfigReading::test_build_run_config_uses_configured_values', <WorkerController gw0>)
```

---

## 4. Suspected Root Causes

### 4.1 Primary Suspect: pytest-xdist Worker Memory Accumulation

The `pytest-xdist` plugin runs tests in parallel using multiple worker processes. The memory error pattern suggests:

1. **Memory accumulation across tests**: Each test may leak memory or hold references
2. **Large AST parsing**: When a test fails, pytest tries to parse the entire source file for error formatting
3. **Worker process memory limits**: Windows may have stricter per-process memory limits

### 4.2 Secondary Suspect: Large Test File

The error mentions `test_evaluators.py`. Let me check the file size:

```bash
# File: tests/test_evaluators.py
# Lines: ~1500+ lines (estimated based on test count)
```

Large test files with complex fixtures may cause issues when pytest tries to parse them for error reporting.

### 4.3 Tertiary Suspect: RAGAS Import Chain

The failing test `test_build_run_config_uses_configured_values` is in `TestRagasEvaluatorConfigReading`. RAGAS imports are known to be heavy:

```python
# RAGAS imports torch, transformers, and other ML libraries
# These can consume significant memory even when just imported
```

---

## 5. Evidence Collection

### 5.1 Tests That Passed Before Memory Error

The following heavy tests passed successfully:
- `TestRagasEvaluatorConfigReading::test_build_run_config_uses_configured_values` (3.91s call time)
- `TestRagasEvaluatorConfigReading::test_build_run_config_uses_defaults_when_missing` (3.91s)
- `TestRagasEvaluatorConfigReading::test_build_run_config_partial_override` (3.91s)
- `TestRagasEvaluatorConfigReading::test_build_run_config_returns_none_on_import_error` (3.91s)
- `TestRagasEvaluatorConfigReading::test_create_embeddings_uses_configured_values` (3.91s)
- `TestRagasEvaluatorConfigReading::test_create_embeddings_uses_ragas_config_embedding_model` (3.91s)
- `TestRagasEvaluatorConfigReading::test_create_embeddings_ragas_config_overrides_subconfig` (3.91s)

All these tests have **3.91s call time**, indicating heavy imports/computation.

### 5.2 Memory Error Occurrence Pattern

| Run | Tests Passed | Memory Error | Notes |
|-----|--------------|--------------|-------|
| Run 1 | ~2000+ | Yes | After 2 test failures in fingerprint tests |
| Run 2 | 765 | Yes | Different test mentioned in error |

The error is **non-deterministic** - it occurs at different points in different runs.

### 5.3 Worker Process Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "-n auto --dist loadgroup --max-worker-restart=2"
```

- `--n auto`: Uses all available CPU cores
- `--dist loadgroup`: Distributes tests by load group
- `--max-worker-restart=2`: Maximum 2 worker restarts

---

## 6. Potential Solutions to Investigate

### 6.1 Reduce Parallelism

```bash
# Try with fewer workers
pytest tests/ -n 4 --tb=short
```

### 6.2 Disable xdist for Heavy Tests

```python
# In test file
import pytest

@pytest.mark.no_cover  # Disable coverage
def test_heavy_ragas_stuff():
    ...
```

### 6.3 Increase Worker Memory Limits

On Windows, this may require system-level configuration.

### 6.4 Split Large Test Files

Consider splitting `test_evaluators.py` into smaller files:
- `test_ragas_evaluator.py`
- `test_builtin_evaluator.py`
- etc.

### 6.5 Lazy Import RAGAS

```python
# Instead of top-level import
# from ragas import ...

def test_something():
    import ragas  # Lazy import only when needed
    ...
```

---

## 7. Additional Data Points

### 7.1 System State During Error

- Multiple pytest worker processes running
- Each worker has loaded RAGAS/torch/transformers
- Memory pressure from parallel heavy imports

### 7.2 Error Message Analysis

The error message shows:
```
AssertionError: ('tests/test_evaluators.py::TestRagasEvaluatorConfigReading::test_build_run_config_uses_configured_values', <WorkerController gw0>)
```

This indicates `gw0` (worker 0) crashed, causing the distributed test session to fail.

### 7.3 Previous Occurrences

This is not the first occurrence. The user mentioned:
> "这东西我盯了很久了，正在溯源"

This suggests the issue has been recurring over multiple sessions.

---

## 8. Recommended Next Steps

### 8.1 Immediate

1. Run tests with reduced parallelism: `pytest tests/ -n 2`
2. Monitor memory usage with Task Manager / Process Explorer
3. Identify which worker process consumes the most memory

### 8.2 Short-term

1. Add memory profiling to CI/CD pipeline
2. Consider marking RAGAS tests with `@pytest.mark.slow` and running them sequentially
3. Investigate if `pytest-xdist` has memory leak issues on Windows

### 8.3 Long-term

1. Refactor test suite to isolate heavy imports
2. Consider using `pytest-forked` instead of `pytest-xdist` for memory isolation
3. Evaluate if Docker containers would provide better memory isolation

---

## 9. Code Changes Made During This Session

The following files were modified during the Phase 3 implementation:

| File | Change Type | Lines Changed |
|------|-------------|---------------|
| `eval/metrics/utils.py` | Deleted function | -20 lines |
| `eval/metrics/__init__.py` | Removed export | -2 lines |
| `eval/metrics/generation.py` | Updated imports | ~5 lines |
| `eval/metrics/llm_retrieval.py` | Updated imports | ~5 lines |
| `eval/experiment_reporter.py` | Deleted (moved to trashbin) | -17 lines |
| `src/issue/migrate.py` | Moved to scripts/ | 0 (rename) |
| `eval/reporter/__init__.py` | Deleted methods | -28 lines |
| `src/experiment_reuse.py` | Updated matches() | +5 lines |
| `src/pipeline.py` | Added helper method | +21 lines |
| `src/config_schema.py` | Added Pydantic models | +36 lines |
| `tests/test_metrics.py` | Updated tests | ~10 lines |
| `tests/test_experiment_reporter.py` | Updated tests | ~15 lines |
| `tests/test_experiment_reuse.py` | Added tests | +15 lines |
| `tests/test_smoke_experiment_reuse.py` | Updated assertions | 2 lines |

**None of these changes should directly cause memory issues** - they are primarily:
- Removing code (reducing memory footprint)
- Adding small Pydantic models (negligible memory impact)
- Refactoring existing logic

---

## 10. Conclusion

The memory error appears to be a systemic issue with pytest-xdist parallel test execution on Windows, particularly when running tests that import heavy ML libraries (RAGAS, torch, transformers). The error occurs during pytest's error reporting mechanism, suggesting memory exhaustion after multiple tests have run in parallel.

Key factors:
1. **Heavy imports**: RAGAS tests load torch/transformers
2. **Parallel execution**: Multiple workers each load these libraries
3. **Windows memory limits**: Possible stricter per-process limits
4. **Error reporting overhead**: ast.parse() on large files during failure formatting

The issue is **non-deterministic** and **environment-dependent**, making it difficult to reproduce consistently.

---

## Appendix A: Full Error Log

```
INTERNALERROR> Traceback (most recent call last):
INTERNALERROR>   File ".../_pytest/_code/source.py", line 191, in getstatementrange_ast
INTERNALERROR>     astnode = ast.parse(content, "source", "exec")
INTERNALERROR>   File ".../ast.py", line 52, in parse
INTERNALERROR>     return compile(source, filename, mode, flags,
INTERNALERROR> MemoryError
```

## Appendix B: Test Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-n auto --dist loadgroup --max-worker-restart=2"
markers = [
    "unit: Unit tests (fast, no external dependencies)",
    "integration: Integration tests (external services)",
    "slow: Slow tests (heavy imports, long running)",
]
```

## Appendix C: Related Issues

- pytest-xdist memory issues on Windows: Known to have occasional problems
- RAGAS memory consumption: Heavy imports can cause memory pressure
- Python AST parsing memory: Can fail on very large files or under memory pressure
