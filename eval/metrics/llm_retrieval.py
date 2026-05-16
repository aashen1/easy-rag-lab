import re
from typing import Any

from loguru import logger

from eval.metrics.utils import (
    DEFAULT_EVAL_BASE_CONFIG,
    get_eval_config,
    llm_judge,
)
from src.utils import create_llm_client

DEFAULT_EVAL_CONFIG = {
    **DEFAULT_EVAL_BASE_CONFIG,
    "context_precision": {"temperature": 0.0, "max_tokens": 256},
    "context_recall": {"temperature": 0.0, "max_tokens": 256},
    "context_relevance": {"temperature": 0.0, "max_tokens": 256},
    "infer_check": {"temperature": 0.0, "max_tokens": 64},
}


CONTEXT_PRECISION_PROMPT = """你是一个专业的信息检索评估专家。请判断以下检索到的上下文是否与问题相关。

【问题】
{question}

【期望答案】
{expected_output}

【检索上下文】
{context}

请判断这个上下文是否包含回答问题所需的关键信息。
只回答"是"或"否"，并简要说明理由。

请以JSON格式输出：
{{"verdict": "是"或"否", "reason": "简要理由"}}

只输出JSON，不要其他内容。"""


CONTEXT_RECALL_SENTENCE_PROMPT = """请判断以下陈述是否可以从给定的上下文中推断出来。

【上下文】
{context}

【陈述】
{sentence}

请判断这个陈述是否可以从上下文中直接推导或合理推断出来。
只回答"是"或"否"。

请以JSON格式输出：
{{"verdict": "是"或"否"}}"""


def judge_context_relevance(
    question: str,
    expected_output: str,
    context: str,
    api_key: str,
    base_url: str,
    model_name: str,
) -> bool:
    """Judge if a context is relevant to the question using LLM.

    Args:
        question: The user's question.
        expected_output: The expected answer (ground truth).
        context: A single context string to evaluate.
        api_key: API key for LLM.
        base_url: Base URL for LLM API.
        model_name: LLM model name.

    Returns:
        True if context is relevant, False otherwise.

    Raises:
        Exception: If LLM call fails.
    """
    client = create_llm_client(
        llm_config={"api_key": api_key, "base_url": base_url, "model_name": ""},
        mode="sdk",
    )

    prompt = CONTEXT_PRECISION_PROMPT.format(
        question=question,
        expected_output=expected_output,
        context=context,
    )

    try:
        result = llm_judge(
            client=client,
            prompt=prompt,
            model_name=model_name,
            max_tokens=256,
            temperature=0.0,
        )

        if result:
            verdict = result.get("verdict", "否")
            return verdict.strip() == "是"

        return False

    except Exception as e:
        logger.warning(f"Failed to judge context relevance: {str(e)}")
        return False


def calculate_context_precision(
    question: str,
    expected_output: str,
    retrieval_context: list[str],
    api_key: str,
    base_url: str = None,
    model_name: str = None,
    config: dict[str, Any] = None,
) -> float:
    """Calculate Context Precision using LLM-as-a-judge.

    This metric measures how accurately the retrieval system ranks relevant
    contexts higher than irrelevant ones. It uses the Weighted Cumulative
    Precision (WCP) formula from DeepEval:

    Context Precision = (1/N) × Σ(Precision@k × r_k)

    Where:
    - N = number of relevant nodes
    - Precision@k = (relevant nodes up to position k) / k
    - r_k = 1 if node k is relevant, 0 otherwise

    Args:
        question: The user's question.
        expected_output: The expected answer (ground truth).
        retrieval_context: List of retrieved context strings, ordered by relevance.
        api_key: API key for LLM.
        base_url: Base URL for LLM API.
            Defaults to config value or LLM_BASE_URL env var.
        model_name: LLM model name.
            Defaults to config value or LLM_MODEL_ID env var.
        config: Optional config dict with 'llm_evaluator' section.

    Returns:
        Context precision score in [0, 1]. Higher is better.

    Raises:
        ValueError: If retrieval_context is empty.

    Example:
        >>> contexts = ["doc1 content", "doc2 content", "doc3 content"]
        >>> score = calculate_context_precision(
        ...     question="What is the revenue?",
        ...     expected_output="Revenue is $1M",
        ...     retrieval_context=contexts,
        ...     api_key="your-api-key"
        ... )
    """
    if not retrieval_context:
        logger.warning("Empty retrieval context for context precision calculation")
        return 0.0

    eval_cfg = get_eval_config(config, DEFAULT_EVAL_CONFIG)
    base_url = base_url or eval_cfg.get("base_url")
    model_name = model_name or eval_cfg.get("model_name")

    relevance_verdicts = []
    for ctx in retrieval_context:
        verdict = judge_context_relevance(
            question, expected_output, ctx, api_key, base_url, model_name
        )
        relevance_verdicts.append(verdict)

    relevant_count = sum(relevance_verdicts)
    if relevant_count == 0:
        return 0.0

    wcp_sum = 0.0
    relevant_up_to_k = 0

    for k, is_relevant in enumerate(relevance_verdicts, 1):
        if is_relevant:
            relevant_up_to_k += 1
            precision_at_k = relevant_up_to_k / k
            wcp_sum += precision_at_k

    score = wcp_sum / relevant_count

    logger.success(
        f"Context precision: {score:.4f} "
        f"({relevant_count}/{len(retrieval_context)} relevant contexts)"
    )

    return score


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, handling Markdown tables.

    For Markdown tables (detected by | and ---), splits by newlines
    to preserve table row structure. For regular text, splits by
    punctuation marks.

    Args:
        text: Text to split.

    Returns:
        List of sentences or table rows.
    """
    if "|" in text and re.search(r"\|[-]+\|", text):
        lines = text.split("\n")
        sentences = []
        for line in lines:
            line = line.strip()
            if line and not re.match(r"^\|[-]+\|", line):
                sentences.append(line)
        return sentences

    sentences = re.split(r"[。！？.!?]", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def can_infer_from_context(
    sentence: str,
    context: str,
    api_key: str,
    base_url: str,
    model_name: str,
) -> bool:
    """Check if a sentence can be inferred from context using LLM.

    Args:
        sentence: The sentence to check.
        context: The context to check against.
        api_key: API key for LLM.
        base_url: Base URL for LLM API.
        model_name: LLM model name.

    Returns:
        True if sentence can be inferred from context.

    Raises:
        Exception: If LLM call fails.
    """
    client = create_llm_client(
        llm_config={"api_key": api_key, "base_url": base_url, "model_name": ""},
        mode="sdk",
    )

    prompt = CONTEXT_RECALL_SENTENCE_PROMPT.format(
        context=context,
        sentence=sentence,
    )

    try:
        result = llm_judge(
            client=client,
            prompt=prompt,
            model_name=model_name,
            max_tokens=64,
            temperature=0.0,
        )

        if result:
            verdict = result.get("verdict", "否")
            return verdict.strip() == "是"

        return False

    except Exception as e:
        logger.warning(f"Failed to check sentence inference: {str(e)}")
        return False


def calculate_context_recall(
    question: str,
    ground_truth: str,
    retrieval_context: list[str],
    api_key: str,
    base_url: str = None,
    model_name: str = None,
    config: dict[str, Any] = None,
) -> float:
    """Calculate Context Recall.

    This metric measures how much of the ground truth can be inferred from
    the retrieved context. It follows the RAGAS approach:

    1. Split ground truth into sentences
    2. For each sentence, check if it can be inferred from the context
    3. Calculate: (inferable sentences) / (total sentences)

    Args:
        question: The user's question (used for context).
        ground_truth: The expected answer (ground truth).
        retrieval_context: List of retrieved context strings.
        api_key: API key for LLM.
        base_url: Base URL for LLM API.
            Defaults to config value or LLM_BASE_URL env var.
        model_name: LLM model name.
            Defaults to config value or LLM_MODEL_ID env var.
        config: Optional config dict with 'llm_evaluator' section.

    Returns:
        Context recall score in [0, 1]. Higher is better.

    Raises:
        ValueError: If ground_truth is empty.

    Example:
        >>> contexts = ["Revenue was $1M in 2023"]
        >>> score = calculate_context_recall(
        ...     question="What is the revenue?",
        ...     ground_truth="The revenue was $1 million in 2023.",
        ...     retrieval_context=contexts,
        ...     api_key="your-api-key"
        ... )
    """
    if not ground_truth:
        logger.warning("Empty ground truth for context recall calculation")
        return 0.0

    if not retrieval_context:
        logger.warning("Empty retrieval context for context recall calculation")
        return 0.0

    eval_cfg = get_eval_config(config, DEFAULT_EVAL_CONFIG)
    base_url = base_url or eval_cfg.get("base_url")
    model_name = model_name or eval_cfg.get("model_name")

    sentences = split_into_sentences(ground_truth)
    if not sentences:
        logger.warning("No sentences extracted from ground truth")
        return 0.0

    context_text = "\n\n".join(retrieval_context)
    inferable_count = 0
    sentence_verdicts = []

    for sentence in sentences:
        can_infer = can_infer_from_context(
            sentence, context_text, api_key, base_url, model_name
        )
        if can_infer:
            inferable_count += 1
        sentence_verdicts.append((sentence[:80], can_infer))

    score = inferable_count / len(sentences)

    if score == 0.0:
        logger.warning(
            f"Context recall is 0.0 — no sentences inferable from context. "
            f"Ground truth: {ground_truth[:200]}, "
            f"Sentences: {sentence_verdicts}, "
            f"Context preview: {context_text[:200]}"
        )

    logger.success(
        f"Context recall: {score:.4f} "
        f"({inferable_count}/{len(sentences)} sentences inferable)"
    )

    return score
