import hashlib
import json
from typing import Any

from loguru import logger

from src.test_generation.models import DOCUMENT_TRUNCATE_MAX, QUESTION_TYPES
from src.test_generation.prompts import (
    BOUNDARY_PROMPT,
    DOCUMENT_LEVEL_PROMPT,
    EVIDENCE_AWARE_PROMPT,
    EVIDENCE_QUESTION_TYPE_SUPPLEMENTS,
    FACTUAL_PROMPT,
    IRRELEVANT_QUESTION_PROMPT,
    MISSING_INDEPENDENT_PROMPT,
    MULTI_HOP_PROMPT,
    QUESTION_TYPE_SUPPLEMENTS,
)
from src.test_generation.validators import validate_question_quality


def parse_json_response(
    response: str,
    required_fields: list[str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Parse an LLM response string into a JSON dictionary.

    Strips markdown code fences, extracts the JSON object, validates
    required fields, and applies default values.

    Args:
        response: Raw LLM response string.
        required_fields: List of field names that must be present and
            non-empty. If None, only basic JSON parsing is done.
        defaults: Dictionary of default values to set on the parsed
            result via ``setdefault``.

    Returns:
        Parsed dictionary, or None if parsing or validation fails.
    """
    try:
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            lines = [line for line in lines if not line.startswith("```")]
            response = "\n".join(lines)

        start = response.find("{")
        end = response.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        json_str = response[start:end]
        qa = json.loads(json_str)

        if required_fields:
            for field in required_fields:
                if field not in qa or not qa[field]:
                    logger.debug(f"Missing or empty required field: {field}")
                    return None

        if defaults:
            for key, value in defaults.items():
                qa.setdefault(key, value)

        return qa

    except (json.JSONDecodeError, KeyError) as e:
        logger.debug(f"Failed to parse LLM response as JSON: {str(e)}")
        return None


def generate_question_with_llm(
    chunks: list[dict],
    strategy: str,
    generator,
    max_retries: int = 3,
) -> dict[str, Any] | None:
    """Generate a single Q&A pair from chunks using an LLM.

    Args:
        chunks: List of chunk dictionaries.
        strategy: Question generation strategy.
        generator: Generator instance used to call the LLM.
        max_retries: Maximum number of retry attempts.

    Returns:
        Dictionary with 'question', 'answer', and 'difficulty' keys, or
        None if all retry attempts fail.

    Raises:
        ValueError: If the strategy is not recognized.
    """
    from src.exceptions import TestSetError

    normalized_strategy = strategy.replace("-", "_")
    if normalized_strategy == "factual":
        prompt = FACTUAL_PROMPT.format(chunk_text=chunks[0].get("text", ""))
    elif normalized_strategy == "boundary":
        prompt = BOUNDARY_PROMPT.format(
            chunk1_text=chunks[0].get("text", ""),
            chunk2_text=chunks[1].get("text", "") if len(chunks) > 1 else "",
        )
    elif normalized_strategy == "multi_hop":
        chunk_texts = "\n\n---\n\n".join(
            f"片段{i + 1}:\n{c.get('text', '')}" for i, c in enumerate(chunks)
        )
        prompt = MULTI_HOP_PROMPT.format(chunk_texts=chunk_texts)
    else:
        raise TestSetError(f"Unknown strategy: {strategy}")

    for attempt in range(max_retries):
        try:
            response = generator.generate(
                query=prompt,
                contexts=[],
                system_prompt="你是一个测试数据生成器。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                category="test_generation",
                allow_no_contexts=True,
            )

            qa = parse_llm_response(response)
            if qa is not None:
                return qa

            logger.debug(f"Attempt {attempt + 1}: failed to parse LLM response")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

    return None


def parse_llm_response(response: str) -> dict[str, Any] | None:
    """Parse an LLM response string into a Q&A dictionary.

    Args:
        response: Raw LLM response string.

    Returns:
        Dictionary with 'question', 'answer', and 'difficulty' keys, or
        None if the response cannot be parsed.
    """
    return parse_json_response(
        response,
        required_fields=["question", "answer"],
        defaults={"difficulty": "medium"},
    )


def generate_question_with_evidence(
    selected_segments: list[dict[str, Any]],
    question_type: str,
    generator,
) -> dict[str, Any] | None:
    """Generate a question with evidence using EVIDENCE_AWARE_PROMPT.

    Args:
        selected_segments: List of selected segment dictionaries.
        question_type: Type of question to generate.
        generator: Generator instance for LLM calls.

    Returns:
        Dictionary with question data, or None if generation fails.
    """
    q_type_cn = QUESTION_TYPES.get(question_type, question_type)

    segments_text = ""
    for i, seg in enumerate(selected_segments):
        segments_text += f"片段{i}:\n{seg.get('text', '')}\n\n"

    prompt = EVIDENCE_AWARE_PROMPT.format(
        num_segments=len(selected_segments),
        segments_text=segments_text.strip(),
        question_type=q_type_cn,
    )

    supplement = EVIDENCE_QUESTION_TYPE_SUPPLEMENTS.get(question_type, "")
    if supplement:
        prompt += "\n" + supplement

    try:
        response = generator.generate(
            query=prompt,
            contexts=[],
            system_prompt="你是一位金融行业从业者。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
            category="test_generation",
            allow_no_contexts=True,
        )

        qa = parse_evidence_question_response(response)
        if qa is not None and validate_question_quality(qa):
            return qa

        logger.debug("Failed to parse or validate evidence question response")
    except Exception as e:
        logger.warning(f"Failed to generate evidence question: {str(e)}")

    return None


def parse_evidence_question_response(response: str) -> dict[str, Any] | None:
    """Parse an LLM response for evidence-aware question generation.

    Args:
        response: Raw LLM response string.

    Returns:
        Dictionary with question data including evidence list, or None.
    """
    return parse_json_response(
        response,
        required_fields=["question", "answer", "question_type"],
        defaults={
            "difficulty": "medium",
            "evidence": [],
            "selected_segments": [],
        },
    )


def generate_single_document_question(
    document_content: str,
    question_type: str,
    generator,
    max_retries: int = 3,
    doc_truncate_cache: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Generate a single question from a document using an LLM.

    Args:
        document_content: Full text content of the document.
        question_type: Type of question to generate.
        generator: Generator instance used to call the LLM.
        max_retries: Maximum number of retry attempts.
        doc_truncate_cache: Optional cache for truncated documents.

    Returns:
        Dictionary with question data, or None if generation fails.
    """
    q_type_cn = QUESTION_TYPES.get(question_type, question_type)

    supplement = QUESTION_TYPE_SUPPLEMENTS.get(question_type, "")

    doc_key = hashlib.sha256(document_content[:1000].encode()).hexdigest()[:16]
    if doc_truncate_cache and doc_key in doc_truncate_cache:
        truncated_doc = doc_truncate_cache[doc_key]
    else:
        truncated_doc = document_content[:DOCUMENT_TRUNCATE_MAX]
        if doc_truncate_cache is not None:
            doc_truncate_cache[doc_key] = truncated_doc

    prompt = DOCUMENT_LEVEL_PROMPT.format(
        document_content=truncated_doc, question_type=q_type_cn
    )

    if supplement:
        prompt += supplement

    for attempt in range(max_retries):
        try:
            response = generator.generate(
                query=prompt,
                contexts=[],
                system_prompt="你是一位金融行业从业者。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                category="test_generation",
                allow_no_contexts=True,
            )

            qa = parse_document_question_response(response)
            if qa is not None and validate_question_quality(qa):
                return qa

            logger.debug(
                f"Attempt {attempt + 1}: failed to parse or validate question response"
            )
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

    return None


def parse_document_question_response(response: str) -> dict[str, Any] | None:
    """Parse an LLM response for document-based question generation.

    Args:
        response: Raw LLM response string.

    Returns:
        Dictionary with question data, or None if parsing fails.
    """
    return parse_json_response(
        response,
        required_fields=["question", "answer", "question_type"],
        defaults={
            "difficulty": "medium",
            "reasoning": "",
            "key_entities": [],
            "answer_sources": [],
        },
    )


def generate_missing_question(
    selected_segments: list[dict[str, Any]],
    generator,
    max_retries: int = 3,
) -> dict[str, Any] | None:
    """Generate a missing-type question using MISSING_INDEPENDENT_PROMPT.

    Uses a dedicated prompt that first analyzes what the document covers,
    then asks about a dimension clearly NOT covered. This avoids the
    contradiction of using evidence-aware prompts for questions that
    should have no evidence.

    Args:
        selected_segments: List of selected segment dictionaries.
        generator: Generator instance for LLM calls.
        max_retries: Maximum number of retry attempts.

    Returns:
        Dictionary with question data, or None if generation fails.
    """
    segments_text = ""
    for i, seg in enumerate(selected_segments):
        segments_text += f"片段{i}:\n{seg.get('text', '')}\n\n"

    prompt = MISSING_INDEPENDENT_PROMPT.format(segments_text=segments_text.strip())

    for _attempt in range(max_retries):
        try:
            response = generator.generate(
                query=prompt,
                contexts=[],
                system_prompt="你是一位金融行业从业者。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                category="test_generation",
                allow_no_contexts=True,
            )

            qa = parse_evidence_question_response(response)
            if qa is None:
                continue

            qa["question_type"] = QUESTION_TYPES.get("missing", "缺失知识点")

            evidence_list = qa.get("evidence", [])
            if evidence_list:
                logger.debug("Missing question has evidence, retrying...")
                continue

            qa["ground_truth_excerpt"] = ""
            return qa

        except Exception as e:
            logger.warning(f"Failed to generate missing question: {str(e)}")
            continue

    return None


def generate_irrelevant_question(
    doc_name: str,
    generator,
    max_retries: int = 3,
) -> dict[str, Any] | None:
    """Generate an irrelevant question unrelated to the document.

    Args:
        doc_name: Name of the document (used to derive topic).
        generator: Generator instance for LLM calls.
        max_retries: Maximum number of retry attempts.

    Returns:
        Dictionary with question data, or None if generation fails.
    """
    doc_topic = doc_name.split("：")[0] if "：" in doc_name else doc_name

    prompt = IRRELEVANT_QUESTION_PROMPT.format(doc_topic=doc_topic)

    for _attempt in range(max_retries):
        try:
            response = generator.generate(
                query=prompt,
                contexts=[],
                system_prompt="你是一位金融行业从业者。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                category="test_generation",
                allow_no_contexts=True,
            )

            qa = parse_evidence_question_response(response)
            if qa is None:
                continue

            qa["question_type"] = QUESTION_TYPES.get("irrelevant", "无关问题")
            qa["ground_truth_excerpt"] = ""

            evidence_list = qa.get("evidence", [])
            if evidence_list:
                logger.debug("Irrelevant question has evidence, retrying...")
                continue

            return qa

        except Exception as e:
            logger.warning(f"Failed to generate irrelevant question: {str(e)}")
            continue

    return None
