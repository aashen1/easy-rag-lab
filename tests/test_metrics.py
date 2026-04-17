import pytest

from eval.metrics import calculate_hit_rate, calculate_mrr, calculate_ndcg, normalize_source


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
class TestCalculateHitRate:

    def test_full_hit(self):
        retrieved = ["doc1", "doc2", "doc3"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected) == 1.0

    def test_partial_hit(self):
        retrieved = ["doc1", "doc2", "doc4"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected) == pytest.approx(2 / 3)

    def test_no_hit(self):
        retrieved = ["doc4", "doc5"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected) == 0.0

    def test_empty_expected(self):
        retrieved = ["doc1", "doc2"]
        expected = []
        assert calculate_hit_rate(retrieved, expected) == 0.0

    def test_empty_retrieved(self):
        retrieved = []
        expected = ["doc1", "doc2"]
        assert calculate_hit_rate(retrieved, expected) == 0.0

    def test_duplicate_sources(self):
        retrieved = ["doc1", "doc1", "doc2", "doc2"]
        expected = ["doc1", "doc2", "doc3"]
        assert calculate_hit_rate(retrieved, expected) == pytest.approx(2 / 3)

    def test_cross_format_hit(self):
        retrieved = ["annual_report/贵州茅台2023年年度报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected) == 1.0

    def test_cross_format_no_hit(self):
        retrieved = ["annual_report/其他报告.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        assert calculate_hit_rate(retrieved, expected) == 0.0


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
        dcg = 1.0 / 1 + 1.0 / 3
        ideal_dcg = 1.0 / 1 + 1.0 / 2 + 1.0 / 3
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
        dcg = 1.0 / 2
        ideal_dcg = 1.0 / 1
        assert score == pytest.approx(dcg / ideal_dcg)

    def test_cross_format_ndcg(self):
        retrieved = ["annual_report/贵州茅台2023年年度报告.md", "other.md"]
        expected = ["贵州茅台2023年年度报告.pdf"]
        score = calculate_ndcg(retrieved, expected)
        assert score == 1.0
