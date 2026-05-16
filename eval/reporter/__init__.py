from pathlib import Path
from typing import Any

from loguru import logger

from eval.reporter.formatters import (
    dict_to_yaml_lines,
    generate_tech_summary,
    get_all_generation_metrics,
    get_generation_metric,
    get_generation_metric_description,
    get_metric_description,
)
from eval.reporter.llm_reporter import (
    DEFAULT_REPORT_CONFIG,
    LLM_REPORT_PROMPT_TEMPLATE,
    LLMReporter,
)
from eval.reporter.models import (
    ReportExperimentResult,
    TestCaseResult,
    VariantResult,
)
from eval.reporter.template_single import TemplateSingleReporter
from eval.reporter.template_variant import TemplateVariantReporter

__all__ = [
    "ExperimentReporter",
    "ReportExperimentResult",
    "TestCaseResult",
    "VariantResult",
    "LLM_REPORT_PROMPT_TEMPLATE",
    "DEFAULT_REPORT_CONFIG",
]


class ExperimentReporter:
    """Experiment report generator supporting template and LLM modes.

    Facade that delegates to specialized sub-modules.
    """

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
        self._template_single = TemplateSingleReporter()
        self._template_variant = TemplateVariantReporter()
        self._llm_reporter = LLMReporter(
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model_name=llm_model_name,
            token_tracker=token_tracker,
        )

    def generate_markdown_report(
        self,
        exp_dir: Path,
        result: ReportExperimentResult,
        use_llm: bool = False,
        output_filename: str = "experiment_report.md",
    ) -> str:
        if use_llm:
            report = self._llm_reporter.generate_llm_report(result)
        else:
            report = self._template_single.generate(result)

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
        if use_llm:
            report = self._llm_reporter.generate_variant_comparison_llm(
                variant_results, meal_info, config_snapshot
            )
        else:
            report = self._template_variant.generate(
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

    def _generate_template_report(self, result: ReportExperimentResult) -> str:
        return self._template_single.generate(result)

    def _generate_llm_report(self, result: ReportExperimentResult) -> str:
        return self._llm_reporter.generate_llm_report(result)

    def _call_llm(self, prompt: str) -> str:
        return self._llm_reporter._call_llm(prompt)

    def _generate_variant_comparison_template(
        self,
        variant_results: list[dict[str, Any]],
        meal_info: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
    ) -> str:
        return self._template_variant.generate(
            variant_results, meal_info, config_snapshot
        )

    def _generate_variant_comparison_llm(
        self,
        variant_results: list[dict[str, Any]],
        meal_info: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
    ) -> str:
        return self._llm_reporter.generate_variant_comparison_llm(
            variant_results, meal_info, config_snapshot
        )
