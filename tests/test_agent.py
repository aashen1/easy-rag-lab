from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agent.state import MaintenanceState
from src.agent.tool_registry import FORBIDDEN_OPERATIONS, HIGH_RISK_TOOLS

pytestmark = pytest.mark.agent


@pytest.fixture
def mock_config():
    return {
        "llm": {
            "api_key": "test-key",
            "base_url": "https://api.test.com",
            "model": "claude-sonnet-4-20250514",
        },
        "meal": {"data_dir": "data/meals"},
        "index": {"persist_dir": "data/index"},
    }


class TestHighRiskTools:
    def test_high_risk_tools_set(self):
        assert "rebuild_index" in HIGH_RISK_TOOLS
        assert "delete_source" in HIGH_RISK_TOOLS
        assert "update_meal" in HIGH_RISK_TOOLS
        assert "delete_and_reindex_tool" in HIGH_RISK_TOOLS

    def test_safe_tools_not_in_high_risk(self):
        assert "list_meals" not in HIGH_RISK_TOOLS
        assert "get_meal_detail" not in HIGH_RISK_TOOLS
        assert "query_rag_tool" not in HIGH_RISK_TOOLS


class TestForbiddenOperations:
    def test_forbidden_operations_set(self):
        assert "delete_collection" in FORBIDDEN_OPERATIONS
        assert "drop_collection" in FORBIDDEN_OPERATIONS
        assert "delete_all" in FORBIDDEN_OPERATIONS
        assert "drop_all" in FORBIDDEN_OPERATIONS
        assert "delete_meal" in FORBIDDEN_OPERATIONS
        assert "remove_meal" in FORBIDDEN_OPERATIONS

    def test_forbidden_not_in_high_risk(self):
        for op in FORBIDDEN_OPERATIONS:
            assert op not in HIGH_RISK_TOOLS


class TestToolFunctions:
    @pytest.mark.parametrize(
        "tool_name,expected_description",
        [
            ("list_meals", "List all available meals"),
            ("get_meal_detail", None),
            ("query_rag_tool", None),
            ("parse_pdf_tool", None),
            ("enhance_page_tool", None),
            ("chunk_parsed_tool", None),
            ("evaluate_answer_tool", None),
            ("get_index_info", None),
        ],
    )
    def test_tool_exists(self, tool_name, expected_description):
        from src.agent.tools import (
            chunk_parsed_tool,
            enhance_page_tool,
            evaluate_answer_tool,
            get_index_info,
            get_meal_detail,
            list_meals,
            parse_pdf_tool,
            query_rag_tool,
        )

        tools_map = {
            "list_meals": list_meals,
            "get_meal_detail": get_meal_detail,
            "query_rag_tool": query_rag_tool,
            "parse_pdf_tool": parse_pdf_tool,
            "enhance_page_tool": enhance_page_tool,
            "chunk_parsed_tool": chunk_parsed_tool,
            "evaluate_answer_tool": evaluate_answer_tool,
            "get_index_info": get_index_info,
        }
        tool = tools_map[tool_name]
        assert tool.name == tool_name
        if expected_description:
            assert expected_description in tool.description

    def test_list_meals_error_handling(self):
        from src.agent.tools import list_meals

        result = list_meals.invoke({})
        assert "Error" in result or isinstance(json.loads(result), list)

    def test_get_meal_detail_error_handling(self):
        from src.agent.tools import get_meal_detail

        result = get_meal_detail.invoke({"meal_name": "nonexistent"})
        assert isinstance(result, str)


class TestGraphBuild:
    def test_build_graph(self):
        from src.agent.graph import build_graph

        graph = build_graph()
        assert "agent" in graph.nodes
        assert "approval" in graph.nodes
        assert "tools" in graph.nodes

    def test_compile_agent(self):
        from src.agent.graph import compile_agent

        agent = compile_agent()
        assert agent is not None

    def test_compile_agent_with_checkpointer(self):
        from langgraph.checkpoint.memory import MemorySaver

        from src.agent.graph import compile_agent

        checkpointer = MemorySaver()
        agent = compile_agent(checkpointer=checkpointer)
        assert agent is not None


class TestShouldContinue:
    def test_routes_to_tools_when_tool_calls(self):
        from langchain_core.messages import AIMessage

        from src.agent.graph import should_continue

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "list_meals", "args": {}, "id": "1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        assert should_continue(state) == "tools"

    def test_routes_to_end_when_no_tool_calls(self):
        from langchain_core.messages import AIMessage

        from src.agent.graph import should_continue

        state = MaintenanceState(
            messages=[AIMessage(content="I'll help you with that.")],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        assert should_continue(state) == "__end__"


class TestToolNode:
    def test_tool_node_handles_unknown_tool(self):
        from langchain_core.messages import AIMessage, ToolMessage

        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "nonexistent_tool", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        result = tool_node(state)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], ToolMessage)
        assert "Unknown tool" in result["messages"][0].content


class TestSystemPrompt:
    def test_prompt_contains_workflow(self):
        from src.agent.prompt import SYSTEM_PROMPT

        assert "诊断" in SYSTEM_PROMPT
        assert "修复" in SYSTEM_PROMPT
        assert "高风险" in SYSTEM_PROMPT

    def test_prompt_mentions_risk_tools(self):
        from src.agent.prompt import SYSTEM_PROMPT

        assert "rebuild_index" in SYSTEM_PROMPT
        assert "delete_source" in SYSTEM_PROMPT
        assert "update_meal" in SYSTEM_PROMPT


class TestBackupToTrashbin:
    def test_backup_file(self, tmp_path):
        from src.agent.tools import _backup_to_trashbin

        src = tmp_path / "test.json"
        src.write_text('{"key": "value"}')

        result = _backup_to_trashbin(src, "test_file")

        assert result is not None
        assert "test_file" in result
        assert ".trashbin" in result

    def test_backup_directory(self, tmp_path):
        from src.agent.tools import _backup_to_trashbin

        src_dir = tmp_path / "test_dir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("content")

        result = _backup_to_trashbin(src_dir, "test_dir")

        assert result is not None
        assert "test_dir" in result

    def test_backup_nonexistent_path(self):
        from src.agent.tools import _backup_to_trashbin

        result = _backup_to_trashbin(Path("/nonexistent/path"), "test")
        assert result is None


class TestScrollBySource:
    def test_scroll_by_source_returns_points(self):
        from unittest.mock import MagicMock, patch

        from src.indexer import VectorIndexer

        with patch.object(VectorIndexer, "__init__", lambda self, *a, **kw: None):
            indexer = VectorIndexer.__new__(VectorIndexer)
            indexer.client = MagicMock()
            indexer.collection_name = "test_collection"
            mock_record = MagicMock()
            mock_record.id = "point1"
            mock_record.payload = {"metadata": {"source": "test.pdf"}}
            indexer.client.scroll.return_value = ([mock_record], None)

            result = indexer.scroll_by_source("test.pdf")
            assert len(result) == 1
            assert result[0]["id"] == "point1"
            assert result[0]["payload"] == {"metadata": {"source": "test.pdf"}}

    def test_scroll_by_source_empty(self):
        from unittest.mock import MagicMock, patch

        from src.indexer import VectorIndexer

        with patch.object(VectorIndexer, "__init__", lambda self, *a, **kw: None):
            indexer = VectorIndexer.__new__(VectorIndexer)
            indexer.client = MagicMock()
            indexer.collection_name = "test_collection"
            indexer.client.scroll.return_value = ([], None)

            result = indexer.scroll_by_source("nonexistent.pdf")
            assert result == []


class TestDeleteSourceBackup:
    def test_delete_source_creates_backup(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from src.agent.tools import delete_source

        mock_indexer = MagicMock()
        mock_indexer.scroll_by_source.return_value = [
            {"id": "p1", "payload": {"metadata": {"source": "test.pdf"}}}
        ]
        mock_indexer.delete_by_source.return_value = 1

        mock_pipeline = MagicMock()
        mock_pipeline.indexer = mock_indexer

        with (
            patch("src.pipeline.RAGPipeline", return_value=mock_pipeline),
            patch("src.agent.tools.Path") as mock_path_cls,
        ):
            mock_path_cls.return_value = tmp_path / ".trashbin"
            result = delete_source.invoke({"meal_name": "test", "source": "test.pdf"})

        assert "backup_path" in result or "deleted" in result


class TestParseExceptionHandling:
    def test_parse_pdf_logs_and_reraises(self):
        from unittest.mock import patch

        from src.core.ops.parse import parse_pdf

        with (
            patch("src.core.ops.parse.Path.exists", return_value=True),
            patch(
                "src.core.ops.parse.ParserRegistry.get_composite",
                side_effect=RuntimeError("parser crash"),
            ),
            pytest.raises(RuntimeError, match="parser crash"),
        ):
            parse_pdf(
                "dummy.pdf", parser_name="pymupdf4llm", enhancer_name="pdfplumber"
            )

    def test_enhance_page_logs_and_reraises(self):
        from unittest.mock import patch

        from src.core.ops.parse import enhance_page

        with (
            patch("src.core.ops.parse.Path.exists", return_value=True),
            patch(
                "src.core.ops.parse.ParserRegistry.get_enhancer",
                side_effect=RuntimeError("enhancer crash"),
            ),
            pytest.raises(RuntimeError, match="enhancer crash"),
        ):
            enhance_page("dummy.pdf", 1, "text", enhancer_name="pdfplumber")

    def test_enhance_table_logs_and_reraises(self):
        from unittest.mock import patch

        from src.core.ops.parse import enhance_table

        with (
            patch("src.core.ops.parse.Path.exists", return_value=True),
            patch(
                "src.core.ops.parse.ParserRegistry.get_enhancer",
                side_effect=RuntimeError("enhancer crash"),
            ),
            pytest.raises(RuntimeError, match="enhancer crash"),
        ):
            enhance_table("dummy.pdf", 1, 1, "text", enhancer_name="pdfplumber")


class TestAgentConfig:
    def test_get_agent_default_returns_configured_value(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config, get_agent_default

        get_agent_config.cache_clear()
        with patch(
            "src.utils.load_config",
            return_value={"agent": {"defaults": {"parser_name": "fitz"}}},
        ):
            assert get_agent_default("parser_name", "pymupdf4llm") == "fitz"

    def test_get_agent_default_returns_fallback(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config, get_agent_default

        get_agent_config.cache_clear()
        with patch("src.utils.load_config", return_value={}):
            assert get_agent_default("parser_name", "pymupdf4llm") == "pymupdf4llm"

    def test_get_agent_config_returns_section(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config

        get_agent_config.cache_clear()
        with patch(
            "src.utils.load_config",
            return_value={"agent": {"defaults": {"chunk_size": 1024}}},
        ):
            result = get_agent_config()
            assert result == {"defaults": {"chunk_size": 1024}}


class TestNewTools:
    @pytest.mark.parametrize(
        "tool_name",
        [
            "embed_chunks_tool",
            "index_chunks_tool",
            "delete_and_reindex_tool",
            "create_curated_meal",
            "list_pdfs",
            "create_issue",
            "list_issues",
            "close_issue",
        ],
    )
    def test_tool_exists(self, tool_name):
        from src.agent.tools import (
            close_issue,
            create_curated_meal,
            create_issue,
            delete_and_reindex_tool,
            embed_chunks_tool,
            index_chunks_tool,
            list_issues,
            list_pdfs,
        )

        tools_map = {
            "embed_chunks_tool": embed_chunks_tool,
            "index_chunks_tool": index_chunks_tool,
            "delete_and_reindex_tool": delete_and_reindex_tool,
            "create_curated_meal": create_curated_meal,
            "list_pdfs": list_pdfs,
            "create_issue": create_issue,
            "list_issues": list_issues,
            "close_issue": close_issue,
        }
        tool = tools_map[tool_name]
        assert tool.name == tool_name

    def test_delete_and_reindex_is_high_risk(self):
        from src.agent.tool_registry import HIGH_RISK_TOOLS

        assert "delete_and_reindex_tool" in HIGH_RISK_TOOLS

    @pytest.mark.parametrize(
        "tool_name,invoke_args,expected_in_result",
        [
            (
                "create_issue",
                {"title": "Test bug", "issue_type": "bug", "priority": "high"},
                "created",
            ),
            ("list_issues", {"status": "todo"}, "ok"),
            ("close_issue", {"issue_id": "BUG-20260504-001-wt1"}, "closed"),
        ],
    )
    def test_issue_tools_with_mock_subprocess(
        self, tool_name, invoke_args, expected_in_result
    ):
        from unittest.mock import MagicMock, patch

        from src.agent.tools import close_issue, create_issue, list_issues

        tools_map = {
            "create_issue": create_issue,
            "list_issues": list_issues,
            "close_issue": close_issue,
        }
        tool = tools_map[tool_name]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            f"✓ Issue {expected_in_result} successfully!"
            if expected_in_result != "ok"
            else "No issues found."
        )
        mock_result.stderr = ""

        with patch("src.agent.tools.subprocess.run", return_value=mock_result):
            result = tool.invoke(invoke_args)
            assert expected_in_result in result

    def test_get_tools_returns_all_22_tools(self):
        from src.agent.graph import _get_tools

        _get_tools.cache_clear()
        tools = _get_tools()
        assert len(tools) == 22
        tool_names = {t.name for t in tools}
        assert "embed_chunks_tool" in tool_names
        assert "index_chunks_tool" in tool_names
        assert "delete_and_reindex_tool" in tool_names
        assert "create_curated_meal" in tool_names
        assert "list_pdfs" in tool_names
        assert "create_issue" in tool_names
        assert "list_issues" in tool_names
        assert "close_issue" in tool_names
        _get_tools.cache_clear()


class TestToolNodeStageHistory:
    def test_tool_node_updates_stage_history(self):
        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["parse_pdf_tool"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        result = tool_node(state)
        assert "parse_pdf_tool" in result["stage_history"]
        assert "list_meals" in result["stage_history"]


class TestBuildSystemPrompt:
    @pytest.mark.parametrize(
        "expected_substring",
        [
            "诊断",
            "修复",
            "工具选择示例",
            "解析器选择",
            "分块策略选择",
            "约束规则",
            "不要连续调用同一工具超过 3 次",
            "错误处理指导",
            "先分析错误原因",
            "Issue",
            "回退",
        ],
    )
    def test_base_prompt_contains_expected_strings(self, expected_substring):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert expected_substring in prompt

    def test_prompt_with_stage_history(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt(
            stage_history=["parse_pdf_tool", "chunk_parsed_tool"]
        )
        assert "已执行步骤" in prompt
        assert "parse_pdf_tool" in prompt
        assert "chunk_parsed_tool" in prompt

    def test_prompt_with_experiences(self):
        from src.agent.prompt import build_system_prompt

        experiences = [
            {
                "pdf_type": "年报",
                "best_parser": "pymupdf4llm+pdfplumber",
                "best_chunk_strategy": "page_aware",
                "best_chunk_size": 512,
                "reason": "年报表格多",
            }
        ]
        prompt = build_system_prompt(experiences=experiences)
        assert "历史经验推荐" in prompt
        assert "年报" in prompt
        assert "pymupdf4llm+pdfplumber" in prompt

    def test_prompt_without_optional_sections(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "已执行步骤" not in prompt

    def test_system_prompt_backward_compat(self):
        from src.agent.prompt import SYSTEM_PROMPT

        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100


class TestExperienceStore:
    def test_save_experience_new_api(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        key = exp_store.save_experience(
            summary="test summary",
            category="tool_execution",
            details="some details",
            pdf_type="annual_report",
        )
        assert key.startswith("exp_")

    def test_get_relevant_experiences(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        exp_store.save_experience(
            summary="test",
            category="tool_execution",
            details="details",
            pdf_type="annual_report",
        )
        results = exp_store.get_relevant_experiences(pdf_type="annual_report")
        assert len(results) >= 1

    def test_get_relevant_experiences_empty(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        results = exp_store.get_relevant_experiences(pdf_type="nonexistent")
        assert results == []

    def test_save_experience_includes_timestamp(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        exp_store.save_experience(
            summary="test",
            pdf_type="annual_report",
        )
        results = exp_store.get_relevant_experiences(pdf_type="annual_report")
        assert "timestamp" in results[0]

    def test_list_experiences(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        exp_store.save_experience(
            summary="test",
            category="tool_execution",
            pdf_type="annual_report",
        )
        results = exp_store.list_experiences(pdf_type="annual_report")
        assert len(results) >= 1
        assert "namespace" in results[0]
        assert "key" in results[0]
        assert "value" in results[0]

    def test_delete_experience(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        key = exp_store.save_experience(
            summary="to delete",
            pdf_type="annual_report",
        )
        ns = ExperienceStore.NAMESPACE_PREFIX + ("annual_report",)
        exp_store.delete_experience(ns, key)
        results = exp_store.get_relevant_experiences(pdf_type="annual_report")
        assert all(r.get("summary") != "to delete" for r in results)

    def test_namespace_prefix_constant(self):
        from src.agent.memory.experience_store import ExperienceStore

        assert ExperienceStore.NAMESPACE_PREFIX == ("maintenance", "experience")


class TestExperienceStoreSqlitePersistence:
    def test_save_and_reload_sqlite(self, tmp_path):
        import sqlite3

        from langgraph.store.sqlite import SqliteStore

        from src.agent.memory.experience_store import ExperienceStore

        db_path = tmp_path / "experience.db"
        conn1 = sqlite3.connect(str(db_path))
        conn1.autocommit = True
        store1 = SqliteStore(conn1)
        store1.setup()
        exp_store1 = ExperienceStore(store1)
        exp_store1.save_experience(
            summary="test summary",
            category="tool_execution",
            details="best_parser=pymupdf4llm+pdfplumber",
            pdf_type="annual_report",
        )
        conn1.close()

        conn2 = sqlite3.connect(str(db_path))
        conn2.autocommit = True
        store2 = SqliteStore(conn2)
        store2.setup()
        exp_store2 = ExperienceStore(store2)
        results = exp_store2.get_relevant_experiences(pdf_type="annual_report")
        assert len(results) >= 1
        assert results[0]["summary"] == "test summary"
        conn2.close()

    def test_migrate_from_json(self, tmp_path):
        import json
        import sqlite3

        from langgraph.store.sqlite import SqliteStore

        from src.agent.memory.experience_store import ExperienceStore

        json_path = tmp_path / "experience.json"
        data = {
            "namespaces": {
                "default/maintenance_experience/annual_report": [
                    {
                        "pdf_type": "annual_report",
                        "best_parser": "pymupdf4llm+pdfplumber",
                        "_store_key": "exp_legacy_001",
                    }
                ]
            }
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        db_path = tmp_path / "experience.db"
        conn = sqlite3.connect(str(db_path))
        conn.autocommit = True
        store = SqliteStore(conn)
        store.setup()

        ExperienceStore._migrate_from_json(store, json_path)

        exp_store = ExperienceStore(store)
        results = exp_store.get_all_experiences(
            ("default", "maintenance_experience", "annual_report")
        )
        assert len(results) >= 1
        assert results[0]["best_parser"] == "pymupdf4llm+pdfplumber"
        assert "_store_key" not in results[0]

        assert json_path.with_suffix(".json.migrated").exists()
        assert not json_path.exists()
        conn.close()

    def test_migrate_from_json_no_file(self, tmp_path):
        import sqlite3

        from langgraph.store.sqlite import SqliteStore

        from src.agent.memory.experience_store import ExperienceStore

        json_path = tmp_path / "nonexistent.json"
        db_path = tmp_path / "experience.db"
        conn = sqlite3.connect(str(db_path))
        conn.autocommit = True
        store = SqliteStore(conn)
        store.setup()

        ExperienceStore._migrate_from_json(store, json_path)
        conn.close()


class TestCompileAgentWithStore:
    def test_compile_agent_with_store(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.graph import compile_agent

        store = InMemoryStore()
        agent = compile_agent(store=store)
        assert agent is not None

    def test_compile_agent_without_store(self):
        from src.agent.graph import compile_agent

        agent = compile_agent()
        assert agent is not None


class TestInferPdfType:
    def test_annual_report(self):
        from src.agent.graph import _infer_pdf_type

        assert _infer_pdf_type("2025年报.pdf") == "annual_report"
        assert _infer_pdf_type("annual_report_2025.pdf") == "annual_report"

    def test_research_report(self):
        from src.agent.graph import _infer_pdf_type

        assert _infer_pdf_type("行业研报.pdf") == "research_report"
        assert _infer_pdf_type("research_q1.pdf") == "research_report"

    def test_generic(self):
        from src.agent.graph import _infer_pdf_type

        assert _infer_pdf_type("document.pdf") == "generic"


class TestAutoReviewInterrupt:
    def test_auto_review_interrupts_on_parse_tool(self):
        from unittest.mock import patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "parse_pdf_tool",
                            "args": {"pdf_path": "test.pdf"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=True,
            locked_tool=None,
            locked_tool_args=None,
        )
        with patch("src.agent.graph.interrupt") as mock_interrupt:
            tool_node(state)
            mock_interrupt.assert_called_once()

    def test_auto_review_no_interrupt_for_other_tools(self):
        from unittest.mock import patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=True,
            locked_tool=None,
            locked_tool_args=None,
        )
        with patch("src.agent.graph.interrupt") as mock_interrupt:
            tool_node(state)
            mock_interrupt.assert_not_called()

    def test_no_interrupt_when_auto_review_off(self):
        from unittest.mock import patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "parse_pdf_tool",
                            "args": {"pdf_path": "test.pdf"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        with patch("src.agent.graph.interrupt") as mock_interrupt:
            tool_node(state)
            mock_interrupt.assert_not_called()


class TestAgentNodeExperienceRetrieval:
    def test_agent_node_retrieves_experiences(self):
        from unittest.mock import MagicMock, patch

        from langgraph.store.memory import InMemoryStore

        from src.agent.graph import agent_node
        from src.agent.state import MaintenanceState

        store = InMemoryStore()

        from src.agent.memory.experience_store import ExperienceStore

        exp_store = ExperienceStore(store)
        exp_store.save_experience(
            summary="test",
            category="tool_execution",
            details="best_parser=pymupdf4llm+pdfplumber",
            pdf_type="annual_report",
        )

        state = MaintenanceState(
            messages=[{"role": "user", "content": "test"}],
            current_meal=None,
            current_source="2025年报.pdf",
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
        )

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "test response"
        mock_llm.bind_tools.return_value.invoke.return_value = mock_response

        with (
            patch("src.agent.graph._get_llm", return_value=mock_llm),
            patch("src.agent.graph._get_tools", return_value=[]),
        ):
            result = agent_node(state, store=store)
            assert "messages" in result


class TestCLIReviewCommand:
    def test_review_on_not_handled_by_cli_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":review on", False)
        assert result is None

    def test_review_off_not_handled_by_cli_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":review off", False)
        assert result is None


class TestLockedTool:
    def test_locked_tool_skips_llm(self):
        from langchain_core.messages import AIMessage

        from src.agent.graph import agent_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[{"role": "user", "content": "test"}],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool="parse_pdf_tool",
            locked_tool_args={"pdf_path": "test.pdf"},
        )
        result = agent_node(state)
        assert len(result["messages"]) == 1
        ai_msg = result["messages"][0]
        assert isinstance(ai_msg, AIMessage)
        assert len(ai_msg.tool_calls) == 1
        assert ai_msg.tool_calls[0]["name"] == "parse_pdf_tool"
        assert ai_msg.tool_calls[0]["args"] == {"pdf_path": "test.pdf"}
        assert result["locked_tool"] is None
        assert result["locked_tool_args"] is None

    def test_no_locked_tool_calls_llm(self):
        from unittest.mock import MagicMock, patch

        from src.agent.graph import agent_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[{"role": "user", "content": "test"}],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "test response"
        mock_llm.bind_tools.return_value.invoke.return_value = mock_response

        with (
            patch("src.agent.graph._get_llm", return_value=mock_llm),
            patch("src.agent.graph._get_tools", return_value=[]),
        ):
            result = agent_node(state)
            assert "messages" in result
            mock_llm.bind_tools.return_value.invoke.assert_called_once()

    def test_state_has_locked_tool_fields(self):
        state = MaintenanceState(
            messages=[],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool="list_meals",
            locked_tool_args=None,
        )
        assert state["locked_tool"] == "list_meals"
        assert state["locked_tool_args"] is None


class TestCLICommands:
    @pytest.mark.parametrize(
        "command,expected",
        [
            (":parse pymupdf4llm", "请用 pymupdf4llm 解析当前 PDF"),
            (":back chunk", "回到chunk阶段重新做"),
            (":compare", "生成对比报告"),
            (":report", "生成维修报告"),
            (":history", "__show_history__"),
            (":status", "__show_status__"),
            ("hello", None),
            (":unknown", None),
            (":mode", "__set_mode__"),
        ],
    )
    def test_cli_commands(self, command, expected):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(command, False)
        assert result == expected


class TestDeleteCountSafety:
    def test_state_has_delete_count_field(self):
        state = MaintenanceState(
            messages=[],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        assert state["delete_count"] == 0
        assert state["mode"] == "light"

    def test_delete_count_increments(self):
        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_source",
                            "args": {"source": "test.pdf"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["list_meals", "get_index_info"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "delete_source"
            mock_tool.invoke.return_value = "Deleted test.pdf"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        assert result["delete_count"] == 1

    def test_delete_count_accumulates(self):
        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_source",
                            "args": {"source": "a.pdf"},
                            "id": "tc1",
                        },
                        {
                            "name": "delete_source",
                            "args": {"source": "b.pdf"},
                            "id": "tc2",
                        },
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["list_meals"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=1,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "delete_source"
            mock_tool.invoke.return_value = "Deleted"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        assert result["delete_count"] == 3


class TestStageGuard:
    def test_repair_blocked_without_diagnosis(self):
        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "rebuild_index", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "rebuild_index"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        assert any("被拒绝" in str(m.content) for m in result["messages"])
        log_data = json.loads(result["execution_log"][-1])
        assert log_data["status"] == "blocked"
        assert log_data["tool"] == "rebuild_index"

    def test_repair_allowed_after_diagnosis(self):
        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "rebuild_index", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["list_meals", "get_index_info"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "rebuild_index"
            mock_tool.invoke.return_value = "Index rebuilt"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        assert not any("被拒绝" in str(m.content) for m in result["messages"])

    def test_delete_source_blocked_without_diagnosis(self):
        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_source",
                            "args": {"source": "test.pdf"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "delete_source"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        assert any("被拒绝" in str(m.content) for m in result["messages"])

    def test_diagnosis_tools_not_blocked(self):
        from src.agent.tool_registry import DIAGNOSIS_TOOLS

        assert "list_meals" in DIAGNOSIS_TOOLS
        assert "get_meal_detail" in DIAGNOSIS_TOOLS
        assert "query_rag_tool" in DIAGNOSIS_TOOLS
        assert "get_index_info" in DIAGNOSIS_TOOLS
        assert "evaluate_answer_tool" in DIAGNOSIS_TOOLS


class TestModePrompt:
    def test_light_mode_prompt(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt(mode="light")
        assert "轻量模式" in prompt
        assert "仅处理用户指定的 1-2 个 PDF" in prompt

    def test_full_mode_prompt(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt(mode="full")
        assert "全量模式" in prompt
        assert "Meal 批量体系" in prompt

    def test_default_mode_is_light(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "轻量模式" in prompt


class TestReportToolStateInjection:
    def test_report_tool_auto_fills_state(self):
        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "generate_maintenance_report_tool",
                            "args": {"session_id": "test-session"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal="test_meal",
            current_source="test.pdf",
            diagnosis=[{"issue": "bad chunk"}],
            pending_action=None,
            approved=None,
            execution_log=[
                json.dumps(
                    {
                        "tool": "list_meals",
                        "time": "2026-05-05T10:00:00",
                        "status": "ok",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "tool": "rebuild_index",
                        "time": "2026-05-05T10:01:00",
                        "status": "ok",
                    },
                    ensure_ascii=False,
                ),
            ],
            stage_history=["list_meals", "get_index_info"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "generate_maintenance_report_tool"
            mock_tool.invoke.return_value = '{"status": "generated"}'
            mock_tools.return_value = [mock_tool]
            tool_node(state)
        call_args = mock_tool.invoke.call_args[0][0]
        assert call_args["current_meal"] == "test_meal"
        assert call_args["current_source"] == "test.pdf"
        assert call_args["execution_log"] == [
            json.dumps(
                {"tool": "list_meals", "time": "2026-05-05T10:00:00", "status": "ok"},
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "tool": "rebuild_index",
                    "time": "2026-05-05T10:01:00",
                    "status": "ok",
                },
                ensure_ascii=False,
            ),
        ]
        assert call_args["stage_history"] == ["list_meals", "get_index_info"]
        assert call_args["diagnosis"] == [{"issue": "bad chunk"}]

    def test_report_tool_preserves_explicit_args(self):
        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "generate_maintenance_report_tool",
                            "args": {
                                "session_id": "test-session",
                                "current_meal": "explicit_meal",
                            },
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal="state_meal",
            current_source="test.pdf",
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["list_meals"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "generate_maintenance_report_tool"
            mock_tool.invoke.return_value = '{"status": "generated"}'
            mock_tools.return_value = [mock_tool]
            tool_node(state)
        call_args = mock_tool.invoke.call_args[0][0]
        assert call_args["current_meal"] == "explicit_meal"


class TestDeleteCountHardBlock:
    def test_delete_source_hard_blocked_at_threshold(self):
        from langchain_core.messages import AIMessage, ToolMessage

        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_source",
                            "args": {"source": "test.pdf"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["list_meals"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=3,
            mode="light",
        )
        with (
            patch("src.agent.graph._get_tools") as mock_tools,
            patch("src.agent.graph.interrupt") as mock_interrupt,
        ):
            mock_tool = MagicMock()
            mock_tool.name = "delete_source"
            mock_tool.invoke.return_value = "Deleted"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        mock_interrupt.assert_not_called()
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], ToolMessage)
        assert "防止误操作" in result["messages"][0].content
        assert "3" in result["messages"][0].content
        assert result["delete_count"] == 3
        assert "delete_source" not in result["stage_history"]
        assert any(
            json.loads(e).get("status") == "blocked" for e in result["execution_log"]
        )

    def test_delete_source_interrupt_below_threshold(self):
        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_source",
                            "args": {"source": "test.pdf"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["list_meals"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=1,
            mode="light",
        )
        with (
            patch("src.agent.graph._get_tools") as mock_tools,
            patch("src.agent.graph.interrupt") as mock_interrupt,
        ):
            mock_tool = MagicMock()
            mock_tool.name = "delete_source"
            mock_tool.invoke.return_value = "Deleted"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        mock_interrupt.assert_not_called()
        assert result["delete_count"] == 2
        assert "delete_source" in result["stage_history"]


class TestFullModeBehavior:
    def test_full_mode_higher_delete_threshold(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config, get_delete_count_threshold

        get_agent_config.cache_clear()
        with patch(
            "src.utils.load_config",
            return_value={
                "agent": {
                    "delete_count_threshold": 3,
                    "full_mode_delete_threshold": 10,
                }
            },
        ):
            assert get_delete_count_threshold(mode="full") == 10
        get_agent_config.cache_clear()

    def test_light_mode_delete_threshold(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config, get_delete_count_threshold

        get_agent_config.cache_clear()
        with patch(
            "src.utils.load_config",
            return_value={
                "agent": {
                    "delete_count_threshold": 3,
                    "full_mode_delete_threshold": 10,
                }
            },
        ):
            assert get_delete_count_threshold(mode="light") == 3
        get_agent_config.cache_clear()

    def test_full_mode_prompt_has_batch_guidance(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt(mode="full")
        assert "批量操作指导" in prompt

    def test_light_mode_no_batch_guidance(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt(mode="light")
        assert "批量操作指导" not in prompt


class TestExecutionLogJsonFormat:
    def test_tool_success_log_is_valid_json(self):
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "list_meals"
            mock_tool.invoke.return_value = "[]"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        entry = result["execution_log"][-1]
        data = json.loads(entry)
        assert data["tool"] == "list_meals"
        assert data["status"] == "ok"
        assert "time" in data

    def test_tool_error_log_is_valid_json(self):
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "list_meals"
            mock_tool.invoke.side_effect = RuntimeError("connection failed")
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        entry = result["execution_log"][-1]
        data = json.loads(entry)
        assert data["tool"] == "list_meals"
        assert data["status"] == "error"
        assert "connection failed" in data["error"]
        assert "time" in data

    def test_guard_log_is_valid_json(self):
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "rebuild_index", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=0,
            mode="light",
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "rebuild_index"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        entry = result["execution_log"][-1]
        data = json.loads(entry)
        assert data["tool"] == "rebuild_index"
        assert data["status"] == "blocked"
        assert data["reason"] == "no diagnosis"
        assert "time" in data

    def test_blocked_log_is_valid_json(self):
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_source",
                            "args": {"source": "test.pdf"},
                            "id": "tc1",
                        }
                    ],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=["list_meals"],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
            delete_count=3,
            mode="light",
        )
        with (
            patch("src.agent.graph._get_tools") as mock_tools,
            patch("src.agent.graph.interrupt"),
        ):
            mock_tool = MagicMock()
            mock_tool.name = "delete_source"
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        entry = result["execution_log"][-1]
        data = json.loads(entry)
        assert data["tool"] == "delete_source"
        assert data["status"] == "blocked"
        assert "delete count" in data["reason"]
        assert "time" in data

    def test_error_truncated_to_200_chars(self):
        from unittest.mock import MagicMock, patch

        from langchain_core.messages import AIMessage

        from src.agent.graph import tool_node
        from src.agent.state import MaintenanceState

        long_error = "x" * 500
        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        with patch("src.agent.graph._get_tools") as mock_tools:
            mock_tool = MagicMock()
            mock_tool.name = "list_meals"
            mock_tool.invoke.side_effect = RuntimeError(long_error)
            mock_tools.return_value = [mock_tool]
            result = tool_node(state)
        entry = result["execution_log"][-1]
        data = json.loads(entry)
        assert len(data["error"]) <= 200
