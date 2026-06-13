"""Local environment diagnostics for Clark."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

from .memory import DB_PATH


def collect_diagnostics() -> dict:
    db_path = Path(DB_PATH).expanduser()
    db_parent = db_path.parent
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 10),
            "version": sys.version.split()[0],
        },
        "package": {
            "ok": True,
            "version": importlib.metadata.version("clark"),
        },
        "sqlite": {
            "ok": True,
            "version": sqlite3.sqlite_version,
        },
        "db_path": {
            "ok": db_parent.exists() or os.access(db_parent.parent, os.W_OK),
            "path": str(db_path),
            "parent_exists": db_parent.exists(),
        },
        "sqlite_vec": {
            "ok": importlib.util.find_spec("sqlite_vec") is not None,
        },
        "deepseek": {
            "ok": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "model": os.environ.get("CLARK_LLM_MODEL", "deepseek-v4-flash"),
        },
        "gemini": {
            "ok": bool(os.environ.get("GEMINI_API_KEY")),
            "configured": bool(os.environ.get("GEMINI_API_KEY")),
            "model": os.environ.get("CLARK_EMBEDDING_MODEL", "gemini-embedding-001"),
        },
    }
    database_url = os.environ.get("CLARK_DATABASE_URL")
    if database_url:
        try:
            import psycopg
            from psycopg.rows import dict_row

            with psycopg.connect(database_url, row_factory=dict_row) as conn:
                postgres_version = conn.execute("SHOW server_version").fetchone()["server_version"]
                pgvector = conn.execute(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                ).fetchone()
            checks["postgres"] = {
                "ok": pgvector is not None,
                "configured": True,
                "postgres_version": postgres_version,
                "pgvector_version": pgvector["extversion"] if pgvector else None,
            }
        except Exception as exc:
            checks["postgres"] = {
                "ok": False,
                "configured": True,
                "error": str(exc),
            }
    else:
        checks["postgres"] = {"ok": True, "configured": False}
    checks["overall_ok"] = all(
        checks[name]["ok"]
        for name in ("python", "package", "sqlite", "db_path", "sqlite_vec", "postgres")
    )
    return checks


def main() -> int:
    diagnostics = collect_diagnostics()
    print(json.dumps(diagnostics, indent=2, ensure_ascii=False))
    return 0 if diagnostics["overall_ok"] else 1
