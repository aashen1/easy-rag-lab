from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from eval.pipeline_profiler import PipelineProfiler

try:
    import matplotlib
    import matplotlib.pyplot as plt

    matplotlib.use("Agg")

    matplotlib.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning(
        "matplotlib not available, chart generation disabled. "
        "Install with: pip install matplotlib"
    )


class ProfilerVisualizer:
    def __init__(self, profiler: PipelineProfiler | None = None):
        self.profiler = profiler

    def load_from_json(self, json_path: Path) -> dict[str, Any]:
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)

    def generate_all_charts(
        self,
        output_dir: Path,
        profile_data: dict[str, Any] | None = None,
    ) -> list[Path]:
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("matplotlib not available, skipping chart generation")
            return []

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if profile_data is None and self.profiler is not None:
            profile_data = self.profiler.to_dict()

        if profile_data is None:
            logger.error("No profile data available")
            return []

        generated_files = []

        try:
            chart_path = self.generate_stage_duration_pie(output_dir, profile_data)
            if chart_path:
                generated_files.append(chart_path)
        except Exception as e:
            logger.warning(f"Failed to generate pie chart: {e}")

        try:
            chart_path = self.generate_stage_duration_bar(output_dir, profile_data)
            if chart_path:
                generated_files.append(chart_path)
        except Exception as e:
            logger.warning(f"Failed to generate bar chart: {e}")

        try:
            chart_path = self.generate_token_distribution(output_dir, profile_data)
            if chart_path:
                generated_files.append(chart_path)
        except Exception as e:
            logger.warning(f"Failed to generate token chart: {e}")

        logger.success(f"Generated {len(generated_files)} charts in {output_dir}")
        return generated_files

    def generate_stage_duration_pie(
        self,
        output_dir: Path,
        profile_data: dict[str, Any],
    ) -> Path | None:
        if not MATPLOTLIB_AVAILABLE:
            return None

        stages = profile_data.get("stages", {})
        if not stages:
            return None

        labels = []
        sizes = []
        for stage_id, stage_data in sorted(stages.items()):
            stage_name = stage_data.get("stage_name", stage_id)
            duration = stage_data.get("duration_seconds", 0)
            if duration > 0:
                labels.append(f"{stage_id}\n{stage_name}")
                sizes.append(duration)

        if not sizes:
            return None

        fig, ax = plt.subplots(figsize=(10, 8))
        colors = plt.cm.Set3(range(len(labels)))

        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90,
            colors=colors,
        )

        for text in texts:
            text.set_fontsize(9)
        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_fontweight("bold")

        ax.set_title(
            f"Pipeline Stage Duration Distribution\n{profile_data.get('experiment_name', 'Experiment')}",
            fontsize=14,
            fontweight="bold",
        )

        total_duration = sum(sizes)
        ax.text(
            0.5,
            -0.1,
            f"Total Duration: {total_duration:.2f}s",
            ha="center",
            transform=ax.transAxes,
            fontsize=10,
        )

        plt.tight_layout()

        output_path = output_dir / "stage_duration_pie.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.debug(f"Pie chart saved to: {output_path}")
        return output_path

    def generate_stage_duration_bar(
        self,
        output_dir: Path,
        profile_data: dict[str, Any],
    ) -> Path | None:
        if not MATPLOTLIB_AVAILABLE:
            return None

        stages = profile_data.get("stages", {})
        if not stages:
            return None

        stage_ids = []
        stage_names = []
        durations = []
        for stage_id, stage_data in sorted(stages.items()):
            stage_name = stage_data.get("stage_name", stage_id)
            duration = stage_data.get("duration_seconds", 0)
            stage_ids.append(stage_id)
            stage_names.append(stage_name)
            durations.append(duration)

        if not durations:
            return None

        fig, ax = plt.subplots(figsize=(12, 6))

        x = range(len(stage_ids))
        bars = ax.bar(x, durations, color=plt.cm.viridis(0.5), edgecolor="black")

        ax.set_xlabel("Pipeline Stage", fontsize=12)
        ax.set_ylabel("Duration (seconds)", fontsize=12)
        ax.set_title(
            f"Pipeline Stage Duration Breakdown\n{profile_data.get('experiment_name', 'Experiment')}",
            fontsize=14,
            fontweight="bold",
        )

        ax.set_xticks(x)
        ax.set_xticklabels(
            [
                f"{sid}\n{sname}"
                for sid, sname in zip(stage_ids, stage_names, strict=False)
            ],
            fontsize=9,
        )

        for bar, duration in zip(bars, durations, strict=False):
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{duration:.2f}s",
                ha="center",
                va="bottom",
                fontsize=9,
            )

        ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()

        output_path = output_dir / "stage_duration_bar.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.debug(f"Bar chart saved to: {output_path}")
        return output_path

    def generate_token_distribution(
        self,
        output_dir: Path,
        profile_data: dict[str, Any],
    ) -> Path | None:
        if not MATPLOTLIB_AVAILABLE:
            return None

        token_summary = profile_data.get("token_summary", {})
        by_stage = token_summary.get("by_stage", {})

        if not by_stage:
            return None

        stage_ids = []
        input_tokens = []
        output_tokens = []

        for stage_id, data in sorted(by_stage.items()):
            stage_ids.append(stage_id)
            input_tokens.append(data.get("input_tokens", 0))
            output_tokens.append(data.get("output_tokens", 0))

        if not stage_ids or (
            all(t == 0 for t in input_tokens) and all(t == 0 for t in output_tokens)
        ):
            return None

        fig, ax = plt.subplots(figsize=(10, 6))

        x = range(len(stage_ids))
        width = 0.35

        ax.bar(
            [i - width / 2 for i in x],
            input_tokens,
            width,
            label="Input Tokens",
            color=plt.cm.Blues(0.6),
        )
        ax.bar(
            [i + width / 2 for i in x],
            output_tokens,
            width,
            label="Output Tokens",
            color=plt.cm.Oranges(0.6),
        )

        ax.set_xlabel("Pipeline Stage", fontsize=12)
        ax.set_ylabel("Token Count", fontsize=12)
        ax.set_title(
            f"Token Distribution by Stage\n{profile_data.get('experiment_name', 'Experiment')}",
            fontsize=14,
            fontweight="bold",
        )

        ax.set_xticks(x)
        ax.set_xticklabels(stage_ids, fontsize=10)
        ax.legend()

        ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()

        output_path = output_dir / "token_distribution.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.debug(f"Token chart saved to: {output_path}")
        return output_path


def generate_profiler_charts(
    profiler: PipelineProfiler,
    output_dir: Path,
) -> list[Path]:
    visualizer = ProfilerVisualizer(profiler)
    return visualizer.generate_all_charts(output_dir)
