"""Gemini embedding provider."""

from __future__ import annotations

import os
from typing import Sequence

import requests


class GeminiEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        dimension: int = 768,
        timeout: int = 30,
    ) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini embeddings")
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.timeout = timeout

    @classmethod
    def from_env(cls, dimension: int = 768) -> "GeminiEmbeddingProvider":
        return cls(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("JKG_EMBEDDING_MODEL", "gemini-embedding-001"),
            dimension=dimension,
        )

    def embed_text(self, text: str) -> list[float]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent"
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]},
        }
        response = requests.post(
            url,
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
            payload = response.json()
            values = payload["embedding"]["values"]
        except Exception as exc:
            body = (response.text or "")[:300]
            raise RuntimeError(f"Gemini embedding request failed: {exc}; body={body}") from exc

        if len(values) > self.dimension:
            values = values[: self.dimension]
        if len(values) < self.dimension:
            values = values + [0.0] * (self.dimension - len(values))
        return [float(value) for value in values]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

