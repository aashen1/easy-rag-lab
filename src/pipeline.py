from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.chunker import process_parsed_files
from src.embedder import Embedder
from src.generator import Generator
from src.indexer import VectorIndexer
from src.parser import parse_all_pdfs
from src.retriever import Retriever
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
        )

        vector_store_config = self.config["vector_store"]
        collection_name = vector_store_config["collection_name"]

        if meal_name is not None:
            from src.meal import MealManager
            meal_manager = MealManager(self.config)
            self.meal_config = meal_manager.load_meal(meal_name)
            collection_name = self.meal_config.collection_name
            logger.info(f"Using meal '{meal_name}' (data_id: {self.meal_config.data_id[:12]}, collection: {collection_name})")

        self.indexer = VectorIndexer(
            persist_dir=vector_store_config["persist_dir"],
            collection_name=collection_name,
            distance=vector_store_config["distance"],
        )

        retrieval_config = self.config["retrieval"]
        self.retriever = Retriever(
            indexer=self.indexer,
            embedder=self.embedder,
            top_k=retrieval_config["top_k"],
        )

        llm_config = get_llm_config(self.config, llm_preset)
        self.generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=llm_config["temperature"],
            max_tokens=llm_config["max_tokens"],
            token_tracker=self.token_tracker,
        )

        logger.success("RAG Pipeline initialized successfully")

    def build_index(
        self,
        rebuild: bool = False,
        force_parse: bool = False,
        sampling_config: Optional[SamplingConfig] = None,
    ) -> None:
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
            logger.info(f"Sampled {len(sampled_pdf_files)} PDFs from {len(all_pdfs)} total")

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
                    source_filter_md.add(str(output_path.relative_to(parsed_dir)))
            logger.info(f"Source filter for chunker: {len(source_filter_md)} files")

        logger.info("Step 2: Chunking documents...")
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
                    source_filter_jsonl.add(str(output_path.relative_to(chunks_dir)))
            logger.info(f"Source filter for indexer: {len(source_filter_jsonl)} files")

        logger.info("Step 3: Building vector index...")
        self.indexer.build_index(
            chunks_dir=chunker_config["output_dir"],
            embedder=self.embedder,
            batch_size=embedding_config["batch_size"],
            rebuild=rebuild,
            source_filter=source_filter_jsonl,
        )

        logger.success("Vector index built successfully")

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

    def use_meal(self, meal_name: str):
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
        self.retriever = Retriever(
            indexer=self.indexer,
            embedder=self.embedder,
            top_k=self.config["retrieval"]["top_k"],
        )
        logger.info(f"Switched to meal '{meal_name}' (data_id: {self.meal_config.data_id[:12]}, collection: {self.meal_config.collection_name})")
        return self.meal_config

    def query(
        self, question: str, return_contexts: bool = True
    ) -> Dict[str, Any]:
        if not question or not isinstance(question, str):
            error_msg = "Question must be a non-empty string"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            logger.info(f"Processing query: {question[:50]}...")

            logger.debug("Retrieving relevant contexts...")
            results = self.retriever.retrieve(question)

            contexts = [result["text"] for result in results]
            scores = [result["score"] for result in results]
            sources = [
                result["metadata"].get("source", "Unknown") for result in results
            ]

            logger.debug("Generating answer...")
            answer = self.generator.generate(question, contexts)

            response = {
                "question": question,
                "answer": answer,
            }

            if return_contexts:
                response["contexts"] = contexts
                response["scores"] = scores
                response["sources"] = sources

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
    parser.add_argument("--build-index", action="store_true", help="Build vector index")
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
