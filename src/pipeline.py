from typing import Any, Dict, List, Optional

from loguru import logger

from src.chunker import process_parsed_files
from src.embedder import Embedder
from src.generator import Generator
from src.indexer import VectorIndexer
from src.parser import parse_all_pdfs
from src.retriever import Retriever
from src.utils import get_llm_config, load_config, setup_logger


class RAGPipeline:
    def __init__(self, config_path: str = "config.yaml", llm_preset: str = None):
        self.config = load_config(config_path)
        setup_logger(self.config)

        logger.info("Initializing RAG Pipeline")

        embedding_config = self.config["embedding"]
        self.embedder = Embedder(
            model_name=embedding_config["model_name"],
            device=embedding_config["device"],
        )

        vector_store_config = self.config["vector_store"]
        self.indexer = VectorIndexer(
            persist_dir=vector_store_config["persist_dir"],
            collection_name=vector_store_config["collection_name"],
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
        )

        logger.success("RAG Pipeline initialized successfully")

    def build_index(
        self, rebuild: bool = False, force_parse: bool = False, sample_size: int = None
    ) -> None:
        logger.info("Building vector index...")

        parser_config = self.config["parser"]
        chunker_config = self.config["chunker"]
        embedding_config = self.config["embedding"]

        logger.info("Step 1: Parsing PDFs...")
        parse_results = parse_all_pdfs(
            input_dir=parser_config["input_dir"],
            output_dir=parser_config["output_dir"],
            force=force_parse,
            sample_size=sample_size,
        )

        logger.info("Step 2: Chunking documents...")
        chunk_results = process_parsed_files(
            input_dir=chunker_config["input_dir"],
            output_dir=chunker_config["output_dir"],
            chunk_size=chunker_config["chunk_size"],
            overlap=chunker_config["chunk_overlap"],
        )

        logger.info("Step 3: Building vector index...")
        self.indexer.build_index(
            chunks_dir=chunker_config["output_dir"],
            embedder=self.embedder,
            batch_size=embedding_config["batch_size"],
            rebuild=rebuild,
        )

        logger.success("Vector index built successfully")

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

            logger.success("Query processed successfully")
            return response

        except Exception as e:
            error_msg = f"Failed to process query: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)


if __name__ == "__main__":
    import argparse

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
        "--sample-size", type=int, help="Sample size for testing (number of PDFs)"
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
        pipeline.build_index(
            rebuild=args.rebuild,
            force_parse=args.force_parse,
            sample_size=args.sample_size,
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
