from __future__ import annotations

import json

import pytest
from langgraph.store.memory import InMemoryStore

from src.agent.memory.experience_store import ExperienceStore

pytestmark = pytest.mark.unit


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def experience_store(store):
    return ExperienceStore(store)


class TestSaveExperienceNewAPI:
    def test_save_returns_key(self, experience_store):
        key = experience_store.save_experience(
            summary="年报用 pymupdf4llm 效果好",
            category="parser_selection",
            details="年报 PDF 表格密集，pymupdf4llm 解析质量优于 pdfplumber",
            pdf_type="annual_report",
        )
        assert key.startswith("exp_")

    def test_save_stores_all_fields(self, experience_store, store):
        key = experience_store.save_experience(
            summary="年报用 pymupdf4llm 效果好",
            category="parser_selection",
            details="年报 PDF 表格密集，pymupdf4llm 解析质量优于 pdfplumber",
            session_id="sess_001",
            pdf_type="annual_report",
            source_path="data/raw/annual_2024.pdf",
        )
        ns = ("maintenance", "experience", "annual_report")
        item = store.get(ns, key)
        assert item is not None
        assert item.value["summary"] == "年报用 pymupdf4llm 效果好"
        assert item.value["category"] == "parser_selection"
        assert (
            item.value["details"]
            == "年报 PDF 表格密集，pymupdf4llm 解析质量优于 pdfplumber"
        )
        assert item.value["session_id"] == "sess_001"
        assert item.value["pdf_type"] == "annual_report"
        assert item.value["source_path"] == "data/raw/annual_2024.pdf"
        assert "timestamp" in item.value

    def test_save_without_pdf_type_uses_generic(self, experience_store, store):
        key = experience_store.save_experience(
            summary="通用经验",
            category="workflow_tip",
            details="先诊断再修复",
        )
        ns = ("maintenance", "experience", "generic")
        item = store.get(ns, key)
        assert item is not None
        assert item.value["pdf_type"] is None

    def test_save_with_empty_strings(self, experience_store, store):
        key = experience_store.save_experience()
        ns = ("maintenance", "experience", "generic")
        item = store.get(ns, key)
        assert item is not None
        assert item.value["summary"] == ""
        assert item.value["category"] == ""
        assert item.value["details"] == ""


class TestGetRelevantExperiences:
    def test_with_pdf_type(self, experience_store):
        experience_store.save_experience(
            summary="年报经验",
            category="parser_selection",
            details="年报推荐 pymupdf4llm",
            pdf_type="annual_report",
        )
        experience_store.save_experience(
            summary="研报经验",
            category="chunk_strategy",
            details="研推荐 page_aware",
            pdf_type="research_report",
        )
        results = experience_store.get_relevant_experiences(pdf_type="annual_report")
        assert len(results) >= 1
        summaries = [r["summary"] for r in results]
        assert "年报经验" in summaries

    def test_without_pdf_type(self, experience_store):
        experience_store.save_experience(
            summary="通用经验",
            category="workflow_tip",
            details="先诊断再修复",
            pdf_type="annual_report",
        )
        results = experience_store.get_relevant_experiences()
        assert isinstance(results, list)

    def test_empty_store(self, experience_store):
        results = experience_store.get_relevant_experiences(pdf_type="annual_report")
        assert results == []


class TestSearchExperiences:
    def test_keyword_search(self, experience_store):
        experience_store.save_experience(
            summary="年报解析推荐 pymupdf4llm",
            category="parser_selection",
            details="年报中表格密集，pymupdf4llm 表现好",
            pdf_type="annual_report",
        )
        experience_store.save_experience(
            summary="分块策略推荐 page_aware",
            category="chunk_strategy",
            details="page_aware 保留页面边界",
            pdf_type="research_report",
        )
        results = experience_store.search_experiences("pymupdf4llm")
        assert isinstance(results, list)

    def test_search_no_match(self, experience_store):
        experience_store.save_experience(
            summary="年报解析推荐",
            category="parser_selection",
            details="pymupdf4llm",
            pdf_type="annual_report",
        )
        results = experience_store.search_experiences("完全不相关的关键词xyz")
        assert isinstance(results, list)

    def test_search_limit(self, experience_store):
        for i in range(5):
            experience_store.save_experience(
                summary=f"经验{i}",
                category="workflow_tip",
                details=f"详情{i}",
            )
        results = experience_store.search_experiences("经验", limit=2)
        assert len(results) <= 2


class TestListExperiences:
    def test_list_all(self, experience_store):
        experience_store.save_experience(
            summary="经验1",
            category="parser_selection",
            details="详情1",
            pdf_type="annual_report",
        )
        experience_store.save_experience(
            summary="经验2",
            category="chunk_strategy",
            details="详情2",
            pdf_type="research_report",
        )
        results = experience_store.list_experiences()
        assert len(results) >= 2
        for item in results:
            assert "namespace" in item
            assert "key" in item
            assert "value" in item

    def test_list_with_pdf_type_filter(self, experience_store):
        experience_store.save_experience(
            summary="年报经验",
            category="parser_selection",
            details="详情",
            pdf_type="annual_report",
        )
        experience_store.save_experience(
            summary="研报经验",
            category="chunk_strategy",
            details="详情",
            pdf_type="research_report",
        )
        results = experience_store.list_experiences(pdf_type="annual_report")
        assert len(results) >= 1
        for item in results:
            assert item["value"]["pdf_type"] == "annual_report"

    def test_list_with_limit(self, experience_store):
        for i in range(5):
            experience_store.save_experience(
                summary=f"经验{i}",
                category="workflow_tip",
                details=f"详情{i}",
            )
        results = experience_store.list_experiences(limit=3)
        assert len(results) <= 3

    def test_list_empty(self, experience_store):
        results = experience_store.list_experiences()
        assert results == []


class TestDeleteExperience:
    def test_delete_existing(self, experience_store, store):
        key = experience_store.save_experience(
            summary="待删除",
            category="other",
            details="将被删除",
        )
        ns = ("maintenance", "experience", "generic")
        experience_store.delete_experience(ns, key)
        item = store.get(ns, key)
        assert item is None

    def test_delete_nonexistent_no_raise(self, experience_store):
        ns = ("maintenance", "experience", "generic")
        experience_store.delete_experience(ns, "exp_nonexistent")


class TestGetAllExperiences:
    def test_returns_all_in_namespace(self, experience_store):
        experience_store.save_experience(
            summary="经验A",
            category="parser_selection",
            details="详情A",
            pdf_type="annual_report",
        )
        experience_store.save_experience(
            summary="经验B",
            category="chunk_strategy",
            details="详情B",
            pdf_type="annual_report",
        )
        ns = ("maintenance", "experience", "annual_report")
        results = experience_store.get_all_experiences(ns)
        assert len(results) == 2
        summaries = [r["summary"] for r in results]
        assert "经验A" in summaries
        assert "经验B" in summaries

    def test_empty_namespace(self, experience_store):
        ns = ("maintenance", "experience", "nonexistent")
        results = experience_store.get_all_experiences(ns)
        assert results == []


class TestMigrateFromJson:
    def test_migrate_valid_json(self, store, tmp_path):
        json_path = tmp_path / "experiences.json"
        data = {
            "namespaces": {
                "maintenance/experience/annual_report": [
                    {
                        "_store_key": "exp_migrated_001",
                        "summary": "年报经验",
                        "category": "parser_selection",
                        "details": "pymupdf4llm 适合年报",
                    }
                ]
            }
        }
        json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        ExperienceStore._migrate_from_json(store, json_path)

        ns = ("maintenance", "experience", "annual_report")
        item = store.get(ns, "exp_migrated_001")
        assert item is not None
        assert item.value["summary"] == "年报经验"
        assert "_store_key" not in item.value

        migrated_path = tmp_path / "experiences.json.migrated"
        assert migrated_path.exists()
        assert not json_path.exists()

    def test_migrate_json_without_store_key(self, store, tmp_path):
        json_path = tmp_path / "experiences.json"
        data = {
            "namespaces": {
                "maintenance/experience/generic": [
                    {"summary": "无key经验", "category": "other", "details": "测试"}
                ]
            }
        }
        json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        ExperienceStore._migrate_from_json(store, json_path)

        ns = ("maintenance", "experience", "generic")
        items = store.search(ns)
        assert len(items) >= 1

    def test_migrate_nonexistent_file(self, store, tmp_path):
        json_path = tmp_path / "nonexistent.json"
        ExperienceStore._migrate_from_json(store, json_path)

    def test_migrate_invalid_json(self, store, tmp_path):
        json_path = tmp_path / "bad.json"
        json_path.write_text("not valid json {{{", encoding="utf-8")
        ExperienceStore._migrate_from_json(store, json_path)

    def test_migrate_multiple_namespaces(self, store, tmp_path):
        json_path = tmp_path / "multi.json"
        data = {
            "namespaces": {
                "maintenance/experience/annual_report": [
                    {
                        "summary": "年报经验1",
                        "category": "parser_selection",
                        "details": "d1",
                    },
                    {
                        "summary": "年报经验2",
                        "category": "chunk_strategy",
                        "details": "d2",
                    },
                ],
                "maintenance/experience/research_report": [
                    {
                        "summary": "研报经验1",
                        "category": "workflow_tip",
                        "details": "d3",
                    },
                ],
            }
        }
        json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        ExperienceStore._migrate_from_json(store, json_path)

        ns_ar = ("maintenance", "experience", "annual_report")
        ns_rr = ("maintenance", "experience", "research_report")
        ar_items = store.search(ns_ar)
        rr_items = store.search(ns_rr)
        assert len(ar_items) == 2
        assert len(rr_items) == 1
