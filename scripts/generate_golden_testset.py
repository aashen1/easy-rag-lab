"""Golden test set generator for RAG evaluation.

Generates a high-quality ~150-question golden test set with three core
elements: question, precise answer, and ground truth location (document +
excerpt). Uses LLM-assisted generation with improved prompts that require
ground_truth_excerpt output, then performs quality pre-checks.

Usage:
    pixi run python scripts/generate_golden_testset.py --num-questions 150
    pixi run python scripts/generate_golden_testset.py --num-questions 150 --llm-preset default
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.generator import Generator
from src.utils import get_llm_config, load_config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


GOLDEN_QUESTION_TYPES = {
    "single_fact": "单知识点查询",
    "multi_fact": "多知识点综合",
    "reasoning": "推理型问题",
    "comparative": "对比分析",
    "missing": "缺失知识点",
    "irrelevant": "无关问题",
    "adversarial": "对抗性问题",
}

GOLDEN_TYPE_DISTRIBUTION = {
    "single_fact": 0.17,
    "multi_fact": 0.20,
    "reasoning": 0.17,
    "comparative": 0.17,
    "missing": 0.13,
    "irrelevant": 0.07,
    "adversarial": 0.10,
}

FAILURE_MODES = {
    "single_fact": "基础检索失败：精确数据/事实无法被检索到",
    "multi_fact": "多跳检索失败：需要整合多个信息点但系统只返回部分",
    "reasoning": "推理能力不足：无法基于检索到的信息进行逻辑推断",
    "comparative": "对比分析失败：无法跨段落/跨文档对比信息",
    "missing": "拒答能力不足：文档中没有的信息未能正确识别，产生幻觉",
    "irrelevant": "幻觉控制失败：无关问题产生了看似相关的编造内容",
    "adversarial": "边界场景翻车：数字近似/跨文档混淆/时序陷阱等",
}

GOLDEN_PROMPT = """你是一位资深金融行业QA工程师，正在为RAG问答系统编写高质量测试题。

{type_specific_instruction}

## 文档内容
---
{document_content}
---

## 输出格式

请严格按以下JSON格式输出（不要输出其他内容）：

{{
    "question": "你的问题（直接、口语化，像在问同事）",
    "answer": "精确答案（引用具体数据和结论）",
    "question_type": "{question_type_en}",
    "difficulty": "easy/medium/hard",
    "ground_truth_excerpt": "从原文逐字摘录的答案所在片段（50-200字）",
    "key_entities": ["问题涉及的关键实体"],
    "target_failure_mode": "该题针对的RAG失败模式"
}}

重要数值规则：
- 文档中的财务数据通常以"元"为单位（如 12,162,684,368.86）
- 答案中请换算为"亿元"：÷100,000,000（即去掉8位数字）
- 正确示例：12,162,684,368.86元 = 121.63亿元
- 错误示例：12,162,684,368.86元 ≠ 1216.3亿元（多了10倍）
- 如果原文已用"亿元"为单位，则直接引用，不要再次换算"""

SINGLE_FACT_INSTRUCTION = """请基于以上文档，生成一道**单知识点查询**题。

要求：
- 问题只涉及文档中一个具体数据点、事实或概念
- 答案必须是文档中明确出现的具体数值或定义
- 问题要口语化，像在问同事，不要用"请说明""根据文档"等学术化措辞
- 好的例子："2024年光模块市场规模多少？""CPO的全称是什么？"
- ground_truth_excerpt：包含该数据或定义的原文段落（50-200字）"""

MULTI_FACT_INSTRUCTION = """请基于以上文档，生成一道**多知识点综合**题。

要求：
- 问题必须涉及文档中至少2个不同位置的信息，需要整合才能回答
- 不要把多个不相关问题拼在一起，而是要有逻辑关联
- 问题要口语化，像在问同事，不要用"请说明""根据文档"等学术化措辞
- 好的例子："科瑞技术和猎奇智能在光模块设备上有什么区别？"
- ground_truth_excerpt：包含主要信息点的原文段落（可以拼接2-3个片段，用...分隔）"""

REASONING_INSTRUCTION = """请基于以上文档，生成一道**推理型**题。

要求：
- 问题需要基于文档信息进行逻辑推理或判断，不能仅靠查找直接得到答案
- 答案必须展示推理过程，推理依据必须来自文档
- 问题要口语化，像在问同事，不要用"请说明""根据文档"等学术化措辞
- 好的例子："为什么CPO能降低功耗？""如果800G需求翻倍，对设备商有什么影响？"
- ground_truth_excerpt：包含推理前提的原文段落"""

COMPARATIVE_INSTRUCTION = """请基于以上文档，生成一道**对比分析**题。

要求：
- 问题必须涉及文档中两个或多个对象的对比（不同公司、不同时期、不同技术等）
- 答案需要列出对比对象的异同点
- 问题要口语化，像在问同事，不要用"请说明""根据文档"等学术化措辞
- 好的例子："中际旭创和新易盛哪个更值得投资？""CPO和LPO两种技术路线各有什么优缺点？"
- ground_truth_excerpt：包含对比对象信息的原文段落"""

MISSING_INSTRUCTION = """请基于以上文档，生成一道**缺失知识点**题。

要求：
- 问题询问的是文档中没有或不完整的信息
- 答案必须明确说明"文档未提及该信息"或"文档信息不完整"
- 问题要口语化，像在问同事，不要用"请说明""根据文档"等学术化措辞
- 好的例子："光模块行业的ESG评级情况怎么样？"（文档未涉及ESG）
- ground_truth_excerpt：与问题最相关但确实不包含答案的原文段落"""

IRRELEVANT_INSTRUCTION = (
    """请生成一道与以上文档主题**完全无关**的问题。

要求：
- 问题必须与文档主题完全无关，测试系统的拒答能力
- 不要提及文档中的任何公司、行业或概念
- 问题要口语化，像在问同事
- 好的例子：如果文档是关于光模块的，可以问"新能源汽车的电池技术发展怎么样？"
- answer：写"该问题与文档内容无关，无法基于文档回答"
- ground_truth_excerpt：留空字符串"""
    ""
)

ADVERSARIAL_INSTRUCTION = """请基于以上文档，生成一道**对抗性**问题，故意设计容易让RAG系统出错的边界场景。

可选的对抗策略（选一种）：
1. 数字近似陷阱：在问题中包含一个与文档中数字接近但不相同的值，看系统是否会纠正
2. 时序陷阱：问一个文档未覆盖的时间段数据
3. 否定问题：用"不是""没有"等否定措辞，看系统是否会忽略否定
4. 部分匹配陷阱：问一个答案恰好跨越文档段落边界的问题

要求：
- 问题中必须包含"诱饵"信息，好的系统应该能识别并纠正
- 答案必须指出文档中的正确信息，并说明问题中的诱饵
- 问题要口语化，像在问同事，不要用"请说明""根据文档"等学术化措辞
- 好的例子："光模块市场增长了15%吗？"（文档实际是12.5%，测试系统是否会纠正）
- ground_truth_excerpt：包含正确信息的原文段落"""

TYPE_INSTRUCTIONS = {
    "single_fact": SINGLE_FACT_INSTRUCTION,
    "multi_fact": MULTI_FACT_INSTRUCTION,
    "reasoning": REASONING_INSTRUCTION,
    "comparative": COMPARATIVE_INSTRUCTION,
    "missing": MISSING_INSTRUCTION,
    "irrelevant": IRRELEVANT_INSTRUCTION,
    "adversarial": ADVERSARIAL_INSTRUCTION,
}

DOCUMENT_TRUNCATE_MAX = 10000


def _load_pages_json(file_path: Path, parsed_dir: Path) -> dict[str, str] | None:
    """Load a .pages.json file and concatenate all pages.

    Args:
        file_path: Path to the .pages.json file.
        parsed_dir: Base parsed directory for computing relative paths.

    Returns:
        Dictionary with 'name', 'content', 'source_path', 'doc_id' keys,
        or None on error.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            pages_data = json.load(f)

        if not isinstance(pages_data, list):
            logger.warning(f"Invalid pages.json format in {file_path}")
            return None

        full_text = "\n\n".join(
            page.get("text", "")
            for page in sorted(pages_data, key=lambda p: p.get("page_number", 0))
        )

        rel_path = file_path.relative_to(parsed_dir).as_posix()
        doc_name = file_path.stem
        if doc_name.endswith(".pages"):
            doc_name = doc_name[: -len(".pages")]

        return {
            "name": doc_name,
            "content": full_text,
            "source_path": rel_path,
            "doc_id": rel_path,
        }
    except Exception as e:
        logger.error(f"Failed to load {file_path}: {str(e)}")
        return None


def load_documents(parsed_dir: Path) -> list[dict[str, str]]:
    """Load all documents from the parsed directory.

    Supports both .md and .pages.json formats. For .pages.json files,
    all pages are concatenated into a single text document.

    Args:
        parsed_dir: Path to the directory containing parsed document files.

    Returns:
        List of dicts with 'name', 'content', 'source_path' keys.
    """
    documents = []
    if not parsed_dir.exists():
        logger.error(f"Parsed directory not found: {parsed_dir}")
        return documents

    for md_file in sorted(parsed_dir.rglob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            rel_path = md_file.relative_to(parsed_dir).as_posix()
            doc_name = md_file.stem
            documents.append(
                {
                    "name": doc_name,
                    "content": content,
                    "source_path": rel_path,
                    "doc_id": rel_path,
                }
            )
            logger.debug(f"Loaded document: {doc_name} ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Failed to load {md_file}: {str(e)}")

    for pages_file in sorted(parsed_dir.rglob("*.pages.json")):
        result = _load_pages_json(pages_file, parsed_dir)
        if result is not None:
            documents.append(result)
            logger.debug(
                f"Loaded document: {result['name']} ({len(result['content'])} chars)"
            )

    return documents


def calculate_type_counts(
    num_questions: int, distribution: dict[str, float]
) -> dict[str, int]:
    """Calculate the number of questions for each type.

    Args:
        num_questions: Total number of questions.
        distribution: Type distribution mapping.

    Returns:
        Dictionary mapping type names to question counts.
    """
    type_counts = {}
    remaining = num_questions
    sorted_types = sorted(distribution.items(), key=lambda x: x[1], reverse=True)

    for i, (q_type, proportion) in enumerate(sorted_types):
        if i == len(sorted_types) - 1:
            type_counts[q_type] = remaining
        else:
            count = int(num_questions * proportion)
            type_counts[q_type] = count
            remaining -= count

    return type_counts


def distribute_across_documents(
    type_counts: dict[str, int],
    documents: list[dict[str, str]],
    min_per_doc: int = 1,
    max_per_doc: int | None = None,
    seed: int | None = None,
) -> dict[str, list[str]]:
    """Distribute question types across documents using progressive power weighting.

    Uses weight = L^p where p = max(0, (r-1)/r) and r = Q/N.
    When r ≈ 1 (few questions per doc), p ≈ 0 → equal allocation.
    When r >> 1 (many questions per doc), p → 1 → proportional to content length.
    The transition is smooth with no discontinuity.

    Args:
        type_counts: Dictionary mapping question type names to counts.
        documents: List of document dicts with 'doc_id' and 'content' keys.
        min_per_doc: Minimum questions per document (default 1, ensures coverage).
        max_per_doc: Maximum questions per document (default None; optional safety cap).
        seed: Random seed for reproducibility.

    Returns:
        Dictionary mapping doc_id to list of assigned question types.
    """
    import random

    rng = random.Random(seed)

    total_questions = sum(type_counts.values())
    n_docs = len(documents)
    if n_docs == 0:
        return {}

    r = total_questions / n_docs

    if r < 1:
        selected = rng.sample(documents, total_questions)
        raw_alloc = {d["doc_id"]: 1.0 for d in selected}
    else:
        p = (r - 1) / r
        lengths = [len(d["content"]) for d in documents]
        powered = [length**p for length in lengths]
        total_powered = sum(powered)
        raw_alloc = {}
        for doc, pw in zip(documents, powered, strict=True):
            raw_alloc[doc["doc_id"]] = (pw / total_powered) * total_questions

    int_alloc = _round_allocations(
        raw_alloc,
        total_questions,
        min_per_doc,
        max_per_doc,
    )

    all_types = []
    for q_type, count in type_counts.items():
        all_types.extend([q_type] * count)
    rng.shuffle(all_types)

    result = {}
    idx = 0
    doc_order = sorted(
        documents, key=lambda d: int_alloc.get(d["doc_id"], 0), reverse=True
    )
    for doc in doc_order:
        doc_id = doc["doc_id"]
        n = int_alloc.get(doc_id, 0)
        result[doc_id] = all_types[idx : idx + n]
        idx += n

    return result


def _round_allocations(
    raw_alloc: dict[str, float],
    total: int,
    min_per_doc: int = 1,
    max_per_doc: int | None = None,
) -> dict[str, int]:
    """Round float allocations to integers, respecting min/max constraints.

    Adjusts for rounding drift by adding/removing from the largest allocations.

    Args:
        raw_alloc: Dictionary mapping doc_id to float allocation.
        total: Target total number of questions.
        min_per_doc: Minimum allocation per document.
        max_per_doc: Maximum allocation per document (None for no limit).

    Returns:
        Dictionary mapping doc_id to integer allocation.
    """
    int_alloc = {}
    for doc_id, val in raw_alloc.items():
        n = round(val)
        n = max(min_per_doc, n)
        if max_per_doc is not None:
            n = min(max_per_doc, n)
        int_alloc[doc_id] = n

    diff = total - sum(int_alloc.values())
    sorted_ids = sorted(
        int_alloc.keys(),
        key=lambda k: int_alloc[k],
        reverse=True,
    )

    if diff > 0:
        for doc_id in sorted_ids:
            if diff <= 0:
                break
            if max_per_doc is None or int_alloc[doc_id] < max_per_doc:
                int_alloc[doc_id] += 1
                diff -= 1
    elif diff < 0:
        for doc_id in sorted_ids:
            if diff >= 0:
                break
            if int_alloc[doc_id] > min_per_doc:
                int_alloc[doc_id] -= 1
                diff += 1

    return int_alloc


def detect_content_overlaps(
    documents: list[dict],
    threshold: float = 0.8,
) -> list[tuple[str, str, float]]:
    """Detect content overlap between document pairs.

    Samples 3 segments (beginning, middle, end) from the shorter document
    and checks if they appear in the longer document. If the hit rate
    exceeds the threshold, the shorter document is marked as supplementary.

    Args:
        documents: List of document dicts with 'doc_id' and 'content' keys.
        threshold: Minimum hit rate to mark as supplementary (default 0.8).

    Returns:
        List of tuples: (supplementary_doc_id, primary_doc_id, overlap_ratio).
    """
    overlaps: list[tuple[str, str, float]] = []

    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):
            doc_a = documents[i]
            doc_b = documents[j]
            len_a = len(doc_a["content"])
            len_b = len(doc_b["content"])

            if len_a <= len_b:
                shorter, longer = doc_a, doc_b
            else:
                shorter, longer = doc_b, doc_a

            short_text = re.sub(r"\s+", "", shorter["content"])
            long_text = re.sub(r"\s+", "", longer["content"])

            if len(short_text) < 100:
                continue

            sample_size = 500
            samples = [
                short_text[:sample_size],
                short_text[len(short_text) // 2 : len(short_text) // 2 + sample_size],
                short_text[-sample_size:],
            ]

            hits = sum(1 for s in samples if len(s) >= 50 and s in long_text)
            hit_rate = hits / len(samples)

            if hit_rate >= threshold:
                overlaps.append(
                    (
                        shorter["doc_id"],
                        longer["doc_id"],
                        hit_rate,
                    )
                )

    return overlaps


def build_primary_pool(
    documents: list[dict],
    overlaps: list[tuple[str, str, float]],
) -> list[dict]:
    """Build primary document pool, excluding supplementary documents.

    If document A is marked as supplementary to B, A is excluded from
    the primary pool. If A is supplementary to both B and C, only the
    longer one (B or C) is kept as the primary.

    Args:
        documents: List of document dicts.
        overlaps: Overlap tuples from detect_content_overlaps().

    Returns:
        List of primary document dicts (supplementary documents excluded).
    """
    supplementary_ids: set[str] = set()
    primary_map: dict[str, str] = {}

    for supp_id, primary_id, _ratio in overlaps:
        if supp_id not in supplementary_ids:
            supplementary_ids.add(supp_id)
            primary_map[supp_id] = primary_id
        else:
            existing_primary_id = primary_map[supp_id]
            existing_doc = next(
                (d for d in documents if d["doc_id"] == existing_primary_id),
                None,
            )
            new_doc = next(
                (d for d in documents if d["doc_id"] == primary_id),
                None,
            )
            if (
                new_doc
                and existing_doc
                and len(new_doc["content"]) > len(existing_doc["content"])
            ):
                primary_map[supp_id] = primary_id

    return [d for d in documents if d["doc_id"] not in supplementary_ids]


def validate_answer_numerical_accuracy(
    question_data: dict,
) -> tuple[bool, dict | None]:
    """Validate numerical accuracy in answer against ground_truth_excerpt.

    Detects 10x unit conversion errors where excerpt has large numbers
    in yuan but answer incorrectly converts to yi-yuan.

    Args:
        question_data: Dictionary containing 'answer' and 'ground_truth_excerpt'.

    Returns:
        Tuple of (is_valid, correction). is_valid is True if numbers are
        consistent. correction is None or contains fix information.
    """
    answer = question_data.get("answer", "")
    excerpt = question_data.get("ground_truth_excerpt", "")

    if not answer or not excerpt:
        return True, None

    excerpt_nums_raw = re.findall(r"[\d,]{8,}(?:\.\d+)?", excerpt)
    excerpt_yi_values: list[float] = []
    for raw_num in excerpt_nums_raw:
        try:
            clean = raw_num.replace(",", "")
            val = float(clean)
            yi_val = val / 1e8
            if yi_val > 1:
                excerpt_yi_values.append(yi_val)
        except ValueError:
            continue

    if not excerpt_yi_values:
        return True, None

    answer_yi_matches = re.findall(r"([\d,.]+)\s*亿", answer)
    answer_yi_values: list[float] = []
    for num_str in answer_yi_matches:
        try:
            answer_yi_values.append(float(num_str.replace(",", "")))
        except ValueError:
            continue

    if not answer_yi_values:
        return True, None

    errors: list[dict] = []
    for ans_val in answer_yi_values:
        for exc_val in excerpt_yi_values:
            if exc_val == 0:
                continue
            ratio = ans_val / exc_val
            if 9.5 <= ratio <= 10.5:
                errors.append(
                    {
                        "type": "10x_error",
                        "answer_value": ans_val,
                        "excerpt_value_yi": round(exc_val, 2),
                        "correct_value": round(exc_val, 2),
                    }
                )
            elif 0.05 <= ratio <= 0.15:
                errors.append(
                    {
                        "type": "10x_error_reverse",
                        "answer_value": ans_val,
                        "excerpt_value_yi": round(exc_val, 2),
                        "correct_value": round(exc_val, 2),
                    }
                )

    if errors:
        correction = {
            "errors": errors,
            "suggestion": "Answer contains 10x unit conversion errors. "
            "Values in yuan should be divided by 100,000,000 "
            "to convert to yi-yuan.",
        }
        return False, correction

    return True, None


def generate_single_question(
    document_content: str,
    question_type: str,
    generator: Generator,
    max_retries: int = 5,
) -> dict[str, Any] | None:
    """Generate a single golden question from a document.

    Args:
        document_content: Full text content of the document.
        question_type: Type of question to generate.
        generator: Generator instance for LLM calls.
        max_retries: Maximum number of retry attempts.

    Returns:
        Dictionary with question data, or None if generation fails.
    """
    type_cn = GOLDEN_QUESTION_TYPES.get(question_type, question_type)
    type_instruction = TYPE_INSTRUCTIONS.get(question_type, "")

    truncated_doc = document_content[:DOCUMENT_TRUNCATE_MAX]

    prompt = GOLDEN_PROMPT.format(
        document_content=truncated_doc,
        question_type=type_cn,
        question_type_en=question_type,
        type_specific_instruction=type_instruction,
    )

    for attempt in range(max_retries):
        try:
            response = generator.generate(
                query=prompt,
                contexts=[],
                system_prompt="你是一位资深金融行业QA工程师。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                category="golden_test_generation",
                allow_no_contexts=True,
            )

            qa = parse_question_response(response)
            if qa is not None and validate_question_quality(qa):
                qa["question_type"] = question_type
                return qa

            logger.debug(f"Attempt {attempt + 1}: failed to parse or validate")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

    return None


def parse_question_response(response: str) -> dict[str, Any] | None:
    """Parse an LLM response for golden question generation.

    Args:
        response: Raw LLM response string.

    Returns:
        Dictionary with question data, or None if parsing fails.
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

        required_fields = [
            "question",
            "answer",
            "question_type",
            "ground_truth_excerpt",
        ]
        for field in required_fields:
            if field not in qa:
                logger.debug(f"Missing required field: {field}")
                return None

        if not qa["question"]:
            return None

        qa.setdefault("difficulty", "medium")
        qa.setdefault("key_entities", [])
        qa.setdefault("target_failure_mode", "")

        return qa

    except (json.JSONDecodeError, KeyError) as e:
        logger.debug(f"Failed to parse LLM response as JSON: {str(e)}")
        return None


def validate_question_quality(question_data: dict) -> bool:
    """Validate the quality of a generated golden question.

    Args:
        question_data: Dictionary containing question data.

    Returns:
        True if the question passes quality checks, False otherwise.
    """
    question = question_data.get("question", "")
    answer = question_data.get("answer", "")
    excerpt = question_data.get("ground_truth_excerpt", "")

    if len(question) < 5:
        logger.debug("Question too short")
        return False

    if len(question) > 200:
        logger.debug("Question too long")
        return False

    if not answer and question_data.get("question_type") not in ("irrelevant",):
        logger.debug("Answer is empty for non-irrelevant question")
        return False

    if not excerpt and question_data.get("question_type") not in ("irrelevant",):
        logger.debug("ground_truth_excerpt is empty for non-irrelevant question")
        return False

    academic_patterns = [
        "根据文档",
        "根据提供的信息",
        "请分析",
        "请说明",
        "请对比",
        "请总结",
        "文档中提到",
        "片段中提到",
    ]
    for pattern in academic_patterns:
        if pattern in question:
            logger.debug(f"Question contains academic pattern: '{pattern}'")
            return False

    return True


def locate_source_chunks(
    ground_truth_excerpt: str,
    source_path: str,
    chunks_dir: Path,
) -> list[str]:
    """Locate chunk IDs that contain the ground truth excerpt.

    Uses exact substring matching of the excerpt against chunk text,
    which is more accurate than the keyword-based heuristic in
    TestSetGenerator._locate_answer_chunks().

    Args:
        ground_truth_excerpt: The excerpt text to locate in chunks.
        source_path: Relative path of the source document.
        chunks_dir: Path to the chunks directory.

    Returns:
        List of chunk_id strings for matched chunks.
    """
    if not ground_truth_excerpt or not source_path:
        return []

    if not chunks_dir.exists():
        logger.warning(f"Chunks directory not found: {chunks_dir}")
        return []

    normalized_source = source_path.replace("\\", "/")

    doc_chunks: list[dict[str, Any]] = []
    jsonl_files = list(chunks_dir.rglob("*.jsonl"))

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    chunk_source = (
                        chunk.get("metadata", {}).get("source", "").replace("\\", "/")
                    )
                    if chunk_source == normalized_source:
                        doc_chunks.append(chunk)
        except Exception as e:
            logger.warning(f"Failed to read {jsonl_file}: {str(e)}")
            continue

    if not doc_chunks:
        logger.debug(f"No chunks found for source_path: {source_path}")
        return []

    doc_chunks.sort(key=lambda c: c.get("metadata", {}).get("chunk_index", 0))

    excerpt_core = extract_excerpt_core(ground_truth_excerpt)

    matched_chunk_ids: list[str] = []
    for chunk in doc_chunks:
        chunk_text = chunk.get("text", "")
        if excerpt_core and excerpt_core in chunk_text:
            chunk_id = chunk.get("chunk_id", "")
            if chunk_id:
                matched_chunk_ids.append(chunk_id)

    if not matched_chunk_ids and doc_chunks:
        key_terms = extract_key_terms_from_excerpt(ground_truth_excerpt)
        if key_terms:
            best_chunk = None
            best_score = 0
            for chunk in doc_chunks:
                chunk_text = chunk.get("text", "")
                score = sum(1 for term in key_terms if term in chunk_text)
                if score > best_score:
                    best_score = score
                    best_chunk = chunk
            if best_chunk and best_score >= len(key_terms) * 0.5:
                chunk_id = best_chunk.get("chunk_id", "")
                if chunk_id:
                    matched_chunk_ids.append(chunk_id)

    return matched_chunk_ids


def extract_excerpt_core(excerpt: str, min_length: int = 20) -> str:
    """Extract the core substring from an excerpt for matching.

    Tries progressively shorter substrings from the beginning of the
    excerpt until finding one that is at least min_length characters.

    Args:
        excerpt: The full excerpt text.
        min_length: Minimum length for the core substring.

    Returns:
        Core substring suitable for exact matching, or empty string.
    """
    cleaned = re.sub(r"\s+", "", excerpt)
    if len(cleaned) >= min_length:
        return cleaned[: max(min_length, len(cleaned) // 2)]

    sentences = re.split(r"[。！？；\n]", excerpt)
    for sent in sentences:
        sent_clean = re.sub(r"\s+", "", sent)
        if len(sent_clean) >= min_length:
            return sent_clean

    return ""


def extract_key_terms_from_excerpt(excerpt: str) -> list[str]:
    """Extract key terms from an excerpt for fuzzy chunk matching.

    Args:
        excerpt: The excerpt text.

    Returns:
        List of key term strings.
    """
    terms = re.findall(r"[\u4e00-\u9fff]{2,4}|\d+\.?\d*%?", excerpt)
    stop_terms = {
        "的",
        "了",
        "在",
        "是",
        "和",
        "与",
        "或",
        "等",
        "为",
        "中",
        "对",
        "将",
    }
    return [t for t in terms if t not in stop_terms and len(t) >= 2]


def verify_excerpt_in_document(
    excerpt: str,
    document_content: str,
    min_overlap: int = 15,
) -> bool:
    """Verify that the excerpt can be found in the document content.

    Uses fuzzy matching: strips whitespace and checks for substring
    overlap of at least min_overlap consecutive characters.

    Args:
        excerpt: The ground truth excerpt to verify.
        document_content: The full document content to search in.
        min_overlap: Minimum number of consecutive matching characters.

    Returns:
        True if the excerpt (or a substantial part of it) is found.
    """
    if not excerpt:
        return False

    excerpt_clean = re.sub(r"\s+", "", excerpt)
    doc_clean = re.sub(r"\s+", "", document_content)

    if excerpt_clean in doc_clean:
        return True

    for start in range(0, len(excerpt_clean) - min_overlap + 1, min_overlap // 2):
        window = excerpt_clean[start : start + min_overlap]
        if len(window) >= min_overlap and window in doc_clean:
            return True

    return False


def generate_golden_testset(
    config: dict[str, Any],
    num_questions: int = 150,
    llm_preset: str = "default",
    output_path: Path | None = None,
    parsed_dir: Path | None = None,
    chunks_dir: Path | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a golden test set with LLM-assisted question generation.

    Args:
        config: Application configuration dictionary.
        num_questions: Total number of questions to generate.
        llm_preset: LLM preset name for generation.
        output_path: Path to save the output JSON file.
        parsed_dir: Path to the parsed documents directory.
        chunks_dir: Path to the chunks directory.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary containing the golden test set.
    """
    import random

    if parsed_dir is None:
        data_dir = config.get("data_dir", "data")
        parsed_dir = Path(data_dir) / "parsed"
    if chunks_dir is None:
        data_dir = config.get("data_dir", "data")
        chunks_dir = Path(data_dir) / "chunks"

    documents = load_documents(parsed_dir)
    if not documents:
        logger.error("No documents found in parsed directory")
        return {}

    logger.info(f"Loaded {len(documents)} documents")

    overlaps = detect_content_overlaps(documents)
    if overlaps:
        for supp_id, primary_id, ratio in overlaps:
            logger.info(
                f"Content overlap detected: {supp_id} is supplementary "
                f"to {primary_id} (overlap={ratio:.0%})"
            )

    primary_docs = build_primary_pool(documents, overlaps)
    logger.info(
        f"Primary document pool: {len(primary_docs)} documents "
        f"({len(documents) - len(primary_docs)} supplementary excluded)"
    )

    rng = random.Random(seed)
    rng.shuffle(primary_docs)

    type_counts = calculate_type_counts(num_questions, GOLDEN_TYPE_DISTRIBUTION)
    logger.info(f"Question type distribution: {type_counts}")

    doc_plans = distribute_across_documents(
        type_counts,
        primary_docs,
        seed=seed,
    )

    llm_config = get_llm_config(config, llm_preset)
    generator = Generator(
        model_name=llm_config["model_name"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=0.7,
        max_tokens=1024,
    )

    questions: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    question_id = 1
    total_attempts = 0
    failed_count = 0

    for doc_data in primary_docs:
        doc_id = doc_data["doc_id"]
        assigned_types = doc_plans.get(doc_id, [])
        if not assigned_types:
            continue

        if len(questions) >= num_questions:
            break

        doc_content = doc_data["content"]
        source_path = doc_data["source_path"]

        for q_type in assigned_types:
            if len(questions) >= num_questions:
                break

            total_attempts += 1
            logger.info(
                f"Generating question {len(questions) + 1}/{num_questions} "
                f"(type={q_type}, doc={doc_id})..."
            )

            qa = generate_single_question(doc_content, q_type, generator)

            if qa is not None:
                q_text = qa.get("question", "")
                if q_text in seen_questions:
                    logger.debug(f"Duplicate question skipped: {q_text[:50]}")
                    continue
                seen_questions.add(q_text)

                is_valid, correction = validate_answer_numerical_accuracy(qa)
                if not is_valid and correction:
                    logger.warning(
                        f"Numerical accuracy issue for question: "
                        f"{correction['suggestion']}"
                    )
                    for err in correction.get("errors", []):
                        wrong_val = err["answer_value"]
                        correct_val = err["correct_value"]
                        answer_text = qa.get("answer", "")
                        qa["answer"] = answer_text.replace(
                            f"{wrong_val}",
                            f"{correct_val}",
                        )
                        logger.warning(
                            f"Auto-corrected: {wrong_val}亿 → {correct_val}亿"
                        )
                    qa.setdefault("metadata", {})
                    qa["metadata"]["numerical_auto_corrected"] = True

                qa["id"] = f"golden_{question_id:03d}"
                qa["source_document"] = doc_data["name"]

                if q_type == "irrelevant":
                    qa["source_files"] = []
                    qa["source_chunks"] = []
                    qa["expect_retrieval"] = False
                    qa["expect_no_answer"] = False
                elif q_type == "missing":
                    qa["source_files"] = [source_path]
                    qa["source_chunks"] = []
                    qa["expect_retrieval"] = True
                    qa["expect_no_answer"] = True
                else:
                    qa["source_files"] = [source_path]
                    excerpt = qa.get("ground_truth_excerpt", "")
                    qa["source_chunks"] = locate_source_chunks(
                        excerpt,
                        source_path,
                        chunks_dir,
                    )
                    qa["expect_retrieval"] = True
                    qa["expect_no_answer"] = False

                qa.setdefault("metadata", {})
                qa["metadata"]["author"] = "llm_assisted"
                qa["metadata"]["reviewed"] = False
                qa["metadata"]["review_notes"] = ""
                if not qa["metadata"].get("target_failure_mode"):
                    qa["metadata"]["target_failure_mode"] = FAILURE_MODES.get(
                        q_type, ""
                    )

                excerpt = qa.get("ground_truth_excerpt", "")
                if excerpt and q_type not in ("irrelevant",):
                    excerpt_verified = verify_excerpt_in_document(
                        excerpt,
                        doc_content,
                    )
                    qa["metadata"]["excerpt_verified"] = excerpt_verified
                    if not excerpt_verified:
                        logger.warning(
                            f"ground_truth_excerpt not found in document "
                            f"for question {qa['id']}"
                        )

                questions.append(qa)
                question_id += 1
            else:
                failed_count += 1
                logger.warning(
                    f"Failed to generate question, total failures: "
                    f"{failed_count}/{total_attempts}"
                )

    if len(questions) < num_questions:
        deficit = num_questions - len(questions)
        logger.info(
            f"Main loop generated {len(questions)}/{num_questions}. "
            f"Supplementing {deficit} more..."
        )
        all_types = list(GOLDEN_TYPE_DISTRIBUTION.keys())
        extra_attempt = 0
        max_extra = deficit * 3

        while len(questions) < num_questions and extra_attempt < max_extra:
            extra_attempt += 1
            doc_data = primary_docs[extra_attempt % len(primary_docs)]
            q_type = all_types[extra_attempt % len(all_types)]
            doc_content = doc_data["content"]
            source_path = doc_data["source_path"]

            qa = generate_single_question(doc_content, q_type, generator)
            if qa is not None:
                q_text = qa.get("question", "")
                if q_text in seen_questions:
                    continue
                seen_questions.add(q_text)

                is_valid, correction = validate_answer_numerical_accuracy(qa)
                if not is_valid and correction:
                    logger.warning(
                        f"Numerical accuracy issue: {correction['suggestion']}"
                    )
                    for err in correction.get("errors", []):
                        wrong_val = err["answer_value"]
                        correct_val = err["correct_value"]
                        answer_text = qa.get("answer", "")
                        qa["answer"] = answer_text.replace(
                            f"{wrong_val}",
                            f"{correct_val}",
                        )
                    qa.setdefault("metadata", {})
                    qa["metadata"]["numerical_auto_corrected"] = True

                qa["id"] = f"golden_{question_id:03d}"
                qa["source_document"] = doc_data["name"]

                if q_type == "irrelevant":
                    qa["source_files"] = []
                    qa["source_chunks"] = []
                    qa["expect_retrieval"] = False
                    qa["expect_no_answer"] = False
                elif q_type == "missing":
                    qa["source_files"] = [source_path]
                    qa["source_chunks"] = []
                    qa["expect_retrieval"] = True
                    qa["expect_no_answer"] = True
                else:
                    qa["source_files"] = [source_path]
                    excerpt = qa.get("ground_truth_excerpt", "")
                    qa["source_chunks"] = locate_source_chunks(
                        excerpt,
                        source_path,
                        chunks_dir,
                    )
                    qa["expect_retrieval"] = True
                    qa["expect_no_answer"] = False

                qa.setdefault("metadata", {})
                qa["metadata"]["author"] = "llm_assisted"
                qa["metadata"]["reviewed"] = False
                qa["metadata"]["review_notes"] = ""
                if not qa["metadata"].get("target_failure_mode"):
                    qa["metadata"]["target_failure_mode"] = FAILURE_MODES.get(
                        q_type, ""
                    )

                questions.append(qa)
                question_id += 1
            else:
                failed_count += 1

    if not questions:
        logger.error("No questions could be generated")
        return {}

    type_dist = {}
    for q in questions:
        qt = q.get("question_type", "unknown")
        type_dist[qt] = type_dist.get(qt, 0) + 1

    excerpt_verified_count = sum(
        1 for q in questions if q.get("metadata", {}).get("excerpt_verified", False)
    )
    chunks_located_count = sum(1 for q in questions if q.get("source_chunks"))

    quality_metrics = {
        "total_questions": len(questions),
        "type_distribution": type_dist,
        "excerpt_verified_rate": (
            excerpt_verified_count / len(questions) if questions else 0.0
        ),
        "chunks_located_rate": (
            chunks_located_count / len(questions) if questions else 0.0
        ),
        "generation_failures": failed_count,
    }

    now = datetime.now().isoformat()

    test_set = {
        "metadata": {
            "name": "golden_150",
            "version": "1.0.0",
            "meal_id": "",
            "created_at": now,
            "updated_at": now,
            "generation": {
                "strategy": "golden",
                "num_questions": num_questions,
                "type_distribution": GOLDEN_TYPE_DISTRIBUTION,
                "llm_preset": llm_preset,
            },
            "user_defined": True,
            "invalid_policy": "immutable",
            "audit_log": [],
            "suppress_warnings": False,
            "composition": {
                "type": "golden",
                "documents_used": [d["source_path"] for d in primary_docs],
                "supplementary_excluded": [
                    d["source_path"]
                    for d in documents
                    if d["doc_id"] not in {pd["doc_id"] for pd in primary_docs}
                ],
            },
        },
        "quality_metrics": quality_metrics,
        "questions": questions,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(test_set, f, ensure_ascii=False, indent=2)
        logger.success(f"Golden test set saved to {output_path}")

    logger.success(
        f"Generated {len(questions)}/{num_questions} golden questions "
        f"(failures: {failed_count})"
    )

    return test_set


def main():
    """CLI entry point for golden test set generation.

    Delegates to TestSetGenerator.generate_golden_testset().
    """
    parser = argparse.ArgumentParser(
        description="Generate golden test set for RAG evaluation"
    )
    parser.add_argument(
        "--num-questions",
        type=int,
        default=150,
        help="Total number of questions to generate (default: 150)",
    )
    parser.add_argument(
        "--llm-preset",
        default="default",
        help="LLM preset name from config (default: default)",
    )
    parser.add_argument(
        "--name",
        default="golden_150",
        help="Name for the golden test set (default: golden_150)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args()

    config = load_config()

    from src.test_generator import TestSetGenerator

    generator = TestSetGenerator(config)
    generator.generate_golden_testset(
        num_questions=args.num_questions,
        name=args.name,
        llm_preset=args.llm_preset,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
