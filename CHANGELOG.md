# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes yet._

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
