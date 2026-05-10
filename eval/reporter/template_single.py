from typing import Any

from eval.reporter.formatters import (
    dict_to_yaml_lines,
    generate_tech_summary,
    get_generation_metric,
    get_generation_metric_description,
    get_metric_description,
)
from eval.reporter.models import ReportExperimentResult
from eval.reporter.utils import generate_recommendations


class TemplateSingleReporter:
    """Generates single-variant template reports."""

    def generate(self, result: ReportExperimentResult) -> str:
        sections = [
            self._generate_header(result),
            self._generate_overview_section(result),
            self._generate_data_section(result),
            self._generate_config_section(result),
            self._generate_test_set_section(result),
            self._generate_results_section(result),
            self._generate_comparison_table(result),
            self._generate_conclusion_section(result),
            self._generate_assets_section(result),
        ]
        return "\n\n".join(s for s in sections if s)

    def _generate_header(self, result: ReportExperimentResult) -> str:
        title = "# RAG Experiment Report"
        if result.meal_name:
            title += f" - {result.meal_name}"
        return title

    def _generate_overview_section(self, result: ReportExperimentResult) -> str:
        lines = [
            "## 1. Experiment Overview",
            "",
            f"- **Experiment Time**: {result.timestamp}",
            f"- **Total Test Cases**: {result.total_test_cases}",
            f"- **Total Duration**: {result.total_time_seconds:.2f}s",
            f"- **Average Time per Case**: {result.avg_time_per_case:.2f}s",
        ]
        if result.meal_data_id:
            lines.append(f"- **Data ID**: `{result.meal_data_id[:12]}...`")
        return "\n".join(lines)

    def _generate_data_section(self, result: ReportExperimentResult) -> str:
        lines = ["## 2. Data Source", ""]

        if result.pdf_files:
            lines.append(f"### PDF Files ({len(result.pdf_files)} files)")
            lines.append("")
            lines.append("| File Path | Size |")
            lines.append("|-----------|------|")
            for pdf in result.pdf_files[:20]:
                path = pdf.get("path", "unknown")
                size = pdf.get("size_bytes", 0)
                size_kb = size / 1024
                lines.append(f"| {path} | {size_kb:.1f} KB |")
            if len(result.pdf_files) > 20:
                lines.append(f"| ... and {len(result.pdf_files) - 20} more files | |")
            lines.append("")

        if result.stats:
            lines.append("### Statistics")
            lines.append("")
            for key, value in result.stats.items():
                formatted_key = key.replace("_", " ").title()
                lines.append(f"- **{formatted_key}**: {value}")
            lines.append("")

        return "\n".join(lines)

    def _generate_config_section(self, result: ReportExperimentResult) -> str:
        lines = ["## 3. Technical Configuration", ""]

        if result.config_snapshot:
            merged = result.config_snapshot.get("merged", result.config_snapshot)
            if "retrieval" in merged or "chunker" in merged:
                lines.append("### Technology Summary")
                lines.append("")
                lines.extend(generate_tech_summary(merged))
                lines.append("")

            lines.append("### Configuration Snapshot")
            lines.append("")
            lines.append("```yaml")
            lines.extend(dict_to_yaml_lines(result.config_snapshot))
            lines.append("```")
            lines.append("")

        if result.config_hashes:
            lines.append("### Configuration Hashes")
            lines.append("")
            for key, hash_val in result.config_hashes.items():
                lines.append(f"- **{key}**: `{hash_val}`")
            lines.append("")

        return "\n".join(lines)

    def _generate_test_set_section(self, result: ReportExperimentResult) -> str:
        lines = ["## 4. Test Set Information", ""]

        categories: dict[str, int] = {}
        for r in result.results:
            cat = r.category or "uncategorized"
            categories[cat] = categories.get(cat, 0) + 1

        if categories:
            lines.append("### Question Categories")
            lines.append("")
            lines.append("| Category | Count | Percentage |")
            lines.append("|----------|-------|------------|")
            for cat, count in sorted(categories.items()):
                pct = count / result.total_test_cases * 100
                lines.append(f"| {cat} | {count} | {pct:.1f}% |")
            lines.append("")

        lines.append("### Sample Questions")
        lines.append("")
        sample_size = min(5, len(result.results))
        for i, r in enumerate(result.results[:sample_size]):
            lines.append(f"{i + 1}. **{r.question}**")
            if r.category:
                lines.append(f"   - Category: {r.category}")
        lines.append("")

        return "\n".join(lines)

    def _generate_results_section(self, result: ReportExperimentResult) -> str:
        lines = ["## 5. Evaluation Results", ""]

        lines.append("### Overall Retrieval Metrics")
        lines.append("")
        lines.append("| Metric | Value | Description |")
        lines.append("|--------|-------|-------------|")
        for metric, value in result.retrieval_metrics.items():
            metric_name = metric.replace("avg_", "").replace("_", " ").upper()
            description = get_metric_description(metric)
            lines.append(f"| {metric_name} | {value:.4f} | {description} |")
        lines.append("")

        if result.generation_metrics:
            lines.append("### Generation Quality Metrics")
            lines.append("")
            lines.append("| Metric | Value | Description |")
            lines.append("|--------|-------|-------------|")
            for metric, value in result.generation_metrics.items():
                metric_name = metric.replace("avg_", "").replace("_", " ").title()
                description = get_generation_metric_description(metric)
                lines.append(f"| {metric_name} | {value:.4f} | {description} |")
            lines.append("")

        categories: dict[str, dict[str, Any]] = {}
        for r in result.results:
            if r.retrieval:
                cat = r.category or "uncategorized"
                if cat not in categories:
                    categories[cat] = {
                        "hit_rate": [],
                        "mrr": [],
                        "ndcg": [],
                        "count": 0,
                    }
                categories[cat]["hit_rate"].append(r.retrieval.get("hit_rate", 0))
                categories[cat]["mrr"].append(r.retrieval.get("mrr", 0))
                categories[cat]["ndcg"].append(r.retrieval.get("ndcg", 0))
                categories[cat]["count"] += 1

        if categories:
            lines.append("### Results by Question Category")
            lines.append("")
            lines.append("| Category | Count | Avg Hit Rate | Avg MRR | Avg NDCG |")
            lines.append("|----------|-------|--------------|---------|----------|")
            for cat, metrics in sorted(categories.items()):
                avg_hr = (
                    sum(metrics["hit_rate"]) / len(metrics["hit_rate"])
                    if metrics["hit_rate"]
                    else 0
                )
                avg_mrr = (
                    sum(metrics["mrr"]) / len(metrics["mrr"]) if metrics["mrr"] else 0
                )
                avg_ndcg = (
                    sum(metrics["ndcg"]) / len(metrics["ndcg"])
                    if metrics["ndcg"]
                    else 0
                )
                lines.append(
                    f"| {cat} | {metrics['count']} | {avg_hr:.4f} | {avg_mrr:.4f} | {avg_ndcg:.4f} |"
                )
            lines.append("")

        error_count = sum(1 for r in result.results if r.error)
        if error_count > 0:
            lines.append(f"### Errors ({error_count} cases)")
            lines.append("")
            for r in result.results:
                if r.error:
                    lines.append(f"- **{r.id}**: {r.error}")
            lines.append("")

        return "\n".join(lines)

    def _generate_comparison_table(self, result: ReportExperimentResult) -> str:
        lines = ["## 6. Detailed Results Comparison", ""]

        has_generation = any(r.generation for r in result.results)

        if has_generation:
            lines.append(
                "| ID | Question | Hit Rate | MRR | NDCG | Faithfulness | Relevancy | Time (s) |"
            )
            lines.append(
                "|----|----------|----------|-----|------|--------------|-----------|----------|"
            )
        else:
            lines.append("| ID | Question | Hit Rate | MRR | NDCG | Time (s) |")
            lines.append("|----|----------|----------|-----|------|----------|")

        for r in result.results[:50]:
            q_short = r.question[:30] + "..." if len(r.question) > 30 else r.question
            if r.retrieval:
                hr = r.retrieval.get("hit_rate", 0)
                mrr = r.retrieval.get("mrr", 0)
                ndcg = r.retrieval.get("ndcg", 0)

                if has_generation and r.generation:
                    faithfulness = r.generation.get("builtin_faithfulness")
                    if faithfulness is None:
                        faithfulness = r.generation.get("ragas_faithfulness")
                    if faithfulness is None:
                        faithfulness = r.generation.get("faithfulness")
                    relevancy = r.generation.get("builtin_answer_relevancy")
                    if relevancy is None:
                        relevancy = r.generation.get("ragas_answer_relevancy")
                    if relevancy is None:
                        relevancy = r.generation.get("answer_relevancy")
                    fa_str = (
                        f"{faithfulness:.2f}" if faithfulness is not None else "N/A"
                    )
                    ar_str = f"{relevancy:.2f}" if relevancy is not None else "N/A"
                    lines.append(
                        f"| {r.id} | {q_short} | {hr:.4f} | {mrr:.4f} | {ndcg:.4f} | {fa_str} | {ar_str} | {r.time_seconds:.2f} |"
                    )
                else:
                    lines.append(
                        f"| {r.id} | {q_short} | {hr:.4f} | {mrr:.4f} | {ndcg:.4f} | {r.time_seconds:.2f} |"
                    )
            else:
                if has_generation:
                    lines.append(
                        f"| {r.id} | {q_short} | N/A | N/A | N/A | N/A | N/A | {r.time_seconds:.2f} |"
                    )
                else:
                    lines.append(
                        f"| {r.id} | {q_short} | N/A | N/A | N/A | {r.time_seconds:.2f} |"
                    )

        if len(result.results) > 50:
            lines.append(
                f"| ... | ... and {len(result.results) - 50} more results | ... | ... | ... | ... |"
            )

        lines.append("")
        return "\n".join(lines)

    def _generate_conclusion_section(self, result: ReportExperimentResult) -> str:
        lines = ["## 7. Conclusions and Recommendations", ""]

        avg_hr = result.retrieval_metrics.get("avg_hit_rate", 0)
        avg_mrr = result.retrieval_metrics.get("avg_mrr", 0)
        avg_ndcg = result.retrieval_metrics.get("avg_ndcg", 0)

        lines.append("### Retrieval Performance Summary")
        lines.append("")

        if avg_hr >= 0.8:
            hr_assessment = "Excellent - Most relevant documents are being retrieved."
        elif avg_hr >= 0.6:
            hr_assessment = "Good - Majority of relevant documents are being retrieved."
        elif avg_hr >= 0.4:
            hr_assessment = "Moderate - Some relevant documents are being retrieved, room for improvement."
        else:
            hr_assessment = (
                "Needs Improvement - Many relevant documents are being missed."
            )

        if avg_mrr >= 0.7:
            mrr_assessment = "Excellent - Relevant documents appear early in results."
        elif avg_mrr >= 0.5:
            mrr_assessment = "Good - Relevant documents appear reasonably early."
        else:
            mrr_assessment = (
                "Needs Improvement - Relevant documents may be buried in results."
            )

        lines.append(f"- **Hit Rate ({avg_hr:.4f})**: {hr_assessment}")
        lines.append(f"- **MRR ({avg_mrr:.4f})**: {mrr_assessment}")
        lines.append(f"- **NDCG ({avg_ndcg:.4f})**: Ranking quality assessment.")
        lines.append("")

        if result.generation_metrics:
            avg_faithfulness = (
                get_generation_metric(result.generation_metrics, "faithfulness") or 0
            )
            avg_relevancy = (
                get_generation_metric(result.generation_metrics, "answer_relevancy")
                or 0
            )

            lines.append("### Generation Quality Summary")
            lines.append("")

            if avg_faithfulness >= 0.8:
                fa_assessment = (
                    "Excellent - Answers are well-grounded in retrieved contexts."
                )
            elif avg_faithfulness >= 0.6:
                fa_assessment = "Good - Most answer content is supported by contexts."
            elif avg_faithfulness >= 0.4:
                fa_assessment = (
                    "Moderate - Some hallucinations detected, review needed."
                )
            else:
                fa_assessment = "Needs Improvement - Significant hallucinations, answers not grounded."

            if avg_relevancy >= 0.8:
                ar_assessment = "Excellent - Answers directly address the questions."
            elif avg_relevancy >= 0.6:
                ar_assessment = "Good - Answers are mostly relevant to questions."
            elif avg_relevancy >= 0.4:
                ar_assessment = (
                    "Moderate - Some answers may be off-topic or incomplete."
                )
            else:
                ar_assessment = (
                    "Needs Improvement - Answers often irrelevant to questions."
                )

            lines.append(
                f"- **Faithfulness ({avg_faithfulness:.4f})**: {fa_assessment}"
            )
            lines.append(
                f"- **Answer Relevancy ({avg_relevancy:.4f})**: {ar_assessment}"
            )
            lines.append("")

        lines.append("### Recommendations")
        lines.append("")

        avg_faithfulness = None
        avg_relevancy = None
        if result.generation_metrics:
            avg_faithfulness = (
                get_generation_metric(result.generation_metrics, "faithfulness") or 0
            )
            avg_relevancy = (
                get_generation_metric(result.generation_metrics, "answer_relevancy")
                or 0
            )

        recommendations = generate_recommendations(
            hr=avg_hr,
            mrr=avg_mrr,
            ndcg=avg_ndcg,
            faithfulness=avg_faithfulness,
            relevancy=avg_relevancy,
            has_generation_metrics=result.generation_metrics is not None,
        )

        lines.extend(recommendations)
        lines.append("")

        return "\n".join(lines)

    def _generate_assets_section(self, result: ReportExperimentResult) -> str:
        lines = ["## 8. Experiment Assets", ""]
        lines.append("The following artifacts are available for this experiment:")
        lines.append("")
        lines.append("- Evaluation results: `baseline_report.json`")
        lines.append("- Experiment report: `experiment_report.md`")
        if result.meal_data_id:
            lines.append(
                f"- Data artifacts: `data/artifacts/{result.meal_data_id[:12]}/`"
            )
        lines.append("")

        return "\n".join(lines)
