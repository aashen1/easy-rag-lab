import json
import re
from typing import Any

from anthropic import Anthropic
from loguru import logger

from eval.metrics.utils import (
    DEFAULT_EVAL_BASE_CONFIG,
    create_llm_client,
    get_eval_config,
)
from src.exceptions import EvaluationError

DEFAULT_EVAL_CONFIG = {
    **DEFAULT_EVAL_BASE_CONFIG,
    "extract_statements": {"temperature": 0.0, "max_tokens": 1024},
    "verify_statements": {"temperature": 0.0, "max_tokens": 1024},
    "faithfulness": {"temperature": 0.0, "max_tokens": 512},
    "answer_relevancy": {"temperature": 0.0, "max_tokens": 512},
}


FAITHFULNESS_STATEMENT_PROMPT = """请分析以下回答，提取其中的所有事实陈述（statements）。

回答：
{answer}

要求：
1. 将回答拆分为独立的事实陈述，每个陈述应该是一个可以独立验证的命题
2. 忽略问候语、过渡语等非事实性内容
3. 每个陈述一行，编号从1开始

请以JSON格式输出，格式如下：
{{"statements": ["陈述1", "陈述2", ...]}}

只输出JSON，不要其他内容。"""


FAITHFULNESS_VERIFICATION_PROMPT = """请判断以下陈述是否可以从给定的上下文中推导出来。

上下文：
{contexts}

陈述：
{statements}

要求：
1. 对每个陈述，判断它是否可以从上下文中直接推导或合理推断
2. 如果陈述中的信息在上下文中明确存在或可以合理推断，标记为"是"
3. 如果陈述中的信息在上下文中不存在或与上下文矛盾，标记为"否"

请以JSON格式输出，格式如下：
{{"verdict": [{{"statement": "陈述内容", "verdict": 1或0}}]}}

其中verdict为1表示可以从上下文推导，0表示不能。
只输出JSON，不要其他内容。"""


ANSWER_RELEVANCY_PROMPT = """你是一个专业的问答系统评估专家。请评估以下回答与问题的相关性。

【问题】
{question}

【回答】
{answer}

请从以下三个维度评估回答的相关性，每个维度给出1-5分的评分：

1. 直接相关性：回答是否直接针对问题，是否切题
   - 1分：完全无关，答非所问
   - 2分：相关性低，只有少量内容与问题相关
   - 3分：部分相关，但存在偏题或不够聚焦的情况
   - 4分：相关性高，大部分内容切题
   - 5分：完全切题，回答直接针对问题核心

2. 信息充分性：回答是否提供了足够的信息来解答问题
   - 1分：信息严重不足，无法回答问题
   - 2分：信息较少，只能部分回答问题
   - 3分：信息基本足够，但可以更详细
   - 4分：信息充分，较好地回答了问题
   - 5分：信息完整详尽，完美回答问题

3. 简洁聚焦性：回答是否避免了无关信息，是否简洁
   - 1分：大量无关信息，严重冗余
   - 2分：存在较多无关内容或冗余
   - 3分：基本聚焦，有少量无关内容
   - 4分：较为简洁，无关内容很少
   - 5分：非常简洁，无任何无关信息

请以JSON格式返回评估结果，格式如下：
{{
    "direct_relevance": <1-5的整数>,
    "information_sufficiency": <1-5的整数>,
    "conciseness": <1-5的整数>,
    "overall_score": <0.0-1.0的浮点数，综合相关性得分>,
    "reasoning": "<简要说明评分理由>"
}}

注意：
- overall_score 应该是三个维度的综合评分，转换为0.0-1.0的范围
- 只返回JSON，不要有其他内容"""


def extract_statements(
    client: Anthropic,
    answer: str,
    model_name: str = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> list[str]:
    """Extract factual statements from an answer using LLM.

    Args:
        client: Anthropic client instance.
        answer: The answer text to extract statements from.
        model_name: Name of the LLM model to use.
        max_tokens: Maximum tokens in the LLM response.
        temperature: Sampling temperature for LLM generation.

    Returns:
        List of extracted statement strings.

    Raises:
        Exception: If LLM call fails or response parsing fails.
    """
    prompt = FAITHFULNESS_STATEMENT_PROMPT.format(answer=answer)

    try:
        message = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("statements", [])

        logger.warning(f"Could not parse JSON from response: {response_text[:100]}")
        return []

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        return []
    except Exception as e:
        error_msg = f"Failed to extract statements: {str(e)}"
        logger.error(error_msg)
        raise EvaluationError(error_msg) from e


def calculate_hallucination_rate(
    faithfulness_scores: list[float],
    threshold: float = 0.5,
) -> float:
    """Calculate hallucination rate from faithfulness scores.

    Measures the fraction of questions whose faithfulness score falls
    below the given threshold, indicating potential hallucination.

    Args:
        faithfulness_scores: List of faithfulness scores per question.
        threshold: Hallucination detection threshold. Scores below this
            value are considered hallucinated. Defaults to 0.5.

    Returns:
        Hallucination rate as a float between 0.0 and 1.0.
    """
    if not faithfulness_scores:
        return 0.0
    valid_scores = [s for s in faithfulness_scores if s is not None]
    if not valid_scores:
        return 0.0
    hallucinated = sum(1 for s in valid_scores if s < threshold)
    return hallucinated / len(valid_scores)


def verify_statements(
    client: Anthropic,
    statements: list[str],
    contexts: list[str],
    model_name: str = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> list[dict[str, Any]]:
    """Verify if statements can be derived from contexts using LLM.

    Args:
        client: Anthropic client instance.
        statements: List of statement strings to verify.
        contexts: List of context strings to verify against.
        model_name: Name of the LLM model to use.
        max_tokens: Maximum tokens in the LLM response.
        temperature: Sampling temperature for LLM generation.

    Returns:
        List of dicts with statement and verdict (1 for derivable, 0 for not).

    Raises:
        Exception: If LLM call fails or response parsing fails.
    """
    context_text = "\n\n".join(
        [f"上下文 {i + 1}:\n{ctx}" for i, ctx in enumerate(contexts)]
    )
    statements_text = "\n".join([f"{i + 1}. {s}" for i, s in enumerate(statements)])

    prompt = FAITHFULNESS_VERIFICATION_PROMPT.format(
        contexts=context_text,
        statements=statements_text,
    )

    try:
        message = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("verdict", [])

        logger.warning(f"Could not parse JSON from response: {response_text[:100]}")
        return []

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        return []
    except Exception as e:
        error_msg = f"Failed to verify statements: {str(e)}"
        logger.error(error_msg)
        raise EvaluationError(error_msg) from e


def calculate_faithfulness(
    answer: str,
    contexts: list[str],
    api_key: str,
    base_url: str = None,
    model_name: str = None,
    config: dict[str, Any] = None,
) -> float:
    """Calculate faithfulness score for an answer given contexts.

    Faithfulness measures how well the answer is grounded in the retrieved
    contexts. A high faithfulness score indicates that the answer contains
    information that can be derived from the contexts, while a low score
    suggests the answer contains hallucinations or unsupported claims.

    The calculation follows these steps:
    1. Extract all factual statements from the answer
    2. Verify each statement against the contexts
    3. Calculate the ratio of supported statements to total statements

    Args:
        answer: The generated answer text to evaluate.
        contexts: List of context strings retrieved for the query.
        api_key: API key for LLM authentication.
        base_url: Base URL for the LLM API endpoint.
            Defaults to config value or LLM_BASE_URL env var.
        model_name: Name of the LLM model to use for evaluation.
            Defaults to config value or LLM_MODEL_ID env var.
        config: Optional config dict with 'llm_evaluator' section.

    Returns:
        Faithfulness score as a float between 0.0 and 1.0:
        - 1.0 indicates all statements are supported by contexts
        - 0.0 indicates no statements are supported (or no statements found)
        - Intermediate values indicate partial support

    Raises:
        ValueError: If answer is empty or not a string.
        Exception: If LLM client creation or API calls fail.

    Example:
        >>> answer = "贵州茅台2023年营业收入为1505.60亿元。"
        >>> contexts = ["贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元。"]
        >>> score = calculate_faithfulness(answer, contexts, api_key="...")
        >>> print(score)
        1.0
    """
    if not answer or not isinstance(answer, str):
        error_msg = "Answer must be a non-empty string"
        logger.error(error_msg)
        raise EvaluationError(error_msg)

    if not contexts:
        logger.warning("No contexts provided for faithfulness evaluation")
        return 0.0

    answer = answer.strip()
    if not answer:
        logger.warning("Answer is empty after stripping whitespace")
        return 0.0

    eval_cfg = get_eval_config(config, DEFAULT_EVAL_CONFIG)
    base_url = base_url or eval_cfg.get("base_url")
    model_name = model_name or eval_cfg.get("model_name")

    extract_cfg = eval_cfg.get(
        "extract_statements", DEFAULT_EVAL_CONFIG["extract_statements"]
    )
    verify_cfg = eval_cfg.get(
        "verify_statements", DEFAULT_EVAL_CONFIG["verify_statements"]
    )

    try:
        client = create_llm_client(api_key=api_key, base_url=base_url)

        logger.info("Extracting statements from answer")
        statements = extract_statements(
            client,
            answer,
            model_name,
            max_tokens=extract_cfg.get("max_tokens", 1024),
            temperature=extract_cfg.get("temperature", 0.0),
        )

        if not statements:
            logger.warning("No statements extracted from answer")
            return 0.0

        logger.info(
            f"Extracted {len(statements)} statements, verifying against contexts"
        )
        verdicts = verify_statements(
            client,
            statements,
            contexts,
            model_name,
            max_tokens=verify_cfg.get("max_tokens", 1024),
            temperature=verify_cfg.get("temperature", 0.0),
        )

        if not verdicts:
            logger.warning("No verdicts returned from verification")
            return 0.0

        supported_count = sum(1 for v in verdicts if v.get("verdict", 0) == 1)
        total_count = len(verdicts)

        if total_count == 0:
            return 0.0

        faithfulness_score = supported_count / total_count
        logger.success(
            f"Faithfulness calculated: {faithfulness_score:.2f} "
            f"({supported_count}/{total_count} statements supported)"
        )

        return faithfulness_score

    except Exception as e:
        error_msg = f"Failed to calculate faithfulness: {str(e)}"
        logger.error(error_msg)
        raise EvaluationError(error_msg) from e


def parse_relevancy_response(response_text: str) -> dict[str, Any]:
    """Parse LLM response for answer relevancy evaluation.

    Args:
        response_text: Raw text response from LLM.

    Returns:
        Parsed dictionary with relevancy scores.

    Raises:
        ValueError: If response cannot be parsed as JSON.
    """
    json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        raise EvaluationError(f"Failed to parse LLM response as JSON: {e}") from e


def calculate_answer_relevancy(
    question: str,
    answer: str,
    api_key: str,
    base_url: str = None,
    model_name: str = None,
    max_tokens: int = None,
    temperature: float = None,
    config: dict[str, Any] = None,
) -> float:
    """Calculate answer relevancy score using LLM evaluation.

    This function evaluates how relevant an answer is to a given question
    using a multi-dimensional LLM-based assessment. The evaluation considers:
    - Direct relevance: Does the answer directly address the question?
    - Information sufficiency: Does the answer provide enough information?
    - Conciseness: Does the answer avoid irrelevant information?

    Args:
        question: The user's question.
        answer: The generated answer to evaluate.
        api_key: API key for LLM authentication.
        base_url: Base URL for the LLM API endpoint.
            Defaults to config value or LLM_BASE_URL env var.
        model_name: Name of the LLM model to use.
            Defaults to config value or LLM_MODEL_ID env var.
        max_tokens: Maximum tokens in the LLM response.
            Defaults to config value or 512.
        temperature: Sampling temperature for LLM generation.
            Defaults to config value or 0.0.
        config: Optional config dict with 'llm_evaluator' section.

    Returns:
        Relevancy score as a float between 0.0 and 1.0:
        - 1.0: Perfectly relevant answer
        - 0.5: Moderately relevant answer
        - 0.0: Completely irrelevant answer

    Raises:
        ValueError: If question or answer is empty.
        Exception: If LLM call fails or response cannot be parsed.

    Example:
        >>> score = calculate_answer_relevancy(
        ...     question="贵州茅台2023年营收是多少？",
        ...     answer="贵州茅台2023年实现营业收入1505.60亿元。",
        ...     api_key="your-api-key"
        ... )
        >>> print(f"Relevancy: {score:.2f}")
    """
    if not question or not isinstance(question, str):
        raise EvaluationError("Question must be a non-empty string")
    if not answer or not isinstance(answer, str):
        raise EvaluationError("Answer must be a non-empty string")

    eval_cfg = get_eval_config(config, DEFAULT_EVAL_CONFIG)
    base_url = base_url or eval_cfg.get("base_url")
    model_name = model_name or eval_cfg.get("model_name")
    relevancy_cfg = eval_cfg.get(
        "answer_relevancy", DEFAULT_EVAL_CONFIG["answer_relevancy"]
    )
    max_tokens = (
        max_tokens if max_tokens is not None else relevancy_cfg.get("max_tokens", 512)
    )
    temperature = (
        temperature
        if temperature is not None
        else relevancy_cfg.get("temperature", 0.0)
    )

    try:
        client = create_llm_client(api_key=api_key, base_url=base_url)

        prompt = ANSWER_RELEVANCY_PROMPT.format(question=question, answer=answer)

        logger.info(f"Evaluating answer relevancy for question: {question[:50]}...")

        message = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        response_text = message.content[0].text
        logger.debug(f"LLM response: {response_text}")

        result = parse_relevancy_response(response_text)

        overall_score = result.get("overall_score")
        if overall_score is None:
            direct = result.get("direct_relevance", 3)
            sufficiency = result.get("information_sufficiency", 3)
            conciseness = result.get("conciseness", 3)
            overall_score = (direct + sufficiency + conciseness) / 15.0

        overall_score = max(0.0, min(1.0, float(overall_score)))

        logger.success(
            f"Answer relevancy score: {overall_score:.2f} "
            f"(direct={result.get('direct_relevance', 'N/A')}, "
            f"sufficiency={result.get('information_sufficiency', 'N/A')}, "
            f"conciseness={result.get('conciseness', 'N/A')})"
        )

        return overall_score

    except Exception as e:
        error_msg = f"Failed to calculate answer relevancy: {str(e)}"
        logger.error(error_msg)
        raise EvaluationError(error_msg) from e
