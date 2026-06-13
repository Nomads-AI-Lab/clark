from __future__ import annotations

import requests


def test_gemini_provider_reads_timeout_from_env(monkeypatch) -> None:
    from clark.providers.gemini import GeminiEmbeddingProvider

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CLARK_GEMINI_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("CLARK_GEMINI_MAX_RETRIES", "7")

    provider = GeminiEmbeddingProvider.from_env()

    assert provider.timeout == 120
    assert provider.max_retries == 7


def test_gemini_provider_retries_timeouts(monkeypatch) -> None:
    from clark.providers.gemini import GeminiEmbeddingProvider

    calls = {"count": 0}

    class Response:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"embedding": {"values": [1.0] * 768}}

    def post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.Timeout("temporary timeout")
        return Response()

    monkeypatch.setattr("clark.providers.gemini.requests.post", post)
    monkeypatch.setattr("clark.providers.gemini.time.sleep", lambda seconds: None)

    provider = GeminiEmbeddingProvider(api_key="test-key", max_retries=1)
    embedding = provider.embed_text("retry timeout test")

    assert calls["count"] == 2
    assert len(embedding) == 768
