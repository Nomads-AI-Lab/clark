"""Provider protocols used by Clark core services."""

from __future__ import annotations

from typing import Protocol, Sequence


class LLMProvider(Protocol):
    def complete(self, prompt: str, system: str) -> str:
        """Return text from a real LLM provider or raise a provider error."""


class EmbeddingProvider(Protocol):
    model: str
    dimension: int

    def embed_text(self, text: str) -> list[float]:
        """Embed one text string or raise a provider error."""

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a sequence of text strings or raise a provider error."""

