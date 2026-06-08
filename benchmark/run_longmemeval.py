#!/usr/bin/env python3
"""Run LongMemEval-style retrieval against the real JKG Postgres backend."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from jkg.db import PostgresMemory, migrate_postgres


TOP_K_VALUES = [1, 3, 5, 10, 20]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a real LongMemEval-style retrieval benchmark against JKG Postgres/pgvector."
    )
    parser.add_argument(
        "--dataset",
        default=os.environ.get("LONGMEMEVAL_PATH"),
        help="Path to LongMemEval-S JSON file. Can also be set with LONGMEMEVAL_PATH.",
    )
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--tenant-id", default=f"benchmark-{uuid.uuid4()}")
    parser.add_argument("--output", default=None)
    parser.add_argument("--cleanup", action="store_true", help="Delete this benchmark tenant after the run.")
    args = parser.parse_args()

    require_env("JKG_DATABASE_URL")
    require_env("GEMINI_API_KEY")
    if not args.dataset:
        raise SystemExit("LONGMEMEVAL_PATH or --dataset is required")

    dataset_path = Path(args.dataset).expanduser()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset file does not exist: {dataset_path}")

    records = load_dataset(dataset_path)
    if args.max_questions is not None:
        records = records[: args.max_questions]
    if not records:
        raise SystemExit("Dataset is empty")

    migrate_postgres()
    memory = PostgresMemory.from_env()
    run_tenant_id = args.tenant_id

    started = time.time()
    results = run_benchmark(memory, records, run_tenant_id=run_tenant_id)
    results["tenant_id"] = run_tenant_id
    results["dataset"] = str(dataset_path)
    results["elapsed_seconds"] = round(time.time() - started, 3)
    results["top_k_values"] = TOP_K_VALUES

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")

    print_report(results)
    print(f"\nSaved results to {output_path}")

    if args.cleanup:
        cleanup_run_tenants(memory, run_tenant_id)
        print(f"Deleted benchmark tenants with prefix {run_tenant_id}-")

    return 0


def require_env(name: str) -> None:
    if not os.environ.get(name):
        raise SystemExit(f"{name} is required for this real benchmark")


def load_dataset(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise SystemExit("Expected dataset JSON root to be a list")
    return data


def run_benchmark(
    memory: PostgresMemory,
    records: list[dict[str, Any]],
    *,
    run_tenant_id: str,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "benchmark": "LongMemEval-style retrieval",
        "system": "JKG Postgres pgvector",
        "total": 0,
        "skipped_abstention": 0,
        "skipped_invalid": 0,
        "recall_at_k": defaultdict(int),
        "by_type": defaultdict(lambda: {"total": 0, "hits": defaultdict(int)}),
        "failures": [],
    }

    for index, record in enumerate(records, start=1):
        try:
            item = normalize_record(record)
        except ValueError as exc:
            metrics["skipped_invalid"] += 1
            metrics["failures"].append({"index": index, "error": str(exc)})
            continue

        if not item["gold_session_ids"]:
            metrics["skipped_abstention"] += 1
            continue

        question_tenant_id = f"{run_tenant_id}-{item['question_id']}"
        memory.tenant_id = question_tenant_id

        memory.remember_many(
            [
                {
                    "text": text,
                    "source": "longmemeval",
                    "layer": "episodic",
                    "metadata": {
                        "benchmark": "longmemeval",
                        "question_id": item["question_id"],
                        "session_id": session_id,
                    },
                }
                for session_id, text in item["sessions"]
            ],
            source="longmemeval",
            layer="episodic",
        )

        query_result = memory.query(item["question"], layers=["episodic"], limit=max(TOP_K_VALUES))
        ranked_session_ids = [
            row["metadata"].get("session_id")
            for row in query_result["results"]
            if isinstance(row.get("metadata"), dict)
        ]

        metrics["total"] += 1
        metrics["by_type"][item["question_type"]]["total"] += 1
        gold = set(item["gold_session_ids"])
        for top_k in TOP_K_VALUES:
            if set(ranked_session_ids[:top_k]) & gold:
                key = f"recall@{top_k}"
                metrics["recall_at_k"][key] += 1
                metrics["by_type"][item["question_type"]]["hits"][key] += 1

        if index % 10 == 0:
            total = metrics["total"]
            hits = metrics["recall_at_k"]["recall@5"]
            print(f"[{index}/{len(records)}] recall@5={hits / max(1, total):.3f}")

        if os.environ.get("JKG_BENCHMARK_CLEANUP_EACH_QUESTION") == "1":
            cleanup_tenant(memory)

    metrics["recall_at_k"] = dict(metrics["recall_at_k"])
    metrics["by_type"] = {
        question_type: {
            "total": values["total"],
            "hits": dict(values["hits"]),
        }
        for question_type, values in metrics["by_type"].items()
    }
    return metrics


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    question_id = str(record.get("question_id") or record.get("id") or "")
    question = str(record.get("question") or "")
    question_type = str(record.get("question_type") or "unknown")
    gold_session_ids = record.get("answer_session_ids") or record.get("gold_session_ids") or []
    haystack_sessions = record.get("haystack_sessions")
    haystack_session_ids = record.get("haystack_session_ids")

    if not question_id:
        raise ValueError("missing question_id")
    if not question:
        raise ValueError(f"{question_id}: missing question")
    if not isinstance(gold_session_ids, list):
        raise ValueError(f"{question_id}: answer_session_ids must be a list")
    if not isinstance(haystack_sessions, list):
        raise ValueError(f"{question_id}: haystack_sessions must be a list")
    if not isinstance(haystack_session_ids, list):
        raise ValueError(f"{question_id}: haystack_session_ids must be a list")
    if len(haystack_sessions) != len(haystack_session_ids):
        raise ValueError(f"{question_id}: haystack_sessions and haystack_session_ids length mismatch")

    sessions = [
        (str(session_id), render_session_text(session))
        for session_id, session in zip(haystack_session_ids, haystack_sessions, strict=True)
    ]
    return {
        "question_id": question_id,
        "question": question,
        "question_type": question_type,
        "gold_session_ids": [str(session_id) for session_id in gold_session_ids],
        "sessions": sessions,
    }


def render_session_text(session: Any) -> str:
    if isinstance(session, str):
        return session
    if not isinstance(session, list):
        raise ValueError("session must be a string or list of turns")

    turns = []
    for turn in session:
        if isinstance(turn, str):
            turns.append(turn)
            continue
        if not isinstance(turn, dict):
            raise ValueError("session turn must be a string or object")
        role = turn.get("role", "unknown")
        content = turn.get("content", "")
        turns.append(f"{role}: {content}")
    return "\n".join(turns)


def default_output_path() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path("benchmark/results") / f"longmemeval_jkg_{stamp}.json"


def cleanup_tenant(memory: PostgresMemory) -> None:
    with memory._connect() as conn:
        conn.execute("DELETE FROM jkg_memory_items WHERE tenant_id = %s", (memory.tenant_id,))
        conn.commit()


def cleanup_run_tenants(memory: PostgresMemory, run_tenant_id: str) -> None:
    with memory._connect() as conn:
        conn.execute("DELETE FROM jkg_memory_items WHERE tenant_id LIKE %s", (f"{run_tenant_id}-%",))
        conn.commit()


def print_report(results: dict[str, Any]) -> None:
    total = results["total"]
    print("\nJKG LongMemEval-style retrieval results")
    print(f"Questions scored: {total}")
    print(f"Skipped abstention: {results['skipped_abstention']}")
    print(f"Skipped invalid: {results['skipped_invalid']}")
    for top_k in TOP_K_VALUES:
        key = f"recall@{top_k}"
        hits = results["recall_at_k"].get(key, 0)
        print(f"{key}: {hits / max(1, total):.4f} ({hits}/{total})")


if __name__ == "__main__":
    raise SystemExit(main())
