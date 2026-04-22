import math
from unittest.mock import MagicMock, patch

import pytest

from eval.metrics import (
    _create_llm_client,
    _extract_statements,
    _parse_chunk_id,
    _parse_relevancy_response,
    _verify_statements,
    calculate_answer_relevancy,
    calculate_chunk_hit_rate,
    calculate_chunk_mrr,
    calculate_chunk_ndcg,
    calculate_dedup_hit_rate,
    calculate_dedup_mrr,
    calculate_dedup_ndcg,
    calculate_faithfulness,
    calculate_false_positive_rate,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    deduplicate_by_document,
    normalize_source,
    normalize_source_with_equivalence,
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

    def test_path_with_parent_include_parent(self):
        assert normalize_source("annual_reports/2025/贵州茅台.md", include_parent=True) == "2025/贵州茅台"

    def test_path_with_parent_exclude_parent(self):
        assert normalize_source("annual_reports/2025/贵州茅台.md", include_parent=False) == "贵州茅台"

    def test_no_parent_include_parent(self):
        assert normalize_source("贵州茅台.md", include_parent=True) == "贵州茅台"

    def test_current_dir_parent(self):
        assert normalize_source("./贵州茅台.md", include_parent=True) == "贵州茅台"

    def test_deeply_nested_path(self):
        assert normalize_source("a/b/c/report.md", include_parent=True) == "c/report"


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
        expected = ["annual_report/贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 1.0

    def test_cross_format_no_hit(self):
        retrieved = ["annual_report/其他报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected, k=5, mode="standard") == 0.0

    def test_different_dir_same_stem_no_hit(self):
        retrieved = ["annual_report/贵州茅台2023年年度报告.md"]
        expected = ["research/贵州茅台2023年年度报告.pdf"]
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
        expected = ["annual_report/贵州茅台2023年年度报告.pdf"]
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
        expected = ["annual_report/贵州茅台2023年年度报告.pdf"]
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
        expected = ["path/to/report_(2023)_final.pdf"]
        assert calculate_mrr(retrieved, expected) == 1.0

    def test_unicode_filename(self):
        retrieved = ["reports/贵州茅台_2023年报.md"]
        expected = ["reports/贵州茅台_2023年报.pdf"]
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
        expected = ["annual_report/贵州茅台2023年年度报告.pdf"]
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
        expected = ["annual_report/doc1.pdf"]
        rel_scores = {"annual_report/doc1": 3}
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

    @patch("eval.metrics.generation._create_llm_client")
    def test_successful_relevancy_calculation(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

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

    @patch("eval.metrics.generation._create_llm_client")
    def test_low_relevancy_calculation(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

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

    @patch("eval.metrics.generation._create_llm_client")
    def test_missing_overall_score_calculates_from_dimensions(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

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

    @patch("eval.metrics.generation._create_llm_client")
    def test_score_clamped_to_range(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

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

    @patch("eval.metrics.generation._create_llm_client")
    def test_negative_score_clamped_to_zero(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

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

    @patch("eval.metrics.generation._create_llm_client")
    def test_llm_api_error_raises_exception(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="Failed to calculate answer relevancy"):
            calculate_answer_relevancy(
                question="问题",
                answer="回答",
                api_key="test-api-key"
            )

    @patch("eval.metrics.generation._create_llm_client")
    def test_custom_model_parameters(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

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

    @patch("src.utils.create_llm_client")
    def test_create_client_success(self, mock_create_llm_client):
        mock_client = MagicMock()
        mock_create_llm_client.return_value = mock_client

        client = _create_llm_client(
            api_key="test-api-key",
            base_url="https://api.test.com/anthropic"
        )

        assert client == mock_client
        mock_create_llm_client.assert_called_once()

    @patch("src.utils.create_llm_client")
    def test_create_client_with_custom_url(self, mock_create_llm_client):
        mock_client = MagicMock()
        mock_create_llm_client.return_value = mock_client

        _create_llm_client(
            api_key="test-key",
            base_url="https://custom.url/api"
        )

        mock_create_llm_client.assert_called_once()
        call_kwargs = mock_create_llm_client.call_args[1]
        assert call_kwargs["llm_config"]["base_url"] == "https://custom.url/api"


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
        with patch("eval.metrics.generation._create_llm_client") as mock_create_client:
            score = calculate_faithfulness(
                answer="这是一个回答",
                contexts=[],
                api_key="test-key"
            )
            assert score == 0.0

    def test_whitespace_only_answer_returns_zero(self):
        with patch("eval.metrics.generation._create_llm_client") as mock_create_client:
            score = calculate_faithfulness(
                answer="   \n\t  ",
                contexts=["上下文"],
                api_key="test-key"
            )
            assert score == 0.0

    @patch("eval.metrics.generation._create_llm_client")
    @patch("eval.metrics.generation._extract_statements")
    @patch("eval.metrics.generation._verify_statements")
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

    @patch("eval.metrics.generation._create_llm_client")
    @patch("eval.metrics.generation._extract_statements")
    @patch("eval.metrics.generation._verify_statements")
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

    @patch("eval.metrics.generation._create_llm_client")
    @patch("eval.metrics.generation._extract_statements")
    @patch("eval.metrics.generation._verify_statements")
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

    @patch("eval.metrics.generation._create_llm_client")
    @patch("eval.metrics.generation._extract_statements")
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

    @patch("eval.metrics.generation._create_llm_client")
    @patch("eval.metrics.generation._extract_statements")
    @patch("eval.metrics.generation._verify_statements")
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

    @patch("eval.metrics.generation._create_llm_client")
    def test_llm_client_error_raises_exception(self, mock_create_client):
        mock_create_client.side_effect = Exception("Client creation failed")

        with pytest.raises(Exception, match="Failed to calculate faithfulness"):
            calculate_faithfulness(
                answer="回答",
                contexts=["上下文"],
                api_key="test-api-key"
            )

    @patch("eval.metrics.generation._create_llm_client")
    @patch("eval.metrics.generation._extract_statements")
    @patch("eval.metrics.generation._verify_statements")
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
            mock_client, "回答", "custom-model",
            max_tokens=1024, temperature=0.0,
        )

    @patch("eval.metrics.generation._create_llm_client")
    @patch("eval.metrics.generation._extract_statements")
    @patch("eval.metrics.generation._verify_statements")
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


@pytest.mark.unit
class TestSplitIntoSentences:
    """Tests for _split_into_sentences function."""

    def test_chinese_sentences(self):
        from eval.metrics import _split_into_sentences
        text = "这是第一句。这是第二句！这是第三句？"
        sentences = _split_into_sentences(text)
        assert len(sentences) == 3
        assert sentences[0] == "这是第一句"
        assert sentences[1] == "这是第二句"
        assert sentences[2] == "这是第三句"

    def test_english_sentences(self):
        from eval.metrics import _split_into_sentences
        text = "First sentence. Second sentence! Third sentence?"
        sentences = _split_into_sentences(text)
        assert len(sentences) == 3

    def test_mixed_sentences(self):
        from eval.metrics import _split_into_sentences
        text = "中文句子。English sentence. 混合内容！"
        sentences = _split_into_sentences(text)
        assert len(sentences) == 3

    def test_empty_text(self):
        from eval.metrics import _split_into_sentences
        sentences = _split_into_sentences("")
        assert sentences == []

    def test_no_punctuation(self):
        from eval.metrics import _split_into_sentences
        text = "没有标点的文本"
        sentences = _split_into_sentences(text)
        assert len(sentences) == 1
        assert sentences[0] == "没有标点的文本"


@pytest.mark.unit
class TestJudgeContextRelevance:
    """Tests for _judge_context_relevance function."""

    @patch("eval.metrics.llm_retrieval._create_llm_client")
    def test_relevant_context_returns_true(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"verdict": "是", "reason": "上下文包含答案"}'
        mock_client.messages.create.return_value = mock_message

        from eval.metrics import _judge_context_relevance
        result = _judge_context_relevance(
            question="营收是多少？",
            expected_output="营收是100万元",
            context="公司2023年营收为100万元",
            api_key="test-key",
            base_url="https://api.test.com",
            model_name="test-model"
        )

        assert result is True

    @patch("eval.metrics.llm_retrieval._create_llm_client")
    def test_irrelevant_context_returns_false(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"verdict": "否", "reason": "上下文无关"}'
        mock_client.messages.create.return_value = mock_message

        from eval.metrics import _judge_context_relevance
        result = _judge_context_relevance(
            question="营收是多少？",
            expected_output="营收是100万元",
            context="今天天气很好",
            api_key="test-key",
            base_url="https://api.test.com",
            model_name="test-model"
        )

        assert result is False

    @patch("eval.metrics.llm_retrieval._create_llm_client")
    def test_llm_error_returns_false(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API Error")

        from eval.metrics import _judge_context_relevance
        result = _judge_context_relevance(
            question="问题",
            expected_output="答案",
            context="上下文",
            api_key="test-key",
            base_url="https://api.test.com",
            model_name="test-model"
        )

        assert result is False


@pytest.mark.unit
class TestCalculateContextPrecision:
    """Tests for calculate_context_precision function."""

    def test_empty_context_returns_zero(self):
        from eval.metrics import calculate_context_precision
        score = calculate_context_precision(
            question="问题",
            expected_output="答案",
            retrieval_context=[],
            api_key="test-key"
        )
        assert score == 0.0

    @patch("eval.metrics.llm_retrieval._judge_context_relevance")
    def test_all_relevant_contexts(self, mock_judge):
        mock_judge.return_value = True

        from eval.metrics import calculate_context_precision
        score = calculate_context_precision(
            question="问题",
            expected_output="答案",
            retrieval_context=["上下文1", "上下文2", "上下文3"],
            api_key="test-key"
        )

        assert score == 1.0
        assert mock_judge.call_count == 3

    @patch("eval.metrics.llm_retrieval._judge_context_relevance")
    def test_no_relevant_contexts(self, mock_judge):
        mock_judge.return_value = False

        from eval.metrics import calculate_context_precision
        score = calculate_context_precision(
            question="问题",
            expected_output="答案",
            retrieval_context=["上下文1", "上下文2", "上下文3"],
            api_key="test-key"
        )

        assert score == 0.0

    @patch("eval.metrics.llm_retrieval._judge_context_relevance")
    def test_partial_relevant_contexts(self, mock_judge):
        mock_judge.side_effect = [True, False, True]

        from eval.metrics import calculate_context_precision
        score = calculate_context_precision(
            question="问题",
            expected_output="答案",
            retrieval_context=["上下文1", "上下文2", "上下文3"],
            api_key="test-key"
        )

        assert 0.0 < score < 1.0

    @patch("eval.metrics.llm_retrieval._judge_context_relevance")
    def test_weighted_precision_calculation(self, mock_judge):
        mock_judge.side_effect = [True, False, True]

        from eval.metrics import calculate_context_precision
        score = calculate_context_precision(
            question="问题",
            expected_output="答案",
            retrieval_context=["上下文1", "上下文2", "上下文3"],
            api_key="test-key"
        )

        wcp_sum = (1/1) + (2/3)
        expected = wcp_sum / 2
        assert score == pytest.approx(expected)


@pytest.mark.unit
class TestCanInferFromContext:
    """Tests for _can_infer_from_context function."""

    @patch("eval.metrics.llm_retrieval._create_llm_client")
    def test_inferable_sentence_returns_true(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"verdict": "是"}'
        mock_client.messages.create.return_value = mock_message

        from eval.metrics import _can_infer_from_context
        result = _can_infer_from_context(
            sentence="营收是100万元",
            context="公司2023年营收为100万元",
            api_key="test-key",
            base_url="https://api.test.com",
            model_name="test-model"
        )

        assert result is True

    @patch("eval.metrics.llm_retrieval._create_llm_client")
    def test_non_inferable_sentence_returns_false(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = '{"verdict": "否"}'
        mock_client.messages.create.return_value = mock_message

        from eval.metrics import _can_infer_from_context
        result = _can_infer_from_context(
            sentence="利润是50万元",
            context="营收是100万元",
            api_key="test-key",
            base_url="https://api.test.com",
            model_name="test-model"
        )

        assert result is False


@pytest.mark.unit
class TestCalculateContextRecall:
    """Tests for calculate_context_recall function."""

    def test_empty_ground_truth_returns_zero(self):
        from eval.metrics import calculate_context_recall
        score = calculate_context_recall(
            question="问题",
            ground_truth="",
            retrieval_context=["上下文"],
            api_key="test-key"
        )
        assert score == 0.0

    def test_empty_context_returns_zero(self):
        from eval.metrics import calculate_context_recall
        score = calculate_context_recall(
            question="问题",
            ground_truth="答案",
            retrieval_context=[],
            api_key="test-key"
        )
        assert score == 0.0

    @patch("eval.metrics.llm_retrieval._can_infer_from_context")
    @patch("eval.metrics.llm_retrieval._split_into_sentences")
    def test_all_sentences_inferable(self, mock_split, mock_infer):
        mock_split.return_value = ["句子1", "句子2", "句子3"]
        mock_infer.return_value = True

        from eval.metrics import calculate_context_recall
        score = calculate_context_recall(
            question="问题",
            ground_truth="句子1。句子2。句子3。",
            retrieval_context=["上下文"],
            api_key="test-key"
        )

        assert score == 1.0
        assert mock_infer.call_count == 3

    @patch("eval.metrics.llm_retrieval._can_infer_from_context")
    @patch("eval.metrics.llm_retrieval._split_into_sentences")
    def test_no_sentences_inferable(self, mock_split, mock_infer):
        mock_split.return_value = ["句子1", "句子2"]
        mock_infer.return_value = False

        from eval.metrics import calculate_context_recall
        score = calculate_context_recall(
            question="问题",
            ground_truth="句子1。句子2。",
            retrieval_context=["上下文"],
            api_key="test-key"
        )

        assert score == 0.0

    @patch("eval.metrics.llm_retrieval._can_infer_from_context")
    @patch("eval.metrics.llm_retrieval._split_into_sentences")
    def test_partial_sentences_inferable(self, mock_split, mock_infer):
        mock_split.return_value = ["句子1", "句子2", "句子3"]
        mock_infer.side_effect = [True, False, True]

        from eval.metrics import calculate_context_recall
        score = calculate_context_recall(
            question="问题",
            ground_truth="句子1。句子2。句子3。",
            retrieval_context=["上下文"],
            api_key="test-key"
        )

        assert score == pytest.approx(2/3)


@pytest.mark.unit
class TestChunkHitRate:

    def test_exact_match(self):
        retrieved = ["doc1::chunk::000", "doc1::chunk::001"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_hit_rate(retrieved, expected) == 1.0

    def test_adjacent_match(self):
        retrieved = ["doc1::chunk::001"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_hit_rate(retrieved, expected, adjacent_tolerance=1) == 1.0

    def test_no_match(self):
        retrieved = ["doc1::chunk::005"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_hit_rate(retrieved, expected, adjacent_tolerance=1) == 0.0

    def test_different_document(self):
        retrieved = ["doc2::chunk::000"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_hit_rate(retrieved, expected) == 0.0

    def test_empty_expected(self):
        retrieved = ["doc1::chunk::000"]
        expected = []
        assert calculate_chunk_hit_rate(retrieved, expected) == 0.0

    def test_empty_retrieved(self):
        retrieved = []
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_hit_rate(retrieved, expected) == 0.0

    def test_multiple_expected_one_adjacent_match(self):
        retrieved = ["doc1::chunk::001"]
        expected = ["doc1::chunk::000", "doc1::chunk::005"]
        assert calculate_chunk_hit_rate(retrieved, expected, adjacent_tolerance=1) == 1.0

    def test_k_parameter(self):
        retrieved = ["doc1::chunk::010", "doc1::chunk::000"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_hit_rate(retrieved, expected, k=1) == 0.0

    def test_zero_tolerance(self):
        retrieved = ["doc1::chunk::001"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_hit_rate(retrieved, expected, adjacent_tolerance=0) == 0.0


@pytest.mark.unit
class TestChunkMRR:

    def test_exact_match_at_position_1(self):
        retrieved = ["doc1::chunk::000", "doc2::chunk::000"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_mrr(retrieved, expected) == 1.0

    def test_adjacent_match_at_position_2(self):
        retrieved = ["doc2::chunk::000", "doc1::chunk::001"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_mrr(retrieved, expected) == pytest.approx(0.5)

    def test_no_match(self):
        retrieved = ["doc2::chunk::000", "doc2::chunk::001"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_mrr(retrieved, expected) == 0.0

    def test_empty_expected(self):
        retrieved = ["doc1::chunk::000"]
        expected = []
        assert calculate_chunk_mrr(retrieved, expected) == 0.0


@pytest.mark.unit
class TestChunkNDCG:

    def test_exact_match_relevance_2(self):
        retrieved = ["doc1::chunk::000", "doc2::chunk::000"]
        expected = ["doc1::chunk::000"]
        dcg = (2**2 - 1) / math.log2(2)
        ideal_dcg = (2**2 - 1) / math.log2(2)
        assert calculate_chunk_ndcg(retrieved, expected) == pytest.approx(dcg / ideal_dcg)

    def test_adjacent_match_relevance_1(self):
        retrieved = ["doc1::chunk::001"]
        expected = ["doc1::chunk::000"]
        dcg = (2**1 - 1) / math.log2(2)
        ideal_dcg = (2**2 - 1) / math.log2(2)
        assert calculate_chunk_ndcg(retrieved, expected) == pytest.approx(dcg / ideal_dcg)

    def test_no_match(self):
        retrieved = ["doc2::chunk::000", "doc2::chunk::001"]
        expected = ["doc1::chunk::000"]
        assert calculate_chunk_ndcg(retrieved, expected) == 0.0

    def test_mixed_exact_and_adjacent(self):
        retrieved = ["doc1::chunk::000", "doc1::chunk::001", "doc2::chunk::000"]
        expected = ["doc1::chunk::000"]
        dcg = (2**2 - 1) / math.log2(2) + (2**1 - 1) / math.log2(3)
        ideal_dcg = (2**2 - 1) / math.log2(2)
        assert calculate_chunk_ndcg(retrieved, expected) == pytest.approx(min(1.0, dcg / ideal_dcg))


@pytest.mark.unit
class TestFalsePositiveRate:

    def test_all_slots_filled(self):
        retrieved = ["doc1.md", "doc2.md", "doc3.md", "doc4.md", "doc5.md"]
        assert calculate_false_positive_rate(retrieved, k=5) == 1.0

    def test_partial_slots_filled(self):
        retrieved = ["doc1.md", "doc2.md", "doc3.md"]
        assert calculate_false_positive_rate(retrieved, k=5) == pytest.approx(0.6)

    def test_no_results(self):
        retrieved = []
        assert calculate_false_positive_rate(retrieved, k=5) == 0.0

    def test_more_results_than_k(self):
        retrieved = ["doc1.md", "doc2.md", "doc3.md", "doc4.md", "doc5.md", "doc6.md", "doc7.md"]
        assert calculate_false_positive_rate(retrieved, k=5) == 1.0


@pytest.mark.unit
class TestDeduplicateByDocument:

    def test_all_same_document(self):
        sources = ["doc1.md", "doc1.md", "doc1.md"]
        assert deduplicate_by_document(sources) == [0]

    def test_mixed_documents(self):
        sources = ["doc1.md", "doc2.md", "doc1.md"]
        assert deduplicate_by_document(sources) == [0, 1]

    def test_single_result(self):
        sources = ["doc1.md"]
        assert deduplicate_by_document(sources) == [0]

    def test_empty(self):
        sources = []
        assert deduplicate_by_document(sources) == []


@pytest.mark.unit
class TestDedupMetrics:

    def test_dedup_hit_rate_same_doc_repeated(self):
        sources = ["doc1.md", "doc1.md", "doc1.md", "doc1.md", "doc1.md"]
        expected = ["doc1.md"]
        assert calculate_dedup_hit_rate(sources, expected, k=5) == 1.0

    def test_dedup_hit_rate_different_docs_match(self):
        sources = ["doc1.md", "doc2.md", "doc3.md"]
        expected = ["doc1.md"]
        assert calculate_dedup_hit_rate(sources, expected, k=5) == 1.0

    def test_dedup_hit_rate_no_match(self):
        sources = ["doc1.md", "doc2.md", "doc3.md"]
        expected = ["doc4.md"]
        assert calculate_dedup_hit_rate(sources, expected, k=5) == 0.0

    def test_dedup_mrr_same_doc_repeated(self):
        sources = ["doc1.md", "doc1.md", "doc1.md", "doc1.md", "doc1.md"]
        expected = ["doc1.md"]
        assert calculate_dedup_mrr(sources, expected) == 1.0

    def test_dedup_mrr_different_docs_match(self):
        sources = ["doc2.md", "doc1.md", "doc3.md"]
        expected = ["doc1.md"]
        assert calculate_dedup_mrr(sources, expected) == pytest.approx(0.5)

    def test_dedup_mrr_no_match(self):
        sources = ["doc1.md", "doc2.md", "doc3.md"]
        expected = ["doc4.md"]
        assert calculate_dedup_mrr(sources, expected) == 0.0

    def test_dedup_ndcg_same_doc_repeated(self):
        sources = ["doc1.md", "doc1.md", "doc1.md", "doc1.md", "doc1.md"]
        expected = ["doc1.md"]
        assert calculate_dedup_ndcg(sources, expected, k=5) == 1.0

    def test_dedup_ndcg_different_docs_match(self):
        sources = ["doc1.md", "doc2.md", "doc3.md"]
        expected = ["doc1.md"]
        assert calculate_dedup_ndcg(sources, expected, k=5) == 1.0

    def test_dedup_ndcg_no_match(self):
        sources = ["doc1.md", "doc2.md", "doc3.md"]
        expected = ["doc4.md"]
        assert calculate_dedup_ndcg(sources, expected, k=5) == 0.0


@pytest.mark.unit
class TestNormalizeSourceWithEquivalence:

    def test_no_equivalence_groups_returns_stem(self):
        result = normalize_source_with_equivalence(
            "annual_report/贵州茅台2023年年度报告.md"
        )
        assert result == "贵州茅台2023年年度报告"

    def test_none_equivalence_groups_returns_stem(self):
        result = normalize_source_with_equivalence(
            "annual_report/贵州茅台2023年年度报告.md",
            equivalence_groups=None,
        )
        assert result == "贵州茅台2023年年度报告"

    def test_empty_equivalence_groups_returns_stem(self):
        result = normalize_source_with_equivalence(
            "annual_report/贵州茅台2023年年度报告.md",
            equivalence_groups={},
        )
        assert result == "贵州茅台2023年年度报告"

    def test_member_maps_to_group_key(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        result = normalize_source_with_equivalence(
            "中国建筑2023年年度报告摘要.pdf",
            equivalence_groups=groups,
        )
        assert result == "中国建筑2023年年度报告"

    def test_primary_member_maps_to_group_key(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        result = normalize_source_with_equivalence(
            "中国建筑2023年年度报告.pdf",
            equivalence_groups=groups,
        )
        assert result == "中国建筑2023年年度报告"

    def test_non_member_returns_original_stem(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        result = normalize_source_with_equivalence(
            "其他公司2023年年度报告.pdf",
            equivalence_groups=groups,
        )
        assert result == "其他公司2023年年度报告"

    def test_path_with_directory_maps_to_group_key(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        result = normalize_source_with_equivalence(
            "annual_report/中国建筑2023年年度报告摘要.md",
            equivalence_groups=groups,
        )
        assert result == "中国建筑2023年年度报告"

    def test_multiple_groups(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ],
            "贵州茅台2023年年度报告": [
                "贵州茅台2023年年度报告.pdf",
                "贵州茅台2023年年度报告_英文版_.pdf",
            ],
        }
        result_a = normalize_source_with_equivalence(
            "中国建筑2023年年度报告摘要.pdf",
            equivalence_groups=groups,
        )
        result_b = normalize_source_with_equivalence(
            "贵州茅台2023年年度报告_英文版_.pdf",
            equivalence_groups=groups,
        )
        assert result_a == "中国建筑2023年年度报告"
        assert result_b == "贵州茅台2023年年度报告"

    def test_single_member_group(self):
        groups = {
            "独立报告": [
                "独立报告.pdf",
            ]
        }
        result = normalize_source_with_equivalence(
            "独立报告.pdf",
            equivalence_groups=groups,
        )
        assert result == "独立报告"

    def test_include_parent_with_equivalence_groups(self):
        groups = {
            "2025/贵州茅台": [
                "annual_reports/2025/贵州茅台.md",
                "annual_reports/2025/贵州茅台_摘要.md",
            ]
        }
        result = normalize_source_with_equivalence(
            "annual_reports/2025/贵州茅台_摘要.md",
            equivalence_groups=groups,
            include_parent=True,
        )
        assert result == "2025/贵州茅台"

    def test_include_parent_no_equivalence_groups(self):
        result = normalize_source_with_equivalence(
            "annual_reports/2025/贵州茅台.md",
            include_parent=True,
        )
        assert result == "2025/贵州茅台"

    def test_include_parent_non_member_returns_parent_stem(self):
        groups = {
            "2025/贵州茅台": [
                "annual_reports/2025/贵州茅台.md",
            ]
        }
        result = normalize_source_with_equivalence(
            "annual_reports/2024/其他报告.md",
            equivalence_groups=groups,
            include_parent=True,
        )
        assert result == "2024/其他报告"


@pytest.mark.unit
class TestEquivalenceGroupDocumentMatching:

    def test_annual_report_vs_summary_hit_rate(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in ["annual_report/中国建筑2023年年度报告摘要.md"]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告.pdf"]
        ]
        assert calculate_hit_rate(retrieved, expected) == 1.0

    def test_annual_report_vs_summary_mrr(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in ["other.md", "annual_report/中国建筑2023年年度报告摘要.md"]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告.pdf"]
        ]
        assert calculate_mrr(retrieved, expected) == pytest.approx(0.5)

    def test_annual_report_vs_summary_ndcg(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in ["annual_report/中国建筑2023年年度报告摘要.md"]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告.pdf"]
        ]
        assert calculate_ndcg(retrieved, expected) == 1.0

    def test_chinese_vs_english_version(self):
        groups = {
            "贵州茅台2023年年度报告": [
                "贵州茅台2023年年度报告.pdf",
                "贵州茅台2023年年度报告_英文版_.pdf",
            ]
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in ["贵州茅台2023年年度报告_英文版_.md"]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["贵州茅台2023年年度报告.pdf"]
        ]
        assert calculate_hit_rate(retrieved, expected) == 1.0
        assert calculate_mrr(retrieved, expected) == 1.0
        assert calculate_ndcg(retrieved, expected) == 1.0

    def test_no_equivalence_groups_still_works(self):
        retrieved = ["annual_report/中国建筑2023年年度报告摘要.md"]
        expected = ["中国建筑2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected) == 0.0

    def test_non_equivalent_documents_not_matched(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in ["其他公司2023年年度报告.md"]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告.pdf"]
        ]
        assert calculate_hit_rate(retrieved, expected) == 0.0


@pytest.mark.unit
class TestParseChunkId:

    def test_new_format_parsing(self):
        assert _parse_chunk_id("doc1::chunk::003") == ("doc1", 3)

    def test_new_format_with_underscores_in_name(self):
        assert _parse_chunk_id("贵州茅台_英文版_::chunk::005") == ("贵州茅台_英文版_", 5)

    def test_old_format_backward_compat(self):
        assert _parse_chunk_id("doc1_003") == ("doc1", 3)

    def test_old_format_with_underscores(self):
        assert _parse_chunk_id("贵州茅台_英文版__003") == ("贵州茅台_英文版_", 3)

    def test_no_separator(self):
        assert _parse_chunk_id("nodata") == ("nodata", -1)

    def test_non_numeric_suffix(self):
        assert _parse_chunk_id("doc1_abc") == ("doc1_abc", -1)


@pytest.mark.unit
class TestEquivalenceGroupExactMatchPriority:

    def test_exact_match_still_works_with_equivalence_groups(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告.pdf"]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告.pdf"]
        ]
        assert calculate_hit_rate(retrieved, expected) == 1.0
        assert calculate_mrr(retrieved, expected) == 1.0
        assert calculate_ndcg(retrieved, expected) == 1.0

    def test_exact_match_and_equivalence_both_present(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ]
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.md",
            ]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告.pdf"]
        ]
        assert calculate_hit_rate(retrieved, expected) == 1.0
        assert calculate_mrr(retrieved, expected) == 1.0

    def test_different_groups_not_conflated(self):
        groups = {
            "中国建筑2023年年度报告": [
                "中国建筑2023年年度报告.pdf",
                "中国建筑2023年年度报告摘要.pdf",
            ],
            "贵州茅台2023年年度报告": [
                "贵州茅台2023年年度报告.pdf",
                "贵州茅台2023年年度报告摘要.pdf",
            ],
        }
        retrieved = [
            normalize_source_with_equivalence(s, groups)
            for s in ["中国建筑2023年年度报告摘要.md"]
        ]
        expected = [
            normalize_source_with_equivalence(s, groups)
            for s in ["贵州茅台2023年年度报告.pdf"]
        ]
        assert calculate_hit_rate(retrieved, expected) == 0.0



