from pathlib import Path
from typing import Any

from loguru import logger

from src.llm_client import create_anthropic_client
from src.token_tracker import (
    DetailedTokenUsage,
    TokenTracker,
    compute_detailed_usage,
)


class Generator:
    """LLM answer generator with token usage tracking.

    Args:
        model_name: Name of the LLM model.
        api_key: API key for authentication.
        base_url: Base URL for the API endpoint.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in the response.
        token_tracker: Optional TokenTracker for recording usage.
        system_prompt: Optional default system prompt. When None, the
            hardcoded default is used as the final fallback in generate().

    Returns:
        Generator instance.

    Raises:
        Exception: If Anthropic client initialization fails.
    """

    DEFAULT_SYSTEM_PROMPT = """你是一个金融研报分析助手。请基于以下参考资料回答用户问题。

要求：
1. 回答要准确、简洁、专业
2. 如果参考资料中有相关信息，请基于资料回答
3. 如果参考资料中没有相关信息，请明确说明"根据提供的参考资料，我无法回答这个问题"
4. 回答时请引用具体的来源（如"根据贵州茅台2023年年度报告..."）
5. 直接以回答内容开头，禁止使用"好的"、"当然"、"我来"等对话性用语开头"""

    def __init__(
        self,
        model_name: str = "LongCat-Flash-Lite",
        api_key: str = None,
        base_url: str = "https://api.longcat.chat/anthropic",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        token_tracker: TokenTracker | None = None,
        system_prompt: str | None = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.token_tracker = token_tracker
        self.default_system_prompt = system_prompt
        self.last_token_usage: DetailedTokenUsage | None = None

        try:
            logger.info("Initializing Anthropic client")

            self.client = create_anthropic_client(
                api_key=api_key,
                base_url=base_url,
            )

            logger.success("Anthropic client initialized successfully")

        except Exception as e:
            error_msg = f"Failed to initialize Anthropic client: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def generate(
        self,
        query: str,
        contexts: list[str],
        system_prompt: str = None,
        category: str = "rag_qa",
        sources: list[str] | None = None,
        **metadata: Any,
    ) -> str:
        """Generate an answer using the LLM.

        Args:
            query: The user's question.
            contexts: List of retrieved context strings.
            system_prompt: Optional system prompt override. When None,
                falls back to self.default_system_prompt, then to the
                hardcoded DEFAULT_SYSTEM_PROMPT.
            category: Token tracking category (default "rag_qa").
            sources: Optional list of source document paths, one per
                context. When provided, each context is annotated with
                its source name (filename stem) so the LLM can cite
                sources. When None or empty, the old format without
                source names is used for backward compatibility.
            **metadata: Additional metadata for token tracking.

        Returns:
            Generated answer string.

        Raises:
            ValueError: If query is empty or not a string.
            Exception: If LLM call fails.
        """
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not contexts:
            logger.warning("No contexts provided for generation")

        try:
            if system_prompt is None:
                system_prompt = self.default_system_prompt
            if system_prompt is None:
                system_prompt = self.DEFAULT_SYSTEM_PROMPT

            if sources:
                context_text = "\n\n".join(
                    [
                        f"参考资料 {i+1}（来源：{Path(sources[i]).stem if i < len(sources) else '未知'}）:\n{ctx}"
                        for i, ctx in enumerate(contexts)
                    ]
                )
            else:
                context_text = "\n\n".join(
                    [f"参考资料 {i+1}:\n{ctx}" for i, ctx in enumerate(contexts)]
                )

            user_message = f"""{context_text}

用户问题：{query}

请基于参考资料回答上述问题："""

            logger.info(f"Generating answer for query: {query[:50]}...")

            message = self.client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ],
            )

            answer = message.content[0].text

            api_input_tokens = getattr(message.usage, "input_tokens", 0) or 0
            api_output_tokens = getattr(message.usage, "output_tokens", 0) or 0

            detailed_usage = compute_detailed_usage(
                api_input_tokens=api_input_tokens,
                api_output_tokens=api_output_tokens,
                system_prompt=system_prompt,
                contexts=contexts,
                query=query,
            )
            self.last_token_usage = detailed_usage

            if self.token_tracker is not None:
                self.token_tracker.record(
                    category=category,
                    model_name=self.model_name,
                    usage=detailed_usage,
                    **metadata,
                )

            logger.success(
                f"Generated answer: {answer[:100]}... "
                f"(tokens: in={api_input_tokens}, out={api_output_tokens})"
            )
            return answer

        except Exception as e:
            error_msg = f"Failed to generate answer: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)


if __name__ == "__main__":
    from src.utils import get_llm_config, load_config, setup_logger

    config = load_config()
    setup_logger(config)

    llm_config = get_llm_config(config)

    generator = Generator(
        model_name=llm_config["model_name"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=llm_config["temperature"],
        max_tokens=llm_config["max_tokens"],
    )

    query = "贵州茅台2023年的营业收入是多少？"
    contexts = [
        "贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元，同比增长18.04%。",
        "贵州茅台2023年归属于上市公司股东的净利润为747.34亿元，同比增长19.14%。",
    ]

    answer = generator.generate(query, contexts)
    logger.info(f"\nAnswer:\n{answer}")
