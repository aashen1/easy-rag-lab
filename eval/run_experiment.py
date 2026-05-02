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
from src.experiment_reuse import (  # noqa: E402
    InPlaceReuseHandler,
    ReportReuseConfig,
)


def _build_reuse_config(args: argparse.Namespace) -> ReportReuseConfig | None:
    if not args.reuse:
        return None

    mode = args.reuse.replace("-", "_")
    return ReportReuseConfig(
        mode=mode,
        target_dir=args.target_dir,
        source_dir=args.source_dir,
        backup_before_append=not args.no_backup,
    )


def _handle_list_backups(args: argparse.Namespace) -> None:
    from src.utils import load_config

    system_config = load_config(args.system_config)
    exp_dir = Path(system_config.get("experiments", {}).get("dir", "data/exp_reports"))
    target_dir = exp_dir / args.list_backups

    if not target_dir.exists():
        candidate = Path(args.list_backups)
        if candidate.exists():
            target_dir = candidate
        else:
            print(f"Experiment directory not found: {args.list_backups}")
            sys.exit(1)

    handler = InPlaceReuseHandler(target_dir=target_dir)
    snapshots = handler.list_snapshots()

    if not snapshots:
        print(f"No backup snapshots found for: {target_dir.name}")
        return

    print(f"\nBackup snapshots for {target_dir.name}:")
    print("=" * 60)
    for snap in snapshots:
        print(f"  Timestamp: {snap['timestamp']}")
        print(f"  Path:      {snap['path']}")
        print(f"  Created:   {snap['created_at']}")
        print()
    print("=" * 60)


def _handle_restore_backup(args: argparse.Namespace) -> None:
    from src.utils import load_config

    if not args.snapshot:
        print("Error: --snapshot is required when using --restore-backup")
        sys.exit(1)

    system_config = load_config(args.system_config)
    exp_dir = Path(system_config.get("experiments", {}).get("dir", "data/exp_reports"))
    target_dir = exp_dir / args.restore_backup

    if not target_dir.exists():
        candidate = Path(args.restore_backup)
        if candidate.exists():
            target_dir = candidate
        else:
            print(f"Experiment directory not found: {args.restore_backup}")
            sys.exit(1)

    handler = InPlaceReuseHandler(target_dir=target_dir)

    print(f"Restoring experiment from snapshot: {args.snapshot}")
    print(f"Target directory: {target_dir}")
    print("\nWARNING: This will overwrite current experiment data!")

    try:
        confirm = input("Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Restore cancelled.")
            return

        handler.restore_snapshot(args.snapshot)
        print(f"\nExperiment restored successfully from snapshot: {args.snapshot}")
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)


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

  # In-place reuse: append new variants to existing experiment
  pixi run python eval/run_experiment.py --config exp.yaml --reuse in-place --target-dir data/exp_reports/exp_20260501_120000

  # Copy-migrate reuse: copy existing experiment and add variants
  pixi run python eval/run_experiment.py --config exp.yaml --reuse copy-migrate --source-dir data/exp_reports/exp_20260501_120000

  # List backup snapshots for an experiment
  pixi run python eval/run_experiment.py --list-backups exp_20260501_120000

  # Restore from a backup snapshot
  pixi run python eval/run_experiment.py --restore-backup exp_20260501_120000 --snapshot 20260502_140000
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
        "--force-rerun",
        action="store_true",
        help="Force re-run all variants, ignoring checkpoints from previous runs",
    )
    parser.add_argument(
        "--force-variant",
        nargs="+",
        metavar="VARIANT",
        help="Force re-run specific variant(s) by name, even if they have completed checkpoints",
    )
    parser.add_argument(
        "--resume",
        type=str,
        metavar="EXP_DIR",
        help="Resume an interrupted experiment from an existing experiment directory",
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
    parser.add_argument(
        "--reuse",
        type=str,
        choices=["in-place", "copy-migrate"],
        help="Experiment report reuse mode: 'in-place' appends to an existing "
        "experiment directory, 'copy-migrate' copies an existing experiment "
        "to a new directory",
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        metavar="PATH",
        help="Target experiment directory for in-place reuse mode",
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        metavar="PATH",
        help="Source experiment directory for copy-migrate reuse mode",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Disable backup snapshot before appending (in-place mode only)",
    )
    parser.add_argument(
        "--list-backups",
        type=str,
        metavar="EXP_ID",
        help="List all backup snapshots for an experiment",
    )
    parser.add_argument(
        "--restore-backup",
        type=str,
        metavar="EXP_ID",
        help="Restore experiment directory from a backup snapshot",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        metavar="TIMESTAMP",
        help="Backup snapshot timestamp to restore (used with --restore-backup)",
    )

    args = parser.parse_args()

    if args.list:
        list_experiments(args.system_config)
    elif args.info:
        show_experiment_info(args.info, args.system_config)
    elif args.list_backups:
        _handle_list_backups(args)
    elif args.restore_backup:
        _handle_restore_backup(args)
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
        reuse_config = _build_reuse_config(args)
        result = run_experiment(
            config_path=args.config,
            skip_preprocessing=args.skip_preprocessing,
            use_llm_report=args.llm_report,
            system_config_path=args.system_config,
            force_rerun=args.force_rerun,
            force_variant=args.force_variant,
            resume_dir=args.resume,
            reuse_config=reuse_config,
        )
        print(f"\nExperiment completed: {result['experiment_id']}")
        print(f"Results saved to: {result['exp_dir']}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
