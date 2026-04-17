# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Sampling System (`src/sampler.py`)

- `SamplingConfig` dataclass with three mutually exclusive sampling modes:
  - `count`: sample exactly N PDFs (via `random.sample`, no replacement)
  - `pages`: sample PDFs until cumulative page count reaches N (random shuffle + greedy accumulation)
  - `ratio`: sample R fraction of total PDFs, 0.0 < R ≤ 1.0 (ceil rounding, at least 1 file)
- `count_pdf_pages()` helper using PyMuPDF (`fitz`) for page counting
- `determine_sample()` function with input validation and graceful handling of unreadable PDFs
- CLI parameters: `--sample-count N`, `--sample-pages N`, `--sample-ratio R`, `--seed S`
- Sampling applies end-to-end across all pipeline stages (parsing → chunking → indexing) via `source_filter` mechanism
- Sampling automatically forces index rebuild to prevent stale data contamination
- `pdf_files` parameter to `parse_all_pdfs()` allowing explicit file list instead of directory scan
- `source_filter` parameter to `process_parsed_files()` and `VectorIndexer.build_index()` for filtering files by relative path

#### Meal Data Management System (`src/meal.py`)

- `MealConfig` dataclass with fields: `data_id`, `name`, `created_at`, `sampling_config`, `collection_name`, `pdf_files`, `config_snapshot`, `config_hashes`, `stats`
- `MealFile` dataclass with `path`, `sha256`, `size_bytes` for per-file tracking
- `MealStatus` enum: `AVAILABLE`, `FILES_MISSING`, `FILES_CHANGED`, `MIXED`
- `MealManager` class with full lifecycle management:
  - `create_meal()`: end-to-end creation (sample PDFs → compute hashes → parse → chunk → build index → save manifest), with cache hit detection at parsed and chunked levels
  - `load_meal()` / `delete_meal()`: load and delete meals; delete safely handles shared Qdrant collections
  - `rename_meal()` / `copy_meal()`: rename (directory + manifest update) and full directory copy; both preserve `data_id`
  - `repair_meal()`: interactive repair with file replacement support, option to create new meal or fix in-place, auto-rebuild index after repair
  - `check_meal_status()`: per-file existence and SHA256 verification, returns `MealStatus` + issue list
  - `find_equivalent_meals()`: find meals with same `data_id` (same dataset, different config)
  - `list_meals()` / `meal_exists()` / `get_meal_dir()`: query helpers
- `ArtifactCache` class for intermediate artifact management:
  - Directory layout: `artifacts/{data_id[:12]}/parsed/` and `artifacts/{data_id[:12]}/chunks_{chunker_hash}/`
  - `parsed_exists()` / `chunks_exist()`: verify completeness by checking expected file subsets
  - `ensure_dirs()` / `save_manifest()` / `load_manifest()`: directory and manifest management
- Data version management via config hash tracking — same data + config automatically reuses Qdrant collection
- Intermediate artifact caching with deduplication across meals sharing the same `data_id`
- Helper functions: `compute_file_sha256()`, `compute_data_id()`, `compute_parser_config_hash()`, `compute_chunker_config_hash()`, `compute_embedding_config_hash()`, `compute_index_key()`, `generate_collection_name()`, `validate_meal_name()`, `generate_timestamp_name()`
- Legacy UUID migration support in `MealConfig.from_dict()` (auto-recalculates `data_id` from PDF hashes when `uuid` field detected)
- CLI operations via `main.py`: `--create-meal`, `--meal`, `--list-meals`, `--meal-info`, `--delete-meal`, `--rename-meal`, `--copy-meal`, `--repair-meal`

#### Test Set Generator (`src/test_generator.py`)

- `TestSetGenerator` class with LLM-assisted question generation
- Three question strategies:
  - `factual` (difficulty: easy): generate questions answerable from a single chunk
  - `boundary` (difficulty: medium): generate questions requiring adjacent chunks (tests chunk boundary handling)
  - `multi_hop` (difficulty: hard): generate questions requiring non-adjacent chunks from same document (tests multi-source reasoning)
- Chunk selection logic: random sampling for factual, adjacent-pair matching for boundary, distant-pair selection (gap ≥ 2) for multi_hop
- Configurable retry mechanism (`max_retries=3`) with LLM response JSON parsing
- Seed-based reproducibility for chunk selection
- Test sets persisted to meal directory under `test_sets/` subdirectory
- Auto-reuse of existing test sets (same strategy + same count)
- CLI: `--generate-test-set`, `--strategy`, `--num-questions`

#### Experiment System (`src/experiment.py` + `eval/run_experiment.py`)

- `ExperimentConfig` dataclass with validation (name, description, data, test_sets, variants, evaluation)
- `ExperimentResult` dataclass for per-variant results
- `ExperimentManager` class for experiment lifecycle:
  - `create_experiment_dir()`, `save_snapshots()`, `load_experiment_result()`
  - `list_experiments()`, `get_experiment_info()`, `update_manifest_status()`, `save_variant_result()`
- `deep_merge()` and `merge_config()` for deep configuration merging (base config + variant overrides)
- Full experiment runner (`eval/run_experiment.py`) with 4-step workflow:
  1. Prepare Meal (auto-create if missing, supports all sampling modes)
  2. Prepare Test Sets (auto-generate if missing)
  3. Run Variant Evaluation (merge config → build index → evaluate per question)
  4. Generate Report (template-based and/or LLM-enhanced)
- Multi-variant comparison experiments with independent index management per variant
- Experiment snapshots: `manifest.json`, `config_snapshot.yaml`, `meal_snapshot.json` persisted to `data/exp_reports/`
- Asset verification for experiment reproduction: file existence, JSON/YAML validity, PDF SHA256 hash consistency
- Experiment management CLI: `--config`, `--list`, `--info`, `--compare`, `--reproduce`, `--llm-report`
- 5 experiment config files in `exp_configs/`:
  - `baseline.yaml`: standard baseline (1 variant, factual + boundary)
  - `baseline_v01x.yaml`: v0.1.x baseline (1 variant, factual + boundary + multi_hop)
  - `chunk_comparison.yaml`: chunk parameter comparison (6 variants: 256/512/1024 with various overlaps)
  - `quicktest111_v01x.yaml`: smoke test (1 question per strategy)
  - `test_llm_report_321.yaml`: LLM report feature test (3 factual + 2 boundary + 1 multi_hop, `llm_report: true`)
- `pixi run exp <name>` pixi task for quick experiment execution (auto-completes path and `.yaml` suffix)

#### Experiment Reporter (`eval/experiment_reporter.py`)

- Template-based Markdown reports with 8 sections for single-variant (overview, data sources, tech config, test set info, evaluation results, detailed comparison, conclusions, assets) and 6 sections for multi-variant comparison
- LLM-enhanced analysis reports using Anthropic SDK with detailed Chinese prompt template; automatic fallback to template report on failure
- Best variant identification and per-category metric breakdown
- Optimization recommendations based on performance level

#### Token Tracking System (`src/token_tracker.py`)

- `TokenUsage` dataclass: input, output, total token counts
- `DetailedTokenUsage` dataclass: system_prompt, contexts, query token estimation (proportional scaling from API-reported totals via tiktoken)
- `TokenRecord` dataclass: single LLM call record with category, model, metadata
- `TokenTracker` class: accumulator with per-category summarization, cost estimation (configurable per-model pricing), formatted output, serialization, merge, and reset
- Integrated into `Generator` (per-call tracking) and `Pipeline` (session-level accumulation)
- Cost configuration in `config.yaml`: per-model input/output pricing and cost coefficient
- Token usage display in query results (detailed breakdown) and experiment reports

#### Enhanced CLI (`main.py`)

- Unified CLI entry point with all operations:
  - Query: `--query`, `--llm-preset`
  - Index: `--build-index`, `--rebuild`, `--force-parse`
  - Sampling: `--sample-count`, `--sample-pages`, `--sample-ratio`, `--seed`
  - Meal management: `--create-meal`, `--meal`, `--list-meals`, `--meal-info`, `--delete-meal`, `--rename-meal`, `--copy-meal`, `--repair-meal`
  - Test generation: `--generate-test-set`, `--strategy`, `--num-questions`
- Interactive QA mode: auto-enters when `--meal` is specified without `--query`
- Meal status check before use (warns on missing/changed files)
- Token usage display in query output with detailed breakdown

#### Testing

- ~220+ test cases across 12 test files
- `conftest.py` with global `transformers` mock via `sys.modules` injection for test isolation
- Unit tests for: parser (12 cases), chunker (19 cases), embedder (12 cases), sampler (24 cases), meal (50 cases), test_generator (19 cases), token_tracker (31 cases), experiment (55 cases), experiment_reporter (37 cases), run_eval (12 cases), run_experiment (23 cases)
- End-to-end experiment test (`test_e2e_experiment.py`, 18 cases, marked `@pytest.mark.integration`)
- pytest markers: `integration` (exclude with `-m "not integration"`), `slow` (exclude with `-m "not slow"`)

#### Configuration & Infrastructure

- Token cost configuration in `config.yaml` with per-model pricing (LongCat-Flash-Lite, claude-3-opus, claude-3-5-sonnet, claude-3-haiku)
- Experiment and meal directory configuration in `config.yaml` (`experiments.dir`, `meals.dir`, `artifacts.dir`)
- Test generation defaults in `config.yaml` (`default_strategy`, `default_num_questions`, `max_retries`)
- `pixi run exp <name>` convenience task with auto path completion
- `pytest.ini` with `integration` and `slow` markers

### Changed

- Replaced `--sample-size` CLI parameter with three mutually exclusive sampling modes (`--sample-count`, `--sample-pages`, `--sample-ratio`)
- Sampling now applies end-to-end across all pipeline stages (parsing → chunking → indexing) via `source_filter` mechanism, instead of only affecting the parsing step
- Sampling automatically forces index rebuild to prevent stale data contamination
- `RAGPipeline.build_index()` accepts `SamplingConfig` and propagates `source_filter` through all stages
- `RAGPipeline` integrates `TokenTracker` for session-level token accumulation
- `Generator` tracks detailed token usage per call via `TokenTracker` integration
- `main.py` expanded from simple query/index CLI to unified entry point covering meal management, test generation, and interactive QA

### Known Issues

1. **Source Path Format Mismatch in Metrics**: Retrieved sources use relative markdown paths (e.g., `annual_report/xxx.md`) while expected sources use PDF filenames (e.g., `xxx.pdf`), causing all retrieval metrics (Hit Rate, MRR, NDCG) to always return 0
2. **Test Data Placeholders**: Some `expected_answer` fields in test data contain placeholder values ("XXX亿元")
3. **Missing Generation Metrics**: Faithfulness and Answer Relevancy metrics not implemented
4. **Incomplete Test Coverage**: No unit tests for `indexer`, `retriever`, `generator`, `pipeline`, or `eval/metrics` modules; `test_test_generator.py` does not test the `generate_test_set` main entry method; `test_run_eval.py` only tests config loading, not evaluation execution
5. **NDCG Simplified Implementation**: Current NDCG uses binary relevance (gain=1.0 for all hits), no graded relevance support
6. **Hit Rate Definition Non-standard**: Current Hit Rate calculates "fraction of expected documents retrieved" (recall-oriented) rather than the standard "fraction of queries with at least one hit" (Hit Rate@K)
7. **Evaluation Metrics Config Not Used**: `evaluation.metrics.retrieval` list in experiment config is declared but not dynamically applied; all three metrics are hardcoded
8. **Category Logic Duplication**: Document category detection (annual_report/research_report) is hardcoded and duplicated in both `parser.py` and `chunker.py`
9. **Embedder show_progress Unused**: `Embedder.embed_texts()` accepts `show_progress` parameter but does not implement progress display

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

1. **Preprocessing Performance**: `PDF -> ... -> Qdrant` pipeline performance not optimized for large datasets. Given that preprocessing can be extremely slow on a personal PC, it is recommended not to prepare excessive data — for long documents such as corporate annual reports, no more than 10 files; for short documents like industry research reports, up to 50 files.

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

#### Feature Improvements (Medium Priority)

- Implement generation quality metrics (Faithfulness, Answer Relevancy) using `ragas`
- Fill in placeholder values in test data (`expected_answer` fields with "XXX亿元")
- Expand test dataset beyond 10 questions

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
