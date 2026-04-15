import argparse
import sys

from loguru import logger

from src.pipeline import RAGPipeline
from src.sampler import SamplingConfig
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

    if not args.query and not args.build_index and not args.rebuild:
        parser.print_help()
        return

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
