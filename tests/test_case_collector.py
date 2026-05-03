import json
from unittest.mock import patch

import pytest
import yaml

from src.case_collector import (
    CASE_TYPE_BAD,
    CASE_TYPE_GOOD,
    DEDUP_STATUS_DUPLICATE,
    DEDUP_STATUS_SAVED,
    DEDUP_STATUS_TYPE_CHANGED,
    convert_case,
    delete_case,
    find_case_by_question,
    list_cases,
    load_case,
    save_case,
    save_case_with_dedup,
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


@pytest.mark.unit
class TestDeleteCase:
    def test_delete_case_moves_to_trashbin(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                CASE_TYPE_BAD, "问题1", _make_result(), {}, _make_base_config()
            )
            case_id = case_dir.name
            assert case_dir.exists()

            delete_case(case_id)

            assert not case_dir.exists()
            trashbin = tmp_path.parent.parent / ".trashbin"
            assert trashbin.exists()
            trashed = list(trashbin.iterdir())
            assert any(case_id in t.name for t in trashed)

    def test_delete_case_not_found(self, tmp_path):
        with (
            patch("src.case_collector.get_cases_dir", return_value=tmp_path),
            pytest.raises(FileNotFoundError),
        ):
            delete_case("nonexistent_case")


@pytest.mark.unit
class TestConvertCase:
    def test_convert_bad_to_good(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            src_dir = save_case(
                CASE_TYPE_BAD,
                "公司2024年营业收入是多少？",
                _make_result(),
                {},
                _make_base_config(),
                meal_name="test_meal",
            )
            src_id = src_dir.name

            new_dir = convert_case(src_id, CASE_TYPE_GOOD)

        assert not src_dir.exists()
        assert new_dir.name.startswith("gc_")
        new_manifest = json.loads(
            (new_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert new_manifest["case_type"] == CASE_TYPE_GOOD

    def test_convert_good_to_bad(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            src_dir = save_case(
                CASE_TYPE_GOOD,
                "测试问题",
                _make_result(),
                {},
                _make_base_config(),
            )
            src_id = src_dir.name

            new_dir = convert_case(src_id, CASE_TYPE_BAD)

        assert not src_dir.exists()
        assert new_dir.name.startswith("bc_")

    def test_convert_preserves_query_result(self, tmp_path):
        result = _make_result()
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            src_dir = save_case(
                CASE_TYPE_BAD, "测试问题", result, {}, _make_base_config()
            )

            new_dir = convert_case(src_dir.name, CASE_TYPE_GOOD)

        new_result = json.loads(
            (new_dir / "query_result.json").read_text(encoding="utf-8")
        )
        assert new_result["question"] == result["question"]
        assert new_result["answer"] == result["answer"]

    def test_convert_invalid_type_raises(self, tmp_path):
        with (
            patch("src.case_collector.get_cases_dir", return_value=tmp_path),
            pytest.raises(ValueError, match="Invalid target_type"),
        ):
            convert_case("some_case", "invalid")

    def test_convert_not_found_raises(self, tmp_path):
        with (
            patch("src.case_collector.get_cases_dir", return_value=tmp_path),
            pytest.raises(FileNotFoundError),
        ):
            convert_case("nonexistent_case", CASE_TYPE_GOOD)

    def test_convert_migrates_chat_history_and_trace(self, tmp_path):
        from src.trace_models import PipelineTrace, TraceStep

        chat_history = [
            {"role": "user", "content": "前一轮问题"},
            {"role": "assistant", "content": "前一轮回答"},
        ]
        trace = PipelineTrace(
            trace_id="t1",
            question="测试问题",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "测试问题"},
                    output_data={"results": [], "count": 0},
                )
            ],
        )
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            src_dir = save_case(
                CASE_TYPE_BAD,
                "测试问题",
                _make_result(),
                {},
                _make_base_config(),
                chat_history=chat_history,
                trace=trace,
            )

            new_dir = convert_case(src_dir.name, CASE_TYPE_GOOD)

        new_history = json.loads(
            (new_dir / "chat_history.json").read_text(encoding="utf-8")
        )
        assert len(new_history) == 2
        assert new_history[0]["content"] == "前一轮问题"

        new_trace = json.loads(
            (new_dir / "pipeline_trace.json").read_text(encoding="utf-8")
        )
        assert new_trace["trace_id"] == "t1"
        assert len(new_trace["steps"]) == 1

    def test_convert_migrates_ground_truth_and_diagnosis(self, tmp_path):
        from src.case_collector import save_diagnosis, save_ground_truth
        from src.trace_models import DiagnosisResult, GroundTruth

        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            src_dir = save_case(
                CASE_TYPE_BAD,
                "测试问题",
                _make_result(),
                {},
                _make_base_config(),
            )
            src_id = src_dir.name

            gt = GroundTruth(
                answer_text="参考答案",
                source_pdf="report.pdf",
                source_page=5,
                chunk_ids=["c1"],
                annotated_at="2026-05-01T10:00:00",
                annotator="user",
            )
            save_ground_truth(src_id, gt)

            diag = DiagnosisResult(
                root_cause="retrieval_miss",
                root_cause_id="RC-1",
                severity="high",
                finding="Chunk not retrieved",
                fix_suggestion="Increase top_k",
                config_patch={"retrieval": {"top_k": 20}},
                confidence=0.85,
            )
            save_diagnosis(src_id, diag)

            new_dir = convert_case(src_id, CASE_TYPE_GOOD)

        new_gt = json.loads((new_dir / "ground_truth.json").read_text(encoding="utf-8"))
        assert new_gt["answer_text"] == "参考答案"
        assert new_gt["source_page"] == 5

        new_diag = json.loads((new_dir / "diagnosis.json").read_text(encoding="utf-8"))
        assert new_diag["root_cause_id"] == "RC-1"
        assert new_diag["severity"] == "high"

        new_manifest = json.loads(
            (new_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert new_manifest["has_ground_truth"] is True
        assert new_manifest["has_diagnosis"] is True
        assert new_manifest["root_cause"] == "retrieval_miss"


@pytest.mark.unit
class TestFindCaseByQuestion:
    def test_find_case_by_question_match(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            save_case(
                CASE_TYPE_BAD,
                "公司2024年营业收入是多少？",
                _make_result(),
                {},
                _make_base_config(),
            )

            manifest = find_case_by_question("公司2024年营业收入是多少？")

        assert manifest is not None
        assert manifest["case_type"] == CASE_TYPE_BAD

    def test_find_case_by_question_no_match(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            save_case(CASE_TYPE_BAD, "问题A", _make_result(), {}, _make_base_config())

            manifest = find_case_by_question("完全不相关的问题")

        assert manifest is None

    def test_find_case_by_question_with_type_filter(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            save_case(CASE_TYPE_BAD, "问题1", _make_result(), {}, _make_base_config())
            save_case(CASE_TYPE_GOOD, "问题2", _make_result(), {}, _make_base_config())

            manifest = find_case_by_question("问题1", case_type=CASE_TYPE_GOOD)

        assert manifest is None

    def test_find_case_by_question_empty(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            manifest = find_case_by_question("任何问题")

        assert manifest is None


@pytest.mark.unit
class TestSaveCaseWithChatHistory:
    def test_save_case_with_chat_history_creates_file(self, tmp_path):
        chat_history = [
            {"role": "user", "content": "第一个问题"},
            {"role": "assistant", "content": "第一个回答"},
        ]
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="第二个问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                chat_history=chat_history,
            )

        assert (case_dir / "chat_history.json").exists()
        saved_history = json.loads(
            (case_dir / "chat_history.json").read_text(encoding="utf-8")
        )
        assert len(saved_history) == 2
        assert saved_history[0]["role"] == "user"
        assert saved_history[1]["role"] == "assistant"

    def test_save_case_without_chat_history_no_file(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
            )

        assert not (case_dir / "chat_history.json").exists()

    def test_save_case_empty_chat_history_no_file(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                chat_history=[],
            )

        assert not (case_dir / "chat_history.json").exists()

    def test_manifest_has_chat_history_flag(self, tmp_path):
        chat_history = [
            {"role": "user", "content": "问题"},
            {"role": "assistant", "content": "回答"},
        ]
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                chat_history=chat_history,
            )

        manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["has_chat_history"] is True

    def test_manifest_no_chat_history_flag_false(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
            )

        manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["has_chat_history"] is False


@pytest.mark.unit
class TestLoadCaseWithChatHistory:
    def test_load_case_with_chat_history(self, tmp_path):
        chat_history = [
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
        ]
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                CASE_TYPE_BAD,
                "测试问题",
                _make_result(),
                {},
                _make_base_config(),
                chat_history=chat_history,
            )

            data = load_case(case_dir.name)

        assert "chat_history" in data
        assert len(data["chat_history"]) == 2

    def test_load_case_without_chat_history(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir = save_case(
                CASE_TYPE_BAD,
                "测试问题",
                _make_result(),
                {},
                _make_base_config(),
            )

            data = load_case(case_dir.name)

        assert "chat_history" not in data


@pytest.mark.unit
class TestSaveCaseWithDedup:
    def test_first_save_returns_saved(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir, status = save_case_with_dedup(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                saved_case_type=None,
                saved_case_id=None,
            )

        assert status == DEDUP_STATUS_SAVED
        assert case_dir is not None
        assert case_dir.name.startswith("bc_")

    def test_duplicate_same_type_returns_duplicate(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir, status = save_case_with_dedup(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                saved_case_type=CASE_TYPE_BAD,
                saved_case_id="bc_existing_case",
            )

        assert status == DEDUP_STATUS_DUPLICATE
        assert case_dir is None

    def test_type_changed_returns_type_changed(self, tmp_path):
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            src_dir = save_case(
                CASE_TYPE_BAD,
                "测试问题",
                _make_result(),
                {},
                _make_base_config(),
            )

            case_dir, status = save_case_with_dedup(
                case_type=CASE_TYPE_GOOD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                saved_case_type=CASE_TYPE_BAD,
                saved_case_id=src_dir.name,
            )

        assert status == DEDUP_STATUS_TYPE_CHANGED
        assert case_dir is not None
        assert case_dir.name.startswith("gc_")

    def test_with_chat_history(self, tmp_path):
        chat_history = [
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
        ]
        with patch("src.case_collector.get_cases_dir", return_value=tmp_path):
            case_dir, status = save_case_with_dedup(
                case_type=CASE_TYPE_BAD,
                question="测试问题",
                result=_make_result(),
                config_overrides={},
                base_config=_make_base_config(),
                chat_history=chat_history,
                saved_case_type=None,
                saved_case_id=None,
            )

        assert status == DEDUP_STATUS_SAVED
        assert (case_dir / "chat_history.json").exists()
