import hashlib
import json
import random
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.document_loader import LazyDocumentLoader
from src.exceptions import TestSetError
from src.generator import Generator
from src.meal import ArtifactCache, MealConfig, MealManager
from src.test_generation.chunk_locator import (
    extract_key_sentences,
    extract_key_terms,
    fuzzy_match_quote,
)
from src.test_generation.chunk_locator import (
    locate_answer_chunks as _locate_answer_chunks_standalone,
)
from src.test_generation.chunk_locator import (
    locate_chunks_by_quote as _locate_chunks_by_quote_standalone,
)
from src.test_generation.chunk_locator import (
    locate_multi_hop_chunks as _locate_multi_hop_chunks_standalone,
)
from src.test_generation.chunk_locator import (
    locate_source_chunks as _locate_source_chunks_standalone,
)
from src.test_generation.chunk_locator import (
    map_segments_to_chunks as _map_segments_to_chunks_standalone,
)
from src.test_generation.chunk_locator import (
    texts_overlap as _texts_overlap_standalone,
)
from src.test_generation.chunk_locator import (
    verify_quote_in_segment as _verify_quote_in_segment_standalone,
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
)
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
from src.test_generation.validators import (
    build_primary_pool as _build_primary_pool_standalone,
)
from src.test_generation.validators import (
    calculate_hybrid_quality_metrics as _calculate_hybrid_quality_metrics_standalone,
)
from src.test_generation.validators import (
    calculate_quality_metrics as _calculate_quality_metrics_standalone,
)
from src.test_generation.validators import (
    check_authenticity_rules as _check_authenticity_rules_standalone,
)
from src.test_generation.validators import (
    detect_content_overlaps as _detect_content_overlaps_standalone,
)
from src.test_generation.validators import (
    filter_adversarial_issues as _filter_adversarial_issues_standalone,
)
from src.test_generation.validators import (
    supplement_evidence_for_uncovered_numbers as _supplement_evidence_for_uncovered_numbers_standalone,
)
from src.test_generation.validators import (
    truncate_answer as _truncate_answer_standalone,
)
from src.test_generation.validators import (
    validate_answer_consistency as _validate_answer_consistency_standalone,
)
from src.test_generation.validators import (
    validate_answer_evidence_consistency as _validate_answer_evidence_consistency_standalone,
)
from src.test_generation.validators import (
    validate_evidence as _validate_evidence_standalone,
)
from src.test_generation.validators import (
    validate_numerical_accuracy as _validate_numerical_accuracy_standalone,
)
from src.test_generation.validators import (
    validate_question_quality as _validate_question_quality_standalone,
)
from src.test_generation.validators import (
    verify_excerpt_in_document as _verify_excerpt_in_document_standalone,
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
        self.test_gen_model_name = tg_config.get("model_name", "LongCat-Flash-Lite")
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
        self._doc_truncate_cache: dict[str, str] = {}

    def _segment_document(
        self, document_content: str, segment_size: int = 8000
    ) -> list[dict[str, Any]]:
        """Divide a document into segments for question generation.

        Attempts to segment at sentence boundaries to avoid cutting mid-sentence.
        For documents shorter than segment_size, returns a single segment.

        Args:
            document_content: The full text content of the document.
            segment_size: Target character count per segment. Defaults to 8000.

        Returns:
            List of segment dictionaries, each containing:
                - text: The segment text content
                - start_char: Starting character position in original document
                - end_char: Ending character position in original document
                - segment_index: Zero-based index of the segment
        """
        if not document_content:
            return []

        doc_length = len(document_content)
        if doc_length <= segment_size:
            return [
                {
                    "text": document_content,
                    "start_char": 0,
                    "end_char": doc_length,
                    "segment_index": 0,
                }
            ]

        segments: list[dict[str, Any]] = []
        current_pos = 0
        segment_index = 0

        sentence_endings = ["。", "！", "？", "！", "?", "!", "\n\n", "；", ";"]

        while current_pos < doc_length:
            target_end = min(current_pos + segment_size, doc_length)

            if target_end >= doc_length:
                segment_text = document_content[current_pos:doc_length]
                if segment_text.strip():
                    segments.append(
                        {
                            "text": segment_text,
                            "start_char": current_pos,
                            "end_char": doc_length,
                            "segment_index": segment_index,
                        }
                    )
                break

            best_break = -1
            search_start = max(current_pos + segment_size // 2, current_pos)

            for ending in sentence_endings:
                pos = document_content.rfind(ending, search_start, target_end)
                if pos > best_break:
                    best_break = pos

            if best_break == -1:
                space_pos = document_content.rfind(" ", search_start, target_end)
                if space_pos > current_pos:
                    best_break = space_pos

            actual_end = best_break + 1 if best_break > current_pos else target_end

            segment_text = document_content[current_pos:actual_end]
            if segment_text.strip():
                segments.append(
                    {
                        "text": segment_text,
                        "start_char": current_pos,
                        "end_char": actual_end,
                        "segment_index": segment_index,
                    }
                )
                segment_index += 1

            current_pos = actual_end

        return segments

    def _build_segments_from_pages(
        self,
        pages: list[dict[str, Any]],
        target_chars: int = 8000,
    ) -> list[dict[str, Any]]:
        """Build segments by aggregating pages from parser output.

        Unlike :meth:`_segment_document` which re-segments from full
        document text, this method groups whole pages together so that
        each segment carries ``page_numbers`` for reliable chunk
        mapping.

        Args:
            pages: List of page dicts, each containing ``page_number``
                and ``text`` keys.
            target_chars: Target character count per segment.

        Returns:
            List of segment dictionaries.
        """
        if not pages:
            return []

        sorted_pages = sorted(pages, key=lambda p: p.get("page_number", 0))

        segments: list[dict[str, Any]] = []
        current_pages: list[dict[str, Any]] = []
        current_chars = 0
        segment_index = 0

        for page in sorted_pages:
            page_text = page.get("text", "")
            if not page_text or not page_text.strip():
                continue

            current_pages.append(page)
            current_chars += len(page_text)

            if current_chars >= target_chars:
                page_numbers = sorted(p.get("page_number", 0) for p in current_pages)
                text = "\n\n".join(p.get("text", "") for p in current_pages)
                segments.append(
                    {
                        "text": text,
                        "segment_index": segment_index,
                        "page_numbers": page_numbers,
                        "start_char": 0,
                        "end_char": len(text),
                        "source_type": "pages_json",
                    }
                )
                segment_index += 1
                current_pages = []
                current_chars = 0

        if current_pages:
            page_numbers = sorted(p.get("page_number", 0) for p in current_pages)
            text = "\n\n".join(p.get("text", "") for p in current_pages)
            segments.append(
                {
                    "text": text,
                    "segment_index": segment_index,
                    "page_numbers": page_numbers,
                    "start_char": 0,
                    "end_char": len(text),
                    "source_type": "pages_json",
                }
            )

        for i, seg in enumerate(segments):
            seg["start_char"] = sum(len(segments[j]["text"]) + 2 for j in range(i))
            seg["end_char"] = seg["start_char"] + len(seg["text"])

        return segments

    def _compact_segments(
        self,
        segments: list[dict[str, Any]],
        max_chars: int,
    ) -> list[dict[str, Any]]:
        """Truncate segment text to reduce token consumption.

        Args:
            segments: List of segment dictionaries with 'text' key.
            max_chars: Maximum characters per segment.

        Returns:
            Segments with truncated text (copies, originals unchanged).
        """
        compacted = []
        for seg in segments:
            text = seg.get("text", "")
            if len(text) <= max_chars:
                compacted.append(seg)
            else:
                compacted_seg = dict(seg)
                compacted_seg["text"] = text[:max_chars]
                compacted.append(compacted_seg)
        return compacted

    def _select_segments_for_question_type(
        self,
        segments: list[dict[str, Any]],
        question_type: str,
        num_segments: int = 1,
    ) -> list[dict[str, Any]]:
        """Select document segments based on question type.

        Args:
            segments: List of segment dictionaries from _segment_document.
            question_type: Type of question to generate.
            num_segments: Number of segments to select.

        Returns:
            List of selected segment dictionaries.
        """
        if not segments:
            return []

        if question_type == "irrelevant":
            return []

        if question_type == "single_fact" or question_type == "missing":
            selected_count = 1
        elif question_type in ["multi_fact", "reasoning", "comparative"]:
            selected_count = min(random.randint(2, 3), len(segments))
        elif question_type == "adversarial":
            selected_count = min(random.randint(1, 2), len(segments))
        else:
            selected_count = min(num_segments, len(segments))

        if selected_count >= len(segments):
            return segments.copy()

        if self.segment_sampling_strategy == "random":
            return random.sample(segments, selected_count)
        elif self.segment_sampling_strategy == "sequential":
            start_idx = random.randint(0, len(segments) - selected_count)
            return segments[start_idx : start_idx + selected_count]
        else:
            return random.sample(segments, selected_count)

    def _select_candidate_segments(
        self,
        segments: list[dict[str, Any]],
        question_type: str,
        num_candidates: int = 4,
    ) -> list[dict[str, Any]]:
        """Select candidate segments for multi-hop question generation.

        Args:
            segments: List of segment dictionaries.
            question_type: Type of question to generate.
            num_candidates: Number of candidate segments.

        Returns:
            List of selected segment dictionaries.
        """
        if not segments:
            return []

        multi_hop_types = {"multi_fact", "reasoning", "comparative"}

        if question_type not in multi_hop_types:
            return self._select_segments_for_question_type(
                segments, question_type, num_candidates
            )

        actual_count = min(num_candidates, len(segments))

        if actual_count >= len(segments):
            return segments.copy()

        if self.segment_sampling_strategy == "random":
            return self._select_diverse_segments(segments, actual_count)
        elif self.segment_sampling_strategy == "sequential":
            start_idx = random.randint(0, len(segments) - actual_count)
            return segments[start_idx : start_idx + actual_count]
        else:
            return self._select_diverse_segments(segments, actual_count)

    def _select_diverse_segments(
        self,
        segments: list[dict[str, Any]],
        count: int,
    ) -> list[dict[str, Any]]:
        """Select segments with diversity in document position.

        Args:
            segments: List of segment dictionaries.
            count: Number of segments to select.

        Returns:
            List of selected segment dictionaries with diverse positions.
        """
        if count >= len(segments):
            return segments.copy()

        total_segments = len(segments)
        step = total_segments / count

        selected: list[dict[str, Any]] = []
        for i in range(count):
            target_index = int(i * step)
            target_index = min(target_index, total_segments - 1)

            for seg in segments:
                if seg.get("segment_index", 0) == target_index:
                    selected.append(seg)
                    break
            else:
                if segments:
                    selected.append(segments[target_index])

        if len(selected) < count:
            remaining = [s for s in segments if s not in selected]
            needed = count - len(selected)
            if remaining and needed > 0:
                selected.extend(random.sample(remaining, min(needed, len(remaining))))

        return selected

    def _parse_segment_selection(
        self,
        llm_response: dict[str, Any],
        num_available_segments: int,
    ) -> list[int]:
        """Parse segment selection from LLM response.

        Args:
            llm_response: Parsed LLM response dictionary.
            num_available_segments: Total number of available segments.

        Returns:
            List of valid segment indices.
        """
        if num_available_segments <= 0:
            return []

        all_indices = list(range(num_available_segments))

        selected = llm_response.get("selected_segments")
        if selected is None:
            return all_indices

        if not isinstance(selected, list):
            logger.warning(
                f"selected_segments is not a list: {type(selected).__name__}"
            )
            return all_indices

        valid_indices: list[int] = []
        for idx in selected:
            if isinstance(idx, int) and 0 <= idx < num_available_segments:
                valid_indices.append(idx)
            else:
                logger.warning(
                    f"Invalid segment index: {idx} (available: 0-{num_available_segments - 1})"
                )

        if not valid_indices:
            logger.warning("No valid segment indices found in selected_segments")
            return all_indices

        return valid_indices

    def _validate_segment_relevance(
        self,
        selected_indices: list[int],
        segments: list[dict[str, Any]],
    ) -> bool:
        """Validate if selected segments share any common keywords.

        Args:
            selected_indices: List of segment indices that were selected.
            segments: List of all available segment dictionaries.

        Returns:
            True if segments share common keywords or if only one segment
            is selected. False if segments appear unrelated.
        """
        if len(selected_indices) <= 1:
            return True

        selected_segments = [segments[i] for i in selected_indices if i < len(segments)]

        if len(selected_segments) <= 1:
            return True

        keyword_sets: list[set[str]] = []
        for seg in selected_segments:
            text = seg.get("text", "")
            keywords = self._extract_segment_keywords(text)
            keyword_sets.append(keywords)

        if not keyword_sets:
            return True

        common_keywords = keyword_sets[0]
        for kw_set in keyword_sets[1:]:
            common_keywords = common_keywords & kw_set

        if not common_keywords:
            logger.warning(
                f"Selected segments (indices: {selected_indices}) share no common keywords. "
                "They may be unrelated, which could affect question quality."
            )
            return False

        logger.debug(
            f"Segments share {len(common_keywords)} common keywords: "
            f"{list(common_keywords)[:5]}"
        )
        return True

    def _extract_segment_keywords(self, text: str) -> set[str]:
        """Extract meaningful keywords from segment text.

        Args:
            text: The segment text to extract keywords from.

        Returns:
            Set of keyword strings extracted from the text.
        """
        keywords: set[str] = set()

        numbers_with_units = re.findall(r"\d+\.?\d*[万亿千百%％]?", text)
        keywords.update(numbers_with_units)

        proper_nouns = re.findall(
            r"[\u4e00-\u9fff]{2,8}(?:股份|集团|公司|行业|市场|技术|产品|业务)",
            text,
        )
        keywords.update(proper_nouns)

        domain_keywords = [
            "增长",
            "下降",
            "上升",
            "减少",
            "增加",
            "收入",
            "利润",
            "营收",
            "市值",
            "占比",
            "规模",
            "产量",
            "销量",
            "价格",
            "成本",
            "投资",
            "融资",
            "估值",
            "盈利",
            "亏损",
            "负债",
            "资产",
            "现金流",
            "毛利率",
            "净利率",
        ]
        for kw in domain_keywords:
            if kw in text:
                keywords.add(kw)

        return keywords

    def _map_segments_to_chunks(
        self,
        segments: list[dict[str, Any]],
        doc_chunks: list[dict[str, Any]],
    ) -> dict[int, list[str]]:
        """Map document segments to chunk IDs based on text content overlap.

        .. deprecated::
            Use :meth:`_locate_source_chunks` with ``page_numbers``
            from page-based segments instead.

        Args:
            segments: List of segment dictionaries.
            doc_chunks: List of chunk dictionaries.

        Returns:
            Dictionary mapping segment_index to list of chunk_ids.
        """
        return _map_segments_to_chunks_standalone(segments, doc_chunks)

    @staticmethod
    def _texts_overlap(text_a: str, text_b: str, min_overlap_chars: int = 30) -> bool:
        """Check if two texts have significant overlapping content.

        .. deprecated::
            No longer used by the primary mapping path.

        Args:
            text_a: First text.
            text_b: Second text.
            min_overlap_chars: Minimum consecutive matching characters.

        Returns:
            True if the texts share significant overlapping content.
        """
        return _texts_overlap_standalone(text_a, text_b, min_overlap_chars)

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

        chunks = self._load_meal_chunks(meal_config)
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
            qa = self._generate_question_with_llm(chunk_group, strategy, generator)
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

    def _resolve_parsed_dir(self, meal_config: MealConfig) -> Path | None:
        """Resolve the parsed artifacts directory for a meal.

        Args:
            meal_config: MealConfig object with data_id and config_hashes.

        Returns:
            Path to the parsed directory, or None if not found.
        """
        if meal_config.data_id and meal_config.config_hashes:
            parser_hash = meal_config.config_hashes.get("parser", "")
            if parser_hash:
                artifacts_config = self.config.get("artifacts", {})
                artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
                raw_dir = Path(
                    self.config.get("parser", {}).get("input_dir", "data/raw")
                )
                cache = ArtifactCache(artifacts_dir, raw_dir)
                parsed_dir = cache.get_parsed_dir(meal_config.data_id, parser_hash)
                if parsed_dir.exists():
                    logger.debug(f"Resolved parsed dir via ArtifactCache: {parsed_dir}")
                    return parsed_dir

        logger.warning(
            f"Could not resolve parsed dir via ArtifactCache for "
            f"meal_config data_id={meal_config.data_id}"
        )
        return None

    def _resolve_chunks_dir(self, meal_config: MealConfig) -> Path | None:
        """Resolve the chunks artifacts directory for a meal.

        Args:
            meal_config: MealConfig object with data_id and config_hashes.

        Returns:
            Path to the chunks directory, or None if not found.
        """
        if meal_config.data_id and meal_config.config_hashes:
            chunker_hash = meal_config.config_hashes.get("chunker", "")
            if chunker_hash:
                artifacts_config = self.config.get("artifacts", {})
                artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
                raw_dir = Path(
                    self.config.get("parser", {}).get("input_dir", "data/raw")
                )
                cache = ArtifactCache(artifacts_dir, raw_dir)
                chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)
                if chunks_dir.exists():
                    logger.debug(f"Resolved chunks dir via ArtifactCache: {chunks_dir}")
                    return chunks_dir

        logger.warning(
            f"Could not resolve chunks dir via ArtifactCache for "
            f"meal_config data_id={meal_config.data_id}"
        )
        return None

    def _load_meal_chunks(self, meal_config) -> list[dict[str, Any]]:
        """Load chunk data from JSONL files associated with a meal's PDF files.

        Args:
            meal_config: MealConfig object.

        Returns:
            List of chunk dictionaries loaded from matching JSONL files.
        """
        chunks_dir = self._resolve_chunks_dir(meal_config)
        if not chunks_dir or not chunks_dir.exists():
            return []

        source_filter = set()
        for mf in meal_config.pdf_files:
            md_path = Path(mf.path).with_suffix(".md")
            source_filter.add(md_path.as_posix())

        all_chunks = []
        jsonl_files = list(chunks_dir.rglob("*.jsonl"))

        for jsonl_file in jsonl_files:
            try:
                rel_path = jsonl_file.relative_to(chunks_dir).as_posix()
                jsonl_md_path = rel_path.rsplit(".", 1)[0] + ".md"

                if source_filter and jsonl_md_path not in source_filter:
                    continue

                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            chunk = json.loads(line)
                            all_chunks.append(chunk)
            except Exception as e:
                logger.warning(f"Failed to load {jsonl_file}: {str(e)}")
                continue

        return all_chunks

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

    def _generate_question_with_llm(
        self,
        chunks: list[dict],
        strategy: str,
        generator,
    ) -> dict[str, Any] | None:
        """Generate a single Q&A pair from chunks using an LLM.

        Args:
            chunks: List of chunk dictionaries.
            strategy: Question generation strategy.
            generator: Generator instance used to call the LLM.

        Returns:
            Dictionary with 'question', 'answer', and 'difficulty' keys, or
            None if all retry attempts fail.
        """
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

        for attempt in range(self.max_retries):
            try:
                response = generator.generate(
                    query=prompt,
                    contexts=[],
                    system_prompt="你是一个测试数据生成器。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                    category="test_generation",
                    allow_no_contexts=True,
                )

                qa = self._parse_llm_response(response)
                if qa is not None:
                    return qa

                logger.debug(f"Attempt {attempt + 1}: failed to parse LLM response")
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

        return None

    def _parse_llm_response(self, response: str) -> dict[str, Any] | None:
        """Parse an LLM response string into a Q&A dictionary.

        Args:
            response: Raw LLM response string.

        Returns:
            Dictionary with 'question', 'answer', and 'difficulty' keys, or
            None if the response cannot be parsed.
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

            if "question" not in qa or "answer" not in qa:
                return None

            if not qa["question"] or not qa["answer"]:
                return None

            qa.setdefault("difficulty", "medium")
            return qa

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Failed to parse LLM response as JSON: {str(e)}")
            return None

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

        document_contents = self._load_full_documents(meal_config)
        if not document_contents:
            raise TestSetError(f"No documents found for meal '{meal_name}'")

        logger.info(f"Loaded {len(document_contents)} documents")

        doc_chunks_map = self._load_document_chunks(
            meal_config, document_contents, chunks_dir
        )

        doc_pages_map = self._load_document_pages(meal_config)

        type_counts = self._calculate_question_distribution(
            num_questions, type_distribution
        )
        logger.info(f"Question type distribution: {type_counts}")

        doc_question_plans = self._distribute_questions_across_docs(
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

        questions = []
        question_id = 1
        total_attempts = 0
        failed_count = 0
        seen_questions: set[str] = set()

        for doc_name, doc_data in document_contents.items():
            assigned_types = doc_question_plans.get(doc_name, [])
            if not assigned_types:
                continue

            doc_content = doc_data["content"]
            source_path = doc_data["source_path"]
            doc_chunks = doc_chunks_map.get(doc_name, [])

            pages = doc_pages_map.get(doc_name, [])
            if pages:
                segments = self._build_segments_from_pages(pages, self.segment_size)
            else:
                segments = self._segment_document(doc_content, self.segment_size)
                for seg in segments:
                    seg["page_numbers"] = []
                    seg["source_type"] = "fallback"
            if not segments:
                logger.warning(f"No segments generated for document: {doc_name}")
                continue

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

                    is_valid, correction = self._validate_numerical_accuracy(qa)
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

                    excerpt = qa.get("ground_truth_excerpt", "")
                    if excerpt and q_type not in ("irrelevant",):
                        excerpt_verified = self._verify_excerpt_in_document(
                            excerpt,
                            doc_content,
                        )
                        qa.setdefault("metadata", {})
                        qa["metadata"]["excerpt_verified"] = excerpt_verified
                        if not excerpt_verified:
                            logger.warning(
                                f"ground_truth_excerpt not found in document "
                                f"for question {qa['id']}"
                            )

                    evidence_list = qa.get("evidence", [])
                    if evidence_list and q_type not in ("irrelevant", "missing"):
                        is_consistent, issues = (
                            self._validate_answer_evidence_consistency(
                                qa.get("answer", ""),
                                evidence_list,
                            )
                        )
                        if not is_consistent:
                            logger.warning(
                                f"Answer-evidence inconsistency for question {qa['id']}: "
                                f"{'; '.join(issues)}"
                            )
                            qa.setdefault("metadata", {})
                            qa["metadata"]["answer_evidence_issues"] = issues

                    question_text = qa.get("question", "")
                    if question_text in seen_questions:
                        logger.debug(
                            f"Skipping duplicate question: {question_text[:50]}..."
                        )
                        failed_count += 1
                        continue

                    questions.append(qa)
                    seen_questions.add(question_text)
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
            type_weights = [type_distribution[t] for t in all_types]
            total_weight = sum(type_weights)
            weighted_types = []
            if total_weight > 0:
                cumulative = 0.0
                for t, w in zip(all_types, type_weights, strict=False):
                    cumulative += w / total_weight
                    weighted_types.append((t, cumulative))
            else:
                step = 1.0 / len(all_types)
                weighted_types = [(t, (i + 1) * step) for i, t in enumerate(all_types)]
            extra_attempt = 0
            max_extra_attempts = deficit * 3

            while len(questions) < num_questions and extra_attempt < max_extra_attempts:
                extra_attempt += 1
                doc_name = doc_names[extra_attempt % len(doc_names)]
                r = random.random()
                q_type = all_types[0]
                for t, threshold in weighted_types:
                    if r <= threshold:
                        q_type = t
                        break
                doc_data = document_contents[doc_name]
                doc_content = doc_data["content"]
                source_path = doc_data["source_path"]
                doc_chunks = doc_chunks_map.get(doc_name, [])

                pages = doc_pages_map.get(doc_name, [])
                if pages:
                    segments = self._build_segments_from_pages(pages, self.segment_size)
                else:
                    segments = self._segment_document(doc_content, self.segment_size)
                    for seg in segments:
                        seg["page_numbers"] = []
                        seg["source_type"] = "fallback"
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

                    is_valid, correction = self._validate_numerical_accuracy(qa)
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

                    excerpt = qa.get("ground_truth_excerpt", "")
                    if excerpt and q_type not in ("irrelevant",):
                        excerpt_verified = self._verify_excerpt_in_document(
                            excerpt,
                            doc_content,
                        )
                        qa.setdefault("metadata", {})
                        qa["metadata"]["excerpt_verified"] = excerpt_verified
                        if not excerpt_verified:
                            logger.warning(
                                f"ground_truth_excerpt not found in document "
                                f"for question {qa['id']}"
                            )

                    evidence_list = qa.get("evidence", [])
                    if evidence_list and q_type not in ("irrelevant", "missing"):
                        is_consistent, issues = (
                            self._validate_answer_evidence_consistency(
                                qa.get("answer", ""),
                                evidence_list,
                            )
                        )
                        if not is_consistent:
                            logger.warning(
                                f"Answer-evidence inconsistency for question {qa['id']}: "
                                f"{'; '.join(issues)}"
                            )
                            qa.setdefault("metadata", {})
                            qa["metadata"]["answer_evidence_issues"] = issues

                    question_text = qa.get("question", "")
                    if question_text in seen_questions:
                        logger.debug(
                            f"Skipping duplicate question: {question_text[:50]}..."
                        )
                        failed_count += 1
                        continue

                    questions.append(qa)
                    seen_questions.add(question_text)
                    question_id += 1
                else:
                    failed_count += 1
                    logger.warning(
                        f"Supplemental question failed, total failures: {failed_count}"
                    )

        if not questions:
            raise TestSetError("No questions could be generated")

        quality_metrics = self._calculate_hybrid_quality_metrics(questions)

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

        document_contents = self._load_full_documents(meal_config)
        if not document_contents:
            raise TestSetError(f"No documents found for meal '{meal_config.name}'")

        logger.info(f"Loaded {len(document_contents)} documents")

        doc_chunks_map = self._load_document_chunks(meal_config, document_contents)

        doc_pages_map = self._load_document_pages(meal_config)

        doc_list = [
            {"doc_id": doc_name, "content": doc_data["content"]}
            for doc_name, doc_data in document_contents.items()
        ]
        overlaps = self._detect_content_overlaps(doc_list)
        if overlaps:
            for supp_id, primary_id, ratio in overlaps:
                logger.info(
                    f"Content overlap: {supp_id} is supplementary "
                    f"to {primary_id} (overlap={ratio:.0%})"
                )

        primary_pool = self._build_primary_pool(doc_list, overlaps)
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

        type_counts = self._calculate_question_distribution(
            num_questions, type_distribution
        )
        logger.info(f"Golden type distribution: {type_counts}")

        doc_question_plans = self._distribute_questions_across_docs(
            type_counts, list(filtered_contents.keys())
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

            pages = doc_pages_map.get(doc_name, [])
            if pages:
                segments = self._build_segments_from_pages(pages, self.segment_size)
            else:
                segments = self._segment_document(doc_content, self.segment_size)
                for seg in segments:
                    seg["page_numbers"] = []
                    seg["source_type"] = "fallback"
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
                    qa["id"] = f"golden_{question_id:03d}"
                    qa["source_document"] = doc_name
                    qa["category"] = "golden"

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

                    is_valid, correction = self._validate_numerical_accuracy(qa)
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

                    is_consistent, consistency_warning = (
                        self._validate_answer_consistency(qa)
                    )
                    if not is_consistent:
                        logger.warning(
                            f"Answer consistency issue: {consistency_warning}"
                        )
                        qa.setdefault("metadata", {})
                        qa["metadata"]["answer_consistency_warning"] = (
                            consistency_warning
                        )

                    excerpt = qa.get("ground_truth_excerpt", "")
                    if excerpt and q_type not in ("irrelevant",):
                        excerpt_verified = self._verify_excerpt_in_document(
                            excerpt,
                            doc_content,
                        )
                        qa.setdefault("metadata", {})
                        qa["metadata"]["excerpt_verified"] = excerpt_verified
                        if not excerpt_verified:
                            logger.warning(
                                f"ground_truth_excerpt not found in document "
                                f"for question {qa['id']}"
                            )

                    evidence_list = qa.get("evidence", [])
                    if evidence_list and q_type not in ("irrelevant", "missing"):
                        is_consistent, issues = (
                            self._validate_answer_evidence_consistency(
                                qa.get("answer", ""),
                                evidence_list,
                            )
                        )
                        if not is_consistent:
                            logger.warning(
                                f"Answer-evidence inconsistency for question {qa['id']}: "
                                f"{'; '.join(issues)}"
                            )
                            qa.setdefault("metadata", {})
                            qa["metadata"]["answer_evidence_issues"] = issues

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
                        logger.debug(
                            f"Skipping duplicate question: {question_text[:50]}..."
                        )
                        failed_count += 1
                        continue

                    questions.append(qa)
                    seen_questions.add(question_text)
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
            all_types = list(type_distribution.keys())
            type_weights = [type_distribution[t] for t in all_types]
            total_weight = sum(type_weights)
            weighted_types = []
            if total_weight > 0:
                cumulative = 0.0
                for t, w in zip(all_types, type_weights, strict=False):
                    cumulative += w / total_weight
                    weighted_types.append((t, cumulative))
            else:
                step = 1.0 / len(all_types)
                weighted_types = [(t, (i + 1) * step) for i, t in enumerate(all_types)]
            extra_attempt = 0
            max_extra_attempts = deficit * 3

            while len(questions) < num_questions and extra_attempt < max_extra_attempts:
                extra_attempt += 1
                doc_name = doc_names[extra_attempt % len(doc_names)]

                if type_deficits:
                    max_deficit = max(type_deficits.values())
                    deficit_types = [
                        t for t, d in type_deficits.items() if d == max_deficit
                    ]
                    q_type = deficit_types[extra_attempt % len(deficit_types)]
                else:
                    r = random.random()
                    q_type = all_types[0]
                    for t, threshold in weighted_types:
                        if r <= threshold:
                            q_type = t
                            break
                doc_data = filtered_contents[doc_name]
                doc_content = doc_data["content"]
                source_path = doc_data["source_path"]
                doc_chunks = doc_chunks_map.get(doc_name, [])

                pages = doc_pages_map.get(doc_name, [])
                if pages:
                    segments = self._build_segments_from_pages(pages, self.segment_size)
                else:
                    segments = self._segment_document(doc_content, self.segment_size)
                    for seg in segments:
                        seg["page_numbers"] = []
                        seg["source_type"] = "fallback"
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
                    qa["id"] = f"golden_{question_id:03d}"
                    qa["source_document"] = doc_name
                    qa["category"] = "golden"

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

                    is_valid, correction = self._validate_numerical_accuracy(qa)
                    if not is_valid and correction:
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

                    is_consistent, consistency_warning = (
                        self._validate_answer_consistency(qa)
                    )
                    if not is_consistent:
                        logger.warning(
                            f"Answer consistency issue: {consistency_warning}"
                        )
                        qa.setdefault("metadata", {})
                        qa["metadata"]["answer_consistency_warning"] = (
                            consistency_warning
                        )

                    excerpt = qa.get("ground_truth_excerpt", "")
                    if excerpt and q_type not in ("irrelevant",):
                        excerpt_verified = self._verify_excerpt_in_document(
                            excerpt,
                            doc_content,
                        )
                        qa.setdefault("metadata", {})
                        qa["metadata"]["excerpt_verified"] = excerpt_verified

                    evidence_list = qa.get("evidence", [])
                    if evidence_list and q_type not in ("irrelevant", "missing"):
                        is_consistent, issues = (
                            self._validate_answer_evidence_consistency(
                                qa.get("answer", ""),
                                evidence_list,
                            )
                        )
                        if not is_consistent:
                            logger.warning(
                                f"Answer-evidence inconsistency for question {qa['id']}: "
                                f"{'; '.join(issues)}"
                            )
                            qa.setdefault("metadata", {})
                            qa["metadata"]["answer_evidence_issues"] = issues

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
                        logger.debug(
                            f"Skipping duplicate question: {question_text[:50]}..."
                        )
                        failed_count += 1
                        continue

                    questions.append(qa)
                    seen_questions.add(question_text)
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
                    logger.warning(
                        f"Supplemental question failed, total failures: {failed_count}"
                    )

        if not questions:
            raise TestSetError("No golden questions could be generated")

        quality_metrics = self._calculate_hybrid_quality_metrics(questions)

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

    def _load_document_chunks(
        self,
        meal_config: MealConfig,
        document_contents: dict[str, dict[str, str]],
        chunks_dir: Path | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Load chunks for each document in document_contents.

        Args:
            meal_config: MealConfig object for resolving chunks directory.
            document_contents: Dictionary mapping document names to content dicts.
            chunks_dir: Optional path to chunks directory.

        Returns:
            Dictionary mapping document names to lists of chunk dictionaries.
        """
        if chunks_dir is not None:
            chunks_path = chunks_dir
        else:
            chunks_path = self._resolve_chunks_dir(meal_config)

        if not chunks_path or not chunks_path.exists():
            logger.warning(f"Chunks directory not found: {chunks_path}")
            return {doc_name: [] for doc_name in document_contents}

        source_to_doc_name: dict[str, str] = {}
        for doc_name, doc_data in document_contents.items():
            source_path = doc_data.get("source_path", "")
            source_to_doc_name[source_path] = doc_name

        doc_chunks_map: dict[str, list[dict[str, Any]]] = {
            doc_name: [] for doc_name in document_contents
        }

        jsonl_files = list(chunks_path.rglob("*.jsonl"))

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

                        doc_name = source_to_doc_name.get(chunk_source)
                        if doc_name:
                            doc_chunks_map[doc_name].append(chunk)
            except Exception as e:
                logger.warning(f"Failed to load {jsonl_file}: {str(e)}")
                continue

        for doc_name, chunks in doc_chunks_map.items():
            if chunks:
                chunks.sort(key=lambda c: c.get("metadata", {}).get("chunk_index", 0))
                logger.debug(f"Loaded {len(chunks)} chunks for document: {doc_name}")

        return doc_chunks_map

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
            selected_segments = self._select_candidate_segments(
                segments, question_type, self.multi_hop_candidate_count
            )
        else:
            selected_segments = self._select_segments_for_question_type(
                segments, question_type
            )

        if not selected_segments and question_type != "irrelevant":
            logger.debug(f"No segments selected for question type: {question_type}")
            return None

        if question_type == "irrelevant":
            return self._generate_irrelevant_question(
                doc_name=doc_name,
                generator=generator,
            )

        compact_types = {"single_fact", "missing", "adversarial"}
        if question_type in compact_types and selected_segments:
            selected_segments = self._compact_segments(
                selected_segments, self.compact_segment_max_chars
            )

        for attempt in range(self.max_retries):
            qa = self._generate_question_with_evidence(
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

            validation = self._validate_evidence(
                evidence_list, selected_segments, question_type, doc_content
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
                    chunk_ids = self._locate_source_chunks(
                        sorted(all_page_numbers), q, doc_chunks
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
                source_chunks = self._locate_source_chunks(
                    page_numbers, quote, doc_chunks
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

    def _generate_missing_question(
        self,
        selected_segments: list[dict[str, Any]],
        generator: Generator,
    ) -> dict[str, Any] | None:
        """Generate a missing-type question using MISSING_INDEPENDENT_PROMPT.

        Uses a dedicated prompt that first analyzes what the document covers,
        then asks about a dimension clearly NOT covered. This avoids the
        contradiction of using evidence-aware prompts for questions that
        should have no evidence.

        Args:
            selected_segments: List of selected segment dictionaries.
            generator: Generator instance for LLM calls.

        Returns:
            Dictionary with question data, or None if generation fails.
        """
        segments_text = ""
        for i, seg in enumerate(selected_segments):
            segments_text += f"片段{i}:\n{seg.get('text', '')}\n\n"

        prompt = MISSING_INDEPENDENT_PROMPT.format(segments_text=segments_text.strip())

        for _attempt in range(self.max_retries):
            try:
                response = generator.generate(
                    query=prompt,
                    contexts=[],
                    system_prompt="你是一位金融行业从业者。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                    category="test_generation",
                    allow_no_contexts=True,
                )

                qa = self._parse_evidence_question_response(response)
                if qa is None:
                    continue

                qa["question_type"] = self.QUESTION_TYPES.get("missing", "缺失知识点")

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

    def _generate_irrelevant_question(
        self,
        doc_name: str,
        generator: Generator,
    ) -> dict[str, Any] | None:
        """Generate an irrelevant question unrelated to the document.

        Args:
            doc_name: Name of the document (used to derive topic).
            generator: Generator instance for LLM calls.

        Returns:
            Dictionary with question data, or None if generation fails.
        """
        doc_topic = doc_name.split("：")[0] if "：" in doc_name else doc_name

        prompt = IRRELEVANT_QUESTION_PROMPT.format(doc_topic=doc_topic)

        for _attempt in range(self.max_retries):
            try:
                response = generator.generate(
                    query=prompt,
                    contexts=[],
                    system_prompt="你是一位金融行业从业者。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                    category="test_generation",
                    allow_no_contexts=True,
                )

                qa = self._parse_evidence_question_response(response)
                if qa is None:
                    continue

                qa["question_type"] = self.QUESTION_TYPES.get("irrelevant", "无关问题")
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

    def _validate_numerical_accuracy(
        self, question_data: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None]:
        """Validate numerical accuracy in answer against ground_truth_excerpt.

        Args:
            question_data: Dictionary containing 'answer' and 'ground_truth_excerpt'.

        Returns:
            Tuple of (is_valid, correction).
        """
        return _validate_numerical_accuracy_standalone(question_data)

    def _validate_answer_consistency(
        self, question_data: dict[str, Any]
    ) -> tuple[bool, str]:
        """Validate answer for internal consistency.

        Args:
            question_data: Dictionary containing 'answer' and 'ground_truth_excerpt'.

        Returns:
            Tuple of (is_consistent, warning_message).
        """
        return _validate_answer_consistency_standalone(question_data)

    def _validate_answer_evidence_consistency(
        self,
        answer: str,
        evidence_list: list[dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        """Validate that key information in answer appears in evidence.

        Args:
            answer: The generated answer text.
            evidence_list: List of evidence dictionaries.

        Returns:
            Tuple of (is_valid, issues).
        """
        return _validate_answer_evidence_consistency_standalone(answer, evidence_list)

    def _filter_adversarial_issues(
        self,
        issues: list[str],
        question_text: str,
    ) -> list[str]:
        """Filter answer-evidence issues for adversarial question type.

        Args:
            issues: List of issue strings from _validate_answer_evidence_consistency.
            question_text: The question text to check for number presence.

        Returns:
            Filtered list of issues relevant to adversarial type.
        """
        return _filter_adversarial_issues_standalone(issues, question_text)

    def _supplement_evidence_for_uncovered_numbers(
        self,
        answer: str,
        evidence_list: list[dict[str, Any]],
        issues: list[str],
        doc_content: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Supplement evidence with document context for uncovered numbers.

        Args:
            answer: The generated answer text.
            evidence_list: Current list of evidence dictionaries.
            issues: List of issues from consistency check.
            doc_content: Full document content for searching.

        Returns:
            Tuple of (updated_evidence_list, remaining_issues).
        """
        return _supplement_evidence_for_uncovered_numbers_standalone(
            answer, evidence_list, issues, doc_content
        )

    def _truncate_answer(
        self,
        qa: dict[str, Any],
        answer_text: str,
        answer_limit: int,
    ) -> None:
        """Truncate answer to the specified length limit.

        Args:
            qa: Question-answer dictionary to modify in place.
            answer_text: Original answer text.
            answer_limit: Maximum character length for the answer.
        """
        return _truncate_answer_standalone(qa, answer_text, answer_limit)

    def _verify_excerpt_in_document(
        self,
        excerpt: str,
        document_content: str,
        min_overlap: int = 15,
    ) -> bool:
        """Verify that the excerpt can be found in the document content.

        Args:
            excerpt: The ground truth excerpt to verify.
            document_content: The full document content to search in.
            min_overlap: Minimum number of consecutive matching characters.

        Returns:
            True if the excerpt (or a substantial part of it) is found.
        """
        return _verify_excerpt_in_document_standalone(
            excerpt, document_content, min_overlap
        )

    def _detect_content_overlaps(
        self,
        documents: list[dict[str, Any]],
        threshold: float = 0.8,
    ) -> list[tuple[str, str, float]]:
        """Detect content overlap between document pairs.

        Args:
            documents: List of document dicts with 'doc_id' and 'content'.
            threshold: Minimum hit rate to mark as supplementary.

        Returns:
            List of tuples: (supplementary_doc_id, primary_doc_id, ratio).
        """
        return _detect_content_overlaps_standalone(documents, threshold)

    def _build_primary_pool(
        self,
        documents: list[dict[str, Any]],
        overlaps: list[tuple[str, str, float]],
    ) -> list[dict[str, Any]]:
        """Build primary document pool, excluding supplementary documents.

        Args:
            documents: List of document dicts.
            overlaps: Overlap tuples from _detect_content_overlaps().

        Returns:
            List of primary document dicts.
        """
        return _build_primary_pool_standalone(documents, overlaps)

    def _generate_question_with_evidence(
        self,
        selected_segments: list[dict[str, Any]],
        question_type: str,
        generator: Generator,
    ) -> dict[str, Any] | None:
        """Generate a question with evidence using EVIDENCE_AWARE_PROMPT.

        Args:
            selected_segments: List of selected segment dictionaries.
            question_type: Type of question to generate.
            generator: Generator instance for LLM calls.

        Returns:
            Dictionary with question data, or None if generation fails.
        """
        q_type_cn = self.QUESTION_TYPES.get(question_type, question_type)

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

            qa = self._parse_evidence_question_response(response)
            if qa is not None and self._validate_question_quality(qa):
                return qa

            logger.debug("Failed to parse or validate evidence question response")
        except Exception as e:
            logger.warning(f"Failed to generate evidence question: {str(e)}")

        return None

    def _parse_evidence_question_response(self, response: str) -> dict[str, Any] | None:
        """Parse an LLM response for evidence-aware question generation.

        Args:
            response: Raw LLM response string.

        Returns:
            Dictionary with question data including evidence list, or None.
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

            required_fields = ["question", "answer", "question_type"]
            for field in required_fields:
                if field not in qa or not qa[field]:
                    logger.debug(f"Missing or empty required field: {field}")
                    return None

            qa.setdefault("difficulty", "medium")
            qa.setdefault("evidence", [])
            qa.setdefault("selected_segments", [])

            return qa

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Failed to parse LLM response as JSON: {str(e)}")
            return None

    def _calculate_hybrid_quality_metrics(
        self, questions: list[dict]
    ) -> dict[str, Any]:
        """Calculate quality metrics for hybrid-generated questions.

        Args:
            questions: List of generated question dictionaries.

        Returns:
            Dictionary containing quality metrics.
        """
        return _calculate_hybrid_quality_metrics_standalone(questions)

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

        meal_manager = MealManager(self.config)
        meal_config = meal_manager.load_meal(meal_name)

        logger.info(
            f"Generating document-based questions for meal '{meal_name}' "
            f"(num_questions={num_questions}, use_hybrid=False)"
        )

        document_contents = self._load_full_documents(meal_config)
        if not document_contents:
            raise TestSetError(f"No documents found for meal '{meal_name}'")

        logger.info(f"Loaded {len(document_contents)} documents")

        type_counts = self._calculate_question_distribution(
            num_questions, type_distribution
        )
        logger.info(f"Question type distribution: {type_counts}")

        doc_question_plans = self._distribute_questions_across_docs(
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

        questions = []
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

                qa = self._generate_single_document_question(
                    doc_content, q_type, generator
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
                        qa["source_chunks"] = self._locate_answer_chunks(
                            answer_text,
                            source_path,
                            meal_config=meal_config,
                            chunks_dir=chunks_dir,
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
            all_types = list(self.TYPE_DISTRIBUTION.keys())
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

                qa = self._generate_single_document_question(
                    doc_content, q_type, generator
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
                        qa["source_chunks"] = self._locate_answer_chunks(
                            answer_text,
                            source_path,
                            meal_config=meal_config,
                            chunks_dir=chunks_dir,
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

        quality_metrics = self._calculate_quality_metrics(questions)

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

        self._save_test_set(meal_name, test_set, name)

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

        meal_manager = MealManager(self.config)
        meal_config = meal_manager.load_meal(meal_name)

        document_contents = self._load_full_documents(meal_config)
        if not document_contents:
            raise TestSetError(f"No documents found for meal '{meal_name}'")

        llm_config = get_llm_config(self.config, llm_preset)
        generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=self.test_gen_temperature,
            max_tokens=self.test_gen_supplement_max_tokens,
            token_tracker=token_tracker,
        )

        doc_names = list(document_contents.keys())
        all_types = list(self.TYPE_DISTRIBUTION.keys())
        question_id = len(existing_questions) + 1
        new_questions = []
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

            qa = self._generate_single_document_question(doc_content, q_type, generator)

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
                    qa["source_chunks"] = self._locate_answer_chunks(
                        answer_text,
                        source_path,
                        meal_config=meal_config,
                        chunks_dir=chunks_dir,
                    )

                question_text = qa.get("question", "")
                if question_text in seen_questions:
                    logger.debug(
                        f"Skipping duplicate question: {question_text[:50]}..."
                    )
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
        quality_metrics = self._calculate_quality_metrics(all_questions)

        existing_test_set["questions"] = all_questions
        existing_test_set["quality_metrics"] = quality_metrics

        if "metadata" in existing_test_set:
            existing_test_set["metadata"]["updated_at"] = datetime.now().isoformat()
            if "generation" in existing_test_set["metadata"]:
                existing_test_set["metadata"]["generation"]["num_questions"] = (
                    target_count
                )
            audit_entry = {
                "event": "supplemented",
                "added_count": len(new_questions),
                "timestamp": datetime.now().isoformat(),
            }
            existing_test_set["metadata"].setdefault("audit_log", []).append(
                audit_entry
            )
            test_set_name = existing_test_set["metadata"]["name"]
        else:
            if "generation_config" not in existing_test_set:
                existing_test_set["generation_config"] = {}
            existing_test_set["generation_config"]["num_questions"] = target_count
            test_set_name = existing_test_set.get(
                "name", f"document_level_n{target_count}"
            )

        self._save_test_set(meal_name, existing_test_set, test_set_name)

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

    def _load_document_pages(
        self,
        meal_config: MealConfig,
    ) -> dict[str, list[dict[str, Any]]]:
        """Load per-page data from ``.pages.json`` files.

        Args:
            meal_config: MealConfig whose ``pdf_files`` determine which
                documents to load.

        Returns:
            Dictionary mapping document names to lists of page dicts.
        """
        parsed_dir = self._resolve_parsed_dir(meal_config)
        if not parsed_dir or not parsed_dir.exists():
            logger.warning(f"Parsed directory not found: {parsed_dir}")
            return {}

        source_filter: set[str] = set()
        for mf in meal_config.pdf_files:
            pages_rel = Path(mf.path).with_suffix(".pages.json").as_posix()
            source_filter.add(pages_rel)

        result: dict[str, list[dict[str, Any]]] = {}
        pages_files = list(parsed_dir.rglob("*.pages.json"))

        for pages_file in pages_files:
            try:
                rel_path = pages_file.relative_to(parsed_dir).as_posix()
                if source_filter and rel_path not in source_filter:
                    continue

                with open(pages_file, encoding="utf-8") as f:
                    pages_data = json.load(f)

                if not isinstance(pages_data, list):
                    continue

                doc_name = pages_file.stem.replace(".pages", "")
                page_list: list[dict[str, Any]] = []
                for page in pages_data:
                    if not isinstance(page, dict):
                        continue
                    text = page.get("text", "")
                    page_number = page.get("page_number", 0)
                    if text and text.strip():
                        page_list.append({"page_number": page_number, "text": text})

                if page_list:
                    result[doc_name] = page_list
                    logger.debug(
                        f"Loaded {len(page_list)} pages for document: {doc_name}"
                    )
            except Exception as e:
                logger.error(f"Failed to load {pages_file}: {str(e)}")
                continue

        return result

    def _load_full_documents(
        self, meal_config: MealConfig
    ) -> dict[str, dict[str, str]]:
        """Load full documents associated with a meal's PDF files.

        Args:
            meal_config: MealConfig object whose pdf_files determine the
                documents to load.

        Returns:
            Dictionary mapping document names to dicts with 'content' and
            'source_path' keys.
        """
        parsed_dir = self._resolve_parsed_dir(meal_config)
        if not parsed_dir or not parsed_dir.exists():
            logger.warning(f"Parsed directory not found: {parsed_dir}")
            return {}

        try:
            loader = LazyDocumentLoader(parsed_dir)
        except FileNotFoundError as e:
            logger.error(f"Failed to initialize LazyDocumentLoader: {str(e)}")
            return {}

        source_filter = set()
        for mf in meal_config.pdf_files:
            md_path = Path(mf.path).with_suffix(".md").as_posix()
            pages_path = Path(mf.path).with_suffix(".pages.json").as_posix()
            source_filter.add(md_path)
            source_filter.add(pages_path)

        documents: dict[str, dict[str, str]] = {}

        for doc_name in loader.document_names:
            try:
                doc = loader.get(doc_name)
                rel_path = Path(doc.source_path).relative_to(parsed_dir).as_posix()

                if source_filter and rel_path not in source_filter:
                    continue

                documents[doc_name] = {
                    "content": doc.content,
                    "source_path": rel_path,
                }
                logger.debug(f"Loaded document: {doc_name} ({len(doc.content)} chars)")
            except Exception as e:
                logger.error(f"Failed to load document '{doc_name}': {str(e)}")
                continue

        return documents

    def _load_pages_json_documents(
        self, parsed_dir: Path, meal_config: MealConfig
    ) -> dict[str, dict[str, str]]:
        """Load documents from .pages.json format.

        Args:
            parsed_dir: Directory containing .pages.json files.
            meal_config: MealConfig object for source filtering.

        Returns:
            Dictionary mapping document names to content dicts.
        """
        source_filter = set()
        for mf in meal_config.pdf_files:
            pages_rel = Path(mf.path).with_suffix(".pages.json").as_posix()
            source_filter.add(pages_rel)

        documents = {}
        pages_files = list(parsed_dir.rglob("*.pages.json"))

        for pages_file in pages_files:
            try:
                rel_path = pages_file.relative_to(parsed_dir).as_posix()
                if source_filter and rel_path not in source_filter:
                    continue

                with open(pages_file, encoding="utf-8") as f:
                    pages_data = json.load(f)

                full_text = "\n\n".join(
                    page.get("text", "")
                    for page in sorted(
                        pages_data, key=lambda p: p.get("page_number", 0)
                    )
                )

                doc_name = pages_file.stem.replace(".pages", "")
                documents[doc_name] = {
                    "content": full_text,
                    "source_path": rel_path,
                }
                logger.debug(f"Loaded document: {doc_name} ({len(full_text)} chars)")
            except Exception as e:
                logger.error(f"Failed to load {pages_file}: {str(e)}")

        return documents

    def _load_md_documents(
        self, parsed_dir: Path, meal_config: MealConfig
    ) -> dict[str, dict[str, str]]:
        """Load documents from .md format.

        Args:
            parsed_dir: Directory containing .md files.
            meal_config: MealConfig object for source filtering.

        Returns:
            Dictionary mapping document names to content dicts.
        """
        source_filter = set()
        for mf in meal_config.pdf_files:
            md_rel = Path(mf.path).with_suffix(".md").as_posix()
            source_filter.add(md_rel)

        documents = {}
        md_files = list(parsed_dir.rglob("*.md"))

        for md_file in md_files:
            try:
                rel_path = md_file.relative_to(parsed_dir).as_posix()
                if source_filter and rel_path not in source_filter:
                    continue

                with open(md_file, encoding="utf-8") as f:
                    content = f.read()

                doc_name = md_file.stem
                documents[doc_name] = {
                    "content": content,
                    "source_path": rel_path,
                }
                logger.debug(f"Loaded document: {doc_name} ({len(content)} chars)")
            except Exception as e:
                logger.error(f"Failed to load {md_file}: {str(e)}")

        return documents

    def _chinese_to_type_key(self, chinese_type: str) -> str | None:
        """Convert a Chinese question type label to its English key.

        Args:
            chinese_type: Chinese label like '单知识点查询'.

        Returns:
            English key like 'single_fact', or None if not found.
        """
        reverse_map = {v: k for k, v in self.QUESTION_TYPES.items()}
        return reverse_map.get(chinese_type)

    def _calculate_question_distribution(
        self,
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

        type_counts = {}
        allocated = 0
        remainders = []

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

    def _distribute_questions_across_docs(
        self,
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
        doc_question_plans: dict[str, list[str]] = {name: [] for name in doc_names}
        for i, q_type in enumerate(question_plan):
            doc_name = doc_names[i % num_docs]
            doc_question_plans[doc_name].append(q_type)

        return doc_question_plans

    def _generate_single_document_question(
        self,
        document_content: str,
        question_type: str,
        generator,
    ) -> dict[str, Any] | None:
        """Generate a single question from a document using an LLM.

        Args:
            document_content: Full text content of the document.
            question_type: Type of question to generate.
            generator: Generator instance used to call the LLM.

        Returns:
            Dictionary with question data, or None if generation fails.
        """
        q_type_cn = self.QUESTION_TYPES.get(question_type, question_type)

        supplement = QUESTION_TYPE_SUPPLEMENTS.get(question_type, "")

        doc_key = hashlib.sha256(document_content[:1000].encode()).hexdigest()[:16]
        if doc_key in self._doc_truncate_cache:
            truncated_doc = self._doc_truncate_cache[doc_key]
        else:
            truncated_doc = document_content[: self.DOCUMENT_TRUNCATE_MAX]
            self._doc_truncate_cache[doc_key] = truncated_doc

        prompt = DOCUMENT_LEVEL_PROMPT.format(
            document_content=truncated_doc, question_type=q_type_cn
        )

        if supplement:
            prompt += supplement

        for attempt in range(self.max_retries):
            try:
                response = generator.generate(
                    query=prompt,
                    contexts=[],
                    system_prompt="你是一位金融行业从业者。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                    category="test_generation",
                    allow_no_contexts=True,
                )

                qa = self._parse_document_question_response(response)
                if qa is not None and self._validate_question_quality(qa):
                    return qa

                logger.debug(
                    f"Attempt {attempt + 1}: failed to parse or validate "
                    f"question response"
                )
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

        return None

    def _parse_document_question_response(self, response: str) -> dict[str, Any] | None:
        """Parse an LLM response for document-based question generation.

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

            required_fields = ["question", "answer", "question_type"]
            for field in required_fields:
                if field not in qa or not qa[field]:
                    logger.debug(f"Missing or empty required field: {field}")
                    return None

            qa.setdefault("difficulty", "medium")
            qa.setdefault("reasoning", "")
            qa.setdefault("key_entities", [])
            qa.setdefault("answer_sources", [])

            return qa

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Failed to parse LLM response as JSON: {str(e)}")
            return None

    def _validate_question_quality(self, question_data: dict) -> bool:
        """Validate the quality of a generated question.

        Args:
            question_data: Dictionary containing question data.

        Returns:
            True if the question passes quality checks, False otherwise.
        """
        return _validate_question_quality_standalone(question_data)

    def _check_authenticity_rules(self, question: str) -> dict[str, Any]:
        """Check if a question follows authenticity rules.

        Args:
            question: The question text to check.

        Returns:
            Dictionary with 'has_issues', 'issues', and 'is_authentic' keys.
        """
        return _check_authenticity_rules_standalone(question)

    def _calculate_quality_metrics(self, questions: list[dict]) -> dict[str, Any]:
        """Calculate quality metrics for generated questions.

        Args:
            questions: List of generated question dictionaries.

        Returns:
            Dictionary containing quality metrics.
        """
        return _calculate_quality_metrics_standalone(questions)

    def _locate_source_chunks(
        self,
        page_numbers: list[int],
        quote: str,
        doc_chunks: list[dict[str, Any]],
    ) -> list[str]:
        """Locate chunk IDs via two-stage mapping: page filter then quote match.

        Args:
            page_numbers: Page numbers associated with the segment.
            quote: Verified quote text to locate within candidate chunks.
            doc_chunks: All chunk dictionaries for the document.

        Returns:
            Sorted list of chunk_id strings.
        """
        return _locate_source_chunks_standalone(
            page_numbers, quote, doc_chunks, self.quote_fuzzy_match_threshold
        )

    def _locate_chunks_by_quote(
        self,
        quote: str,
        segments: list[dict[str, Any]],
        segment_chunk_map: dict[int, list[str]],
        doc_chunks: list[dict[str, Any]],
    ) -> list[str]:
        """Locate chunk IDs that contain a verified quote text.

        .. deprecated::
            Use :meth:`_locate_source_chunks` with ``page_numbers``
            from page-based segments instead.

        Args:
            quote: The verified quote text to locate.
            segments: List of segment dictionaries.
            segment_chunk_map: Dictionary mapping segment_index to chunk_ids.
            doc_chunks: List of all chunk dictionaries.

        Returns:
            List of chunk_id strings.
        """
        return _locate_chunks_by_quote_standalone(
            quote,
            segments,
            segment_chunk_map,
            doc_chunks,
            self.quote_fuzzy_match_threshold,
        )

    def _locate_multi_hop_chunks(
        self,
        evidence_list: list[dict[str, Any]],
        segments: list[dict[str, Any]],
        segment_chunk_map: dict[int, list[str]],
        doc_chunks: list[dict[str, Any]],
    ) -> list[str]:
        """Locate chunk IDs for multi-hop questions from multiple evidence entries.

        .. deprecated::
            Use :meth:`_locate_source_chunks` with ``page_numbers``
            from page-based segments instead.

        Args:
            evidence_list: List of evidence dictionaries.
            segments: List of segment dictionaries.
            segment_chunk_map: Dictionary mapping segment_index to chunk_ids.
            doc_chunks: List of all chunk dictionaries.

        Returns:
            List of unique chunk_id strings.
        """
        return _locate_multi_hop_chunks_standalone(
            evidence_list,
            segments,
            segment_chunk_map,
            doc_chunks,
            self.quote_fuzzy_match_threshold,
        )

    def _locate_answer_chunks(
        self,
        answer: str,
        source_path: str,
        meal_config: "MealConfig" = None,
        adjacent_tolerance: int = 1,
        chunks_dir: Path | None = None,
    ) -> list[str]:
        """Locate chunk IDs that contain information relevant to the answer.

        .. deprecated::
            Use :meth:`_locate_chunks_by_quote` instead.

        Args:
            answer: The answer text to locate in chunks.
            source_path: Relative path of the source document.
            meal_config: MealConfig object for resolving chunks directory.
            adjacent_tolerance: Number of adjacent chunks to include.
            chunks_dir: Optional path to chunks directory.

        Returns:
            List of chunk_id strings for matched and adjacent chunks.
        """
        warnings.warn(
            "_locate_answer_chunks is deprecated. "
            "Use _locate_chunks_by_quote for more accurate quote-based "
            "chunk location.",
            DeprecationWarning,
            stacklevel=2,
        )
        if chunks_dir is not None:
            resolved_chunks_dir = chunks_dir
        elif meal_config is not None:
            resolved_chunks_dir = self._resolve_chunks_dir(meal_config)
            if not resolved_chunks_dir:
                return []
        else:
            logger.warning(
                "No chunks_dir or meal_config provided for find_adjacent_chunks"
            )
            return []

        return _locate_answer_chunks_standalone(
            answer, source_path, resolved_chunks_dir, adjacent_tolerance
        )

    def _extract_key_sentences(self, answer: str) -> list[str]:
        """Extract key sentences from an answer text.

        Args:
            answer: The answer text to extract sentences from.

        Returns:
            List of key sentences.
        """
        return extract_key_sentences(answer)

    def _extract_key_terms(self, answer: str) -> list[str]:
        """Extract key terms from an answer text for chunk matching.

        Args:
            answer: The answer text to extract terms from.

        Returns:
            List of key term strings.
        """
        return extract_key_terms(answer)

    def _chunk_matches_answer(
        self,
        chunk_text: str,
        key_sentences: list[str],
        key_terms: list[str],
        term_threshold: int = 3,
        overlap_threshold: float = 0.7,
    ) -> bool:
        """Check if a chunk text contains information relevant to the answer.

        Args:
            chunk_text: The text content of the chunk.
            key_sentences: Key sentences extracted from the answer.
            key_terms: Key terms extracted from the answer.
            term_threshold: Minimum number of key terms for a match.
            overlap_threshold: Minimum character overlap ratio for a match.

        Returns:
            True if the chunk is considered relevant to the answer.
        """
        from src.test_generation.chunk_locator import chunk_matches_answer

        return chunk_matches_answer(
            chunk_text, key_sentences, key_terms, term_threshold, overlap_threshold
        )

    def _verify_quote_in_segment(self, quote: str, segment_text: str) -> dict[str, Any]:
        """Verify if a quote exists in a segment text.

        Args:
            quote: The quote text to verify.
            segment_text: The segment text to search within.

        Returns:
            Dictionary with 'found', 'position', and 'match_type' keys.
        """
        return _verify_quote_in_segment_standalone(
            quote, segment_text, self.quote_fuzzy_match_threshold
        )

    def _fuzzy_match_quote(
        self, quote: str, segment_text: str, threshold: float = 0.85
    ) -> dict[str, Any]:
        """Perform fuzzy matching of a quote within segment text.

        Args:
            quote: The quote text to match.
            segment_text: The segment text to search within.
            threshold: Minimum similarity ratio for a match.

        Returns:
            Dictionary with 'found', 'position', and 'similarity' keys.
        """
        return fuzzy_match_quote(quote, segment_text, threshold)

    def _validate_evidence(
        self,
        evidence_list: list[dict[str, Any]],
        segments: list[dict[str, Any]],
        question_type: str = "unknown",
        doc_content: str = "",
    ) -> dict[str, Any]:
        """Validate evidence entries against document segments.

        Args:
            evidence_list: List of evidence dictionaries.
            segments: List of segment dictionaries.
            question_type: Type of question for logging context.
            doc_content: Full document content for fallback verification.

        Returns:
            Dictionary with 'valid', 'verified_evidence', and 'invalid_quotes' keys.
        """
        return _validate_evidence_standalone(
            evidence_list,
            segments,
            question_type,
            doc_content,
            self.MIN_QUOTE_LENGTH,
            self.quote_fuzzy_match_threshold,
        )
