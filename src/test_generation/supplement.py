from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.exceptions import TestSetError
from src.generator import Generator
from src.meal import MealManager
from src.test_generation.chunk_locator import locate_answer_chunks
from src.test_generation.distribution import (
    calculate_question_distribution,
    distribute_questions_across_docs,
    save_test_set,
)
from src.test_generation.document_loader import (
    load_full_documents,
    resolve_chunks_dir,
)
from src.test_generation.llm_caller import generate_single_document_question
from src.test_generation.models import TYPE_DISTRIBUTION
from src.test_generation.validators import calculate_quality_metrics
from src.test_set_manager import TestSetMetadata
from src.utils import get_llm_config


def generate_document_based_questions(
    config: dict[str, Any],
    meal_name: str,
    num_questions: int,
    name: str,
    type_distribution: dict[str, float],
    llm_preset: str = "default",
    token_tracker: Any | None = None,
    chunks_dir: Path | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    max_retries: int = 3,
    doc_truncate_cache: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate questions based on full MD documents (non-hybrid path).

    Args:
        config: Application configuration dictionary.
        meal_name: Name of the meal to generate questions for.
        num_questions: Total number of questions to generate.
        name: Name for the test set.
        type_distribution: Distribution of question types.
        llm_preset: LLM preset name.
        token_tracker: Optional token usage tracker.
        chunks_dir: Optional path to chunks directory.
        temperature: LLM temperature.
        max_tokens: LLM max tokens.
        max_retries: Maximum retry attempts per question.
        doc_truncate_cache: Cache for truncated document content.

    Returns:
        Dictionary containing the test set metadata and generated questions.

    Raises:
        TestSetError: If no documents are found or no questions could be generated.
    """
    if doc_truncate_cache is None:
        doc_truncate_cache = {}

    meal_manager = MealManager(config)
    meal_config = meal_manager.load_meal(meal_name)

    logger.info(
        f"Generating document-based questions for meal '{meal_name}' "
        f"(num_questions={num_questions}, use_hybrid=False)"
    )

    document_contents = load_full_documents(config, meal_config)
    if not document_contents:
        raise TestSetError(f"No documents found for meal '{meal_name}'")

    logger.info(f"Loaded {len(document_contents)} documents")

    type_counts = calculate_question_distribution(num_questions, type_distribution)
    logger.info(f"Question type distribution: {type_counts}")

    doc_question_plans = distribute_questions_across_docs(
        type_counts, list(document_contents.keys())
    )
    num_docs = len(document_contents)

    logger.info(
        f"Distributing {num_questions} questions across {num_docs} "
        f"documents (~{num_questions // num_docs} per document)"
    )

    llm_config = get_llm_config(config, llm_preset)
    generator = Generator(
        model_name=llm_config["model_name"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=temperature,
        max_tokens=max_tokens,
        token_tracker=token_tracker,
    )

    questions: list[dict[str, Any]] = []
    question_id = 1
    total_attempts = 0
    failed_count = 0

    for doc_name, doc_data in document_contents.items():
        assigned_types = doc_question_plans.get(doc_name, [])
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

            qa = generate_single_document_question(
                doc_content,
                q_type,
                generator,
                max_retries,
                doc_truncate_cache,
            )

            if qa is not None:
                qa["id"] = f"q{question_id:03d}"
                qa["source_document"] = doc_name
                qa["category"] = "document"

                if q_type == "irrelevant":
                    qa["source_files"] = []
                    qa["source_chunks"] = []
                    qa["expect_retrieval"] = False
                elif q_type == "missing":
                    qa["source_files"] = [source_path]
                    qa["source_chunks"] = []
                    qa["expect_no_answer"] = True
                    qa["expect_retrieval"] = False
                else:
                    qa["source_files"] = [source_path]
                    answer_text = qa.get("answer", "")
                    resolved_dir = (
                        chunks_dir or resolve_chunks_dir(config, meal_config) or Path()
                    )
                    qa["source_chunks"] = locate_answer_chunks(
                        answer_text,
                        source_path,
                        resolved_dir,
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
            f"Main loop generated {len(questions)}/{num_questions} questions. "
            f"Supplementing {deficit} more questions..."
        )
        doc_names = list(document_contents.keys())
        all_types = list(type_distribution.keys())
        extra_attempt = 0
        max_extra_attempts = deficit * 3

        while len(questions) < num_questions and extra_attempt < max_extra_attempts:
            extra_attempt += 1
            doc_name = doc_names[extra_attempt % len(doc_names)]
            q_type = all_types[extra_attempt % len(all_types)]
            doc_data = document_contents[doc_name]
            doc_content = doc_data["content"]
            source_path = doc_data["source_path"]

            logger.info(
                f"Supplemental question {len(questions) + 1}/{num_questions} "
                f"(type={q_type}, doc={doc_name})..."
            )

            qa = generate_single_document_question(
                doc_content,
                q_type,
                generator,
                max_retries,
                doc_truncate_cache,
            )

            if qa is not None:
                qa["id"] = f"q{question_id:03d}"
                qa["source_document"] = doc_name
                qa["category"] = "document"

                if q_type == "irrelevant":
                    qa["source_files"] = []
                    qa["source_chunks"] = []
                    qa["expect_retrieval"] = False
                elif q_type == "missing":
                    qa["source_files"] = [source_path]
                    qa["source_chunks"] = []
                    qa["expect_no_answer"] = True
                    qa["expect_retrieval"] = False
                else:
                    qa["source_files"] = [source_path]
                    answer_text = qa.get("answer", "")
                    resolved_dir = (
                        chunks_dir or resolve_chunks_dir(config, meal_config) or Path()
                    )
                    qa["source_chunks"] = locate_answer_chunks(
                        answer_text,
                        source_path,
                        resolved_dir,
                    )

                questions.append(qa)
                question_id += 1
            else:
                failed_count += 1
                logger.warning(
                    f"Supplemental question failed, total failures: {failed_count}"
                )

    if not questions:
        raise TestSetError("No questions could be generated")

    quality_metrics = calculate_quality_metrics(questions)

    metadata = TestSetMetadata(
        name=name,
        meal_id=meal_config.data_id,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        generation={
            "strategy": "document",
            "num_questions": num_questions,
            "type_distribution": type_distribution,
            "llm_preset": llm_preset,
        },
        user_defined=False,
    )

    test_set = {
        "metadata": metadata.to_dict(),
        "quality_metrics": quality_metrics,
        "questions": questions,
    }

    save_test_set(config, meal_name, test_set, name)

    if len(questions) < num_questions:
        logger.warning(
            f"Could only generate {len(questions)}/{num_questions} questions "
            f"after supplemental attempts"
        )

    logger.success(
        f"Generated {len(questions)}/{num_questions} questions "
        f"for meal '{meal_name}' (strategy: document)"
    )
    return test_set


def supplement_document_based_questions(
    config: dict[str, Any],
    meal_name: str,
    existing_test_set: dict[str, Any],
    target_count: int,
    llm_preset: str = "default",
    token_tracker: Any | None = None,
    chunks_dir: Path | None = None,
    type_distribution: dict[str, float] | None = None,
    temperature: float = 0.7,
    supplement_max_tokens: int = 1024,
    max_retries: int = 3,
    doc_truncate_cache: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Supplement an existing test set with additional questions.

    Args:
        config: Application configuration dictionary.
        meal_name: Name of the meal to generate questions for.
        existing_test_set: Existing test set dictionary to supplement.
        target_count: Target total number of questions.
        llm_preset: LLM preset name.
        token_tracker: Optional token usage tracker.
        chunks_dir: Optional path to chunks directory.
        type_distribution: Distribution of question types.
        temperature: LLM temperature.
        supplement_max_tokens: LLM max tokens for supplement generation.
        max_retries: Maximum retry attempts per question.
        doc_truncate_cache: Cache for truncated document content.

    Returns:
        Updated test set dictionary with supplemented questions.

    Raises:
        TestSetError: If no documents are found for the meal.
    """
    if doc_truncate_cache is None:
        doc_truncate_cache = {}
    if type_distribution is None:
        type_distribution = TYPE_DISTRIBUTION

    existing_questions = existing_test_set.get("questions", [])
    deficit = target_count - len(existing_questions)

    if deficit <= 0:
        logger.info(
            f"Existing test set already has {len(existing_questions)} "
            f"questions, no supplementation needed"
        )
        return existing_test_set

    logger.info(
        f"Supplementing test set for meal '{meal_name}': "
        f"existing={len(existing_questions)}, target={target_count}, "
        f"deficit={deficit}"
    )

    meal_manager = MealManager(config)
    meal_config = meal_manager.load_meal(meal_name)

    document_contents = load_full_documents(config, meal_config)
    if not document_contents:
        raise TestSetError(f"No documents found for meal '{meal_name}'")

    llm_config = get_llm_config(config, llm_preset)
    generator = Generator(
        model_name=llm_config["model_name"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=temperature,
        max_tokens=supplement_max_tokens,
        token_tracker=token_tracker,
    )

    doc_names = list(document_contents.keys())
    all_types = list(type_distribution.keys())
    question_id = len(existing_questions) + 1
    new_questions: list[dict[str, Any]] = []
    failed_count = 0
    max_attempts = deficit * 3
    attempt = 0
    seen_questions: set[str] = {
        q.get("question", "") for q in existing_questions if q.get("question")
    }

    while len(new_questions) < deficit and attempt < max_attempts:
        attempt += 1
        doc_name = doc_names[attempt % len(doc_names)]
        q_type = all_types[attempt % len(all_types)]
        doc_data = document_contents[doc_name]
        doc_content = doc_data["content"]
        source_path = doc_data["source_path"]

        logger.info(
            f"Supplementing question {len(new_questions) + 1}/{deficit} "
            f"(type={q_type}, doc={doc_name})..."
        )

        qa = generate_single_document_question(
            doc_content,
            q_type,
            generator,
            max_retries,
            doc_truncate_cache,
        )

        if qa is not None:
            qa["id"] = f"q{question_id:03d}"
            qa["source_document"] = doc_name
            qa["category"] = "document"

            if q_type == "irrelevant":
                qa["source_files"] = []
                qa["source_chunks"] = []
                qa["expect_retrieval"] = False
            elif q_type == "missing":
                qa["source_files"] = [source_path]
                qa["source_chunks"] = []
                qa["expect_no_answer"] = True
                qa["expect_retrieval"] = False
            else:
                qa["source_files"] = [source_path]
                answer_text = qa.get("answer", "")
                resolved_dir = (
                    chunks_dir or resolve_chunks_dir(config, meal_config) or Path()
                )
                qa["source_chunks"] = locate_answer_chunks(
                    answer_text,
                    source_path,
                    resolved_dir,
                )

            question_text = qa.get("question", "")
            if question_text in seen_questions:
                logger.debug(f"Skipping duplicate question: {question_text[:50]}...")
                failed_count += 1
                continue

            new_questions.append(qa)
            seen_questions.add(question_text)
            question_id += 1
        else:
            failed_count += 1
            logger.warning(
                f"Supplemental question failed, total failures: "
                f"{failed_count}/{attempt}"
            )

    if not new_questions:
        logger.warning("Could not generate any supplemental questions")
        return existing_test_set

    all_questions = existing_questions + new_questions
    quality_metrics = calculate_quality_metrics(all_questions)

    existing_test_set["questions"] = all_questions
    existing_test_set["quality_metrics"] = quality_metrics

    if "metadata" in existing_test_set:
        existing_test_set["metadata"]["updated_at"] = datetime.now().isoformat()
        if "generation" in existing_test_set["metadata"]:
            existing_test_set["metadata"]["generation"]["num_questions"] = target_count
        audit_entry = {
            "event": "supplemented",
            "added_count": len(new_questions),
            "timestamp": datetime.now().isoformat(),
        }
        existing_test_set["metadata"].setdefault("audit_log", []).append(audit_entry)
        test_set_name = existing_test_set["metadata"]["name"]
    else:
        if "generation_config" not in existing_test_set:
            existing_test_set["generation_config"] = {}
        existing_test_set["generation_config"]["num_questions"] = target_count
        test_set_name = existing_test_set.get("name", f"document_level_n{target_count}")

    save_test_set(config, meal_name, existing_test_set, test_set_name)

    logger.success(
        f"Supplemented test set: {len(existing_questions)} + "
        f"{len(new_questions)} = {len(all_questions)}/{target_count} "
        f"questions for meal '{meal_name}'"
    )

    if len(all_questions) < target_count:
        logger.warning(
            f"Could only reach {len(all_questions)}/{target_count} "
            f"questions after supplementation"
        )

    return existing_test_set
