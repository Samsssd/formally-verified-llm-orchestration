"""Context window management with token counting and intelligent truncation.

Inspired by LangGraph's StateGraph approach to explicit state management —
the context window is treated as a first-class resource to be managed,
not an afterthought. Token counting uses tiktoken for accurate estimates.
"""

from __future__ import annotations

import tiktoken

from excelsior_harness._types import Messages


class TokenCounter:
    """Count tokens using tiktoken.

    Defaults to cl100k_base encoding (used by GPT-4, Claude-compatible).
    """

    def __init__(self, model: str = "cl100k_base") -> None:
        self._enc = tiktoken.get_encoding(model)

    def count(self, text: str | object) -> int:
        """Count tokens in a string (non-strings are converted via str())."""
        if not text:
            return 0
        if not isinstance(text, str):
            text = str(text)
        return len(self._enc.encode(text))

    def count_messages(self, messages: Messages) -> int:
        """Count total tokens across all messages.

        Uses a simplified per-message overhead of 4 tokens (role + delimiters),
        matching the OpenAI token counting convention.
        """
        total = 0
        for msg in messages:
            total += 4  # role + structural overhead
            total += self.count(msg.get("content", ""))
        return total


class ContextManager:
    """Manage the context window by truncating old messages when needed.

    Truncation strategy:
      1. Always keep the system prompt (first message).
      2. Always keep the last ``keep_recent`` messages.
      3. If the total exceeds ``max_context_tokens``, replace the middle
         messages with a deterministic "[Context Summary]" message.

    The summary is a simple concatenation of truncated content — not
    LLM-generated — to stay deterministic and mock-friendly.
    """

    def __init__(
        self,
        max_context_tokens: int = 8000,
        keep_recent: int = 10,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.keep_recent = keep_recent
        self._counter = TokenCounter()

    def prepare(self, messages: Messages) -> Messages:
        """Return a (possibly truncated) copy of *messages* that fits the window."""
        if not messages:
            return []

        total = self._counter.count_messages(messages)
        if total <= self.max_context_tokens:
            return list(messages)

        # Split into: system | middle | recent
        system = [messages[0]]
        recent = messages[-self.keep_recent :] if self.keep_recent else []
        middle = messages[1 : len(messages) - len(recent)] if recent else messages[1:]

        # Build a deterministic summary of the middle messages
        summary_parts: list[str] = []
        for msg in middle:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            snippet = content[:80].replace("\n", " ")
            if len(content) > 80:
                snippet += "..."
            summary_parts.append(f"[{role}]: {snippet}")

        summary_text = "[Context Summary] Older messages condensed:\n" + "\n".join(
            summary_parts
        )
        summary_msg = {"role": "system", "content": summary_text}

        return system + [summary_msg] + recent
