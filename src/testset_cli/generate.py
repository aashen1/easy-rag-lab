from __future__ import annotations

from loguru import logger

from src.utils import load_config


def run_generate(args) -> int:
    config = load_config()

    from src.meal import MealManager
    from src.test_generation.generator import TestSetGenerator

    meal_manager = MealManager(config)
    generator = TestSetGenerator(config)

    meal_name = args.meal
    strategy = args.strategy
    num_questions = args.num
    name = getattr(args, "name", None)
    llm_preset = getattr(args, "llm_preset", "default")
    seed = getattr(args, "seed", None)

    try:
        if strategy == "golden":
            test_set = generator.generate_golden_testset(
                num_questions=num_questions or 150,
                name=name or "golden_150",
                llm_preset=llm_preset,
                seed=seed,
            )
        elif strategy == "document":
            if not meal_manager.meal_exists(meal_name):
                logger.error(f"Meal '{meal_name}' not found")
                return 1
            test_set = generator.generate_document_based_questions(
                meal_name=meal_name,
                name=name,
                num_questions=num_questions,
                llm_preset=llm_preset,
            )
        elif strategy == "hybrid":
            if not meal_manager.meal_exists(meal_name):
                logger.error(f"Meal '{meal_name}' not found")
                return 1
            test_set = generator.generate_hybrid_questions(
                meal_name=meal_name,
                name=name,
                num_questions=num_questions,
                llm_preset=llm_preset,
            )
        else:
            if not meal_manager.meal_exists(meal_name):
                logger.error(f"Meal '{meal_name}' not found")
                return 1
            test_set = generator.generate_test_set(
                meal_name=meal_name,
                strategy=strategy,
                num_questions=num_questions,
                llm_preset=llm_preset,
                seed=seed,
            )

        test_set_name = test_set.get("name") or test_set.get("metadata", {}).get(
            "name", "unknown"
        )
        logger.success(
            f"Test set '{test_set_name}' generated for meal '{meal_name}' "
            f"({len(test_set['questions'])} questions, strategy: {strategy})"
        )
        return 0
    except Exception as e:
        logger.error(f"Failed to generate test set: {str(e)}")
        return 1
