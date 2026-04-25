import difflib
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
from src.test_set_manager import TestSetManager, TestSetMetadata
from src.utils import get_llm_config

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
- 对抗性问题：故意设计容易让RAG系统出错的边界场景

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

EVIDENCE_AWARE_PROMPT = """你是一位金融行业从业者，正在阅读一份研究报告的若干片段。请基于这些片段，生成一个你会真实提出的问题，并提供支撑答案的原文引用。

## 你的背景
- 你可能是投资分析师、基金经理、行业研究员或企业战略规划人员
- 你关心的是能帮助你做决策的信息
- 你的提问风格是直接、口语化、不啰嗦

## 文档片段
以下是从同一份文档中选取的 {num_segments} 个片段：

{segments_text}

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

2. 答案要求：
   - 答案应基于文档内容
   - 答案中必须使用【原文引用】标注引用内容
   - 如果文档无法回答，明确说明原因

3. 证据要求：
   - 必须提供支撑答案的原文引用
   - 引用必须与片段原文完全一致（逐字逐句）
   - 说明每个引用如何支撑答案

## 输出格式

请严格按以下JSON格式输出（不要输出其他内容）：

{{
    "question": "你的问题",
    "answer": "答案文本，包含【原文引用】标注",
    "question_type": "{question_type}",
    "difficulty": "easy/medium/hard",
    "evidence": [
        {{
            "segment_index": 0,
            "quote": "必须与选段原文完全一致的引用",
            "relevance": "该引用如何支撑答案"
        }}
    ],
    "selected_segments": [0, 1]
}}

注意：
- segment_index 对应片段编号（从0开始）
- quote 必须与片段原文完全一致，不能修改或概括
- selected_segments 仅多知识点综合问题需要填写，其他类型可省略
- 单知识点问题通常只需1条证据
- 多知识点综合问题需要多条证据，且必须填写 selected_segments

重要数值规则：
- 文档中的财务数据通常以"元"为单位（如 12,162,684,368.86）
- 答案中请换算为"亿元"：÷100,000,000（即去掉8位数字）
- 正确示例：12,162,684,368.86元 = 121.63亿元
- 错误示例：12,162,684,368.86元 ≠ 1216.3亿元（多了10倍）
- 如果原文已用"亿元"为单位，则直接引用，不要再次换算"""

EVIDENCE_SINGLE_FACT_SUPPLEMENT = """
## 单知识点查询的特别说明

好的示例：
- "2024年光模块市场规模多少？"
- "CPO的全称是什么？"
- "中际旭创的主要产品是什么？"

证据要求：
- 通常只需1条证据
- 引用应直接包含答案所需的具体数据或事实
- quote 必须逐字逐句与原文一致

不好的示例（太学术化）：
- "请根据文档说明2024年光模块市场规模"
- "文档中提到的CPO技术的全称是什么？"
"""

EVIDENCE_MULTI_FACT_SUPPLEMENT = """
## 多知识点综合的特别说明

好的示例：
- "科瑞技术和猎奇智能在光模块设备上有什么区别？"
- "光模块行业未来几年的增长点主要在哪里？"

证据要求：
- 必须提供2条或以上证据
- 每条证据来自不同的片段
- 必须填写 selected_segments 字段，列出涉及的所有片段编号
- 引用应展示不同片段的关键信息

答案要求：
- 答案应综合多个片段的信息
- 明确标注信息来源（如"片段0提到..."、"片段2显示..."）
"""

EVIDENCE_REASONING_SUPPLEMENT = """
## 推理型问题的特别说明

好的示例：
- "为什么CPO能降低功耗？"
- "如果800G需求翻倍，对设备商有什么影响？"

证据要求：
- 提供支撑推理过程的原文依据
- 引用应包含推理的前提条件或逻辑链条
- relevance 字段应说明引用如何支撑推理步骤

答案要求：
- 必须展示推理过程
- 推理依据必须来自文档
- 可以有合理的推断，但要说明依据
"""

EVIDENCE_COMPARATIVE_SUPPLEMENT = """
## 对比分析的特别说明

好的示例：
- "中际旭创和新易盛哪个更值得投资？"
- "CPO和LPO两种技术路线各有什么优缺点？"

证据要求：
- 为对比的每个对象提供对应的引用
- 引用应展示对比的关键维度
- relevance 字段应说明引用在对比中的作用

答案要求：
- 客观呈现对比结果
- 如果文档信息不足以对比，如实说明
- 可以给出倾向性结论，但要说明依据
"""

EVIDENCE_MISSING_SUPPLEMENT = """
## 缺失知识点的特别说明

这类问题测试系统处理"不知道"的能力。

好的示例：
- "光模块行业的ESG评级情况怎么样？"（文档未涉及ESG）
- "2025年的市场预测数据有吗？"（文档只有到2024年）

证据要求：
- evidence 数组可以为空，或提供部分相关但不完整的信息
- 如果提供证据，relevance 应说明该信息的局限性

答案要求：
- 明确说明"文档未提及该信息"或"文档信息不完整"
- 如果有部分相关信息，可以提供并说明局限性
- 不要编造信息
"""

EVIDENCE_IRRELEVANT_SUPPLEMENT = """
## 无关问题的特别说明

这类问题测试系统的拒答能力。

好的示例：
- "新能源汽车的电池技术发展怎么样？"（文档是关于光模块的）
- "最近美联储加息对股市有什么影响？"（文档未涉及宏观政策）

证据要求：
- evidence 数组应为空
- 不需要提供任何引用

答案要求：
- 明确说明"该问题与文档内容无关"
- 可以简要说明文档的主题范围
"""

EVIDENCE_ADVERSARIAL_SUPPLEMENT = """
## 对抗性问题的特别说明

请生成一道故意设计容易让RAG系统出错的边界场景问题。

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

证据要求：
- 必须提供包含正确信息的原文引用
- 引用应直接反驳问题中的诱饵信息
"""

EVIDENCE_QUESTION_TYPE_SUPPLEMENTS = {
    "single_fact": EVIDENCE_SINGLE_FACT_SUPPLEMENT,
    "multi_fact": EVIDENCE_MULTI_FACT_SUPPLEMENT,
    "reasoning": EVIDENCE_REASONING_SUPPLEMENT,
    "comparative": EVIDENCE_COMPARATIVE_SUPPLEMENT,
    "missing": EVIDENCE_MISSING_SUPPLEMENT,
    "irrelevant": EVIDENCE_IRRELEVANT_SUPPLEMENT,
    "adversarial": EVIDENCE_ADVERSARIAL_SUPPLEMENT,
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
        "adversarial": "对抗性问题",
    }

    TYPE_DISTRIBUTION = {
        "single_fact": 0.30,
        "multi_fact": 0.25,
        "reasoning": 0.15,
        "comparative": 0.15,
        "missing": 0.10,
        "irrelevant": 0.05,
        "adversarial": 0.00,
    }

    DOCUMENT_TRUNCATE_MAX = 8000

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

    def _select_segments_for_question_type(
        self,
        segments: list[dict[str, Any]],
        question_type: str,
        num_segments: int = 1,
    ) -> list[dict[str, Any]]:
        """Select document segments based on question type.

        Different question types require different amounts of context:
        - single_fact: Random 1 segment
        - multi_fact/reasoning/comparative: Random 2-3 segments
        - missing: Random 1 segment
        - irrelevant: Empty list (no document context needed)

        Args:
            segments: List of segment dictionaries from _segment_document.
            question_type: Type of question to generate (e.g., 'single_fact',
                'multi_fact', 'reasoning', 'comparative', 'missing', 'irrelevant').
            num_segments: Number of segments to select. For multi-segment types,
                this is the maximum; actual count may vary. Defaults to 1.

        Returns:
            List of selected segment dictionaries. Empty list for irrelevant
            questions or when no segments are available.
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

        For multi-hop question types (multi_fact, reasoning, comparative),
        selects multiple candidate segments with diversity in document position.
        For other types, delegates to _select_segments_for_question_type.

        Args:
            segments: List of segment dictionaries from _segment_document.
            question_type: Type of question to generate.
            num_candidates: Number of candidate segments to select for multi-hop
                types. Defaults to 4.

        Returns:
            List of selected segment dictionaries for multi-hop types,
            or result of _select_segments_for_question_type for other types.
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

        Ensures selected segments are spread across different parts of the
        document to maximize information diversity for multi-hop questions.

        Args:
            segments: List of segment dictionaries with 'segment_index' key.
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

        Extracts and validates the 'selected_segments' field from the LLM
        response. Returns all segment indices if the field is missing or
        invalid.

        Args:
            llm_response: Parsed LLM response dictionary.
            num_available_segments: Total number of available segments.

        Returns:
            List of valid segment indices. Returns all indices (0 to
            num_available_segments-1) if selection is invalid or missing.
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

        Performs a simple heuristic check to determine if the selected
        segments are potentially related by looking for shared keywords.
        Logs a warning if segments seem unrelated but does not reject them.

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

        Identifies domain-specific terms, numbers with units, and
        significant Chinese words for keyword matching.

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

        Determines which chunks belong to each segment by checking if the
        chunk's text content overlaps with the segment's text content. Uses
        a sliding-window fuzzy match to handle OCR-induced whitespace
        differences between segment text (from raw markdown) and chunk text
        (from OCR-processed content).

        Args:
            segments: List of segment dictionaries with 'text' and
                'segment_index' keys.
            doc_chunks: List of chunk dictionaries from JSONL files, each
                containing 'chunk_id' and 'text' keys.

        Returns:
            Dictionary mapping segment_index to list of chunk_ids whose text
            overlaps with that segment. Segments with no overlapping chunks
            are mapped to empty lists.
        """
        mapping: dict[int, list[str]] = {}

        chunk_texts: list[tuple[str, str]] = []
        for chunk in doc_chunks:
            chunk_id = chunk.get("chunk_id", "")
            text = chunk.get("text", "")
            if chunk_id and text:
                chunk_texts.append((chunk_id, text))

        for segment in segments:
            seg_text = segment.get("text", "")
            seg_index = segment.get("segment_index", 0)

            overlapping_chunks: list[str] = []

            if seg_text:
                for chunk_id, chunk_text in chunk_texts:
                    if self._texts_overlap(seg_text, chunk_text):
                        overlapping_chunks.append(chunk_id)

            mapping[seg_index] = overlapping_chunks

        return mapping

    @staticmethod
    def _texts_overlap(text_a: str, text_b: str, min_overlap_chars: int = 30) -> bool:
        """Check if two texts have significant overlapping content.

        Uses a sliding-window approach: extracts substrings from text_a and
        checks if they appear in text_b. Handles OCR-induced whitespace
        differences by normalizing both texts before comparison.

        Args:
            text_a: First text (typically segment text).
            text_b: Second text (typically chunk text).
            min_overlap_chars: Minimum number of consecutive characters that
                must match to consider the texts overlapping.

        Returns:
            True if the texts share significant overlapping content.
        """
        if not text_a or not text_b:
            return False

        def _normalize(t: str) -> str:
            return " ".join(t.split())

        norm_a = _normalize(text_a)
        norm_b = _normalize(text_b)

        window = min_overlap_chars
        step = max(1, window // 3)

        for start in range(0, len(norm_a) - window + 1, step):
            substr = norm_a[start : start + window]
            if substr in norm_b:
                return True

        return False

    def generate_test_set(
        self,
        meal_name: str,
        strategy: str = None,
        num_questions: int = None,
        llm_preset: str = "default",
        seed: int | None = None,
        token_tracker: Any | None = None,
    ) -> dict[str, Any]:
        """Generate a test set of Q&A pairs for a given meal.

        Args:
            meal_name: Name of the meal to generate questions for.
            strategy: Question generation strategy. Supported strategies:
                - 'hybrid': Use hybrid segment-chunk strategy (recommended)
                - 'document': Use document-based generation (delegates to hybrid)
                - 'factual', 'boundary', 'multi_hop': Deprecated legacy strategies
                Defaults to the configured default_strategy.
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
            TestSetError: If no chunks are found for the meal or no questions
                could be generated.
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

        Tries the ArtifactCache first (based on meal data_id and parser_hash),
        then falls back to the config-based ``parser.output_dir`` path.

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

        fallback = Path(self.config.get("parser", {}).get("output_dir", "data/parsed"))
        if fallback.exists():
            logger.debug(f"Resolved parsed dir via config fallback: {fallback}")
            return fallback

        return None

    def _resolve_chunks_dir(self, meal_config: MealConfig) -> Path | None:
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
                raw_dir = Path(
                    self.config.get("parser", {}).get("input_dir", "data/raw")
                )
                cache = ArtifactCache(artifacts_dir, raw_dir)
                chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)
                if chunks_dir.exists():
                    logger.debug(f"Resolved chunks dir via ArtifactCache: {chunks_dir}")
                    return chunks_dir

        fallback = Path(self.config.get("chunker", {}).get("output_dir", "data/chunks"))
        if fallback.exists():
            logger.debug(f"Resolved chunks dir via config fallback: {fallback}")
            return fallback

        return None

    def _load_meal_chunks(self, meal_config) -> list[dict[str, Any]]:
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
        grouped_chunks: dict[str, list[dict]],
        strategy: str,
        num_questions: int,
    ) -> list[list[dict]]:
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
            raise TestSetError(f"Unknown strategy: {strategy}")

    def _select_chunks_for_factual(
        self, grouped_chunks: dict[str, list[dict]], num_questions: int
    ) -> list[list[dict]]:
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

        selected = random.sample(all_chunks, min(num_questions, len(all_chunks)))
        return [[c] for c in selected]

    def _select_chunks_for_boundary(
        self, grouped_chunks: dict[str, list[dict]], num_questions: int
    ) -> list[list[dict]]:
        """Select adjacent chunk pairs for boundary question generation.

        Args:
            grouped_chunks: Dictionary mapping source file names to chunk lists.
            num_questions: Target number of chunk pairs to select.

        Returns:
            List of two-element chunk lists, each containing an adjacent pair.
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
            num_questions: Target number of chunk pairs to select.

        Returns:
            List of two-element chunk lists, each containing non-adjacent chunks
            from the same source file.
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

        This method combines document-level segmentation with chunk-level
        evidence verification for high-quality question generation with
        reliable ground truth.

        Args:
            meal_name: Name of the meal to generate questions for.
            num_questions: Total number of questions to generate. Defaults to
                the configured default_num_questions.
            name: Name for the test set. Defaults to
                f"hybrid_n{num_questions}".
            type_distribution: Custom distribution of question types. Keys are
                type names ('single_fact', 'multi_fact', etc.) and values are
                proportions (0.0-1.0). Defaults to TYPE_DISTRIBUTION.
            llm_preset: LLM preset name from the configuration to use for
                question generation.
            token_tracker: Optional token usage tracker passed to the LLM
                generator.
            chunks_dir: Optional path to chunks directory for locating answer
                chunks. When provided, bypasses ArtifactCache resolution.

        Returns:
            Dictionary containing the test set metadata and generated questions
            with quality metrics including quote_verification_rate and
            ground_truth_confidence.

        Raises:
            TestSetError: If no documents are found for the meal or no questions
                could be generated.
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
            doc_chunks = doc_chunks_map.get(doc_name, [])

            segments = self._segment_document(doc_content, self.segment_size)
            if not segments:
                logger.warning(f"No segments generated for document: {doc_name}")
                continue

            segment_chunk_map = self._map_segments_to_chunks(segments, doc_chunks)

            for q_type in assigned_types:
                total_attempts += 1
                logger.info(
                    f"Generating question {question_id}/{num_questions} "
                    f"(type={q_type}, doc={doc_name})..."
                )

                qa = self._generate_hybrid_question(
                    segments=segments,
                    doc_chunks=doc_chunks,
                    segment_chunk_map=segment_chunk_map,
                    question_type=q_type,
                    generator=generator,
                    source_path=source_path,
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
                        qa["expect_retrieval"] = True
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
                doc_chunks = doc_chunks_map.get(doc_name, [])

                segments = self._segment_document(doc_content, self.segment_size)
                if not segments:
                    continue

                segment_chunk_map = self._map_segments_to_chunks(segments, doc_chunks)

                logger.info(
                    f"Supplemental question {len(questions) + 1}/{num_questions} "
                    f"(type={q_type}, doc={doc_name})..."
                )

                qa = self._generate_hybrid_question(
                    segments=segments,
                    doc_chunks=doc_chunks,
                    segment_chunk_map=segment_chunk_map,
                    question_type=q_type,
                    generator=generator,
                    source_path=source_path,
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
                        qa["expect_retrieval"] = True
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

                    questions.append(qa)
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

        Uses the full-dataset meal to load all documents, applies content
        deduplication, and generates questions with golden-specific
        metadata (FAILURE_MODES, audit fields, immutable policy).

        Args:
            num_questions: Total number of questions to generate.
            name: Name for the golden test set.
            llm_preset: LLM preset name for generation.
            token_tracker: Optional token tracker.
            type_distribution: Override type distribution. Defaults to
                GOLDEN_TYPE_DISTRIBUTION.
            seed: Random seed for reproducibility.

        Returns:
            Dictionary containing the golden test set.

        Raises:
            TestSetError: If no full-dataset meal is found or generation
                fails.
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

        for doc_name, doc_data in filtered_contents.items():
            assigned_types = doc_question_plans.get(doc_name, [])
            if not assigned_types:
                continue

            doc_content = doc_data["content"]
            source_path = doc_data["source_path"]
            doc_chunks = doc_chunks_map.get(doc_name, [])

            segments = self._segment_document(doc_content, self.segment_size)
            if not segments:
                logger.warning(f"No segments for document: {doc_name}")
                continue

            segment_chunk_map = self._map_segments_to_chunks(segments, doc_chunks)

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
                    segment_chunk_map=segment_chunk_map,
                    question_type=q_type,
                    generator=generator,
                    source_path=source_path,
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
                        qa["expect_retrieval"] = True
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

                    qa.setdefault("metadata", {})
                    qa["metadata"]["author"] = "llm_assisted"
                    qa["metadata"]["reviewed"] = False
                    qa["metadata"]["review_notes"] = ""
                    if not qa["metadata"].get("target_failure_mode"):
                        qa["metadata"]["target_failure_mode"] = self.FAILURE_MODES.get(
                            q_type, ""
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
            doc_names = list(filtered_contents.keys())
            all_types = list(type_distribution.keys())
            extra_attempt = 0
            max_extra_attempts = deficit * 3

            while len(questions) < num_questions and extra_attempt < max_extra_attempts:
                extra_attempt += 1
                doc_name = doc_names[extra_attempt % len(doc_names)]
                q_type = all_types[extra_attempt % len(all_types)]
                doc_data = filtered_contents[doc_name]
                doc_content = doc_data["content"]
                source_path = doc_data["source_path"]
                doc_chunks = doc_chunks_map.get(doc_name, [])

                segments = self._segment_document(doc_content, self.segment_size)
                if not segments:
                    continue

                segment_chunk_map = self._map_segments_to_chunks(segments, doc_chunks)

                logger.info(
                    f"Supplemental question {len(questions) + 1}/{num_questions} "
                    f"(type={q_type}, doc={doc_name})..."
                )

                qa = self._generate_hybrid_question(
                    segments=segments,
                    doc_chunks=doc_chunks,
                    segment_chunk_map=segment_chunk_map,
                    question_type=q_type,
                    generator=generator,
                    source_path=source_path,
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
                        qa["expect_retrieval"] = True
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

                    excerpt = qa.get("ground_truth_excerpt", "")
                    if excerpt and q_type not in ("irrelevant",):
                        excerpt_verified = self._verify_excerpt_in_document(
                            excerpt,
                            doc_content,
                        )
                        qa.setdefault("metadata", {})
                        qa["metadata"]["excerpt_verified"] = excerpt_verified

                    qa.setdefault("metadata", {})
                    qa["metadata"]["author"] = "llm_assisted"
                    qa["metadata"]["reviewed"] = False
                    qa["metadata"]["review_notes"] = ""
                    if not qa["metadata"].get("target_failure_mode"):
                        qa["metadata"]["target_failure_mode"] = self.FAILURE_MODES.get(
                            q_type, ""
                        )

                    questions.append(qa)
                    question_id += 1
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
        segment_chunk_map: dict[int, list[str]],
        question_type: str,
        generator: Generator,
        source_path: str,
    ) -> dict[str, Any] | None:
        """Generate a single question using hybrid strategy.

        Args:
            segments: List of document segments.
            doc_chunks: List of chunk dictionaries for the document.
            segment_chunk_map: Mapping from segment index to chunk IDs.
            question_type: Type of question to generate.
            generator: Generator instance for LLM calls.
            source_path: Source path of the document.

        Returns:
            Dictionary with question data including verified evidence and
            source_chunks, or None if generation fails.
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

        for attempt in range(self.max_retries):
            qa = self._generate_question_with_evidence(
                selected_segments=selected_segments,
                question_type=question_type,
                generator=generator,
            )

            if qa is None:
                continue

            if question_type == "irrelevant":
                qa["ground_truth_excerpt"] = ""
                return qa

            evidence_list = qa.get("evidence", [])
            if not evidence_list:
                if question_type == "missing":
                    qa["ground_truth_excerpt"] = ""
                    return qa
                logger.debug(f"No evidence provided for question type: {question_type}")
                continue

            validation = self._validate_evidence(
                evidence_list, selected_segments, question_type
            )

            if not validation["valid"]:
                logger.debug(
                    f"Evidence validation failed on attempt {attempt + 1}: "
                    f"{len(validation['invalid_quotes'])} invalid quotes"
                )
                if attempt < self.max_retries - 1:
                    continue

            qa["evidence"] = validation["verified_evidence"]

            if question_type in multi_hop_types:
                source_chunks = self._locate_multi_hop_chunks(
                    validation["verified_evidence"],
                    selected_segments,
                    segment_chunk_map,
                    doc_chunks,
                )
            else:
                first_evidence = (
                    validation["verified_evidence"][0]
                    if validation["verified_evidence"]
                    else {}
                )
                quote = first_evidence.get("quote", "")
                source_chunks = self._locate_chunks_by_quote(
                    quote, selected_segments, segment_chunk_map, doc_chunks
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

    def _validate_numerical_accuracy(
        self, question_data: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None]:
        """Validate numerical accuracy in answer against ground_truth_excerpt.

        Detects 10x unit conversion errors where excerpt has large numbers
        in yuan but answer incorrectly converts to yi-yuan.

        Args:
            question_data: Dictionary containing 'answer' and
                'ground_truth_excerpt'.

        Returns:
            Tuple of (is_valid, correction). is_valid is True if numbers
            are consistent. correction is None or contains fix information.
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

        errors: list[dict[str, Any]] = []
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
                "suggestion": (
                    "Answer contains 10x unit conversion errors. "
                    "Values in yuan should be divided by 100,000,000 "
                    "to convert to yi-yuan."
                ),
            }
            return False, correction

        return True, None

    def _verify_excerpt_in_document(
        self,
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

    def _detect_content_overlaps(
        self,
        documents: list[dict[str, Any]],
        threshold: float = 0.8,
    ) -> list[tuple[str, str, float]]:
        """Detect content overlap between document pairs.

        Samples 3 segments (beginning, middle, end) from the shorter
        document and checks if they appear in the longer document. If the
        hit rate exceeds the threshold, the shorter document is marked as
        supplementary.

        Args:
            documents: List of document dicts with 'doc_id' and 'content'.
            threshold: Minimum hit rate to mark as supplementary.

        Returns:
            List of tuples: (supplementary_doc_id, primary_doc_id, ratio).
        """
        overlaps: list[tuple[str, str, float]] = []
        sample_size = 500

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

                samples = [
                    short_text[:sample_size],
                    short_text[
                        len(short_text) // 2 : len(short_text) // 2 + sample_size
                    ],
                    short_text[-sample_size:],
                ]

                hits = sum(1 for s in samples if len(s) >= 50 and s in long_text)
                hit_rate = hits / len(samples)

                if hit_rate >= threshold:
                    overlaps.append((shorter["doc_id"], longer["doc_id"], hit_rate))

        return overlaps

    def _build_primary_pool(
        self,
        documents: list[dict[str, Any]],
        overlaps: list[tuple[str, str, float]],
    ) -> list[dict[str, Any]]:
        """Build primary document pool, excluding supplementary documents.

        If document A is marked as supplementary to B, A is excluded from
        the primary pool. If A is supplementary to both B and C, only the
        longer one (B or C) is kept as the primary.

        Args:
            documents: List of document dicts.
            overlaps: Overlap tuples from _detect_content_overlaps().

        Returns:
            List of primary document dicts (supplementary excluded).
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
                    (d for d in documents if d["doc_id"] == primary_id), None
                )
                if (
                    new_doc
                    and existing_doc
                    and len(new_doc["content"]) > len(existing_doc["content"])
                ):
                    primary_map[supp_id] = primary_id

        return [d for d in documents if d["doc_id"] not in supplementary_ids]

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
            Dictionary with question data including evidence list, or None
            if parsing fails.
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

        Includes standard metrics plus quote_verification_rate and
        ground_truth_confidence.

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
                "quote_verification_rate": 0.0,
                "ground_truth_confidence": 0.0,
                "excerpt_verified_rate": 0.0,
                "numerical_correction_rate": 0.0,
            }

        base_metrics = self._calculate_quality_metrics(questions)

        total = len(questions)
        questions_with_verified_quotes = 0
        total_confidence = 0.0

        for q in questions:
            evidence = q.get("evidence", [])
            if not evidence:
                if q.get("question_type") in ("irrelevant", "missing"):
                    questions_with_verified_quotes += 1
                continue

            verified_evidence = [e for e in evidence if e.get("verified", False)]
            if verified_evidence:
                questions_with_verified_quotes += 1

                for e in verified_evidence:
                    match_type = e.get("match_type", "none")
                    if match_type == "exact":
                        total_confidence += 1.0
                    elif match_type == "fuzzy":
                        total_confidence += 0.9

        quote_verification_rate = questions_with_verified_quotes / total

        total_verified_evidence = sum(
            len([e for e in q.get("evidence", []) if e.get("verified", False)])
            for q in questions
        )
        ground_truth_confidence = (
            total_confidence / total_verified_evidence
            if total_verified_evidence > 0
            else 0.0
        )

        questions_with_excerpt = sum(
            1 for q in questions if q.get("metadata", {}).get("excerpt_verified", True)
        )
        questions_with_numerical_correction = sum(
            1
            for q in questions
            if q.get("metadata", {}).get("numerical_auto_corrected", False)
        )
        excerpt_verified_rate = questions_with_excerpt / total
        numerical_correction_rate = questions_with_numerical_correction / total

        return {
            **base_metrics,
            "quote_verification_rate": round(quote_verification_rate, 4),
            "ground_truth_confidence": round(ground_truth_confidence, 4),
            "excerpt_verified_rate": round(excerpt_verified_rate, 4),
            "numerical_correction_rate": round(numerical_correction_rate, 4),
        }

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

        This method generates questions from complete documents rather than
        chunks, supporting 6 different question types with realistic style.

        Args:
            meal_name: Name of the meal to generate questions for.
            num_questions: Total number of questions to generate. Defaults to
                the configured default_num_questions.
            name: Name for the test set. Defaults to
                f"document_level_n{num_questions}".
            type_distribution: Custom distribution of question types. Keys are
                type names ('single_fact', 'multi_fact', etc.) and values are
                proportions (0.0-1.0). Defaults to TYPE_DISTRIBUTION.
            llm_preset: LLM preset name from the configuration to use for
                question generation.
            token_tracker: Optional token usage tracker passed to the LLM
                generator.
            chunks_dir: Optional path to chunks directory for locating answer
                chunks. When provided, passed to _locate_answer_chunks() to
                bypass ArtifactCache resolution.
            use_hybrid: If True, delegate to generate_hybrid_questions for
                improved ground truth quality. If False, use the legacy
                document-based generation. Defaults to True.

        Returns:
            Dictionary containing the test set metadata and generated questions
            with quality metrics.

        Raises:
            TestSetError: If no documents are found for the meal or no questions
                could be generated.
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
                        qa["expect_retrieval"] = True
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
                        qa["expect_retrieval"] = True
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

        Generates only the deficit number of questions and appends them to
        the existing test set, avoiding wasteful full regeneration.

        Args:
            meal_name: Name of the meal to generate questions for.
            existing_test_set: Existing test set dictionary to supplement.
            target_count: Target total number of questions.
            llm_preset: LLM preset name from the configuration.
            token_tracker: Optional token usage tracker.
            chunks_dir: Optional path to chunks directory for locating answer
                chunks.

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
                    qa["expect_retrieval"] = True
                else:
                    qa["source_files"] = [source_path]
                    answer_text = qa.get("answer", "")
                    qa["source_chunks"] = self._locate_answer_chunks(
                        answer_text,
                        source_path,
                        meal_config=meal_config,
                        chunks_dir=chunks_dir,
                    )

                new_questions.append(qa)
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

    def _load_full_documents(
        self, meal_config: MealConfig
    ) -> dict[str, dict[str, str]]:
        """Load full documents associated with a meal's PDF files.

        Resolves the parsed directory via the ArtifactCache first, falling
        back to the config-based ``parser.output_dir`` path. Supports both
        .md and .pages.json formats using LazyDocumentLoader for efficient
        on-demand loading.

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

    def _calculate_question_distribution(
        self,
        num_questions: int,
        type_distribution: dict[str, float],
    ) -> dict[str, int]:
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
            type_distribution.items(), key=lambda x: x[1], reverse=True
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
        type_counts: dict[str, int],
        doc_names: list[str],
    ) -> dict[str, list[str]]:
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
            question_type: Type of question to generate (e.g., 'single_fact',
                'multi_fact', etc.).
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
        question = question_data.get("question", "")

        authenticity = self._check_authenticity_rules(question)
        if authenticity["has_issues"]:
            logger.debug(
                f"Question failed authenticity check: {authenticity['issues']}"
            )
            return False

        if len(question) < 5:
            logger.debug("Question too short")
            return False

        if len(question) > 200:
            logger.debug("Question too long")
            return False

        return True

    def _check_authenticity_rules(self, question: str) -> dict[str, Any]:
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
            "is_authentic": len(issues) == 0,
        }

    def _calculate_quality_metrics(self, questions: list[dict]) -> dict[str, Any]:
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
            1
            for q in questions
            if self._check_authenticity_rules(q.get("question", ""))["is_authentic"]
        )

        return {
            "format_correct_rate": 1.0,
            "authenticity_pass_rate": authenticity_passed / total,
            "type_distribution": type_counts,
        }

    def _locate_chunks_by_quote(
        self,
        quote: str,
        segments: list[dict[str, Any]],
        segment_chunk_map: dict[int, list[str]],
        doc_chunks: list[dict[str, Any]],
    ) -> list[str]:
        """Locate chunk IDs that contain a verified quote text.

        Finds which segment contains the quote using character position,
        then looks up the chunk_ids from segment_chunk_map and verifies
        the quote appears in each chunk's text.

        Args:
            quote: The verified quote text to locate.
            segments: List of segment dictionaries with 'text', 'start_char',
                'end_char', and 'segment_index' keys.
            segment_chunk_map: Dictionary mapping segment_index to list of
                chunk_ids that overlap with that segment.
            doc_chunks: List of all chunk dictionaries from the document,
                each containing 'chunk_id' and 'text' keys.

        Returns:
            List of chunk_id strings that contain the quote text.
            Returns an empty list if no chunks contain the quote or if
            the quote cannot be located in any segment.
        """
        if not quote or not segments or not doc_chunks:
            return []

        containing_segment_index: int | None = None
        for segment in segments:
            segment_text = segment.get("text", "")
            seg_index = segment.get("segment_index")

            verification = self._verify_quote_in_segment(quote, segment_text)
            if verification["found"]:
                containing_segment_index = seg_index
                break

        if containing_segment_index is None:
            logger.debug(
                f"Quote not found in any segment, searching all chunks: {quote[:50]}..."
            )
            chunk_ids = [
                c.get("chunk_id", "") for c in doc_chunks if c.get("chunk_id", "")
            ]
        else:
            chunk_ids = segment_chunk_map.get(containing_segment_index, [])
            if not chunk_ids:
                logger.debug(
                    f"No chunks mapped to segment {containing_segment_index}, "
                    f"searching all chunks directly"
                )
                chunk_ids = [
                    c.get("chunk_id", "") for c in doc_chunks if c.get("chunk_id", "")
                ]

        chunk_id_to_text: dict[str, str] = {}
        for chunk in doc_chunks:
            chunk_id = chunk.get("chunk_id", "")
            if chunk_id:
                chunk_id_to_text[chunk_id] = chunk.get("text", "")

        matching_chunk_ids: list[str] = []
        for chunk_id in chunk_ids:
            chunk_text = chunk_id_to_text.get(chunk_id, "")
            if not chunk_text:
                continue
            if quote in chunk_text:
                matching_chunk_ids.append(chunk_id)
            else:
                verification = self._verify_quote_in_segment(quote, chunk_text)
                if verification["found"]:
                    matching_chunk_ids.append(chunk_id)

        if not matching_chunk_ids:
            logger.debug(
                f"Quote found in segment but not in any mapped chunk: {quote[:50]}..."
            )

        return matching_chunk_ids

    def _locate_multi_hop_chunks(
        self,
        evidence_list: list[dict[str, Any]],
        segments: list[dict[str, Any]],
        segment_chunk_map: dict[int, list[str]],
        doc_chunks: list[dict[str, Any]],
    ) -> list[str]:
        """Locate chunk IDs for multi-hop questions from multiple evidence entries.

        For each evidence entry with a verified quote, calls
        _locate_chunks_by_quote to find the containing chunks, then
        returns the union of all unique chunk_ids.

        Args:
            evidence_list: List of evidence dictionaries, each containing
                a 'quote' key with verified quote text.
            segments: List of segment dictionaries with 'text', 'start_char',
                'end_char', and 'segment_index' keys.
            segment_chunk_map: Dictionary mapping segment_index to list of
                chunk_ids that overlap with that segment.
            doc_chunks: List of all chunk dictionaries from the document,
                each containing 'chunk_id' and 'text' keys.

        Returns:
            List of unique chunk_id strings that contain any of the quotes.
            Returns an empty list if no evidence entries have valid quotes
            or no chunks are found.
        """
        if not evidence_list:
            return []

        all_chunk_ids: set[str] = set()

        for evidence in evidence_list:
            quote = evidence.get("quote", "")
            if not quote:
                continue

            chunk_ids = self._locate_chunks_by_quote(
                quote, segments, segment_chunk_map, doc_chunks
            )
            all_chunk_ids.update(chunk_ids)

        result = sorted(list(all_chunk_ids))

        if result:
            logger.debug(
                f"Located {len(result)} unique chunks from "
                f"{len(evidence_list)} evidence entries"
            )
        else:
            logger.warning(f"No chunks found for {len(evidence_list)} evidence entries")

        return result

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
            This method is deprecated. Use :meth:`_locate_chunks_by_quote`
            instead for more accurate quote-based chunk location.

        Scans JSONL files in chunks_dir to find chunks belonging to the
        source document, then matches chunks against the answer text using
        keyword and substring overlap heuristics.

        Args:
            answer: The answer text to locate in chunks.
            source_path: Relative path of the source document (e.g.
                'research_reports/doc.md'), using forward slashes.
            meal_config: MealConfig object for resolving chunks directory
                via ArtifactCache. If provided, uses
                ``_resolve_chunks_dir()`` to find the actual chunks
                location. Falls back to config-based path otherwise.
            adjacent_tolerance: Number of adjacent chunks (by chunk_index)
                to include around each matched chunk. Defaults to 1.
            chunks_dir: Optional path to chunks directory. When provided,
                bypasses ArtifactCache resolution and uses this path
                directly.

        Returns:
            List of chunk_id strings for matched and adjacent chunks.
            Returns an empty list if no chunks match or the directory is
            not found.
        """
        warnings.warn(
            "_locate_answer_chunks is deprecated. "
            "Use _locate_chunks_by_quote for more accurate quote-based "
            "chunk location.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not answer or not source_path:
            return []

        if chunks_dir is not None:
            chunks_path = chunks_dir
        elif meal_config is not None:
            chunks_path = self._resolve_chunks_dir(meal_config)
            if not chunks_path:
                logger.warning(
                    f"Chunks directory not found via ArtifactCache for "
                    f"meal_config data_id={meal_config.data_id}"
                )
                return []
        else:
            resolved_chunks_dir = self.config.get("chunker", {}).get(
                "output_dir", "data/chunks"
            )
            chunks_path = Path(resolved_chunks_dir)

        if not chunks_path.exists():
            logger.warning(f"Chunks directory not found: {chunks_path}")
            return []

        normalized_source = source_path.replace("\\", "/")

        doc_chunks: list[dict[str, Any]] = []
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
                        if chunk_source == normalized_source:
                            doc_chunks.append(chunk)
            except Exception as e:
                logger.warning(f"Failed to read {jsonl_file}: {str(e)}")
                continue

        if not doc_chunks:
            logger.debug(f"No chunks found for source_path: {source_path}")
            return []

        doc_chunks.sort(key=lambda c: c.get("metadata", {}).get("chunk_index", 0))

        key_sentences = self._extract_key_sentences(answer)
        key_terms = self._extract_key_terms(answer)

        matched_indices: set = set()
        for i, chunk in enumerate(doc_chunks):
            chunk_text = chunk.get("text", "")
            if self._chunk_matches_answer(chunk_text, key_sentences, key_terms):
                matched_indices.add(i)

        if not matched_indices:
            logger.debug(f"No chunks matched for answer in source: {source_path}")
            return []

        expanded_indices: set = set()
        for idx in matched_indices:
            for offset in range(-adjacent_tolerance, adjacent_tolerance + 1):
                adj = idx + offset
                if 0 <= adj < len(doc_chunks):
                    expanded_indices.add(adj)

        expanded_indices.discard(-1)

        result = [doc_chunks[i].get("chunk_id", "") for i in sorted(expanded_indices)]
        result = [cid for cid in result if cid]

        return result

    def _extract_key_sentences(self, answer: str) -> list[str]:
        """Extract key sentences from an answer text.

        Splits the answer by sentence delimiters and filters for sentences
        that contain specific data such as numbers, proper nouns, or
        domain-specific terms.

        Args:
            answer: The answer text to extract sentences from.

        Returns:
            List of key sentences that likely contain answer-specific
            information.
        """
        sentences = re.split(r"[。！？\n]", answer)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 4]

        key_sentences = []
        for sent in sentences:
            has_number = bool(re.search(r"\d", sent))
            has_percentage = "%" in sent
            has_domain_terms = any(
                kw in sent
                for kw in [
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
                ]
            )
            if has_number or has_percentage or has_domain_terms:
                key_sentences.append(sent)

        if not key_sentences:
            key_sentences = [s for s in sentences if len(s) >= 6][:5]

        return key_sentences

    def _extract_key_terms(self, answer: str) -> list[str]:
        """Extract key terms from an answer text for chunk matching.

        Identifies meaningful terms including numbers with units, proper
        nouns, and domain-specific keywords.

        Args:
            answer: The answer text to extract terms from.

        Returns:
            List of key term strings.
        """
        terms: list[str] = []

        number_patterns = re.findall(r"\d+\.?\d*[万亿千百%％]?", answer)
        terms.extend(number_patterns)

        proper_nouns = re.findall(
            r"[\u4e00-\u9fff]{2,8}(?:股份|集团|公司|行业|市场|技术|产品|业务|报告|年度)",
            answer,
        )
        terms.extend(proper_nouns)

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
            "ROE",
            "ROA",
        ]
        for kw in domain_keywords:
            if kw in answer:
                terms.append(kw)

        return list(set(terms))

    def _chunk_matches_answer(
        self,
        chunk_text: str,
        key_sentences: list[str],
        key_terms: list[str],
        term_threshold: int = 3,
        overlap_threshold: float = 0.7,
    ) -> bool:
        """Check if a chunk text contains information relevant to the answer.

        A chunk is considered relevant if either:
        - It contains at least ``term_threshold`` key terms from the answer, OR
        - A key sentence from the answer has > ``overlap_threshold`` character
          overlap with the chunk text.

        Args:
            chunk_text: The text content of the chunk.
            key_sentences: Key sentences extracted from the answer.
            key_terms: Key terms extracted from the answer.
            term_threshold: Minimum number of key terms that must appear in
                the chunk for a match. Defaults to 3.
            overlap_threshold: Minimum character overlap ratio for a key
                sentence to be considered matching. Defaults to 0.7.

        Returns:
            True if the chunk is considered relevant to the answer.
        """
        if not key_terms and not key_sentences:
            return False

        matched_terms = sum(1 for term in key_terms if term in chunk_text)
        if matched_terms >= term_threshold:
            return True

        for sentence in key_sentences:
            if len(sentence) == 0:
                continue
            overlap_chars = 0
            window_size = min(len(sentence), len(chunk_text))
            for start in range(0, len(chunk_text) - window_size + 1):
                substring = chunk_text[start : start + len(sentence)]
                common = sum(
                    1 for a, b in zip(sentence, substring, strict=False) if a == b
                )
                ratio = common / len(sentence)
                if ratio > overlap_chars:
                    overlap_chars = ratio
            if overlap_chars > overlap_threshold:
                return True

        return False

    def _verify_quote_in_segment(self, quote: str, segment_text: str) -> dict[str, Any]:
        """Verify if a quote exists in a segment text.

        First attempts exact match, then falls back to fuzzy matching if
        exact match fails.

        Args:
            quote: The quote text to verify.
            segment_text: The segment text to search within.

        Returns:
            Dictionary with keys:
                - found: bool indicating if quote was found
                - position: int or None, the character position of the match
                - match_type: str, one of "exact", "fuzzy", or None
        """
        if not quote or not segment_text:
            return {"found": False, "position": None, "match_type": None}

        pos = segment_text.find(quote)
        if pos != -1:
            return {"found": True, "position": pos, "match_type": "exact"}

        fuzzy_result = self._fuzzy_match_quote(
            quote, segment_text, self.quote_fuzzy_match_threshold
        )
        if fuzzy_result["found"]:
            return {
                "found": True,
                "position": fuzzy_result["position"],
                "match_type": "fuzzy",
            }

        return {"found": False, "position": None, "match_type": None}

    def _fuzzy_match_quote(
        self, quote: str, segment_text: str, threshold: float = 0.85
    ) -> dict[str, Any]:
        """Perform fuzzy matching of a quote within segment text.

        Uses difflib.SequenceMatcher for similarity calculation. Handles
        minor differences such as whitespace variations and punctuation
        differences.

        Args:
            quote: The quote text to match.
            segment_text: The segment text to search within.
            threshold: Minimum similarity ratio for a match. Defaults to 0.85.

        Returns:
            Dictionary with keys:
                - found: bool indicating if a match was found
                - position: int or None, the starting character position
                - similarity: float, the similarity ratio of the best match
        """
        if not quote or not segment_text:
            return {"found": False, "position": None, "similarity": 0.0}

        quote_len = len(quote)
        if quote_len == 0:
            return {"found": False, "position": None, "similarity": 0.0}

        best_similarity = 0.0
        best_position = None

        normalized_quote = quote.replace("\n", " ").replace("\t", " ")
        normalized_quote = " ".join(normalized_quote.split())

        step = max(1, quote_len // 10)

        for start in range(0, len(segment_text) - quote_len + 1, step):
            substring = segment_text[start : start + quote_len]
            normalized_substring = substring.replace("\n", " ").replace("\t", " ")
            normalized_substring = " ".join(normalized_substring.split())

            matcher = difflib.SequenceMatcher(
                None, normalized_quote, normalized_substring
            )
            similarity = matcher.ratio()

            if similarity > best_similarity:
                best_similarity = similarity
                best_position = start

            if similarity >= threshold:
                for fine_start in range(
                    max(0, start - step),
                    min(len(segment_text) - quote_len + 1, start + step),
                ):
                    fine_substring = segment_text[fine_start : fine_start + quote_len]
                    fine_normalized = fine_substring.replace("\n", " ").replace(
                        "\t", " "
                    )
                    fine_normalized = " ".join(fine_normalized.split())

                    fine_matcher = difflib.SequenceMatcher(
                        None, normalized_quote, fine_normalized
                    )
                    fine_similarity = fine_matcher.ratio()

                    if fine_similarity > best_similarity:
                        best_similarity = fine_similarity
                        best_position = fine_start

        if best_similarity >= threshold:
            return {
                "found": True,
                "position": best_position,
                "similarity": best_similarity,
            }

        return {"found": False, "position": None, "similarity": best_similarity}

    def _validate_evidence(
        self,
        evidence_list: list[dict[str, Any]],
        segments: list[dict[str, Any]],
        question_type: str = "unknown",
    ) -> dict[str, Any]:
        """Validate evidence entries against document segments.

        For each evidence entry, verifies that the segment_index is valid
        and that the quote exists in the specified segment. Records
        verification results and detects potential hallucinations.

        Args:
            evidence_list: List of evidence dictionaries, each containing
                'segment_index' and 'quote' keys.
            segments: List of segment dictionaries, each containing 'text'
                and 'segment_index' keys.
            question_type: Type of question for logging context. Defaults
                to "unknown".

        Returns:
            Dictionary with keys:
                - valid: bool indicating if all evidence is valid
                - verified_evidence: list of evidence dicts with added
                    'verified' field
                - invalid_quotes: list of dicts with 'quote' and 'reason'
                    for invalid entries
        """
        if not evidence_list:
            return {
                "valid": True,
                "verified_evidence": [],
                "invalid_quotes": [],
            }

        segment_map = {
            seg.get("segment_index", i): seg for i, seg in enumerate(segments)
        }

        verified_evidence: list[dict[str, Any]] = []
        invalid_quotes: list[dict[str, str]] = []

        for evidence in evidence_list:
            segment_index = evidence.get("segment_index")
            quote = evidence.get("quote", "")

            if segment_index is None:
                verified_evidence.append({**evidence, "verified": False})
                invalid_quotes.append(
                    {
                        "quote": quote[:50] + "..." if len(quote) > 50 else quote,
                        "reason": "Missing segment_index",
                    }
                )
                continue

            if segment_index not in segment_map:
                verified_evidence.append({**evidence, "verified": False})
                invalid_quotes.append(
                    {
                        "quote": quote[:50] + "..." if len(quote) > 50 else quote,
                        "reason": f"Invalid segment_index: {segment_index}",
                    }
                )
                continue

            segment = segment_map[segment_index]
            segment_text = segment.get("text", "")

            verification = self._verify_quote_in_segment(quote, segment_text)

            if verification["found"]:
                verified_evidence.append(
                    {
                        **evidence,
                        "verified": True,
                        "match_type": verification["match_type"],
                        "position": verification["position"],
                    }
                )
            else:
                verified_evidence.append({**evidence, "verified": False})
                truncated_quote = quote[:50] + "..." if len(quote) > 50 else quote
                invalid_quotes.append(
                    {
                        "quote": truncated_quote,
                        "reason": "Quote not found in segment",
                    }
                )

                logger.warning(
                    f"Potential hallucination detected: quote '{truncated_quote}' "
                    f"not found in segment {segment_index}. "
                    f"Question type: {question_type}"
                )

        all_valid = len(invalid_quotes) == 0

        return {
            "valid": all_valid,
            "verified_evidence": verified_evidence,
            "invalid_quotes": invalid_quotes,
        }
