from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from eval.runner import (  # noqa: E402
    AssetVerificationResult,
    build_comparison_data,
    build_legacy_resolver,
    collect_environment_info,
    collect_rag_samples,
    compare_experiments,
    compute_aggregate_metrics,
    create_evaluators,
    evaluate_test_set,
    evaluate_with_builtin,
    evaluate_with_ragas,
    extract_category_metrics,
    generate_comparison_report,
    generate_llm_report_only,
    list_experiments,
    merge_result,
    namespace_result,
    prepare_index_for_variant,
    prepare_legacy_test_set,
    prepare_meal,
    prepare_test_sets,
    prepare_variant_chunks,
    print_comparison_table,
    reproduce_experiment,
    run_experiment,
    run_variant_evaluation,
    sanitize_config,
    show_experiment_info,
    verify_experiment_assets,
)


def main():
    parser = argparse.ArgumentParser(
        description="RAG Experiment Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run experiment
  pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml

  # Run with LLM-generated report
  pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml --llm-report

  # List all experiments
  pixi run python eval/run_experiment.py --list

  # Show experiment details
  pixi run python eval/run_experiment.py --info exp_20250416_120000_baseline

  # Compare experiments
  pixi run python eval/run_experiment.py --compare exp_001 exp_002 exp_003

  # Compare experiments and save report
  pixi run python eval/run_experiment.py --compare exp_001 exp_002 --save-report

  # Reproduce experiment
  pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000_baseline

  # Reproduce experiment without hash verification
  pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000_baseline --skip-verification
        """,
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to experiment configuration YAML file",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all experiments",
    )
    parser.add_argument(
        "--info",
        type=str,
        metavar="EXP_ID",
        help="Show detailed information about an experiment",
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        metavar="EXP_ID",
        help="Compare multiple experiments",
    )
    parser.add_argument(
        "--reproduce",
        type=str,
        metavar="EXP_DIR",
        help="Reproduce an experiment from its saved configuration",
    )
    parser.add_argument(
        "--skip-preprocessing",
        action="store_true",
        help="Skip meal and test set creation if missing",
    )
    parser.add_argument(
        "--llm-report",
        action="store_true",
        help="Use LLM to generate experiment report",
    )
    parser.add_argument(
        "--system-config",
        type=str,
        default="config.yaml",
        help="Path to system configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="Skip asset verification when reproducing experiment",
    )
    parser.add_argument(
        "--skip-hash-verification",
        action="store_true",
        help="Skip PDF SHA256 hash verification (faster but less secure)",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["table", "json"],
        default="table",
        help="Output format for comparison (default: table)",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save comparison report to a Markdown file",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        metavar="PATH",
        help="Path to save the comparison report (implies --save-report)",
    )

    args = parser.parse_args()

    if args.list:
        list_experiments(args.system_config)
    elif args.info:
        show_experiment_info(args.info, args.system_config)
    elif args.compare:
        save_report = args.save_report or args.report_path is not None
        compare_experiments(
            exp_ids=args.compare,
            system_config_path=args.system_config,
            output_format=args.output_format,
            save_report=save_report,
            report_path=args.report_path,
        )
    elif args.reproduce:
        try:
            result = reproduce_experiment(
                exp_dir=args.reproduce,
                system_config_path=args.system_config,
                skip_verification=args.skip_verification,
                verify_pdf_hashes=not args.skip_hash_verification,
            )
            print("\nExperiment reproduced successfully!")
            print(f"Original: {result['original_exp_dir']}")
            print(f"Reproduced: {result['reproduced_exp_dir']}")
        except ValueError as e:
            print(f"\nError: {str(e)}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"\nError: {str(e)}")
            sys.exit(1)
    elif args.config:
        result = run_experiment(
            config_path=args.config,
            skip_preprocessing=args.skip_preprocessing,
            use_llm_report=args.llm_report,
            system_config_path=args.system_config,
        )
        print(f"\nExperiment completed: {result['experiment_id']}")
        print(f"Results saved to: {result['exp_dir']}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
