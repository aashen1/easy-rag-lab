import json
import random
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.generator import Generator
from src.meal import ArtifactCache, MealConfig, MealManager
from src.utils import ensure_dir, get_llm_config


FACTUAL_PROMPT = """你是一个金融研报问答系统的测试工程师。请根据以下文本片段，生成一个可以用该文本直接回答的事实性问题。

要求：
1. 问题必须能用提供的文本完全回答
2. 问题应该具体、明确，避免过于宽泛
3. 答案应该简洁准确，直接引用文本中的关键数据或结论
4. 不要生成需要外部知识才能回答的问题

文本片段：
---
{chunk_text}
---

请严格以以下JSON格式输出（不要输出其他内容）：
{{"question": "你的问题", "answer": "期望的答案", "difficulty": "easy"}}"""

BOUNDARY_PROMPT = """你是一个金融研报问答系统的测试工程师。以下两个文本片段是同一份文档中相邻的部分。请注意，重要信息可能恰好被分割在两个片段之间。

请生成一个需要同时参考两个片段才能完整回答的问题。这个问题应该测试系统在信息被chunk边界切断时的检索和回答能力。

片段1：
---
{chunk1_text}
---

片段2：
---
{chunk2_text}
---

请严格以以下JSON格式输出（不要输出其他内容）：
{{"question": "你的问题", "answer": "期望的答案", "difficulty": "medium"}}"""

MULTI_HOP_PROMPT = """你是一个金融研报问答系统的测试工程师。以下文本片段来自同一份文档的不同部分。请生成一个需要综合多个片段中的信息才能回答的复杂问题。

要求：
1. 问题不能仅凭单个片段回答
2. 需要对比、综合或推理多个片段的信息
3. 答案应明确指出信息来自哪些片段

片段：
---
{chunk_texts}
---

请严格以以下JSON格式输出（不要输出其他内容）：
{{"question": "你的问题", "answer": "期望的答案", "difficulty": "hard"}}"""

DOCUMENT_LEVEL_PROMPT = """你是一位金融行业从业者，正在阅读一份行业研究报告。请基于这份报告，生成一个你会真实提出的问题。

## 你的背景
- 你可能是投资分析师、基金经理、行业研究员或企业战略规划人员
- 你关心的是能帮助你做决策的信息
- 你的提问风格是直接、口语化、不啰嗦

## 报告内容
---
{document_content}
---

## 问题类型要求
请生成一个【{question_type}】类型的问题。

类型说明：
- 单知识点查询：查询某个具体数据、事实或概念
- 多知识点综合：需要整合多个信息点才能回答
- 推理型问题：需要基于信息进行推理或判断
- 对比分析：对比两个或多个对象
- 缺失知识点：询问文档中没有或不完整的信息
- 无关问题：与文档主题无关的问题

## 生成要求

1. 问题风格：
   - 直接、口语化，像在问同事问题
   - 不要用"根据文档"、"请分析"等学术化表述
   - 避免过于正式或结构化的问题

2. 问题质量：
   - 问题应该有明确的意图
   - 问题应该有合理的答案（即使是"文档未提及"）
   - 问题应该体现真实业务场景

3. 答案要求：
   - 答案应基于文档内容
   - 如果文档无法回答，明确说明原因
   - 答案应简洁、准确

## 输出格式

请严格按以下JSON格式输出（不要输出其他内容）：

{{
    "question": "你的问题",
    "answer": "期望的答案",
    "question_type": "{question_type}",
    "difficulty": "easy/medium/hard/special",
    "reasoning": "简要说明为什么这个问题属于该类型",
    "key_entities": ["问题涉及的关键实体，如公司名、技术名等"],
    "answer_sources": ["答案依据的文档段落，如'第3段'或'表格数据'"]
}}"""

SINGLE_FACT_SUPPLEMENT = """
## 单知识点查询的特别说明

好的示例：
- "2024年光模块市场规模多少？"
- "CPO的全称是什么？"
- "中际旭创的主要产品是什么？"

不好的示例（太学术化）：
- "请根据文档说明2024年光模块市场规模"
- "文档中提到的CPO技术的全称是什么？"
"""

MULTI_FACT_SUPPLEMENT = """
## 多知识点综合的特别说明

好的示例：
- "科瑞技术和猎奇智能在光模块设备上有什么区别？"
- "光模块行业未来几年的增长点主要在哪里？"

不好的示例：
- "请对比分析科瑞技术和猎奇智能的业务差异"
- "请总结光模块行业的发展趋势"
"""

REASONING_SUPPLEMENT = """
## 推理型问题的特别说明

好的示例：
- "为什么CPO能降低功耗？"
- "如果800G需求翻倍，对设备商有什么影响？"

答案要求：
- 必须展示推理过程
- 推理依据必须来自文档
- 可以有合理的推断，但要说明依据
"""

COMPARATIVE_SUPPLEMENT = """
## 对比分析的特别说明

好的示例：
- "中际旭创和新易盛哪个更值得投资？"
- "CPO和LPO两种技术路线各有什么优缺点？"

答案要求：
- 客观呈现对比结果
- 如果文档信息不足以对比，如实说明
- 可以给出倾向性结论，但要说明依据
"""

MISSING_KNOWLEDGE_SUPPLEMENT = """
## 缺失知识点的特别说明

这类问题测试系统处理"不知道"的能力。

好的示例：
- "光模块行业的ESG评级情况怎么样？"（文档未涉及ESG）
- "2025年的市场预测数据有吗？"（文档只有到2024年）

答案要求：
- 明确说明"文档未提及该信息"或"文档信息不完整"
- 如果有部分相关信息，可以提供并说明局限性
- 不要编造信息
"""

IRRELEVANT_SUPPLEMENT = """
## 无关问题的特别说明

这类问题测试系统的拒答能力。

好的示例：
- "新能源汽车的电池技术发展怎么样？"（文档是关于光模块的）
- "最近美联储加息对股市有什么影响？"（文档未涉及宏观政策）

答案要求：
- 明确说明"该问题与文档内容无关"
- 可以简要说明文档的主题范围
"""

QUESTION_TYPE_SUPPLEMENTS = {
    "single_fact": SINGLE_FACT_SUPPLEMENT,
    "multi_fact": MULTI_FACT_SUPPLEMENT,
    "reasoning": REASONING_SUPPLEMENT,
    "comparative": COMPARATIVE_SUPPLEMENT,
    "missing": MISSING_KNOWLEDGE_SUPPLEMENT,
    "irrelevant": IRRELEVANT_SUPPLEMENT,
}


class TestSetGenerator:
    __test__ = False

    QUESTION_TYPES = {
        "single_fact": "单知识点查询",
        "multi_fact": "多知识点综合",
        "reasoning": "推理型问题",
        "comparative": "对比分析",
        "missing": "缺失知识点",
        "irrelevant": "无关问题",
    }

    TYPE_DISTRIBUTION = {
        "single_fact": 0.30,
        "multi_fact": 0.25,
        "reasoning": 0.15,
        "comparative": 0.15,
        "missing": 0.10,
        "irrelevant": 0.05,
    }

    def __init__(self, config: Dict[str, Any]):
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

    def generate_test_set(
        self,
        meal_name: str,
        strategy: str = None,
        num_questions: int = None,
        llm_preset: str = "default",
        seed: Optional[int] = None,
        token_tracker: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Generate a test set of Q&A pairs for a given meal.

        Args:
            meal_name: Name of the meal to generate questions for.
            strategy: Question generation strategy. 'factual', 'boundary',
                and 'multi_hop' are deprecated and will emit a DeprecationWarning.
                Please use 'document' strategy instead. Defaults to the
                configured default_strategy.
            num_questions: Number of questions to generate. Defaults to the
                configured default_num_questions.
            llm_preset: LLM preset name from the configuration to use for
                question generation.
            seed: Random seed for reproducible chunk selection. If None, the
                random state is not reset.
            token_tracker: Optional token usage tracker passed to the LLM
                generator.

        Returns:
            Dictionary containing the test set metadata and generated questions.

        Raises:
            ValueError: If no chunks are found for the meal or no questions
                could be generated.
        """
        strategy = strategy or self.default_strategy
        num_questions = num_questions or self.default_num_questions

        deprecated_strategies = {"factual", "boundary", "multi_hop"}
        normalized_strategy = strategy.replace("-", "_")
        if normalized_strategy in deprecated_strategies:
            deprecation_msg = (
                f"Strategy '{strategy}' is deprecated and will be removed in a future version. "
                f"Please use 'document' strategy instead."
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
            raise ValueError(f"No chunks found for meal '{meal_name}'")

        grouped = self._group_chunks_by_source(chunks)
        logger.info(
            f"Loaded {len(chunks)} chunks from {len(grouped)} source files"
        )

        chunk_groups = self._select_chunks(grouped, strategy, num_questions)
        logger.info(
            f"Selected {len(chunk_groups)} chunk groups for question generation")

        llm_config = get_llm_config(self.config, llm_preset)
        generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=0.7,
            max_tokens=512,
            token_tracker=token_tracker,
        )

        questions = []
        for i, chunk_group in enumerate(chunk_groups):
            logger.info(f"Generating question {i + 1}/{len(chunk_groups)}...")
            qa = self._generate_question_with_llm(
                chunk_group, strategy, generator)
            if qa is not None:
                source_files = list({
                    c.get("metadata", {}).get("source", "unknown")
                    for c in chunk_group
                })
                source_chunks = [
                    c.get("chunk_id", f"chunk_{i}") for c in chunk_group]
                qa["id"] = f"q{i + 1:03d}"
                qa["source_chunks"] = source_chunks
                qa["source_files"] = source_files
                qa["category"] = strategy
                questions.append(qa)
            else:
                logger.warning(
                    f"Failed to generate question {i + 1}, skipping")

        if not questions:
            raise ValueError("No questions could be generated")

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

    def _resolve_parsed_dir(self, meal_config: MealConfig) -> Optional[Path]:
        """Resolve the parsed artifacts directory for a meal.

        Tries the ArtifactCache first (based on meal data_id), then falls
        back to the config-based ``parser.output_dir`` path.

        Args:
            meal_config: MealConfig object with data_id and config_hashes.

        Returns:
            Path to the parsed directory, or None if not found.
        """
        if meal_config.data_id:
            artifacts_config = self.config.get("artifacts", {})
            artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
            cache = ArtifactCache(artifacts_dir)
            parsed_dir = cache.get_parsed_dir(meal_config.data_id)
            if parsed_dir.exists():
                logger.debug(f"Resolved parsed dir via ArtifactCache: {parsed_dir}")
                return parsed_dir

        fallback = Path(self.config.get("parser", {}).get("output_dir", "data/parsed"))
        if fallback.exists():
            logger.debug(f"Resolved parsed dir via config fallback: {fallback}")
            return fallback

        return None

    def _resolve_chunks_dir(self, meal_config: MealConfig) -> Optional[Path]:
        """Resolve the chunks artifacts directory for a meal.

        Tries the ArtifactCache first (based on meal data_id and chunker
        hash), then falls back to the config-based ``chunker.output_dir``
        path.

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
                cache = ArtifactCache(artifacts_dir)
                chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)
                if chunks_dir.exists():
                    logger.debug(f"Resolved chunks dir via ArtifactCache: {chunks_dir}")
                    return chunks_dir

        fallback = Path(self.config.get("chunker", {}).get("output_dir", "data/chunks"))
        if fallback.exists():
            logger.debug(f"Resolved chunks dir via config fallback: {fallback}")
            return fallback

        return None

    def _load_meal_chunks(self, meal_config) -> List[Dict[str, Any]]:
        """Load chunk data from JSONL files associated with a meal's PDF files.

        Resolves the chunks directory via the ArtifactCache first, falling
        back to the config-based ``chunker.output_dir`` path.

        Args:
            meal_config: MealConfig object whose pdf_files determine the
                source filter for chunk loading.

        Returns:
            List of chunk dictionaries loaded from matching JSONL files.
        """
        chunks_dir = self._resolve_chunks_dir(meal_config)
        if not chunks_dir or not chunks_dir.exists():
            return []

        source_filter = set()
        for mf in meal_config.pdf_files:
            md_path = Path(mf.path).with_suffix(".md")
            source_filter.add(str(md_path).replace("\\", "/"))

        all_chunks = []
        jsonl_files = list(chunks_dir.rglob("*.jsonl"))

        for jsonl_file in jsonl_files:
            try:
                rel_path = str(jsonl_file.relative_to(
                    chunks_dir)).replace("\\", "/")
                jsonl_md_path = rel_path.rsplit(".", 1)[0] + ".md"

                if source_filter and jsonl_md_path not in source_filter:
                    continue

                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            chunk = json.loads(line)
                            all_chunks.append(chunk)
            except Exception as e:
                logger.warning(f"Failed to load {jsonl_file}: {str(e)}")
                continue

        return all_chunks

    def _group_chunks_by_source(
        self, chunks: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """Group chunks by their source file metadata.

        Chunks within each group are sorted by chunk_index in ascending order.

        Args:
            chunks: List of chunk dictionaries, each containing a 'metadata'
                field with a 'source' key.

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
        grouped_chunks: Dict[str, List[Dict]],
        strategy: str,
        num_questions: int,
    ) -> List[List[Dict]]:
        """Select chunk groups for question generation based on the strategy.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            strategy: Question generation strategy. 'factual', 'boundary',
                and 'multi_hop' are deprecated. Please use 'document' strategy
                instead.
            num_questions: Target number of chunk groups to select.

        Returns:
            List of chunk groups, where each group is a list of chunk
            dictionaries.

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
            raise ValueError(f"Unknown strategy: {strategy}")

    def _select_chunks_for_factual(
        self, grouped_chunks: Dict[str, List[Dict]], num_questions: int
    ) -> List[List[Dict]]:
        """Select individual chunks randomly for factual question generation.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            num_questions: Target number of chunks to select.

        Returns:
            List of single-element chunk lists, one per selected chunk.
        """
        all_chunks = []
        for chunks in grouped_chunks.values():
            all_chunks.extend(chunks)

        if not all_chunks:
            return []

        selected = random.sample(
            all_chunks, min(num_questions, len(all_chunks))
        )
        return [[c] for c in selected]

    def _select_chunks_for_boundary(
        self, grouped_chunks: Dict[str, List[Dict]], num_questions: int
    ) -> List[List[Dict]]:
        """Select adjacent chunk pairs for boundary question generation.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            num_questions: Target number of chunk pairs to select.

        Returns:
            List of two-element chunk lists, each containing an adjacent pair.
        """
        pairs = []
        for source, chunks in grouped_chunks.items():
            for i in range(len(chunks) - 1):
                idx_i = chunks[i].get("metadata", {}).get("chunk_index", i)
                idx_next = chunks[i + 1].get("metadata",
                                             {}).get("chunk_index", i + 1)
                if idx_next == idx_i + 1:
                    pairs.append([chunks[i], chunks[i + 1]])

        if not pairs:
            logger.warning(
                "No adjacent chunk pairs found for boundary strategy")
            return []

        return random.sample(pairs, min(num_questions, len(pairs)))

    def _select_chunks_for_multi_hop(
        self, grouped_chunks: Dict[str, List[Dict]], num_questions: int
    ) -> List[List[Dict]]:
        """Select non-adjacent chunk pairs for multi-hop question generation.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            num_questions: Target number of chunk pairs to select.

        Returns:
            List of two-element chunk lists, each containing non-adjacent chunks
            from the same source file.
        """
        groups = []
        for source, chunks in grouped_chunks.items():
            if len(chunks) >= 3:
                for i in range(len(chunks)):
                    for j in range(i + 2, min(i + 5, len(chunks))):
                        groups.append([chunks[i], chunks[j]])

        if not groups:
            logger.warning(
                "No non-adjacent chunk groups found for multi_hop strategy")
            return []

        return random.sample(groups, min(num_questions, len(groups)))

    def _generate_question_with_llm(
        self,
        chunks: List[Dict],
        strategy: str,
        generator,
    ) -> Optional[Dict[str, Any]]:
        """Generate a single Q&A pair from chunks using an LLM.

        Retries up to max_retries times on failure or unparseable responses.

        Args:
            chunks: List of chunk dictionaries to base the question on.
            strategy: Question generation strategy. 'factual', 'boundary',
                and 'multi_hop' are deprecated. Please use 'document' strategy
                instead.
            generator: Generator instance used to call the LLM.

        Returns:
            Dictionary with 'question', 'answer', and 'difficulty' keys, or
            None if all retry attempts fail.

        Raises:
            ValueError: If the strategy is not recognized.
        """
        normalized_strategy = strategy.replace("-", "_")
        if normalized_strategy == "factual":
            prompt = FACTUAL_PROMPT.format(
                chunk_text=chunks[0].get("text", ""))
        elif normalized_strategy == "boundary":
            prompt = BOUNDARY_PROMPT.format(
                chunk1_text=chunks[0].get("text", ""),
                chunk2_text=chunks[1].get(
                    "text", "") if len(chunks) > 1 else "",
            )
        elif normalized_strategy == "multi_hop":
            chunk_texts = "\n\n---\n\n".join(
                f"片段{i + 1}:\n{c.get('text', '')}"
                for i, c in enumerate(chunks)
            )
            prompt = MULTI_HOP_PROMPT.format(chunk_texts=chunk_texts)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        for attempt in range(self.max_retries):
            try:
                response = generator.generate(
                    query=prompt,
                    contexts=[],
                    system_prompt="你是一个测试数据生成器。请严格按照要求的JSON格式输出，不要输出任何其他内容。",
                    category="test_generation",
                )

                qa = self._parse_llm_response(response)
                if qa is not None:
                    return qa

                logger.debug(
                    f"Attempt {attempt + 1}: failed to parse LLM response")
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

        return None

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse an LLM response string into a Q&A dictionary.

        Handles responses wrapped in markdown code blocks and extracts the
        first JSON object found in the text.

        Args:
            response: Raw LLM response string.

        Returns:
            Dictionary with 'question', 'answer', and 'difficulty' keys, or
            None if the response cannot be parsed or is missing required fields.
        """
        try:
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
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
        self, meal_name: str, test_set: Dict[str, Any], filename: str
    ) -> Path:
        """Save a test set to a JSON file in the meal's test_sets directory.

        Args:
            meal_name: Name of the meal the test set belongs to.
            test_set: Test set dictionary to serialize.
            filename: Base filename without extension.

        Returns:
            Path to the saved JSON file.
        """
        meal_manager = MealManager(self.config)
        meal_dir = meal_manager.get_meal_dir(meal_name)
        test_sets_dir = meal_dir / "test_sets"
        ensure_dir(str(test_sets_dir))

        output_path = test_sets_dir / f"{filename}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(test_set, f, ensure_ascii=False, indent=2)

        logger.info(f"Test set saved to {output_path}")
        return output_path

    def generate_document_based_questions(
        self,
        meal_name: str,
        num_questions: int = None,
        type_distribution: Optional[Dict[str, float]] = None,
        llm_preset: str = "default",
        token_tracker: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Generate questions based on full MD documents.

        This method generates questions from complete documents rather than
        chunks, supporting 6 different question types with realistic style.

        Args:
            meal_name: Name of the meal to generate questions for.
            num_questions: Total number of questions to generate. Defaults to
                the configured default_num_questions.
            type_distribution: Custom distribution of question types. Keys are
                type names ('single_fact', 'multi_fact', etc.) and values are
                proportions (0.0-1.0). Defaults to TYPE_DISTRIBUTION.
            llm_preset: LLM preset name from the configuration to use for
                question generation.
            token_tracker: Optional token usage tracker passed to the LLM
                generator.

        Returns:
            Dictionary containing the test set metadata and generated questions
            with quality metrics.

        Raises:
            ValueError: If no documents are found for the meal or no questions
                could be generated.
        """
        num_questions = num_questions or self.default_num_questions
        type_distribution = type_distribution or self.TYPE_DISTRIBUTION

        meal_manager = MealManager(self.config)
        meal_config = meal_manager.load_meal(meal_name)

        logger.info(
            f"Generating document-based questions for meal '{meal_name}' "
            f"(num_questions={num_questions})"
        )

        document_contents = self._load_full_documents(meal_config)
        if not document_contents:
            raise ValueError(f"No documents found for meal '{meal_name}'")

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
            temperature=0.7,
            max_tokens=1024,
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
                        qa["expect_retrieval"] = False
                    elif q_type == "missing":
                        qa["source_files"] = [source_path]
                        qa["expect_no_answer"] = True
                        qa["expect_retrieval"] = False
                    else:
                        qa["source_files"] = [source_path]

                    questions.append(qa)
                    question_id += 1
                else:
                    failed_count += 1
                    logger.warning(
                        f"Failed to generate question, total failures: "
                        f"{failed_count}/{total_attempts}"
                    )

        if not questions:
            raise ValueError("No questions could be generated")

        quality_metrics = self._calculate_quality_metrics(questions)

        test_set = {
            "name": f"document_level_n{num_questions}",
            "meal_data_id": meal_config.data_id,
            "meal_name": meal_name,
            "strategy": "document",
            "created_at": datetime.now().isoformat(),
            "generation_config": {
                "num_questions": num_questions,
                "type_distribution": type_distribution,
                "llm_preset": llm_preset,
            },
            "quality_metrics": quality_metrics,
            "questions": questions,
        }

        filename = f"document_level_n{num_questions}"
        self._save_test_set(meal_name, test_set, filename)

        logger.success(
            f"Generated {len(questions)}/{num_questions} questions "
            f"for meal '{meal_name}' (strategy: document)"
        )
        return test_set

    def _load_full_documents(
        self, meal_config: MealConfig
    ) -> Dict[str, Dict[str, str]]:
        """Load full MD documents associated with a meal's PDF files.

        Resolves the parsed directory via the ArtifactCache first, falling
        back to the config-based ``parser.output_dir`` path.

        Args:
            meal_config: MealConfig object whose pdf_files determine the
                documents to load.

        Returns:
            Dictionary mapping document names to dicts with 'content' and
            'source_path' keys. 'source_path' is the relative path from
            the parsed directory (e.g. 'research_reports/doc.md').
        """
        parsed_dir = self._resolve_parsed_dir(meal_config)
        if not parsed_dir or not parsed_dir.exists():
            logger.warning(f"Parsed directory not found: {parsed_dir}")
            return {}

        source_filter = set()
        for mf in meal_config.pdf_files:
            md_rel = str(Path(mf.path).with_suffix(".md")).replace("\\", "/")
            source_filter.add(md_rel)

        documents = {}
        md_files = list(parsed_dir.rglob("*.md"))

        for md_file in md_files:
            try:
                rel_path = str(md_file.relative_to(parsed_dir)).replace("\\", "/")
                if source_filter and rel_path not in source_filter:
                    continue

                with open(md_file, "r", encoding="utf-8") as f:
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

    def _calculate_question_distribution(
        self,
        num_questions: int,
        type_distribution: Dict[str, float],
    ) -> Dict[str, int]:
        """Calculate the number of questions for each type.

        Args:
            num_questions: Total number of questions to generate.
            type_distribution: Dictionary mapping type names to proportions.

        Returns:
            Dictionary mapping type names to question counts.
        """
        type_counts = {}
        remaining = num_questions

        sorted_types = sorted(
            type_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )

        for i, (q_type, proportion) in enumerate(sorted_types):
            if i == len(sorted_types) - 1:
                type_counts[q_type] = remaining
            else:
                count = int(num_questions * proportion)
                type_counts[q_type] = count
                remaining -= count

        return type_counts

    def _distribute_questions_across_docs(
        self,
        type_counts: Dict[str, int],
        doc_names: List[str],
    ) -> Dict[str, List[str]]:
        """Distribute question types across documents using round-robin.

        Creates a flat list of question types from type_counts, then assigns
        each question to a document in round-robin order so that the total
        number of questions equals the sum of type_counts (not multiplied
        by the number of documents).

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
        doc_question_plans: Dict[str, List[str]] = {
            name: [] for name in doc_names
        }
        for i, q_type in enumerate(question_plan):
            doc_name = doc_names[i % num_docs]
            doc_question_plans[doc_name].append(q_type)

        return doc_question_plans

    def _generate_single_document_question(
        self,
        document_content: str,
        question_type: str,
        generator,
    ) -> Optional[Dict[str, Any]]:
        """Generate a single question from a document using an LLM.

        Args:
            document_content: Full text content of the document.
            question_type: Type of question to generate (e.g., 'single_fact',
                'multi_fact', etc.).
            generator: Generator instance used to call the LLM.

        Returns:
            Dictionary with question data, or None if generation fails.
        """
        q_type_cn = self.QUESTION_TYPES.get(question_type, question_type)

        supplement = QUESTION_TYPE_SUPPLEMENTS.get(question_type, "")

        prompt = DOCUMENT_LEVEL_PROMPT.format(
            document_content=document_content[:8000],
            question_type=q_type_cn
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

    def _parse_document_question_response(
        self, response: str
    ) -> Optional[Dict[str, Any]]:
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
                lines = [l for l in lines if not l.startswith("```")]
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

    def _validate_question_quality(self, question_data: Dict) -> bool:
        """Validate the quality of a generated question.

        Args:
            question_data: Dictionary containing question data.

        Returns:
            True if the question passes quality checks, False otherwise.
        """
        question = question_data.get("question", "")

        authenticity = self._check_authenticity_rules(question)
        if authenticity["has_issues"]:
            logger.debug(
                f"Question failed authenticity check: "
                f"{authenticity['issues']}"
            )
            return False

        if len(question) < 5:
            logger.debug("Question too short")
            return False

        if len(question) > 200:
            logger.debug("Question too long")
            return False

        return True

    def _check_authenticity_rules(self, question: str) -> Dict[str, Any]:
        """Check if a question follows authenticity rules.

        Args:
            question: The question text to check.

        Returns:
            Dictionary with 'has_issues', 'issues', and 'is_authentic' keys.
        """
        issues = []

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
                issues.append(f"包含学术化表述：'{pattern}'")

        template_starts = [
            "请问",
            "请解释",
            "请描述",
        ]
        for start in template_starts:
            if question.startswith(start):
                issues.append(f"模板化开头：'{start}'")

        if len(question) > 100:
            issues.append("问题过长，可能不够直接")

        return {
            "has_issues": len(issues) > 0,
            "issues": issues,
            "is_authentic": len(issues) == 0
        }

    def _calculate_quality_metrics(
        self, questions: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate quality metrics for generated questions.

        Args:
            questions: List of generated question dictionaries.

        Returns:
            Dictionary containing quality metrics.
        """
        if not questions:
            return {
                "format_correct_rate": 0.0,
                "authenticity_pass_rate": 0.0,
                "type_distribution": {},
            }

        type_counts = {}
        for q in questions:
            q_type = q.get("question_type", "unknown")
            type_counts[q_type] = type_counts.get(q_type, 0) + 1

        total = len(questions)
        authenticity_passed = sum(
            1 for q in questions
            if self._check_authenticity_rules(q.get("question", ""))["is_authentic"]
        )

        return {
            "format_correct_rate": 1.0,
            "authenticity_pass_rate": authenticity_passed / total,
            "type_distribution": type_counts,
        }
