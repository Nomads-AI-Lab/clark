"""Postgres + pgvector backend for production Clark deployments."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from clark.providers import GeminiEmbeddingProvider


EMBEDDING_DIMENSION = 768


MIGRATION_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS clark_memory_items (
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    layer TEXT NOT NULL DEFAULT 'factual',
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'api',
    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    embedding vector({EMBEDDING_DIMENSION}) NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(content, ''))
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clark_memory_items_tenant_created
    ON clark_memory_items (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_clark_memory_items_search
    ON clark_memory_items USING gin (search_vector);

CREATE INDEX IF NOT EXISTS idx_clark_memory_items_embedding_hnsw
    ON clark_memory_items USING hnsw (embedding vector_cosine_ops);
"""


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def migrate_postgres(database_url: str | None = None) -> dict[str, Any]:
    dsn = database_url or os.environ.get("CLARK_DATABASE_URL")
    if not dsn:
        raise RuntimeError("CLARK_DATABASE_URL is required for Postgres migrations")

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.execute(MIGRATION_SQL)
        version = conn.execute("SHOW server_version").fetchone()["server_version"]
        pgvector = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        conn.commit()
    return {
        "status": "ok",
        "postgres_version": version,
        "pgvector_version": pgvector["extversion"] if pgvector else None,
    }


@dataclass
class PostgresMemory:
    database_url: str
    tenant_id: str = "default"

    @classmethod
    def from_env(cls) -> "PostgresMemory":
        database_url = os.environ.get("CLARK_DATABASE_URL")
        if not database_url:
            raise RuntimeError("CLARK_DATABASE_URL is required for Postgres backend")
        return cls(
            database_url=database_url,
            tenant_id=os.environ.get("CLARK_TENANT_ID", "default"),
        )

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _embedding_provider(self) -> GeminiEmbeddingProvider:
        return GeminiEmbeddingProvider.from_env(dimension=EMBEDDING_DIMENSION)

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    count(*)::int AS memories,
                    count(*) FILTER (WHERE layer = 'profile')::int AS profile,
                    count(*) FILTER (WHERE layer = 'factual')::int AS factual,
                    count(*) FILTER (WHERE layer = 'episodic')::int AS episodic,
                    count(*) FILTER (WHERE layer = 'procedural')::int AS procedural
                FROM clark_memory_items
                WHERE tenant_id = %s
                """,
                (self.tenant_id,),
            ).fetchone()
        return {
            "backend": "postgres",
            "tenant_id": self.tenant_id,
            "memories": row["memories"],
            "profile": row["profile"],
            "factual": row["factual"],
            "episodic": row["episodic"],
            "procedural": row["procedural"],
            "embedding_dimension": EMBEDDING_DIMENSION,
        }

    def remember(
        self,
        text: str,
        source: str = "api",
        layer: str = "factual",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        embedding = self._embedding_provider().embed_text(text)
        memory_id = uuid.uuid4()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO clark_memory_items
                    (id, tenant_id, layer, content, source, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    memory_id,
                    self.tenant_id,
                    layer,
                    text,
                    source,
                    Jsonb(metadata or {}),
                    _vector_literal(embedding),
                ),
            )
            conn.commit()
        return {
            "status": "ok",
            "backend": "postgres",
            "id": str(memory_id),
            "layer": layer,
            "source": source,
        }

    def remember_many(
        self,
        items: list[dict[str, Any]],
        *,
        source: str = "api",
        layer: str = "factual",
    ) -> dict[str, Any]:
        if not items:
            return {"status": "ok", "backend": "postgres", "inserted": 0, "ids": []}

        texts = [str(item["text"]) for item in items]
        embeddings = self._embedding_provider().embed_batch(texts)
        memory_ids = [uuid.uuid4() for _ in items]
        rows = [
            (
                memory_id,
                self.tenant_id,
                str(item.get("layer", layer)),
                str(item["text"]),
                str(item.get("source", source)),
                Jsonb(item.get("metadata") or {}),
                _vector_literal(embedding),
            )
            for memory_id, item, embedding in zip(memory_ids, items, embeddings, strict=True)
        ]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO clark_memory_items
                        (id, tenant_id, layer, content, source, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                    """,
                    rows,
                )
            conn.commit()
        return {
            "status": "ok",
            "backend": "postgres",
            "inserted": len(rows),
            "ids": [str(memory_id) for memory_id in memory_ids],
        }

    def query(self, text: str, layers: list[str] | None = None, limit: int = 10) -> dict[str, Any]:
        embedding = self._embedding_provider().embed_text(text)
        layer_filter = layers or ["profile", "factual", "episodic", "procedural"]
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH q AS (
                    SELECT
                        plainto_tsquery('simple', %s) AS text_query,
                        %s::vector AS query_embedding
                )
                SELECT
                    id::text,
                    layer,
                    content,
                    source,
                    metadata,
                    created_at::text,
                    1 - (embedding <=> q.query_embedding) AS vector_score,
                    ts_rank_cd(search_vector, q.text_query) AS text_score,
                    (
                        (1 - (embedding <=> q.query_embedding)) * 0.8
                        + ts_rank_cd(search_vector, q.text_query) * 0.2
                    ) AS score
                FROM clark_memory_items, q
                WHERE tenant_id = %s
                  AND layer = ANY(%s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (
                    text,
                    _vector_literal(embedding),
                    self.tenant_id,
                    layer_filter,
                    limit,
                ),
            ).fetchall()
        return {
            "query": text,
            "backend": "postgres",
            "tenant_id": self.tenant_id,
            "layers_searched": layer_filter,
            "total_candidates": len(rows),
            "results": [
                {
                    "id": row["id"],
                    "layer": row["layer"],
                    "content": row["content"],
                    "source": row["source"],
                    "metadata": row["metadata"],
                    "created_at": row["created_at"],
                    "score": float(row["score"] or 0.0),
                    "vector_score": float(row["vector_score"] or 0.0),
                    "text_score": float(row["text_score"] or 0.0),
                }
                for row in rows
            ],
        }
