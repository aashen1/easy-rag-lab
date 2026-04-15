import argparse

from loguru import logger

from src.pipeline import RAGPipeline
from src.utils import load_config, setup_logger


def main():
    parser = argparse.ArgumentParser(description="RAG System - Financial Report Q&A")
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

    if not args.query and not args.build_index and not args.rebuild:
        parser.print_help()
        return

    pipeline = RAGPipeline(config_path=args.config, llm_preset=args.llm_preset)

    if args.build_index or args.rebuild:
        pipeline.build_index(
            rebuild=args.rebuild,
            force_parse=args.force_parse,
            sample_size=args.sample_size,
        )
        logger.info("✅ Index built successfully")

    if args.query:
        result = pipeline.query(args.query)
        print(f"\n{'='*60}")
        print(f"Question: {result['question']}")
        print(f"{'='*60}")
        print(f"\nAnswer:\n{result['answer']}")
        if "contexts" in result:
            print(f"\n{'='*60}")
            print("Sources:")
            print(f"{'='*60}")
            for i, (source, score) in enumerate(
                zip(result["sources"], result["scores"]), 1
            ):
                print(f"{i}. {source} (relevance: {score:.4f})")


if __name__ == "__main__":
    main()
