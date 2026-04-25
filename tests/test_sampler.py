from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import ConfigurationError, ParsingError
from src.sampler import SamplingConfig, count_pdf_pages, determine_sample


class TestSamplingConfig:
    def test_count_mode_valid(self):
        config = SamplingConfig(mode="count", value=10)
        assert config.mode == "count"
        assert config.value == 10

    def test_pages_mode_valid(self):
        config = SamplingConfig(mode="pages", value=5000)
        assert config.mode == "pages"
        assert config.value == 5000

    def test_ratio_mode_valid(self):
        config = SamplingConfig(mode="ratio", value=0.1)
        assert config.mode == "ratio"
        assert config.value == 0.1

    def test_ratio_mode_one(self):
        config = SamplingConfig(mode="ratio", value=1.0)
        assert config.value == 1.0

    def test_invalid_mode(self):
        with pytest.raises(ConfigurationError, match="Invalid sampling mode"):
            SamplingConfig(mode="invalid", value=10)

    def test_count_mode_zero(self):
        with pytest.raises(ConfigurationError, match="must be a positive integer"):
            SamplingConfig(mode="count", value=0)

    def test_count_mode_negative(self):
        with pytest.raises(ConfigurationError, match="must be a positive integer"):
            SamplingConfig(mode="count", value=-5)

    def test_count_mode_float(self):
        with pytest.raises(ConfigurationError, match="must be a positive integer"):
            SamplingConfig(mode="count", value=5.5)

    def test_pages_mode_zero(self):
        with pytest.raises(ConfigurationError, match="must be a positive integer"):
            SamplingConfig(mode="pages", value=0)

    def test_ratio_mode_zero(self):
        with pytest.raises(ConfigurationError, match="must be a float in"):
            SamplingConfig(mode="ratio", value=0.0)

    def test_ratio_mode_negative(self):
        with pytest.raises(ConfigurationError, match="must be a float in"):
            SamplingConfig(mode="ratio", value=-0.1)

    def test_ratio_mode_over_one(self):
        with pytest.raises(ConfigurationError, match="must be a float in"):
            SamplingConfig(mode="ratio", value=1.5)


class TestCountPdfPages:
    @patch("src.sampler.fitz")
    def test_count_pages_success(self, mock_fitz):
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=42)
        mock_fitz.open.return_value = mock_doc

        result = count_pdf_pages(Path("test.pdf"))
        assert result == 42
        mock_doc.close.assert_called_once()

    @patch("src.sampler.fitz")
    def test_count_pages_failure(self, mock_fitz):
        mock_fitz.open.side_effect = Exception("Cannot open file")

        with pytest.raises(ParsingError, match="Failed to count pages"):
            count_pdf_pages(Path("bad.pdf"))


class TestDetermineSample:
    def test_empty_pdf_list_raises(self):
        config = SamplingConfig(mode="count", value=5)
        with pytest.raises(
            ConfigurationError, match="Cannot sample from an empty list"
        ):
            determine_sample([], config)

    def test_count_mode_basic(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(20)]
        config = SamplingConfig(mode="count", value=5)
        result = determine_sample(pdf_files, config)
        assert len(result) == 5
        assert all(f in pdf_files for f in result)

    def test_count_mode_exceeds_total(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(3)]
        config = SamplingConfig(mode="count", value=10)
        result = determine_sample(pdf_files, config)
        assert len(result) == 3

    def test_count_mode_equals_total(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(5)]
        config = SamplingConfig(mode="count", value=5)
        result = determine_sample(pdf_files, config)
        assert len(result) == 5

    @patch("src.sampler.count_pdf_pages")
    def test_pages_mode_basic(self, mock_count_pages):
        page_counts = [100, 200, 150, 50, 300]
        pdf_files = [Path(f"file_{i}.pdf") for i in range(5)]
        page_map = {str(f): c for f, c in zip(pdf_files, page_counts, strict=False)}
        mock_count_pages.side_effect = lambda f: page_map[str(f)]
        config = SamplingConfig(mode="pages", value=500)
        result = determine_sample(pdf_files, config)
        total_pages = sum(page_map[str(f)] for f in result)
        assert total_pages >= 500
        assert len(result) <= 5

    @patch("src.sampler.count_pdf_pages")
    def test_pages_mode_single_large_pdf(self, mock_count_pages):
        mock_count_pages.return_value = 6000
        pdf_files = [Path("large.pdf")]
        config = SamplingConfig(mode="pages", value=5000)
        result = determine_sample(pdf_files, config)
        assert len(result) == 1

    @patch("src.sampler.count_pdf_pages")
    def test_pages_mode_skips_unreadable(self, mock_count_pages):
        mock_count_pages.side_effect = [
            Exception("Cannot read"),
            200,
            300,
        ]
        pdf_files = [Path(f"file_{i}.pdf") for i in range(3)]
        config = SamplingConfig(mode="pages", value=400)
        result = determine_sample(pdf_files, config)
        assert len(result) == 2

    @patch("src.sampler.count_pdf_pages")
    def test_pages_mode_all_unreadable(self, mock_count_pages):
        mock_count_pages.side_effect = Exception("Cannot read")
        pdf_files = [Path(f"file_{i}.pdf") for i in range(3)]
        config = SamplingConfig(mode="pages", value=100)
        result = determine_sample(pdf_files, config)
        assert result == []

    def test_ratio_mode_basic(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(100)]
        config = SamplingConfig(mode="ratio", value=0.1)
        result = determine_sample(pdf_files, config)
        assert len(result) == 10

    def test_ratio_mode_small_dataset(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(3)]
        config = SamplingConfig(mode="ratio", value=0.1)
        result = determine_sample(pdf_files, config)
        assert len(result) >= 1

    def test_ratio_mode_one(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(10)]
        config = SamplingConfig(mode="ratio", value=1.0)
        result = determine_sample(pdf_files, config)
        assert len(result) == 10

    def test_ratio_mode_very_small_ratio(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(50)]
        config = SamplingConfig(mode="ratio", value=0.01)
        result = determine_sample(pdf_files, config)
        assert len(result) >= 1

    def test_count_mode_returns_subset(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(20)]
        config = SamplingConfig(mode="count", value=5)
        result = determine_sample(pdf_files, config)
        assert set(result).issubset(set(pdf_files))

    def test_count_mode_no_duplicates(self):
        pdf_files = [Path(f"file_{i}.pdf") for i in range(20)]
        config = SamplingConfig(mode="count", value=10)
        result = determine_sample(pdf_files, config)
        assert len(result) == len(set(result))
