from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class TestCaseResult:
    id: str
    question: str
    answer: Optional[str]
    retrieval: Optional[Dict[str, float]] = None
    sources: Optional[List[str]] = None
    error: Optional[str] = None
    time_seconds: float = 0.0
    category: Optional[str] = None


@dataclass
class VariantResult:
    variant_name: str
    variant_description: Optional[str] = None
    retrieval_metrics: Optional[Dict[str, float]] = None
    config_snapshot: Optional[Dict[str, Any]] = None
    total_questions: int = 0
    total_time_seconds: float = 0.0
    error: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VariantResult":
        return cls(
            variant_name=data.get("variant_name", "unnamed"),
            variant_description=data.get("variant_description"),
            retrieval_metrics=data.get("retrieval_metrics"),
            config_snapshot=data.get("config_snapshot"),
            total_questions=data.get("total_questions", 0),
            total_time_seconds=data.get("total_time_seconds", 0.0),
            error=data.get("error"),
        )


@dataclass
class ExperimentResult:
    timestamp: str
    total_test_cases: int
    total_time_seconds: float
    avg_time_per_case: float
    retrieval_metrics: Dict[str, float]
    results: List[TestCaseResult]
    meal_data_id: Optional[str] = None
    meal_name: Optional[str] = None
    config_snapshot: Optional[Dict[str, Any]] = None
    config_hashes: Optional[Dict[str, str]] = None
    pdf_files: Optional[List[Dict[str, Any]]] = None
    stats: Optional[Dict[str, Any]] = None
    variant_results: Optional[List[VariantResult]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentResult":
        results = []
        for r in data.get("results", []):
            results.append(TestCaseResult(
                id=r.get("id", ""),
                question=r.get("question", ""),
                answer=r.get("answer"),
                retrieval=r.get("retrieval"),
                sources=r.get("sources"),
                error=r.get("error"),
                time_seconds=r.get("time_seconds", 0.0),
                category=r.get("category"),
            ))

        variant_results = None
        if "variant_results" in data:
            variant_results = [
                VariantResult.from_dict(vr) for vr in data.get("variant_results", [])
            ]

        return cls(
            timestamp=data.get("timestamp", ""),
            total_test_cases=data.get("total_test_cases", 0),
            total_time_seconds=data.get("total_time_seconds", 0.0),
            avg_time_per_case=data.get("avg_time_per_case", 0.0),
            retrieval_metrics=data.get("retrieval_metrics", {}),
            results=results,
            meal_data_id=data.get("meal_data_id"),
            meal_name=data.get("meal_name"),
            config_snapshot=data.get("config_snapshot"),
            config_hashes=data.get("config_hashes"),
            pdf_files=data.get("pdf_files"),
            stats=data.get("stats"),
            variant_results=variant_results,
        )


LLM_REPORT_PROMPT_TEMPLATE = """You are an expert RAG system analyst. Please write a comprehensive experiment report based on the following data.

## Experiment Overview
- Experiment Time: {timestamp}
- Data ID: {data_id}
- Total Test Cases: {total_test_cases}

## Data Source
{data_section}

## Technical Configuration
{config_section}

## Evaluation Results
{results_section}

## Requirements
Please write a professional experiment report in Chinese (Simplified) with the following sections:

### 1. 实验概述
- Describe the purpose and hypothesis of this experiment
- Explain the significance of the evaluation

### 2. 数据来源分析
- Analyze the data characteristics
- Discuss potential impact of data on results

### 3. 技术选型分析
- Evaluate the chosen technologies and models
- Discuss potential strengths and limitations

### 4. 评测结果分析
- Interpret the retrieval metrics (Hit Rate, MRR, NDCG)
- Analyze performance patterns across different question types
- Identify potential bottlenecks or issues

### 5. 结论与建议
- Summarize key findings
- Provide actionable recommendations for improvement
- Suggest next steps for optimization

Please write the report in a professional, objective tone with specific data references.
"""


class ExperimentReporter:
    """Experiment report generator supporting template and LLM modes."""

    def __init__(
        self,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model_name: Optional[str] = None,
    ):
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model_name = llm_model_name
        self._llm_client = None

    def generate_markdown_report(
        self,
        exp_dir: Path,
        result: ExperimentResult,
        use_llm: bool = False,
        output_filename: str = "experiment_report.md",
    ) -> str:
        if use_llm:
            report = self._generate_llm_report(result)
        else:
            report = self._generate_template_report(result)

        output_path = Path(exp_dir) / output_filename
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.success(f"Report saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save report: {str(e)}")
            raise

        return report

    def generate_variant_comparison_report(
        self,
        exp_dir: Path,
        variant_results: List[Dict[str, Any]],
        meal_info: Optional[Dict[str, Any]] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
        output_filename: str = "experiment_report.md",
        use_llm: bool = False,
    ) -> str:
        """
        Generate a multi-variant comparison report.

        Args:
            exp_dir: Experiment directory path.
            variant_results: List of variant result dictionaries.
            meal_info: Meal information dictionary.
            config_snapshot: Configuration snapshot dictionary.
            output_filename: Output filename.
            use_llm: If True, use LLM to enhance the report.

        Returns:
            Generated report content.
        """
        if use_llm:
            report = self._generate_variant_comparison_llm(
                variant_results, meal_info, config_snapshot
            )
        else:
            report = self._generate_variant_comparison_template(
                variant_results, meal_info, config_snapshot
            )

        output_path = Path(exp_dir) / output_filename
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.success(f"Variant comparison report saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save report: {str(e)}")
            raise

        return report

    def _generate_variant_comparison_template(
        self,
        variant_results: List[Dict[str, Any]],
        meal_info: Optional[Dict[str, Any]] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        sections = [
            self._generate_variant_header(meal_info),
            self._generate_variant_overview_section(variant_results, meal_info),
            self._generate_variant_comparison_table_section(variant_results),
            self._generate_best_variant_section(variant_results),
            self._generate_variant_details_section(variant_results),
            self._generate_variant_config_section(variant_results, config_snapshot),
            self._generate_variant_recommendations_section(variant_results),
        ]
        return "\n\n".join(s for s in sections if s)

    def _generate_variant_comparison_llm(
        self,
        variant_results: List[Dict[str, Any]],
        meal_info: Optional[Dict[str, Any]] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        try:
            prompt = self._build_variant_comparison_llm_prompt(
                variant_results, meal_info, config_snapshot
            )
            llm_response = self._call_llm(prompt)
            return self._format_variant_comparison_llm_report(
                variant_results, llm_response, meal_info
            )
        except Exception as e:
            logger.warning(f"LLM report generation failed, falling back to template: {str(e)}")
            return self._generate_variant_comparison_template(
                variant_results, meal_info, config_snapshot
            )

    def _generate_variant_header(
        self, meal_info: Optional[Dict[str, Any]] = None
    ) -> str:
        title = "# RAG Multi-Variant Experiment Report"
        if meal_info and meal_info.get("name"):
            title += f" - {meal_info['name']}"
        return title

    def _generate_variant_overview_section(
        self,
        variant_results: List[Dict[str, Any]],
        meal_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        lines = ["## 1. Experiment Overview", ""]

        total_variants = len(variant_results)
        successful_variants = sum(
            1 for v in variant_results if "retrieval_metrics" in v
        )
        failed_variants = total_variants - successful_variants

        lines.append(f"- **Total Variants**: {total_variants}")
        lines.append(f"- **Successful Variants**: {successful_variants}")
        lines.append(f"- **Failed Variants**: {failed_variants}")

        if meal_info:
            if meal_info.get("data_id"):
                lines.append(f"- **Data ID**: `{meal_info['data_id'][:12]}...`")
            if meal_info.get("name"):
                lines.append(f"- **Meal Name**: {meal_info['name']}")

        lines.append(f"- **Timestamp**: {datetime.now().isoformat()}")
        lines.append("")
        return "\n".join(lines)

    def _generate_variant_comparison_table_section(
        self, variant_results: List[Dict[str, Any]]
    ) -> str:
        lines = ["## 2. Variant Comparison Table", ""]
        lines.append(
            "| Variant | Description | Hit Rate | MRR | NDCG | Questions | Time (s) |"
        )
        lines.append(
            "|---------|-------------|----------|-----|------|-----------|----------|"
        )

        best_variant = self._find_best_variant(variant_results)

        for vr in variant_results:
            name = vr.get("variant_name", "unnamed")
            desc = vr.get("variant_description", "")
            if len(desc) > 30:
                desc = desc[:27] + "..."

            if "retrieval_metrics" in vr:
                metrics = vr["retrieval_metrics"]
                hr = metrics.get("avg_hit_rate", 0)
                mrr = metrics.get("avg_mrr", 0)
                ndcg = metrics.get("avg_ndcg", 0)
                q_count = vr.get("total_questions", 0)
                time_s = vr.get("total_time_seconds", 0)

                marker = " ⭐" if vr == best_variant else ""
                lines.append(
                    f"| {name}{marker} | {desc} | {hr:.4f} | {mrr:.4f} | {ndcg:.4f} | {q_count} | {time_s:.2f} |"
                )
            else:
                error = vr.get("error", "Unknown error")
                if len(error) > 30:
                    error = error[:27] + "..."
                lines.append(f"| {name} | {desc} | ERROR | ERROR | ERROR | - | - |")

        lines.append("")
        lines.append("_⭐ = Best performing variant_")
        lines.append("")
        return "\n".join(lines)

    def _find_best_variant(
        self, variant_results: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        best = None
        best_hr = -1

        for vr in variant_results:
            if "retrieval_metrics" in vr:
                hr = vr["retrieval_metrics"].get("avg_hit_rate", 0)
                if hr > best_hr:
                    best_hr = hr
                    best = vr

        return best

    def _generate_best_variant_section(
        self, variant_results: List[Dict[str, Any]]
    ) -> str:
        best = self._find_best_variant(variant_results)

        if not best:
            return "## 3. Best Variant\n\nNo successful variants to compare.\n"

        lines = ["## 3. Best Performing Variant", ""]
        name = best.get("variant_name", "unnamed")
        desc = best.get("variant_description", "No description")
        metrics = best.get("retrieval_metrics", {})

        lines.append(f"**Variant**: {name}")
        lines.append(f"**Description**: {desc}")
        lines.append("")
        lines.append("**Performance Metrics**:")
        lines.append(f"- Hit Rate: {metrics.get('avg_hit_rate', 0):.4f}")
        lines.append(f"- MRR: {metrics.get('avg_mrr', 0):.4f}")
        lines.append(f"- NDCG: {metrics.get('avg_ndcg', 0):.4f}")
        lines.append(f"- Total Questions: {best.get('total_questions', 0)}")
        lines.append(f"- Total Time: {best.get('total_time_seconds', 0):.2f}s")
        lines.append("")

        config_snapshot = best.get("config_snapshot", {})
        if config_snapshot and "merged" in config_snapshot:
            lines.append("**Configuration**:")
            lines.append("```yaml")
            merged = config_snapshot["merged"]
            for section, config in merged.items():
                lines.append(f"{section}:")
                if isinstance(config, dict):
                    for k, v in config.items():
                        lines.append(f"  {k}: {v}")
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _generate_variant_details_section(
        self, variant_results: List[Dict[str, Any]]
    ) -> str:
        lines = ["## 4. Variant Details", ""]

        for i, vr in enumerate(variant_results, 1):
            name = vr.get("variant_name", "unnamed")
            desc = vr.get("variant_description", "No description")

            lines.append(f"### 4.{i} {name}")
            lines.append("")
            lines.append(f"**Description**: {desc}")
            lines.append("")

            if "retrieval_metrics" in vr:
                metrics = vr["retrieval_metrics"]
                lines.append("**Retrieval Metrics**:")
                lines.append(f"- Hit Rate: {metrics.get('avg_hit_rate', 0):.4f}")
                lines.append(f"- MRR: {metrics.get('avg_mrr', 0):.4f}")
                lines.append(f"- NDCG: {metrics.get('avg_ndcg', 0):.4f}")
                lines.append("")

                config_snapshot = vr.get("config_snapshot", {})
                if config_snapshot and "merged" in config_snapshot:
                    lines.append("**Configuration**:")
                    lines.append("```yaml")
                    merged = config_snapshot["merged"]
                    for section, config in merged.items():
                        lines.append(f"{section}:")
                        if isinstance(config, dict):
                            for k, v in config.items():
                                lines.append(f"  {k}: {v}")
                    lines.append("```")
                    lines.append("")
            else:
                error = vr.get("error", "Unknown error")
                lines.append(f"**Error**: {error}")
                lines.append("")

        return "\n".join(lines)

    def _generate_variant_config_section(
        self,
        variant_results: List[Dict[str, Any]],
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        lines = ["## 5. Common Configuration", ""]

        if config_snapshot:
            lines.append("### Experiment Configuration")
            lines.append("")
            lines.append("```yaml")
            for section, config in config_snapshot.items():
                if section == "variant":
                    continue
                lines.append(f"{section}:")
                if isinstance(config, dict):
                    for k, v in config.items():
                        if isinstance(v, dict):
                            lines.append(f"  {k}:")
                            for k2, v2 in v.items():
                                lines.append(f"    {k2}: {v2}")
                        else:
                            lines.append(f"  {k}: {v}")
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _generate_variant_recommendations_section(
        self, variant_results: List[Dict[str, Any]]
    ) -> str:
        lines = ["## 6. Recommendations", ""]

        best = self._find_best_variant(variant_results)
        if not best:
            lines.append("Unable to generate recommendations due to lack of successful variants.")
            lines.append("")
            return "\n".join(lines)

        best_metrics = best.get("retrieval_metrics", {})
        best_hr = best_metrics.get("avg_hit_rate", 0)
        best_mrr = best_metrics.get("avg_mrr", 0)
        best_ndcg = best_metrics.get("avg_ndcg", 0)

        lines.append("### Performance Analysis")
        lines.append("")

        if best_hr >= 0.8:
            hr_assessment = "Excellent retrieval performance."
        elif best_hr >= 0.6:
            hr_assessment = "Good retrieval performance with room for improvement."
        elif best_hr >= 0.4:
            hr_assessment = "Moderate retrieval performance, optimization recommended."
        else:
            hr_assessment = "Low retrieval performance, significant optimization needed."

        lines.append(f"- **Hit Rate ({best_hr:.4f})**: {hr_assessment}")

        if best_mrr >= 0.7:
            mrr_assessment = "Excellent ranking quality."
        elif best_mrr >= 0.5:
            mrr_assessment = "Good ranking quality."
        else:
            mrr_assessment = "Ranking quality needs improvement."

        lines.append(f"- **MRR ({best_mrr:.4f})**: {mrr_assessment}")
        lines.append(f"- **NDCG ({best_ndcg:.4f})**: Overall ranking quality metric.")
        lines.append("")

        lines.append("### Optimization Suggestions")
        lines.append("")

        recommendations = []

        if best_hr < 0.6:
            recommendations.append(
                "1. Consider increasing `top_k` to retrieve more candidate documents."
            )
            recommendations.append(
                "2. Evaluate embedding model quality for domain-specific content."
            )
            recommendations.append(
                "3. Consider hybrid retrieval (BM25 + vector search)."
            )

        if best_mrr < 0.5:
            recommendations.append(
                "4. Add a reranker to improve document ranking."
            )
            recommendations.append(
                "5. Review chunking strategy for better context preservation."
            )

        if best_ndcg < 0.5:
            recommendations.append(
                "6. Consider semantic chunking for better context boundaries."
            )

        if not recommendations:
            recommendations.append(
                "1. Current best variant shows satisfactory performance."
            )
            recommendations.append(
                "2. Consider fine-tuning embedding model for domain-specific improvements."
            )
            recommendations.append(
                "3. Explore advanced retrieval strategies for edge cases."
            )

        lines.extend(recommendations)
        lines.append("")

        lines.append("### Next Steps")
        lines.append("")
        lines.append("1. Deploy the best performing variant for production use.")
        lines.append("2. Continue experimenting with other optimization techniques.")
        lines.append("3. Monitor performance in real-world usage.")
        lines.append("")

        return "\n".join(lines)

    def _generate_template_report(self, result: ExperimentResult) -> str:
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

    def _generate_llm_report(self, result: ExperimentResult) -> str:
        try:
            prompt = self._build_llm_prompt(result)
            llm_response = self._call_llm(prompt)
            return self._format_llm_report(result, llm_response)
        except Exception as e:
            logger.warning(f"LLM report generation failed, falling back to template: {str(e)}")
            return self._generate_template_report(result)

    def _generate_header(self, result: ExperimentResult) -> str:
        title = f"# RAG Experiment Report"
        if result.meal_name:
            title += f" - {result.meal_name}"
        return title

    def _generate_overview_section(self, result: ExperimentResult) -> str:
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

    def _generate_data_section(self, result: ExperimentResult) -> str:
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

    def _generate_config_section(self, result: ExperimentResult) -> str:
        lines = ["## 3. Technical Configuration", ""]

        if result.config_snapshot:
            lines.append("### Configuration Snapshot")
            lines.append("")
            lines.append("```yaml")
            for section, config in result.config_snapshot.items():
                lines.append(f"{section}:")
                if isinstance(config, dict):
                    for k, v in config.items():
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"  {config}")
            lines.append("```")
            lines.append("")

        if result.config_hashes:
            lines.append("### Configuration Hashes")
            lines.append("")
            for key, hash_val in result.config_hashes.items():
                lines.append(f"- **{key}**: `{hash_val}`")
            lines.append("")

        return "\n".join(lines)

    def _generate_test_set_section(self, result: ExperimentResult) -> str:
        lines = ["## 4. Test Set Information", ""]

        categories = {}
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
            lines.append(f"{i+1}. **{r.question}**")
            if r.category:
                lines.append(f"   - Category: {r.category}")
        lines.append("")

        return "\n".join(lines)

    def _generate_results_section(self, result: ExperimentResult) -> str:
        lines = ["## 5. Evaluation Results", ""]

        lines.append("### Overall Retrieval Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for metric, value in result.retrieval_metrics.items():
            metric_name = metric.replace("avg_", "").replace("_", " ").upper()
            lines.append(f"| {metric_name} | {value:.4f} |")
        lines.append("")

        categories = {}
        for r in result.results:
            if r.retrieval:
                cat = r.category or "uncategorized"
                if cat not in categories:
                    categories[cat] = {"hit_rate": [], "mrr": [], "ndcg": [], "count": 0}
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
                avg_hr = sum(metrics["hit_rate"]) / len(metrics["hit_rate"]) if metrics["hit_rate"] else 0
                avg_mrr = sum(metrics["mrr"]) / len(metrics["mrr"]) if metrics["mrr"] else 0
                avg_ndcg = sum(metrics["ndcg"]) / len(metrics["ndcg"]) if metrics["ndcg"] else 0
                lines.append(f"| {cat} | {metrics['count']} | {avg_hr:.4f} | {avg_mrr:.4f} | {avg_ndcg:.4f} |")
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

    def _generate_comparison_table(self, result: ExperimentResult) -> str:
        lines = ["## 6. Detailed Results Comparison", ""]

        lines.append("| ID | Question | Hit Rate | MRR | NDCG | Time (s) |")
        lines.append("|----|----------|----------|-----|------|----------|")

        for r in result.results[:50]:
            q_short = r.question[:30] + "..." if len(r.question) > 30 else r.question
            if r.retrieval:
                hr = r.retrieval.get("hit_rate", 0)
                mrr = r.retrieval.get("mrr", 0)
                ndcg = r.retrieval.get("ndcg", 0)
                lines.append(f"| {r.id} | {q_short} | {hr:.4f} | {mrr:.4f} | {ndcg:.4f} | {r.time_seconds:.2f} |")
            else:
                lines.append(f"| {r.id} | {q_short} | N/A | N/A | N/A | {r.time_seconds:.2f} |")

        if len(result.results) > 50:
            lines.append(f"| ... | ... and {len(result.results) - 50} more results | ... | ... | ... | ... |")

        lines.append("")
        return "\n".join(lines)

    def _generate_conclusion_section(self, result: ExperimentResult) -> str:
        lines = ["## 7. Conclusions and Recommendations", ""]

        avg_hr = result.retrieval_metrics.get("avg_hit_rate", 0)
        avg_mrr = result.retrieval_metrics.get("avg_mrr", 0)
        avg_ndcg = result.retrieval_metrics.get("avg_ndcg", 0)

        lines.append("### Performance Summary")
        lines.append("")

        if avg_hr >= 0.8:
            hr_assessment = "Excellent - Most relevant documents are being retrieved."
        elif avg_hr >= 0.6:
            hr_assessment = "Good - Majority of relevant documents are being retrieved."
        elif avg_hr >= 0.4:
            hr_assessment = "Moderate - Some relevant documents are being retrieved, room for improvement."
        else:
            hr_assessment = "Needs Improvement - Many relevant documents are being missed."

        if avg_mrr >= 0.7:
            mrr_assessment = "Excellent - Relevant documents appear early in results."
        elif avg_mrr >= 0.5:
            mrr_assessment = "Good - Relevant documents appear reasonably early."
        else:
            mrr_assessment = "Needs Improvement - Relevant documents may be buried in results."

        lines.append(f"- **Hit Rate ({avg_hr:.4f})**: {hr_assessment}")
        lines.append(f"- **MRR ({avg_mrr:.4f})**: {mrr_assessment}")
        lines.append(f"- **NDCG ({avg_ndcg:.4f})**: Ranking quality assessment.")
        lines.append("")

        lines.append("### Recommendations")
        lines.append("")

        recommendations = []
        if avg_hr < 0.6:
            recommendations.append("1. Consider increasing `top_k` to retrieve more candidates.")
            recommendations.append("2. Evaluate embedding model quality for domain-specific content.")
        if avg_mrr < 0.5:
            recommendations.append("3. Consider adding a reranker to improve ranking.")
            recommendations.append("4. Review chunking strategy for better context preservation.")
        if avg_ndcg < 0.5:
            recommendations.append("5. Consider hybrid retrieval (BM25 + vector search).")

        if not recommendations:
            recommendations.append("1. Current performance is satisfactory for baseline.")
            recommendations.append("2. Consider fine-tuning embedding model for domain-specific improvements.")
            recommendations.append("3. Explore advanced retrieval strategies for edge cases.")

        lines.extend(recommendations)
        lines.append("")

        return "\n".join(lines)

    def _generate_assets_section(self, result: ExperimentResult) -> str:
        lines = ["## 8. Experiment Assets", ""]
        lines.append("The following artifacts are available for this experiment:")
        lines.append("")
        lines.append("- Evaluation results: `baseline_report.json`")
        lines.append("- Experiment report: `experiment_report.md`")
        if result.meal_data_id:
            lines.append(f"- Data artifacts: `data/artifacts/{result.meal_data_id[:12]}/`")
        lines.append("")

        return "\n".join(lines)

    def _build_llm_prompt(self, result: ExperimentResult) -> str:
        data_section = self._generate_data_section(result)
        config_section = self._generate_config_section(result)
        results_section = self._generate_results_section(result)

        prompt = LLM_REPORT_PROMPT_TEMPLATE.format(
            timestamp=result.timestamp,
            data_id=result.meal_data_id or "N/A",
            total_test_cases=result.total_test_cases,
            data_section=data_section,
            config_section=config_section,
            results_section=results_section,
        )
        return prompt

    def _call_llm(self, prompt: str) -> str:
        if self._llm_client is None:
            self._init_llm_client()

        try:
            message = self._llm_client.messages.create(
                model=self.llm_model_name or "LongCat-Flash-Lite",
                max_tokens=4096,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            raise

    def _init_llm_client(self) -> None:
        if not self.llm_api_key:
            raise ValueError("LLM API key is required for LLM report generation")

        try:
            from anthropic import Anthropic

            self._llm_client = Anthropic(
                api_key="dummy",
                base_url=self.llm_base_url or "https://api.longcat.chat/anthropic",
                default_headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
                },
            )
            logger.info("LLM client initialized for report generation")
        except ImportError:
            raise ImportError("anthropic package is required for LLM report generation")
        except Exception as e:
            raise Exception(f"Failed to initialize LLM client: {str(e)}")

    def _format_llm_report(self, result: ExperimentResult, llm_response: str) -> str:
        header = self._generate_header(result)
        meta_info = [
            f"> Generated with LLM assistance at {datetime.now().isoformat()}",
            "",
        ]
        return "\n".join([header, ""] + meta_info + [llm_response])

    def _build_variant_comparison_llm_prompt(
        self,
        variant_results: List[Dict[str, Any]],
        meal_info: Optional[Dict[str, Any]] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        template_report = self._generate_variant_comparison_template(
            variant_results, meal_info, config_snapshot
        )

        prompt = f"""You are an expert RAG system analyst. Please write a comprehensive experiment report in Chinese (Simplified) based on the following experiment data.

## Experiment Data

{template_report}

## Requirements

Please write a professional experiment report with the following sections:

### 1. 实验概述
- Describe the purpose and setup of this experiment
- Explain the variants being compared
- Summarize the overall findings

### 2. 性能分析
- Analyze the retrieval metrics (Hit Rate, MRR, NDCG) for each variant
- Compare performance across different variants
- Identify strengths and weaknesses of each configuration

### 3. 问题类型分析
- Analyze performance patterns across different question types (factual, boundary, multi-hop)
- Identify which question types are more challenging
- Discuss potential reasons for performance differences

### 4. 配置影响分析
- Evaluate the impact of different configuration choices
- Discuss how chunk size, overlap, and other parameters affect performance
- Provide insights on optimal configuration choices

### 5. 结论与建议
- Summarize key findings
- Provide actionable recommendations for improvement
- Suggest next steps for optimization

Please write the report in a professional, objective tone with specific data references. Use markdown formatting for better readability.
"""
        return prompt

    def _format_variant_comparison_llm_report(
        self,
        variant_results: List[Dict[str, Any]],
        llm_response: str,
        meal_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        header = self._generate_variant_header(meal_info)
        meta_info = [
            "",
            f"> Generated with LLM assistance at {datetime.now().isoformat()}",
            "",
        ]
        return "\n".join([header] + meta_info + [llm_response])
