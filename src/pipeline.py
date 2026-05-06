from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.bm25_retriever import BM25Retriever
from src.chunker import process_parsed_files
from src.embedder import Embedder
from src.exceptions import RetrievalError
from src.generator import Generator
from src.hybrid_retriever import HybridRetriever
from src.indexer import VectorIndexer
from src.parser import parse_all_pdfs_unified
from src.query_rewrite_strategies import (
    HyDERewriteStrategy,
    MultiQueryRewriteStrategy,
    NoRewriteStrategy,
    QueryRewriteStrategy,
)
from src.query_rewriter import QueryRewriter
from src.retrieval_strategies import (
    BM25RetrievalStrategy,
    HybridRetrievalStrategy,
    RetrievalStrategy,
    VectorRetrievalStrategy,
)

if TYPE_CHECKING:
    from eval.pipeline_profiler import PipelineProfiler
    from src.meal import MealConfig
from src.reranker import Reranker
from src.retriever import Retriever
from src.sampler import SamplingConfig, determine_sample
from src.semantic_chunker import process_parsed_files_semantic
from src.token_tracker import TokenTracker
from src.trace_models import PipelineTrace, TraceStep
from src.utils import get_llm_config, load_config


class RAGPipeline:
    def __init__(
        self,
        config: str | dict[str, Any] | None = None,
        llm_preset: str | None = None,
        meal_name: str | None = None,
        token_tracker: TokenTracker | None = None,
        profiler: PipelineProfiler | None = None,
        embedder: Embedder | None = None,
    ):
        """Initialize the RAG pipeline with all components.

        Sets up the embedding model, vector indexer, retrievers (vector/BM25/hybrid),
        optional reranker, optional query rewriter, and the LLM generator. When a
        meal_name is provided, loads the pre-built Meal's vector collection instead
        of creating a new one.

        Args:
            config: Configuration source. Can be:
                - ``None``: Load from default ``"config.yaml"``
                - ``str``: Path to a YAML configuration file
                - ``dict``: Configuration dictionary (e.g., merged experiment config)
            llm_preset: Optional LLM preset name from config. When None, uses
                the default preset.
            meal_name: Optional name of a pre-built Meal to load. When provided,
                the pipeline uses the Meal's existing vector collection.
            token_tracker: Optional TokenTracker for recording LLM API usage.
                When None, creates a new TokenTracker instance.
            profiler: Optional PipelineProfiler for performance profiling.
            embedder: Optional pre-initialized Embedder instance to share
                across pipelines. When provided, skips model loading (~1.3 GB
                saved per variant in experiments).

        Raises:
            ConfigurationError: If the config file is invalid or missing.
            Exception: If any component fails to initialize.
        """
        if config is None:
            config = "config.yaml"

        if isinstance(config, str):
            self.config = load_config(config)
        else:
            self.config = config

        self.llm_preset = llm_preset
        self.meal_name = meal_name
        self.meal_config = None
        self._chunks_dir: Path | None = None
        self.token_tracker = (
            token_tracker if token_tracker is not None else TokenTracker()
        )
        self.profiler = profiler

        logger.info("Initializing RAG Pipeline")

        if embedder is not None:
            self.embedder = embedder
            self._shared_embedder = True
            logger.debug("Using shared Embedder instance")
        else:
            embedding_config = self.config["embedding"]
            self.embedder = Embedder(
                model_name=embedding_config["model_name"],
                device=embedding_config["device"],
                query_instruction=embedding_config.get("query_instruction"),
            )
            self._shared_embedder = False

        vector_store_config = self.config["vector_store"]
        collection_name = vector_store_config["collection_name"]

        if meal_name is not None:
            from src.meal import MealManager

            meal_manager = MealManager(self.config)
            self.meal_config = meal_manager.load_meal(meal_name)
            collection_name = self.meal_config.collection_name
            logger.info(
                f"Using meal '{meal_name}' (data_id: {self.meal_config.data_id[:12]}, collection: {collection_name})"
            )

            from src.meal import create_artifact_cache

            cache = create_artifact_cache(self.config)
            chunker_hash = self.meal_config.config_hashes.get("chunker", "")
            self._chunks_dir = cache.get_chunks_dir(
                self.meal_config.data_id, chunker_hash
            )

            self.indexer = VectorIndexer(
                persist_dir=vector_store_config["persist_dir"],
                collection_name=collection_name,
                distance=vector_store_config["distance"],
            )
        else:
            self._chunks_dir = None
            self.indexer: VectorIndexer | None = None

        self._setup_retrievers()

        llm_config = get_llm_config(self.config, llm_preset)
        self.generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=llm_config["temperature"],
            max_tokens=llm_config["max_tokens"],
            token_tracker=self.token_tracker,
            system_prompt=self.config.get("generation", {}).get("system_prompt"),
            max_context_tokens=self.config.get("generation", {}).get(
                "max_context_tokens"
            ),
        )

        logger.success("RAG Pipeline initialized successfully")

    def _setup_retrievers(self) -> None:
        """Set up retrievers based on the current retrieval config.

        Creates vector, BM25, and hybrid retrievers as needed based on
        ``self.config["retrieval"]["method"]``. Called during initialization
        and when the config is hot-swapped during experiments.
        """
        retrieval_config = self.config["retrieval"]
        retrieval_method = retrieval_config.get("method", "vector")
        top_k = retrieval_config["top_k"]

        self.retriever = Retriever(
            indexer=self.indexer,
            embedder=self.embedder,
            top_k=top_k,
            score_threshold=retrieval_config.get("score_threshold", 0),
        )

        self.bm25_retriever: BM25Retriever | None = None
        self.hybrid_retriever: HybridRetriever | None = None
        self.retrieval_method = retrieval_method

        bm25_config = retrieval_config.get("bm25", {})
        self.bm25_retriever = BM25Retriever(
            k1=bm25_config.get("k1", 1.5),
            b=bm25_config.get("b", 0.75),
        )

        if retrieval_method == "hybrid":
            hybrid_config = retrieval_config.get("hybrid", {})
            self.hybrid_retriever = HybridRetriever(
                vector_retriever=self.retriever,
                bm25_retriever=self.bm25_retriever,
                fusion_method=hybrid_config.get("fusion", "rrf"),
                rrf_k=hybrid_config.get("rrf_k", 60),
                vector_weight=hybrid_config.get("vector_weight", 0.7),
                bm25_weight=hybrid_config.get("bm25_weight", 0.3),
                top_k=top_k,
            )

        self.reranker: Reranker | None = None
        reranker_config = retrieval_config.get("reranker", {})
        if reranker_config.get("enabled", False):
            self.reranker = Reranker(
                model_name=reranker_config.get("model_name", "BAAI/bge-reranker-large"),
                device=reranker_config.get("device", "cuda"),
            )
            self.reranker_top_n = reranker_config.get("top_n", top_k)

        self.query_rewriter: QueryRewriter | None = None
        rewrite_config = retrieval_config.get("query_rewrite", {})
        if rewrite_config.get("enabled", False):
            llm_config = get_llm_config(self.config, self.llm_preset)
            self.query_rewriter = QueryRewriter(
                strategy=rewrite_config.get("strategy", "hyde"),
                llm_model_name=llm_config["model_name"],
                llm_api_key=llm_config["api_key"],
                llm_base_url=llm_config["base_url"],
                llm_temperature=llm_config.get("temperature", 0.0),
                llm_max_tokens=llm_config.get("max_tokens", 512),
                num_queries=rewrite_config.get("num_queries", 3),
                token_tracker=self.token_tracker,
            )

    def build_index(
        self,
        rebuild: bool = False,
        force_parse: bool = False,
        sampling_config: SamplingConfig | None = None,
    ) -> None:
        """Build the vector index from raw PDFs through the full pipeline.

        Executes three steps in order: PDF parsing, document chunking, and
        vector index construction. When a sampling configuration is provided,
        the index is always rebuilt and only the sampled PDFs are processed.

        Args:
            rebuild: Whether to recreate the vector collection from scratch.
            force_parse: Whether to force re-parsing of PDFs even if parsed
                output already exists.
            sampling_config: Optional sampling configuration to select a subset
                of PDFs. When provided, ``rebuild`` is forced to True.

        Raises:
            FileNotFoundError: If the configured input directory does not exist.
            Exception: If any step (parse, chunk, index) fails.
        """
        logger.info("Building vector index...")

        parser_config = self.config["parser"]
        chunker_config = self.config["chunker"]
        embedding_config = self.config["embedding"]

        if sampling_config is not None:
            rebuild = True
            logger.info("Sampling enabled - forcing index rebuild")

        sampled_pdf_files = None
        if sampling_config is not None:
            input_path = Path(parser_config["input_dir"])
            all_pdfs = list(input_path.rglob("*.pdf"))
            sampled_pdf_files = determine_sample(all_pdfs, sampling_config)
            logger.info(
                f"Sampled {len(sampled_pdf_files)} PDFs from {len(all_pdfs)} total"
            )

        from src.meal import (
            MealFile,
            compute_chunker_config_hash,
            compute_data_id,
            compute_file_sha256,
            compute_parser_config_hash,
            create_artifact_cache,
        )

        cache = create_artifact_cache(self.config)
        raw_dir = cache.raw_dir
        all_pdf_files = sorted(raw_dir.rglob("*.pdf"))
        meal_files = []
        for pdf_path in all_pdf_files:
            try:
                rel = pdf_path.relative_to(raw_dir).as_posix()
                sha = compute_file_sha256(pdf_path)
                meal_files.append(
                    MealFile(path=rel, sha256=sha, size_bytes=pdf_path.stat().st_size)
                )
            except Exception:
                continue
        data_id = compute_data_id(meal_files)

        algorithm = parser_config.get("algorithm", "pymupdf4llm")
        parser_options = parser_config.get(algorithm, {})

        parser_hash = compute_parser_config_hash(
            {
                "algorithm": algorithm,
                "options": parser_options,
            }
        )
        parsed_dir = cache.get_parsed_dir(data_id, parser_hash)

        logger.info("Step 1: Parsing PDFs...")
        parse_results = parse_all_pdfs_unified(
            input_dir=parser_config["input_dir"],
            artifacts_dir=str(cache.artifacts_dir),
            algorithm=algorithm,
            force=force_parse,
            parser_options=parser_options,
        )

        source_filter_md = None
        if sampling_config is not None:
            source_filter_md = set()
            for r in parse_results:
                if r.get("output"):
                    output_path = Path(r["output"])
                    source_filter_md.add(output_path.relative_to(parsed_dir).as_posix())
            logger.info(f"Source filter for chunker: {len(source_filter_md)} files")

        use_page_chunks = bool(parser_options.get("page_chunks", False))

        chunker_hash = compute_chunker_config_hash(
            {
                "chunk_size": chunker_config.get("chunk_size", 512),
                "chunk_overlap": chunker_config.get("chunk_overlap", 0),
                "encoding": chunker_config.get("encoding", "cl100k_base"),
            }
        )
        chunks_dir = cache.get_chunks_dir(data_id, chunker_hash)

        logger.info("Step 2: Chunking documents...")
        chunker_strategy = chunker_config.get("strategy", "fixed")
        chunker_encoding = chunker_config.get("encoding", "cl100k_base")
        embedding_model_name = embedding_config.get("model_name")

        if use_page_chunks and chunker_strategy != "semantic":
            from src.chunker import process_parsed_files_page_aware

            source_filter_pages = None
            if sampling_config is not None:
                source_filter_pages = set()
                for r in parse_results:
                    if r.get("output"):
                        output_path = Path(r["output"])
                        source_filter_pages.add(
                            output_path.relative_to(parsed_dir).as_posix()
                        )

            chunk_results = process_parsed_files_page_aware(
                input_dir=str(parsed_dir),
                output_dir=str(chunks_dir),
                chunk_size=chunker_config["chunk_size"],
                overlap=chunker_config["chunk_overlap"],
                encoding_name=chunker_encoding,
                source_filter=source_filter_pages,
                model_name=embedding_model_name,
                cross_page_overlap=chunker_config.get("cross_page_overlap", 0),
            )
        elif chunker_strategy == "semantic":
            semantic_config = chunker_config.get("semantic", {})
            chunk_results = process_parsed_files_semantic(
                input_dir=str(parsed_dir),
                output_dir=str(chunks_dir),
                embedder=self.embedder,
                chunk_size=chunker_config["chunk_size"],
                similarity_threshold=semantic_config.get("similarity_threshold", 0.5),
                breakpoint_percentile=semantic_config.get("breakpoint_percentile"),
                min_chunk_size=semantic_config.get("min_chunk_size", 100),
                source_filter=source_filter_md,
            )
        else:
            chunk_results = process_parsed_files(
                input_dir=str(parsed_dir),
                output_dir=str(chunks_dir),
                chunk_size=chunker_config["chunk_size"],
                overlap=chunker_config["chunk_overlap"],
                encoding_name=chunker_encoding,
                source_filter=source_filter_md,
                model_name=embedding_model_name,
            )

        source_filter_jsonl = None
        if sampling_config is not None:
            source_filter_jsonl = set()
            for r in chunk_results:
                if r.get("output"):
                    output_path = Path(r["output"])
                    source_filter_jsonl.add(
                        output_path.relative_to(chunks_dir).as_posix()
                    )
            logger.info(f"Source filter for indexer: {len(source_filter_jsonl)} files")

        if sampling_config is None:
            relative_chunks = f"{data_id[:16]}/chunks_{chunker_hash}"
            cache.save_pointer("full_chunks", relative_chunks)

        if self.profiler:
            self.profiler.begin_stage("S3")

        logger.info("Step 3: Building vector index...")
        if self.indexer is None:
            vector_store_config = self.config["vector_store"]
            self.indexer = VectorIndexer(
                persist_dir=vector_store_config["persist_dir"],
                collection_name=vector_store_config["collection_name"],
                distance=vector_store_config["distance"],
            )
            self._setup_retrievers()

        import json as _json

        from src.core.ops.index import index_chunks

        _all_chunks: list[dict] = []
        _chunks_path = Path(str(chunks_dir))
        if _chunks_path.exists():
            for _jsonl_file in _chunks_path.rglob("*.jsonl"):
                if (
                    source_filter_jsonl is not None
                    and _jsonl_file.relative_to(_chunks_path).as_posix()
                    not in source_filter_jsonl
                ):
                    continue
                try:
                    with open(_jsonl_file, encoding="utf-8") as _f:
                        for _line in _f:
                            _all_chunks.append(_json.loads(_line.strip()))
                except Exception as _e:
                    logger.error(f"Failed to load {_jsonl_file}: {str(_e)}")
                    continue

        if _all_chunks:
            index_chunks(
                _all_chunks,
                self.embedder,
                collection_name=self.indexer.collection_name,
                batch_size=embedding_config["batch_size"],
                recreate=rebuild,
                indexer=self.indexer,
            )

        if self.profiler:
            self.profiler.end_stage()

        if (
            self.retrieval_method in ("bm25", "hybrid")
            and self.bm25_retriever is not None
        ):
            if self.profiler:
                self.profiler.begin_stage("S4")
            logger.info("Step 4: Building BM25 index...")
            self.bm25_retriever.build_index_from_chunks(
                chunks_dir=str(chunks_dir),
                source_filter=source_filter_jsonl,
            )
            if self.profiler:
                self.profiler.end_stage()

        logger.success("Index built successfully")
        self._chunks_dir = chunks_dir
        if sampling_config is None:
            logger.info(
                f"Artifacts: parsed={parsed_dir}, chunks={chunks_dir} "
                f"| Pointers: data/artifacts/_pointers/full_parsed.pointer, "
                f"data/artifacts/_pointers/full_chunks.pointer"
            )

    def close(self) -> None:
        """Close the pipeline and release all heavy resources.

        Releases the Qdrant client, embedding model weights, BM25 index
        data, and reranker model weights.  After calling this method the
        pipeline instance must not be reused.
        """
        import gc

        if hasattr(self, "indexer") and self.indexer is not None:
            self.indexer.close()
            self.indexer = None
            logger.debug("RAGPipeline indexer closed")

        if hasattr(self, "bm25_retriever") and self.bm25_retriever is not None:
            self.bm25_retriever.clear()
            self.bm25_retriever = None
            logger.debug("RAGPipeline BM25 retriever cleared")

        if hasattr(self, "reranker") and self.reranker is not None:
            self.reranker.unload()
            self.reranker = None
            logger.debug("RAGPipeline reranker unloaded")

        if hasattr(self, "embedder") and self.embedder is not None:
            if not getattr(self, "_shared_embedder", False):
                self.embedder.unload()
            self.embedder = None
            logger.debug("RAGPipeline embedder released")

        gc.collect()
        logger.info("RAGPipeline closed, all heavy resources released")

    def clone_for_concurrency(self) -> RAGPipeline:
        """Create a lightweight clone for concurrent query execution.

        Shares the indexer (Qdrant client, thread-safe for reads) and
        embedder (stateless inference) with the original. Creates new
        instances of components that hold per-call state (generator,
        reranker, query_rewriter). The cloned pipeline must NOT call
        ``close()`` — only the original owner should close the shared
        indexer.

        Returns:
            A new RAGPipeline instance suitable for use in a separate thread.

        Raises:
            ConfigurationError: If the LLM config is missing or invalid.
        """
        clone = RAGPipeline.__new__(RAGPipeline)
        clone.config = self.config
        clone.meal_name = self.meal_name
        clone.meal_config = self.meal_config
        clone._chunks_dir = self._chunks_dir

        clone.indexer = self.indexer
        clone.embedder = self.embedder
        clone.token_tracker = self.token_tracker
        clone.profiler = self.profiler

        clone._setup_retrievers()

        llm_config = get_llm_config(self.config, self.llm_preset)
        clone.generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=llm_config["temperature"],
            max_tokens=llm_config["max_tokens"],
            token_tracker=clone.token_tracker,
            system_prompt=self.config.get("generation", {}).get("system_prompt"),
            max_context_tokens=self.config.get("generation", {}).get(
                "max_context_tokens"
            ),
        )

        clone.reranker = None
        clone.query_rewriter = None

        logger.debug("Created lightweight pipeline clone for concurrent execution")
        return clone

    def __enter__(self) -> RAGPipeline:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    def use_meal(self, meal_name: str) -> MealConfig:
        """Switch the pipeline to use a pre-built Meal's vector collection.

        Closes the current indexer and creates a new one pointing to the
        Meal's collection. The retriever is also re-created to reference the
        new indexer.

        Args:
            meal_name: Name of the Meal to load.

        Returns:
            MealConfig: The configuration of the loaded Meal.

        Raises:
            Exception: If the Meal does not exist or fails to load.
        """
        from src.meal import MealManager

        if hasattr(self, "indexer") and self.indexer is not None:
            self.indexer.close()

        meal_manager = MealManager(self.config)
        self.meal_config = meal_manager.load_meal(meal_name)
        self.meal_name = meal_name

        from src.meal import create_artifact_cache

        cache = create_artifact_cache(self.config)
        chunker_hash = self.meal_config.config_hashes.get("chunker", "")
        self._chunks_dir = cache.get_chunks_dir(self.meal_config.data_id, chunker_hash)

        vector_store_config = self.config["vector_store"]
        self.indexer = VectorIndexer(
            persist_dir=vector_store_config["persist_dir"],
            collection_name=self.meal_config.collection_name,
            distance=vector_store_config["distance"],
        )

        self._setup_retrievers()

        if (
            self.retrieval_method in ("bm25", "hybrid")
            and self.bm25_retriever is not None
        ):
            from src.meal import create_artifact_cache

            cache = create_artifact_cache(self.config)
            chunker_hash = self.meal_config.config_hashes.get("chunker", "")
            chunks_dir = cache.get_chunks_dir(self.meal_config.data_id, chunker_hash)
            if chunks_dir.exists():
                self.bm25_retriever.build_index_from_chunks(str(chunks_dir))
            else:
                logger.warning(f"Chunks dir not found for BM25: {chunks_dir}")

            if self.retrieval_method == "hybrid" and self.hybrid_retriever is not None:
                self.hybrid_retriever = HybridRetriever(
                    vector_retriever=self.retriever,
                    bm25_retriever=self.bm25_retriever,
                    fusion_method=self.config["retrieval"]
                    .get("hybrid", {})
                    .get("fusion", "rrf"),
                    rrf_k=self.config["retrieval"].get("hybrid", {}).get("rrf_k", 60),
                    vector_weight=self.config["retrieval"]
                    .get("hybrid", {})
                    .get("vector_weight", 0.7),
                    bm25_weight=self.config["retrieval"]
                    .get("hybrid", {})
                    .get("bm25_weight", 0.3),
                    top_k=self.config["retrieval"]["top_k"],
                )

        logger.info(
            f"Switched to meal '{meal_name}' (data_id: {self.meal_config.data_id[:12]}, collection: {self.meal_config.collection_name})"
        )
        return self.meal_config

    def query(
        self,
        question: str,
        return_contexts: bool = True,
        config_overrides: dict[str, Any] | None = None,
        chat_history: list[dict[str, str]] | None = None,
        capture_trace: bool = False,
    ) -> dict[str, Any]:
        """Execute a RAG query: retrieve relevant contexts and generate an answer.

        When ``config_overrides`` is provided, the overrides are deep-merged
        with the pipeline's base config to produce an *effective config* that
        drives this single query.  This allows callers to experiment with
        different retrieval methods, top-k values, reranker settings, etc.
        without re-initialising the pipeline.

        Args:
            question: The user question to answer. Must be a non-empty string.
            return_contexts: Whether to include retrieved contexts, scores, and
                sources in the response dictionary. Defaults to True.
            config_overrides: Optional dictionary of config overrides to
                deep-merge with ``self.config`` for this query only. When
                None, the pipeline's base config is used unchanged.
            chat_history: Optional conversation history for multi-turn context.
                Format: ``[{"role": "user"/"assistant", "content": "..."}]``.
                Passed through to ``Generator.generate()``.
            capture_trace: When True, records detailed timing and data at each
                pipeline stage (query_rewrite, retrieval, rerank,
                context_assembly, generation) and includes a ``trace`` key in
                the response dictionary. Defaults to False.

        Returns:
            A dictionary containing at minimum ``question`` and ``answer`` keys.
            When ``return_contexts`` is True, also includes ``contexts``,
            ``scores``, ``sources``, ``chunk_ids``, and optionally ``token_usage``.
            When ``capture_trace`` is True, also includes ``trace`` with the
            full pipeline trace data.

        Raises:
            RetrievalError: If ``question`` is empty or not a string, or if
                retrieval / generation fails.
        """
        if not question or not isinstance(question, str):
            error_msg = "Question must be a non-empty string"
            logger.error(error_msg)
            raise RetrievalError(error_msg)

        try:
            logger.info(f"Processing query: {question[:50]}...")

            trace = None
            if capture_trace:
                trace = PipelineTrace(
                    trace_id=f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(question) % 10000:04d}",
                    question=question,
                )

            if config_overrides is not None:
                from src.utils import deep_merge

                effective_config = deep_merge(self.config, config_overrides)
                logger.debug(f"Using config overrides: {config_overrides}")
            else:
                effective_config = self.config

            effective_retrieval = effective_config.get("retrieval", {})
            effective_method = effective_retrieval.get("method", "vector")
            effective_top_k = effective_retrieval.get("top_k", 5)
            effective_reranker_enabled = effective_retrieval.get("reranker", {}).get(
                "enabled", False
            )
            effective_rewrite_enabled = effective_retrieval.get(
                "query_rewrite", {}
            ).get("enabled", False)
            effective_rewrite_strategy = effective_retrieval.get(
                "query_rewrite", {}
            ).get("strategy", "hyde")

            if effective_rewrite_enabled:
                self._ensure_query_rewriter(effective_rewrite_strategy)
                rewrite_strategy = self._get_rewrite_strategy()
            else:
                rewrite_strategy = NoRewriteStrategy()

            t0 = time.perf_counter()
            rewritten = rewrite_strategy.rewrite(question)
            if capture_trace and effective_rewrite_enabled:
                trace.steps.append(
                    TraceStep(
                        stage="query_rewrite",
                        input_data={"original_question": question},
                        output_data={
                            "rewritten_queries": rewritten.queries,
                            "is_multi": rewritten.is_multi,
                        },
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        metadata={"strategy": type(rewrite_strategy).__name__},
                    )
                )

            if effective_method in ("bm25", "hybrid"):
                self._ensure_bm25_index()

            if effective_method == "bm25" and self.bm25_retriever is not None:
                retrieval_strategy = BM25RetrievalStrategy(self.bm25_retriever)
            elif effective_method == "hybrid" and self.bm25_retriever is not None:
                if self.hybrid_retriever is None:
                    hybrid_config = effective_retrieval.get("hybrid", {})
                    self.hybrid_retriever = HybridRetriever(
                        vector_retriever=self.retriever,
                        bm25_retriever=self.bm25_retriever,
                        fusion_method=hybrid_config.get("fusion", "rrf"),
                        rrf_k=hybrid_config.get("rrf_k", 60),
                        vector_weight=hybrid_config.get("vector_weight", 0.7),
                        bm25_weight=hybrid_config.get("bm25_weight", 0.3),
                        top_k=effective_top_k,
                    )
                retrieval_strategy = HybridRetrievalStrategy(self.hybrid_retriever)
            else:
                retrieval_strategy = VectorRetrievalStrategy(self.retriever)

            is_multi = rewritten.is_multi

            if not is_multi:
                logger.debug("Retrieving relevant contexts...")
            if not is_multi and self.profiler:
                self.profiler.begin_stage("S6")

            t0 = time.perf_counter()
            if is_multi:
                results = self._retrieve_multi(
                    retrieval_strategy, rewritten.queries, effective_top_k
                )
            else:
                results = retrieval_strategy.retrieve(
                    rewritten.queries[0], effective_top_k
                ).chunks
            if capture_trace:
                trace.steps.append(
                    TraceStep(
                        stage="retrieval",
                        input_data={
                            "query": (
                                rewritten.queries[0]
                                if not is_multi
                                else rewritten.queries
                            ),
                            "top_k": effective_top_k,
                        },
                        output_data={
                            "results": [
                                {
                                    "chunk_id": r.get("chunk_id", ""),
                                    "score": r["score"],
                                    "source": r["metadata"].get("source", ""),
                                }
                                for r in results
                            ],
                            "count": len(results),
                        },
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        metadata={"method": effective_method},
                    )
                )

            if effective_reranker_enabled and results:
                self._ensure_reranker()
                logger.debug(
                    f"Reranking {'multi-query ' if is_multi else ''}results..."
                )
                t0 = time.perf_counter()
                pre_rerank_count = len(results)
                pre_rerank_snapshot = [
                    {
                        "chunk_id": r.get("chunk_id", ""),
                        "score": r["score"],
                        "source": r["metadata"].get("source", ""),
                    }
                    for r in results
                ]
                results = self.reranker.rerank(
                    question, results, top_n=self.reranker_top_n
                )
                if capture_trace:
                    trace.steps.append(
                        TraceStep(
                            stage="rerank",
                            input_data={
                                "result_count": pre_rerank_count,
                                "results": pre_rerank_snapshot,
                            },
                            output_data={
                                "results": [
                                    {
                                        "chunk_id": r.get("chunk_id", ""),
                                        "rerank_score": r.get("rerank_score"),
                                        "score": r["score"],
                                    }
                                    for r in results
                                ],
                                "count": len(results),
                            },
                            duration_ms=(time.perf_counter() - t0) * 1000,
                            metadata={
                                "model": (
                                    self.reranker.model_name if self.reranker else None
                                ),
                                "top_n": self.reranker_top_n,
                            },
                        )
                    )

            if not is_multi and self.profiler:
                self.profiler.end_stage()

            t0 = time.perf_counter()
            scores = self._compute_scores(results, is_multi)
            contexts = [r["text"] for r in results]
            sources = [r["metadata"].get("source", "Unknown") for r in results]
            chunk_ids = [r.get("chunk_id", "") for r in results]
            ctx_step = None
            if capture_trace:
                ctx_step = TraceStep(
                    stage="context_assembly",
                    input_data={"context_count": len(contexts), "sources": sources},
                    output_data={"final_context_count": len(contexts)},
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    metadata={"max_context_tokens": self.generator.max_context_tokens},
                )
                trace.steps.append(ctx_step)

            logger.debug("Generating answer...")
            if not is_multi and self.profiler:
                self.profiler.begin_stage("S7")

            t0 = time.perf_counter()
            if capture_trace:
                gen_result = self.generator.generate(
                    question,
                    contexts,
                    sources=sources,
                    chat_history=chat_history,
                    return_prompt_details=True,
                )
                answer = gen_result["answer"]
                truncated_count = gen_result.get("truncated_count", 0)
                if ctx_step is not None and truncated_count > 0:
                    ctx_step.output_data["final_context_count"] = (
                        len(contexts) - truncated_count
                    )
                trace.steps.append(
                    TraceStep(
                        stage="generation",
                        input_data={
                            "system_prompt": gen_result["system_prompt"],
                            "user_message": gen_result["user_message"],
                        },
                        output_data={
                            "answer": answer,
                            "token_usage": (
                                self.generator.last_token_usage.to_dict()
                                if self.generator.last_token_usage
                                else None
                            ),
                        },
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        metadata={
                            "model": self.generator.model_name,
                            "temperature": self.generator.temperature,
                        },
                    )
                )
            else:
                answer = self.generator.generate(
                    question, contexts, sources=sources, chat_history=chat_history
                )

            if not is_multi and self.profiler:
                self.profiler.end_stage()

            response = {"question": question, "answer": answer}
            if return_contexts:
                response["contexts"] = contexts
                response["scores"] = scores
                response["sources"] = sources
                response["chunk_ids"] = chunk_ids
            if self.generator.last_token_usage is not None:
                response["token_usage"] = self.generator.last_token_usage.to_dict()
            if capture_trace:
                response["trace"] = trace.to_dict()

            logger.success(
                f"Query processed successfully{' (multi-query)' if is_multi else ''}"
            )
            return response

        except Exception as e:
            error_msg = f"Failed to process query: {str(e)}"
            logger.error(error_msg)
            raise RetrievalError(error_msg) from e

    def _ensure_bm25_index(self) -> None:
        """Build BM25 index from chunks directory if not already built.

        Uses the cached ``_chunks_dir`` to lazy-load the BM25 index on
        first access. Subsequent calls are no-ops once the index is ready.

        Raises:
            RetrievalError: If chunks directory is not available.
        """
        if self.bm25_retriever is not None and self.bm25_retriever.is_indexed():
            return

        if self._chunks_dir is None or not self._chunks_dir.exists():
            raise RetrievalError(
                "BM25 索引不可用：找不到 chunks 数据目录。"
                "请先构建索引（pixi run python main.py --build-index）或选择一个 Meal。"
            )

        logger.info(f"Lazy-loading BM25 index from {self._chunks_dir}...")
        self.bm25_retriever.build_index_from_chunks(str(self._chunks_dir))
        logger.success("BM25 index lazy-loaded successfully")

    def _ensure_reranker(self) -> None:
        """Load reranker model if not already loaded.

        Initializes the cross-encoder reranker on first call, reading
        model name, device, and top_n from the retrieval config.
        """
        if self.reranker is not None:
            return

        reranker_config = self.config.get("retrieval", {}).get("reranker", {})
        logger.info("Lazy-loading reranker model...")
        self.reranker = Reranker(
            model_name=reranker_config.get("model_name", "BAAI/bge-reranker-large"),
            device=reranker_config.get("device", "cuda"),
        )
        self.reranker_top_n = reranker_config.get(
            "top_n", self.config["retrieval"]["top_k"]
        )
        logger.success("Reranker model lazy-loaded successfully")

    def _ensure_query_rewriter(self, strategy: str) -> None:
        """Initialize query rewriter if not already initialized or strategy changed.

        Args:
            strategy: Query rewrite strategy (``"hyde"`` or ``"multi_query"``).
        """
        if self.query_rewriter is not None and self.query_rewriter.strategy == strategy:
            return

        logger.info(f"Lazy-initializing query rewriter (strategy={strategy})...")
        llm_config = get_llm_config(self.config, self.llm_preset)
        rewrite_config = self.config.get("retrieval", {}).get("query_rewrite", {})
        self.query_rewriter = QueryRewriter(
            strategy=strategy,
            llm_model_name=llm_config["model_name"],
            llm_api_key=llm_config["api_key"],
            llm_base_url=llm_config["base_url"],
            llm_temperature=llm_config.get("temperature", 0.0),
            llm_max_tokens=llm_config.get("max_tokens", 512),
            num_queries=rewrite_config.get("num_queries", 3),
            token_tracker=self.token_tracker,
        )
        logger.success(f"Query rewriter lazy-initialized (strategy={strategy})")

    def _get_rewrite_strategy(self) -> QueryRewriteStrategy:
        if self.query_rewriter is None:
            return NoRewriteStrategy()
        if self.query_rewriter.strategy == "hyde":
            return HyDERewriteStrategy(self.query_rewriter)
        if self.query_rewriter.strategy == "multi_query":
            return MultiQueryRewriteStrategy(self.query_rewriter)
        return NoRewriteStrategy()

    def _retrieve_multi(
        self,
        strategy: RetrievalStrategy,
        queries: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Retrieve results for multiple queries and merge by deduplication.

        Executes retrieval for each query, deduplicates by chunk_id, and
        returns the top_k results sorted by score.

        Args:
            strategy: The retrieval strategy to use.
            queries: List of query strings to retrieve for.
            top_k: Maximum number of results to return.

        Returns:
            Deduplicated and sorted list of result dictionaries.
        """
        all_results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for q in queries:
            result = strategy.retrieve(q, top_k)
            for r in result.chunks:
                if r["chunk_id"] not in seen_ids:
                    seen_ids.add(r["chunk_id"])
                    all_results.append(r)
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_results[:top_k]

    def _compute_scores(
        self, results: list[dict[str, Any]], is_multi: bool
    ) -> list[float]:
        """Extract scores from retrieval results.

        For multi-query results, prefers rerank_score over base score when
        available. For single-query results, uses the base score.

        Args:
            results: List of retrieval result dictionaries.
            is_multi: Whether the results came from multi-query retrieval.

        Returns:
            List of float scores corresponding to each result.
        """
        if is_multi:
            return [
                r.get("rerank_score", r["score"]) if "rerank_score" in r else r["score"]
                for r in results
            ]
        return [r["score"] for r in results]
