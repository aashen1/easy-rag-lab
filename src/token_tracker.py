from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import tiktoken
from loguru import logger


@dataclass
class TokenUsage:
    """Token usage for a single LLM call.

    Args:
        input_tokens: Number of tokens in the input (prompt).
        output_tokens: Number of tokens in the output (completion).

    Returns:
        TokenUsage instance.

    Raises:
        ValueError: If token counts are negative.
    """

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary.

        Returns:
            Dictionary with input_tokens, output_tokens, total_tokens.
        """
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class DetailedTokenUsage(TokenUsage):
    """Token usage with fine-grained input-side breakdown.

    The input_tokens field holds the authoritative total from the API.
    The breakdown fields (system_prompt_tokens, contexts_tokens, query_tokens)
    are estimated via tiktoken and proportionally scaled so their sum equals
    input_tokens.

    Args:
        input_tokens: Total input tokens from API response.
        output_tokens: Total output tokens from API response.
        system_prompt_tokens: Estimated tokens for the system prompt.
        contexts_tokens: Estimated tokens for retrieved context chunks.
        query_tokens: Estimated tokens for the user query portion.

    Returns:
        DetailedTokenUsage instance.
    """

    system_prompt_tokens: int = 0
    contexts_tokens: int = 0
    query_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary.

        Returns:
            Dictionary with all token counts.
        """
        result = super().to_dict()
        result["system_prompt_tokens"] = self.system_prompt_tokens
        result["contexts_tokens"] = self.contexts_tokens
        result["query_tokens"] = self.query_tokens
        return result


@dataclass
class TokenRecord:
    """A single LLM call's complete token record.

    Args:
        category: Call category, e.g. "rag_qa", "test_generation", "report_generation".
        model_name: Name of the LLM model used.
        usage: Detailed token usage for this call.
        timestamp: ISO format timestamp of the call.
        metadata: Additional metadata (question_id, variant_name, etc.).

    Returns:
        TokenRecord instance.
    """

    category: str
    model_name: str
    usage: DetailedTokenUsage
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the record.
        """
        return {
            "category": self.category,
            "model_name": self.model_name,
            "usage": self.usage.to_dict(),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


def estimate_tokens_tiktoken(text: str, encoding_name: str = "cl100k_base") -> int:
    """Estimate token count for a text string using tiktoken.

    Args:
        text: The text to count tokens for.
        encoding_name: The tiktoken encoding name to use.

    Returns:
        Estimated token count.
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"tiktoken estimation failed, falling back to char-based: {str(e)}")
        return max(1, len(text) // 4)


def compute_detailed_usage(
    api_input_tokens: int,
    api_output_tokens: int,
    system_prompt: str,
    contexts: list[str],
    query: str,
    encoding_name: str = "cl100k_base",
) -> DetailedTokenUsage:
    """Compute detailed token usage with proportional scaling.

    Uses tiktoken to estimate the relative proportions of system_prompt,
    contexts, and query, then scales them so the sum equals the API-reported
    input_tokens.

    Args:
        api_input_tokens: Authoritative input token count from API.
        api_output_tokens: Authoritative output token count from API.
        system_prompt: The system prompt text.
        contexts: List of context strings.
        query: The user query text.
        encoding_name: The tiktoken encoding name.

    Returns:
        DetailedTokenUsage with proportionally-scaled breakdown.
    """
    system_prompt_est = estimate_tokens_tiktoken(system_prompt, encoding_name) if system_prompt else 0
    contexts_text = "\n\n".join(contexts) if contexts else ""
    contexts_est = estimate_tokens_tiktoken(contexts_text, encoding_name) if contexts_text else 0
    query_est = estimate_tokens_tiktoken(query, encoding_name) if query else 0

    total_est = system_prompt_est + contexts_est + query_est

    if total_est > 0 and api_input_tokens > 0:
        scale = api_input_tokens / total_est
        system_prompt_scaled = round(system_prompt_est * scale)
        contexts_scaled = round(contexts_est * scale)
        query_scaled = api_input_tokens - system_prompt_scaled - contexts_scaled
        if query_scaled < 0:
            query_scaled = 0
    else:
        system_prompt_scaled = 0
        contexts_scaled = 0
        query_scaled = api_input_tokens

    return DetailedTokenUsage(
        input_tokens=api_input_tokens,
        output_tokens=api_output_tokens,
        system_prompt_tokens=system_prompt_scaled,
        contexts_tokens=contexts_scaled,
        query_tokens=query_scaled,
    )


class TokenTracker:
    """Token usage accumulator for tracking LLM API consumption.

    Records each LLM call's token usage and provides aggregation,
    summarization, and cost estimation capabilities.

    Args:
        None

    Returns:
        TokenTracker instance.

    Raises:
        None
    """

    def __init__(self) -> None:
        self._records: list[TokenRecord] = []

    def record(
        self,
        category: str,
        model_name: str,
        usage: DetailedTokenUsage,
        **metadata: Any,
    ) -> None:
        """Record a single LLM call's token usage.

        Args:
            category: Call category (e.g. "rag_qa", "test_generation").
            model_name: Name of the LLM model.
            usage: Detailed token usage for this call.
            **metadata: Additional metadata to attach to the record.
        """
        rec = TokenRecord(
            category=category,
            model_name=model_name,
            usage=usage,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
        )
        self._records.append(rec)
        logger.debug(
            f"Token tracked: {category} | "
            f"in={usage.input_tokens} out={usage.output_tokens} "
            f"total={usage.total_tokens}"
        )

    def get_summary_by_category(self) -> dict[str, TokenUsage]:
        """Get aggregated token usage grouped by category.

        Returns:
            Dictionary mapping category names to aggregated TokenUsage.
        """
        summary: dict[str, TokenUsage] = {}
        for rec in self._records:
            if rec.category not in summary:
                summary[rec.category] = TokenUsage()
            summary[rec.category] = summary[rec.category] + rec.usage
        return summary

    def get_summary_by_category_detailed(self) -> dict[str, DetailedTokenUsage]:
        """Get aggregated detailed token usage grouped by category.

        Returns:
            Dictionary mapping category names to aggregated DetailedTokenUsage.
        """
        summary: dict[str, DetailedTokenUsage] = {}
        for rec in self._records:
            if rec.category not in summary:
                summary[rec.category] = DetailedTokenUsage()
            existing = summary[rec.category]
            summary[rec.category] = DetailedTokenUsage(
                input_tokens=existing.input_tokens + rec.usage.input_tokens,
                output_tokens=existing.output_tokens + rec.usage.output_tokens,
                system_prompt_tokens=existing.system_prompt_tokens + rec.usage.system_prompt_tokens,
                contexts_tokens=existing.contexts_tokens + rec.usage.contexts_tokens,
                query_tokens=existing.query_tokens + rec.usage.query_tokens,
            )
        return summary

    def get_total(self) -> TokenUsage:
        """Get total token usage across all categories.

        Returns:
            Aggregated TokenUsage for all recorded calls.
        """
        total = TokenUsage()
        for rec in self._records:
            total = total + rec.usage
        return total

    def get_records_by_category(self, category: str) -> list[TokenRecord]:
        """Get all records for a specific category.

        Args:
            category: The category to filter by.

        Returns:
            List of TokenRecord instances matching the category.
        """
        return [r for r in self._records if r.category == category]

    def estimate_cost(
        self, cost_config: dict[str, Any], model_name: str | None = None
    ) -> dict[str, Any]:
        """Estimate cost based on token usage and model pricing.

        Args:
            cost_config: Cost configuration from config.yaml token_cost section.
            model_name: Override model name for cost lookup. If None, uses
                       the model from the first record.

        Returns:
            Dictionary with input_cost, output_cost, total_cost, model, and
            per-category breakdown.
        """
        if not self._records:
            return {
                "input_cost": 0.0,
                "output_cost": 0.0,
                "total_cost": 0.0,
                "model": model_name or "unknown",
                "by_category": {},
            }

        resolved_model = model_name or self._records[0].model_name
        models_config = cost_config.get("models", {})
        model_pricing = models_config.get(resolved_model, {})

        input_price = model_pricing.get("input_price_per_1k", 0.0)
        output_price = model_pricing.get("output_price_per_1k", 0.0)

        total = self.get_total()
        input_cost = total.input_tokens * input_price / 1000
        output_cost = total.output_tokens * output_price / 1000

        by_category = {}
        category_summary = self.get_summary_by_category()
        for cat, usage in category_summary.items():
            cat_input_cost = usage.input_tokens * input_price / 1000
            cat_output_cost = usage.output_tokens * output_price / 1000
            by_category[cat] = {
                "input_cost": round(cat_input_cost, 6),
                "output_cost": round(cat_output_cost, 6),
                "total_cost": round(cat_input_cost + cat_output_cost, 6),
            }

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6),
            "model": resolved_model,
            "by_category": by_category,
        }

    def get_detailed_table(self) -> str:
        """Format token usage as a readable table string.

        Returns:
            Multi-line string with formatted token usage table.
        """
        if not self._records:
            return "No token usage recorded."

        lines = []
        lines.append("=" * 72)
        lines.append("TOKEN USAGE SUMMARY")
        lines.append("=" * 72)
        lines.append(
            f"{'Category':<22} | {'Input':>10} | {'Output':>10} | {'Total':>10}"
        )
        lines.append("-" * 72)

        category_summary = self.get_summary_by_category()
        for cat, usage in category_summary.items():
            lines.append(
                f"{cat:<22} | {usage.input_tokens:>10,} | {usage.output_tokens:>10,} | {usage.total_tokens:>10,}"
            )

        lines.append("-" * 72)
        total = self.get_total()
        lines.append(
            f"{'TOTAL':<22} | {total.input_tokens:>10,} | {total.output_tokens:>10,} | {total.total_tokens:>10,}"
        )

        detailed_summary = self.get_summary_by_category_detailed()
        has_detailed = any(
            v.system_prompt_tokens > 0 or v.contexts_tokens > 0
            for v in detailed_summary.values()
        )
        if has_detailed:
            lines.append("")
            lines.append("Detailed Breakdown (input side):")
            lines.append(
                f"  {'Component':<22} | {'Tokens':>10}"
            )
            lines.append("  " + "-" * 40)
            for cat, usage in detailed_summary.items():
                if usage.system_prompt_tokens > 0 or usage.contexts_tokens > 0:
                    lines.append(f"  {cat + ' - System Prompt':<22} | {usage.system_prompt_tokens:>10,}")
                    lines.append(f"  {cat + ' - Contexts':<22} | {usage.contexts_tokens:>10,}")
                    lines.append(f"  {cat + ' - Query':<22} | {usage.query_tokens:>10,}")

        lines.append("=" * 72)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize tracker state to dictionary.

        Returns:
            Dictionary with total, by_category, by_category_detailed, and records.
        """
        total = self.get_total()
        category_summary = self.get_summary_by_category()
        detailed_summary = self.get_summary_by_category_detailed()

        return {
            "total": total.to_dict(),
            "by_category": {k: v.to_dict() for k, v in category_summary.items()},
            "by_category_detailed": {k: v.to_dict() for k, v in detailed_summary.items()},
            "records": [r.to_dict() for r in self._records],
        }

    def merge(self, other: "TokenTracker") -> None:
        """Merge another tracker's records into this one.

        Args:
            other: Another TokenTracker whose records to merge.
        """
        self._records.extend(other._records)

    @property
    def record_count(self) -> int:
        """Number of recorded LLM calls."""
        return len(self._records)

    def reset(self) -> None:
        """Clear all recorded data."""
        self._records.clear()
