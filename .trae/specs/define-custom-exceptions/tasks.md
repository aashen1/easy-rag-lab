# Tasks

- [x] Task 1: Create src/exceptions.py with custom exception hierarchy
  - [x] SubTask 1.1: Define RAGPipelineError base class
  - [x] SubTask 1.2: Define 8 custom exception subclasses
  - [x] SubTask 1.3: Add proper docstrings and type annotations

- [x] Task 2: Update src/__init__.py to export all exception classes

- [x] Task 3: Replace exceptions in src/pipeline.py
  - [x] SubTask 3.1: ValueError → ConfigurationError (question validation)
  - [x] SubTask 3.2: Exception from e → GenerationError (pipeline failure)

- [x] Task 4: Replace exceptions in src/retriever.py
  - [x] SubTask 4.1: ValueError → ConfigurationError (query validation)
  - [x] SubTask 4.2: Exception from e → RetrievalError (retrieval failure)

- [x] Task 5: Replace exceptions in src/hybrid_retriever.py
  - [x] SubTask 5.1: ValueError → ConfigurationError (fusion_method, weight validation)
  - [x] SubTask 5.2: ValueError → ConfigurationError (query validation)
  - [x] SubTask 5.3: Exception from e → RetrievalError (retrieval failure)

- [x] Task 6: Replace exceptions in src/bm25_retriever.py
  - [x] SubTask 6.1: ValueError → ConfigurationError (k1, b validation)
  - [x] SubTask 6.2: ValueError → RetrievalError (empty chunks, query validation)
  - [x] SubTask 6.3: RuntimeError → RetrievalError (index not built)
  - [x] SubTask 6.4: FileNotFoundError → IndexingError (chunks dir not found)
  - [x] SubTask 6.5: Exception from e → RetrievalError (retrieve failure)

- [x] Task 7: Replace exceptions in src/parser.py
  - [x] SubTask 7.1: FileNotFoundError → ParsingError (file not found)
  - [x] SubTask 7.2: ValueError → ParsingError (not a PDF)
  - [x] SubTask 7.3: Exception from e → ParsingError (parse failure)

- [x] Task 8: Replace exceptions in src/parsers/registry.py
  - [x] SubTask 8.1: TypeError → ConfigurationError (not a subclass)
  - [x] SubTask 8.2: ValueError → ConfigurationError (parser not found)
  - [x] SubTask 8.3: ImportError → ConfigurationError (import failure)

- [x] Task 9: Replace exceptions in src/parsers/pymupdf4llm_parser.py
  - [x] SubTask 9.1: FileNotFoundError → ParsingError
  - [x] SubTask 9.2: ValueError → ParsingError
  - [x] SubTask 9.3: Exception from e → ParsingError

- [x] Task 10: Replace exceptions in src/parsers/fitz_pdfplumber_parser.py
  - [x] SubTask 10.1: FileNotFoundError → ParsingError
  - [x] SubTask 10.2: ValueError → ParsingError
  - [x] SubTask 10.3: Exception from e → ParsingError

- [x] Task 11: Replace exceptions in src/generator.py
  - [x] SubTask 11.1: ValueError → ConfigurationError (query validation)
  - [x] SubTask 11.2: Exception from e → GenerationError (LLM call failure)

- [x] Task 12: Replace exceptions in src/experiment.py
  - [x] SubTask 12.1: ValueError → ConfigurationError (missing fields, validation)
  - [x] SubTask 12.2: FileNotFoundError → ConfigurationError (config file not found)
  - [x] SubTask 12.3: Update except ValueError → except ConfigurationError

- [x] Task 13: Replace exceptions in src/meal.py
  - [x] SubTask 13.1: ValueError → MealError (all meal validation)
  - [x] SubTask 13.2: FileNotFoundError → MealError (meal file not found)
  - [x] SubTask 13.3: Update except ValueError → except MealError where applicable

- [x] Task 14: Replace exceptions in src/test_set_manager.py
  - [x] SubTask 14.1: ValueError → TestSetError (all test set validation)
  - [x] SubTask 14.2: FileNotFoundError → TestSetError (test set file not found)
  - [x] SubTask 14.3: Update except FileNotFoundError → except TestSetError where applicable

- [x] Task 15: Replace exceptions in src/indexer.py
  - [x] SubTask 15.1: Exception from e → IndexingError (Qdrant init, collection, upsert, delete)
  - [x] SubTask 15.2: ValueError → IndexingError (chunk/embedding mismatch)
  - [x] SubTask 15.3: FileNotFoundError → IndexingError (chunks dir not found)

- [x] Task 16: Replace exceptions in src/embedder.py
  - [x] SubTask 16.1: Exception from e → IndexingError (model load, embed failures)
  - [x] SubTask 16.2: ValueError → ConfigurationError (input validation)

- [x] Task 17: Replace exceptions in src/chunker.py
  - [x] SubTask 17.1: ValueError → ConfigurationError (overlap validation)
  - [x] SubTask 17.2: Exception from e → ParsingError (tiktoken load failure)
  - [x] SubTask 17.3: FileNotFoundError → ParsingError (input dir not found)

- [x] Task 18: Replace exceptions in src/semantic_chunker.py
  - [x] SubTask 18.1: ValueError → ConfigurationError (embedder required)
  - [x] SubTask 18.2: Exception from e → ParsingError (tiktoken load failure)
  - [x] SubTask 18.3: FileNotFoundError → ParsingError (file not found)

- [x] Task 19: Replace exceptions in src/sampler.py
  - [x] SubTask 19.1: ValueError → ConfigurationError (sampling config validation)
  - [x] SubTask 19.2: Exception from e → ParsingError (page count failure)
  - [x] SubTask 19.3: ValueError → ConfigurationError (empty PDF list)

- [x] Task 20: Replace exceptions in src/query_rewriter.py
  - [x] SubTask 20.1: ValueError → ConfigurationError (strategy validation)
  - [x] SubTask 20.2: ValueError → ConfigurationError (query validation)
  - [x] SubTask 20.3: Exception from e → GenerationError (LLM call failure)

- [x] Task 21: Replace exceptions in src/reranker.py
  - [x] SubTask 21.1: Exception from e → IndexingError (model load failure)
  - [x] SubTask 21.2: ValueError → ConfigurationError (query validation)
  - [x] SubTask 21.3: Exception from e → RetrievalError (rerank failure)

- [x] Task 22: Replace exceptions in src/test_generator.py
  - [x] SubTask 22.1: ValueError → TestSetError (no chunks, no questions, unknown strategy)

- [x] Task 23: Replace exceptions in src/llm_client.py
  - [x] SubTask 23.1: ValueError → ConfigurationError (empty API key)
  - [x] SubTask 23.2: Exception → GenerationError (client creation failure)

- [x] Task 24: Replace exceptions in eval/metrics/generation.py
  - [x] SubTask 24.1: Exception from e → EvaluationError (LLM call failures)
  - [x] SubTask 24.2: ValueError → EvaluationError (input validation, JSON parse)

- [x] Task 25: Replace exceptions in eval/metrics/retrieval.py
  - [x] SubTask 25.1: ValueError → EvaluationError (invalid mode)

- [x] Task 26: Replace exceptions in eval/metrics/llm_retrieval.py
  - [x] SubTask 26.1: Exception from e → EvaluationError (LLM call failures)

- [x] Task 27: Replace exceptions in eval/experiment_reporter.py
  - [x] SubTask 27.1: ValueError → EvaluationError (API key required)
  - [x] SubTask 27.2: ImportError → EvaluationError (anthropic missing)
  - [x] SubTask 27.3: Exception from e → EvaluationError (LLM client init failure)

- [x] Task 28: Replace exceptions in eval/run_experiment.py
  - [x] SubTask 28.1: FileNotFoundError → ConfigurationError (exp dir, config, manifest not found)
  - [x] SubTask 28.2: ValueError → ConfigurationError (meal name missing, validation)
  - [x] SubTask 28.3: Update except ValueError/FileNotFoundError → except ConfigurationError

- [x] Task 29: Replace exceptions in eval/evaluators/ragas_evaluator.py
  - [x] SubTask 29.1: ImportError → EvaluationError (RAGAS import failures)
  - [x] SubTask 29.2: ValueError → EvaluationError (llm_config required)
  - [x] SubTask 29.3: Exception from e → EvaluationError (evaluation failure)

- [x] Task 30: Replace exceptions in eval/evaluators/builtin_evaluator.py
  - [x] SubTask 30.1: Exception from e → EvaluationError (metric calculation failure)

- [x] Task 31: Replace exceptions in eval/visualize.py
  - [x] SubTask 31.1: FileNotFoundError → EvaluationError (exp dir not found)
  - [x] SubTask 31.2: ImportError → EvaluationError (matplotlib missing)

- [ ] Task 32: Update test files - pytest.raises patterns
  - [ ] SubTask 32.1: tests/test_pipeline.py - ValueError → RetrievalError
  - [ ] SubTask 32.2: tests/test_parser.py - FileNotFoundError/ValueError/Exception → ParsingError
  - [ ] SubTask 32.3: tests/test_parsers_base.py - ValueError → ParsingError, TypeError → ParsingError
  - [ ] SubTask 32.4: tests/test_parsers_fitz_pdfplumber.py - FileNotFoundError/ValueError → ParsingError
  - [ ] SubTask 32.5: tests/test_parsers_pymupdf4llm.py - FileNotFoundError/ValueError/Exception → ParsingError
  - [ ] SubTask 32.6: tests/test_generator.py - ValueError → GenerationError, Exception → GenerationError
  - [ ] SubTask 32.7: tests/test_chunker.py - ValueError → ParsingError, FileNotFoundError → ParsingError
  - [ ] SubTask 32.8: tests/test_bm25_retriever.py - ValueError → ConfigurationError/RetrievalError, RuntimeError → RetrievalError, FileNotFoundError → IndexingError
  - [ ] SubTask 32.9: tests/test_hybrid_retriever.py - ValueError → ConfigurationError/RetrievalError
  - [ ] SubTask 32.10: tests/test_experiment.py - ValueError → ConfigurationError, FileNotFoundError → ConfigurationError, IndexError → ConfigurationError
  - [ ] SubTask 32.11: tests/test_meal.py - ValueError → MealError, FileNotFoundError → MealError
  - [ ] SubTask 32.12: tests/test_test_set_manager.py - ValueError → TestSetError, FileNotFoundError → TestSetError
  - [ ] SubTask 32.13: tests/test_metrics.py - ValueError → EvaluationError, Exception → EvaluationError
  - [ ] SubTask 32.14: tests/test_sampler.py - ValueError → ConfigurationError, Exception → ParsingError
  - [ ] SubTask 32.15: tests/test_query_rewriter.py - ValueError → ConfigurationError/GenerationError, Exception → GenerationError
  - [ ] SubTask 32.16: tests/test_test_generator.py - SystemExit → keep as-is
  - [ ] SubTask 32.17: tests/test_run_experiment.py - FileNotFoundError → ConfigurationError, ValueError → ConfigurationError/TestSetError
  - [ ] SubTask 32.18: tests/test_run_eval.py - ValueError → ConfigurationError/EvaluationError
  - [ ] SubTask 32.19: tests/test_semantic_chunker.py - ValueError → ParsingError
  - [ ] SubTask 32.20: tests/test_utils.py - ValueError → ConfigurationError, FileNotFoundError → ConfigurationError, yaml.YAMLError → keep as-is
  - [ ] SubTask 32.21: tests/test_embedder.py - ValueError → ConfigurationError, Exception → IndexingError
  - [ ] SubTask 32.22: tests/test_reranker.py - ValueError → ConfigurationError
  - [ ] SubTask 32.23: tests/test_retriever.py - ValueError → ConfigurationError, Exception → RetrievalError
  - [ ] SubTask 32.24: tests/test_indexer.py - FileNotFoundError → IndexingError, ValueError → IndexingError

- [ ] Task 33: Run lint and tests to verify all changes
  - [ ] SubTask 33.1: Run pixi run lint
  - [ ] SubTask 33.2: Run pixi run pytest tests/ -m "not integration" --tb=line -q
  - [ ] SubTask 33.3: Fix any lint/test failures

# Task Dependencies

- Task 1 MUST complete before all other tasks (exceptions.py is the foundation)
- Task 2 depends on Task 1
- Tasks 3-31 depend on Task 1 (can be parallelized)
- Task 32 depends on Tasks 3-31 (tests reference the new exception types)
- Task 33 depends on all previous tasks
