from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.bm25_retriever import BM25Retriever
from src.chunker import process_parsed_files
from src.embedder import Embedder
from src.generator import Generator
from src.hybrid_retriever import HybridRetriever
from src.indexer import VectorIndexer
from src.parser import parse_all_pdfs
from src.query_rewriter import QueryRewriter
from src.reranker import Reranker
from src.retriever import Retriever
from src.semantic_chunker import process_parsed_files_semantic
from src.sampler import SamplingConfig, determine_sample
from src.token_tracker import DetailedTokenUsage, TokenTracker
from src.utils import get_llm_config, load_config, setup_logger


class RAGPipeline:
    def __init__(self, config_path: str = "config.yaml", llm_preset: str = None, meal_name: str = None, token_tracker: Optional[TokenTracker] = None):
        self.config = load_config(config_path)
        setup_logger(self.config)
        self.meal_name = meal_name
        self.meal_config = None
        self.token_tracker = token_tracker if token_tracker is not None else TokenTracker()

        logger.info("Initializing RAG Pipeline")

        embedding_config = self.config["embedding"]
        self.embedder = Embedder(
            model_name=embedding_config["model_name"],
            device=embedding_config["device"],
            query_instruction=embedding_config.get("query_instruction"),
        )

        vector_store_config = self.config["vector_store"]
        collection_name = vector_store_config["collection_name"]

        if meal_name is not None:
            from src.meal import MealManager
            meal_manager = MealManager(self.config)
            self.meal_config = meal_manager.load_meal(meal_name)
            collection_name = self.meal_config.collection_name
            logger.info(
                f"Using meal '{meal_name}' (data_id: {self.meal_config.data_id[:12]}, collection: {collection_name})")

        self.indexer = VectorIndexer(
            persist_dir=vector_store_config["persist_dir"],
            collection_name=collection_name,
            distance=vector_store_config["distance"],
        )

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

        self.bm25_retriever: Optional[BM25Retriever] = None
        self.hybrid_retriever: Optional[HybridRetriever] = None
        self.retrieval_method = retrieval_method

        if retrieval_method in ("bm25", "hybrid"):
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

        self.reranker: Optional[Reranker] = None
        reranker_config = retrieval_config.get("reranker", {})
        if reranker_config.get("enabled", False):
            self.reranker = Reranker(
                model_name=reranker_config.get("model_name", "BAAI/bge-reranker-large"),
                device=reranker_config.get("device", "cuda"),
            )
            self.reranker_top_n = reranker_config.get("top_n", top_k)

        self.query_rewriter: Optional[QueryRewriter] = None
        rewrite_config = retrieval_config.get("query_rewrite", {})
        if rewrite_config.get("enabled", False):
            llm_config = get_llm_config(self.config)
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
        sampling_config: Optional[SamplingConfig] = None,
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
                f"Sampled {len(sampled_pdf_files)} PDFs from {len(all_pdfs)} total")

        logger.info("Step 1: Parsing PDFs...")
        parse_results = parse_all_pdfs(
            input_dir=parser_config["input_dir"],
            output_dir=parser_config["output_dir"],
            force=force_parse,
            pdf_files=sampled_pdf_files,
        )

        source_filter_md = None
        if sampling_config is not None:
            source_filter_md = set()
            for r in parse_results:
                if r.get("output"):
                    output_path = Path(r["output"])
                    parsed_dir = Path(parser_config["output_dir"])
                    source_filter_md.add(
                        str(output_path.relative_to(parsed_dir)))
            logger.info(
                f"Source filter for chunker: {len(source_filter_md)} files")

        logger.info("Step 2: Chunking documents...")
        chunker_strategy = chunker_config.get("strategy", "fixed")

        if chunker_strategy == "semantic":
            semantic_config = chunker_config.get("semantic", {})
            chunk_results = process_parsed_files_semantic(
                input_dir=chunker_config["input_dir"],
                output_dir=chunker_config["output_dir"],
                embedder=self.embedder,
                chunk_size=chunker_config["chunk_size"],
                similarity_threshold=semantic_config.get("similarity_threshold", 0.5),
                breakpoint_percentile=semantic_config.get("breakpoint_percentile"),
                min_chunk_size=semantic_config.get("min_chunk_size", 100),
                source_filter=source_filter_md,
            )
        else:
            chunk_results = process_parsed_files(
                input_dir=chunker_config["input_dir"],
                output_dir=chunker_config["output_dir"],
                chunk_size=chunker_config["chunk_size"],
                overlap=chunker_config["chunk_overlap"],
                source_filter=source_filter_md,
            )

        source_filter_jsonl = None
        if sampling_config is not None:
            source_filter_jsonl = set()
            for r in chunk_results:
                if r.get("output"):
                    output_path = Path(r["output"])
                    chunks_dir = Path(chunker_config["output_dir"])
                    source_filter_jsonl.add(
                        str(output_path.relative_to(chunks_dir)))
            logger.info(
                f"Source filter for indexer: {len(source_filter_jsonl)} files")

        logger.info("Step 3: Building vector index...")
        self.indexer.build_index(
            chunks_dir=chunker_config["output_dir"],
            embedder=self.embedder,
            batch_size=embedding_config["batch_size"],
            rebuild=rebuild,
            source_filter=source_filter_jsonl,
        )

        if self.retrieval_method in ("bm25", "hybrid") and self.bm25_retriever is not None:
            logger.info("Step 4: Building BM25 index...")
            self.bm25_retriever.build_index_from_chunks(
                chunks_dir=chunker_config["output_dir"],
                source_filter=source_filter_jsonl,
            )

        logger.success("Index built successfully")

    def close(self) -> None:
        """Close the pipeline and release resources.

        Closes the Qdrant client held by the indexer to prevent
        resource leaks (file handles, WAL locks, etc.).
        """
        if hasattr(self, 'indexer') and self.indexer is not None:
            self.indexer.close()
            logger.info("RAGPipeline indexer closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def use_meal(self, meal_name: str) -> "MealConfig":
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

        if hasattr(self, 'indexer') and self.indexer is not None:
            self.indexer.close()

        meal_manager = MealManager(self.config)
        self.meal_config = meal_manager.load_meal(meal_name)
        self.meal_name = meal_name

        vector_store_config = self.config["vector_store"]
        self.indexer = VectorIndexer(
            persist_dir=vector_store_config["persist_dir"],
            collection_name=self.meal_config.collection_name,
            distance=vector_store_config["distance"],
        )

        self._setup_retrievers()

        if self.retrieval_method in ("bm25", "hybrid") and self.bm25_retriever is not None:
            from src.meal import ArtifactCache
            artifacts_config = self.config.get("artifacts", {})
            artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
            cache = ArtifactCache(artifacts_dir)
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
                    fusion_method=self.config["retrieval"].get("hybrid", {}).get("fusion", "rrf"),
                    rrf_k=self.config["retrieval"].get("hybrid", {}).get("rrf_k", 60),
                    vector_weight=self.config["retrieval"].get("hybrid", {}).get("vector_weight", 0.7),
                    bm25_weight=self.config["retrieval"].get("hybrid", {}).get("bm25_weight", 0.3),
                    top_k=self.config["retrieval"]["top_k"],
                )

        logger.info(
            f"Switched to meal '{meal_name}' (data_id: {self.meal_config.data_id[:12]}, collection: {self.meal_config.collection_name})")
        return self.meal_config

    def query(
        self, question: str, return_contexts: bool = True
    ) -> Dict[str, Any]:
        """Execute a RAG query: retrieve relevant contexts and generate an answer.

        Args:
            question: The user question to answer. Must be a non-empty string.
            return_contexts: Whether to include retrieved contexts, scores, and
                sources in the response dictionary. Defaults to True.

        Returns:
            A dictionary containing at minimum ``question`` and ``answer`` keys.
            When ``return_contexts`` is True, also includes ``contexts``,
            ``scores``, ``sources``, ``chunk_ids``, and optionally ``token_usage``.

        Raises:
            ValueError: If ``question`` is empty or not a string.
            Exception: If retrieval or generation fails.
        """
        if not question or not isinstance(question, str):
            error_msg = "Question must be a non-empty string"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            logger.info(f"Processing query: {question[:50]}...")

            retrieval_query = question
            if self.query_rewriter is not None:
                logger.debug("Rewriting query...")
                rewrite_result = self.query_rewriter.rewrite(question)

                if rewrite_result["strategy"] == "hyde":
                    retrieval_query = rewrite_result["rewritten"]
                    logger.info(f"HyDE: using hypothetical answer for retrieval")
                elif rewrite_result["strategy"] == "multi_query":
                    all_results = []
                    seen_ids = set()
                    for sub_query in rewrite_result["rewritten"]:
                        if self.retrieval_method == "hybrid" and self.hybrid_retriever is not None:
                            sub_results = self.hybrid_retriever.retrieve(sub_query)
                        elif self.retrieval_method == "bm25" and self.bm25_retriever is not None:
                            sub_results = self.bm25_retriever.retrieve(
                                sub_query, top_k=self.config["retrieval"]["top_k"]
                            )
                        else:
                            sub_results = self.retriever.retrieve(sub_query)
                        for r in sub_results:
                            if r["chunk_id"] not in seen_ids:
                                seen_ids.add(r["chunk_id"])
                                all_results.append(r)

                    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
                    results = all_results[:self.config["retrieval"]["top_k"]]

                    if self.reranker is not None and results:
                        logger.debug("Reranking multi-query results...")
                        results = self.reranker.rerank(
                            question, results, top_n=self.reranker_top_n
                        )

                    contexts = [r["text"] for r in results]
                    scores = [r.get("rerank_score", r["score"]) if "rerank_score" in r else r["score"] for r in results]
                    sources = [r["metadata"].get("source", "Unknown") for r in results]
                    chunk_ids = [r.get("chunk_id", "") for r in results]

                    logger.debug("Generating answer...")
                    answer = self.generator.generate(question, contexts, sources=sources)

                    response = {"question": question, "answer": answer}
                    if return_contexts:
                        response["contexts"] = contexts
                        response["scores"] = scores
                        response["sources"] = sources
                        response["chunk_ids"] = chunk_ids
                    if self.generator.last_token_usage is not None:
                        response["token_usage"] = self.generator.last_token_usage.to_dict()

                    logger.success("Query processed successfully (multi-query)")
                    return response

            logger.debug("Retrieving relevant contexts...")
            if self.retrieval_method == "hybrid" and self.hybrid_retriever is not None:
                results = self.hybrid_retriever.retrieve(retrieval_query)
            elif self.retrieval_method == "bm25" and self.bm25_retriever is not None:
                results = self.bm25_retriever.retrieve(
                    retrieval_query, top_k=self.config["retrieval"]["top_k"]
                )
            else:
                results = self.retriever.retrieve(retrieval_query)

            if self.reranker is not None and results:
                logger.debug("Reranking results...")
                results = self.reranker.rerank(
                    question, results, top_n=self.reranker_top_n
                )

            contexts = [result["text"] for result in results]
            scores = [result["score"] for result in results]
            sources = [
                result["metadata"].get("source", "Unknown") for result in results
            ]
            chunk_ids = [result.get("chunk_id", "") for result in results]

            logger.debug("Generating answer...")
            answer = self.generator.generate(question, contexts, sources=sources)

            response = {
                "question": question,
                "answer": answer,
            }

            if return_contexts:
                response["contexts"] = contexts
                response["scores"] = scores
                response["sources"] = sources
                response["chunk_ids"] = chunk_ids

            if self.generator.last_token_usage is not None:
                response["token_usage"] = self.generator.last_token_usage.to_dict()

            logger.success("Query processed successfully")
            return response

        except Exception as e:
            error_msg = f"Failed to process query: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="RAG Pipeline CLI")
    parser.add_argument("--query", type=str, help="Query question")
    parser.add_argument("--build-index", action="store_true",
                        help="Build vector index")
    parser.add_argument(
        "--rebuild", action="store_true", help="Rebuild index from scratch"
    )
    parser.add_argument(
        "--force-parse",
        action="store_true",
        help="Force re-parse PDFs even if output exists",
    )
    parser.add_argument(
        "--sample-count", type=int, help="Sample N PDFs for testing"
    )
    parser.add_argument(
        "--sample-pages", type=int, help="Sample PDFs until total pages reach N"
    )
    parser.add_argument(
        "--sample-ratio", type=float, help="Sample ratio of total PDFs (0.0-1.0)"
    )
    parser.add_argument(
        "--config", type=str, default="config.yaml", help="Config file path"
    )
    parser.add_argument(
        "--llm-preset", type=str, help="LLM preset name (default, opus, sonnet, haiku)"
    )

    args = parser.parse_args()

    pipeline = RAGPipeline(config_path=args.config, llm_preset=args.llm_preset)

    if args.build_index or args.rebuild:
        sampling_config = None
        sample_modes = [
            ("count", args.sample_count),
            ("pages", args.sample_pages),
            ("ratio", args.sample_ratio),
        ]
        active_modes = [(m, v) for m, v in sample_modes if v is not None]
        if len(active_modes) > 1:
            logger.error(
                "Only one sampling mode can be specified at a time "
                f"(got: {', '.join(m for m, _ in active_modes)})"
            )
            sys.exit(1)
        if active_modes:
            mode, value = active_modes[0]
            sampling_config = SamplingConfig(mode=mode, value=value)

        pipeline.build_index(
            rebuild=args.rebuild,
            force_parse=args.force_parse,
            sampling_config=sampling_config,
        )
        logger.info("Index built successfully")

    if args.query:
        result = pipeline.query(args.query)
        print(f"\nQuestion: {result['question']}")
        print(f"\nAnswer: {result['answer']}")
        if "contexts" in result:
            print(f"\nSources:")
            for i, (source, score) in enumerate(
                zip(result["sources"], result["scores"]), 1
            ):
                print(f"{i}. {source} (score: {score:.4f})")
