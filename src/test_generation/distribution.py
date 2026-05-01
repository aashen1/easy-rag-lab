import random as rng_module
from typing import Any


def calculate_question_distribution(
    num_questions: int,
    type_distribution: dict[str, float],
) -> dict[str, int]:
    """Calculate the number of questions for each type using largest remainder method.

    Args:
        num_questions: Total number of questions to generate.
        type_distribution: Dictionary mapping type names to proportions.

    Returns:
        Dictionary mapping type names to question counts.
    """
    if not type_distribution or num_questions <= 0:
        return {}

    total_proportion = sum(type_distribution.values())
    if total_proportion <= 0:
        n_types = len(type_distribution)
        return {t: num_questions // n_types for t in type_distribution}

    type_counts: dict[str, int] = {}
    allocated = 0
    remainders: list[tuple[str, float]] = []

    for q_type, proportion in type_distribution.items():
        normalized = proportion / total_proportion * num_questions
        floor_count = int(normalized)
        remainder = normalized - floor_count
        type_counts[q_type] = floor_count
        allocated += floor_count
        remainders.append((q_type, remainder))

    remainders.sort(key=lambda x: x[1], reverse=True)

    idx = 0
    while allocated < num_questions:
        q_type = remainders[idx % len(remainders)][0]
        type_counts[q_type] += 1
        allocated += 1
        idx += 1

    return type_counts


def distribute_questions_across_docs(
    type_counts: dict[str, int],
    doc_names: list[str],
    seed: int | None = None,
) -> dict[str, list[str]]:
    """Distribute question types across documents using round-robin.

    Args:
        type_counts: Dictionary mapping question type names to counts.
        doc_names: List of document names to distribute across.
        seed: Random seed for shuffling doc_names. If None, no shuffle.

    Returns:
        Dictionary mapping document names to their assigned question types.
    """
    shuffled_names = list(doc_names)
    if seed is not None:
        rng = rng_module.Random(seed)
        rng.shuffle(shuffled_names)

    question_plan: list[str] = []
    for q_type, count in type_counts.items():
        question_plan.extend([q_type] * count)

    num_docs = len(shuffled_names)
    doc_question_plans: dict[str, list[str]] = {name: [] for name in shuffled_names}
    for i, q_type in enumerate(question_plan):
        doc_name = shuffled_names[i % num_docs]
        doc_question_plans[doc_name].append(q_type)

    return doc_question_plans


def save_test_set(
    config: dict[str, Any], meal_name: str, test_set: dict[str, Any], name: str
) -> Any:
    from src.test_set_manager import TestSetManager

    if "metadata" in test_set:
        test_set["metadata"]["name"] = name
    test_set_manager = TestSetManager(config)
    return test_set_manager.save_test_set(meal_name, test_set)
