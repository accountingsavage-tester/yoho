from __future__ import annotations

from typing import Iterable


class ConversationContext:
    def __init__(self, max_messages: int = 20):
        if max_messages < 1:
            raise ValueError("max_messages must be at least 1")
        self.max_messages = max_messages
        self.messages: list[dict[str, str]] = []

    def load(self, messages: Iterable[dict[str, str]]) -> None:
        self.messages = []
        for message in messages:
            self.add(message["role"], message["content"])

    def add(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        self.messages.append({"role": role, "content": str(content)})
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def build_prompt(self, system_prompt: str) -> str:
        lines = ["<|system|>", system_prompt]
        for message in self.messages:
            lines.extend([f"<|{message['role']}|>", message["content"]])
        lines.append("<|assistant|>")
        return "\n".join(lines)
