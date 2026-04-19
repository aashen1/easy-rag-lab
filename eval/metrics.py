import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from anthropic import Anthropic
from loguru import logger


def normalize_source(source: str) -> str:
    """Normalize source path to a comparable form.

    Extracts the filename stem (without extension and directory),
    so that paths like "annual_report/贵州茅台2023年年度报告.md"
    and "贵州茅台2023年年度报告.pdf" both become "贵州茅台2023年年度报告".

    Args:
        source: Source path string.

    Returns:
        Normalized source stem string.
    """
    return Path(source).stem


def calculate_hit_rate(
    retrieved_sources: List[str],
    expected_sources: List[str],
    k: int = 5,
    mode: str = "standard"
) -> float:
    """Calculate hit rate for retrieval evaluation.

    Industry Standard Definition (mode='standard'):
        Hit Rate@k = 1.0 if at least one relevant document is in top-k results,
        otherwise 0.0. This is the recommended mode for fair comparison with
        other systems.

    Legacy Mode (mode='recall'):
        Calculates recall = (retrieved relevant docs) / (total relevant docs).
        This mode is kept for backward compatibility but may produce inflated
        scores compared to standard Hit Rate.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider for standard mode. Defaults to 5.
        mode: Calculation mode - 'standard' for industry standard Hit Rate@k,
              'recall' for legacy recall-based calculation. Defaults to 'standard'.

    Returns:
        Hit rate as a float between 0.0 and 1.0.

    Raises:
        ValueError: If mode is not 'standard' or 'recall'.
    """
    if mode not in ("standard", "recall"):
        raise ValueError(f"mode must be 'standard' or 'recall', got '{mode}'")

    if not expected_sources:
        return 0.0

    if mode == "standard":
        top_k = retrieved_sources[:k]
        top_k_set = set(normalize_source(s) for s in top_k)
        expected_set = set(normalize_source(s) for s in expected_sources)
        return 1.0 if top_k_set & expected_set else 0.0

    retrieved_set = set(normalize_source(s) for s in retrieved_sources)
    expected_set = set(normalize_source(s) for s in expected_sources)
    hits = len(retrieved_set & expected_set)
    return hits / len(expected_set)


def calculate_mrr(
    retrieved_sources: List[str], expected_sources: List[str]
) -> float:
    """Calculate Reciprocal Rank (RR) for a single query.

    This function computes the Reciprocal Rank for a single query, which is
    defined as 1/rank where rank is the position of the first relevant document
    in the retrieved list (1-indexed). The Mean Reciprocal Rank (MRR) is obtained
    by averaging RR values across multiple queries.

    The function normalizes source paths using their filename stems, allowing
    cross-format matching (e.g., "path/to/doc.pdf" matches "doc.md").

    Args:
        retrieved_sources: List of retrieved source paths, ordered by relevance
            (most relevant first).
        expected_sources: List of expected (relevant) source paths.

    Returns:
        Reciprocal Rank as a float between 0.0 and 1.0:
        - 1.0 if a relevant document is found at position 1
        - 1/n if the first relevant document is at position n
        - 0.0 if no relevant document is found or expected_sources is empty

    Note:
        This function calculates RR for a single query. To compute MRR across
        multiple queries, average the RR values from multiple calls.

    Example:
        >>> calculate_mrr(["doc2", "doc1", "doc3"], ["doc1"])
        0.5  # doc1 is at position 2, so RR = 1/2
    """
    if not expected_sources:
        return 0.0

    expected_set = set(normalize_source(s) for s in expected_sources)

    for i, source in enumerate(retrieved_sources):
        if normalize_source(source) in expected_set:
            return 1.0 / (i + 1)

    return 0.0


def calculate_ndcg(
    retrieved_sources: List[str],
    expected_sources: List[str],
    k: int = 5,
    relevance_scores: Optional[Dict[str, int]] = None,
) -> float:
    """Calculate Normalized Discounted Cumulative Gain for retrieval evaluation.

    Supports multi-level relevance scoring (e.g., 0-3 scale) instead of simple
    binary relevance. Uses the standard DCG formula:
        DCG@k = Σ((2^rel_i - 1) / log2(i + 2))

    This implementation includes deduplication to handle cases where the same
    document appears multiple times in the retrieved results, ensuring NDCG
    always falls within [0, 1].

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider.
        relevance_scores: Optional dict mapping source names to relevance scores
            (e.g., {"doc1": 3, "doc2": 1}). Higher scores indicate higher relevance.
            If None, uses binary relevance (score=1 for all expected documents).

    Returns:
        NDCG as a float between 0.0 and 1.0.

    Examples:
        Binary relevance (default):
            >>> calculate_ndcg(["doc1", "doc2"], ["doc1", "doc2"])
            1.0

        Multi-level relevance:
            >>> rel_scores = {"doc1": 3, "doc2": 1}
            >>> calculate_ndcg(["doc1", "doc2"], ["doc1", "doc2"],
            ...                relevance_scores=rel_scores)
            1.0

        With duplicates (should not exceed 1.0):
            >>> calculate_ndcg(["doc1", "doc1", "doc1"], ["doc1"])
            1.0
    """
    if not expected_sources:
        return 0.0

    expected_normalized = [normalize_source(s) for s in expected_sources]
    expected_set = set(expected_normalized)

    if relevance_scores is None:
        relevance_scores = {normalize_source(s): 1 for s in expected_sources}

    retrieved_normalized = [normalize_source(s) for s in retrieved_sources[:k]]

    seen: set = set()
    unique_retrieved: List[str] = []
    for source in retrieved_normalized:
        if source not in seen:
            seen.add(source)
            unique_retrieved.append(source)

    dcg = 0.0
    for i, source in enumerate(unique_retrieved):
        if source in expected_set and source in relevance_scores:
            rel = relevance_scores[source]
            dcg += (2**rel - 1) / math.log2(i + 2)

    ideal_rels = []
    for source in expected_normalized:
        if source in relevance_scores:
            ideal_rels.append(relevance_scores[source])

    ideal_rels.sort(reverse=True)
    ideal_rels = ideal_rels[:k]

    ideal_dcg = 0.0
    for i, rel in enumerate(ideal_rels):
        ideal_dcg += (2**rel - 1) / math.log2(i + 2)

    if ideal_dcg == 0:
        return 0.0

    ndcg = dcg / ideal_dcg

    return min(1.0, max(0.0, ndcg))


def _parse_chunk_id(chunk_id: str) -> tuple:
    """Parse chunk_id into (doc_stem, chunk_index).

    Chunk IDs are expected to follow the format "{doc_stem}_{index:03d}",
    where the suffix after the last underscore is a zero-padded integer
    representing the chunk index within the document.

    Args:
        chunk_id: Chunk identifier string to parse.

    Returns:
        Tuple of (doc_stem, chunk_index) where doc_stem is the document
        stem string and chunk_index is the integer chunk index.
        Returns (chunk_id, -1) if the suffix cannot be parsed as an integer.
    """
    last_underscore = chunk_id.rfind("_")
    if last_underscore == -1:
        return (chunk_id, -1)
    doc_stem = chunk_id[:last_underscore]
    suffix = chunk_id[last_underscore + 1:]
    try:
        chunk_index = int(suffix)
        return (doc_stem, chunk_index)
    except ValueError:
        return (chunk_id, -1)


def calculate_chunk_hit_rate(
    retrieved_chunk_ids: List[str],
    expected_chunk_ids: List[str],
    adjacent_tolerance: int = 1,
    k: int = 5,
) -> float:
    """Calculate chunk-level hit rate with adjacent tolerance.

    This metric evaluates whether any of the top-k retrieved chunks match
    the expected chunks, supporting both exact matches and adjacent matches
    within a configurable tolerance window.

    A match occurs when:
    - The retrieved chunk_id is exactly in expected_chunk_ids (exact match), OR
    - The retrieved chunk belongs to the same document as an expected chunk
      AND the absolute difference between their chunk indices is within
      adjacent_tolerance (adjacent match).

    Args:
        retrieved_chunk_ids: List of retrieved chunk identifiers, ordered
            by relevance (most relevant first).
        expected_chunk_ids: List of expected (ground truth) chunk identifiers.
        adjacent_tolerance: Maximum allowed index difference for adjacent
            matching. Defaults to 1.
        k: Number of top results to consider. Defaults to 5.

    Returns:
        Hit rate as 1.0 if any match is found in top-k, 0.0 otherwise.
        Returns 0.0 if expected_chunk_ids is empty.
    """
    if not expected_chunk_ids:
        return 0.0

    expected_parsed = [_parse_chunk_id(cid) for cid in expected_chunk_ids]
    expected_exact_set = set(expected_chunk_ids)

    for chunk_id in retrieved_chunk_ids[:k]:
        if chunk_id in expected_exact_set:
            return 1.0
        ret_stem, ret_index = _parse_chunk_id(chunk_id)
        if ret_index == -1:
            continue
        for exp_stem, exp_index in expected_parsed:
            if exp_index == -1:
                continue
            if ret_stem == exp_stem and abs(ret_index - exp_index) <= adjacent_tolerance:
                return 1.0

    return 0.0


def calculate_chunk_mrr(
    retrieved_chunk_ids: List[str],
    expected_chunk_ids: List[str],
    adjacent_tolerance: int = 1,
) -> float:
    """Calculate chunk-level Mean Reciprocal Rank with adjacent tolerance.

    Uses the same matching logic as calculate_chunk_hit_rate but returns
    the reciprocal of the rank at which the first match is found, rather
    than a binary hit/miss.

    Args:
        retrieved_chunk_ids: List of retrieved chunk identifiers, ordered
            by relevance (most relevant first).
        expected_chunk_ids: List of expected (ground truth) chunk identifiers.
        adjacent_tolerance: Maximum allowed index difference for adjacent
            matching. Defaults to 1.

    Returns:
        Reciprocal rank as a float between 0.0 and 1.0:
        - 1.0 if the first match is at position 1
        - 1/n if the first match is at position n
        - 0.0 if no match is found or expected_chunk_ids is empty
    """
    if not expected_chunk_ids:
        return 0.0

    expected_parsed = [_parse_chunk_id(cid) for cid in expected_chunk_ids]
    expected_exact_set = set(expected_chunk_ids)

    for i, chunk_id in enumerate(retrieved_chunk_ids):
        if chunk_id in expected_exact_set:
            return 1.0 / (i + 1)
        ret_stem, ret_index = _parse_chunk_id(chunk_id)
        if ret_index == -1:
            continue
        for exp_stem, exp_index in expected_parsed:
            if exp_index == -1:
                continue
            if ret_stem == exp_stem and abs(ret_index - exp_index) <= adjacent_tolerance:
                return 1.0 / (i + 1)

    return 0.0


def calculate_chunk_ndcg(
    retrieved_chunk_ids: List[str],
    expected_chunk_ids: List[str],
    k: int = 5,
    adjacent_tolerance: int = 1,
) -> float:
    """Calculate chunk-level NDCG with adjacent tolerance.

    Assigns multi-level relevance scores based on match type:
    - Exact match: relevance = 2
    - Adjacent match (within tolerance): relevance = 1
    - No match: relevance = 0

    Uses the standard DCG formula:
        DCG@k = sum((2^rel_i - 1) / log2(i + 2))

    Deduplicates by chunk_id before computing to avoid inflated scores.

    Args:
        retrieved_chunk_ids: List of retrieved chunk identifiers, ordered
            by relevance (most relevant first).
        expected_chunk_ids: List of expected (ground truth) chunk identifiers.
        k: Number of top results to consider. Defaults to 5.
        adjacent_tolerance: Maximum allowed index difference for adjacent
            matching. Defaults to 1.

    Returns:
        NDCG as a float between 0.0 and 1.0.
        Returns 0.0 if expected_chunk_ids is empty.
    """
    if not expected_chunk_ids:
        return 0.0

    expected_exact_set = set(expected_chunk_ids)
    expected_parsed = [_parse_chunk_id(cid) for cid in expected_chunk_ids]

    seen: set = set()
    unique_retrieved: List[str] = []
    for chunk_id in retrieved_chunk_ids[:k]:
        if chunk_id not in seen:
            seen.add(chunk_id)
            unique_retrieved.append(chunk_id)

    def _get_relevance(chunk_id: str) -> int:
        if chunk_id in expected_exact_set:
            return 2
        ret_stem, ret_index = _parse_chunk_id(chunk_id)
        if ret_index == -1:
            return 0
        for exp_stem, exp_index in expected_parsed:
            if exp_index == -1:
                continue
            if ret_stem == exp_stem and abs(ret_index - exp_index) <= adjacent_tolerance:
                return 1
        return 0

    dcg = 0.0
    for i, chunk_id in enumerate(unique_retrieved):
        rel = _get_relevance(chunk_id)
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(i + 2)

    ideal_rels = [2] * len(expected_chunk_ids)
    ideal_rels.sort(reverse=True)
    ideal_rels = ideal_rels[:k]

    ideal_dcg = 0.0
    for i, rel in enumerate(ideal_rels):
        ideal_dcg += (2**rel - 1) / math.log2(i + 2)

    if ideal_dcg == 0:
        return 0.0

    ndcg = dcg / ideal_dcg
    return min(1.0, max(0.0, ndcg))


def calculate_false_positive_rate(
    retrieved_sources: List[str],
    k: int = 5,
) -> float:
    """Calculate False Positive Rate for irrelevant questions.

    For questions that have no relevant documents (irrelevant questions),
    all retrieved documents are false positives. The FPR measures the
    proportion of top-k slots occupied by irrelevant retrievals.

    Args:
        retrieved_sources: List of retrieved source paths for an
            irrelevant question.
        k: Number of top results to consider. Defaults to 5.

    Returns:
        False positive rate as a float between 0.0 and 1.0:
        - 1.0 if all k slots are filled with irrelevant results
        - 0.0 if no results are retrieved
        - Proportional value for partial retrieval
    """
    top_k = retrieved_sources[:k]
    return len(top_k) / k


def deduplicate_by_document(
    retrieved_sources: List[str],
    retrieved_chunk_ids: Optional[List[str]] = None,
) -> List[int]:
    """Return indices to keep after deduplicating by document.

    Identifies the first occurrence of each unique document in the
    retrieved results and returns their indices. Subsequent occurrences
    of the same document are excluded.

    When retrieved_chunk_ids is provided, the function first attempts
    to extract the document stem from the chunk_id (format:
    "{doc_stem}_{index:03d}") for more precise deduplication. If
    chunk_id parsing fails, it falls back to normalizing the source path.

    Args:
        retrieved_sources: List of retrieved source paths.
        retrieved_chunk_ids: Optional list of chunk identifiers
            corresponding to retrieved_sources. If provided, used for
            document identification. If None, deduplication is based
            on source path only.

    Returns:
        List of integer indices to keep (first occurrence of each
        unique document), in ascending order.
    """
    seen: set = set()
    keep_indices: List[int] = []

    for i, source in enumerate(retrieved_sources):
        if retrieved_chunk_ids is not None and i < len(retrieved_chunk_ids):
            doc_stem, _ = _parse_chunk_id(retrieved_chunk_ids[i])
            if doc_stem != retrieved_chunk_ids[i]:
                key = doc_stem
            else:
                key = normalize_source(source)
        else:
            key = normalize_source(source)

        if key not in seen:
            seen.add(key)
            keep_indices.append(i)

    return keep_indices


def calculate_dedup_hit_rate(
    retrieved_sources: List[str],
    expected_sources: List[str],
    k: int = 5,
    retrieved_chunk_ids: Optional[List[str]] = None,
) -> float:
    """Calculate hit rate after deduplicating by document.

    First deduplicates the retrieved sources so that each document
    appears only once, then calculates hit rate on the deduplicated
    list using the standard calculate_hit_rate function.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider. Defaults to 5.
        retrieved_chunk_ids: Optional list of chunk identifiers for
            more precise deduplication.

    Returns:
        Hit rate as a float between 0.0 and 1.0.
    """
    keep_indices = deduplicate_by_document(retrieved_sources, retrieved_chunk_ids)
    deduped_sources = [retrieved_sources[i] for i in keep_indices]
    return calculate_hit_rate(deduped_sources, expected_sources, k=k)


def calculate_dedup_mrr(
    retrieved_sources: List[str],
    expected_sources: List[str],
    retrieved_chunk_ids: Optional[List[str]] = None,
) -> float:
    """Calculate MRR after deduplicating by document.

    First deduplicates the retrieved sources so that each document
    appears only once, then calculates MRR on the deduplicated list
    using the standard calculate_mrr function.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        retrieved_chunk_ids: Optional list of chunk identifiers for
            more precise deduplication.

    Returns:
        Reciprocal rank as a float between 0.0 and 1.0.
    """
    keep_indices = deduplicate_by_document(retrieved_sources, retrieved_chunk_ids)
    deduped_sources = [retrieved_sources[i] for i in keep_indices]
    return calculate_mrr(deduped_sources, expected_sources)


def calculate_dedup_ndcg(
    retrieved_sources: List[str],
    expected_sources: List[str],
    k: int = 5,
    relevance_scores: Optional[Dict[str, int]] = None,
    retrieved_chunk_ids: Optional[List[str]] = None,
) -> float:
    """Calculate NDCG after deduplicating by document.

    First deduplicates the retrieved sources so that each document
    appears only once, then calculates NDCG on the deduplicated list
    using the standard calculate_ndcg function.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider. Defaults to 5.
        relevance_scores: Optional dict mapping source names to
            relevance scores.
        retrieved_chunk_ids: Optional list of chunk identifiers for
            more precise deduplication.

    Returns:
        NDCG as a float between 0.0 and 1.0.
    """
    keep_indices = deduplicate_by_document(retrieved_sources, retrieved_chunk_ids)
    deduped_sources = [retrieved_sources[i] for i in keep_indices]
    return calculate_ndcg(deduped_sources, expected_sources, k=k, relevance_scores=relevance_scores)


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


def _create_llm_client(
    api_key: str,
    base_url: str,
) -> Anthropic:
    """Create an Anthropic client for LLM calls.

    Args:
        api_key: API key for authentication.
        base_url: Base URL for the API endpoint.

    Returns:
        Configured Anthropic client instance.

    Raises:
        Exception: If client creation fails.
    """
    try:
        client = Anthropic(
            api_key="dummy",
            base_url=base_url,
            default_headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        return client
    except Exception as e:
        error_msg = f"Failed to create LLM client: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def _extract_statements(
    client: Anthropic,
    answer: str,
    model_name: str = "LongCat-Flash-Lite",
) -> List[str]:
    """Extract factual statements from an answer using LLM.

    Args:
        client: Anthropic client instance.
        answer: The answer text to extract statements from.
        model_name: Name of the LLM model to use.

    Returns:
        List of extracted statement strings.

    Raises:
        Exception: If LLM call fails or response parsing fails.
    """
    prompt = FAITHFULNESS_STATEMENT_PROMPT.format(answer=answer)

    try:
        message = client.messages.create(
            model=model_name,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        json_match = re.search(r'\{[\s\S]*\}', response_text)
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
        raise Exception(error_msg)


def _verify_statements(
    client: Anthropic,
    statements: List[str],
    contexts: List[str],
    model_name: str = "LongCat-Flash-Lite",
) -> List[Dict[str, Any]]:
    """Verify if statements can be derived from contexts using LLM.

    Args:
        client: Anthropic client instance.
        statements: List of statement strings to verify.
        contexts: List of context strings to verify against.
        model_name: Name of the LLM model to use.

    Returns:
        List of dicts with statement and verdict (1 for derivable, 0 for not).

    Raises:
        Exception: If LLM call fails or response parsing fails.
    """
    context_text = "\n\n".join([f"上下文 {i+1}:\n{ctx}" for i, ctx in enumerate(contexts)])
    statements_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(statements)])

    prompt = FAITHFULNESS_VERIFICATION_PROMPT.format(
        contexts=context_text,
        statements=statements_text,
    )

    try:
        message = client.messages.create(
            model=model_name,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        json_match = re.search(r'\{[\s\S]*\}', response_text)
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
        raise Exception(error_msg)


def calculate_faithfulness(
    answer: str,
    contexts: List[str],
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
    model_name: str = "LongCat-Flash-Lite",
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
            Defaults to "https://api.longcat.chat/anthropic".
        model_name: Name of the LLM model to use for evaluation.
            Defaults to "LongCat-Flash-Lite".

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
        raise ValueError(error_msg)

    if not contexts:
        logger.warning("No contexts provided for faithfulness evaluation")
        return 0.0

    answer = answer.strip()
    if not answer:
        logger.warning("Answer is empty after stripping whitespace")
        return 0.0

    try:
        client = _create_llm_client(api_key=api_key, base_url=base_url)

        logger.info("Extracting statements from answer")
        statements = _extract_statements(client, answer, model_name)

        if not statements:
            logger.warning("No statements extracted from answer")
            return 0.0

        logger.info(f"Extracted {len(statements)} statements, verifying against contexts")
        verdicts = _verify_statements(client, statements, contexts, model_name)

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
        raise Exception(error_msg)


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


def _parse_relevancy_response(response_text: str) -> Dict[str, Any]:
    """Parse LLM response for answer relevancy evaluation.

    Args:
        response_text: Raw text response from LLM.

    Returns:
        Parsed dictionary with relevancy scores.

    Raises:
        ValueError: If response cannot be parsed as JSON.
    """
    json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}")


def calculate_answer_relevancy(
    question: str,
    answer: str,
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
    model_name: str = "LongCat-Flash-Lite",
    max_tokens: int = 512,
    temperature: float = 0.0,
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
        model_name: Name of the LLM model to use.
        max_tokens: Maximum tokens in the LLM response.
        temperature: Sampling temperature for LLM generation.

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
        raise ValueError("Question must be a non-empty string")
    if not answer or not isinstance(answer, str):
        raise ValueError("Answer must be a non-empty string")

    try:
        client = _create_llm_client(api_key=api_key, base_url=base_url)

        prompt = ANSWER_RELEVANCY_PROMPT.format(
            question=question,
            answer=answer
        )

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

        result = _parse_relevancy_response(response_text)

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
        raise Exception(error_msg)


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


def _judge_context_relevance(
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
    client = _create_llm_client(api_key=api_key, base_url=base_url)

    prompt = CONTEXT_PRECISION_PROMPT.format(
        question=question,
        expected_output=expected_output,
        context=context,
    )

    try:
        message = client.messages.create(
            model=model_name,
            max_tokens=256,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            verdict = result.get("verdict", "否")
            return verdict.strip() == "是"

        return False

    except Exception as e:
        logger.warning(f"Failed to judge context relevance: {str(e)}")
        return False


def calculate_context_precision(
    question: str,
    expected_output: str,
    retrieval_context: List[str],
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
    model_name: str = "LongCat-Flash-Lite",
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
        base_url: Base URL for LLM API. Defaults to "https://api.longcat.chat/anthropic".
        model_name: LLM model name. Defaults to "LongCat-Flash-Lite".

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

    relevance_verdicts = []
    for ctx in retrieval_context:
        verdict = _judge_context_relevance(
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


CONTEXT_RECALL_SENTENCE_PROMPT = """请判断以下陈述是否可以从给定的上下文中推断出来。

【上下文】
{context}

【陈述】
{sentence}

请判断这个陈述是否可以从上下文中直接推导或合理推断出来。
只回答"是"或"否"。

请以JSON格式输出：
{{"verdict": "是"或"否"}}"""


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences.

    Args:
        text: Text to split.

    Returns:
        List of sentences.
    """
    import re

    sentences = re.split(r'[。！？.!?]', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def _can_infer_from_context(
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
    client = _create_llm_client(api_key=api_key, base_url=base_url)

    prompt = CONTEXT_RECALL_SENTENCE_PROMPT.format(
        context=context,
        sentence=sentence,
    )

    try:
        message = client.messages.create(
            model=model_name,
            max_tokens=64,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            verdict = result.get("verdict", "否")
            return verdict.strip() == "是"

        return False

    except Exception as e:
        logger.warning(f"Failed to check sentence inference: {str(e)}")
        return False


def calculate_context_recall(
    question: str,
    ground_truth: str,
    retrieval_context: List[str],
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
    model_name: str = "LongCat-Flash-Lite",
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
        base_url: Base URL for LLM API. Defaults to "https://api.longcat.chat/anthropic".
        model_name: LLM model name. Defaults to "LongCat-Flash-Lite".

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

    sentences = _split_into_sentences(ground_truth)
    if not sentences:
        logger.warning("No sentences extracted from ground truth")
        return 0.0

    context_text = "\n\n".join(retrieval_context)
    inferable_count = 0

    for sentence in sentences:
        if _can_infer_from_context(sentence, context_text, api_key, base_url, model_name):
            inferable_count += 1

    score = inferable_count / len(sentences)

    logger.success(
        f"Context recall: {score:.4f} "
        f"({inferable_count}/{len(sentences)} sentences inferable)"
    )

    return score
