# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Sampling System with three modes (count/pages/ratio)
- Meal Data Management System
- Test Set Generator with LLM-assisted question generation
- Experiment System with multi-variant comparison
- Token Tracking System
- ~220+ test cases

### Changed

- Sampling now applies end-to-end across all pipeline stages
- Unified CLI entry point covering meal management, test generation, and interactive QA

### Fixed

- Fix invalid strategy name in chunk_comparison.yaml
- Fix Generator to use Anthropic API `system` parameter
- Fix RAGPipeline to properly release VectorIndexer resources
- Fix Meal total_chunks off-by-one error

## [0.1.0] - 2026-04-16

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

[详细功能说明请参阅 docs/](docs/)
