from typing import Iterator

from groq import Groq

from .base import LLMProvider


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "", max_tokens: int = 1024, client=None):
        # `client` can be injected so tests don't need a real API key.
        self._client = client or Groq(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def stream(self, messages, system_prompt=None) -> Iterator[str]:
        # Groq speaks the OpenAI format: system prompt = first message, role "system".
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}, *messages]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
            max_tokens=self._max_tokens,
        )
        for chunk in response:
            token = chunk.choices[0].delta.content or ""
            if token:  # Groq sends empty deltas at stream edges; drop them
                yield token