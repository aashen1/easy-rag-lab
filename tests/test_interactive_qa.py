import pytest

from src.interactive_qa import (
    _build_chat_history,
    _get_assistant_messages,
    _parse_case_command,
    _resolve_assistant_msg,
)


def _make_messages():
    return [
        {"role": "user", "content": "第一个问题"},
        {
            "role": "assistant",
            "result": {
                "question": "第一个问题",
                "answer": "第一个回答",
                "sources": [],
                "scores": [],
            },
            "config_overrides": None,
            "meal_name": "test_meal",
            "saved_case_type": None,
            "saved_case_id": None,
        },
        {"role": "user", "content": "第二个问题"},
        {
            "role": "assistant",
            "result": {
                "question": "第二个问题",
                "answer": "第二个回答",
                "sources": [],
                "scores": [],
            },
            "config_overrides": None,
            "meal_name": "test_meal",
            "saved_case_type": None,
            "saved_case_id": None,
        },
    ]


@pytest.mark.unit
class TestBuildChatHistory:
    def test_build_chat_history_from_messages(self):
        messages = _make_messages()
        history = _build_chat_history(messages)
        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "第一个问题"}
        assert history[1] == {"role": "assistant", "content": "第一个回答"}
        assert history[2] == {"role": "user", "content": "第二个问题"}
        assert history[3] == {"role": "assistant", "content": "第二个回答"}

    def test_build_chat_history_empty(self):
        history = _build_chat_history([])
        assert history == []

    def test_build_chat_history_skips_empty_answer(self):
        messages = [
            {"role": "user", "content": "问题"},
            {
                "role": "assistant",
                "result": {"question": "问题", "answer": ""},
                "saved_case_type": None,
                "saved_case_id": None,
            },
        ]
        history = _build_chat_history(messages)
        assert len(history) == 1
        assert history[0]["role"] == "user"


@pytest.mark.unit
class TestGetAssistantMessages:
    def test_get_assistant_messages(self):
        messages = _make_messages()
        assistants = _get_assistant_messages(messages)
        assert len(assistants) == 2
        assert assistants[0]["result"]["answer"] == "第一个回答"
        assert assistants[1]["result"]["answer"] == "第二个回答"

    def test_get_assistant_messages_empty(self):
        assert _get_assistant_messages([]) == []


@pytest.mark.unit
class TestParseCaseCommand:
    def test_badcase_no_index(self):
        case_type, index = _parse_case_command("/badcase")
        assert case_type == "bad"
        assert index is None

    def test_goodcase_no_index(self):
        case_type, index = _parse_case_command("/goodcase")
        assert case_type == "good"
        assert index is None

    def test_badcase_with_index(self):
        case_type, index = _parse_case_command("/badcase 3")
        assert case_type == "bad"
        assert index == 3

    def test_goodcase_with_index(self):
        case_type, index = _parse_case_command("/goodcase 2")
        assert case_type == "good"
        assert index == 2

    def test_non_case_command(self):
        case_type, index = _parse_case_command("/help")
        assert case_type is None
        assert index is None

    def test_regular_question(self):
        case_type, index = _parse_case_command("什么是营业收入？")
        assert case_type is None
        assert index is None

    def test_invalid_index_returns_none(self):
        case_type, index = _parse_case_command("/badcase abc")
        assert case_type == "bad"
        assert index is None

    def test_case_insensitive(self):
        case_type, index = _parse_case_command("/BadCase")
        assert case_type == "bad"


@pytest.mark.unit
class TestResolveAssistantMsg:
    def test_resolve_latest(self):
        messages = _make_messages()
        msg, global_idx, err = _resolve_assistant_msg(messages, None)
        assert err == ""
        assert msg["result"]["answer"] == "第二个回答"
        assert global_idx == 3

    def test_resolve_by_index(self):
        messages = _make_messages()
        msg, global_idx, err = _resolve_assistant_msg(messages, 1)
        assert err == ""
        assert msg["result"]["answer"] == "第一个回答"
        assert global_idx == 1

    def test_resolve_second_assistant(self):
        messages = _make_messages()
        msg, global_idx, err = _resolve_assistant_msg(messages, 2)
        assert err == ""
        assert msg["result"]["answer"] == "第二个回答"

    def test_resolve_out_of_range(self):
        messages = _make_messages()
        msg, global_idx, err = _resolve_assistant_msg(messages, 5)
        assert msg is None
        assert "无效的轮次编号" in err

    def test_resolve_zero_index(self):
        messages = _make_messages()
        msg, global_idx, err = _resolve_assistant_msg(messages, 0)
        assert msg is None
        assert "无效的轮次编号" in err

    def test_resolve_no_messages(self):
        msg, global_idx, err = _resolve_assistant_msg([], None)
        assert msg is None
        assert "还没有查询记录" in err
