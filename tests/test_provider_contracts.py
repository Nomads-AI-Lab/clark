import json
import os

import pytest


pytestmark = pytest.mark.provider


def test_deepseek_llm_returns_parseable_json_contract():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY is required for DeepSeek provider contract test")

    from clark.memory import _llm

    raw = _llm(
        'Return exactly this JSON object and nothing else: {"ok": true, "provider": "deepseek"}',
        system="You are a JSON contract test endpoint. Return JSON only.",
    )
    payload = json.loads(raw)

    assert payload == {"ok": True, "provider": "deepseek"}


def test_gemini_embedding_returns_configured_vector_dimension():
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is required for Gemini embedding provider contract test")

    from clark.memory import EMBEDDING_DIM, HybridMemory

    memory = HybridMemory(db_path=":memory:")
    embedding = memory.encode("Clark provider contract test")

    assert len(embedding) == EMBEDDING_DIM
    assert any(float(value) != 0.0 for value in embedding)


def test_gemini_batch_embedding_returns_one_vector_per_text():
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is required for Gemini batch embedding provider contract test")

    from clark.providers import GeminiEmbeddingProvider

    provider = GeminiEmbeddingProvider.from_env(dimension=768)
    embeddings = provider.embed_batch(["Clark batch embedding A", "Clark batch embedding B"])

    assert len(embeddings) == 2
    assert all(len(embedding) == 768 for embedding in embeddings)
    assert all(any(float(value) != 0.0 for value in embedding) for embedding in embeddings)
