"""Gemini embedding provider."""

from __future__ import annotations

import os
import time
from typing import Sequence

import requests


class GeminiEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        dimension: int = 768,
        timeout: int = 30,
        max_retries: int = 5,
    ) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini embeddings")
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.timeout = timeout
        self.max_retries = max_retries

    @classmethod
    def from_env(cls, dimension: int = 768) -> "GeminiEmbeddingProvider":
        return cls(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("JKG_EMBEDDING_MODEL", "gemini-embedding-001"),
            dimension=dimension,
            max_retries=int(os.environ.get("JKG_GEMINI_MAX_RETRIES", "5")),
        )

    def embed_text(self, text: str) -> list[float]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent"
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]},
        }
        response = self._post_with_retries(url, payload)
        try:
            response.raise_for_status()
            payload = response.json()
            values = payload["embedding"]["values"]
        except Exception as exc:
            body = (response.text or "")[:300]
            raise RuntimeError(f"Gemini embedding request failed: {exc}; body={body}") from exc

        return self._normalize_values(values)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents"
        payload = {
            "requests": [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                }
                for text in texts
            ]
        }
        response = self._post_with_retries(url, payload)
        try:
            response.raise_for_status()
            payload = response.json()
            embeddings = payload["embeddings"]
        except Exception as exc:
            body = (response.text or "")[:300]
            raise RuntimeError(f"Gemini batch embedding request failed: {exc}; body={body}") from exc

        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Gemini batch embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
            )
        return [self._normalize_values(item["values"]) for item in embeddings]

    def _normalize_values(self, values: Sequence[float]) -> list[float]:
        result = list(values)
        if len(result) > self.dimension:
            result = result[: self.dimension]
        if len(result) < self.dimension:
            result = result + [0.0] * (self.dimension - len(result))
        return [float(value) for value in result]

    def _post_with_retries(self, url: str, payload: dict) -> requests.Response:
        last_response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            response = requests.post(
                url,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response

            last_response = response
            if attempt >= self.max_retries:
                return response

            retry_after = response.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                delay = float(retry_after)
            else:
                delay = min(60.0, 2.0**attempt)
            time.sleep(delay)

        assert last_response is not None
        return last_response
