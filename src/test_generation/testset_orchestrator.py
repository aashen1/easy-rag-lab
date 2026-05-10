"""Test set orchestrator for coordinating test set generation.

This module provides the TestSetOrchestrator class that coordinates
the overall test set generation workflow.
"""

from typing import Any

from src.test_generation.generator import TestSetGenerator


class TestSetOrchestrator:
    """Orchestrator for test set generation workflow.

    This class coordinates the overall test set generation process,
    including document loading, question distribution, and test set assembly.

    Args:
        config: Application configuration dictionary.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._generator = TestSetGenerator(config)

    def generate_test_set(
        self,
        meal_name: str,
        strategy: str | None = None,
        num_questions: int | None = None,
        llm_preset: str = "default",
        seed: int | None = None,
        token_tracker: Any | None = None,
        type_distribution: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Generate a test set of Q&A pairs for a given meal.

        Args:
            meal_name: Name of the meal to generate questions for.
            strategy: Question generation strategy.
            num_questions: Number of questions to generate.
            llm_preset: LLM preset name.
            seed: Random seed for reproducibility.
            token_tracker: Optional token usage tracker.
            type_distribution: Optional type distribution override.

        Returns:
            Dictionary containing the test set metadata and generated questions.
        """
        return self._generator.generate_test_set(
            meal_name=meal_name,
            strategy=strategy,
            num_questions=num_questions,
            llm_preset=llm_preset,
            seed=seed,
            token_tracker=token_tracker,
            type_distribution=type_distribution,
        )

    def generate_golden_testset(
        self,
        num_questions: int = 150,
        name: str = "golden_150",
        llm_preset: str = "default",
        token_tracker: Any | None = None,
        type_distribution: dict[str, float] | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Generate a golden test set from the full dataset.

        Args:
            num_questions: Total number of questions to generate.
            name: Name for the golden test set.
            llm_preset: LLM preset name for generation.
            token_tracker: Optional token tracker.
            type_distribution: Override type distribution.
            seed: Random seed for reproducibility.

        Returns:
            Dictionary containing the golden test set.
        """
        return self._generator.generate_golden_testset(
            num_questions=num_questions,
            name=name,
            llm_preset=llm_preset,
            token_tracker=token_tracker,
            type_distribution=type_distribution,
            seed=seed,
        )

    def supplement_document_based_questions(
        self,
        meal_name: str,
        existing_test_set: dict[str, Any],
        target_count: int,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
        chunks_dir: Any | None = None,
    ) -> dict[str, Any]:
        """Supplement an existing test set with additional questions.

        Args:
            meal_name: Name of the meal to generate questions for.
            existing_test_set: Existing test set dictionary to supplement.
            target_count: Target total number of questions.
            llm_preset: LLM preset name.
            token_tracker: Optional token usage tracker.
            chunks_dir: Optional path to chunks directory.

        Returns:
            Updated test set dictionary with supplemented questions.
        """
        return self._generator.supplement_document_based_questions(
            meal_name=meal_name,
            existing_test_set=existing_test_set,
            target_count=target_count,
            llm_preset=llm_preset,
            token_tracker=token_tracker,
            chunks_dir=chunks_dir,
        )
