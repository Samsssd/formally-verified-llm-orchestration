"""Tests for token counting and context management."""

from excelsior_harness.context import ContextManager, TokenCounter


class TestTokenCounter:
    def test_count_simple_text(self):
        counter = TokenCounter()
        count = counter.count("hello world")
        assert isinstance(count, int)
        assert count > 0

    def test_count_empty_string(self):
        counter = TokenCounter()
        assert counter.count("") == 0

    def test_count_messages(self):
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi there."},
        ]
        count = counter.count_messages(messages)
        assert count > 0


class TestContextManager:
    def test_no_truncation_when_under_limit(self):
        cm = ContextManager(max_context_tokens=10000, keep_recent=5)
        messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = cm.prepare(messages)
        assert len(result) == 3

    def test_truncation_preserves_system_and_recent(self):
        cm = ContextManager(max_context_tokens=100, keep_recent=2)
        messages = [
            {"role": "system", "content": "System prompt."},
        ]
        for i in range(20):
            messages.append({"role": "user", "content": f"Message {i} " * 20})
        result = cm.prepare(messages)
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == messages[-1]["content"]
        assert result[-2]["content"] == messages[-2]["content"]
        assert len(result) == 4  # system + summary + 2 recent

    def test_summary_message_contains_context_summary_marker(self):
        cm = ContextManager(max_context_tokens=100, keep_recent=1)
        messages = [
            {"role": "system", "content": "System."},
        ]
        for i in range(20):
            messages.append({"role": "user", "content": f"Long message {i} " * 20})
        result = cm.prepare(messages)
        summary_msg = result[1]
        assert summary_msg["role"] == "system"
        assert "[Context Summary]" in summary_msg["content"]
