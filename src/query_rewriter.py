from typing import Any

from loguru import logger

from src.exceptions import ConfigurationError, GenerationError
from src.token_tracker import DetailedTokenUsage, TokenTracker


class QueryRewriter:
    def __init__(
        self,
        strategy: str = "hyde",
        llm_model_name: str = "",
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_temperature: float = 0.0,
        llm_max_tokens: int = 512,
        num_queries: int = 3,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        """Initialize the QueryRewriter with a specified strategy.

        Supports two query rewriting strategies:

        - **HyDE (Hypothetical Document Embeddings)**: Generates a
          hypothetical answer to the query, then uses that answer's
          embedding for retrieval. Bridges the semantic gap between
          short queries and long documents.

        - **Multi-Query**: Rewrites the original query into multiple
          diverse sub-queries, retrieves for each, and merges results.
          Increases recall by covering different aspects of the query.

        Args:
            strategy: Rewriting strategy, either ``"hyde"`` or ``"multi_query"``.
                Defaults to ``"hyde"``.
            llm_model_name: Model name for the LLM API.
            llm_api_key: API key for the LLM.
            llm_base_url: Base URL for the LLM API.
            llm_temperature: Sampling temperature for generation. Defaults to 0.0.
            llm_max_tokens: Maximum tokens for LLM response. Defaults to 512.
            num_queries: Number of sub-queries for Multi-Query strategy.
                Defaults to 3.
            token_tracker: Optional TokenTracker for recording LLM usage.

        Raises:
            ValueError: If strategy is not ``"hyde"`` or ``"multi_query"``.
        """
        if strategy not in ("hyde", "multi_query"):
            raise ConfigurationError(
                f"strategy must be 'hyde' or 'multi_query', got '{strategy}'"
            )

        self.strategy = strategy
        self.llm_model_name = llm_model_name
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_temperature = llm_temperature
        self.llm_max_tokens = llm_max_tokens
        self.num_queries = num_queries
        self.token_tracker = token_tracker

        self._client = None

    def _get_client(self):
        """Lazy-initialize the Anthropic client.

        Returns:
            Anthropic client instance.
        """
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.llm_api_key, base_url=self.llm_base_url)
        return self._client

    def rewrite(self, query: str) -> dict[str, Any]:
        """Rewrite the query using the configured strategy.

        Args:
            query: The original user query. Must be non-empty.

        Returns:
            A dictionary with:
            - ``strategy``: The rewriting strategy used.
            - ``original_query``: The original query.
            - ``rewritten``: For HyDE, the hypothetical answer text.
              For Multi-Query, a list of sub-query strings.
            - ``token_usage``: Token usage for the LLM call (if tracked).

        Raises:
            ValueError: If ``query`` is empty or not a string.
            Exception: If the LLM call fails.
        """
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise GenerationError(error_msg)

        try:
            if self.strategy == "hyde":
                return self._hyde_rewrite(query)
            else:
                return self._multi_query_rewrite(query)
        except Exception as e:
            error_msg = f"Failed to rewrite query: {str(e)}"
            logger.error(error_msg)
            raise GenerationError(error_msg) from e

    def _hyde_rewrite(self, query: str) -> dict[str, Any]:
        """Generate a hypothetical answer for HyDE retrieval.

        The hypothetical answer serves as a proxy document that
        bridges the semantic gap between the short query and the
        actual documents in the corpus.

        Args:
            query: The original user query.

        Returns:
            Dictionary with ``strategy``, ``original_query``, ``rewritten``,
            and ``token_usage`` keys.
        """
        logger.info(f"HyDE rewriting query: {query[:50]}...")

        prompt = (
            "请写一段详细的回答来回应以下问题。即使你不确定答案，"
            "也请根据你的知识给出一个合理的、详细的回答。"
            "回答应该像一篇专业的研究报告片段。\n\n"
            f"问题：{query}\n\n"
            "回答："
        )

        response_text, token_usage = self._call_llm(prompt)

        result = {
            "strategy": "hyde",
            "original_query": query,
            "rewritten": response_text,
        }

        if token_usage is not None:
            result["token_usage"] = token_usage

        logger.success(f"HyDE rewrite completed: {len(response_text)} chars")
        return result

    def _multi_query_rewrite(self, query: str) -> dict[str, Any]:
        """Generate multiple diverse sub-queries for Multi-Query retrieval.

        Each sub-query approaches the original question from a different
        angle, increasing the chance of retrieving relevant documents.

        Args:
            query: The original user query.

        Returns:
            Dictionary with ``strategy``, ``original_query``, ``rewritten``
            (list of sub-queries), and ``token_usage`` keys.
        """
        logger.info(f"Multi-Query rewriting: {query[:50]}...")

        prompt = (
            f"你是一个查询改写助手。请将以下问题改写为{self.num_queries}个不同角度的子问题。"
            "每个子问题应该从不同的视角或关键词切入，但都指向同一个核心问题。"
            "请每行输出一个子问题，不要编号，不要其他说明。\n\n"
            f"原始问题：{query}\n\n"
            f"改写后的{self.num_queries}个子问题："
        )

        response_text, token_usage = self._call_llm(prompt)

        sub_queries = [
            line.strip()
            for line in response_text.strip().split("\n")
            if line.strip()
        ]

        sub_queries = [q.lstrip("0123456789.-) ") for q in sub_queries]

        sub_queries = sub_queries[: self.num_queries]

        result = {
            "strategy": "multi_query",
            "original_query": query,
            "rewritten": sub_queries,
        }

        if token_usage is not None:
            result["token_usage"] = token_usage

        logger.success(f"Multi-Query rewrite: {len(sub_queries)} sub-queries generated")
        return result

    def _call_llm(self, prompt: str) -> tuple:
        """Call the LLM API with the given prompt.

        Args:
            prompt: The prompt string to send to the LLM.

        Returns:
            Tuple of (response_text, token_usage_dict_or_None).
        """
        try:
            client = self._get_client()

            message = client.messages.create(
                model=self.llm_model_name,
                max_tokens=self.llm_max_tokens,
                temperature=self.llm_temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text

            token_usage = None
            if self.token_tracker is not None and hasattr(message, "usage"):
                detailed = DetailedTokenUsage(
                    input_tokens=message.usage.input_tokens,
                    output_tokens=message.usage.output_tokens,
                )
                self.token_tracker.record(
                    category="query_rewrite",
                    model_name=self.llm_model_name,
                    usage=detailed,
                )
                token_usage = detailed.to_dict()

            return response_text, token_usage

        except Exception as e:
            error_msg = f"LLM call failed: {str(e)}"
            logger.error(error_msg)
            raise GenerationError(error_msg) from e


if __name__ == "__main__":
    from src.utils import get_env_var, load_config, setup_logger

    config = load_config()
    setup_logger(config)

    llm_config = config["llm_presets"]["default"]

    rewriter = QueryRewriter(
        strategy="hyde",
        llm_model_name=llm_config["model_name"],
        llm_api_key=get_env_var(llm_config["api_key"]),
        llm_base_url=get_env_var(llm_config["base_url"]),
    )

    query = "贵州茅台2023年的营业收入是多少？"
    result = rewriter.rewrite(query)

    logger.info(f"Strategy: {result['strategy']}")
    logger.info(f"Original: {result['original_query']}")
    logger.info(f"Rewritten: {result['rewritten'][:200]}...")
