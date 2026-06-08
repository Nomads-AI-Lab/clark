import os

import pytest


pytestmark = pytest.mark.postgres


def test_postgres_migrate_remember_and_query_round_trip():
    if not os.environ.get("JKG_DATABASE_URL"):
        pytest.skip("JKG_DATABASE_URL is required for Postgres integration test")
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is required for Postgres vector integration test")

    from jkg.db import PostgresMemory, migrate_postgres

    migration = migrate_postgres()
    memory = PostgresMemory.from_env()
    text = "JKG Postgres integration test remembers CLARK retrieval architecture."

    stored = memory.remember(text, source="pytest", metadata={"test": "postgres"})
    result = memory.query("What architecture does the JKG Postgres test remember?", limit=3)

    assert migration["status"] == "ok"
    assert migration["pgvector_version"]
    assert stored["status"] == "ok"
    assert stored["backend"] == "postgres"
    assert result["backend"] == "postgres"
    assert result["results"]
    assert any("CLARK retrieval architecture" in row["content"] for row in result["results"])


def test_postgres_remember_many_batches_embeddings():
    if not os.environ.get("JKG_DATABASE_URL"):
        pytest.skip("JKG_DATABASE_URL is required for Postgres integration test")
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is required for Postgres vector integration test")

    from jkg.db import PostgresMemory, migrate_postgres

    migrate_postgres()
    memory = PostgresMemory.from_env()
    memory.tenant_id = "pytest-batch"

    stored = memory.remember_many(
        [
            {
                "text": "Batch memory alpha stores pgvector embeddings.",
                "metadata": {"batch": "alpha"},
            },
            {
                "text": "Batch memory beta stores Gemini embeddings.",
                "metadata": {"batch": "beta"},
            },
        ],
        source="pytest",
        layer="episodic",
    )
    result = memory.query("Which batch memory stores Gemini embeddings?", layers=["episodic"], limit=2)

    assert stored["status"] == "ok"
    assert stored["inserted"] == 2
    assert len(stored["ids"]) == 2
    assert result["results"]
    assert any("Gemini embeddings" in row["content"] for row in result["results"])
