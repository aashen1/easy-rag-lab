import json
from unittest.mock import patch

import pytest
import yaml

from src.case_collector import (
    CASE_TYPE_BAD,
    CASE_TYPE_GOOD,
    list_cases,
    load_case,
    save_case,
)


def _make_meal_config():
    from src.meal.models import MealConfig, MealFile

    return MealConfig(
        data_id="abc123def456",
        name="test_meal",
        created_at="2026-05-02T12:00:00",
        sampling_config=None,
        collection_name="test_collection",
        pdf_files=[
            MealFile(
                path="annual_reports/2023/report.pdf",
                sha256="a1b2c3d4",
                size_bytes=1234567,
            ),
        ],
        config_snapshot=None,
        config_hashes=None,
    )


def _make_result():
    return {
        "question": "公司2024年营业收入是多少？",
        "answer": "根据年报，公司2024年营业收入为500亿元。",
        "contexts": ["Revenue was 50 billion..."],
        "scores": [0.95],
        "sources": ["annual_reports/2023/report.pdf"],
        "chunk_ids": ["c1"],
        "token_usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "total_tokens": 1200,
        },
    }


def _make_base_config():
    return {
        "llm_presets": {
            "default": {
                "model_name": "test-model",
                "api_key": "sk-secret-key-12345",
                "temperature": 0.0,
            }
        },
        "retrieval": {
            "method": "vector",
            "top_k": 5,
        },
        "embedding": {
            "model_name": "BAAI/bge-large-zh-v1.5",
        },
    }


def _make_config_overrides():
    return {
        "retrieval": {
            "method": "hybrid",
            "top_k": 10,
            "reranker": {"enabled": True},
        }
    }


@pytest.mark.unit
class TestSaveCase:
    def test_save_badcase_creates_all_files(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides=_make_config_overrides(),
                base_config=_make_base_config(),
                meal_config=_make_meal_config(),
                meal_name="test_meal",
            )

        assert (case_dir / "manifest.json").exists()
        assert (case_dir / "config_snapshot.yaml").exists()
        assert (case_dir / "meal_snapshot.json").exists()
        assert (case_dir / "query_result.json").exists()
        assert (case_dir / "environment.json").exists()

    def test_save_goodcase_creates_all_files(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_GOOD,
                question="测试问题",
                result=_make_result(),
                config_overrides=_make_config_overrides(),
                base_config=_make_base_config(),
                meal_config=_make_meal_config(),
                meal_name="test_meal",
            )

        assert (case_dir / "manifest.json").exists()
        assert (case_dir / "config_snapshot.yaml").exists()
        assert (case_dir / "meal_snapshot.json").exists()
        assert (case_dir / "query_result.json").exists()
        assert (case_dir / "environment.json").exists()

    def test_save_badcase_prefix(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
            )
        assert case_dir.name.startswith("bc_")

    def test_save_goodcase_prefix(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_GOOD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
            )
        assert case_dir.name.startswith("gc_")

    def test_config_sanitized(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides=_make_config_overrides(),
                base_config=_make_base_config(),
            )

        config = yaml.safe_load(
            (case_dir / "config_snapshot.yaml").read_text(encoding="utf-8")
        )
        assert config["llm_presets"]["default"]["api_key"] == "***"

    def test_config_merged_with_overrides(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides=_make_config_overrides(),
                base_config=_make_base_config(),
            )

        config = yaml.safe_load(
            (case_dir / "config_snapshot.yaml").read_text(encoding="utf-8")
        )
        assert config["retrieval"]["method"] == "hybrid"
        assert config["retrieval"]["top_k"] == 10
        assert config["retrieval"]["reranker"]["enabled"] is True
        assert config["embedding"]["model_name"] == "BAAI/bge-large-zh-v1.5"

    def test_manifest_structure(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="公司2024年营业收入是多少？",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                meal_name="test_meal",
            )

        manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["case_type"] == CASE_TYPE_BAD
        assert manifest["status"] == "open"
        assert manifest["question_preview"] == "公司2024年营业收入是多少？"
        assert manifest["meal_name"] == "test_meal"
        assert "case_id" in manifest
        assert "created_at" in manifest

    def test_meal_snapshot_with_pdf_hashes(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                meal_config=_make_meal_config(),
                meal_name="test_meal",
            )

        meal = json.loads((case_dir / "meal_snapshot.json").read_text(encoding="utf-8"))
        assert meal["meal_name"] == "test_meal"
        assert meal["data_id"] == "abc123def456"
        assert len(meal["pdf_files"]) == 1
        assert meal["pdf_files"][0]["sha256"] == "a1b2c3d4"

    def test_query_result_preserved(self, tmp_path):
        result = _make_result()
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=result,
                config_overrides={},
                base_config=_make_base_config(),
            )

        saved_result = json.loads(
            (case_dir / "query_result.json").read_text(encoding="utf-8")
        )
        assert saved_result["question"] == result["question"]
        assert saved_result["answer"] == result["answer"]
        assert saved_result["contexts"] == result["contexts"]
        assert saved_result["scores"] == result["scores"]

    def test_environment_info_collected(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
            )

        env = json.loads((case_dir / "environment.json").read_text(encoding="utf-8"))
        assert "timestamp" in env

    def test_invalid_case_type_raises(self, tmp_path):
        with (
            patch("src.case_collector.get_cases_dir", return_value=tmp_path),
            pytest.raises(ValueError, match="Invalid case_type"),
        ):
            save_case(
                case_type="invalid",
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
            )

    def test_none_meal_config(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                meal_config=None,
                meal_name=None,
            )

        meal = json.loads((case_dir / "meal_snapshot.json").read_text(encoding="utf-8"))
        assert meal["pdf_files"] == []


@pytest.mark.unit
class TestListCases:
    def test_list_all_cases(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            save_case(CASE_TYPE_BAD, "问题1", _make_result(), {}, _make_base_config())
            save_case(CASE_TYPE_GOOD, "问题2", _make_result(), {}, _make_base_config())

            cases = list_cases()

        assert len(cases) == 2

    def test_list_cases_filter_bad(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            save_case(CASE_TYPE_BAD, "问题1", _make_result(), {}, _make_base_config())
            save_case(CASE_TYPE_GOOD, "问题2", _make_result(), {}, _make_base_config())

            cases = list_cases(case_type=CASE_TYPE_BAD)

        assert len(cases) == 1
        assert cases[0]["case_type"] == CASE_TYPE_BAD

    def test_list_cases_filter_good(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            save_case(CASE_TYPE_BAD, "问题1", _make_result(), {}, _make_base_config())
            save_case(CASE_TYPE_GOOD, "问题2", _make_result(), {}, _make_base_config())

            cases = list_cases(case_type=CASE_TYPE_GOOD)

        assert len(cases) == 1
        assert cases[0]["case_type"] == CASE_TYPE_GOOD

    def test_list_cases_empty(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            cases = list_cases()

        assert cases == []


@pytest.mark.unit
class TestLoadCase:
    def test_load_case_all_files(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                CASE_TYPE_BAD,
                "测试问题",
                _make_result(),
                _make_config_overrides(),
                _make_base_config(),
                meal_config=_make_meal_config(),
                meal_name="test_meal",
            )

            data = load_case(case_dir.name)

        assert "manifest" in data
        assert "config_snapshot" in data
        assert "meal_snapshot" in data
        assert "query_result" in data
        assert "environment" in data
        assert data["manifest"]["case_type"] == CASE_TYPE_BAD
        assert data["query_result"]["question"] == "公司2024年营业收入是多少？"

    def test_load_case_not_found(self, tmp_path):
        with (
            patch("src.case_collector.get_cases_dir", return_value=tmp_path),
            pytest.raises(FileNotFoundError),
        ):
            load_case("nonexistent_case")


@pytest.mark.unit
class TestCaseIdUniqueness:
    def test_different_questions_different_ids(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            dir1 = save_case(
                CASE_TYPE_BAD, "问题A", _make_result(), {}, _make_base_config()
            )
            dir2 = save_case(
                CASE_TYPE_BAD, "问题B", _make_result(), {}, _make_base_config()
            )

        assert dir1.name != dir2.name
