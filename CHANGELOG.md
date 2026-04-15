# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Replaced `--sample-size` CLI parameter with three mutually exclusive sampling modes:
  - `--sample-count N`: sample N PDFs
  - `--sample-pages N`: sample PDFs until total page count reaches N
  - `--sample-ratio R`: sample R fraction of total PDFs (0.0-1.0)
- Sampling now applies end-to-end across all pipeline stages (parsing → chunking → indexing) via `source_filter` mechanism, instead of only affecting the parsing step
- Sampling automatically forces index rebuild to prevent stale data contamination

### Added

- `src/sampler.py` module with `SamplingConfig` dataclass and `determine_sample()` function
- `source_filter` parameter to `process_parsed_files()` and `VectorIndexer.build_index()` for filtering files by relative path
- `pdf_files` parameter to `parse_all_pdfs()` allowing explicit file list instead of directory scan
- Unit tests for sampler module and source_filter functionality

## [0.1.0] - 2026-04-16

### Added

#### Core Pipeline
- PDF parsing module using `pymupdf4llm` to convert PDFs to Markdown
- Text chunking module with fixed-size chunking strategy (512 tokens, overlap=0)
- Embedding module using `BAAI/bge-large-zh-v1.5` via `transformers`
- Vector storage module using `Qdrant` with local persistence
- Retrieval module with Top-K vector similarity search
- LLM generation module using `Anthropic SDK` to call Meituan LongCat API, `LongCat-Flash-Lite` Model

#### User Interfaces
- Single query CLI: `pixi run python main.py --query "question"`
- Interactive chat CLI: `pixi run python interactive.py`
- Index building CLI with options (UNTESTED): `--build-index`, `--rebuild`, `--force-parse`, `--sample-size`

#### Evaluation System
- Retrieval quality metrics: Hit Rate, MRR, NDCG
- Evaluation script: `pixi run python eval/run_eval.py`
- Test dataset with 10 sample questions covering multiple categories

#### Configuration
- Multi-LLM preset support (default, opus, sonnet, haiku)
- Centralized configuration via `config.yaml`
- Environment variable management via `.env`

#### Testing
- Unit tests for parser, chunker, and embedder modules
- Test fixtures and mock utilities

### Technical Decisions

This version implements a **"MVP RAG"** approach with intentionally simple choices:

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Chunking | Fixed-size (512 tokens, overlap=0) | Simple baseline for comparison |
| Retrieval | Pure vector search (Top-K=5) | No hybrid search or reranking |
| Distance | Cosine similarity | Standard for embedding vectors |
| LLM | LongCat API via Anthropic SDK | Compatible API, easy integration |

These choices are **intentionally basic** to establish a baseline for future optimization.

### Known Issues

1. **Evaluation Stability**: Evaluation script may encounter errors; no stable baseline metrics established yet
2. **Limited Test Dataset**: Only 10 test questions; large-scale test dataset needed
3. **Preprocessing Performance**: `PDF -> ... -> Qdrant` pipeline performance not optimized for large datasets. Given that preprocessing can be extremely slow on a personal PC, it is recommended not to prepare excessive data — for long documents such as corporate annual reports, no more than 10 files; for short documents like industry research reports, up to 50 files.
4. **Missing Generation Metrics**: Faithfulness and Answer Relevancy metrics not implemented
5. **Incomplete Test Coverage**: No unit tests for indexer, retriever, generator, or pipeline modules
6. **Test Data Placeholders**: Some `expected_answer` fields in test data contain placeholder values ("XXX亿元")

### Dependencies

- `pymupdf4llm` - PDF parsing
- `tiktoken` - Token counting
- `transformers` - Embedding model loading
- `qdrant-client` - Vector database
- `anthropic` - LLM API client
- `loguru` - Logging
- `numpy`, `torch` - Numerical computing

See `pixi.toml` for all dependencies.

### Project Structure

```
ash-easy-rag/
├── main.py              # Main CLI entry point
├── interactive.py       # Interactive chat interface
├── config.yaml          # Configuration file
├── src/                 # Core modules
│   ├── parser.py        # PDF parsing
│   ├── chunker.py       # Text chunking
│   ├── embedder.py      # Embedding generation
│   ├── indexer.py       # Vector indexing
│   ├── retriever.py     # Vector retrieval
│   ├── generator.py     # LLM generation
│   └── pipeline.py      # Pipeline orchestration
├── eval/                # Evaluation system
│   ├── metrics.py       # Evaluation metrics
│   ├── run_eval.py      # Evaluation script
│   └── test_data.json   # Test dataset
├── tests/               # Unit tests
└── data/                # Data directories
    ├── raw/             # Input PDFs
    ├── parsed/          # Parsed Markdown
    ├── chunks/          # Chunked JSONL
    └── vector_store/    # Qdrant persistence
```

### Next Steps

Planned improvements for future versions:

- Establish stable baseline evaluation metrics
- Implement generation quality metrics (Faithfulness, Answer Relevancy)
- Expand test dataset
- Hybrid retrieval (BM25 + vector)
- Reranker integration
- Query rewriting
- Semantic chunking
- Sliding window
- Prompt engineering
- Parent-child chunking
- HyDE / Multi-Query
- ......
