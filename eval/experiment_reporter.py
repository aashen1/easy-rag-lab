from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.exceptions import EvaluationError

DEFAULT_REPORT_CONFIG = {
    "model_name": "LongCat-Flash-Lite",
    "base_url": "https://api.longcat.chat/anthropic",
    "temperature": 0.3,
    "max_tokens": 4096,
}


@dataclass
class TestCaseResult:
    __test__ = False
    id: str
    question: str
    answer: str | None
    retrieval: dict[str, float] | None = None
    generation: dict[str, float] | None = None
    llm_retrieval: dict[str, float] | None = None
    sources: list[str] | None = None
    error: str | None = None
    time_seconds: float = 0.0
    category: str | None = None


@dataclass
class VariantResult:
    variant_name: str
    variant_description: str | None = None
    retrieval_metrics: dict[str, float] | None = None
    generation_metrics: dict[str, float] | None = None
    llm_retrieval_metrics: dict[str, float] | None = None
    config_snapshot: dict[str, Any] | None = None
    total_questions: int = 0
    total_time_seconds: float = 0.0
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VariantResult":
        return cls(
            variant_name=data.get("variant_name", "unnamed"),
            variant_description=data.get("variant_description"),
            retrieval_metrics=data.get("retrieval_metrics"),
            generation_metrics=data.get("generation_metrics"),
            llm_retrieval_metrics=data.get("llm_retrieval_metrics"),
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
    retrieval_metrics: dict[str, float]
    results: list[TestCaseResult]
    generation_metrics: dict[str, float] | None = None
    llm_retrieval_metrics: dict[str, float] | None = None
    meal_data_id: str | None = None
    meal_name: str | None = None
    config_snapshot: dict[str, Any] | None = None
    config_hashes: dict[str, str] | None = None
    pdf_files: list[dict[str, Any]] | None = None
    stats: dict[str, Any] | None = None
    variant_results: list[VariantResult] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentResult":
        results = []
        for r in data.get("results", []):
            results.append(TestCaseResult(
                id=r.get("id", ""),
                question=r.get("question", ""),
                answer=r.get("answer"),
                retrieval=r.get("retrieval"),
                generation=r.get("generation"),
                llm_retrieval=r.get("llm_retrieval"),
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
            generation_metrics=data.get("generation_metrics"),
            llm_retrieval_metrics=data.get("llm_retrieval_metrics"),
            meal_data_id=data.get("meal_data_id"),
            meal_name=data.get("meal_name"),
            config_snapshot=data.get("config_snapshot"),
            config_hashes=data.get("config_hashes"),
            pdf_files=data.get("pdf_files"),
            stats=data.get("stats"),
            variant_results=variant_results,
        )


LLM_REPORT_PROMPT_TEMPLATE = """你是一位专业的RAG系统分析师。请根据以下数据撰写一份全面的实验报告。

## 实验概览
- 实验时间：{timestamp}
- 数据ID：{data_id}
- 测试用例总数：{total_test_cases}

## 数据来源
{data_section}

## 技术配置
{config_section}

## 评测结果
{results_section}

## 要求
请撰写一份专业的实验报告，包含以下章节：

### 1. 实验概述
- 描述本实验的目的和假设
- 说明评测的意义

### 2. 数据来源分析
- 分析数据特征
- 讨论数据对结果的潜在影响

### 3. 技术选型分析
- 评估所选技术和模型
- 讨论潜在的优势和局限

### 4. 检索性能分析
- 解读检索指标（Hit Rate、MRR、NDCG）
- 解读 LLM 检索指标（Context Precision、Context Recall）
  - Context Precision: 检索到的上下文是否与问题相关，以及排序质量
  - Context Recall: Ground Truth 中的信息是否能从检索上下文中推断
- **必须分析检索多样性（Retrieval Diversity）**：如果 top-k 结果来自同一文档，说明信息来源单一
- 分析不同问题类型的表现差异
- 识别潜在的瓶颈或问题
- **必须标出检索完全失败的问题（hit_rate=0）**

### 5. 生成质量分析
- 解读生成质量指标（Faithfulness、Answer Relevancy）
- 分析回答是否基于检索内容（Faithfulness）
- 分析回答是否切题（Answer Relevancy）
- **必须标出幻觉问题（faithfulness < 0.5 的问题）**，逐个列出问题ID和具体错误
- 识别潜在的幻觉或不相关问题

### 6. 结论与建议
- 总结关键发现
- **如果有幻觉或检索失败，必须在结论中明确指出，不得用"表现优异"等笼统描述掩盖**
- 提出可行的改进建议
- 建议下一步优化方向

报告须以专业、客观的语气撰写，引用具体数据。直接以报告正文开头，禁止使用"好的"、"当然"、"我来"等对话性用语开头。
"""


class ExperimentReporter:
    """Experiment report generator supporting template and LLM modes."""

    @staticmethod
    def _dict_to_yaml_lines(data: Any, indent: int = 0) -> list[str]:
        """Convert a dict to YAML-like lines with arbitrary nesting depth.

        Args:
            data: Data to convert (dict, list, or scalar).
            indent: Current indentation level.

        Returns:
            List of YAML-formatted lines.
        """
        lines = []
        prefix = "  " * indent

        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    lines.append(f"{prefix}{k}:")
                    lines.extend(ExperimentReporter._dict_to_yaml_lines(v, indent + 1))
                elif isinstance(v, list):
                    lines.append(f"{prefix}{k}:")
                    for item in v:
                        if isinstance(item, dict):
                            lines.append(f"{prefix}  -")
                            lines.extend(ExperimentReporter._dict_to_yaml_lines(item, indent + 2))
                        else:
                            lines.append(f"{prefix}  - {item}")
                else:
                    lines.append(f"{prefix}{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    lines.extend(ExperimentReporter._dict_to_yaml_lines(item, indent + 1))
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}{data}")

        return lines

    @staticmethod
    def _generate_tech_summary(merged_config: dict[str, Any]) -> list[str]:
        """Generate a concise technology summary from merged config.

        Args:
            merged_config: Full merged configuration dictionary.

        Returns:
            List of markdown lines summarizing key technology choices.
        """
        lines = []
        retrieval = merged_config.get("retrieval", {})
        chunker = merged_config.get("chunker", {})
        embedding = merged_config.get("embedding", {})
        vector_store = merged_config.get("vector_store", {})

        method = retrieval.get("method", "vector")
        method_labels = {
            "vector": "Vector (dense)",
            "bm25": "BM25 (sparse)",
            "hybrid": "Hybrid (dense + sparse)",
        }
        lines.append(f"- Retrieval: {method_labels.get(method, method)}")
        lines.append(f"- Top-K: {retrieval.get('top_k', 5)}")

        reranker = retrieval.get("reranker", {})
        if reranker.get("enabled", False):
            lines.append(f"- Reranker: {reranker.get('model_name', 'N/A')} (top_n={reranker.get('top_n', 3)})")
        else:
            lines.append("- Reranker: Disabled")

        query_rewrite = retrieval.get("query_rewrite", {})
        if query_rewrite.get("enabled", False):
            lines.append(f"- Query Rewrite: {query_rewrite.get('strategy', 'N/A')}")
        else:
            lines.append("- Query Rewrite: Disabled")

        if method == "hybrid":
            hybrid = retrieval.get("hybrid", {})
            lines.append(f"- Fusion: {hybrid.get('fusion', 'rrf')} (rrf_k={hybrid.get('rrf_k', 60)})")

        lines.append(f"- Chunking: {chunker.get('strategy', 'fixed')} (size={chunker.get('chunk_size', 512)}, overlap={chunker.get('chunk_overlap', 0)})")
        lines.append(f"- Embedding: {embedding.get('model_name', 'N/A')}")
        lines.append(f"- Vector Store: {vector_store.get('type', 'N/A')} ({vector_store.get('distance', 'Cosine')})")

        return lines

    def __init__(
        self,
        llm_api_key: str | None = None,
        llm_base_url: str | None = None,
        llm_model_name: str | None = None,
        token_tracker: Any | None = None,
    ):
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model_name = llm_model_name
        self._llm_client = None
        self.token_tracker = token_tracker

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
        variant_results: list[dict[str, Any]],
        meal_info: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
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

    def _generate_variant_comparison_llm(
        self,
        variant_results: list[dict[str, Any]],
        meal_info: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
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
        self, meal_info: dict[str, Any] | None = None
    ) -> str:
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

        has_generation = any(
            vr.get("generation_metrics") for vr in variant_results
        )
        has_llm_retrieval = any(
            vr.get("llm_retrieval_metrics") for vr in variant_results
        )

        headers = [
            "Variant", "Description",
            "Hit Rate (doc)", "Hit Rate (chunk)", "Hit Rate (dedup)",
            "MRR (doc)", "MRR (chunk)",
            "NDCG (doc)", "NDCG (chunk)",
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
                chunk_hr = metrics.get("avg_chunk_hit_rate")
                dedup_hr = metrics.get("avg_dedup_hit_rate")
                mrr = metrics.get("avg_mrr", 0)
                chunk_mrr = metrics.get("avg_chunk_mrr")
                ndcg = metrics.get("avg_ndcg", 0)
                chunk_ndcg = metrics.get("avg_chunk_ndcg")
                fpr = metrics.get("avg_false_positive_rate")
                q_count = vr.get("total_questions", 0)
                time_s = vr.get("total_time_seconds", 0)

                marker = " ⭐" if vr == best_variant else ""

                chunk_hr_str = f"{chunk_hr:.4f}" if chunk_hr is not None else "N/A"
                dedup_hr_str = f"{dedup_hr:.4f}" if dedup_hr is not None else "N/A"
                chunk_mrr_str = f"{chunk_mrr:.4f}" if chunk_mrr is not None else "N/A"
                chunk_ndcg_str = f"{chunk_ndcg:.4f}" if chunk_ndcg is not None else "N/A"
                fpr_str = f"{fpr:.4f}" if fpr is not None else "N/A"

                row = [
                    f"{name}{marker}", desc,
                    f"{hr:.4f}", chunk_hr_str, dedup_hr_str,
                    f"{mrr:.4f}", chunk_mrr_str,
                    f"{ndcg:.4f}", chunk_ndcg_str,
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
                    faithfulness = gen_metrics.get("avg_faithfulness")
                    relevancy = gen_metrics.get("avg_answer_relevancy")
                    fa_str = f"{faithfulness:.2f}" if faithfulness is not None else "N/A"
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

        chunk_hr = metrics.get("avg_chunk_hit_rate")
        chunk_mrr = metrics.get("avg_chunk_mrr")
        chunk_ndcg = metrics.get("avg_chunk_ndcg")
        dedup_hr = metrics.get("avg_dedup_hit_rate")
        dedup_mrr = metrics.get("avg_dedup_mrr")
        fpr = metrics.get("avg_false_positive_rate")

        if any(v is not None for v in [chunk_hr, chunk_mrr, chunk_ndcg, dedup_hr, dedup_mrr, fpr]):
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
                lines.append(f"- False Positive Rate: {fpr:.4f}")

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
            faithfulness = gen_metrics.get("avg_faithfulness")
            relevancy = gen_metrics.get("avg_answer_relevancy")
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
            lines.extend(self._generate_tech_summary(merged))
            lines.append("")
            lines.append("**Configuration**:")
            lines.append("```yaml")
            lines.extend(self._dict_to_yaml_lines(merged))
            lines.append("```")
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
                lines.append("")

                if vr.get("generation_metrics"):
                    gen_metrics = vr["generation_metrics"]
                    lines.append("**Generation Quality Metrics**:")
                    faithfulness = gen_metrics.get("avg_faithfulness")
                    relevancy = gen_metrics.get("avg_answer_relevancy")
                    if faithfulness is not None:
                        lines.append(f"- Faithfulness: {faithfulness:.4f}")
                    if relevancy is not None:
                        lines.append(f"- Answer Relevancy: {relevancy:.4f}")
                    lines.append("")

                config_snapshot = vr.get("config_snapshot", {})
                if config_snapshot and "merged" in config_snapshot:
                    merged = config_snapshot["merged"]
                    lines.append("**Technology Summary**:")
                    lines.extend(self._generate_tech_summary(merged))
                    lines.append("")
                    lines.append("**Configuration**:")
                    lines.append("```yaml")
                    lines.extend(self._dict_to_yaml_lines(merged))
                    lines.append("```")
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
                    lines.extend(self._dict_to_yaml_lines(config, indent=1))
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
            lines.append("Unable to generate recommendations due to lack of successful variants.")
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

        has_chunk_metrics = any(
            vr.get("retrieval_metrics", {}).get("avg_chunk_hit_rate") is not None
            for vr in variant_results
        )

        if has_chunk_metrics:
            lines.append("### Document vs Chunk-Level Analysis")
            lines.append("")

            best_chunk_hr = best_metrics.get("avg_chunk_hit_rate")
            best_dedup_hr = best_metrics.get("avg_dedup_hit_rate")
            best_fpr = best_metrics.get("avg_false_positive_rate")

            if best_chunk_hr is not None:
                doc_chunk_gap = best_hr - best_chunk_hr
                if doc_chunk_gap > 0.1:
                    gap_assessment = "Significant gap - chunk-level retrieval is substantially harder, suggesting fine-grained matching needs improvement."
                elif doc_chunk_gap > 0.05:
                    gap_assessment = "Moderate gap - chunk-level performance is lower but acceptable."
                else:
                    gap_assessment = "Small gap - chunk-level retrieval performs nearly as well as document-level."
                lines.append(f"- **Doc vs Chunk Hit Rate Gap ({doc_chunk_gap:.4f})**: {gap_assessment}")

            if best_dedup_hr is not None and best_chunk_hr is not None:
                dedup_improvement = best_dedup_hr - best_chunk_hr
                if dedup_improvement > 0.05:
                    dedup_assessment = "Deduplication significantly improves hit rate, indicating many redundant chunks in results."
                elif dedup_improvement > 0:
                    dedup_assessment = "Deduplication provides marginal improvement in hit rate."
                else:
                    dedup_assessment = "Deduplication shows no improvement, suggesting minimal redundancy in retrieved chunks."
                lines.append(f"- **Dedup vs Chunk Hit Rate ({dedup_improvement:+.4f})**: {dedup_assessment}")

            if best_fpr is not None:
                if best_fpr > 0.3:
                    fpr_assessment = "High false positive rate - many retrieved chunks are irrelevant, consider improving retrieval precision."
                elif best_fpr > 0.1:
                    fpr_assessment = "Moderate false positive rate - some irrelevant chunks are retrieved."
                else:
                    fpr_assessment = "Low false positive rate - retrieved chunks are mostly relevant."
                lines.append(f"- **False Positive Rate ({best_fpr:.4f})**: {fpr_assessment}")

            lines.append("")

        if best.get("generation_metrics"):
            gen_metrics = best["generation_metrics"]
            best_faithfulness = gen_metrics.get("avg_faithfulness", 0)
            best_relevancy = gen_metrics.get("avg_answer_relevancy", 0)

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

            lines.append(f"- **Faithfulness ({best_faithfulness:.4f})**: {fa_assessment}")
            lines.append(f"- **Answer Relevancy ({best_relevancy:.4f})**: {ar_assessment}")
            lines.append("")

        lines.append("### Anomaly Detection")
        lines.append("")

        hallucination_rate = best_metrics.get("hallucination_rate")
        if hallucination_rate is not None and hallucination_rate > 0:
            lines.append(f"- **Hallucination Rate ({hallucination_rate:.2%})**: {hallucination_rate * 100:.1f}% of questions show faithfulness below 0.5, indicating potential hallucination.")
        else:
            lines.append("- **Hallucination Rate**: No hallucination detected (all faithfulness scores >= 0.5).")

        avg_diversity = best_metrics.get("avg_retrieval_diversity")
        if avg_diversity is not None:
            if avg_diversity < 0.4:
                lines.append(f"- **Retrieval Diversity ({avg_diversity:.4f})**: ⚠️ LOW - Top-k results often come from the same document, limiting information breadth.")
            elif avg_diversity < 0.7:
                lines.append(f"- **Retrieval Diversity ({avg_diversity:.4f})**: Moderate - Some diversity in retrieved documents.")
            else:
                lines.append(f"- **Retrieval Diversity ({avg_diversity:.4f})**: Good - Top-k results come from diverse documents.")
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
                hr_str = f"{hr:.4f}" if isinstance(hr, int | float) else hr
                mrr_str = f"{mrr:.4f}" if isinstance(mrr, int | float) else mrr
                faith_str = f"{faith:.4f}" if isinstance(faith, int | float) else faith
                lines.append(f"| {qtype} | {count} | {hr_str} | {mrr_str} | {faith_str} |")
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
            best_faithfulness = gen_metrics.get("avg_faithfulness", 0)
            best_relevancy = gen_metrics.get("avg_answer_relevancy", 0)

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
        title = "# RAG Experiment Report"
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
            merged = result.config_snapshot.get("merged", result.config_snapshot)
            if "retrieval" in merged or "chunker" in merged:
                lines.append("### Technology Summary")
                lines.append("")
                lines.extend(self._generate_tech_summary(merged))
                lines.append("")

            lines.append("### Configuration Snapshot")
            lines.append("")
            lines.append("```yaml")
            lines.extend(self._dict_to_yaml_lines(result.config_snapshot))
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

    def _get_metric_description(self, metric: str) -> str:
        """Get description for a retrieval metric.

        Args:
            metric: Metric name (e.g., 'avg_hit_rate', 'avg_mrr').

        Returns:
            Human-readable description of the metric.
        """
        descriptions = {
            "avg_hit_rate": "Percentage of queries where relevant docs were retrieved",
            "avg_mrr": "Average position of first relevant document",
            "avg_ndcg": "Normalized ranking quality across all positions",
        }
        return descriptions.get(metric, "Retrieval quality metric")

    def _get_generation_metric_description(self, metric: str) -> str:
        """Get description for a generation quality metric.

        Args:
            metric: Metric name (e.g., 'avg_faithfulness', 'avg_builtin_faithfulness').

        Returns:
            Human-readable description of the metric.
        """
        descriptions = {
            "avg_faithfulness": "How well the answer is grounded in retrieved contexts",
            "avg_answer_relevancy": "How relevant the answer is to the question",
            "avg_builtin_faithfulness": "Builtin: How well the answer is grounded in retrieved contexts",
            "avg_builtin_answer_relevancy": "Builtin: How relevant the answer is to the question",
            "avg_ragas_faithfulness": "RAGAS: How well the answer is grounded in retrieved contexts",
            "avg_ragas_answer_relevancy": "RAGAS: How relevant the answer is to the question",
            "avg_ragas_context_precision": "RAGAS: How precise the retrieved contexts are",
            "avg_ragas_context_recall": "RAGAS: How completely the contexts cover the ground truth",
            "avg_ragas_answer_correctness": "RAGAS: How correct the answer is compared to reference",
            "avg_ragas_semantic_similarity": "RAGAS: Semantic similarity between answer and reference",
        }
        if metric not in descriptions:
            for prefix in ["builtin_", "ragas_"]:
                if prefix in metric:
                    base_metric = metric.replace(prefix, "")
                    base_desc = descriptions.get(f"avg_{base_metric}", "")
                    backend = prefix.rstrip("_").upper()
                    if base_desc:
                        return f"{backend}: {base_desc}"
                    return f"{backend}: Generation quality metric"
        return descriptions.get(metric, "Generation quality metric")

    def _generate_results_section(self, result: ExperimentResult) -> str:
        lines = ["## 5. Evaluation Results", ""]

        lines.append("### Overall Retrieval Metrics")
        lines.append("")
        lines.append("| Metric | Value | Description |")
        lines.append("|--------|-------|-------------|")
        for metric, value in result.retrieval_metrics.items():
            metric_name = metric.replace("avg_", "").replace("_", " ").upper()
            description = self._get_metric_description(metric)
            lines.append(f"| {metric_name} | {value:.4f} | {description} |")
        lines.append("")

        if result.generation_metrics:
            lines.append("### Generation Quality Metrics")
            lines.append("")
            lines.append("| Metric | Value | Description |")
            lines.append("|--------|-------|-------------|")
            for metric, value in result.generation_metrics.items():
                metric_name = metric.replace("avg_", "").replace("_", " ").title()
                description = self._get_generation_metric_description(metric)
                lines.append(f"| {metric_name} | {value:.4f} | {description} |")
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

        has_generation = any(r.generation for r in result.results)

        if has_generation:
            lines.append("| ID | Question | Hit Rate | MRR | NDCG | Faithfulness | Relevancy | Time (s) |")
            lines.append("|----|----------|----------|-----|------|--------------|-----------|----------|")
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
                    faithfulness = r.generation.get("faithfulness")
                    relevancy = r.generation.get("answer_relevancy")
                    fa_str = f"{faithfulness:.2f}" if faithfulness is not None else "N/A"
                    ar_str = f"{relevancy:.2f}" if relevancy is not None else "N/A"
                    lines.append(f"| {r.id} | {q_short} | {hr:.4f} | {mrr:.4f} | {ndcg:.4f} | {fa_str} | {ar_str} | {r.time_seconds:.2f} |")
                else:
                    lines.append(f"| {r.id} | {q_short} | {hr:.4f} | {mrr:.4f} | {ndcg:.4f} | {r.time_seconds:.2f} |")
            else:
                if has_generation:
                    lines.append(f"| {r.id} | {q_short} | N/A | N/A | N/A | N/A | N/A | {r.time_seconds:.2f} |")
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

        lines.append("### Retrieval Performance Summary")
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

        if result.generation_metrics:
            avg_faithfulness = result.generation_metrics.get("avg_faithfulness", 0)
            avg_relevancy = result.generation_metrics.get("avg_answer_relevancy", 0)

            lines.append("### Generation Quality Summary")
            lines.append("")

            if avg_faithfulness >= 0.8:
                fa_assessment = "Excellent - Answers are well-grounded in retrieved contexts."
            elif avg_faithfulness >= 0.6:
                fa_assessment = "Good - Most answer content is supported by contexts."
            elif avg_faithfulness >= 0.4:
                fa_assessment = "Moderate - Some hallucinations detected, review needed."
            else:
                fa_assessment = "Needs Improvement - Significant hallucinations, answers not grounded."

            if avg_relevancy >= 0.8:
                ar_assessment = "Excellent - Answers directly address the questions."
            elif avg_relevancy >= 0.6:
                ar_assessment = "Good - Answers are mostly relevant to questions."
            elif avg_relevancy >= 0.4:
                ar_assessment = "Moderate - Some answers may be off-topic or incomplete."
            else:
                ar_assessment = "Needs Improvement - Answers often irrelevant to questions."

            lines.append(f"- **Faithfulness ({avg_faithfulness:.4f})**: {fa_assessment}")
            lines.append(f"- **Answer Relevancy ({avg_relevancy:.4f})**: {ar_assessment}")
            lines.append("")

        lines.append("### Recommendations")
        lines.append("")

        recommendations = []
        rec_num = 1

        if avg_hr < 0.6:
            recommendations.append(f"{rec_num}. Consider increasing `top_k` to retrieve more candidates.")
            rec_num += 1
            recommendations.append(f"{rec_num}. Evaluate embedding model quality for domain-specific content.")
            rec_num += 1
        if avg_mrr < 0.5:
            recommendations.append(f"{rec_num}. Consider adding a reranker to improve ranking.")
            rec_num += 1
            recommendations.append(f"{rec_num}. Review chunking strategy for better context preservation.")
            rec_num += 1
        if avg_ndcg < 0.5:
            recommendations.append(f"{rec_num}. Consider hybrid retrieval (BM25 + vector search).")
            rec_num += 1

        if result.generation_metrics:
            avg_faithfulness = result.generation_metrics.get("avg_faithfulness", 0)
            avg_relevancy = result.generation_metrics.get("avg_answer_relevancy", 0)

            if avg_faithfulness < 0.6:
                recommendations.append(f"{rec_num}. Review prompt engineering to reduce hallucinations.")
                rec_num += 1
                recommendations.append(f"{rec_num}. Ensure retrieved contexts are relevant and complete.")
                rec_num += 1
            if avg_relevancy < 0.6:
                recommendations.append(f"{rec_num}. Improve question understanding in the generation prompt.")
                rec_num += 1
                recommendations.append(f"{rec_num}. Consider answer validation or filtering.")
                rec_num += 1

        if not recommendations:
            recommendations.append(f"{rec_num}. Current performance is satisfactory for baseline.")
            rec_num += 1
            recommendations.append(f"{rec_num}. Consider fine-tuning embedding model for domain-specific improvements.")
            rec_num += 1
            recommendations.append(f"{rec_num}. Explore advanced retrieval strategies for edge cases.")
            rec_num += 1

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

        report_cfg = DEFAULT_REPORT_CONFIG
        try:
            message = self._llm_client.messages.create(
                model=self.llm_model_name or report_cfg["model_name"],
                max_tokens=report_cfg["max_tokens"],
                temperature=report_cfg["temperature"],
                messages=[{"role": "user", "content": prompt}],
            )

            api_input_tokens = getattr(message.usage, "input_tokens", 0) or 0
            api_output_tokens = getattr(message.usage, "output_tokens", 0) or 0

            if self.token_tracker is not None:
                from src.token_tracker import DetailedTokenUsage

                usage = DetailedTokenUsage(
                    input_tokens=api_input_tokens,
                    output_tokens=api_output_tokens,
                    query_tokens=api_input_tokens,
                )
                self.token_tracker.record(
                    category="report_generation",
                    model_name=self.llm_model_name or report_cfg["model_name"],
                    usage=usage,
                )

            return message.content[0].text
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            raise

    def _init_llm_client(self) -> None:
        if not self.llm_api_key:
            raise EvaluationError("LLM API key is required for LLM report generation")

        try:
            from src.utils import create_llm_client

            self._llm_client = create_llm_client(
                llm_config={
                    "api_key": self.llm_api_key,
                    "base_url": self.llm_base_url or DEFAULT_REPORT_CONFIG["base_url"],
                },
                mode="sdk",
            )
            logger.info("LLM client initialized for report generation")
        except ImportError as e:
            raise EvaluationError("anthropic package is required for LLM report generation") from e
        except Exception as e:
            raise EvaluationError(f"Failed to initialize LLM client: {str(e)}") from e

    def _format_llm_report(self, result: ExperimentResult, llm_response: str) -> str:
        header = self._generate_header(result)
        meta_info = [
            f"> Generated with LLM assistance at {datetime.now().isoformat()}",
            "",
        ]
        return "\n".join([header, ""] + meta_info + [llm_response])

    def _build_variant_comparison_llm_prompt(
        self,
        variant_results: list[dict[str, Any]],
        meal_info: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
    ) -> str:
        template_report = self._generate_variant_comparison_template(
            variant_results, meal_info, config_snapshot
        )

        has_generation = any(
            vr.get("generation_metrics") for vr in variant_results
        )

        generation_section = ""
        if has_generation:
            generation_section = """
### 5. 生成质量分析
- 分析各变体的生成质量指标（Faithfulness、Answer Relevancy）
- 对比不同变体之间的生成质量差异
- 识别潜在的幻觉或不相关问题
- 讨论检索质量与生成质量的关系
"""

        prompt = f"""你是一位专业的RAG系统分析师。请根据以下实验数据撰写一份全面的实验报告。

## 实验数据

{template_report}

## 要求

请撰写一份专业的实验报告，包含以下章节：

### 1. 实验概述
- 描述本实验的目的和设置
- 说明正在对比的各变体
- 总结整体发现

### 2. 检索性能分析
- 分析各变体的检索指标（Hit Rate、MRR、NDCG）
- 对比不同变体之间的性能差异
- 识别各配置的优势和不足

### 3. 问题类型分析
- 分析不同问题类型（single_fact、multi_fact、reasoning、comparative、missing、irrelevant）的表现差异
- 识别哪些问题类型更具挑战性
- 讨论性能差异的潜在原因

### 4. 配置影响分析
- 评估不同配置选择的影响
- 讨论分块大小、重叠率等参数如何影响性能
- 提供最优配置选择的见解
{generation_section}
### 结论与建议
- 总结关键发现
- 提出可行的改进建议
- 建议下一步优化方向

报告须以专业、客观的语气撰写，引用具体数据。使用markdown格式以提高可读性。直接以报告正文开头，禁止使用"好的"、"当然"、"我来"等对话性用语开头。
"""
        return prompt

    def _format_variant_comparison_llm_report(
        self,
        variant_results: list[dict[str, Any]],
        llm_response: str,
        meal_info: dict[str, Any] | None = None,
    ) -> str:
        header = self._generate_variant_header(meal_info)
        meta_info = [
            "",
            f"> Generated with LLM assistance at {datetime.now().isoformat()}",
            "",
        ]
        return "\n".join([header] + meta_info + [llm_response])
