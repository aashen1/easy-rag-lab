import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.meal import MealManager
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


class TestSetGenerator:
    __test__ = False

    def __init__(self, config: Dict[str, Any]):
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
    ) -> Dict[str, Any]:
        strategy = strategy or self.default_strategy
        num_questions = num_questions or self.default_num_questions

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
        logger.info(f"Selected {len(chunk_groups)} chunk groups for question generation")

        from src.generator import Generator

        llm_config = get_llm_config(self.config, llm_preset)
        generator = Generator(
            model_name=llm_config["model_name"],
            api_key=llm_config["api_key"],
            base_url=llm_config["base_url"],
            temperature=0.7,
            max_tokens=512,
        )

        questions = []
        for i, chunk_group in enumerate(chunk_groups):
            logger.info(f"Generating question {i + 1}/{len(chunk_groups)}...")
            qa = self._generate_question_with_llm(chunk_group, strategy, generator)
            if qa is not None:
                source_files = list({
                    c.get("metadata", {}).get("source", "unknown")
                    for c in chunk_group
                })
                source_chunks = [c.get("chunk_id", f"chunk_{i}") for c in chunk_group]
                qa["id"] = f"q{i + 1:03d}"
                qa["source_chunks"] = source_chunks
                qa["source_files"] = source_files
                qa["category"] = strategy
                questions.append(qa)
            else:
                logger.warning(f"Failed to generate question {i + 1}, skipping")

        if not questions:
            raise ValueError("No questions could be generated")

        test_set = {
            "name": f"auto_{strategy}",
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

        filename = f"auto_{strategy}"
        self._save_test_set(meal_name, test_set, filename)

        logger.success(
            f"Generated {len(questions)}/{num_questions} questions "
            f"for meal '{meal_name}' (strategy: {strategy})"
        )
        return test_set

    def _load_meal_chunks(self, meal_config) -> List[Dict[str, Any]]:
        chunks_dir = Path(self.config.get("chunker", {}).get("output_dir", "data/chunks"))
        if not chunks_dir.exists():
            return []

        source_filter = set()
        for mf in meal_config.pdf_files:
            md_path = Path(mf.path).with_suffix(".md")
            source_filter.add(str(md_path).replace("\\", "/"))

        all_chunks = []
        jsonl_files = list(chunks_dir.rglob("*.jsonl"))

        for jsonl_file in jsonl_files:
            try:
                rel_path = str(jsonl_file.relative_to(chunks_dir)).replace("\\", "/")
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
        pairs = []
        for source, chunks in grouped_chunks.items():
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
        self, grouped_chunks: Dict[str, List[Dict]], num_questions: int
    ) -> List[List[Dict]]:
        groups = []
        for source, chunks in grouped_chunks.items():
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
        chunks: List[Dict],
        strategy: str,
        generator,
    ) -> Optional[Dict[str, Any]]:
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
                )

                qa = self._parse_llm_response(response)
                if qa is not None:
                    return qa

                logger.debug(f"Attempt {attempt + 1}: failed to parse LLM response")
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

        return None

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
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
        meal_manager = MealManager(self.config)
        meal_dir = meal_manager.get_meal_dir(meal_name)
        test_sets_dir = meal_dir / "test_sets"
        ensure_dir(str(test_sets_dir))

        output_path = test_sets_dir / f"{filename}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(test_set, f, ensure_ascii=False, indent=2)

        logger.info(f"Test set saved to {output_path}")
        return output_path
