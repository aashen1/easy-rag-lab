from datetime import datetime
from typing import Any

from eval.reporter.formatters import (
    dict_to_yaml_lines,
    generate_tech_summary,
    get_generation_metric,
)


class TemplateVariantReporter:
    """Generates multi-variant comparison template reports."""

    def generate(
        self,
        variant_results: list[dict[str, Any]],
        meal_info: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
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

    def _generate_variant_header(self, meal_info: dict[str, Any] | None = None) -> str:
        title = "# RAG Multi-Variant Experiment Report"
        if meal_info and meal_info.get("name"):
            title += f" - {meal_info['name']}"
        return title

    def _generate_variant_overview_section(
        self,
        variant_results: list[dict[str, Any]],
        meal_info: dict[str, Any] | None = None,
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
        self, variant_results: list[dict[str, Any]]
    ) -> str:
        lines = ["## 2. Variant Comparison Table", ""]

        has_generation = any(vr.get("generation_metrics") for vr in variant_results)
        has_llm_retrieval = any(
            vr.get("llm_retrieval_metrics") for vr in variant_results
        )

        headers = [
            "Variant",
            "Description",
            "Hit Rate (doc)",
            "Hit Rate (chunk)",
            "Hit Rate (dedup)",
            "MRR (doc)",
            "MRR (chunk)",
            "NDCG (doc)",
            "NDCG (chunk)",
            "FPR",
        ]
        if has_llm_retrieval:
            headers.extend(["CP", "CR"])
        if has_generation:
            headers.extend(["Faithfulness", "Relevancy"])
        headers.extend(["Questions", "Time (s)"])

        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["---------"] * len(headers)) + "|")

        best_variant = self._find_best_variant(variant_results)

        for vr in variant_results:
            name = vr.get("variant_name", "unnamed")
            desc = vr.get("variant_description", "")
            if len(desc) > 30:
                desc = desc[:27] + "..."

            if "retrieval_metrics" in vr:
                metrics = vr["retrieval_metrics"]
                hr = metrics.get("avg_hit_rate", 0)
                chunk_metrics = metrics.get("chunk_level_metrics", {})
                chunk_hr = chunk_metrics.get("avg_hit_rate") if chunk_metrics else None
                dedup_metrics = metrics.get("dedup_metrics", {})
                dedup_hr = dedup_metrics.get("avg_hit_rate") if dedup_metrics else None
                mrr = metrics.get("avg_mrr", 0)
                chunk_mrr = chunk_metrics.get("avg_mrr") if chunk_metrics else None
                ndcg = metrics.get("avg_ndcg", 0)
                chunk_ndcg = chunk_metrics.get("avg_ndcg") if chunk_metrics else None
                fpr = metrics.get("avg_false_positive_rate")
                q_count = vr.get("total_questions", 0)
                time_s = vr.get("total_time_seconds", 0)

                marker = " ⭐" if vr == best_variant else ""

                chunk_hr_str = f"{chunk_hr:.4f}" if chunk_hr is not None else "N/A"
                dedup_hr_str = f"{dedup_hr:.4f}" if dedup_hr is not None else "N/A"
                chunk_mrr_str = f"{chunk_mrr:.4f}" if chunk_mrr is not None else "N/A"
                chunk_ndcg_str = (
                    f"{chunk_ndcg:.4f}" if chunk_ndcg is not None else "N/A"
                )
                if fpr is not None:
                    fpr_count = vr.get("retrieval_metrics", {}).get(
                        "irrelevant_questions_count", 0
                    )
                    fpr_str = f"{fpr:.4f} (n={fpr_count}"
                    if fpr_count < 3:
                        fpr_str += "⚠"
                    fpr_str += ")"
                else:
                    fpr_str = "N/A"

                row = [
                    f"{name}{marker}",
                    desc,
                    f"{hr:.4f}",
                    chunk_hr_str,
                    dedup_hr_str,
                    f"{mrr:.4f}",
                    chunk_mrr_str,
                    f"{ndcg:.4f}",
                    chunk_ndcg_str,
                    fpr_str,
                ]

                if has_llm_retrieval:
                    llm_metrics = vr.get("llm_retrieval_metrics", {})
                    cp = llm_metrics.get("avg_context_precision")
                    cr = llm_metrics.get("avg_context_recall")
                    cp_str = f"{cp:.2f}" if cp is not None else "N/A"
                    cr_str = f"{cr:.2f}" if cr is not None else "N/A"
                    row.extend([cp_str, cr_str])

                if has_generation:
                    gen_metrics = vr.get("generation_metrics", {})
                    faithfulness = get_generation_metric(gen_metrics, "faithfulness")
                    relevancy = get_generation_metric(gen_metrics, "answer_relevancy")
                    fa_str = (
                        f"{faithfulness:.2f}" if faithfulness is not None else "N/A"
                    )
                    ar_str = f"{relevancy:.2f}" if relevancy is not None else "N/A"
                    row.extend([fa_str, ar_str])

                row.extend([str(q_count), f"{time_s:.2f}"])
                lines.append("| " + " | ".join(row) + " |")
            else:
                error = vr.get("error", "Unknown error")
                if len(error) > 30:
                    error = error[:27] + "..."
                n_error_cols = 10
                if has_llm_retrieval:
                    n_error_cols += 2
                if has_generation:
                    n_error_cols += 2
                error_parts = " | ".join(["ERROR"] * n_error_cols)
                lines.append(f"| {name} | {desc} | {error_parts} | - | - |")

        lines.append("")
        lines.append("_⭐ = Best performing variant_")
        lines.append("")
        return "\n".join(lines)

    def _find_best_variant(
        self, variant_results: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
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
        self, variant_results: list[dict[str, Any]]
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
        lines.append("**Retrieval Metrics (document-level)**:")
        lines.append(f"- Hit Rate (doc): {metrics.get('avg_hit_rate', 0):.4f}")
        lines.append(f"- MRR (doc): {metrics.get('avg_mrr', 0):.4f}")
        lines.append(f"- NDCG (doc): {metrics.get('avg_ndcg', 0):.4f}")

        chunk_metrics = metrics.get("chunk_level_metrics", {})
        chunk_hr = chunk_metrics.get("avg_hit_rate") if chunk_metrics else None
        chunk_mrr = chunk_metrics.get("avg_mrr") if chunk_metrics else None
        chunk_ndcg = chunk_metrics.get("avg_ndcg") if chunk_metrics else None
        dedup_metrics = metrics.get("dedup_metrics", {})
        dedup_hr = dedup_metrics.get("avg_hit_rate") if dedup_metrics else None
        dedup_mrr = dedup_metrics.get("avg_mrr") if dedup_metrics else None
        fpr = metrics.get("avg_false_positive_rate")

        if any(
            v is not None
            for v in [chunk_hr, chunk_mrr, chunk_ndcg, dedup_hr, dedup_mrr, fpr]
        ):
            lines.append("")
            lines.append("**Retrieval Metrics (chunk-level)**:")
            if chunk_hr is not None:
                lines.append(f"- Hit Rate (chunk): {chunk_hr:.4f}")
            if chunk_mrr is not None:
                lines.append(f"- MRR (chunk): {chunk_mrr:.4f}")
            if chunk_ndcg is not None:
                lines.append(f"- NDCG (chunk): {chunk_ndcg:.4f}")
            if dedup_hr is not None:
                lines.append(f"- Hit Rate (dedup): {dedup_hr:.4f}")
            if dedup_mrr is not None:
                lines.append(f"- MRR (dedup): {dedup_mrr:.4f}")
            if fpr is not None:
                fpr_count = metrics.get("irrelevant_questions_count", 0)
                fpr_line = f"- False Positive Rate: {fpr:.4f} (n={fpr_count}"
                if fpr_count < 3:
                    fpr_line += ", ⚠ 样本量不足，统计意义有限"
                fpr_line += ")"
                lines.append(fpr_line)
            chunk_applicable = (
                chunk_metrics.get("retrieval_applicable_questions")
                if chunk_metrics
                else None
            )
            total_q = best.get("total_questions", 0)
            if chunk_applicable is not None and chunk_applicable < total_q:
                lines.append(
                    f"- Applicable Questions (chunk): {chunk_applicable}/{total_q}"
                )

        lines.append("")

        if best.get("llm_retrieval_metrics"):
            llm_metrics = best["llm_retrieval_metrics"]
            lines.append("**LLM Retrieval Metrics**:")
            cp = llm_metrics.get("avg_context_precision")
            cr = llm_metrics.get("avg_context_recall")
            if cp is not None:
                lines.append(f"- Context Precision: {cp:.4f}")
            if cr is not None:
                lines.append(f"- Context Recall: {cr:.4f}")
            lines.append("")

        if best.get("generation_metrics"):
            gen_metrics = best["generation_metrics"]
            lines.append("**Generation Quality Metrics**:")
            faithfulness = get_generation_metric(gen_metrics, "faithfulness")
            relevancy = get_generation_metric(gen_metrics, "answer_relevancy")
            if faithfulness is not None:
                lines.append(f"- Faithfulness: {faithfulness:.4f}")
            if relevancy is not None:
                lines.append(f"- Answer Relevancy: {relevancy:.4f}")
            lines.append("")

        lines.append(f"- Total Questions: {best.get('total_questions', 0)}")
        lines.append(f"- Total Time: {best.get('total_time_seconds', 0):.2f}s")
        lines.append("")

        config_snapshot = best.get("config_snapshot", {})
        if config_snapshot and "merged" in config_snapshot:
            merged = config_snapshot["merged"]
            lines.append("**Technology Summary**:")
            lines.extend(generate_tech_summary(merged))
            lines.append("")

        return "\n".join(lines)

    def _generate_variant_details_section(
        self, variant_results: list[dict[str, Any]]
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

                chunk_metrics = metrics.get("chunk_level_metrics", {})
                if chunk_metrics:
                    chunk_hr = chunk_metrics.get("avg_hit_rate")
                    chunk_mrr = chunk_metrics.get("avg_mrr")
                    chunk_ndcg = chunk_metrics.get("avg_ndcg")
                    if any(v is not None for v in [chunk_hr, chunk_mrr, chunk_ndcg]):
                        lines.append("")
                        lines.append("**Chunk-Level Metrics**:")
                        if chunk_hr is not None:
                            lines.append(f"- Hit Rate (chunk): {chunk_hr:.4f}")
                        if chunk_mrr is not None:
                            lines.append(f"- MRR (chunk): {chunk_mrr:.4f}")
                        if chunk_ndcg is not None:
                            lines.append(f"- NDCG (chunk): {chunk_ndcg:.4f}")
                    chunk_applicable = chunk_metrics.get(
                        "retrieval_applicable_questions"
                    )
                    total_q = vr.get("total_questions", 0)
                    if chunk_applicable is not None and chunk_applicable < total_q:
                        lines.append(
                            f"- Applicable Questions (chunk): {chunk_applicable}/{total_q}"
                        )

                lines.append("")

                if vr.get("generation_metrics"):
                    gen_metrics = vr["generation_metrics"]
                    lines.append("**Generation Quality Metrics**:")
                    faithfulness = get_generation_metric(gen_metrics, "faithfulness")
                    relevancy = get_generation_metric(gen_metrics, "answer_relevancy")
                    if faithfulness is not None:
                        lines.append(f"- Faithfulness: {faithfulness:.4f}")
                    if relevancy is not None:
                        lines.append(f"- Answer Relevancy: {relevancy:.4f}")
                    lines.append("")

                config_snapshot = vr.get("config_snapshot", {})
                if config_snapshot and "merged" in config_snapshot:
                    merged = config_snapshot["merged"]
                    lines.append("**Technology Summary**:")
                    lines.extend(generate_tech_summary(merged))
                    lines.append("")
            else:
                error = vr.get("error", "Unknown error")
                lines.append(f"**Error**: {error}")
                lines.append("")

        return "\n".join(lines)

    def _generate_variant_config_section(
        self,
        variant_results: list[dict[str, Any]],
        config_snapshot: dict[str, Any] | None = None,
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
                    lines.extend(dict_to_yaml_lines(config, indent=1))
                else:
                    lines.append(f"  {config}")
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _generate_variant_recommendations_section(
        self, variant_results: list[dict[str, Any]]
    ) -> str:
        lines = ["## 6. Recommendations", ""]

        best = self._find_best_variant(variant_results)
        if not best:
            lines.append(
                "Unable to generate recommendations due to lack of successful variants."
            )
            lines.append("")
            return "\n".join(lines)

        best_metrics = best.get("retrieval_metrics", {})
        best_hr = best_metrics.get("avg_hit_rate", 0)
        best_mrr = best_metrics.get("avg_mrr", 0)
        best_ndcg = best_metrics.get("avg_ndcg", 0)

        lines.append("### Retrieval Performance Analysis")
        lines.append("")

        if best_hr >= 0.95:
            hr_assessment = "⚠️ WARNING: Hit rate is unusually high (>0.95). This may indicate test set leakage or overly broad ground truth. Please verify the test set quality."
        elif best_hr >= 0.8:
            hr_assessment = "Excellent retrieval performance."
        elif best_hr >= 0.6:
            hr_assessment = "Good retrieval performance with room for improvement."
        elif best_hr >= 0.4:
            hr_assessment = "Moderate retrieval performance, optimization recommended."
        else:
            hr_assessment = (
                "Low retrieval performance, significant optimization needed."
            )

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

        has_chunk_metrics = any(
            vr.get("retrieval_metrics", {})
            .get("chunk_level_metrics", {})
            .get("avg_hit_rate")
            is not None
            for vr in variant_results
        )

        if has_chunk_metrics:
            lines.append("### Document vs Chunk-Level Analysis")
            lines.append("")

            chunk_metrics = best_metrics.get("chunk_level_metrics", {})
            best_chunk_hr = chunk_metrics.get("avg_hit_rate") if chunk_metrics else None
            dedup_metrics = best_metrics.get("dedup_metrics", {})
            best_dedup_hr = dedup_metrics.get("avg_hit_rate") if dedup_metrics else None
            best_fpr = best_metrics.get("avg_false_positive_rate")

            if best_chunk_hr is not None:
                doc_chunk_gap = best_hr - best_chunk_hr
                if doc_chunk_gap > 0.1:
                    gap_assessment = "Significant gap - chunk-level retrieval is substantially harder, suggesting fine-grained matching needs improvement."
                elif doc_chunk_gap > 0.05:
                    gap_assessment = "Moderate gap - chunk-level performance is lower but acceptable."
                else:
                    gap_assessment = "Small gap - chunk-level retrieval performs nearly as well as document-level."
                lines.append(
                    f"- **Doc vs Chunk Hit Rate Gap ({doc_chunk_gap:.4f})**: {gap_assessment}"
                )

            if best_dedup_hr is not None and best_chunk_hr is not None:
                dedup_improvement = best_dedup_hr - best_chunk_hr
                if dedup_improvement > 0.05:
                    dedup_assessment = "Deduplication significantly improves hit rate, indicating many redundant chunks in results."
                elif dedup_improvement > 0:
                    dedup_assessment = (
                        "Deduplication provides marginal improvement in hit rate."
                    )
                else:
                    dedup_assessment = "Deduplication shows no improvement, suggesting minimal redundancy in retrieved chunks."
                lines.append(
                    f"- **Dedup vs Chunk Hit Rate ({dedup_improvement:+.4f})**: {dedup_assessment}"
                )

            if best_fpr is not None:
                fpr_count = best.get("retrieval_metrics", {}).get(
                    "irrelevant_questions_count", 0
                )
                if best_fpr > 0.3:
                    if fpr_count >= 3:
                        fpr_assessment = "High retrieval occupancy for irrelevant questions — standard vector retrieval typically returns top-k results regardless of relevance; consider adding a rejection mechanism if needed."
                    else:
                        fpr_assessment = "High retrieval occupancy (⚠ insufficient sample) — FPR near 1.0 is expected for vector retrieval; sample too small for reliable assessment."
                else:
                    fpr_assessment = "Low retrieval occupancy — system effectively filters irrelevant queries."
                lines.append(
                    f"- **False Positive Rate ({best_fpr:.4f})**: {fpr_assessment}"
                )

            lines.append("")

        if best.get("generation_metrics"):
            gen_metrics = best["generation_metrics"]
            best_faithfulness = get_generation_metric(gen_metrics, "faithfulness") or 0
            best_relevancy = get_generation_metric(gen_metrics, "answer_relevancy") or 0

            lines.append("### Generation Quality Analysis")
            lines.append("")

            if best_faithfulness >= 0.8:
                fa_assessment = "Excellent - Answers are well-grounded in contexts."
            elif best_faithfulness >= 0.6:
                fa_assessment = "Good - Most answers are supported by contexts."
            elif best_faithfulness >= 0.4:
                fa_assessment = "Moderate - Some hallucinations detected."
            else:
                fa_assessment = "Low - Significant hallucinations, needs improvement."

            if best_relevancy >= 0.8:
                ar_assessment = "Excellent - Answers directly address questions."
            elif best_relevancy >= 0.6:
                ar_assessment = "Good - Answers are mostly relevant."
            elif best_relevancy >= 0.4:
                ar_assessment = "Moderate - Some answers may be off-topic."
            else:
                ar_assessment = "Low - Answers often irrelevant, needs improvement."

            lines.append(
                f"- **Faithfulness ({best_faithfulness:.4f})**: {fa_assessment}"
            )
            lines.append(
                f"- **Answer Relevancy ({best_relevancy:.4f})**: {ar_assessment}"
            )
            lines.append("")

        lines.append("### Anomaly Detection")
        lines.append("")

        hallucination_rate = best_metrics.get("hallucination_rate")
        if hallucination_rate is not None and hallucination_rate > 0:
            lines.append(
                f"- **Hallucination Rate ({hallucination_rate:.2%})**: {hallucination_rate * 100:.1f}% of questions show faithfulness below 0.5, indicating potential hallucination."
            )
        else:
            lines.append(
                "- **Hallucination Rate**: No hallucination detected (all faithfulness scores >= 0.5)."
            )

        avg_diversity = best_metrics.get("avg_retrieval_diversity")
        if avg_diversity is not None:
            if avg_diversity < 0.4:
                lines.append(
                    f"- **Retrieval Diversity ({avg_diversity:.4f})**: ⚠️ LOW - Top-k results often come from the same document, limiting information breadth."
                )
            elif avg_diversity < 0.7:
                lines.append(
                    f"- **Retrieval Diversity ({avg_diversity:.4f})**: Moderate - Some diversity in retrieved documents."
                )
            else:
                lines.append(
                    f"- **Retrieval Diversity ({avg_diversity:.4f})**: Good - Top-k results come from diverse documents."
                )
        lines.append("")

        by_type = best_metrics.get("by_question_type")
        if by_type:
            lines.append("### Per-Question-Type Breakdown")
            lines.append("")
            lines.append("| Type | Count | Avg Hit Rate | Avg MRR | Avg Faithfulness |")
            lines.append("|------|-------|-------------|---------|-----------------|")
            for qtype, tm in sorted(by_type.items()):
                count = tm.get("count", 0)
                hr = tm.get("avg_hit_rate", "N/A")
                mrr = tm.get("avg_mrr", "N/A")
                faith = tm.get("avg_faithfulness", "N/A")
                if faith == "N/A":
                    faith = tm.get("avg_builtin_faithfulness", "N/A")
                if faith == "N/A":
                    faith = tm.get("avg_ragas_faithfulness", "N/A")
                hr_str = f"{hr:.4f}" if isinstance(hr, int | float) else hr
                mrr_str = f"{mrr:.4f}" if isinstance(mrr, int | float) else mrr
                faith_str = f"{faith:.4f}" if isinstance(faith, int | float) else faith
                lines.append(
                    f"| {qtype} | {count} | {hr_str} | {mrr_str} | {faith_str} |"
                )
            lines.append("")

        lines.append("### Optimization Suggestions")
        lines.append("")

        recommendations = []
        rec_num = 1

        if best_hr < 0.6:
            recommendations.append(
                f"{rec_num}. Consider increasing `top_k` to retrieve more candidate documents."
            )
            rec_num += 1
            recommendations.append(
                f"{rec_num}. Evaluate embedding model quality for domain-specific content."
            )
            rec_num += 1
            recommendations.append(
                f"{rec_num}. Consider hybrid retrieval (BM25 + vector search)."
            )
            rec_num += 1

        if best_mrr < 0.5:
            recommendations.append(
                f"{rec_num}. Add a reranker to improve document ranking."
            )
            rec_num += 1
            recommendations.append(
                f"{rec_num}. Review chunking strategy for better context preservation."
            )
            rec_num += 1

        if best_ndcg < 0.5:
            recommendations.append(
                f"{rec_num}. Consider semantic chunking for better context boundaries."
            )
            rec_num += 1

        if best.get("generation_metrics"):
            gen_metrics = best["generation_metrics"]
            best_faithfulness = get_generation_metric(gen_metrics, "faithfulness") or 0
            best_relevancy = get_generation_metric(gen_metrics, "answer_relevancy") or 0

            if best_faithfulness < 0.6:
                recommendations.append(
                    f"{rec_num}. Review prompt engineering to reduce hallucinations."
                )
                rec_num += 1
                recommendations.append(
                    f"{rec_num}. Ensure retrieved contexts are relevant and complete."
                )
                rec_num += 1

            if best_relevancy < 0.6:
                recommendations.append(
                    f"{rec_num}. Improve question understanding in generation prompts."
                )
                rec_num += 1
                recommendations.append(
                    f"{rec_num}. Consider answer validation or filtering."
                )
                rec_num += 1

        if not recommendations:
            recommendations.append(
                f"{rec_num}. Current best variant shows satisfactory performance."
            )
            rec_num += 1
            recommendations.append(
                f"{rec_num}. Consider fine-tuning embedding model for domain-specific improvements."
            )
            rec_num += 1
            recommendations.append(
                f"{rec_num}. Explore advanced retrieval strategies for edge cases."
            )
            rec_num += 1

        lines.extend(recommendations)
        lines.append("")

        lines.append("### Next Steps")
        lines.append("")
        lines.append("1. Deploy the best performing variant for production use.")
        lines.append("2. Continue experimenting with other optimization techniques.")
        lines.append("3. Monitor performance in real-world usage.")
        lines.append("")

        return "\n".join(lines)
