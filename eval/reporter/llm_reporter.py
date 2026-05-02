from datetime import datetime
from typing import Any

from loguru import logger

from eval.reporter.models import ReportExperimentResult
from eval.reporter.template_single import TemplateSingleReporter
from eval.reporter.template_variant import TemplateVariantReporter
from src.exceptions import EvaluationError
from src.llm_retry import call_with_retry
from src.utils import get_env_var

DEFAULT_REPORT_CONFIG = {
    "temperature": 0.3,
    "max_tokens": 4096,
}

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
- **解读 False Positive Rate (FPR)**：
  - FPR measures the proportion of top-k retrieval slots occupied for irrelevant questions
  - FPR near 1.0 is expected for standard vector retrieval (always returns top-k results)
  - FPR = 0.0 means the system correctly returned no results for irrelevant questions (requires explicit rejection mechanism)
  - FPR values based on fewer than 3 irrelevant questions should be interpreted with caution
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


class LLMReporter:
    """LLM-enhanced report generator."""

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

    def generate_llm_report(self, result: ReportExperimentResult) -> str:
        try:
            prompt = self._build_llm_prompt(result)
            llm_response = self._call_llm(prompt)
            return self._format_llm_report(result, llm_response)
        except Exception as e:
            logger.warning(
                f"LLM report generation failed, falling back to template: {str(e)}"
            )
            return self._template_single.generate(result)

    def generate_variant_comparison_llm(
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
            logger.warning(
                f"LLM report generation failed, falling back to template: {str(e)}"
            )
            return self._template_variant.generate(
                variant_results, meal_info, config_snapshot
            )

    def _build_llm_prompt(self, result: ReportExperimentResult) -> str:
        data_section = self._template_single._generate_data_section(result)
        config_section = self._template_single._generate_config_section(result)
        results_section = self._template_single._generate_results_section(result)

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
        resolved_model_name = self.llm_model_name or get_env_var("LLM_MODEL_ID")
        try:
            message = call_with_retry(
                self._llm_client.messages.create,
                model=resolved_model_name,
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
                    model_name=resolved_model_name,
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
                    "base_url": self.llm_base_url or get_env_var("LLM_BASE_URL"),
                },
                mode="sdk",
            )
            logger.info("LLM client initialized for report generation")
        except ImportError as e:
            raise EvaluationError(
                "anthropic package is required for LLM report generation"
            ) from e
        except Exception as e:
            raise EvaluationError(f"Failed to initialize LLM client: {str(e)}") from e

    def _format_llm_report(
        self, result: ReportExperimentResult, llm_response: str
    ) -> str:
        header = self._template_single._generate_header(result)
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
        template_report = self._template_variant.generate(
            variant_results, meal_info, config_snapshot
        )
        lines = template_report.split("\n")
        if lines and lines[0].startswith("# "):
            lines = lines[1:]
            if lines and lines[0] == "":
                lines = lines[1:]
        template_report = "\n".join(lines)

        has_generation = any(vr.get("generation_metrics") for vr in variant_results)

        actual_types = set()
        for vr in variant_results:
            by_type = vr.get("retrieval_metrics", {}).get("by_question_type", {})
            actual_types.update(by_type.keys())
        if not actual_types:
            actual_types = {"unknown"}
        type_list_str = "、".join(sorted(actual_types))

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
- 仅分析数据中实际存在的问题类型（{type_list_str}），不要为不存在的类型编造数据
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
        header = self._template_variant._generate_variant_header(meal_info)
        meta_info = [
            "",
            f"> Generated with LLM assistance at {datetime.now().isoformat()}",
            "",
        ]
        return "\n".join([header] + meta_info + [llm_response])
