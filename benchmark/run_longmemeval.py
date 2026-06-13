#!/usr/bin/env python3
"""Run LongMemEval-style retrieval against the real Clark Postgres backend."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from clark.db import PostgresMemory, migrate_postgres


TOP_K_VALUES = [1, 3, 5, 10, 20]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a real LongMemEval-style retrieval benchmark against Clark Postgres/pgvector."
    )
    parser.add_argument(
        "--dataset",
        default=os.environ.get("LONGMEMEVAL_PATH"),
        help="Path to LongMemEval-S JSON file. Can also be set with LONGMEMEVAL_PATH.",
    )
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--stop-after", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--checkpoint-jsonl", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--tenant-id", default=f"benchmark-{uuid.uuid4()}")
    parser.add_argument("--output", default=None)
    parser.add_argument("--cleanup", action="store_true", help="Delete this benchmark tenant after the run.")
    args = parser.parse_args()

    require_env("CLARK_DATABASE_URL")
    require_env("GEMINI_API_KEY")
    if not args.dataset:
        raise SystemExit("LONGMEMEVAL_PATH or --dataset is required")

    dataset_path = Path(args.dataset).expanduser()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset file does not exist: {dataset_path}")

    records = load_dataset(dataset_path)
    if args.max_questions is not None:
        records = records[: args.max_questions]
    if args.start_index:
        records = records[args.start_index :]
    if not records:
        raise SystemExit("Dataset is empty")

    migrate_postgres()
    memory = PostgresMemory.from_env()
    run_tenant_id = args.tenant_id

    started = time.time()
    checkpoint_path = Path(args.checkpoint_jsonl) if args.checkpoint_jsonl else None
    try:
        results = run_benchmark(
            memory,
            records,
            run_tenant_id=run_tenant_id,
            stop_after=args.stop_after,
            sleep_seconds=args.sleep_seconds,
            checkpoint_path=checkpoint_path,
            resume=args.resume,
        )
        results["status"] = "completed"
    except Exception as exc:
        if not checkpoint_path:
            raise
        results = metrics_from_checkpoint(checkpoint_path)
        results["status"] = "failed"
        results["error"] = str(exc)
        results["error_type"] = type(exc).__name__
    results["tenant_id"] = run_tenant_id
    results["dataset"] = str(dataset_path)
    results["elapsed_seconds"] = round(time.time() - started, 3)
    results["top_k_values"] = TOP_K_VALUES

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")

    print_report(results)
    print(f"\nSaved results to {output_path}")
    if results.get("status") == "failed":
        raise SystemExit(1)

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
    stop_after: int | None = None,
    sleep_seconds: float = 0.0,
    checkpoint_path: Path | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "benchmark": "LongMemEval-style retrieval",
        "system": "Clark Postgres pgvector",
        "total": 0,
        "skipped_abstention": 0,
        "skipped_invalid": 0,
        "recall_at_k": defaultdict(int),
        "by_type": defaultdict(lambda: {"total": 0, "hits": defaultdict(int)}),
        "failures": [],
    }
    completed_question_ids: set[str] = set()
    if resume and checkpoint_path:
        completed_question_ids = load_checkpoint(checkpoint_path, metrics)

    for index, record in enumerate(records, start=1):
        try:
            item = normalize_record(record)
        except ValueError as exc:
            metrics["skipped_invalid"] += 1
            failure = {"index": index, "error": str(exc)}
            metrics["failures"].append(failure)
            write_checkpoint(checkpoint_path, {"status": "invalid", **failure})
            continue

        if item["question_id"] in completed_question_ids:
            continue

        if not item["gold_session_ids"]:
            metrics["skipped_abstention"] += 1
            write_checkpoint(
                checkpoint_path,
                {
                    "status": "abstention",
                    "question_id": item["question_id"],
                    "question_type": item["question_type"],
                },
            )
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
        hits: dict[str, bool] = {}
        gold = set(item["gold_session_ids"])
        for top_k in TOP_K_VALUES:
            key = f"recall@{top_k}"
            if set(ranked_session_ids[:top_k]) & gold:
                metrics["recall_at_k"][key] += 1
                metrics["by_type"][item["question_type"]]["hits"][key] += 1
                hits[key] = True
            else:
                hits[key] = False

        write_checkpoint(
            checkpoint_path,
            {
                "status": "scored",
                "question_id": item["question_id"],
                "question_type": item["question_type"],
                "gold_session_ids": item["gold_session_ids"],
                "ranked_session_ids": ranked_session_ids[: max(TOP_K_VALUES)],
                "hits": hits,
            },
        )

        if index % 10 == 0:
            total = metrics["total"]
            hits = metrics["recall_at_k"]["recall@5"]
            print(f"[{index}/{len(records)}] recall@5={hits / max(1, total):.3f}")

        if os.environ.get("CLARK_BENCHMARK_CLEANUP_EACH_QUESTION") == "1":
            cleanup_tenant(memory)

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        if stop_after is not None and metrics["total"] >= stop_after:
            break

    metrics["recall_at_k"] = dict(metrics["recall_at_k"])
    metrics["by_type"] = {
        question_type: {
            "total": values["total"],
            "hits": dict(values["hits"]),
        }
        for question_type, values in metrics["by_type"].items()
    }
    return metrics


def load_checkpoint(path: Path, metrics: dict[str, Any]) -> set[str]:
    completed: set[str] = set()
    if not path.exists():
        return completed
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        status = entry.get("status")
        question_id = entry.get("question_id")
        if question_id:
            completed.add(str(question_id))
        if status == "scored":
            question_type = str(entry["question_type"])
            metrics["total"] += 1
            metrics["by_type"][question_type]["total"] += 1
            for key, hit in entry.get("hits", {}).items():
                if hit:
                    metrics["recall_at_k"][key] += 1
                    metrics["by_type"][question_type]["hits"][key] += 1
        elif status == "abstention":
            metrics["skipped_abstention"] += 1
        elif status == "invalid":
            metrics["skipped_invalid"] += 1
            metrics["failures"].append(entry)
    return completed


def metrics_from_checkpoint(path: Path) -> dict[str, Any]:
    metrics = empty_metrics()
    load_checkpoint(path, metrics)
    metrics["recall_at_k"] = dict(metrics["recall_at_k"])
    metrics["by_type"] = {
        question_type: {
            "total": values["total"],
            "hits": dict(values["hits"]),
        }
        for question_type, values in metrics["by_type"].items()
    }
    return metrics


def empty_metrics() -> dict[str, Any]:
    return {
        "benchmark": "LongMemEval-style retrieval",
        "system": "Clark Postgres pgvector",
        "total": 0,
        "skipped_abstention": 0,
        "skipped_invalid": 0,
        "recall_at_k": defaultdict(int),
        "by_type": defaultdict(lambda: {"total": 0, "hits": defaultdict(int)}),
        "failures": [],
    }


def write_checkpoint(path: Path | None, entry: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
    return Path("benchmark/results") / f"longmemeval_clark_{stamp}.json"


def cleanup_tenant(memory: PostgresMemory) -> None:
    with memory._connect() as conn:
        conn.execute("DELETE FROM clark_memory_items WHERE tenant_id = %s", (memory.tenant_id,))
        conn.commit()


def cleanup_run_tenants(memory: PostgresMemory, run_tenant_id: str) -> None:
    with memory._connect() as conn:
        conn.execute("DELETE FROM clark_memory_items WHERE tenant_id LIKE %s", (f"{run_tenant_id}-%",))
        conn.commit()


def print_report(results: dict[str, Any]) -> None:
    total = results["total"]
    print("\nClark LongMemEval-style retrieval results")
    print(f"Questions scored: {total}")
    print(f"Skipped abstention: {results['skipped_abstention']}")
    print(f"Skipped invalid: {results['skipped_invalid']}")
    for top_k in TOP_K_VALUES:
        key = f"recall@{top_k}"
        hits = results["recall_at_k"].get(key, 0)
        print(f"{key}: {hits / max(1, total):.4f} ({hits}/{total})")


if __name__ == "__main__":
    raise SystemExit(main())
