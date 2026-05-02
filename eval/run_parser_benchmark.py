from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run parser benchmarks across multiple pipeline configurations"
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the benchmark configuration YAML file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-run even if cached results exist",
    )

    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists() and not config_path.suffix:
        config_path = Path("parser_configs") / f"{config_path.name}.yaml"

    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)

    from eval.parser_benchmark.runner import ParserBenchmarkRunner  # noqa: E402

    runner = ParserBenchmarkRunner(config_path)
    result = runner.run(force=args.force)

    if result.get("status") == "success":
        logger.success(f"Benchmark completed: {result['run_dir']}")
    else:
        logger.warning(f"Benchmark ended with status: {result.get('status')}")


if __name__ == "__main__":
    main()
