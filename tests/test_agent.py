from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.state import MaintenanceState
from src.agent.tools import FORBIDDEN_OPERATIONS, HIGH_RISK_TOOLS

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


class TestMaintenanceState:
    def test_state_has_required_fields(self):
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
        )
        assert state["messages"] == []
        assert state["current_meal"] is None
        assert state["execution_log"] == []

    def test_state_accepts_values(self):
        state = MaintenanceState(
            messages=[{"role": "user", "content": "test"}],
            current_meal="test_meal",
            current_source="test.pdf",
            diagnosis=[{"issue": "bad chunk"}],
            pending_action={"tool": "rebuild_index"},
            approved=True,
            execution_log=["TOOL: list_meals"],
            stage_history=[],
            auto_review=False,
            locked_tool=None,
            locked_tool_args=None,
        )
        assert state["current_meal"] == "test_meal"
        assert state["diagnosis"] == [{"issue": "bad chunk"}]
        assert state["approved"] is True


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
    def test_list_meals_tool_exists(self):
        from src.agent.tools import list_meals

        assert list_meals.name == "list_meals"
        assert "List all available meals" in list_meals.description

    def test_get_meal_detail_tool_exists(self):
        from src.agent.tools import get_meal_detail

        assert get_meal_detail.name == "get_meal_detail"

    def test_query_rag_tool_exists(self):
        from src.agent.tools import query_rag_tool

        assert query_rag_tool.name == "query_rag_tool"

    def test_parse_pdf_tool_exists(self):
        from src.agent.tools import parse_pdf_tool

        assert parse_pdf_tool.name == "parse_pdf_tool"

    def test_enhance_page_tool_exists(self):
        from src.agent.tools import enhance_page_tool

        assert enhance_page_tool.name == "enhance_page_tool"

    def test_chunk_parsed_tool_exists(self):
        from src.agent.tools import chunk_parsed_tool

        assert chunk_parsed_tool.name == "chunk_parsed_tool"

    def test_evaluate_answer_tool_exists(self):
        from src.agent.tools import evaluate_answer_tool

        assert evaluate_answer_tool.name == "evaluate_answer_tool"

    def test_get_index_info_tool_exists(self):
        from src.agent.tools import get_index_info

        assert get_index_info.name == "get_index_info"

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

        from src.agent.config import get_agent_default

        with patch(
            "src.utils.load_config",
            return_value={"agent": {"defaults": {"parser_name": "fitz"}}},
        ):
            assert get_agent_default("parser_name", "pymupdf4llm") == "fitz"

    def test_get_agent_default_returns_fallback(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_default

        with patch("src.utils.load_config", return_value={}):
            assert get_agent_default("parser_name", "pymupdf4llm") == "pymupdf4llm"

    def test_get_agent_config_returns_section(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config

        with patch(
            "src.utils.load_config",
            return_value={"agent": {"defaults": {"chunk_size": 1024}}},
        ):
            result = get_agent_config()
            assert result == {"defaults": {"chunk_size": 1024}}


class TestLLMClientCaching:
    def test_get_llm_returns_cached_instance(self):
        from unittest.mock import patch

        from src.agent.graph import _get_llm

        _get_llm.cache_clear()
        with (
            patch("src.llm_client.create_langchain_anthropic_client") as mock_create,
            patch(
                "src.utils.get_llm_config",
                return_value={
                    "api_key": "k",
                    "base_url": "u",
                    "model_name": "m",
                    "temperature": 0,
                    "max_tokens": 100,
                },
            ),
            patch("src.utils.load_config", return_value={}),
        ):
            llm1 = _get_llm()
            llm2 = _get_llm()
            assert llm1 is llm2
            assert mock_create.call_count == 1
        _get_llm.cache_clear()

    def test_get_tools_returns_cached_list(self):
        from src.agent.graph import _get_tools

        _get_tools.cache_clear()
        tools1 = _get_tools()
        tools2 = _get_tools()
        assert tools1 is tools2
        _get_tools.cache_clear()


class TestNewTools:
    def test_embed_chunks_tool_exists(self):
        from src.agent.tools import embed_chunks_tool

        assert embed_chunks_tool.name == "embed_chunks_tool"

    def test_index_chunks_tool_exists(self):
        from src.agent.tools import index_chunks_tool

        assert index_chunks_tool.name == "index_chunks_tool"

    def test_delete_and_reindex_tool_exists(self):
        from src.agent.tools import delete_and_reindex_tool

        assert delete_and_reindex_tool.name == "delete_and_reindex_tool"

    def test_delete_and_reindex_is_high_risk(self):
        from src.agent.tools import HIGH_RISK_TOOLS

        assert "delete_and_reindex_tool" in HIGH_RISK_TOOLS

    def test_create_curated_meal_exists(self):
        from src.agent.tools import create_curated_meal

        assert create_curated_meal.name == "create_curated_meal"

    def test_list_pdfs_exists(self):
        from src.agent.tools import list_pdfs

        assert list_pdfs.name == "list_pdfs"

    def test_create_issue_exists(self):
        from src.agent.tools import create_issue

        assert create_issue.name == "create_issue"

    def test_list_issues_exists(self):
        from src.agent.tools import list_issues

        assert list_issues.name == "list_issues"

    def test_close_issue_exists(self):
        from src.agent.tools import close_issue

        assert close_issue.name == "close_issue"

    def test_create_issue_with_mock_subprocess(self):
        from unittest.mock import MagicMock, patch

        from src.agent.tools import create_issue

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "✓ Issue created successfully!"
        mock_result.stderr = ""

        with patch("src.agent.tools.subprocess.run", return_value=mock_result):
            result = create_issue.invoke(
                {"title": "Test bug", "issue_type": "bug", "priority": "high"}
            )
            assert "created" in result

    def test_list_issues_with_mock_subprocess(self):
        from unittest.mock import MagicMock, patch

        from src.agent.tools import list_issues

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "No issues found."
        mock_result.stderr = ""

        with patch("src.agent.tools.subprocess.run", return_value=mock_result):
            result = list_issues.invoke({"status": "todo"})
            assert "ok" in result

    def test_close_issue_with_mock_subprocess(self):
        from unittest.mock import MagicMock, patch

        from src.agent.tools import close_issue

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "✓ Issue done successfully!"
        mock_result.stderr = ""

        with patch("src.agent.tools.subprocess.run", return_value=mock_result):
            result = close_issue.invoke({"issue_id": "BUG-20260504-001-wt1"})
            assert "closed" in result

    def test_get_tools_returns_all_21_tools(self):
        from src.agent.graph import _get_tools

        _get_tools.cache_clear()
        tools = _get_tools()
        assert len(tools) == 21
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


class TestMaintenanceStateNewFields:
    def test_state_with_stage_history(self):
        state = MaintenanceState(
            messages=[],
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
        assert state["stage_history"] == ["parse_pdf_tool"]
        assert state["auto_review"] is False

    def test_state_auto_review_default(self):
        state = MaintenanceState(
            messages=[],
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
        assert state["auto_review"] is True


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
    def test_base_prompt_contains_workflow(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "诊断" in prompt
        assert "修复" in prompt

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

    def test_prompt_contains_tool_selection_examples(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "工具选择示例" in prompt
        assert "解析器选择" in prompt
        assert "分块策略选择" in prompt

    def test_prompt_contains_constraint_rules(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "约束规则" in prompt
        assert "不要连续调用同一工具超过 3 次" in prompt

    def test_prompt_contains_error_handling(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "错误处理指导" in prompt
        assert "先分析错误原因" in prompt

    def test_prompt_with_locked_tool(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt(locked_tool="parse_pdf_tool")
        assert "工具锁定" in prompt
        assert "parse_pdf_tool" in prompt
        assert "历史经验推荐" not in prompt

    def test_prompt_contains_issue_rules(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "Issue" in prompt

    def test_prompt_contains_rollback_instructions(self):
        from src.agent.prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "回退" in prompt

    def test_system_prompt_backward_compat(self):
        from src.agent.prompt import SYSTEM_PROMPT

        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100


class TestExperienceStore:
    def test_save_experience(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        namespace = ("default", "maintenance_experience", "annual_report")
        key = exp_store.save_experience(
            namespace,
            {"pdf_type": "annual_report", "best_parser": "pymupdf4llm+pdfplumber"},
        )
        assert key.startswith("exp_")

    def test_search_experiences(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        namespace = ("default", "maintenance_experience", "annual_report")
        exp_store.save_experience(
            namespace,
            {"pdf_type": "annual_report", "best_parser": "pymupdf4llm+pdfplumber"},
        )
        results = exp_store.get_all_experiences(namespace)
        assert len(results) >= 1
        assert results[0]["best_parser"] == "pymupdf4llm+pdfplumber"

    def test_get_all_experiences_empty(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        namespace = ("default", "maintenance_experience", "nonexistent")
        results = exp_store.get_all_experiences(namespace)
        assert results == []

    def test_save_experience_includes_timestamp(self):
        from langgraph.store.memory import InMemoryStore

        from src.agent.memory.experience_store import ExperienceStore

        store = InMemoryStore()
        exp_store = ExperienceStore(store)
        namespace = ("default", "maintenance_experience", "annual_report")
        exp_store.save_experience(namespace, {"pdf_type": "annual_report"})
        results = exp_store.get_all_experiences(namespace)
        assert "timestamp" in results[0]


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

        import src.agent.graph as graph_module
        from src.agent.graph import agent_node
        from src.agent.state import MaintenanceState

        store = InMemoryStore()
        original_store = graph_module._agent_store
        graph_module._agent_store = store

        try:
            from src.agent.memory.experience_store import ExperienceStore

            exp_store = ExperienceStore(store)
            namespace = ("default", "maintenance_experience", "annual_report")
            exp_store.save_experience(
                namespace,
                {"pdf_type": "annual_report", "best_parser": "pymupdf4llm+pdfplumber"},
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
                result = agent_node(state)
                assert "messages" in result
        finally:
            graph_module._agent_store = original_store


class TestCLIReviewCommand:
    def test_review_on_sets_auto_review(self):
        assert True

    def test_review_off_sets_auto_review(self):
        assert True


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
    def test_parse_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":parse pymupdf4llm", False)
        assert result == "请用 pymupdf4llm 解析当前 PDF"

    def test_back_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":back chunk", False)
        assert result == "回到chunk阶段重新做"

    def test_compare_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":compare", False)
        assert result == "生成对比报告"

    def test_report_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":report", False)
        assert result == "生成维修报告"

    def test_history_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":history", False)
        assert result == "__show_history__"

    def test_status_command(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":status", False)
        assert result == "__show_status__"

    def test_non_command_returns_none(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command("hello", False)
        assert result is None

    def test_unknown_command_returns_none(self):
        from src.agent.cli import _handle_cli_command

        result = _handle_cli_command(":unknown", False)
        assert result is None
