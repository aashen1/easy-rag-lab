"""Golden test set generator CLI for RAG evaluation.

DEPRECATED: Use `pixi run testset generate` instead.
This script will be removed in a future version.

Delegates to TestSetGenerator.generate_golden_testset().

Usage:
    pixi run python scripts/generate_golden_testset.py --num-questions 150
    pixi run python scripts/generate_golden_testset.py --num-questions 150 --llm-preset default
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import load_config


def main():
    """CLI entry point for golden test set generation.

    Delegates to TestSetGenerator.generate_golden_testset().
    """
    parser = argparse.ArgumentParser(
        description="Generate golden test set for RAG evaluation"
    )
    parser.add_argument(
        "--num-questions",
        type=int,
        default=150,
        help="Total number of questions to generate (default: 150)",
    )
    parser.add_argument(
        "--llm-preset",
        default="default",
        help="LLM preset name from config (default: default)",
    )
    parser.add_argument(
        "--name",
        default="golden_150",
        help="Name for the golden test set (default: golden_150)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args()

    config = load_config()

    from src.test_generator import TestSetGenerator

    generator = TestSetGenerator(config)
    generator.generate_golden_testset(
        num_questions=args.num_questions,
        name=args.name,
        llm_preset=args.llm_preset,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
