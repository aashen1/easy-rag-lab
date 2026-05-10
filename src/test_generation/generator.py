import json
import random
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.exceptions import TestSetError
from src.generator import Generator
from src.meal import MealManager
from src.test_generation.chunk_locator import locate_source_chunks
from src.test_generation.distribution import (
    calculate_question_distribution,
    distribute_questions_across_docs,
)
from src.test_generation.document_loader import (
    load_document_chunks,
    load_document_pages,
    load_full_documents,
    load_meal_chunks,
)
from src.test_generation.llm_caller import (
    generate_irrelevant_question,
    generate_missing_question,
    generate_question_with_evidence,
    generate_question_with_llm,
)
from src.test_generation.models import (
    ANSWER_LENGTH_LIMITS,
    DOCUMENT_TRUNCATE_MAX,
    EVIDENCE_MAX_TOKENS,
    FAILURE_MODES,
    GOLDEN_TYPE_DISTRIBUTION,
    MIN_QUOTE_LENGTH,
    QUESTION_TYPES,
    TYPE_DISTRIBUTION,
    VALIDATION_STRICTNESS,
)
from src.test_generation.segment_builder import (
    build_segments_from_pages,
    compact_segments,
    segment_document,
    select_candidate_segments,
    select_segments_for_question_type,
)
from src.test_generation.supplement import (
    generate_document_based_questions as _generate_document_based_questions,
)
from src.test_generation.supplement import (
    supplement_document_based_questions as _supplement_document_based_questions,
)
from src.test_generation.validators import (
    build_primary_pool,
    calculate_hybrid_quality_metrics,
    detect_content_overlaps,
    validate_answer_consistency,
    validate_answer_evidence_consistency,
    validate_evidence,
    validate_numerical_accuracy,
    verify_excerpt_in_document,
)
from src.test_set_manager import TestSetManager, TestSetMetadata
from src.utils import get_llm_config


class TestSetGenerator:
    __test__ = False

    QUESTION_TYPES = QUESTION_TYPES
    TYPE_DISTRIBUTION = TYPE_DISTRIBUTION
    DOCUMENT_TRUNCATE_MAX = DOCUMENT_TRUNCATE_MAX
    GOLDEN_TYPE_DISTRIBUTION = GOLDEN_TYPE_DISTRIBUTION
    FAILURE_MODES = FAILURE_MODES
    MIN_QUOTE_LENGTH = MIN_QUOTE_LENGTH
    EVIDENCE_MAX_TOKENS = EVIDENCE_MAX_TOKENS
    ANSWER_LENGTH_LIMITS = ANSWER_LENGTH_LIMITS
    VALIDATION_STRICTNESS = VALIDATION_STRICTNESS

    def __init__(self, config: dict[str, Any]):
        """Initialize the TestSetGenerator with application configuration.

        Args:
            config: Application configuration dictionary containing a
                'test_generation' section with max_retries, default_strategy,
                and default_num_questions settings.
        """
        self.config = config
        tg_config = config.get("test_generation", {})
        self.max_retries = tg_config.get("max_retries", 3)
        self.default_strategy = tg_config.get("default_strategy", "factual")
        self.default_num_questions = tg_config.get("default_num_questions", 20)
        self.test_gen_model_name = tg_config.get("model_name")
        self.test_gen_temperature = tg_config.get("temperature", 0.7)
        self.test_gen_max_tokens = tg_config.get("max_tokens", 1024)
        self.test_gen_initial_max_tokens = tg_config.get("initial_max_tokens", 512)
        self.test_gen_supplement_max_tokens = tg_config.get(
            "supplement_max_tokens", 1024
        )
        self.segment_size = tg_config.get("segment_size", 8000)
        self.compact_segment_max_chars = tg_config.get(
            "compact_segment_max_chars", 6000
        )
        self.segment_sampling_strategy = tg_config.get(
            "segment_sampling_strategy", "random"
        )
        self.multi_hop_candidate_count = tg_config.get("multi_hop_candidate_count", 4)
        self.quote_fuzzy_match_threshold = tg_config.get(
            "quote_fuzzy_match_threshold", 0.85
        )
        validation_config = tg_config.get("validation", {})
        self.check_proper_nouns = validation_config.get("check_proper_nouns", True)
        self._doc_truncate_cache: dict[str, str] = {}

    def generate_test_set(
        self,
        meal_name: str,
        strategy: str = None,
        num_questions: int = None,
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

        Raises:
            TestSetError: If no chunks are found or no questions could be generated.
        """
        strategy = strategy or self.default_strategy
        num_questions = num_questions or self.default_num_questions

        normalized_strategy = strategy.replace("-", "_")

        if normalized_strategy == "hybrid":
            logger.info(f"Using hybrid strategy for meal '{meal_name}'")
            return self.generate_hybrid_questions(
                meal_name=meal_name,
                num_questions=num_questions,
                llm_preset=llm_preset,
                token_tracker=token_tracker,
                type_distribution=type_distribution,
            )

        if normalized_strategy == "document":
            logger.info(
                f"Using document strategy (delegates to hybrid) for meal '{meal_name}'"
            )
            return self.generate_document_based_questions(
                meal_name=meal_name,
                num_questions=num_questions,
                llm_preset=llm_preset,
                token_tracker=token_tracker,
                use_hybrid=True,
                type_distribution=type_distribution,
            )

        deprecated_strategies = {"factual", "boundary", "multi_hop"}
        if normalized_strategy in deprecated_strategies:
            deprecation_msg = (
                f"Strategy '{strategy}' is deprecated and will be removed in a future version. "
                f"Please use 'hybrid' strategy instead."
            )
            warnings.warn(deprecation_msg, DeprecationWarning, stacklevel=2)
            logger.warning(deprecation_msg)

        meal_manager = MealManager(self.config)
        meal_config = meal_manager.load_meal(meal_name)

        if seed is not None:
            random.seed(seed)

        logger.info(
            f"Generating test set for meal '{meal_name}' "
            f"(strategy={strategy}, num_questions={num_questions})"
        )

        chunks = load_meal_chunks(self.config, meal_config)
        if not chunks:
            raise TestSetError(f"No chunks found for meal '{meal_name}'")

        grouped = self._group_chunks_by_source(chunks)
        logger.info(f"Loaded {len(chunks)} chunks from {len(grouped)} source files")

        chunk_groups = self._select_chunks(grouped, strategy, num_questions)
        logger.info(
            f"Selected {len(chunk_groups)} chunk groups for question generation"
        )

        llm_config = get_llm_config(self.config, llm_preset)
        generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=self.test_gen_temperature,
            max_tokens=self.test_gen_initial_max_tokens,
            token_tracker=token_tracker,
        )

        questions = []
        for i, chunk_group in enumerate(chunk_groups):
            logger.info(f"Generating question {i + 1}/{len(chunk_groups)}...")
            qa = generate_question_with_llm(
                chunk_group, strategy, generator, self.max_retries
            )
            if qa is not None:
                source_files = list(
                    {
                        c.get("metadata", {}).get("source", "unknown")
                        for c in chunk_group
                    }
                )
                source_chunks = [c.get("chunk_id", f"chunk_{i}") for c in chunk_group]
                qa["id"] = f"q{i + 1:03d}"
                qa["source_chunks"] = source_chunks
                qa["source_files"] = source_files
                qa["category"] = strategy
                questions.append(qa)
            else:
                logger.warning(f"Failed to generate question {i + 1}, skipping")

        if not questions:
            raise TestSetError("No questions could be generated")

        test_set = {
            "name": f"auto_{strategy}_n{num_questions}",
            "meal_data_id": meal_config.data_id,
            "meal_name": meal_name,
            "strategy": strategy,
            "created_at": datetime.now().isoformat(),
            "generation_config": {
                "num_questions": num_questions,
                "llm_preset": llm_preset,
                "seed": seed,
            },
            "questions": questions,
        }

        filename = f"auto_{strategy}_n{num_questions}"
        self._save_test_set(meal_name, test_set, filename)

        logger.success(
            f"Generated {len(questions)}/{num_questions} questions "
            f"for meal '{meal_name}' (strategy: {strategy})"
        )
        return test_set

    def _group_chunks_by_source(self, chunks: list[dict]) -> dict[str, list[dict]]:
        """Group chunks by their source file metadata.

        Args:
            chunks: List of chunk dictionaries.

        Returns:
            Dictionary mapping source file names to lists of chunk dictionaries.
        """
        grouped = {}
        for chunk in chunks:
            source = chunk.get("metadata", {}).get("source", "unknown")
            if source not in grouped:
                grouped[source] = []
            grouped[source].append(chunk)

        for source in grouped:
            grouped[source].sort(
                key=lambda c: c.get("metadata", {}).get("chunk_index", 0)
            )

        return grouped

    def _select_chunks(
        self,
        grouped_chunks: dict[str, list[dict]],
        strategy: str,
        num_questions: int,
    ) -> list[list[dict]]:
        """Select chunk groups for question generation based on the strategy.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            strategy: Question generation strategy.
            num_questions: Target number of chunk groups.

        Returns:
            List of chunk groups.

        Raises:
            ValueError: If the strategy is not recognized.
        """
        normalized_strategy = strategy.replace("-", "_")
        if normalized_strategy == "factual":
            return self._select_chunks_for_factual(grouped_chunks, num_questions)
        elif normalized_strategy == "boundary":
            return self._select_chunks_for_boundary(grouped_chunks, num_questions)
        elif normalized_strategy == "multi_hop":
            return self._select_chunks_for_multi_hop(grouped_chunks, num_questions)
        else:
            raise TestSetError(f"Unknown strategy: {strategy}")

    def _select_chunks_for_factual(
        self, grouped_chunks: dict[str, list[dict]], num_questions: int
    ) -> list[list[dict]]:
        """Select individual chunks randomly for factual question generation.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            num_questions: Target number of chunks to select.

        Returns:
            List of single-element chunk lists.
        """
        all_chunks = []
        for chunks in grouped_chunks.values():
            all_chunks.extend(chunks)

        if not all_chunks:
            return []

        selected = random.sample(all_chunks, min(num_questions, len(all_chunks)))
        return [[c] for c in selected]

    def _select_chunks_for_boundary(
        self, grouped_chunks: dict[str, list[dict]], num_questions: int
    ) -> list[list[dict]]:
        """Select adjacent chunk pairs for boundary question generation.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            num_questions: Target number of chunk pairs.

        Returns:
            List of two-element chunk lists.
        """
        pairs = []
        for _source, chunks in grouped_chunks.items():
            for i in range(len(chunks) - 1):
                idx_i = chunks[i].get("metadata", {}).get("chunk_index", i)
                idx_next = chunks[i + 1].get("metadata", {}).get("chunk_index", i + 1)
                if idx_next == idx_i + 1:
                    pairs.append([chunks[i], chunks[i + 1]])

        if not pairs:
            logger.warning("No adjacent chunk pairs found for boundary strategy")
            return []

        return random.sample(pairs, min(num_questions, len(pairs)))

    def _select_chunks_for_multi_hop(
        self, grouped_chunks: dict[str, list[dict]], num_questions: int
    ) -> list[list[dict]]:
        """Select non-adjacent chunk pairs for multi-hop question generation.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            num_questions: Target number of chunk pairs.

        Returns:
            List of two-element chunk lists.
        """
        groups = []
        for _source, chunks in grouped_chunks.items():
            if len(chunks) >= 3:
                for i in range(len(chunks)):
                    for j in range(i + 2, min(i + 5, len(chunks))):
                        groups.append([chunks[i], chunks[j]])

        if not groups:
            logger.warning("No non-adjacent chunk groups found for multi_hop strategy")
            return []

        return random.sample(groups, min(num_questions, len(groups)))

    def _save_test_set(
        self, meal_name: str, test_set: dict[str, Any], name: str
    ) -> Path:
        """Save a test set to a JSON file in the meal's test_sets directory.

        Args:
            meal_name: Name of the meal the test set belongs to.
            test_set: Test set dictionary to serialize.
            name: Name for the test set file (without extension).

        Returns:
            Path to the saved JSON file.
        """
        if "metadata" in test_set:
            test_set["metadata"]["name"] = name
        test_set_manager = TestSetManager(self.config)
        return test_set_manager.save_test_set(meal_name, test_set)

    def _prepare_document_segments(
        self,
        doc_name: str,
        doc_data: dict,
        doc_pages_map: dict,
    ) -> list[dict[str, Any]]:
        """Prepare segments for a document from pages or content.

        Args:
            doc_name: Document name.
            doc_data: Document data dict with 'content' key.
            doc_pages_map: Map of doc names to page lists.

        Returns:
            List of segment dictionaries.
        """
        pages = doc_pages_map.get(doc_name, [])
        if pages:
            return build_segments_from_pages(pages, self.segment_size)
        else:
            segments = segment_document(doc_data["content"], self.segment_size)
            for seg in segments:
                seg["page_numbers"] = []
                seg["source_type"] = "fallback"
            return segments

    def _create_question_metadata(
        self,
        qa: dict,
        q_type: str,
        source_path: str,
        doc_name: str,
        question_id: int,
        category: str,
    ) -> dict:
        """Add standard metadata fields to a question dict.

        Args:
            qa: Question-answer dictionary to update.
            q_type: Question type.
            source_path: Source file path.
            doc_name: Document name.
            question_id: Question ID number.
            category: Category label (e.g., 'hybrid', 'golden').

        Returns:
            Updated question dictionary.
        """
        qa["id"] = (
            f"{category}_{question_id:03d}"
            if category == "golden"
            else f"q{question_id:03d}"
        )
        qa["source_document"] = doc_name
        qa["category"] = category

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

        return qa

    def _build_weighted_type_selector(
        self, type_distribution: dict[str, float]
    ) -> list[tuple[str, float]]:
        """Build a weighted type selector for random type selection.

        Args:
            type_distribution: Dict mapping type names to weights.

        Returns:
            List of (type, cumulative_threshold) tuples.
        """
        all_types = list(type_distribution.keys())
        type_weights = [type_distribution[t] for t in all_types]
        total_weight = sum(type_weights)

        if total_weight > 0:
            cumulative = 0.0
            weighted_types = []
            for t, w in zip(all_types, type_weights, strict=False):
                cumulative += w / total_weight
                weighted_types.append((t, cumulative))
            return weighted_types
        else:
            step = 1.0 / len(all_types)
            return [(t, (i + 1) * step) for i, t in enumerate(all_types)]

    def _select_weighted_type(
        self,
        weighted_types: list[tuple[str, float]],
        type_deficits: dict[str, int] | None = None,
        attempt_index: int = 0,
    ) -> str:
        """Select a question type using weighted distribution or deficit priority.

        Args:
            weighted_types: List of (type, cumulative_threshold) tuples.
            type_deficits: Optional dict of type deficits to prioritize.
            attempt_index: Index for round-robin selection from deficit types.

        Returns:
            Selected question type string.
        """
        if type_deficits:
            max_deficit = max(type_deficits.values())
            deficit_types = [t for t, d in type_deficits.items() if d == max_deficit]
            return deficit_types[attempt_index % len(deficit_types)]

        r = random.random()
        for t, threshold in weighted_types:
            if r <= threshold:
                return t
        return weighted_types[0][0]

    def generate_hybrid_questions(
        self,
        meal_name: str,
        num_questions: int | None = None,
        name: str | None = None,
        type_distribution: dict[str, float] | None = None,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
        chunks_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Generate questions using hybrid segment-chunk strategy.

        Args:
            meal_name: Name of the meal to generate questions for.
            num_questions: Total number of questions to generate.
            name: Name for the test set.
            type_distribution: Custom distribution of question types.
            llm_preset: LLM preset name.
            token_tracker: Optional token usage tracker.
            chunks_dir: Optional path to chunks directory.

        Returns:
            Dictionary containing the test set metadata and generated questions.

        Raises:
            TestSetError: If no documents are found or no questions could be generated.
        """
        num_questions = num_questions or self.default_num_questions
        name = name or f"hybrid_n{num_questions}"
        type_distribution = type_distribution or self.TYPE_DISTRIBUTION

        meal_manager = MealManager(self.config)
        meal_config = meal_manager.load_meal(meal_name)

        logger.info(
            f"Generating hybrid questions for meal '{meal_name}' "
            f"(num_questions={num_questions})"
        )

        document_contents = load_full_documents(self.config, meal_config)
        if not document_contents:
            raise TestSetError(f"No documents found for meal '{meal_name}'")

        logger.info(f"Loaded {len(document_contents)} documents")

        doc_chunks_map = load_document_chunks(
            self.config, meal_config, document_contents, chunks_dir
        )

        doc_pages_map = load_document_pages(self.config, meal_config)

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

        llm_config = get_llm_config(self.config, llm_preset)
        generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=self.test_gen_temperature,
            max_tokens=self.test_gen_max_tokens,
            token_tracker=token_tracker,
        )

        concurrent_gen = self.config.get("test_generation", {}).get(
            "concurrent_generation", 1
        )

        questions = []
        question_id = 1
        total_attempts = 0
        failed_count = 0
        seen_questions: set[str] = set()

        _id_lock = threading.Lock()
        _list_lock = threading.Lock()

        def _make_generator():
            return Generator(
                model_name=llm_config["model_name"],
                api_key=llm_config["api_key"],
                base_url=llm_config["base_url"],
                temperature=self.test_gen_temperature,
                max_tokens=self.test_gen_max_tokens,
                token_tracker=token_tracker,
            )

        generators = [generator]
        for _ in range(max(0, concurrent_gen - 1)):
            generators.append(_make_generator())

        _gen_idx = [0]

        def assign_generator():
            with _gen_lock:
                idx = _gen_idx[0] % len(generators)
                _gen_idx[0] += 1
                return generators[idx]

        _gen_lock = threading.Lock()

        def _generate_one(
            segments, doc_chunks, q_type, source_path, doc_name, doc_content
        ):
            gen = assign_generator()
            qa = self._generate_hybrid_question(
                segments=segments,
                doc_chunks=doc_chunks,
                question_type=q_type,
                generator=gen,
                source_path=source_path,
                doc_name=doc_name,
                doc_content=doc_content,
            )
            return qa, q_type, source_path

        for doc_name, doc_data in document_contents.items():
            assigned_types = doc_question_plans.get(doc_name, [])
            if not assigned_types:
                continue

            doc_content = doc_data["content"]
            source_path = doc_data["source_path"]
            doc_chunks = doc_chunks_map.get(doc_name, [])

            segments = self._prepare_document_segments(
                doc_name, doc_data, doc_pages_map
            )
            if not segments:
                logger.warning(f"No segments generated for document: {doc_name}")
                continue

            if concurrent_gen > 1 and len(assigned_types) > 1:
                with ThreadPoolExecutor(
                    max_workers=min(concurrent_gen, len(assigned_types))
                ) as pool:
                    futures = {}
                    for q_type in assigned_types:
                        future = pool.submit(
                            _generate_one,
                            segments,
                            doc_chunks,
                            q_type,
                            source_path,
                            doc_name,
                            doc_content,
                        )
                        futures[future] = q_type

                    for future in as_completed(futures):
                        q_type = futures[future]
                        total_attempts += 1
                        try:
                            qa, actual_type, src_path = future.result()
                        except Exception as e:
                            logger.warning(f"Concurrent generation failed: {e}")
                            with _list_lock:
                                failed_count += 1
                            continue

                        if qa is not None:
                            with _id_lock:
                                qa["id"] = f"q{question_id:03d}"
                                question_id += 1
                            qa["source_document"] = doc_name
                            qa["category"] = "hybrid"

                            if actual_type == "irrelevant":
                                qa["source_files"] = []
                                qa["source_chunks"] = []
                                qa["expect_retrieval"] = False
                            elif actual_type == "missing":
                                qa["source_files"] = [src_path]
                                qa["source_chunks"] = []
                                qa["expect_no_answer"] = True
                                qa["expect_retrieval"] = False
                            else:
                                qa["source_files"] = [src_path]

                            with _list_lock:
                                if self._post_process_question(
                                    qa, doc_content, seen_questions
                                ):
                                    questions.append(qa)
                                else:
                                    failed_count += 1
                        else:
                            with _list_lock:
                                failed_count += 1
                            logger.warning(
                                f"Failed to generate question, total failures: "
                                f"{failed_count}/{total_attempts}"
                            )
            else:
                for q_type in assigned_types:
                    total_attempts += 1
                    logger.info(
                        f"Generating question {question_id}/{num_questions} "
                        f"(type={q_type}, doc={doc_name})..."
                    )

                    qa = self._generate_hybrid_question(
                        segments=segments,
                        doc_chunks=doc_chunks,
                        question_type=q_type,
                        generator=generator,
                        source_path=source_path,
                        doc_name=doc_name,
                        doc_content=doc_content,
                    )

                    if qa is not None:
                        qa["id"] = f"q{question_id:03d}"
                        qa["source_document"] = doc_name
                        qa["category"] = "hybrid"

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

                        if self._post_process_question(qa, doc_content, seen_questions):
                            questions.append(qa)
                            question_id += 1
                        else:
                            failed_count += 1
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
            weighted_types = self._build_weighted_type_selector(type_distribution)
            extra_attempt = 0
            max_extra_attempts = deficit * 3

            while len(questions) < num_questions and extra_attempt < max_extra_attempts:
                extra_attempt += 1
                doc_name = doc_names[extra_attempt % len(doc_names)]
                q_type = self._select_weighted_type(weighted_types)
                doc_data = document_contents[doc_name]
                doc_content = doc_data["content"]
                source_path = doc_data["source_path"]
                doc_chunks = doc_chunks_map.get(doc_name, [])

                segments = self._prepare_document_segments(
                    doc_name, doc_data, doc_pages_map
                )
                if not segments:
                    continue

                logger.info(
                    f"Supplemental question {len(questions) + 1}/{num_questions} "
                    f"(type={q_type}, doc={doc_name})..."
                )

                qa = self._generate_hybrid_question(
                    segments=segments,
                    doc_chunks=doc_chunks,
                    question_type=q_type,
                    generator=generator,
                    source_path=source_path,
                    doc_name=doc_name,
                    doc_content=doc_content,
                )

                if qa is not None:
                    self._create_question_metadata(
                        qa, q_type, source_path, doc_name, question_id, "hybrid"
                    )
                    if self._post_process_question(qa, doc_content, seen_questions):
                        questions.append(qa)
                        question_id += 1
                    else:
                        failed_count += 1
                else:
                    failed_count += 1
                    logger.warning(
                        f"Supplemental question failed, total failures: {failed_count}"
                    )

        if not questions:
            raise TestSetError("No questions could be generated")

        quality_metrics = calculate_hybrid_quality_metrics(questions)

        metadata = TestSetMetadata(
            name=name,
            meal_id=meal_config.data_id,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            generation={
                "strategy": "hybrid",
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

        self._save_test_set(meal_name, test_set, name)

        if len(questions) < num_questions:
            logger.warning(
                f"Could only generate {len(questions)}/{num_questions} questions "
                f"after supplemental attempts"
            )

        logger.success(
            f"Generated {len(questions)}/{num_questions} questions "
            f"for meal '{meal_name}' (strategy: hybrid)"
        )
        return test_set

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

        Raises:
            TestSetError: If no full-dataset meal is found or generation fails.
        """
        import random as rng_module

        from src.meal import MealManager

        meal_manager = MealManager(self.config)
        meal_config = meal_manager.find_full_dataset_meal()

        if meal_config is None:
            raise TestSetError(
                "No full-dataset meal found. Create a meal with "
                "sampling=1.0 (i.e. include all PDFs) first."
            )

        logger.info(
            f"Using full-dataset meal '{meal_config.name}' "
            f"for golden test set generation"
        )

        if type_distribution is None:
            type_distribution = self.GOLDEN_TYPE_DISTRIBUTION

        if seed is not None:
            rng_module.seed(seed)

        document_contents = load_full_documents(self.config, meal_config)
        if not document_contents:
            raise TestSetError(f"No documents found for meal '{meal_config.name}'")

        logger.info(f"Loaded {len(document_contents)} documents")

        doc_chunks_map = load_document_chunks(
            self.config, meal_config, document_contents
        )

        doc_pages_map = load_document_pages(self.config, meal_config)

        doc_list = [
            {"doc_id": doc_name, "content": doc_data["content"]}
            for doc_name, doc_data in document_contents.items()
        ]
        overlaps = detect_content_overlaps(doc_list)
        if overlaps:
            for supp_id, primary_id, ratio in overlaps:
                logger.info(
                    f"Content overlap: {supp_id} is supplementary "
                    f"to {primary_id} (overlap={ratio:.0%})"
                )

        primary_pool = build_primary_pool(doc_list, overlaps)
        primary_names = {d["doc_id"] for d in primary_pool}

        if len(primary_names) < len(document_contents):
            excluded = set(document_contents.keys()) - primary_names
            logger.info(
                f"Primary pool: {len(primary_names)} documents "
                f"({len(excluded)} supplementary excluded: {excluded})"
            )
            filtered_contents = {
                k: v for k, v in document_contents.items() if k in primary_names
            }
        else:
            filtered_contents = document_contents

        type_counts = calculate_question_distribution(num_questions, type_distribution)
        logger.info(f"Golden type distribution: {type_counts}")

        doc_question_plans = distribute_questions_across_docs(
            type_counts, list(filtered_contents.keys()), seed=seed
        )

        llm_config = get_llm_config(self.config, llm_preset)
        generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=self.test_gen_temperature,
            max_tokens=self.test_gen_max_tokens,
            token_tracker=token_tracker,
        )

        questions: list[dict[str, Any]] = []
        question_id = 1
        total_attempts = 0
        failed_count = 0
        seen_questions: set[str] = set()

        for doc_name, doc_data in filtered_contents.items():
            assigned_types = doc_question_plans.get(doc_name, [])
            if not assigned_types:
                continue

            doc_content = doc_data["content"]
            source_path = doc_data["source_path"]
            doc_chunks = doc_chunks_map.get(doc_name, [])

            segments = self._prepare_document_segments(
                doc_name, doc_data, doc_pages_map
            )
            if not segments:
                logger.warning(f"No segments for document: {doc_name}")
                continue

            for q_type in assigned_types:
                if len(questions) >= num_questions:
                    break
                total_attempts += 1
                logger.info(
                    f"Generating question {len(questions) + 1}/{num_questions} "
                    f"(type={q_type}, doc={doc_name})..."
                )

                qa = self._generate_hybrid_question(
                    segments=segments,
                    doc_chunks=doc_chunks,
                    question_type=q_type,
                    generator=generator,
                    source_path=source_path,
                    doc_name=doc_name,
                    doc_content=doc_content,
                )

                if qa is not None:
                    self._create_question_metadata(
                        qa, q_type, source_path, doc_name, question_id, "golden"
                    )
                    if self._post_process_question(
                        qa,
                        doc_content,
                        seen_questions,
                        check_answer_consistency=True,
                        golden_metadata={},
                    ):
                        questions.append(qa)
                        question_id += 1
                    else:
                        failed_count += 1
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

            actual_type_counts: dict[str, int] = {}
            for q in questions:
                qt = q.get("question_type", "")
                qt_key = self._chinese_to_type_key(qt)
                if qt_key:
                    actual_type_counts[qt_key] = actual_type_counts.get(qt_key, 0) + 1

            type_deficits: dict[str, int] = {}
            for qt, target in type_counts.items():
                actual = actual_type_counts.get(qt, 0)
                gap = target - actual
                if gap > 0:
                    type_deficits[qt] = gap

            if type_deficits:
                logger.info(f"Type deficits after main loop: {type_deficits}")

            doc_names = list(filtered_contents.keys())
            weighted_types = self._build_weighted_type_selector(type_distribution)
            extra_attempt = 0
            max_extra_attempts = deficit * 3

            while len(questions) < num_questions and extra_attempt < max_extra_attempts:
                extra_attempt += 1
                doc_name = doc_names[extra_attempt % len(doc_names)]

                q_type = self._select_weighted_type(
                    weighted_types,
                    type_deficits if type_deficits else None,
                    extra_attempt,
                )
                doc_data = filtered_contents[doc_name]
                doc_content = doc_data["content"]
                source_path = doc_data["source_path"]
                doc_chunks = doc_chunks_map.get(doc_name, [])

                segments = self._prepare_document_segments(
                    doc_name, doc_data, doc_pages_map
                )
                if not segments:
                    continue

                logger.info(
                    f"Supplemental question {len(questions) + 1}/{num_questions} "
                    f"(type={q_type}, doc={doc_name})..."
                )

                qa = self._generate_hybrid_question(
                    segments=segments,
                    doc_chunks=doc_chunks,
                    question_type=q_type,
                    generator=generator,
                    source_path=source_path,
                    doc_name=doc_name,
                    doc_content=doc_content,
                )

                if qa is not None:
                    self._create_question_metadata(
                        qa, q_type, source_path, doc_name, question_id, "golden"
                    )

                    if self._post_process_question(
                        qa,
                        doc_content,
                        seen_questions,
                        check_answer_consistency=True,
                        golden_metadata={},
                    ):
                        questions.append(qa)
                        question_id += 1

                        if q_type in type_deficits:
                            type_deficits[q_type] -= 1
                            if type_deficits[q_type] <= 0:
                                del type_deficits[q_type]
                                if type_deficits:
                                    logger.debug(
                                        f"Remaining type deficits: {type_deficits}"
                                    )
                    else:
                        failed_count += 1
                else:
                    failed_count += 1
                    logger.warning(
                        f"Supplemental question failed, total failures: {failed_count}"
                    )

        if not questions:
            raise TestSetError("No golden questions could be generated")

        quality_metrics = calculate_hybrid_quality_metrics(questions)

        metadata = TestSetMetadata(
            name=name,
            meal_id=meal_config.data_id,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            generation={
                "strategy": "golden",
                "num_questions": num_questions,
                "type_distribution": type_distribution,
                "llm_preset": llm_preset,
                "seed": seed,
            },
            user_defined=True,
            invalid_policy="immutable",
        )

        test_set = {
            "metadata": metadata.to_dict(),
            "quality_metrics": quality_metrics,
            "questions": questions,
        }

        golden_dir = Path(self.config.get("data_dir", "data")) / "golden_testset"
        golden_dir.mkdir(parents=True, exist_ok=True)
        output_path = golden_dir / f"{name}.json"

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(test_set, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved golden test set '{name}' to {output_path}")
        except Exception as e:
            raise TestSetError(
                f"Failed to save golden test set '{name}': {str(e)}"
            ) from e

        if len(questions) < num_questions:
            logger.warning(
                f"Could only generate {len(questions)}/{num_questions} "
                f"golden questions after supplemental attempts"
            )

        logger.success(
            f"Generated {len(questions)}/{num_questions} golden questions "
            f"(strategy: golden)"
        )
        return test_set

    def _generate_hybrid_question(
        self,
        segments: list[dict[str, Any]],
        doc_chunks: list[dict[str, Any]],
        question_type: str,
        generator: Generator,
        source_path: str,
        doc_name: str = "",
        doc_content: str = "",
    ) -> dict[str, Any] | None:
        """Generate a single question using hybrid strategy.

        Args:
            segments: List of document segments.
            doc_chunks: List of chunk dictionaries for the document.
            question_type: Type of question to generate.
            generator: Generator instance for LLM calls.
            source_path: Source path of the document.
            doc_name: Name of the document.
            doc_content: Full document content for fallback verification.

        Returns:
            Dictionary with question data, or None if generation fails.
        """
        multi_hop_types = {"multi_fact", "reasoning", "comparative"}

        if question_type in multi_hop_types:
            selected_segments = select_candidate_segments(
                segments,
                question_type,
                self.multi_hop_candidate_count,
                self.segment_sampling_strategy,
            )
        else:
            selected_segments = select_segments_for_question_type(
                segments, question_type, 1, self.segment_sampling_strategy
            )

        if not selected_segments and question_type != "irrelevant":
            logger.debug(f"No segments selected for question type: {question_type}")
            return None

        if question_type == "irrelevant":
            return generate_irrelevant_question(
                doc_name=doc_name,
                generator=generator,
                max_retries=self.max_retries,
            )

        if question_type == "missing":
            selected_segments = select_segments_for_question_type(
                segments, question_type, 1, self.segment_sampling_strategy
            )
            if selected_segments:
                selected_segments = compact_segments(
                    selected_segments, self.compact_segment_max_chars
                )
            return generate_missing_question(
                selected_segments=selected_segments,
                generator=generator,
            )

        compact_types = {"single_fact", "adversarial"}
        if question_type in compact_types and selected_segments:
            selected_segments = compact_segments(
                selected_segments, self.compact_segment_max_chars
            )

        for attempt in range(self.max_retries):
            qa = generate_question_with_evidence(
                selected_segments=selected_segments,
                question_type=question_type,
                generator=generator,
            )

            if qa is None:
                continue

            qa["question_type"] = self.QUESTION_TYPES.get(question_type, question_type)

            evidence_list = qa.get("evidence", [])
            if not evidence_list:
                if question_type == "missing":
                    qa["ground_truth_excerpt"] = ""
                    return qa
                logger.debug(f"No evidence provided for question type: {question_type}")
                continue

            if question_type == "missing":
                logger.debug("Missing type question has evidence, retrying...")
                continue

            validation = validate_evidence(
                evidence_list,
                selected_segments,
                question_type,
                doc_content,
                self.MIN_QUOTE_LENGTH,
                self.quote_fuzzy_match_threshold,
            )

            verified_count = sum(
                1 for e in validation["verified_evidence"] if e.get("verified", False)
            )

            if not validation["valid"]:
                logger.debug(
                    f"Evidence validation failed on attempt {attempt + 1}: "
                    f"{len(validation['invalid_quotes'])} invalid quotes, "
                    f"{verified_count} verified"
                )
                if attempt < self.max_retries - 1:
                    continue

            qa["evidence"] = validation["verified_evidence"]

            if question_type in multi_hop_types:
                all_page_numbers: set[int] = set()
                all_quotes: list[str] = []
                for seg in selected_segments:
                    all_page_numbers.update(seg.get("page_numbers", []))
                for ev in validation["verified_evidence"]:
                    q = ev.get("quote", "")
                    if q:
                        all_quotes.append(q)

                chunk_id_set: set[str] = set()
                for q in all_quotes:
                    chunk_ids = locate_source_chunks(
                        sorted(all_page_numbers),
                        q,
                        doc_chunks,
                        self.quote_fuzzy_match_threshold,
                    )
                    chunk_id_set.update(chunk_ids)
                source_chunks = sorted(chunk_id_set)
            else:
                first_evidence = (
                    validation["verified_evidence"][0]
                    if validation["verified_evidence"]
                    else {}
                )
                quote = first_evidence.get("quote", "")
                page_numbers = []
                if selected_segments:
                    page_numbers = selected_segments[0].get("page_numbers", [])
                source_chunks = locate_source_chunks(
                    page_numbers, quote, doc_chunks, self.quote_fuzzy_match_threshold
                )

            qa["source_chunks"] = source_chunks

            match_types = [
                e.get("match_type", "none")
                for e in validation["verified_evidence"]
                if e.get("verified", False)
            ]
            qa["evidence_match_types"] = match_types

            all_quotes = [
                e["quote"]
                for e in validation["verified_evidence"]
                if e.get("quote", "").strip()
            ]
            qa["ground_truth_excerpt"] = "\n".join(all_quotes) if all_quotes else ""

            return qa

        return None

    def generate_document_based_questions(
        self,
        meal_name: str,
        num_questions: int | None = None,
        name: str | None = None,
        type_distribution: dict[str, float] | None = None,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
        chunks_dir: Path | None = None,
        use_hybrid: bool = True,
    ) -> dict[str, Any]:
        """Generate questions based on full MD documents.

        Args:
            meal_name: Name of the meal to generate questions for.
            num_questions: Total number of questions to generate.
            name: Name for the test set.
            type_distribution: Custom distribution of question types.
            llm_preset: LLM preset name.
            token_tracker: Optional token usage tracker.
            chunks_dir: Optional path to chunks directory.
            use_hybrid: If True, delegate to generate_hybrid_questions.

        Returns:
            Dictionary containing the test set metadata and generated questions.

        Raises:
            TestSetError: If no documents are found or no questions could be generated.
        """
        if use_hybrid:
            logger.info("Delegating to generate_hybrid_questions (use_hybrid=True)")
            return self.generate_hybrid_questions(
                meal_name=meal_name,
                num_questions=num_questions,
                name=name
                or f"document_level_n{num_questions or self.default_num_questions}",
                type_distribution=type_distribution,
                llm_preset=llm_preset,
                token_tracker=token_tracker,
                chunks_dir=chunks_dir,
            )

        num_questions = num_questions or self.default_num_questions
        name = name or f"document_level_n{num_questions}"
        type_distribution = type_distribution or self.TYPE_DISTRIBUTION

        return _generate_document_based_questions(
            config=self.config,
            meal_name=meal_name,
            num_questions=num_questions,
            name=name,
            type_distribution=type_distribution,
            llm_preset=llm_preset,
            token_tracker=token_tracker,
            chunks_dir=chunks_dir,
            temperature=self.test_gen_temperature,
            max_tokens=self.test_gen_max_tokens,
            max_retries=self.max_retries,
            doc_truncate_cache=self._doc_truncate_cache,
        )

    def supplement_document_based_questions(
        self,
        meal_name: str,
        existing_test_set: dict[str, Any],
        target_count: int,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
        chunks_dir: Path | None = None,
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

        Raises:
            ValueError: If no documents are found for the meal.
        """
        return _supplement_document_based_questions(
            config=self.config,
            meal_name=meal_name,
            existing_test_set=existing_test_set,
            target_count=target_count,
            llm_preset=llm_preset,
            token_tracker=token_tracker,
            chunks_dir=chunks_dir,
            type_distribution=self.TYPE_DISTRIBUTION,
            temperature=self.test_gen_temperature,
            supplement_max_tokens=self.test_gen_supplement_max_tokens,
            max_retries=self.max_retries,
            doc_truncate_cache=self._doc_truncate_cache,
        )

    def _chinese_to_type_key(self, chinese_type: str) -> str | None:
        """Convert a Chinese question type label to its English key.

        Args:
            chinese_type: Chinese label like '单知识点查询'.

        Returns:
            English key like 'single_fact', or None if not found.
        """
        reverse_map = {v: k for k, v in self.QUESTION_TYPES.items()}
        return reverse_map.get(chinese_type)

    def _post_process_question(
        self,
        qa: dict,
        doc_content: str,
        seen_questions: set,
        *,
        check_answer_consistency: bool = False,
        golden_metadata: dict | None = None,
    ) -> bool:
        """Validate and deduplicate a generated question.

        Performs numerical accuracy correction, excerpt verification,
        evidence consistency checks, and duplicate detection.

        Args:
            qa: Question-answer dictionary to validate.
            doc_content: Full document content for excerpt verification.
            seen_questions: Set of already-seen question texts for dedup.
            check_answer_consistency: If True, run validate_answer_consistency.
            golden_metadata: If not None, add golden-specific metadata fields.

        Returns:
            True if question passes validation and was added to seen_questions,
            False if filtered out as duplicate.
        """
        q_type_raw = qa.get("question_type", "")
        q_type = self._chinese_to_type_key(q_type_raw) or q_type_raw

        is_valid, correction = validate_numerical_accuracy(qa)
        if not is_valid and correction:
            logger.warning(f"Numerical accuracy issue: {correction['suggestion']}")
            for err in correction.get("errors", []):
                wrong_val = err["answer_value"]
                correct_val = err["correct_value"]
                answer_text = qa.get("answer", "")
                qa["answer"] = answer_text.replace(f"{wrong_val}", f"{correct_val}")
            qa.setdefault("metadata", {})
            qa["metadata"]["numerical_auto_corrected"] = True

        if check_answer_consistency:
            is_consistent, consistency_warning = validate_answer_consistency(qa)
            if not is_consistent:
                logger.warning(f"Answer consistency issue: {consistency_warning}")
                qa.setdefault("metadata", {})
                qa["metadata"]["answer_consistency_warning"] = consistency_warning

        excerpt = qa.get("ground_truth_excerpt", "")
        if excerpt and q_type not in ("irrelevant",):
            excerpt_verified = verify_excerpt_in_document(excerpt, doc_content)
            qa.setdefault("metadata", {})
            qa["metadata"]["excerpt_verified"] = excerpt_verified
            if not excerpt_verified:
                logger.warning(
                    f"ground_truth_excerpt not found in document "
                    f"for question {qa['id']}"
                )

        evidence_list = qa.get("evidence", [])
        if evidence_list and q_type not in ("irrelevant", "missing"):
            strictness = self.VALIDATION_STRICTNESS.get(q_type, "moderate")

            if strictness == "none":
                pass
            elif strictness == "lenient":
                is_consistent, issues = validate_answer_evidence_consistency(
                    qa.get("answer", ""),
                    evidence_list,
                    check_proper_nouns=self.check_proper_nouns,
                )
                if not is_consistent:
                    qa.setdefault("metadata", {})
                    qa["metadata"]["answer_evidence_issues"] = issues
            else:
                is_consistent, issues = validate_answer_evidence_consistency(
                    qa.get("answer", ""),
                    evidence_list,
                    check_proper_nouns=self.check_proper_nouns,
                )
                if not is_consistent:
                    logger.warning(
                        f"Answer-evidence inconsistency for question {qa['id']}: "
                        f"{'; '.join(issues)}"
                    )
                    qa.setdefault("metadata", {})
                    qa["metadata"]["answer_evidence_issues"] = issues

                    numerical_issues = [i for i in issues if i.startswith("数值")]
                    proper_noun_issues = [i for i in issues if i.startswith("专有名词")]

                    if strictness == "strict":
                        should_reject = len(issues) > 3 or len(numerical_issues) > 1
                    else:
                        should_reject = len(numerical_issues) > 2 or (
                            len(numerical_issues) > 1 and len(proper_noun_issues) > 2
                        )

                    if should_reject:
                        logger.info(
                            f"Rejecting question {qa['id']} due to "
                            f"evidence inconsistency: "
                            f"{len(numerical_issues)} numerical issues, "
                            f"{len(issues)} total issues"
                        )
                        return False

        if golden_metadata is not None:
            qa.setdefault("metadata", {})
            qa["metadata"]["author"] = "llm_assisted"
            qa["metadata"]["reviewed"] = False
            qa["metadata"]["review_notes"] = ""
            if not qa["metadata"].get("target_failure_mode"):
                qa["metadata"]["target_failure_mode"] = self.FAILURE_MODES.get(
                    q_type, ""
                )

        question_text = qa.get("question", "")
        if question_text in seen_questions:
            logger.debug(f"Skipping duplicate question: {question_text[:50]}...")
            return False

        seen_questions.add(question_text)
        return True
