import json
from pathlib import Path
from typing import Any

from loguru import logger

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def load_experiment_results(exp_dir: str) -> dict[str, Any]:
    """Load all variant results from an experiment directory.

    Reads the manifest and each variant's result JSON file.

    Args:
        exp_dir: Path to the experiment directory.

    Returns:
        Dictionary with ``manifest``, ``variants`` (dict of variant name
        to result data), and ``exp_name`` keys.

    Raises:
        FileNotFoundError: If the experiment directory does not exist.
    """
    exp_path = Path(exp_dir)

    if not exp_path.exists():
        raise FileNotFoundError(f"Experiment directory not found: {exp_dir}")

    manifest_path = exp_path / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    results_dir = exp_path / "results"
    variants = {}

    if results_dir.exists():
        for result_file in results_dir.glob("*.json"):
            variant_name = result_file.stem
            with open(result_file, encoding="utf-8") as f:
                variants[variant_name] = json.load(f)

    return {
        "manifest": manifest,
        "variants": variants,
        "exp_name": manifest.get("name", exp_path.name),
    }


def extract_metrics(variants: dict[str, Any]) -> dict[str, dict[str, list[tuple]]]:
    """Extract metrics from variant results for visualization.

    Parses each variant's aggregated metrics and organizes them by
    metric category and name.

    Args:
        variants: Dictionary mapping variant names to their result data.

    Returns:
        Dictionary mapping metric categories (``"retrieval"``,
        ``"generation"``) to metric names to lists of
        ``(variant_name, value)`` tuples.
    """
    metrics: dict[str, dict[str, list[tuple]]] = {}

    for variant_name, result in variants.items():
        agg = result.get("aggregated_metrics", {})

        for category in ("retrieval", "generation"):
            cat_metrics = agg.get(category, {})
            if category not in metrics:
                metrics[category] = {}

            for metric_name, value in cat_metrics.items():
                if metric_name not in metrics[category]:
                    metrics[category][metric_name] = []
                metrics[category][metric_name].append((variant_name, value))

    return metrics


def plot_metrics_comparison(
    metrics: dict[str, dict[str, list[tuple]]],
    output_dir: str,
    exp_name: str = "experiment",
) -> list[str]:
    """Generate comparison bar charts for each metric across variants.

    Creates one chart per metric category, with grouped bars showing
    each variant's score.

    Args:
        metrics: Metrics dictionary from ``extract_metrics()``.
        output_dir: Directory to save chart images.
        exp_name: Experiment name for chart titles.
        save_format: Image format for saving charts.

    Returns:
        List of saved chart file paths.

    Raises:
        ImportError: If matplotlib is not available.
    """
    if not HAS_MATPLOTLIB:
        logger.error("matplotlib is required for visualization. Install with: pixi add matplotlib")
        raise ImportError("matplotlib is not available")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for category, cat_metrics in metrics.items():
        if not cat_metrics:
            continue

        metric_names = list(cat_metrics.keys())
        variant_names = sorted(
            set(v for vals in cat_metrics.values() for v, _ in vals),
            key=lambda x: x,
        )

        n_metrics = len(metric_names)
        n_variants = len(variant_names)

        fig, axes = plt.subplots(1, n_metrics, figsize=(6 * n_metrics, 5))
        if n_metrics == 1:
            axes = [axes]

        fig.suptitle(
            f"{exp_name} - {category.title()} Metrics Comparison",
            fontsize=14,
            fontweight="bold",
        )

        for ax, metric_name in zip(axes, metric_names, strict=False):
            values_dict = dict(cat_metrics[metric_name])
            values = [values_dict.get(v, 0) for v in variant_names]

            bars = ax.bar(range(n_variants), values, color=plt.cm.Set2(range(n_variants)))

            ax.set_title(metric_name, fontsize=11)
            ax.set_xticks(range(n_variants))
            ax.set_xticklabels(variant_names, rotation=45, ha="right", fontsize=8)
            ax.set_ylim(0, max(values) * 1.15 if values else 1.0)

            for bar, val in zip(bars, values, strict=False):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.01,
                    f"{val:.3f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

        plt.tight_layout()

        chart_path = output_path / f"{exp_name}_{category}_comparison.png"
        fig.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        saved_files.append(str(chart_path))
        logger.info(f"Saved chart: {chart_path}")

    return saved_files


def plot_metric_trend(
    metrics: dict[str, dict[str, list[tuple]]],
    output_dir: str,
    exp_name: str = "experiment",
    variant_order: list[str] | None = None,
) -> list[str]:
    """Generate trend line charts for metrics across variants.

    Useful for showing how a metric changes as a hyperparameter varies
    (e.g., chunk_size from 256 to 1024).

    Args:
        metrics: Metrics dictionary from ``extract_metrics()``.
        output_dir: Directory to save chart images.
        exp_name: Experiment name for chart titles.
        variant_order: Optional ordered list of variant names for the
            x-axis. If None, uses sorted variant names.

    Returns:
        List of saved chart file paths.

    Raises:
        ImportError: If matplotlib is not available.
    """
    if not HAS_MATPLOTLIB:
        raise ImportError("matplotlib is not available")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for category, cat_metrics in metrics.items():
        if not cat_metrics:
            continue

        fig, ax = plt.subplots(figsize=(10, 6))

        for metric_name, values_list in cat_metrics.items():
            if variant_order:
                values_dict = dict(values_list)
                x_labels = variant_order
                y_values = [values_dict.get(v) for v in variant_order]
            else:
                sorted_vals = sorted(values_list, key=lambda x: x[0])
                x_labels = [v for v, _ in sorted_vals]
                y_values = [val for _, val in sorted_vals]

            ax.plot(
                range(len(x_labels)),
                y_values,
                marker="o",
                label=metric_name,
                linewidth=2,
            )

        ax.set_title(f"{exp_name} - {category.title()} Metrics Trend", fontsize=14, fontweight="bold")
        ax.set_xticks(range(len(x_labels)))
        ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=9)
        ax.set_ylabel("Score")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        chart_path = output_path / f"{exp_name}_{category}_trend.png"
        fig.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        saved_files.append(str(chart_path))
        logger.info(f"Saved trend chart: {chart_path}")

    return saved_files


def visualize_experiment(
    exp_dir: str,
    output_dir: str | None = None,
) -> list[str]:
    """Generate all visualizations for an experiment.

    Convenience function that loads experiment results and generates
    both comparison bar charts and trend line charts.

    Args:
        exp_dir: Path to the experiment directory.
        output_dir: Directory to save charts. Defaults to a ``charts/``
            subdirectory inside the experiment directory.

    Returns:
        List of all saved chart file paths.
    """
    exp_data = load_experiment_results(exp_dir)
    metrics = extract_metrics(exp_data["variants"])

    if output_dir is None:
        output_dir = str(Path(exp_dir) / "charts")

    saved = []
    saved.extend(plot_metrics_comparison(metrics, output_dir, exp_data["exp_name"]))
    saved.extend(plot_metric_trend(metrics, output_dir, exp_data["exp_name"]))

    logger.success(f"Generated {len(saved)} charts for experiment: {exp_data['exp_name']}")
    return saved


if __name__ == "__main__":
    import sys

    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    if len(sys.argv) < 2:
        print("Usage: python -m eval.visualize <exp_dir> [output_dir]")
        sys.exit(1)

    exp_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    visualize_experiment(exp_dir, output_dir)
