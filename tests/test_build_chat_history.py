import pytest

from src.case_collector import build_chat_history


@pytest.mark.unit
class TestBuildChatHistoryNoDuplication:
    def test_current_question_not_in_history_before_append(self):
        messages = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "result": {"answer": "first answer"}},
            {"role": "user", "content": "second question"},
            {"role": "assistant", "result": {"answer": "second answer"}},
        ]

        history = build_chat_history(messages)

        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "first question"}
        assert history[1] == {"role": "assistant", "content": "first answer"}
        assert history[2] == {"role": "user", "content": "second question"}
        assert history[3] == {"role": "assistant", "content": "second answer"}

        new_question = "third question"
        history_before = build_chat_history(messages)

        assert all(msg["content"] != new_question for msg in history_before)

        messages.append({"role": "user", "content": new_question})
        history_after = build_chat_history(messages)

        assert len(history_after) == 5
        assert history_after[-1] == {"role": "user", "content": new_question}

    def test_empty_messages_returns_empty_history(self):
        assert build_chat_history([]) == []

    def test_single_user_message(self):
        messages = [{"role": "user", "content": "hello"}]
        history = build_chat_history(messages)
        assert history == [{"role": "user", "content": "hello"}]

    def test_assistant_without_answer_skipped(self):
        messages = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "result": {}},
        ]
        history = build_chat_history(messages)
        assert len(history) == 1
        assert history[0] == {"role": "user", "content": "question"}
