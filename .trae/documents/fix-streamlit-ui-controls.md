# Plan: Fix Streamlit UI Sidebar Controls

## Problem

`qa_demo.py` sidebar has 4 controls that are **completely fake** — they set `st.session_state` keys but never pass values to `pipeline.query()`. The pipeline always uses `config.yaml` defaults.

Fake controls:
1. **检索策略** (vector/bm25/hybrid) — `st.session_state.retrieval_method`
2. **Top-K** (1-10) — `st.session_state.top_k`
3. **启用 Reranker** (checkbox) — `st.session_state.use_reranker`
4. **启用查询改写** (checkbox) — `st.session_state.use_query_rewrite`

## Strategy: Override Parameters + Lazy Initialization

Instead of re-creating the pipeline when settings change (expensive, defeats caching), we:
1. Add override parameters to `pipeline.query()`
2. Use **lazy initialization** for components that aren't pre-loaded (BM25 index, Reranker model, QueryRewriter)
3. Pass UI values through to `query()` on each call

## Difficulty Assessment

| Control | Difficulty | Approach |
|---------|-----------|----------|
| Top-K | ⭐ Very Easy | Pass through to `query()`, fix strategy classes to forward it |
| 检索策略 | ⭐⭐⭐ Moderate | Lazy-init BM25 index; always create BM25Retriever instance |
| 启用查询改写 | ⭐⭐ Moderate | Lazy-init QueryRewriter (LLM API, no local model) |
| 启用 Reranker | ⭐⭐⭐⭐ Hard | Lazy-load ~1GB cross-encoder model on first use |

All four are feasible. None need to be deleted.

## Implementation Steps

### Step 1: Modify `Retriever.retrieve()` to accept dynamic `top_k`

**File**: `src/retriever.py`

Current: `retrieve(self, query: str)` uses `self.top_k`
Change: Add optional `top_k` parameter that overrides `self.top_k` when provided

### Step 2: Modify `HybridRetriever.retrieve()` to accept dynamic `top_k`

**File**: `src/hybrid_retriever.py`

Current: `retrieve(self, query: str)` uses `self.top_k`
Change: Add optional `top_k` parameter that overrides `self.top_k` when provided

### Step 3: Fix strategy classes to forward `top_k`

**File**: `src/retrieval_strategies.py`

Current: `VectorRetrievalStrategy.retrieve()` ignores the `top_k` parameter
Change: Forward `top_k` to the underlying retriever for all three strategies

### Step 4: Add lazy initialization methods to `RAGPipeline`

**File**: `src/pipeline.py`

Add three methods:
- `_ensure_bm25_index()` — Build BM25 index from chunks_dir if not already built
- `_ensure_reranker()` — Load reranker model if not already loaded
- `_ensure_query_rewriter()` — Initialize QueryRewriter if not already initialized

Also store `self._chunks_dir: Path | None` during init (from meal_config) and during `build_index()`/`use_meal()`.

### Step 5: Modify `_setup_retrievers()` to always create BM25Retriever

**File**: `src/pipeline.py`

Current: BM25Retriever only created when config method is bm25/hybrid
Change: Always create BM25Retriever instance, but only build its index when needed (lazy)

### Step 6: Modify `RAGPipeline.query()` to accept override parameters

**File**: `src/pipeline.py`

New signature:
```python
def query(
    self,
    question: str,
    return_contexts: bool = True,
    retrieval_method: str | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
    use_query_rewrite: bool | None = None,
) -> dict[str, Any]:
```

Logic:
- `retrieval_method`: If provided, use it to select strategy; call `_ensure_bm25_index()` if bm25/hybrid
- `top_k`: If provided, pass to strategy's `retrieve()` call
- `use_reranker`: If True, call `_ensure_reranker()` and apply reranking
- `use_query_rewrite`: If True, call `_ensure_query_rewriter()` and apply rewriting

### Step 7: Modify `qa_demo.py` to pass UI values

**File**: `src/app_pages/qa_demo.py`

Change `pipeline.query(question)` to:
```python
result = pipeline.query(
    question,
    retrieval_method=st.session_state.retrieval_method,
    top_k=st.session_state.top_k,
    use_reranker=st.session_state.use_reranker,
    use_query_rewrite=st.session_state.use_query_rewrite,
)
```

Add error handling for lazy-init failures (e.g., BM25 index unavailable).

### Step 8: Add query rewrite strategy selector in UI

**File**: `src/app_pages/qa_demo.py`

When "启用查询改写" is checked, show a selectbox for strategy (hyde/multi_query).

### Step 9: Update tests

**File**: `tests/test_pipeline.py`

Add tests for `query()` with override parameters.

### Step 10: Run lint and tests

```bash
pixi run lint
pixi run test
```

## Key Design Decisions

1. **Lazy initialization over eager loading**: Don't load the reranker model or build BM25 index at startup. Only do it when the user actually enables the feature. First query will be slower, but startup is fast.

2. **Override parameters over config mutation**: Don't modify `self.config` when UI settings change. Pass overrides to `query()` instead. This keeps the pipeline stateless with respect to UI settings.

3. **Graceful degradation**: If BM25 index can't be built (no chunks_dir), show a clear error message in the UI instead of crashing.

4. **chunks_dir storage**: Store `_chunks_dir` during `__init__()` (from meal_config), `build_index()`, and `use_meal()`. For non-meal pipelines, try to resolve from artifact cache pointers.

## Files to Modify

1. `src/retriever.py` — Add `top_k` parameter to `retrieve()`
2. `src/hybrid_retriever.py` — Add `top_k` parameter to `retrieve()`
3. `src/retrieval_strategies.py` — Forward `top_k` to retrievers
4. `src/pipeline.py` — Add lazy init methods, override params in `query()`, always create BM25Retriever
5. `src/app_pages/qa_demo.py` — Pass UI values, add strategy selector, error handling
6. `tests/test_pipeline.py` — Add tests for override parameters
