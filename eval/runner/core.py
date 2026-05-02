from __future__ import annotations

import contextlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from eval.experiment_reporter import ExperimentReporter
from eval.pipeline_profiler import PipelineProfiler
from eval.runner.asset_verifier import collect_environment_info, sanitize_config
from eval.runner.evaluation import evaluate_test_set
from eval.runner.metrics import compute_aggregate_metrics
from eval.runner.preparation import (
    prepare_index_for_variant,
    prepare_meal,
    prepare_test_sets,
    prepare_variant_chunks,
)
from eval.visualize_profiler import generate_profiler_charts
from src.experiment import (
    ExperimentConfig,
    ExperimentManager,
    load_experiment_config,
    merge_config,
)
from src.experiment_reuse import (
    CopyMigrateHandler,
    InPlaceReuseHandler,
    ReportReuseConfig,
)
from src.generator import Generator
from src.hybrid_retriever import HybridRetriever
from src.meal import compute_variant_config_hash, create_artifact_cache
from src.pipeline import RAGPipeline
from src.token_tracker import DetailedTokenUsage, TokenTracker
from src.utils import get_llm_config, load_config, sanitize_name, setup_logger


def _add_experiment_log_handler(exp_dir: Path) -> int:
    """Add experiment log handler and return handler ID.

    Args:
        exp_dir: Path to the experiment directory.

    Returns:
        Handler ID for later removal.
    """
    experiment_log_path = exp_dir / "experiment.log"
    return logger.add(
        str(experiment_log_path),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        encoding="utf-8",
    )


def run_variant_evaluation(
    system_config: dict[str, Any],
    exp_config: ExperimentConfig,
    variant: dict[str, Any],
    meal_info: dict[str, Any],
    test_sets: list[dict[str, Any]],
    exp_dir: Path,
    test_generation_tracker: TokenTracker | None = None,
    profiler: PipelineProfiler | None = None,
    force_index: bool = False,
    indexer_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run evaluation for a single variant.

    Args:
        system_config: System configuration dictionary.
        exp_config: Experiment configuration.
        variant: Variant configuration dictionary.
        meal_info: Meal information dictionary.
        test_sets: List of test set dictionaries.
        exp_dir: Experiment directory path.
        test_generation_tracker: TokenTracker from test set generation phase.
        profiler: Optional PipelineProfiler for performance tracking.
        force_index: If True, delete existing index and rebuild from scratch.
        indexer_cache: Optional dict mapping chunker_hash to VectorIndexer for
            index reuse across variants with identical chunker configs.

    Returns:
        Evaluation result dictionary.

    Raises:
        Exception: If evaluation fails.
    """
    variant_name = variant.get("name", "unnamed")
    logger.info(f"Running evaluation for variant: {variant_name}")

    merged_config = merge_config(system_config, exp_config, variant)

    checkpoint_dir = exp_dir / "checkpoints"
    if checkpoint_dir.exists():
        safe_name = sanitize_name(variant_name)
        checkpoint_file = checkpoint_dir / f"{safe_name}_checkpoint.json"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, encoding="utf-8") as f:
                    ckpt_data = json.load(f)
                ckpt_model = ckpt_data.get("model_name", "")
                current_model = (
                    merged_config.get("llm_presets", {})
                    .get("default", {})
                    .get("model_name", "")
                )
                if ckpt_model and current_model and ckpt_model != current_model:
                    logger.warning(
                        f"Model change detected for variant '{variant_name}': "
                        f"checkpoint used '{ckpt_model}', current is '{current_model}'. "
                        f"Results may be inconsistent. Use --force-rerun to start fresh."
                    )
            except (json.JSONDecodeError, OSError):
                pass

    meal_name = meal_info["name"]
    meal_config = meal_info["config"]

    config_snapshot = {
        "data": exp_config.data,
        "test_sets": exp_config.test_sets,
        "evaluation": exp_config.evaluation,
        "variant": variant,
        "merged": sanitize_config(merged_config),
    }

    llm_preset = exp_config.evaluation.get("llm_preset", "default")

    try:
        variant_tracker = TokenTracker()
        indexer_from_cache = False

        pipeline = RAGPipeline(
            config=merged_config,
            llm_preset=llm_preset,
            meal_name=meal_name,
            token_tracker=variant_tracker,
            profiler=profiler,
        )

        from src.meal import compute_chunker_config_hash

        chunker_hash = compute_chunker_config_hash(merged_config.get("chunker", {}))

        old_indexer = pipeline.indexer
        if old_indexer is not None:
            with contextlib.suppress(Exception):
                old_indexer.close()
            pipeline.indexer = None

        if (
            indexer_cache is not None
            and chunker_hash in indexer_cache
            and not force_index
        ):
            logger.info(
                f"Reusing cached index for variant '{variant_name}' (chunker_hash={chunker_hash[:8]})"
            )
            indexer = indexer_cache[chunker_hash]
            if indexer.is_closed():
                for cached_indexer in indexer_cache.values():
                    if not cached_indexer.is_closed():
                        cached_indexer.close()
                indexer.reopen()
            indexer_from_cache = True
        else:
            if indexer_cache is not None:
                for cached_indexer in indexer_cache.values():
                    if not cached_indexer.is_closed():
                        cached_indexer.close()
            indexer = prepare_index_for_variant(
                merged_config,
                meal_config,
                variant_name,
                force_index=force_index,
                profiler=profiler,
            )
            if indexer_cache is not None and not force_index:
                indexer_cache[chunker_hash] = indexer
            indexer_from_cache = False

        pipeline.indexer = indexer

        pipeline._setup_retrievers()

        llm_config_merged = get_llm_config(merged_config, llm_preset)
        pipeline.generator = Generator(
            model_name=llm_config_merged["model_name"],
            api_key=llm_config_merged["api_key"],
            base_url=llm_config_merged["base_url"],
            temperature=llm_config_merged["temperature"],
            max_tokens=llm_config_merged["max_tokens"],
            token_tracker=variant_tracker,
            system_prompt=merged_config.get("generation", {}).get("system_prompt"),
        )

        retrieval_method = merged_config.get("retrieval", {}).get("method", "vector")
        if (
            retrieval_method in ("bm25", "hybrid")
            and pipeline.bm25_retriever is not None
        ):
            if profiler:
                profiler.begin_stage("S4")

            cache = create_artifact_cache(merged_config)
            chunker_hash = meal_config.config_hashes.get("chunker", "")
            chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)
            if chunks_dir.exists():
                pipeline.bm25_retriever.build_index_from_chunks(str(chunks_dir))
            else:
                logger.warning(f"Chunks dir not found for BM25: {chunks_dir}")
            if profiler:
                profiler.end_stage()

            if retrieval_method == "hybrid" and pipeline.hybrid_retriever is not None:
                pipeline.hybrid_retriever = HybridRetriever(
                    vector_retriever=pipeline.retriever,
                    bm25_retriever=pipeline.bm25_retriever,
                    fusion_method=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("fusion", "rrf"),
                    rrf_k=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("rrf_k", 60),
                    vector_weight=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("vector_weight", 0.7),
                    bm25_weight=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("bm25_weight", 0.3),
                    top_k=merged_config.get("retrieval", {}).get("top_k", 5),
                )

        total_start_time = time.time()
        all_results = []

        llm_config = get_llm_config(merged_config, llm_preset)

        checkpoint_dir = exp_dir / "checkpoints"
        max_questions = exp_config.evaluation.get("max_questions")

        for test_set in test_sets:
            results = evaluate_test_set(
                pipeline,
                test_set,
                exp_config=exp_config,
                system_config=system_config,
                meal_info=meal_info,
                checkpoint_dir=checkpoint_dir,
                variant_name=variant_name,
                experiment_name=exp_config.name,
                max_questions=max_questions,
                profiler=profiler,
            )
            all_results.extend(results)

        total_time = time.time() - total_start_time

        metrics = compute_aggregate_metrics(all_results)

        if profiler:
            s6_metrics = profiler.get_stage_metrics("S6")
            s7_metrics = profiler.get_stage_metrics("S7")
            rag_total = variant_tracker.get_total()
            if s7_metrics:
                gen_records = [
                    r for r in variant_tracker._records if r.category == "rag_qa"
                ]
                gen_input = sum(r.usage.input_tokens for r in gen_records)
                gen_output = sum(r.usage.output_tokens for r in gen_records)
                profiler.report_stage_tokens("S7", gen_input, gen_output)
                retr_input = rag_total.input_tokens - gen_input
                retr_output = rag_total.output_tokens - gen_output
                profiler.report_stage_tokens("S6", retr_input, retr_output)

        token_usage_data = variant_tracker.to_dict()
        if (
            test_generation_tracker is not None
            and test_generation_tracker.record_count > 0
        ):
            token_usage_data["test_generation"] = test_generation_tracker.to_dict()

        variant_result = {
            "variant_name": variant_name,
            "variant_description": variant.get("description", ""),
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(all_results),
            "partial_evaluation": max_questions is not None,
            "total_time_seconds": total_time,
            "avg_time_per_question": total_time / len(all_results)
            if all_results
            else 0,
            "retrieval_metrics": {
                k: v for k, v in metrics.items() if k != "generation_metrics"
            },
            "config_snapshot": config_snapshot,
            "results": all_results,
            "token_usage": token_usage_data,
        }

        if "generation_metrics" in metrics:
            variant_result["generation_metrics"] = metrics["generation_metrics"]

        log_parts = [
            f"HR={metrics.get('avg_hit_rate', 0):.4f}",
            f"MRR={metrics.get('avg_mrr', 0):.4f}",
            f"NDCG={metrics.get('avg_ndcg', 0):.4f}",
        ]
        if "generation_metrics" in metrics:
            for gk, gv in metrics["generation_metrics"].items():
                log_parts.append(f"{gk}={gv:.4f}")

        if "avg_context_precision" in metrics:
            log_parts.append(f"CP={metrics['avg_context_precision']:.4f}")
        if "avg_context_recall" in metrics:
            log_parts.append(f"CR={metrics['avg_context_recall']:.4f}")

        logger.success(
            f"Variant '{variant_name}' evaluation completed: " + ", ".join(log_parts)
        )

        token_total = variant_tracker.get_total()
        logger.info(
            f"Token usage for variant '{variant_name}': "
            f"in={token_total.input_tokens:,}, out={token_total.output_tokens:,}, "
            f"total={token_total.total_tokens:,}"
        )

        if indexer_cache is None:
            pipeline.close()
        else:
            pipeline.indexer = None

        checkpoint_dir = exp_dir / "checkpoints"
        if checkpoint_dir.exists():
            safe_name = sanitize_name(variant_name)
            checkpoint_file = checkpoint_dir / f"{safe_name}_checkpoint.json"
            if checkpoint_file.exists():
                try:
                    checkpoint_file.unlink()
                    logger.info(f"Cleaned up checkpoint for variant '{variant_name}'")
                except OSError:
                    pass

        return variant_result

    except Exception as e:
        logger.error(f"Failed to evaluate variant '{variant_name}': {str(e)}")
        if "pipeline" in locals():
            with contextlib.suppress(Exception):
                if indexer_cache is None:
                    pipeline.close()
                else:
                    pipeline.indexer = None
        raise


def run_experiment(
    config_path: str,
    skip_preprocessing: bool = False,
    use_llm_report: bool = False,
    system_config_path: str = "config.yaml",
    force_rerun: bool = False,
    force_variant: list[str] | None = None,
    resume_dir: str | None = None,
    reuse_config: ReportReuseConfig | None = None,
) -> dict[str, Any]:
    """
    Execute complete experiment workflow.

    Supports checkpoint resume: if the experiment directory already exists and
    some variants have been completed, those variants are skipped and only
    the remaining ones are executed.  Use ``force_rerun`` to ignore checkpoints
    and re-run everything from scratch.

    Use ``force_variant`` to selectively re-run specific variants by name,
    even if they have completed checkpoints.  This is useful when you want to
    re-run a single variant without affecting others.

    Use ``resume_dir`` to resume an interrupted experiment from an existing
    experiment directory.  When provided, the existing directory is reused
    instead of creating a new one, and the manifest records the resume event.

    Use ``reuse_config`` to enable experiment report reuse.  Two modes are
    supported: "in_place" (append variants to an existing experiment
    directory) and "copy_migrate" (copy an existing experiment to a new
    directory and add variants there).

    Args:
        config_path: Path to experiment configuration YAML file.
        skip_preprocessing: If True, skip meal and test set creation if missing.
        use_llm_report: If True, use LLM to generate experiment report.
        system_config_path: Path to system configuration file.
        force_rerun: If True, ignore checkpoints and re-run all variants.
        resume_dir: If provided, resume from this existing experiment directory.
        reuse_config: If provided, enable experiment report reuse.

    Returns:
        Dictionary containing complete experiment results.

    Raises:
        FileNotFoundError: If configuration files don't exist.
        ValueError: If configuration is invalid or resume_dir is invalid.
        Exception: If experiment execution fails.
    """
    logger.info(f"Loading experiment configuration from {config_path}")
    exp_config = load_experiment_config(config_path)

    logger.info(f"Experiment: {exp_config.name}")
    logger.info(f"Description: {exp_config.description}")
    logger.info(f"Variants: {len(exp_config.variants)}")
    logger.info(f"Test sets: {len(exp_config.test_sets)}")

    system_config = load_config(system_config_path)
    setup_logger(system_config)

    exp_manager = ExperimentManager(system_config)

    # Resolve reuse settings: CLI args take precedence over YAML config
    effective_reuse = reuse_config or exp_config.reuse
    if reuse_config and reuse_config.is_enabled():
        effective_reuse = reuse_config
        logger.info(f"Reuse mode from CLI: {effective_reuse.mode}")
    elif exp_config.reuse.is_enabled():
        effective_reuse = exp_config.reuse
        logger.info(f"Reuse mode from YAML config: {effective_reuse.mode}")

    # Resolve resume settings: CLI args take precedence over YAML config
    effective_resume_dir = resume_dir
    effective_force_rerun = force_rerun
    effective_force_variant = force_variant

    if exp_config.resume.is_enabled() and not resume_dir:
        resume_from = exp_config.resume.from_exp
        if resume_from:
            # Resolve path: if not absolute, treat as exp_id or relative path
            resume_path = Path(resume_from)
            if not resume_path.is_absolute():
                # Try as exp_id first
                exp_reports_dir = Path(
                    system_config.get("experiments", {}).get("dir", "data/exp_reports")
                )
                candidate = exp_reports_dir / resume_from
                if candidate.exists():
                    resume_path = candidate
                else:
                    # Try as relative path from project root
                    candidate = Path(resume_from)
                    if candidate.exists():
                        resume_path = candidate
            effective_resume_dir = str(resume_path)
            logger.info(f"Resume from YAML config: {effective_resume_dir}")

    if exp_config.resume.force_rerun and not force_rerun:
        effective_force_rerun = True
        logger.info("force_rerun from YAML config: True")

    if exp_config.resume.force_variants and not force_variant:
        effective_force_variant = exp_config.resume.force_variants
        logger.info(f"force_variants from YAML config: {effective_force_variant}")

    if effective_resume_dir:
        exp_dir = Path(effective_resume_dir)
        if not (exp_dir / "manifest.json").exists():
            raise ValueError(
                f"Not a valid experiment directory (missing manifest.json): {effective_resume_dir}"
            )
        logger.info(f"Resuming experiment from existing directory: {exp_dir}")
        exp_manager.mark_resumed(exp_dir)
    elif effective_reuse.is_in_place():
        target_path = Path(effective_reuse.target_dir)
        if not target_path.is_absolute():
            exp_reports_dir = Path(
                system_config.get("experiments", {}).get("dir", "data/exp_reports")
            )
            candidate = exp_reports_dir / effective_reuse.target_dir
            if candidate.exists():
                target_path = candidate
            else:
                candidate = Path(effective_reuse.target_dir)
                if candidate.exists():
                    target_path = candidate

        in_place_handler = InPlaceReuseHandler(
            target_dir=target_path,
            backup_before_append=effective_reuse.backup_before_append,
        )
        target_manifest = in_place_handler.validate_target_dir()

        backup_snapshot_path = None
        if effective_reuse.backup_before_append:
            snapshot = in_place_handler.create_full_snapshot()
            if snapshot:
                backup_snapshot_path = str(snapshot)

        stored_hashes = exp_manager.get_variant_config_hashes(target_path)
        incremental_plan = in_place_handler.compute_incremental_updates(
            new_variants=exp_config.variants,
            manifest=target_manifest,
            stored_hashes=stored_hashes,
        )

        if incremental_plan.has_conflicts:
            conflicting = [
                v.get("name", "unnamed") for v in incremental_plan.to_confirm
            ]
            logger.warning(
                f"Conflicting variants detected: {conflicting}. "
                f"Use --force-variant to override, or remove conflicting variants from config."
            )
            for v in incremental_plan.to_confirm:
                vname = v.get("name", "unnamed")
                logger.warning(
                    f"  Variant '{vname}' exists with different config — will be re-run"
                )
            effective_force_variant = list(
                set((effective_force_variant or []) + conflicting)
            )

        exp_dir = target_path
        logger.info(f"In-place reuse mode: appending to {exp_dir}")

        in_place_handler.record_reuse_history(
            action="in_place_start",
            backup_snapshot=backup_snapshot_path,
            details={
                "new_variants": [
                    v.get("name", "unnamed") for v in incremental_plan.to_run
                ],
                "reuse_variants": [
                    v.get("name", "unnamed") for v in incremental_plan.to_reuse
                ],
                "conflict_variants": [
                    v.get("name", "unnamed") for v in incremental_plan.to_confirm
                ],
            },
        )

        for v in incremental_plan.to_run:
            in_place_handler.append_variant_to_manifest(v.get("name", "unnamed"))
    elif effective_reuse.is_copy_migrate():
        source_path = Path(effective_reuse.source_dir)
        if not source_path.is_absolute():
            exp_reports_dir = Path(
                system_config.get("experiments", {}).get("dir", "data/exp_reports")
            )
            candidate = exp_reports_dir / effective_reuse.source_dir
            if candidate.exists():
                source_path = candidate
            else:
                candidate = Path(effective_reuse.source_dir)
                if candidate.exists():
                    source_path = candidate

        migrate_handler = CopyMigrateHandler(
            source_dir=source_path,
            exp_dir=Path("placeholder"),
        )

        source_manifest = migrate_handler.validate_source_dir()
        source_exp_id = source_manifest.get("experiment_id", source_path.name)

        new_exp_dir = exp_manager.create_experiment_dir(exp_config)
        migrate_handler = CopyMigrateHandler(
            source_dir=source_path,
            exp_dir=new_exp_dir,
        )

        migrate_handler.copy_experiment()

        new_exp_id = new_exp_dir.name
        migrate_handler.update_identifiers(new_exp_id, source_exp_id)
        migrate_handler.verify_migration()

        exp_dir = new_exp_dir
        logger.info(
            f"Copy-migrate reuse mode: migrated {source_exp_id} -> {new_exp_id}"
        )
    else:
        exp_dir = exp_manager.create_experiment_dir(exp_config)

    exp_log_handler_id = _add_experiment_log_handler(exp_dir)

    logger.info(f"Experiment directory: {exp_dir}")

    profiling_config = system_config.get("experiments", {}).get("profiling", {})
    profiling_enabled = profiling_config.get("enabled", True)

    if profiling_enabled:
        profiler = PipelineProfiler(
            experiment_name=exp_config.name,
            total_pages=0,
            total_questions=sum(
                ts.get("generation", {}).get(
                    "num_questions", ts.get("num_questions", 10)
                )
                for ts in exp_config.test_sets
            ),
            monitor_interval=profiling_config.get("monitor_interval", 0.5),
        )
        profiler.start_profiling()
        logger.info("Performance profiling enabled")
    else:
        profiler = None
        logger.info("Performance profiling disabled by config")

    try:
        force_meal = exp_config.should_force("meal")
        force_parsed = exp_config.should_force("parsed")
        force_chunk = exp_config.should_force("chunk")
        force_vector = exp_config.should_force("vector")
        force_testset = exp_config.should_force("testset")

        if exp_config.force_overwrite:
            stages = (
                "all"
                if exp_config.force_overwrite == "all"
                else ", ".join(exp_config.force_overwrite)
            )
            logger.info(f"Force overwrite enabled for: {stages}")

        logger.info("Step 1: Preparing meal...")
        meal_info = prepare_meal(
            system_config,
            exp_config,
            skip_preprocessing,
            force_meal=force_meal,
            force_parse=force_parsed,
            force_chunk=force_chunk,
            profiler=profiler,
        )

        test_generation_tracker = TokenTracker()

        logger.info("Step 2: Preparing variant chunks...")
        first_chunks_dir = None
        for i, variant in enumerate(exp_config.variants, 1):
            variant_name = variant.get("name", f"variant_{i}")
            merged_config = merge_config(system_config, exp_config, variant)
            chunks_dir = prepare_variant_chunks(
                merged_config,
                meal_info["config"],
                variant_name,
                force_chunk=force_chunk,
            )
            if first_chunks_dir is None:
                first_chunks_dir = chunks_dir

        logger.info("Step 3: Preparing test sets...")
        with profiler.profile_stage("S5"):
            test_sets = prepare_test_sets(
                system_config,
                exp_config,
                meal_info,
                skip_preprocessing,
                token_tracker=test_generation_tracker,
                chunks_dir=first_chunks_dir,
                force_testset=force_testset,
            )

        if profiler:
            test_gen_total = test_generation_tracker.get_total()
            profiler.report_stage_tokens(
                "S5",
                test_gen_total.input_tokens,
                test_gen_total.output_tokens,
            )

        meal_snapshot = meal_info["config"].to_dict()

        test_set_snapshots = []
        for test_set in test_sets:
            metadata = test_set.get("metadata", {})
            generation = metadata.get("generation", {})
            test_set_snapshots.append(
                {
                    "name": test_set.get("name") or metadata.get("name"),
                    "strategy": test_set.get("strategy") or generation.get("strategy"),
                    "num_questions": len(test_set.get("questions", [])),
                    "created_at": test_set.get("created_at")
                    or metadata.get("created_at"),
                    "meal_data_id": test_set.get("meal_data_id")
                    or metadata.get("meal_id"),
                    "questions": test_set.get("questions", []),
                }
            )

        config_snapshot = {
            "data": exp_config.data,
            "test_sets": exp_config.test_sets,
            "evaluation": exp_config.evaluation,
            "llm": exp_config.llm,
            "system_config": sanitize_config(system_config),
            "environment": collect_environment_info(),
        }

        if not effective_resume_dir and not effective_reuse.is_enabled():
            exp_manager.save_snapshots(
                exp_dir=exp_dir,
                config=exp_config,
                meal_snapshot=meal_snapshot,
                test_set_snapshots=test_set_snapshots,
                config_snapshot=config_snapshot,
            )
        elif effective_reuse.is_in_place():
            logger.info("In-place reuse: skipping snapshot save (already exists)")
        elif effective_reuse.is_copy_migrate():
            logger.info(
                "Copy-migrate reuse: skipping snapshot save (migrated from source)"
            )
        else:
            logger.info("Resuming: skipping snapshot save (already exists)")

        logger.info("Step 4: Running variant evaluations...")
        all_variant_results = []
        experiment_tracker = TokenTracker()

        completed_variants: set[str] = set()
        stored_hashes: dict[str, str] = {}
        if not effective_force_rerun:
            completed_variants = set(exp_manager.get_completed_variants(exp_dir))
            stored_hashes = exp_manager.get_variant_config_hashes(exp_dir)
            if completed_variants:
                logger.info(
                    f"Checkpoint resume: {len(completed_variants)} variant(s) already completed: "
                    f"{sorted(completed_variants)}"
                )
                if stored_hashes:
                    logger.info(
                        f"Config hash verification enabled ({len(stored_hashes)} hash(es) stored)"
                    )
                else:
                    logger.warning(
                        "No config hashes found in manifest — variant reuse will NOT be "
                        "verified. Re-run without --resume to generate hashes, or use "
                        "--force-rerun to start fresh."
                    )
        else:
            logger.info("Force rerun: ignoring checkpoints, re-running all variants")
            exp_manager.update_manifest_field(exp_dir, "completed_variants", [])
            exp_manager.update_manifest_field(exp_dir, "variant_config_hashes", {})

        if effective_force_variant and not effective_force_rerun:
            for vname in effective_force_variant:
                if vname in completed_variants:
                    logger.info(
                        f"Force re-run variant '{vname}' (requested via --force-variant)"
                    )
                    exp_manager.invalidate_variant(exp_dir, vname)
                    completed_variants.discard(vname)
                else:
                    logger.info(
                        f"Force variant '{vname}' requested but it was not yet completed "
                        f"— will run normally"
                    )

        indexer_cache: dict[str, Any] = {}

        for i, variant in enumerate(exp_config.variants, 1):
            variant_name = variant.get("name", f"variant_{i}")

            if variant_name in completed_variants and not effective_force_rerun:
                merged = merge_config(system_config, exp_config, variant)
                current_hash = compute_variant_config_hash(
                    variant=variant,
                    merged_config=sanitize_config(merged),
                    exp_data=exp_config.data,
                    exp_test_sets=exp_config.test_sets,
                    exp_evaluation=exp_config.evaluation,
                )

                stored_hash = stored_hashes.get(variant_name)
                hash_match = stored_hash is not None and stored_hash == current_hash

                if hash_match:
                    logger.info(
                        f"Skipping completed variant {i}/{len(exp_config.variants)}: "
                        f"{variant_name} (checkpoint, hash={current_hash[:8]}… verified)"
                    )
                    existing_result = exp_manager.load_variant_result(
                        exp_dir, variant_name
                    )
                    if existing_result is not None:
                        all_variant_results.append(existing_result)
                        if "token_usage" in existing_result:
                            variant_tracker = TokenTracker()
                            for rec_data in existing_result["token_usage"].get(
                                "records", []
                            ):
                                usage = DetailedTokenUsage(
                                    input_tokens=rec_data["usage"]["input_tokens"],
                                    output_tokens=rec_data["usage"]["output_tokens"],
                                    system_prompt_tokens=rec_data["usage"].get(
                                        "system_prompt_tokens", 0
                                    ),
                                    contexts_tokens=rec_data["usage"].get(
                                        "contexts_tokens", 0
                                    ),
                                    query_tokens=rec_data["usage"].get(
                                        "query_tokens", 0
                                    ),
                                )
                                variant_tracker.record(
                                    category=rec_data["category"],
                                    model_name=rec_data["model_name"],
                                    usage=usage,
                                    variant_name=variant_name,
                                )
                            experiment_tracker.merge(variant_tracker)
                        continue
                    else:
                        logger.warning(
                            f"Variant '{variant_name}' marked completed but result file not found, re-running"
                        )
                        completed_variants.discard(variant_name)
                else:
                    if stored_hash is None:
                        logger.warning(
                            f"Variant '{variant_name}' has no stored config hash — "
                            f"cannot verify reuse. Re-running to be safe."
                        )
                    else:
                        logger.warning(
                            f"Variant '{variant_name}' config has changed "
                            f"(stored={stored_hash[:8]}…, current={current_hash[:8]}…) — "
                            f"invalidating and re-running"
                        )
                    exp_manager.invalidate_variant(exp_dir, variant_name)
                    completed_variants.discard(variant_name)

            logger.info(
                f"Evaluating variant {i}/{len(exp_config.variants)}: {variant_name}"
            )

            try:
                variant_result = run_variant_evaluation(
                    system_config=system_config,
                    exp_config=exp_config,
                    variant=variant,
                    meal_info=meal_info,
                    test_sets=test_sets,
                    exp_dir=exp_dir,
                    test_generation_tracker=test_generation_tracker,
                    profiler=profiler,
                    force_index=force_vector,
                    indexer_cache=indexer_cache,
                )

                merged = merge_config(system_config, exp_config, variant)
                config_hash = compute_variant_config_hash(
                    variant=variant,
                    merged_config=sanitize_config(merged),
                    exp_data=exp_config.data,
                    exp_test_sets=exp_config.test_sets,
                    exp_evaluation=exp_config.evaluation,
                )

                exp_manager.save_variant_result(exp_dir, variant_name, variant_result)
                exp_manager.mark_variant_completed(
                    exp_dir, variant_name, config_hash=config_hash
                )
                all_variant_results.append(variant_result)

                if "token_usage" in variant_result:
                    variant_tracker = TokenTracker()
                    for rec_data in variant_result["token_usage"].get("records", []):
                        usage = DetailedTokenUsage(
                            input_tokens=rec_data["usage"]["input_tokens"],
                            output_tokens=rec_data["usage"]["output_tokens"],
                            system_prompt_tokens=rec_data["usage"].get(
                                "system_prompt_tokens", 0
                            ),
                            contexts_tokens=rec_data["usage"].get("contexts_tokens", 0),
                            query_tokens=rec_data["usage"].get("query_tokens", 0),
                        )
                        variant_tracker.record(
                            category=rec_data["category"],
                            model_name=rec_data["model_name"],
                            usage=usage,
                            variant_name=variant_name,
                        )
                    experiment_tracker.merge(variant_tracker)

            except Exception as e:
                logger.error(f"Variant '{variant_name}' failed: {str(e)}")
                error_result = {
                    "variant_name": variant_name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                exp_manager.save_variant_result(exp_dir, variant_name, error_result)
                all_variant_results.append(error_result)

        experiment_tracker.merge(test_generation_tracker)

        logger.info("Step 4: Generating experiment report...")

        with profiler.profile_stage("S8"):
            if all_variant_results:
                llm_preset_name = exp_config.evaluation.get("llm_preset", "default")
                llm_config = get_llm_config(system_config, llm_preset_name)

                reporter = ExperimentReporter(
                    llm_api_key=llm_config.get("api_key"),
                    llm_base_url=llm_config.get("base_url"),
                    llm_model_name=llm_config.get("model_name"),
                    token_tracker=experiment_tracker,
                )

                reporter.generate_variant_comparison_report(
                    exp_dir=exp_dir,
                    variant_results=all_variant_results,
                    meal_info=meal_info,
                    config_snapshot=config_snapshot,
                    output_filename="experiment_report.md",
                    use_llm=False,
                )

                if use_llm_report or exp_config.evaluation.get("llm_report", False):
                    has_successful = any(
                        "retrieval_metrics" in v for v in all_variant_results
                    )
                    if not has_successful:
                        logger.warning(
                            "All variants failed — skipping LLM report generation"
                        )
                    else:
                        logger.info("Generating LLM-enhanced report...")
                        try:
                            reporter.generate_variant_comparison_report(
                                exp_dir=exp_dir,
                                variant_results=all_variant_results,
                                meal_info=meal_info,
                                config_snapshot=config_snapshot,
                                output_filename="experiment_report_llm.md",
                                use_llm=True,
                            )
                            logger.success("LLM-enhanced report generated successfully")
                        except Exception as e:
                            logger.warning(f"Failed to generate LLM report: {str(e)}")

        exp_manager.update_manifest_status(exp_dir, "completed")

        if profiler:
            profiler.stop_profiling()
            if meal_info.get("config") and hasattr(meal_info["config"], "stats"):
                profiler.total_pages = meal_info["config"].stats.get("total_pages", 0)

            profiling_dir = exp_dir / "profiling"
            profiler.save_report(profiling_dir, "profile_data.json")

            profile_md = profiler.generate_markdown_report()
            profile_md_path = profiling_dir / "profile_report.md"
            profile_md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_md_path, "w", encoding="utf-8") as f:
                f.write(profile_md)
            logger.success(f"Performance profile report saved to: {profile_md_path}")

            if profiling_config.get("generate_charts", True):
                try:
                    chart_files = generate_profiler_charts(
                        profiler, profiling_dir / "charts"
                    )
                    if chart_files:
                        logger.success(
                            f"Generated {len(chart_files)} performance charts"
                        )
                except Exception as e:
                    logger.warning(f"Failed to generate performance charts: {str(e)}")

        experiment_tracker.get_total()
        token_cost_config = system_config.get("token_cost", {})
        cost_info = experiment_tracker.estimate_cost(token_cost_config)

        try:
            token_summary_data = experiment_tracker.to_dict()
            token_summary_data["estimated_cost"] = cost_info
            token_summary_path = exp_dir / "token_summary.json"
            with open(token_summary_path, "w", encoding="utf-8") as f:
                json.dump(token_summary_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Token summary saved to {token_summary_path}")

            token_table = experiment_tracker.get_detailed_table()
            if cost_info["total_cost"] > 0:
                token_table += f"\n\nEstimated Cost (model: {cost_info['model']}):\n"
                token_table += f"  Input:  ${cost_info['input_cost']:.4f}\n"
                token_table += f"  Output: ${cost_info['output_cost']:.4f}\n"
                token_table += f"  Total:  ${cost_info['total_cost']:.4f}\n"
            token_table_path = exp_dir / "token_summary.txt"
            with open(token_table_path, "w", encoding="utf-8") as f:
                f.write(token_table)
            logger.info(f"Token summary table saved to {token_table_path}")
        except Exception as e:
            logger.warning(f"Failed to save token summary: {str(e)}")

        print("\n" + experiment_tracker.get_detailed_table())

        if cost_info["total_cost"] > 0:
            print(f"\nEstimated Cost (model: {cost_info['model']}):")
            print(f"  Input:  ${cost_info['input_cost']:.4f}")
            print(f"  Output: ${cost_info['output_cost']:.4f}")
            print(f"  Total:  ${cost_info['total_cost']:.4f}")

        logger.success(f"Experiment completed successfully: {exp_dir}")

        return {
            "experiment_id": exp_dir.name,
            "exp_dir": str(exp_dir),
            "config": exp_config.to_dict(),
            "meal_info": {
                "name": meal_info["name"],
                "data_id": meal_info["data_id"],
                "status": meal_info["status"].value,
            },
            "test_sets": test_set_snapshots,
            "variant_results": all_variant_results,
            "token_usage": experiment_tracker.to_dict(),
            "estimated_cost": cost_info,
        }

    except Exception as e:
        exp_manager.update_manifest_status(exp_dir, "failed")
        logger.error(f"Experiment failed: {str(e)}")
        raise
    finally:
        logger.remove(exp_log_handler_id)


def list_experiments(system_config_path: str = "config.yaml") -> None:
    """
    List all experiments.

    Args:
        system_config_path: Path to system configuration file.
    """
    system_config = load_config(system_config_path)
    exp_manager = ExperimentManager(system_config)

    experiments = exp_manager.list_experiments()

    if not experiments:
        print("No experiments found.")
        return

    print("\n" + "=" * 80)
    print("EXPERIMENTS")
    print("=" * 80)

    for exp in experiments:
        print(f"\nID: {exp['experiment_id']}")
        print(f"Name: {exp['name']}")
        print(f"Created: {exp['created_at']}")
        print(f"Status: {exp['status']}")
        print(f"Path: {exp['path']}")

    print("\n" + "=" * 80)


def show_experiment_info(exp_id: str, system_config_path: str = "config.yaml") -> None:
    """
    Show detailed information about an experiment.

    Args:
        exp_id: Experiment ID or directory name.
        system_config_path: Path to system configuration file.
    """
    system_config = load_config(system_config_path)
    exp_manager = ExperimentManager(system_config)

    try:
        info = exp_manager.get_experiment_info(exp_id)

        print("\n" + "=" * 80)
        print(f"EXPERIMENT: {info['name']}")
        print("=" * 80)

        print(f"\nID: {info['experiment_id']}")
        print(f"Description: {info['description']}")
        print(f"Created: {info['created_at']}")
        print(f"Status: {info['status']}")

        if info.get("meal_snapshot"):
            print(f"\nMeal: {info['meal_snapshot'].get('name', 'N/A')}")
            print(f"Data ID: {info['meal_snapshot'].get('data_id', 'N/A')[:12]}...")

        if info.get("test_set_snapshots"):
            print(f"\nTest Sets ({len(info['test_set_snapshots'])}):")
            for ts in info["test_set_snapshots"]:
                print(
                    f"  - {ts.get('strategy', 'unknown')}: {ts.get('num_questions', 0)} questions"
                )

        if info.get("variant_results"):
            print(f"\nVariant Results ({len(info['variant_results'])}):")
            for vr in info["variant_results"]:
                name = vr.get("variant_name", "unknown")
                if "retrieval_metrics" in vr:
                    metrics = vr["retrieval_metrics"]
                    print(
                        f"  - {name}: HR={metrics.get('avg_hit_rate', 0):.4f}, "
                        f"MRR={metrics.get('avg_mrr', 0):.4f}, "
                        f"NDCG={metrics.get('avg_ndcg', 0):.4f}"
                    )
                else:
                    print(f"  - {name}: {vr.get('error', 'No metrics')}")

        print("\n" + "=" * 80)

    except FileNotFoundError:
        print(f"Experiment not found: {exp_id}")
        sys.exit(1)
