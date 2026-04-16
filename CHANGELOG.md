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

#### Meal Data Management System

- `src/meal.py` module with `MealConfig` dataclass, `MealManager`, and `ArtifactCache`
- Data version management via config hash tracking — same data + config automatically reuses Qdrant collection
- Intermediate artifact caching (parsed markdown, chunked JSONL) with deduplication across meals
- Meal CLI operations: create, load, delete, rename, copy, repair, check_status
- `--meal` parameter in `main.py` for meal-based pipeline initialization

#### Test Set Generator

- `src/test_generator.py` module with LLM-assisted question generation
- Three question strategies: `factual` (single-chunk facts), `boundary` (cross-boundary), `multi_hop` (multi-source reasoning)
- Configurable retry mechanism (max_retries=3) and seed-based reproducibility
- Test sets persisted to meal directory under `test_sets/` subdirectory

#### Experiment System

- `src/experiment.py` module with `ExperimentConfig` dataclass for experiment configuration management
- `eval/run_experiment.py` full experiment runner supporting multi-variant comparison experiments
- Automatic data preparation: meal creation if missing, test set generation if missing
- Experiment snapshots: manifest, config_snapshot, meal_snapshot, test_sets persisted to `data/exp_reports/`
- `eval/experiment_reporter.py` for report generation: template-based Markdown reports and optional LLM-generated analysis reports
- Experiment management CLI: `--list`, `--info`, `--compare`, `--reproduce`
- Experiment config files in `exp_configs/`: baseline, baseline_v01x, chunk_comparison, quicktest
- `pixi run exp <name>` pixi task for quick experiment execution

#### Testing

- Unit tests for meal, test_generator, experiment, experiment_reporter, run_eval, run_experiment modules
- End-to-end experiment test (`tests/test_e2e_experiment.py`)
- `conftest.py` with mock transformers for test isolation

### Known Issues

1. **Source Path Format Mismatch in Metrics**: Retrieved sources use relative markdown paths (e.g., `annual_report/xxx.md`) while expected sources use PDF filenames (e.g., `xxx.pdf`), causing all retrieval metrics (Hit Rate, MRR, NDCG) to always return 0
2. **Invalid Strategy Name in chunk_comparison.yaml**: Uses `"complex"` strategy which is not supported by `test_generator.py` (only `factual`, `boundary`, `multi_hop`), causing runtime `ValueError`
3. **Generator system_prompt Not Using API `system` Parameter**: `Generator.generate()` concatenates system prompt into user message instead of using Anthropic API's dedicated `system` parameter, reducing instruction-following quality
4. **Indexer Resource Not Automatically Released**: `RAGPipeline` does not call `VectorIndexer.close()`, potentially causing resource leaks and file locking issues on Windows
5. **Meal total_chunks Off-by-One**: `total_chunks` is initialized to file count instead of 0, inflating the count by the number of JSONL files
6. **Test Data Placeholders**: Some `expected_answer` fields in test data contain placeholder values ("XXX亿元")
7. **Missing Generation Metrics**: Faithfulness and Answer Relevancy metrics not implemented
8. **Incomplete Test Coverage**: No unit tests for indexer, retriever, generator, or pipeline modules

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

#### Bug Fixes (High Priority)

- Fix source path format mismatch in retrieval metrics evaluation (metrics always return 0)
- Fix invalid `"complex"` strategy name in `chunk_comparison.yaml`
- Fix `Generator.generate()` to use Anthropic API `system` parameter instead of concatenating into user message
- Fix `RAGPipeline` to properly release `VectorIndexer` resources (add context manager / `close()`)
- Fix `Meal` `total_chunks` off-by-one error (initialized to file count instead of 0)

#### Feature Improvements (Medium Priority)

- Implement generation quality metrics (Faithfulness, Answer Relevancy) using `ragas`
- Fill in placeholder values in test data (`expected_answer` fields with "XXX亿元")
- Add token statistics feature (tiktoken counting + per-model cost coefficients in config)
- Add regression testing to prevent breakage during updates
- Expand test dataset beyond 10 questions
- Optimize LLM report prompt to remove conversational artifacts ("好的……")

#### RAG Optimizations (Lower Priority)

- Establish stable baseline evaluation metrics and archive report to `notes/`
- Hybrid retrieval (BM25 + vector)
- Reranker integration
- Query rewriting
- Semantic chunking
- Sliding window
- Prompt engineering
- Parent-child chunking
- HyDE / Multi-Query
