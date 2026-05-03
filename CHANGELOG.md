# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes yet._

## [0.1.16] - 2026-05-04

Diagnosis-driven development — Bad Case closed-loop analysis, hybrid parser pipeline, experiment reuse, test set consolidation.

### Added

- Bad Case closed-loop analysis: case_collector (5-file reproducible archive), trace_models (pipeline stage capture), case_diagnoser (6 root cause categories RC-0~RC-5), retrieval_analyzer, ground_truth_finder
- Query history ring buffer for CLI single-query mode with dedup and case type conversion
- Interactive QA enhancement: multi-turn chat_history from CLI → Pipeline → Generator, /badcase and /goodcase commands
- Streamlit Case Analyzer page: pipeline trace visualization, ground truth annotation, root cause diagnosis
- CompositeParser two-step architecture: primary parser + table enhancer hot-pluggable combination
- FitzParser (pure fitz primary parser) and PdfPlumberEnhancer (table enhancement module)
- Multi-criteria better_wins quality comparison (row count, empty cell ratio, merged cell ratio)
- Parser benchmark module (eval/parser_benchmark/) for standalone parser quality evaluation
- PdfPlumberEnhancer performance optimization: open PDF once instead of per-page
- Experiment report reuse: InPlaceReuseHandler, CopyMigrateHandler, ExperimentFingerprint config matching
- call_with_retry with exponential backoff for 429 rate-limit errors
- Stress test v2 with binary search for API concurrency limits (safe_max=21, default 10)
- TestSetComposer with merge, filter, and incremental compose
- testset_review package (AI reviewer + display + engine + PDF viewer)
- testset_cli unified CLI with enrich, review, approve, compose, generate, migrate subcommands
- MealManager.get_or_create_full_meal() for default meal resolution
- meals.default_name config option for auto-resolved meal
- Unify --query/--interactive/--build-index into Meal/Artifact system via auto-resolve
- chat_history parameter through RAGPipeline.query() → Generator.generate()
- save_case_with_dedup shared dedup function and chat_history support in save_case/load_case
- S9 evaluation profiling stage and config hash verification
- ResumeConfig for YAML-based resume settings
- Three-layer test system (unit / standard / all) with pytest-xdist parallel execution
- Streamlit AppTest smoke tests for UI automation (Layer 1)
- Automated workflow script for merging feature branches into dev

### Changed

- Default parser switched to pymupdf4llm + pdfplumber(text) with OCR off (experiment-verified)
- PdfPlumberEnhancer better_wins upgraded from single-dimension to multi-criteria quality comparison
- PdfPlumberEnhancer now appends tables when primary parser produces no markdown tables
- Sparse row filtering in pdfplumber table conversion to reduce noise from text strategy
- table_settings strategy override instead of setdefault in PdfPlumberEnhancer
- Interactive QA moved from main.py to src/interactive_qa.py with enhanced case collection
- Web UI qa_demo refactored to use save_case_with_dedup and pass chat_history for multi-turn
- Review tool generalized to support any test set via --input
- Shared distribution functions extracted to test_generation.distribution
- TestSetManager extended with quality_status and portable test set support
- Unified pytest config with slow marker for ragas tests
- Experiment runner integrated reuse logic and manifest

### Fixed

- Stale config in experiment prepare_meal: config_hashes mismatch now triggers rebuild
- find_full_dataset_meal now checks config_hashes to detect stale meals
- Full-parsed cache reuse with page_chunks=True
- Pipeline indexer closed before creating new one to prevent Qdrant concurrent access conflict
- Legacy mode page_chunks metadata key difference handling
- Messages.append moved after build_chat_history to prevent question duplication in multi-turn chat
- Case analyzer updated to support all case types, PDF search, and deprecated API fix
- Root cause label added to case list
- FontBBox warnings from pdfplumber suppressed
- Control characters in LLM JSON responses now handled
- Profiling stage tracking corrected for S1-S4
- Experiment log handler lifecycle management to prevent log loss
- setup_logger force parameter to preserve existing handlers
- RAGPipeline no longer calls setup_logger to prevent handler removal
- Module-level logger.remove call removed to preserve global handlers
- Duplicate log handlers prevented when setup_logger called multiple times
- PDF preview double-click issue on first open
- JS execution enabled in st.html with unsafe_allow_javascript=True
- Duplicate case saves prevented, switching between bad/good allowed
- load_config result cached to avoid repeated YAML reads and log spam
- VectorIndexer created in __init__ when meal_name is provided
- Helper functions moved before main() to fix NameError
- Testset CLI bug fixes and generate subcommand added
- YAML resume config and hash mismatch bug in evaluation
- BM25Retriever instance reuse across retrieve tests with class-scoped fixture
- resolve_chunks_dir patched in supplement tests to prevent full project directory scan

## [0.1.15] - 2026-05-01

Experiment acceleration — concurrent queries, checkpoint resume, thread-safe pipeline, Streamlit UI upgrade.

### Added

- Concurrent query evaluation via clone_for_concurrency() sharing read-only components
- Concurrent builtin evaluation with configurable worker count
- Question-level checkpoint with atomic writes for resume capability
- --resume CLI support for interrupted experiment recovery
- RAGPipeline.clone_for_concurrency() for thread-safe pipeline cloning
- VectorIndexer.reopen() and is_closed() for indexer cache reuse
- Streamlit multi-turn conversation history
- Dynamic config_overrides sidebar with lazy loading (BM25/Reranker/QueryRewriter)
- Floating navigation buttons in Streamlit UI
- Streamlit UI migration to st.html, deprecating st.components.v1.html
- recall@3/5/10 metrics
- MetricResolver graceful filtering of unavailable backends
- Unified error_handler module for evaluation system

### Changed

- deep_merge extracted to utils.py
- top_k dynamic parameter support
- BM25Retriever signature unified
- QueryRewriter auth fix
- Dead code cleanup

### Fixed

- BuiltinEvaluator configuration fix
- sanitize_name() deduplication (6x→1x)

### Refactored

- CLAUDE.md streamlined (116→76 lines)
- Docstring completion and type annotation corrections (str | None)

## [0.1.14] - 2026-04-29

Code health governance — decompose god files into packages, add strategy pattern and Pydantic validation.

### Added

- Pipeline strategy pattern: `query_rewrite_strategies.py` and `retrieval_strategies.py` replacing inline implementations
- ExperimentConfig Pydantic models in `experiment_schemas.py` replacing manual `validate()`
- Adaptive CJK quote length validation in `_validate_evidence`
- Adversarial issue filtering and proper noun suffix stripping in consistency check
- Evidence auto-supplementation for uncovered numbers and answer truncation in pipeline
- Per-type `max_tokens` and answer length limits with `_truncate_answer`
- `MISSING_INDEPENDENT_PROMPT` and `_generate_missing_question` for dedicated missing-type generation
- `max_tokens` per-call override to `Generator.generate()`
- Company name tag display in meal file list when filename lacks it
- `create_artifact_cache` factory function extracted from MealManager
- `EvaluationSample` dataclass to fix LSP violation in evaluators
- `dev-story.md` developer essay
- `release-cadence.md` version rhythm guide

### Changed

- Document directory restructured: `docs/guides/` split into `docs/user-guides/` and `docs/dev-guides/`
- Archive directory restructured by version and narrative theme
- `ExperimentResult` renamed to `ReportExperimentResult` in eval module
- `DEFAULT_EVAL_CONFIG` and `get_eval_config` unified into `metrics/utils.py`
- README rewritten with fixed root-level document links
- `version-history.md` restructured into 5-version storyline (v0.1.9–v0.1.13)
- All broken links in user-guides and dev-guides fixed

### Fixed

- `is_genuine_proper_noun` filter added to reduce false positive rate
- `save_manifest` return type annotation corrected from `None` to `bool`
- Missing `list_snapshot` and `snapshot_file` fields added to `SummaryConfig`
- Hardcoded API URL and model name removed from source code
- Test references updated from extracted class methods to standalone functions
- Mock evidence quote now includes answer values to pass validation

### Refactored

- `src/test_generator.py` (~5000 lines) → `src/test_generation/` package (9 sub-modules: generator, llm_caller, document_loader, segment_builder, models, validators, supplement, prompts, chunk_locator)
- `src/meal.py` (~1500 lines) → `src/meal/` package (6 sub-modules: manager, builders, cache, hashes, models, utils)
- `eval/run_experiment.py` (~3000 lines) → `eval/runner/` package (8 sub-modules: core, evaluation, metrics, preparation, comparison, reporting, reproduction, asset_verifier)
- `eval/experiment_reporter.py` (~1800 lines) → `eval/reporter/` package (5 sub-modules: models, formatters, llm_reporter, template_single, template_variant)
- Removed `__main__` blocks from business modules
- Removed deprecated functions from `chunk_locator.py`
- Removed redundant method-internal `import json` in `manager.py`
- Extracted `_build_pipeline` template method in MealManager
- Extracted `_post_process_question` to reduce validation duplication
- Extracted supplement logic to reduce `generator.py` below 1500 lines
- Normalized underscore prefix in `eval/runner` and `eval/metrics`
- Extracted `TestSetCleaner` from `TestSetManager`
- Ruff auto-formatting applied

## [0.1.13] - 2026-04-28

RAG visualization — interactive web UI for RAG Q&A demo.

### Added

- Streamlit Web UI with interactive RAG Q&A demo and chat_input Enter-to-send UX
- PDF preview via HTTP server + st.iframe with tab-based viewing and page jump
- Mermaid architecture diagram with Diagram/Code toggle view
- Meal file list display in web UI showing included documents
- Company name tag display in meal file list when filename lacks it

### Changed

- Issue ID system: eliminated sequence files, now derives IDs from existing issue files
- Optimized ID collision detection from full scan to on-demand check

### Fixed

- Question generation quality: largest remainder method for type distribution, dedicated prompt for irrelevant questions, LLM output type coverage validation
- RAGAS evaluation: separate samples with/without reference, Markdown table handling in context_recall sentence splitting
- Browser sandbox blocking for PDF preview via raw HTML iframe and singleton server
- Async query execution with background thread + fragment polling

## [0.1.12] - 2026-04-28

Project governance — sustainable development infrastructure.

### Added

- Distributed Issue management system with CLI (create/list/show/start/done/context)
- Issue worktree management commands
- Custom exception hierarchy in src/exceptions.py (9 business exception classes)
- project-memory skill for cross-session memory transfer
- todo-archiver skill for TODO → backlog archiving
- archive-conventions skill for consistent archiving
- CONTRIBUTING.md
- force_overwrite config for pipeline stage cache control
- MetricResolver for multi-backend metric allocation
- Adaptive segment compaction for token savings
- Question deduplication in test set generation
- Enhanced review tools: AI reviewer + PDF viewer + tiered review + progress bar

### Changed

- Migrated from backlog.md to .issues/ directory (47 active + 114 completed + 8 deferred issues)
- License changed from MIT to AGPL-3.0 (due to PyMuPDF dependency)
- Type annotations: Optional[X] → X | None (Python 3.10+)
- TODO-backlog bidirectional sync mechanism

### Fixed

- Exception chaining (B904): added `from e` in 19 files
- Issue ID collision detection and wt_id mapping

## [0.1.11] - 2026-04-26

Pipeline unification — consolidated test set generation logic.

### Added

- Adversarial question types (7 types, 0% default distribution)
- Numeric precision validation with 10x conversion error auto-detection
- Excerpt verification for ground_truth_excerpt authenticity
- Document deduplication with content overlap detection
- MealManager.find_full_dataset_meal() for full dataset meal lookup
- Auto-generation of golden test set when missing in resolve_test_set
- Golden 150-question test set with LLM-assisted + manual review
- Evidence-aware prompt with quote-based tracking and verification
- ground_truth_excerpt support for hybrid question generation

### Changed

- Unified test set generation: Golden logic merged into TestSetGenerator (script reduced from 1242 to 62 lines)
- Golden script simplified to thin CLI shell for parameter parsing only
- Artifact path migration: pipeline uses ArtifactCache for dynamic computation
- Token statistics: get_summary_by_variant() distinguishes by variant

### Fixed

- Artifact path issues in pipeline.py using ArtifactCache (BUG-026)
- Token statistics by variant (BUG-027)
- Irrelevant metrics: context_precision/recall guards, RAGAS reference fallback, expected_answer conditional fallback (BUG-029/030/031)
- LLM report generation skipped when all variants fail (FEAT-042)
- Removed deprecated parser.output_dir / chunker.input_dir / chunker.output_dir from config.yaml

## [0.1.10] - 2026-04-22

Parser renaissance — multi-parser framework and page-aware chunking.

### Added

- Parser abstraction layer: BaseParser + ParseResult + ParsedPage + ParserRegistry
- Three parsers: pymupdf4llm (page_chunks), fitz+pdfplumber (tables/headings/columns), pdfplumber (legacy)
- Page-aware chunking with page markers, heading metadata, cross-page overlap, context length control
- Artifact system: ArtifactCache + Pointer files + artifact CLI (list/pointer/info)
- Pipeline profiling system with OCR comparison experiments
- LazyDocumentLoader with mtime cache invalidation + LRU eviction
- normalize_source with include_parent parameter for directory-aware matching

### Changed

- Path migration: data/parsed → artifacts, pipeline uses ArtifactCache
- Unified tokenizer: BGETokenizerEncoder shared by chunker and embedder
- Parser hash isolation: parser options included in config hash and snapshot

### Fixed

- Cache safety: fixed ArtifactCache and parser cache pollution risks

## [0.1.9] - 2026-04-21

Evaluation dual-engine — RAGAS integration and metric system enhancement.

### Added

- RAGAS integration with 5 metrics: answer_correctness, faithfulness, context_precision, context_recall, answer_relevancy
- Evaluator abstraction layer with MetricResolver for multi-backend metric allocation
- BuiltinEvaluator enhancements: chunk/dedup/FPR/Recall@k/hallucination_rate/diversity/anomaly detection
- Dual-backend unified aggregation for context_precision / context_recall
- create_llm_client factory for unified LLM client creation
- Metric namespace prefixes for multi-backend evaluation
- Score threshold filtering for retrieval
- BGE query instruction prefix
- Configurable system prompt for Generator
- Source document names in Generator prompt

### Changed

- Extracted hardcoded LLM config values to config.yaml (RF-004)
- Code quality: ruff linter/formatter + pre-commit hooks

### Fixed

- Baseline evaluation pipeline: expect_retrieval guard, reference fallback, source separation

## [0.1.8] - 2026-04-20

Evaluation system reliability improvements and TestSetManager architecture.

### Added

- Context Precision and Context Recall metrics for RAG generation quality evaluation
- Chunk-level retrieval metrics for fine-grained evaluation
- Deduplication metrics (Dedup) and False Positive Rate (FPR)
- Equivalence group support in meal building and metric normalization
- TestSetManager system for structured test set lifecycle management
- New test_sets configuration format with automatic migration from old format
- Question validity checking to filter out unanswerable questions
- `--name` parameter for test set generation CLI
- Technology summary and improved YAML rendering in experiment reports
- Full merged config saving in experiment snapshots
- Template-based experiment configuration structure (_complete, _minimal, _preset_*)

### Changed

- Reorganized exp_configs into categorized structure (baseline/, experiments/, golden_tests/, smoke_tests/)
- Integrated Context Precision and Context Recall into evaluation pipeline
- Enhanced experiment reporter to display LLM-based retrieval metrics
- Added source_chunks field to document-level question generation
- Improved test set generation to reach target count incrementally

### Fixed

- NDCG calculation deduplication to ensure values in [0,1] range
- source_files for irrelevant/missing question types in test generator
- Chunker config hash to include strategy and semantic parameters
- Question generation not reaching target num_questions

### Refactored

- Extracted TestSetManager from run_experiment.py for better separation of concerns
- Removed validate_question and filter_valid_questions from metrics module (replaced by validity check)

## [0.1.7] - 2026-04-19

Evaluation system enhancement — document-level question generation and generation quality metrics.

### Added

- Document-level question generation strategy with 6 question types (single_fact, multi_fact, reasoning, comparative, missing, irrelevant)
- Generation quality metrics (Faithfulness, Answer Relevancy) for answer evaluation
- Question authenticity checking to filter academic-style questions
- Multi-level relevance scoring support for NDCG metric
- Industry-standard Hit Rate@k definition with configurable k parameter
- Smoke test configuration for v0.1.7+ features validation

### Changed

- Improved retrieval metrics with standard implementations (NDCG, Hit Rate, MRR)
- Decoupled question generation from chunk parameters to enable chunk-size comparison experiments
- Migrated all experiment configurations to document strategy
- Added generation metrics to golden_test configuration

### Fixed

- Qdrant storage lock conflict in variant evaluation by properly closing indexer
- Zero retrieval metrics in document-based evaluation by setting source_files field
- Question generation exceeding num_questions by distributing questions across documents
- Resolved parsed and chunks directories via ArtifactCache in test_generator

### Deprecated

- Old chunk-based question strategies (factual, boundary, multi_hop) with deprecation warnings

## [0.1.6] - 2026-04-18

Project hygiene overhaul — documentation system restructure and code quality improvements.

### Added

- Document version history and backlog tracking system
- Code quality improvements with comprehensive docstrings
- Missing type annotations to public functions
- Dynamic metric configuration in evaluation pipeline
- `show_progress` parameter for embedding operations
- Multiple test cases for edge cases (retriever, utils, indexer, metrics)

### Changed

- Documentation system restructured with clear navigation
- Spec system archived and organized
- Root-level documents simplified and consolidated
- Known bugs documentation updated and cleaned

### Fixed

- Remove trailing whitespace in chunker.py
- Suppress PytestCollectionWarning for TestCaseResult
- Use public API instead of private `_records` in test_generator

### Refactored

- Extract `detect_document_category` utility to eliminate duplication
- Use fixed vectors in mock_embedder fixture for deterministic tests
- Remove duplicate temp_project_dir fixture

## [0.1.5] - 2026-04-18

Test suite redesign — comprehensive testing framework with golden tests and best practices.

### Added

- Comprehensive test suite with ~220+ test cases
- Golden test suite for regression testing
- Integration tests for API key and meal availability checks
- Three-tier testing framework (unit/integration/e2e)
- Unit markers for test categorization

### Changed

- Removed global sys.modules mock; replaced with pytest fixtures
- Simplified test files by testing public API only
- Reduced duplicate mocks from 150 to 30 lines
- Removed duplicate tests across experiment test files

### Fixed

- Ghost folder issue by correcting output directory creation logic
- Source path normalization to make retrieval metrics functional
- Correct total_chunks off-by-one error in meal.py
- Invalid strategy name 'complex' to 'multi_hop' in chunk_comparison.yaml

### Refactored

- Simplified test files (test_experiment, test_embedder, etc.)
- Removed argparse tests from test_run_eval.py

## [0.1.4] - 2026-04-17

Token tracking system — comprehensive LLM token consumption monitoring across all scenarios.

### Added

- Token Tracking System with DetailedTokenUsage tracking
- Dual-source token tracking: API usage + tiktoken estimation
- Token cost estimation and per-category aggregation
- JSON export for token consumption data
- `token_cost` configuration section in config.yaml
- Token usage display in CLI and interactive mode

### Changed

- Integrated TokenTracker into Generator, RAGPipeline, and ExperimentReporter
- Backward compatible with optional tracker parameter

## [0.1.3] - 2026-04-17

Automated experiment system — config-driven evaluation pipeline for multi-variant comparison.

### Added

- Experiment System with config-driven pipeline
- Experiment configuration templates (exp_configs/)
- Experiment runner and reporter modules
- LLM report generation for experiment results
- Baseline evaluation configuration
- Pixi task shortcut for running experiments
- Quicktest configuration for v0.1.x rapid testing

### Changed

- Reorganized config.yaml structure
- BREAKING: Removed evaluation section from config.yaml, moved to experiment configs
- Enhanced evaluation process with index preparation and metrics computation

### Fixed

- Handle None config_path in load_config
- Handle None value in artifacts config
- Handle missing manifest file gracefully
- Normalize strategy name to support kebab-case in config
- Include num_questions in test set filename to prevent cache collision
- Resolve LLM report generation failures in experiment workflow
- Optimize LLM prompts to remove conversational filler

## [0.1.2] - 2026-04-16

Meal system — reproducible evaluation sets via content-addressable dataset management.

### Added

- Meal Data Management System for reproducible evaluation
- Test Set Generator with automated test set creation
- Meal support to RAGPipeline and evaluation system
- `--list-meals` display with data_id grouping
- `--meal-info` command to show detailed meal information
- Artifacts directory configuration
- Comprehensive documentation for architecture and meal functionality

### Changed

- Replace UUID with data_id for meal identity
- Reorganized documentation structure

### Fixed

- Flaky test in test_sampler pages mode
- Enhanced test data handling in run_evaluation function

## [0.1.1] - 2026-04-16

Sampling system — configurable PDF sampling to speed up evaluation iteration.

### Added

- Sampling System with multi-mode PDF sampling
- Count mode: sample N specific PDF files
- Pages mode: sample Y pages across PDFs
- Ratio mode: sample Z% of all PDFs
- SamplingConfig with source_filter support

### Changed

- Replace `--sample-size` with multi-mode sampling options (count/pages/ratio)
- Sampling applies across all pipeline stages (parser, chunker, indexer)
- Parser now uses pdf_files parameter instead of sample_size

## [0.1.0] - 2026-04-16

Core RAG pipeline — foundational document processing and retrieval system.

### Added

- Core RAG pipeline (PDF parsing → chunking → embedding → indexing → retrieval → generation)
- Evaluation metrics (Hit Rate, MRR, NDCG)
- Multi-LLM preset support (default, opus, sonnet, haiku)
- Single query CLI and interactive chat CLI
- Unit tests for parser, chunker, and embedder modules

### Technical Decisions

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Chunking | Fixed-size (512 tokens, overlap=0) | Simple baseline for comparison |
| Retrieval | Pure vector search (Top-K=5) | No hybrid search or reranking |
| Distance | Cosine similarity | Standard for embedding vectors |
| LLM | LongCat API via Anthropic SDK | Compatible API, easy integration |

---

[For detailed feature documentation, see docs/](docs/)
