"""The contract every LLM provider must satisfy.

The API layer only talks to this. Swapping Groq for OpenAI/Gemini = one new
subclass; the streaming endpoint never changes.
"""
from abc import ABC, abstractmethod
from typing import Iterator


class LLMProvider(ABC):
    @abstractmethod
    def stream(
        self, messages: list[dict], system_prompt: str | None = None
    ) -> Iterator[str]:
        """Yield the reply one token at a time.

        system_prompt is separate from messages because providers attach it
        differently (a "system" role message for OpenAI-style APIs, a
        system_instruction argument for Gemini). The caller shouldn't care.
        """