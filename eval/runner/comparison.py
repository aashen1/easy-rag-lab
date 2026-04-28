from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.experiment import ExperimentManager
from src.utils import load_config


def compare_experiments(
    exp_ids: list[str],
    system_config_path: str = "config.yaml",
    output_format: str = "table",
    save_report: bool = False,
    report_path: str | None = None,
) -> dict[str, Any]:
    """
    Compare multiple experiments and generate a comparison report.

    This function loads multiple experiments and compares their:
    - Retrieval metrics (Hit Rate, MRR, NDCG)
    - Configuration differences
    - Test set characteristics
    - Performance by question category (if available)

    Args:
        exp_ids: List of experiment IDs to compare.
        system_config_path: Path to system configuration file.
        output_format: Output format, either 'table' or 'json'.
        save_report: If True, save the comparison report to a file.
        report_path: Path to save the report. If not specified, saves to
                    data/exp_reports/comparison_{timestamp}.md

    Returns:
        Dictionary containing comparison results.
    """
    system_config = load_config(system_config_path)
    exp_manager = ExperimentManager(system_config)

    results = []
    not_found = []

    for exp_id in exp_ids:
        try:
            info = exp_manager.get_experiment_info(exp_id)
            results.append(info)
        except FileNotFoundError:
            not_found.append(exp_id)
            logger.warning(f"Experiment not found: {exp_id}")

    if not results:
        print("No valid experiments to compare.")
        return {"error": "No valid experiments", "not_found": not_found}

    comparison_data = build_comparison_data(results)

    if output_format == "table":
        print_comparison_table(comparison_data, not_found)
    else:
        print(json.dumps(comparison_data, indent=2, ensure_ascii=False))

    if save_report:
        report_content = generate_comparison_report(comparison_data, not_found)
        if report_path:
            report_file = Path(report_path)
        else:
            exp_dir = Path(
                system_config.get("experiments", {}).get("dir", "data/exp_reports")
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = exp_dir / f"comparison_{timestamp}.md"

        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)
        logger.success(f"Comparison report saved to: {report_file}")

    return {
        "experiments_compared": len(results),
        "not_found": not_found,
        "comparison_data": comparison_data,
    }


def build_comparison_data(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build structured comparison data from experiment results.

    Args:
        results: List of experiment info dictionaries.

    Returns:
        Structured comparison data dictionary.
    """
    experiments = []

    for info in results:
        exp_data = {
            "experiment_id": info.get("experiment_id", "unknown"),
            "name": info.get("name", "unknown"),
            "description": info.get("description", ""),
            "created_at": info.get("created_at", ""),
            "status": info.get("status", "unknown"),
            "variants": [],
            "meal_info": {},
            "test_sets": [],
        }

        if info.get("meal_snapshot"):
            meal = info["meal_snapshot"]
            exp_data["meal_info"] = {
                "name": meal.get("name", "N/A"),
                "data_id": meal.get("data_id", "N/A")[:12]
                if meal.get("data_id")
                else "N/A",
                "pdf_count": meal.get("stats", {}).get("total_pdfs", 0),
                "page_count": meal.get("stats", {}).get("total_pages", 0),
                "chunk_count": meal.get("stats", {}).get("total_chunks", 0),
            }

        if info.get("test_set_snapshots"):
            for ts in info["test_set_snapshots"]:
                exp_data["test_sets"].append(
                    {
                        "strategy": ts.get("strategy", "unknown"),
                        "num_questions": ts.get("num_questions", 0),
                    }
                )

        if info.get("variant_results"):
            for vr in info["variant_results"]:
                variant_data = {
                    "name": vr.get("variant_name", "unknown"),
                    "description": vr.get("variant_description", ""),
                    "total_questions": vr.get("total_questions", 0),
                    "total_time_seconds": vr.get("total_time_seconds", 0),
                    "avg_time_per_question": vr.get("avg_time_per_question", 0),
                }

                if "retrieval_metrics" in vr:
                    metrics = vr["retrieval_metrics"]
                    variant_data["metrics"] = {
                        "hit_rate": metrics.get("avg_hit_rate", 0),
                        "mrr": metrics.get("avg_mrr", 0),
                        "ndcg": metrics.get("avg_ndcg", 0),
                    }
                else:
                    variant_data["metrics"] = {
                        "hit_rate": 0,
                        "mrr": 0,
                        "ndcg": 0,
                    }
                    variant_data["error"] = vr.get("error", "No metrics available")

                if "config_snapshot" in vr:
                    config = vr["config_snapshot"]
                    if "merged" in config:
                        merged = config["merged"]
                        variant_data["config"] = {
                            "chunk_size": merged.get("chunker", {}).get(
                                "chunk_size", "N/A"
                            ),
                            "chunk_overlap": merged.get("chunker", {}).get(
                                "chunk_overlap", "N/A"
                            ),
                            "embedding_model": merged.get("embedding", {}).get(
                                "model_name", "N/A"
                            ),
                            "top_k": merged.get("retrieval", {}).get("top_k", "N/A"),
                        }

                category_metrics = extract_category_metrics(vr)
                if category_metrics:
                    variant_data["category_metrics"] = category_metrics

                exp_data["variants"].append(variant_data)

        experiments.append(exp_data)

    best_variants = []
    for exp in experiments:
        best_variant = None
        best_hr = 0
        for v in exp["variants"]:
            if v["metrics"]["hit_rate"] > best_hr:
                best_hr = v["metrics"]["hit_rate"]
                best_variant = v
        if best_variant:
            best_variants.append(
                {
                    "experiment_name": exp["name"],
                    "variant_name": best_variant["name"],
                    "metrics": best_variant["metrics"],
                }
            )

    if best_variants:
        best_variants.sort(key=lambda x: x["metrics"]["hit_rate"], reverse=True)

    return {
        "experiments": experiments,
        "best_variants": best_variants,
        "summary": {
            "total_experiments": len(experiments),
            "total_variants": sum(len(e["variants"]) for e in experiments),
        },
    }


def extract_category_metrics(
    variant_result: dict[str, Any],
) -> dict[str, dict[str, float]]:
    """
    Extract metrics grouped by question category from variant results.

    Args:
        variant_result: Variant result dictionary.

    Returns:
        Dictionary mapping category names to their metrics.
    """
    category_metrics: dict[str, dict[str, list[float]]] = {}

    for result in variant_result.get("results", []):
        category = result.get("category", "unknown")
        if category not in category_metrics:
            category_metrics[category] = {
                "hit_rates": [],
                "mrrs": [],
                "ndcgs": [],
            }

        if "retrieval" in result:
            category_metrics[category]["hit_rates"].append(
                result["retrieval"].get("hit_rate", 0)
            )
            category_metrics[category]["mrrs"].append(result["retrieval"].get("mrr", 0))
            category_metrics[category]["ndcgs"].append(
                result["retrieval"].get("ndcg", 0)
            )

    averaged_metrics = {}
    for category, values in category_metrics.items():
        if values["hit_rates"]:
            averaged_metrics[category] = {
                "hit_rate": sum(values["hit_rates"]) / len(values["hit_rates"]),
                "mrr": sum(values["mrrs"]) / len(values["mrrs"]),
                "ndcg": sum(values["ndcgs"]) / len(values["ndcgs"]),
                "count": len(values["hit_rates"]),
            }

    return averaged_metrics


def print_comparison_table(
    comparison_data: dict[str, Any],
    not_found: list[str],
) -> None:
    """
    Print comparison results in table format.

    Args:
        comparison_data: Structured comparison data.
        not_found: List of experiment IDs that were not found.
    """
    print("\n" + "=" * 120)
    print("EXPERIMENT COMPARISON REPORT")
    print("=" * 120)

    if not_found:
        print(
            f"\nWarning: The following experiments were not found: {', '.join(not_found)}"
        )

    print("\n" + "-" * 120)
    print("SUMMARY: BEST VARIANT PER EXPERIMENT")
    print("-" * 120)
    print(
        f"{'Experiment':<35} {'Variant':<25} {'Hit Rate':>10} {'MRR':>10} {'NDCG':>10}"
    )
    print("-" * 120)

    for bv in comparison_data["best_variants"]:
        print(
            f"{bv['experiment_name'][:33]:<35} {bv['variant_name'][:23]:<25} "
            f"{bv['metrics']['hit_rate']:>10.4f} {bv['metrics']['mrr']:>10.4f} "
            f"{bv['metrics']['ndcg']:>10.4f}"
        )

    print("-" * 120)

    print("\n" + "-" * 120)
    print("DETAILED RESULTS: ALL VARIANTS")
    print("-" * 120)

    for exp in comparison_data["experiments"]:
        print(f"\nExperiment: {exp['name']} ({exp['experiment_id']})")
        print(f"Status: {exp['status']} | Created: {exp['created_at']}")

        if exp["meal_info"]:
            print(
                f"Meal: {exp['meal_info']['name']} ({exp['meal_info']['pdf_count']} PDFs, "
                f"{exp['meal_info']['page_count']} pages)"
            )

        if exp["test_sets"]:
            test_set_str = ", ".join(
                f"{ts['strategy']}({ts['num_questions']})" for ts in exp["test_sets"]
            )
            print(f"Test Sets: {test_set_str}")

        print(
            f"\n{'Variant':<30} {'Hit Rate':>10} {'MRR':>10} {'NDCG':>10} {'Time':>10}"
        )
        print("-" * 80)

        for v in exp["variants"]:
            time_str = (
                f"{v['avg_time_per_question']:.2f}s"
                if v.get("avg_time_per_question")
                else "N/A"
            )
            print(
                f"{v['name'][:28]:<30} {v['metrics']['hit_rate']:>10.4f} "
                f"{v['metrics']['mrr']:>10.4f} {v['metrics']['ndcg']:>10.4f} {time_str:>10}"
            )

            if "error" in v:
                print(f"  Error: {v['error']}")

            if "category_metrics" in v:
                print("  By Category:")
                for cat, metrics in v["category_metrics"].items():
                    print(
                        f"    {cat}: HR={metrics['hit_rate']:.4f}, "
                        f"MRR={metrics['mrr']:.4f}, NDCG={metrics['ndcg']:.4f} ({metrics['count']} questions)"
                    )

    print("\n" + "=" * 120 + "\n")


def generate_comparison_report(
    comparison_data: dict[str, Any],
    not_found: list[str],
) -> str:
    """
    Generate a Markdown comparison report.

    Args:
        comparison_data: Structured comparison data.
        not_found: List of experiment IDs that were not found.

    Returns:
        Markdown formatted report string.
    """
    lines = []
    lines.append("# Experiment Comparison Report")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().isoformat()}")
    lines.append(
        f"**Experiments Compared**: {comparison_data['summary']['total_experiments']}"
    )
    lines.append(f"**Total Variants**: {comparison_data['summary']['total_variants']}")
    lines.append("")

    if not_found:
        lines.append("## Warnings")
        lines.append("")
        lines.append(
            f"The following experiments were not found: {', '.join(not_found)}"
        )
        lines.append("")

    lines.append("## Summary: Best Variants")
    lines.append("")
    lines.append("| Experiment | Variant | Hit Rate | MRR | NDCG |")
    lines.append("|------------|---------|----------|-----|------|")

    for bv in comparison_data["best_variants"]:
        lines.append(
            f"| {bv['experiment_name']} | {bv['variant_name']} | "
            f"{bv['metrics']['hit_rate']:.4f} | {bv['metrics']['mrr']:.4f} | "
            f"{bv['metrics']['ndcg']:.4f} |"
        )

    lines.append("")

    for exp in comparison_data["experiments"]:
        lines.append(f"## Experiment: {exp['name']}")
        lines.append("")
        lines.append(f"- **ID**: {exp['experiment_id']}")
        lines.append(f"- **Status**: {exp['status']}")
        lines.append(f"- **Created**: {exp['created_at']}")
        lines.append("")

        if exp["meal_info"]:
            lines.append("### Data Source")
            lines.append("")
            lines.append(f"- **Meal**: {exp['meal_info']['name']}")
            lines.append(f"- **PDFs**: {exp['meal_info']['pdf_count']}")
            lines.append(f"- **Pages**: {exp['meal_info']['page_count']}")
            lines.append(f"- **Chunks**: {exp['meal_info']['chunk_count']}")
            lines.append("")

        if exp["test_sets"]:
            lines.append("### Test Sets")
            lines.append("")
            for ts in exp["test_sets"]:
                lines.append(f"- {ts['strategy']}: {ts['num_questions']} questions")
            lines.append("")

        lines.append("### Variant Results")
        lines.append("")
        lines.append("| Variant | Hit Rate | MRR | NDCG | Avg Time |")
        lines.append("|---------|----------|-----|------|----------|")

        for v in exp["variants"]:
            time_str = (
                f"{v['avg_time_per_question']:.2f}s"
                if v.get("avg_time_per_question")
                else "N/A"
            )
            lines.append(
                f"| {v['name']} | {v['metrics']['hit_rate']:.4f} | "
                f"{v['metrics']['mrr']:.4f} | {v['metrics']['ndcg']:.4f} | {time_str} |"
            )

        lines.append("")

        for v in exp["variants"]:
            if "category_metrics" in v:
                lines.append(f"#### {v['name']} - By Category")
                lines.append("")
                lines.append("| Category | Hit Rate | MRR | NDCG | Count |")
                lines.append("|----------|----------|-----|------|-------|")
                for cat, metrics in v["category_metrics"].items():
                    lines.append(
                        f"| {cat} | {metrics['hit_rate']:.4f} | "
                        f"{metrics['mrr']:.4f} | {metrics['ndcg']:.4f} | {metrics['count']} |"
                    )
                lines.append("")

    return "\n".join(lines)
