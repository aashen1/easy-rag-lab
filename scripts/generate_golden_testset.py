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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generator import Generator
from src.utils import get_llm_config, load_config

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

GOLDEN_PROMPT = """你是一位资深金融行业QA工程师，正在为RAG问答系统编写高质量测试题。你需要基于以下文档内容，生成一道【{question_type}】类型的测试题。

## 核心要求

1. **问题必须能区分系统好坏**：好的RAG系统能答对，差的系统会答错或产生幻觉
2. **答案必须精确**：答案要直接引用文档中的具体数据或结论，不能模糊
3. **ground_truth_excerpt必须准确**：必须从原文中逐字摘录答案所在的关键片段（50-200字）

## 文档内容
---
{document_content}
---

## 问题类型说明

{type_description}

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
}}"""

SINGLE_FACT_DESCRIPTION = """单知识点查询：查询某个具体数据、事实或概念。
- 好的示例："2024年光模块市场规模多少？"、"CPO的全称是什么？"
- 关键：答案必须是文档中明确出现的具体数据或定义
- ground_truth_excerpt：包含该数据或定义的原文段落"""

MULTI_FACT_DESCRIPTION = """多知识点综合：需要整合文档中多个位置的信息才能回答。
- 好的示例："科瑞技术和猎奇智能在光模块设备上有什么区别？"
- 关键：答案不能仅凭文档中一个位置的信息得出，必须综合2+个信息点
- ground_truth_excerpt：包含主要信息点的原文段落（可以拼接2-3个片段）"""

REASONING_DESCRIPTION = """推理型问题：需要基于文档信息进行逻辑推理或判断。
- 好的示例："为什么CPO能降低功耗？"、"如果800G需求翻倍，对设备商有什么影响？"
- 关键：答案需要展示推理过程，推理依据必须来自文档
- ground_truth_excerpt：包含推理前提的原文段落"""

COMPARATIVE_DESCRIPTION = """对比分析：对比两个或多个对象的异同。
- 好的示例："中际旭创和新易盛哪个更值得投资？"、"CPO和LPO两种技术路线各有什么优缺点？"
- 关键：必须涉及文档中两个以上对象的对比
- ground_truth_excerpt：包含对比对象信息的原文段落"""

MISSING_DESCRIPTION = """缺失知识点：询问文档中没有或不完整的信息。
- 好的示例："光模块行业的ESG评级情况怎么样？"（文档未涉及ESG）
- 关键：答案必须明确说明"文档未提及该信息"或"文档信息不完整"
- ground_truth_excerpt：与问题最相关但确实不包含答案的原文段落"""

IRRELEVANT_DESCRIPTION = """无关问题：与文档主题完全无关的问题。
- 好的示例："新能源汽车的电池技术发展怎么样？"（文档是关于光模块的）
- 关键：问题必须与文档主题完全无关，测试系统的拒答能力
- ground_truth_excerpt：留空字符串"""

ADVERSARIAL_DESCRIPTION = """对抗性问题：故意设计容易让RAG系统出错的边界场景。
类型包括：
1. 数字近似陷阱：问一个与文档中数字接近但不相同的值
2. 跨文档混淆：问A公司数据但容易与B公司混淆
3. 时序陷阱：问文档未覆盖的时间段数据
4. 否定问题："以下哪个不是..."
5. 部分匹配陷阱：答案恰好跨越chunk边界

- 好的示例："光模块市场增长了15%吗？"（文档实际是12.5%，测试系统是否会纠正）
- 关键：问题中包含"诱饵"信息，好的系统应该能识别并纠正
- ground_truth_excerpt：包含正确信息的原文段落"""

TYPE_DESCRIPTIONS = {
    "single_fact": SINGLE_FACT_DESCRIPTION,
    "multi_fact": MULTI_FACT_DESCRIPTION,
    "reasoning": REASONING_DESCRIPTION,
    "comparative": COMPARATIVE_DESCRIPTION,
    "missing": MISSING_DESCRIPTION,
    "irrelevant": IRRELEVANT_DESCRIPTION,
    "adversarial": ADVERSARIAL_DESCRIPTION,
}

DOCUMENT_TRUNCATE_MAX = 10000


def load_documents(parsed_dir: Path) -> list[dict[str, str]]:
    """Load all MD documents from the parsed directory.

    Args:
        parsed_dir: Path to the directory containing parsed MD files.

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
            documents.append({
                "name": doc_name,
                "content": content,
                "source_path": rel_path,
            })
            logger.debug(f"Loaded document: {doc_name} ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Failed to load {md_file}: {str(e)}")

    return documents


def calculate_type_counts(num_questions: int, distribution: dict[str, float]) -> dict[str, int]:
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
    doc_names: list[str],
) -> dict[str, list[str]]:
    """Distribute question types across documents using round-robin.

    Args:
        type_counts: Dictionary mapping question type names to counts.
        doc_names: List of document names to distribute across.

    Returns:
        Dictionary mapping document names to their assigned question types.
    """
    question_plan = []
    for q_type, count in type_counts.items():
        question_plan.extend([q_type] * count)

    num_docs = len(doc_names)
    doc_plans: dict[str, list[str]] = {name: [] for name in doc_names}
    for i, q_type in enumerate(question_plan):
        doc_name = doc_names[i % num_docs]
        doc_plans[doc_name].append(q_type)

    return doc_plans


def generate_single_question(
    document_content: str,
    question_type: str,
    generator: Generator,
    max_retries: int = 3,
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
    type_desc = TYPE_DESCRIPTIONS.get(question_type, "")

    truncated_doc = document_content[:DOCUMENT_TRUNCATE_MAX]

    prompt = GOLDEN_PROMPT.format(
        document_content=truncated_doc,
        question_type=type_cn,
        question_type_en=question_type,
        type_description=type_desc,
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

        required_fields = ["question", "answer", "question_type", "ground_truth_excerpt"]
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
        "根据文档", "根据提供的信息", "请分析", "请说明",
        "请对比", "请总结", "文档中提到", "片段中提到",
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
                        chunk.get("metadata", {})
                        .get("source", "")
                        .replace("\\", "/")
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
        return cleaned[:max(min_length, len(cleaned) // 2)]

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
    stop_terms = {"的", "了", "在", "是", "和", "与", "或", "等", "为", "中", "对", "将"}
    return [t for t in terms if t not in stop_terms and len(t) >= 2]


def verify_excerpt_in_document(
    excerpt: str, document_content: str, min_overlap: int = 15,
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
) -> dict[str, Any]:
    """Generate a golden test set with LLM-assisted question generation.

    Args:
        config: Application configuration dictionary.
        num_questions: Total number of questions to generate.
        llm_preset: LLM preset name for generation.
        output_path: Path to save the output JSON file.
        parsed_dir: Path to the parsed documents directory.
        chunks_dir: Path to the chunks directory.

    Returns:
        Dictionary containing the golden test set.
    """
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

    type_counts = calculate_type_counts(num_questions, GOLDEN_TYPE_DISTRIBUTION)
    logger.info(f"Question type distribution: {type_counts}")

    doc_names = [d["name"] for d in documents]
    doc_plans = distribute_across_documents(type_counts, doc_names)

    llm_config = get_llm_config(config, llm_preset)
    generator = Generator(
        model_name=llm_config["model_name"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=0.7,
        max_tokens=1024,
    )

    questions: list[dict[str, Any]] = []
    question_id = 1
    total_attempts = 0
    failed_count = 0

    for doc_data in documents:
        doc_name = doc_data["name"]
        assigned_types = doc_plans.get(doc_name, [])
        if not assigned_types:
            continue

        doc_content = doc_data["content"]
        source_path = doc_data["source_path"]

        for q_type in assigned_types:
            total_attempts += 1
            logger.info(
                f"Generating question {question_id}/{num_questions} "
                f"(type={q_type}, doc={doc_name})..."
            )

            qa = generate_single_question(doc_content, q_type, generator)

            if qa is not None:
                qa["id"] = f"golden_{question_id:03d}"
                qa["source_document"] = doc_name

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
                        excerpt, source_path, chunks_dir,
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
                        excerpt, doc_content,
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
            doc_data = documents[extra_attempt % len(documents)]
            q_type = all_types[extra_attempt % len(all_types)]
            doc_content = doc_data["content"]
            source_path = doc_data["source_path"]

            qa = generate_single_question(doc_content, q_type, generator)
            if qa is not None:
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
                        excerpt, source_path, chunks_dir,
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

    seen_questions: set[str] = set()
    deduped_questions: list[dict[str, Any]] = []
    dup_count = 0
    for q in questions:
        q_text = q.get("question", "")
        if q_text in seen_questions:
            dup_count += 1
            continue
        seen_questions.add(q_text)
        deduped_questions.append(q)

    if dup_count > 0:
        logger.info(f"Removed {dup_count} duplicate questions")

    type_dist = {}
    for q in deduped_questions:
        qt = q.get("question_type", "unknown")
        type_dist[qt] = type_dist.get(qt, 0) + 1

    excerpt_verified_count = sum(
        1 for q in deduped_questions
        if q.get("metadata", {}).get("excerpt_verified", False)
    )
    chunks_located_count = sum(
        1 for q in deduped_questions
        if q.get("source_chunks")
    )

    quality_metrics = {
        "total_questions": len(deduped_questions),
        "type_distribution": type_dist,
        "excerpt_verified_rate": (
            excerpt_verified_count / len(deduped_questions)
            if deduped_questions
            else 0.0
        ),
        "chunks_located_rate": (
            chunks_located_count / len(deduped_questions)
            if deduped_questions
            else 0.0
        ),
        "generation_failures": failed_count,
        "duplicates_removed": dup_count,
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
                "documents_used": [d["source_path"] for d in documents],
            },
        },
        "quality_metrics": quality_metrics,
        "questions": deduped_questions,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(test_set, f, ensure_ascii=False, indent=2)
        logger.success(f"Golden test set saved to {output_path}")

    logger.success(
        f"Generated {len(deduped_questions)}/{num_questions} golden questions "
        f"(failures: {failed_count}, duplicates: {dup_count})"
    )

    return test_set


def main():
    """CLI entry point for golden test set generation."""
    parser = argparse.ArgumentParser(
        description="Generate golden test set for RAG evaluation"
    )
    parser.add_argument(
        "--num-questions", type=int, default=150,
        help="Total number of questions to generate (default: 150)",
    )
    parser.add_argument(
        "--llm-preset", default="default",
        help="LLM preset name from config (default: default)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file path (default: data/golden_testset/golden_150.json)",
    )
    parser.add_argument(
        "--parsed-dir", default=None,
        help="Parsed documents directory (default: data/parsed)",
    )
    parser.add_argument(
        "--chunks-dir", default=None,
        help="Chunks directory (default: data/chunks)",
    )
    args = parser.parse_args()

    config = load_config()

    output_path = Path(args.output) if args.output else Path("data/golden_testset/golden_150.json")
    parsed_dir = Path(args.parsed_dir) if args.parsed_dir else None
    chunks_dir = Path(args.chunks_dir) if args.chunks_dir else None

    generate_golden_testset(
        config=config,
        num_questions=args.num_questions,
        llm_preset=args.llm_preset,
        output_path=output_path,
        parsed_dir=parsed_dir,
        chunks_dir=chunks_dir,
    )


if __name__ == "__main__":
    main()
