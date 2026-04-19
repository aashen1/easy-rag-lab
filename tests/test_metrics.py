import math

import pytest
from unittest.mock import MagicMock, patch

from eval.metrics import (
    calculate_answer_relevancy,
    calculate_faithfulness,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    normalize_source,
    _create_llm_client,
    _extract_statements,
    _parse_relevancy_response,
    _verify_statements,
)


@pytest.mark.unit
class TestNormalizeSource:

    def test_md_path_with_directory(self):
        assert normalize_source("annual_report/贵州茅台2023年年度报告.md") == "贵州茅台2023年年度报告"

    def test_pdf_filename(self):
        assert normalize_source("贵州茅台2023年年度报告.pdf") == "贵州茅台2023年年度报告"

    def test_plain_name_no_extension(self):
        assert normalize_source("贵州茅台2023年年度报告") == "贵州茅台2023年年度报告"

    def test_nested_path(self):
        assert normalize_source("a/b/c/report.md") == "report"

    def test_dot_in_stem(self):
        assert normalize_source("贵州茅台2023年年度报告_英文版_.pdf") == "贵州茅台2023年年度报告_英文版_"

    def test_both_formats_produce_same_stem(self):
        md_result = normalize_source("annual_report/贵州茅台2023年年度报告.md")
        pdf_result = normalize_source("贵州茅台2023年年度报告.pdf")
        assert md_result == pdf_result


@pytest.mark.unit
class TestCalculateHitRateStandard:
    """Tests for industry standard Hit Rate@k calculation."""

    def test_hit_at_first_position(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 1.0

    def test_hit_at_kth_position(self):
        retrieved = ["doc4", "doc5", "doc1"]
        expected = ["doc1"]
        assert calculate_hit_rate(retrieved, expected, k=3, mode="standard") == 1.0

    def test_hit_beyond_k(self):
        retrieved = ["doc4", "doc5", "doc6", "doc1"]
        expected = ["doc1"]
        assert calculate_hit_rate(retrieved, expected, k=3, mode="standard") == 0.0

    def test_no_hit(self):
        retrieved = ["doc4", "doc5", "doc6"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 0.0

    def test_empty_expected(self):
        retrieved = ["doc1", "doc2"]
        expected = []
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 0.0

    def test_empty_retrieved(self):
        retrieved = []
        expected = ["doc1", "doc2"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 0.0

    def test_multiple_expected_one_hit(self):
        retrieved = ["doc1", "doc4", "doc5"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 1.0

    def test_k_smaller_than_retrieved(self):
        retrieved = ["doc4", "doc5", "doc1", "doc2", "doc3"]
        expected = ["doc1"]
        assert calculate_hit_rate(retrieved, expected, k=2, mode="standard") == 0.0
        assert calculate_hit_rate(retrieved, expected, k=3, mode="standard") == 1.0

    def test_cross_format_hit(self):
        retrieved = ["annual_report/贵州茅台2023年年度报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 1.0

    def test_cross_format_no_hit(self):
        retrieved = ["annual_report/其他报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 0.0

    def test_default_mode_is_standard(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1"]
        assert calculate_hit_rate(retrieved, expected) == 1.0

    def test_default_k_is_5(self):
        retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5", "doc6"]
        expected = ["doc6"]
        assert calculate_hit_rate(retrieved, expected, mode="standard") == 0.0


@pytest.mark.unit
class TestCalculateHitRateRecall:
    """Tests for legacy recall-based calculation (backward compatibility)."""

    def test_full_hit(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected, mode="recall") == 1.0

    def test_partial_hit(self):
        retrieved = ["doc1", "doc2", "doc4"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected, mode="recall") == pytest.approx(2 / 3)

    def test_no_hit(self):
        retrieved = ["doc4", "doc5"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected, mode="recall") == 0.0

    def test_empty_expected(self):
        retrieved = ["doc1", "doc2"]
        expected = []
        assert calculate_hit_rate(retrieved, expected, mode="recall") == 0.0

    def test_empty_retrieved(self):
        retrieved = []
        expected = ["doc1", "doc2"]
        assert calculate_hit_rate(retrieved, expected, mode="recall") == 0.0

    def test_duplicate_sources(self):
        retrieved = ["doc1", "doc1", "doc2", "doc2"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected, mode="recall") == pytest.approx(2 / 3)

    def test_cross_format_hit(self):
        retrieved = ["annual_report/贵州茅台2023年年度报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected, mode="recall") == 1.0

    def test_cross_format_no_hit(self):
        retrieved = ["annual_report/其他报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected, mode="recall") == 0.0


@pytest.mark.unit
class TestCalculateHitRateValidation:
    """Tests for input validation and error handling."""

    def test_invalid_mode_raises_error(self):
        retrieved = ["doc1"]
        expected = ["doc1"]
        with pytest.raises(ValueError, match="mode must be 'standard' or 'recall'"):
            calculate_hit_rate(retrieved, expected, mode="invalid")


@pytest.mark.unit
class TestCalculateMRR:

    def test_first_position_hit(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1"]
        assert calculate_mrr(retrieved, expected) == 1.0

    def test_last_position_hit(self):
        retrieved = ["doc2", "doc3", "doc1"]
        expected = ["doc1"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 3)

    def test_no_hit(self):
        retrieved = ["doc4", "doc5"]
        expected = ["doc1", "doc2"]
        assert calculate_mrr(retrieved, expected) == 0.0

    def test_empty_expected(self):
        retrieved = ["doc1", "doc2"]
        expected = []
        assert calculate_mrr(retrieved, expected) == 0.0

    def test_multiple_expected(self):
        retrieved = ["doc3", "doc1", "doc2"]
        expected = ["doc1", "doc2"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 2)

    def test_cross_format_mrr(self):
        retrieved = ["other.md", "annual_report/贵州茅台2023年年度报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 2)

    def test_duplicate_in_retrieved(self):
        retrieved = ["doc1", "doc1", "doc2"]
        expected = ["doc1"]
        assert calculate_mrr(retrieved, expected) == 1.0

    def test_empty_retrieved(self):
        retrieved = []
        expected = ["doc1", "doc2"]
        assert calculate_mrr(retrieved, expected) == 0.0

    def test_second_position_hit(self):
        retrieved = ["doc3", "doc1", "doc2"]
        expected = ["doc1"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 2)

    def test_fourth_position_hit(self):
        retrieved = ["doc4", "doc5", "doc6", "doc1", "doc2"]
        expected = ["doc1"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 4)

    def test_duplicate_in_expected(self):
        retrieved = ["doc2", "doc1", "doc3"]
        expected = ["doc1", "doc1", "doc1"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 2)

    def test_all_expected_in_retrieved_returns_first(self):
        retrieved = ["doc3", "doc1", "doc2"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 1)

    def test_large_list_performance(self):
        retrieved = [f"doc{i}" for i in range(1000)]
        retrieved[500] = "target"
        expected = ["target"]
        assert calculate_mrr(retrieved, expected) == pytest.approx(1 / 501)

    def test_special_characters_in_filename(self):
        retrieved = ["path/to/report_(2023)_final.md"]
        expected = ["report_(2023)_final.pdf"]
        assert calculate_mrr(retrieved, expected) == 1.0

    def test_unicode_filename(self):
        retrieved = ["reports/贵州茅台_2023年报.md"]
        expected = ["贵州茅台_2023年报.pdf"]
        assert calculate_mrr(retrieved, expected) == 1.0

    def test_both_empty(self):
        retrieved = []
        expected = []
        assert calculate_mrr(retrieved, expected) == 0.0


@pytest.mark.unit
class TestCalculateNDCG:

    def test_perfect_ranking(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_ndcg(retrieved, expected) == 1.0

    def test_reverse_ranking(self):
        retrieved = ["doc4", "doc5", "doc1"]
        expected = ["doc1", "doc2", "doc3"]
        score = calculate_ndcg(retrieved, expected)
        assert score < 1.0
        assert score > 0.0

    def test_partial_ranking(self):
        retrieved = ["doc1", "doc4", "doc2"]
        expected = ["doc1", "doc2", "doc3"]
        score = calculate_ndcg(retrieved, expected)
        dcg = (2**1 - 1) / math.log2(2) + (2**1 - 1) / math.log2(4)
        ideal_dcg = (2**1 - 1) / math.log2(2) + (2**1 - 1) / math.log2(3) + (2**1 - 1) / math.log2(4)
        assert score == pytest.approx(dcg / ideal_dcg)

    def test_k_truncation(self):
        retrieved = ["doc4", "doc5", "doc1", "doc2", "doc3"]
        expected = ["doc1", "doc2", "doc3"]
        score_k2 = calculate_ndcg(retrieved, expected, k=2)
        assert score_k2 == 0.0
        score_k5 = calculate_ndcg(retrieved, expected, k=5)
        assert score_k5 > 0.0

    def test_empty_expected(self):
        retrieved = ["doc1", "doc2"]
        expected = []
        assert calculate_ndcg(retrieved, expected) == 0.0

    def test_single_document_ideal(self):
        retrieved = ["doc2", "doc1", "doc3"]
        expected = ["doc1"]
        score = calculate_ndcg(retrieved, expected)
        dcg = (2**1 - 1) / math.log2(3)
        ideal_dcg = (2**1 - 1) / math.log2(2)
        assert score == pytest.approx(dcg / ideal_dcg)

    def test_cross_format_ndcg(self):
        retrieved = ["annual_report/贵州茅台2023年年度报告.md", "other.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        score = calculate_ndcg(retrieved, expected)
        assert score == 1.0


@pytest.mark.unit
class TestCalculateNDCGDeduplication:
    """Tests for NDCG deduplication fix - ensures NDCG never exceeds 1.0."""

    def test_duplicate_documents_should_not_exceed_one(self):
        retrieved = ["doc1", "doc1", "doc1", "doc1", "doc1"]
        expected = ["doc1"]
        score = calculate_ndcg(retrieved, expected, k=5)
        assert score == 1.0

    def test_duplicate_with_mixed_results(self):
        retrieved = ["doc1", "doc1", "doc2", "doc1", "doc2"]
        expected = ["doc1", "doc2"]
        score = calculate_ndcg(retrieved, expected, k=5)
        assert score == 1.0
        assert score <= 1.0

    def test_duplicate_first_position_optimal(self):
        retrieved = ["doc1", "doc1", "doc1"]
        expected = ["doc1"]
        score = calculate_ndcg(retrieved, expected, k=5)
        assert score == 1.0

    def test_duplicate_later_position(self):
        retrieved = ["doc3", "doc1", "doc1", "doc1"]
        expected = ["doc1"]
        score = calculate_ndcg(retrieved, expected, k=5)
        dcg = (2**1 - 1) / math.log2(3)
        ideal_dcg = (2**1 - 1) / math.log2(2)
        assert score == pytest.approx(dcg / ideal_dcg)
        assert score <= 1.0

    def test_all_duplicates_no_match(self):
        retrieved = ["doc3", "doc3", "doc3", "doc3"]
        expected = ["doc1", "doc2"]
        score = calculate_ndcg(retrieved, expected, k=5)
        assert score == 0.0

    def test_partial_duplicates_with_match(self):
        retrieved = ["doc1", "doc1", "doc3", "doc3"]
        expected = ["doc1", "doc2"]
        score = calculate_ndcg(retrieved, expected, k=5)
        dcg = (2**1 - 1) / math.log2(2)
        ideal_dcg = (2**1 - 1) / math.log2(2) + (2**1 - 1) / math.log2(3)
        assert score == pytest.approx(dcg / ideal_dcg)
        assert score <= 1.0

    def test_multilevel_relevance_with_duplicates(self):
        retrieved = ["doc1", "doc1", "doc2", "doc2"]
        expected = ["doc1", "doc2"]
        rel_scores = {"doc1": 3, "doc2": 1}
        score = calculate_ndcg(retrieved, expected, k=5, relevance_scores=rel_scores)
        assert score == 1.0
        assert score <= 1.0

    def test_large_k_with_duplicates(self):
        retrieved = ["doc1"] * 100
        expected = ["doc1"]
        score = calculate_ndcg(retrieved, expected, k=100)
        assert score == 1.0
        assert score <= 1.0

    def test_boundary_check_never_exceeds_one(self):
        for num_duplicates in [1, 5, 10, 100]:
            retrieved = ["doc1"] * num_duplicates
            expected = ["doc1"]
            score = calculate_ndcg(retrieved, expected, k=num_duplicates)
            assert score <= 1.0, f"NDCG exceeded 1.0 with {num_duplicates} duplicates"


@pytest.mark.unit
class TestCalculateNDCGMultilevel:

    def test_binary_relevance_backward_compatibility(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1", "doc2", "doc3"]
        score = calculate_ndcg(retrieved, expected)
        assert score == 1.0

    def test_multilevel_perfect_ranking(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1", "doc2", "doc3"]
        rel_scores = {"doc1": 3, "doc2": 2, "doc3": 1}
        score = calculate_ndcg(retrieved, expected, relevance_scores=rel_scores)
        assert score == 1.0

    def test_multilevel_imperfect_ranking(self):
        retrieved = ["doc3", "doc2", "doc1"]
        expected = ["doc1", "doc2", "doc3"]
        rel_scores = {"doc1": 3, "doc2": 2, "doc3": 1}
        score = calculate_ndcg(retrieved, expected, relevance_scores=rel_scores)
        assert score < 1.0
        assert score > 0.0

    def test_multilevel_partial_match(self):
        retrieved = ["doc1", "doc4", "doc2"]
        expected = ["doc1", "doc2", "doc3"]
        rel_scores = {"doc1": 3, "doc2": 2, "doc3": 1}
        score = calculate_ndcg(retrieved, expected, relevance_scores=rel_scores)
        dcg = (2**3 - 1) / math.log2(2) + (2**2 - 1) / math.log2(4)
        ideal_dcg = (2**3 - 1) / math.log2(2) + (2**2 - 1) / math.log2(3) + (2**1 - 1) / math.log2(4)
        assert score == pytest.approx(dcg / ideal_dcg)

    def test_multilevel_zero_relevance(self):
        retrieved = ["doc1", "doc2"]
        expected = ["doc1", "doc2"]
        rel_scores = {"doc1": 0, "doc2": 0}
        score = calculate_ndcg(retrieved, expected, relevance_scores=rel_scores)
        assert score == 0.0

    def test_multilevel_mixed_relevance(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1", "doc2", "doc3"]
        rel_scores = {"doc1": 3, "doc2": 0, "doc3": 1}
        score = calculate_ndcg(retrieved, expected, relevance_scores=rel_scores)
        dcg = (2**3 - 1) / math.log2(2) + 0 + (2**1 - 1) / math.log2(4)
        ideal_dcg = (2**3 - 1) / math.log2(2) + (2**1 - 1) / math.log2(3) + 0
        assert score == pytest.approx(dcg / ideal_dcg)

    def test_multilevel_with_k_truncation(self):
        retrieved = ["doc3", "doc2", "doc1", "doc4"]
        expected = ["doc1", "doc2", "doc3"]
        rel_scores = {"doc1": 3, "doc2": 2, "doc3": 1}
        score_k2 = calculate_ndcg(retrieved, expected, k=2, relevance_scores=rel_scores)
        dcg_k2 = (2**1 - 1) / math.log2(2) + (2**2 - 1) / math.log2(3)
        ideal_dcg_k2 = (2**3 - 1) / math.log2(2) + (2**2 - 1) / math.log2(3)
        assert score_k2 == pytest.approx(dcg_k2 / ideal_dcg_k2)

    def test_multilevel_cross_format(self):
        retrieved = ["annual_report/doc1.md", "other.md"]
        expected = ["doc1.pdf"]
        rel_scores = {"doc1": 3}
        score = calculate_ndcg(retrieved, expected, relevance_scores=rel_scores)
        assert score == 1.0

    def test_multilevel_missing_relevance_score(self):
        retrieved = ["doc1", "doc2"]
        expected = ["doc1", "doc2", "doc3"]
        rel_scores = {"doc1": 3}
        score = calculate_ndcg(retrieved, expected, relevance_scores=rel_scores)
        dcg = (2**3 - 1) / math.log2(2)
        ideal_dcg = (2**3 - 1) / math.log2(2)
        assert score == pytest.approx(dcg / ideal_dcg)

    def test_multilevel_high_vs_low_relevance(self):
        retrieved_high_first = ["doc1", "doc2"]
        retrieved_low_first = ["doc2", "doc1"]
        expected = ["doc1", "doc2"]
        rel_scores = {"doc1": 3, "doc2": 1}

        score_high_first = calculate_ndcg(
            retrieved_high_first, expected, relevance_scores=rel_scores
        )
        score_low_first = calculate_ndcg(
            retrieved_low_first, expected, relevance_scores=rel_scores
        )

        assert score_high_first > score_low_first


@pytest.mark.unit
class TestParseRelevancyResponse:
    """Tests for _parse_relevancy_response function."""

    def test_parse_valid_json(self):
        response_text = '{"direct_relevance": 5, "information_sufficiency": 4, "conciseness": 4, "overall_score": 0.85}'
        result = _parse_relevancy_response(response_text)
        assert result["direct_relevance"] == 5
        assert result["information_sufficiency"] == 4
        assert result["conciseness"] == 4
        assert result["overall_score"] == 0.85

    def test_parse_json_with_surrounding_text(self):
        response_text = '这是一些额外的文本 {"direct_relevance": 3, "overall_score": 0.5} 更多文本'
        result = _parse_relevancy_response(response_text)
        assert result["direct_relevance"] == 3
        assert result["overall_score"] == 0.5

    def test_parse_json_with_newlines(self):
        response_text = '''{
            "direct_relevance": 4,
            "information_sufficiency": 4,
            "conciseness": 3,
            "overall_score": 0.7
        }'''
        result = _parse_relevancy_response(response_text)
        assert result["direct_relevance"] == 4
        assert result["overall_score"] == 0.7

    def test_parse_invalid_json_raises_error(self):
        response_text = "这不是有效的JSON"
        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            _parse_relevancy_response(response_text)

    def test_parse_partial_json(self):
        response_text = '{"direct_relevance": 5, "information_sufficiency": 5'
        with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
            _parse_relevancy_response(response_text)


@pytest.mark.unit
class TestCalculateAnswerRelevancy:
    """Tests for calculate_answer_relevancy function."""

    def test_empty_question_raises_error(self):
        with pytest.raises(ValueError, match="Question must be a non-empty string"):
            calculate_answer_relevancy(
                question="",
                answer="这是一个回答",
                api_key="test-key"
            )

    def test_empty_answer_raises_error(self):
        with pytest.raises(ValueError, match="Answer must be a non-empty string"):
            calculate_answer_relevancy(
                question="这是一个问题",
                answer="",
                api_key="test-key"
            )

    def test_none_question_raises_error(self):
        with pytest.raises(ValueError, match="Question must be a non-empty string"):
            calculate_answer_relevancy(
                question=None,
                answer="这是一个回答",
                api_key="test-key"
            )

    def test_none_answer_raises_error(self):
        with pytest.raises(ValueError, match="Answer must be a non-empty string"):
            calculate_answer_relevancy(
                question="这是一个问题",
                answer=None,
                api_key="test-key"
            )

    @patch("eval.metrics.Anthropic")
    def test_successful_relevancy_calculation(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"direct_relevance": 5, "information_sufficiency": 5, "conciseness": 5, "overall_score": 1.0}'
        mock_client.messages.create.return_value = mock_message

        score = calculate_answer_relevancy(
            question="贵州茅台2023年营收是多少？",
            answer="贵州茅台2023年实现营业收入1505.60亿元，同比增长18.04%。",
            api_key="test-api-key"
        )

        assert score == 1.0
        mock_client.messages.create.assert_called_once()

    @patch("eval.metrics.Anthropic")
    def test_low_relevancy_calculation(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"direct_relevance": 1, "information_sufficiency": 1, "conciseness": 2, "overall_score": 0.1}'
        mock_client.messages.create.return_value = mock_message

        score = calculate_answer_relevancy(
            question="贵州茅台2023年营收是多少？",
            answer="今天天气很好，适合出去玩。",
            api_key="test-api-key"
        )

        assert score == 0.1

    @patch("eval.metrics.Anthropic")
    def test_missing_overall_score_calculates_from_dimensions(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"direct_relevance": 4, "information_sufficiency": 4, "conciseness": 3}'
        mock_client.messages.create.return_value = mock_message

        score = calculate_answer_relevancy(
            question="贵州茅台2023年营收是多少？",
            answer="贵州茅台2023年营收约1500亿元左右。",
            api_key="test-api-key"
        )

        expected_score = (4 + 4 + 3) / 15.0
        assert score == pytest.approx(expected_score)

    @patch("eval.metrics.Anthropic")
    def test_score_clamped_to_range(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"direct_relevance": 5, "information_sufficiency": 5, "conciseness": 5, "overall_score": 1.5}'
        mock_client.messages.create.return_value = mock_message

        score = calculate_answer_relevancy(
            question="问题",
            answer="回答",
            api_key="test-api-key"
        )

        assert score == 1.0

    @patch("eval.metrics.Anthropic")
    def test_negative_score_clamped_to_zero(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"direct_relevance": 1, "information_sufficiency": 1, "conciseness": 1, "overall_score": -0.5}'
        mock_client.messages.create.return_value = mock_message

        score = calculate_answer_relevancy(
            question="问题",
            answer="回答",
            api_key="test-api-key"
        )

        assert score == 0.0

    @patch("eval.metrics.Anthropic")
    def test_llm_api_error_raises_exception(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="Failed to calculate answer relevancy"):
            calculate_answer_relevancy(
                question="问题",
                answer="回答",
                api_key="test-api-key"
            )

    @patch("eval.metrics.Anthropic")
    def test_custom_model_parameters(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"direct_relevance": 5, "information_sufficiency": 5, "conciseness": 5, "overall_score": 1.0}'
        mock_client.messages.create.return_value = mock_message

        calculate_answer_relevancy(
            question="问题",
            answer="回答",
            api_key="test-api-key",
            base_url="https://custom.api.url/anthropic",
            model_name="custom-model",
            max_tokens=1024,
            temperature=0.5
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "custom-model"
        assert call_kwargs["max_tokens"] == 1024
        assert call_kwargs["temperature"] == 0.5


@pytest.mark.unit
class TestCreateLLMClient:
    """Tests for _create_llm_client function."""

    @patch("eval.metrics.Anthropic")
    def test_create_client_success(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        client = _create_llm_client(
            api_key="test-api-key",
            base_url="https://api.test.com/anthropic"
        )

        assert client == mock_client
        mock_anthropic.assert_called_once()

    @patch("eval.metrics.Anthropic")
    def test_create_client_with_custom_url(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        _create_llm_client(
            api_key="test-key",
            base_url="https://custom.url/api"
        )

        call_kwargs = mock_anthropic.call_args[1]
        assert call_kwargs["base_url"] == "https://custom.url/api"


@pytest.mark.unit
class TestExtractStatements:
    """Tests for _extract_statements function."""

    def test_extract_statements_success(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"statements": ["陈述1", "陈述2", "陈述3"]}'
        mock_client.messages.create.return_value = mock_message

        statements = _extract_statements(
            client=mock_client,
            answer="这是一个测试回答",
            model_name="test-model"
        )

        assert len(statements) == 3
        assert statements[0] == "陈述1"
        assert statements[1] == "陈述2"
        assert statements[2] == "陈述3"

    def test_extract_statements_empty_response(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"statements": []}'
        mock_client.messages.create.return_value = mock_message

        statements = _extract_statements(
            client=mock_client,
            answer="这是一个测试回答",
            model_name="test-model"
        )

        assert len(statements) == 0

    def test_extract_statements_json_with_surrounding_text(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '一些额外文本 {"statements": ["陈述A"]} 更多文本'
        mock_client.messages.create.return_value = mock_message

        statements = _extract_statements(
            client=mock_client,
            answer="测试回答",
            model_name="test-model"
        )

        assert len(statements) == 1
        assert statements[0] == "陈述A"

    def test_extract_statements_invalid_json_returns_empty(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = "这不是有效的JSON"
        mock_client.messages.create.return_value = mock_message

        statements = _extract_statements(
            client=mock_client,
            answer="测试回答",
            model_name="test-model"
        )

        assert statements == []

    def test_extract_statements_llm_error_raises_exception(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="Failed to extract statements"):
            _extract_statements(
                client=mock_client,
                answer="测试回答",
                model_name="test-model"
            )


@pytest.mark.unit
class TestVerifyStatements:
    """Tests for _verify_statements function."""

    def test_verify_statements_all_supported(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '''{
            "verdict": [
                {"statement": "陈述1", "verdict": 1},
                {"statement": "陈述2", "verdict": 1}
            ]
        }'''
        mock_client.messages.create.return_value = mock_message

        verdicts = _verify_statements(
            client=mock_client,
            statements=["陈述1", "陈述2"],
            contexts=["上下文1", "上下文2"],
            model_name="test-model"
        )

        assert len(verdicts) == 2
        assert verdicts[0]["verdict"] == 1
        assert verdicts[1]["verdict"] == 1

    def test_verify_statements_partial_support(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '''{
            "verdict": [
                {"statement": "陈述1", "verdict": 1},
                {"statement": "陈述2", "verdict": 0}
            ]
        }'''
        mock_client.messages.create.return_value = mock_message

        verdicts = _verify_statements(
            client=mock_client,
            statements=["陈述1", "陈述2"],
            contexts=["上下文1"],
            model_name="test-model"
        )

        assert len(verdicts) == 2
        assert verdicts[0]["verdict"] == 1
        assert verdicts[1]["verdict"] == 0

    def test_verify_statements_none_supported(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '''{
            "verdict": [
                {"statement": "陈述1", "verdict": 0},
                {"statement": "陈述2", "verdict": 0}
            ]
        }'''
        mock_client.messages.create.return_value = mock_message

        verdicts = _verify_statements(
            client=mock_client,
            statements=["陈述1", "陈述2"],
            contexts=["无关上下文"],
            model_name="test-model"
        )

        assert len(verdicts) == 2
        assert all(v["verdict"] == 0 for v in verdicts)

    def test_verify_statements_invalid_json_returns_empty(self):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = "无效的JSON响应"
        mock_client.messages.create.return_value = mock_message

        verdicts = _verify_statements(
            client=mock_client,
            statements=["陈述1"],
            contexts=["上下文1"],
            model_name="test-model"
        )

        assert verdicts == []

    def test_verify_statements_llm_error_raises_exception(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="Failed to verify statements"):
            _verify_statements(
                client=mock_client,
                statements=["陈述1"],
                contexts=["上下文1"],
                model_name="test-model"
            )


@pytest.mark.unit
class TestCalculateFaithfulness:
    """Tests for calculate_faithfulness function."""

    def test_empty_answer_raises_error(self):
        with pytest.raises(ValueError, match="Answer must be a non-empty string"):
            calculate_faithfulness(
                answer="",
                contexts=["上下文"],
                api_key="test-key"
            )

    def test_none_answer_raises_error(self):
        with pytest.raises(ValueError, match="Answer must be a non-empty string"):
            calculate_faithfulness(
                answer=None,
                contexts=["上下文"],
                api_key="test-key"
            )

    def test_empty_contexts_returns_zero(self):
        with patch("eval.metrics._create_llm_client") as mock_create_client:
            score = calculate_faithfulness(
                answer="这是一个回答",
                contexts=[],
                api_key="test-key"
            )
            assert score == 0.0

    def test_whitespace_only_answer_returns_zero(self):
        with patch("eval.metrics._create_llm_client") as mock_create_client:
            score = calculate_faithfulness(
                answer="   \n\t  ",
                contexts=["上下文"],
                api_key="test-key"
            )
            assert score == 0.0

    @patch("eval.metrics._create_llm_client")
    @patch("eval.metrics._extract_statements")
    @patch("eval.metrics._verify_statements")
    def test_full_faithfulness_score(
        self, mock_verify, mock_extract, mock_create_client
    ):
        mock_create_client.return_value = MagicMock()
        mock_extract.return_value = ["陈述1", "陈述2", "陈述3"]
        mock_verify.return_value = [
            {"statement": "陈述1", "verdict": 1},
            {"statement": "陈述2", "verdict": 1},
            {"statement": "陈述3", "verdict": 1},
        ]

        score = calculate_faithfulness(
            answer="贵州茅台2023年营业收入为1505.60亿元，同比增长18.04%。",
            contexts=["贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元，同比增长18.04%。"],
            api_key="test-api-key"
        )

        assert score == 1.0

    @patch("eval.metrics._create_llm_client")
    @patch("eval.metrics._extract_statements")
    @patch("eval.metrics._verify_statements")
    def test_partial_faithfulness_score(
        self, mock_verify, mock_extract, mock_create_client
    ):
        mock_create_client.return_value = MagicMock()
        mock_extract.return_value = ["陈述1", "陈述2", "陈述3"]
        mock_verify.return_value = [
            {"statement": "陈述1", "verdict": 1},
            {"statement": "陈述2", "verdict": 0},
            {"statement": "陈述3", "verdict": 1},
        ]

        score = calculate_faithfulness(
            answer="回答包含部分幻觉内容。",
            contexts=["上下文信息"],
            api_key="test-api-key"
        )

        assert score == pytest.approx(2 / 3)

    @patch("eval.metrics._create_llm_client")
    @patch("eval.metrics._extract_statements")
    @patch("eval.metrics._verify_statements")
    def test_zero_faithfulness_score(
        self, mock_verify, mock_extract, mock_create_client
    ):
        mock_create_client.return_value = MagicMock()
        mock_extract.return_value = ["陈述1", "陈述2"]
        mock_verify.return_value = [
            {"statement": "陈述1", "verdict": 0},
            {"statement": "陈述2", "verdict": 0},
        ]

        score = calculate_faithfulness(
            answer="完全编造的回答内容。",
            contexts=["无关的上下文信息。"],
            api_key="test-api-key"
        )

        assert score == 0.0

    @patch("eval.metrics._create_llm_client")
    @patch("eval.metrics._extract_statements")
    def test_no_statements_extracted_returns_zero(
        self, mock_extract, mock_create_client
    ):
        mock_create_client.return_value = MagicMock()
        mock_extract.return_value = []

        score = calculate_faithfulness(
            answer="问候语",
            contexts=["上下文"],
            api_key="test-api-key"
        )

        assert score == 0.0

    @patch("eval.metrics._create_llm_client")
    @patch("eval.metrics._extract_statements")
    @patch("eval.metrics._verify_statements")
    def test_no_verdicts_returns_zero(
        self, mock_verify, mock_extract, mock_create_client
    ):
        mock_create_client.return_value = MagicMock()
        mock_extract.return_value = ["陈述1"]
        mock_verify.return_value = []

        score = calculate_faithfulness(
            answer="回答",
            contexts=["上下文"],
            api_key="test-api-key"
        )

        assert score == 0.0

    @patch("eval.metrics._create_llm_client")
    def test_llm_client_error_raises_exception(self, mock_create_client):
        mock_create_client.side_effect = Exception("Client creation failed")

        with pytest.raises(Exception, match="Failed to calculate faithfulness"):
            calculate_faithfulness(
                answer="回答",
                contexts=["上下文"],
                api_key="test-api-key"
            )

    @patch("eval.metrics._create_llm_client")
    @patch("eval.metrics._extract_statements")
    @patch("eval.metrics._verify_statements")
    def test_custom_parameters_passed_correctly(
        self, mock_verify, mock_extract, mock_create_client
    ):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_extract.return_value = ["陈述1"]
        mock_verify.return_value = [{"statement": "陈述1", "verdict": 1}]

        calculate_faithfulness(
            answer="回答",
            contexts=["上下文"],
            api_key="test-api-key",
            base_url="https://custom.api.url/anthropic",
            model_name="custom-model"
        )

        mock_create_client.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://custom.api.url/anthropic"
        )
        mock_extract.assert_called_once_with(
            mock_client, "回答", "custom-model"
        )

    @patch("eval.metrics._create_llm_client")
    @patch("eval.metrics._extract_statements")
    @patch("eval.metrics._verify_statements")
    def test_half_faithfulness_score(
        self, mock_verify, mock_extract, mock_create_client
    ):
        mock_create_client.return_value = MagicMock()
        mock_extract.return_value = ["陈述1", "陈述2"]
        mock_verify.return_value = [
            {"statement": "陈述1", "verdict": 1},
            {"statement": "陈述2", "verdict": 0},
        ]

        score = calculate_faithfulness(
            answer="回答",
            contexts=["上下文"],
            api_key="test-api-key"
        )

        assert score == 0.5
