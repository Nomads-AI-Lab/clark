#!/usr/bin/env python3
"""Compare Clark with real memory providers on LongMemEval-style retrieval."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

from run_longmemeval import TOP_K_VALUES, load_dataset, normalize_record, print_report


class MemoryAdapter(Protocol):
    name: str

    def index_sessions(self, question_id: str, sessions: list[tuple[str, str]]) -> None: ...

    def search(self, question: str, limit: int) -> list[str]: ...

    def cleanup(self) -> None: ...


class ClarkAdapter:
    name = "clark"

    def __init__(self, run_id: str) -> None:
        from clark.db import PostgresMemory, migrate_postgres

        require_env("CLARK_DATABASE_URL")
        require_env("GEMINI_API_KEY")
        migrate_postgres()
        self.memory = PostgresMemory.from_env()
        self.run_id = run_id

    def index_sessions(self, question_id: str, sessions: list[tuple[str, str]]) -> None:
        self.memory.tenant_id = f"{self.run_id}-{question_id}"
        self.memory.remember_many(
            [
                {
                    "text": text,
                    "source": "longmemeval-comparison",
                    "layer": "episodic",
                    "metadata": {"question_id": question_id, "session_id": session_id},
                }
                for session_id, text in sessions
            ],
            source="longmemeval-comparison",
            layer="episodic",
        )

    def search(self, question: str, limit: int) -> list[str]:
        result = self.memory.query(question, layers=["episodic"], limit=limit)
        return [
            row["metadata"].get("session_id")
            for row in result["results"]
            if isinstance(row.get("metadata"), dict)
        ]

    def cleanup(self) -> None:
        with self.memory._connect() as conn:
            conn.execute("DELETE FROM clark_memory_items WHERE tenant_id LIKE %s", (f"{self.run_id}-%",))
            conn.commit()


class Mem0Adapter:
    name = "mem0"

    def __init__(self, run_id: str, root: Path) -> None:
        require_env("GEMINI_API_KEY")
        require_env("DEEPSEEK_API_KEY")
        from mem0 import Memory

        self.run_id = run_id
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory = Memory.from_config(
            {
                "llm": {
                    "provider": "deepseek",
                    "config": {
                        "api_key": os.environ["DEEPSEEK_API_KEY"],
                        "model": os.environ.get("MEM0_DEEPSEEK_MODEL", "deepseek-chat"),
                    },
                },
                "embedder": {
                    "provider": "gemini",
                    "config": {
                        "api_key": os.environ["GEMINI_API_KEY"],
                        "model": os.environ.get("MEM0_GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
                        "embedding_dims": 768,
                    },
                },
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "path": str(self.root / "qdrant"),
                        "collection_name": "longmemeval_comparison",
                        "embedding_model_dims": 768,
                    },
                },
                "history_db_path": str(self.root / "history.db"),
            }
        )
        self.user_id = ""

    def index_sessions(self, question_id: str, sessions: list[tuple[str, str]]) -> None:
        self.user_id = f"{self.run_id}-{question_id}"
        for session_id, text in sessions:
            self.memory.add(
                text,
                user_id=self.user_id,
                metadata={"question_id": question_id, "session_id": session_id},
            )

    def search(self, question: str, limit: int) -> list[str]:
        result = self.memory.search(
            question,
            filters={"user_id": self.user_id},
            top_k=limit,
            rerank=False,
        )
        return [
            row["metadata"].get("session_id")
            for row in result.get("results", [])
            if isinstance(row.get("metadata"), dict)
        ]

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real provider comparisons on LongMemEval-S.")
    parser.add_argument("--dataset", default=os.environ.get("LONGMEMEVAL_PATH"), required=False)
    parser.add_argument("--providers", default="clark,mem0")
    parser.add_argument("--max-questions", type=int, default=1)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--checkpoint-dir", default="benchmark/results/provider-checkpoints")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--output", default=None)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    if not args.dataset:
        raise SystemExit("LONGMEMEVAL_PATH or --dataset is required")
    dataset = Path(args.dataset).expanduser()
    records = load_dataset(dataset)[: args.max_questions]
    run_id = args.run_id or f"provider-compare-{uuid.uuid4()}"
    checkpoint_dir = Path(args.checkpoint_dir)

    all_results: dict[str, Any] = {
        "benchmark": "LongMemEval-S provider comparison",
        "dataset": str(dataset),
        "max_questions": args.max_questions,
        "run_id": run_id,
        "providers": {},
    }

    for provider_name in [item.strip() for item in args.providers.split(",") if item.strip()]:
        adapter = build_adapter(provider_name, run_id)
        started = time.time()
        checkpoint_path = checkpoint_dir / f"{run_id}.{adapter.name}.jsonl"
        try:
            result = run_provider(
                adapter,
                records,
                checkpoint_path=checkpoint_path,
                resume=args.resume,
                sleep_seconds=args.sleep_seconds,
            )
            result["status"] = "completed"
        except Exception as exc:
            result = metrics_from_checkpoint(adapter.name, checkpoint_path)
            result["status"] = "failed"
            result["error"] = str(exc)
            result["error_type"] = type(exc).__name__
            if not result["total"]:
                raise
        finally:
            result["elapsed_seconds"] = round(time.time() - started, 3)
            result["checkpoint"] = str(checkpoint_path)
            all_results["providers"][adapter.name] = result
            print_report(result)
            if args.cleanup:
                adapter.cleanup()

    output_path = Path(args.output) if args.output else Path("benchmark/results/provider-comparison.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False) + "\n")
    print(f"Saved comparison to {output_path}")
    return 0


def build_adapter(provider_name: str, run_id: str) -> MemoryAdapter:
    if provider_name == "clark":
        return ClarkAdapter(run_id)
    if provider_name == "mem0":
        return Mem0Adapter(run_id, Path("benchmark/provider_state") / run_id / "mem0")
    raise SystemExit(f"Unsupported provider: {provider_name}")


def run_provider(
    adapter: MemoryAdapter,
    records: list[dict[str, Any]],
    *,
    checkpoint_path: Path,
    resume: bool = False,
    sleep_seconds: float = 0.0,
) -> dict[str, Any]:
    metrics = empty_metrics(adapter.name)
    completed_question_ids: set[str] = set()
    if resume:
        completed_question_ids = load_checkpoint(adapter.name, checkpoint_path, metrics)

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

        adapter.index_sessions(item["question_id"], item["sessions"])
        ranked_session_ids = adapter.search(item["question"], max(TOP_K_VALUES))

        question_type = item["question_type"]
        metrics["total"] += 1
        metrics["by_type"].setdefault(question_type, {"total": 0, "hits": {}})
        metrics["by_type"][question_type]["total"] += 1
        gold = set(item["gold_session_ids"])
        hits_for_checkpoint: dict[str, bool] = {}
        for top_k in TOP_K_VALUES:
            key = f"recall@{top_k}"
            if set(ranked_session_ids[:top_k]) & gold:
                metrics["recall_at_k"][key] = metrics["recall_at_k"].get(key, 0) + 1
                hits = metrics["by_type"][question_type]["hits"]
                hits[key] = hits.get(key, 0) + 1
                hits_for_checkpoint[key] = True
            else:
                hits_for_checkpoint[key] = False

        write_checkpoint(
            checkpoint_path,
            {
                "status": "scored",
                "question_id": item["question_id"],
                "question_type": question_type,
                "gold_session_ids": item["gold_session_ids"],
                "ranked_session_ids": ranked_session_ids[: max(TOP_K_VALUES)],
                "hits": hits_for_checkpoint,
            },
        )

        if index % 5 == 0:
            hits = metrics["recall_at_k"].get("recall@5", 0)
            print(f"[{adapter.name} {index}/{len(records)}] recall@5={hits / max(1, metrics['total']):.3f}")
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return metrics


def empty_metrics(system: str) -> dict[str, Any]:
    return {
        "benchmark": "LongMemEval-S provider comparison",
        "system": system,
        "total": 0,
        "skipped_abstention": 0,
        "skipped_invalid": 0,
        "recall_at_k": {},
        "by_type": {},
        "failures": [],
    }


def load_checkpoint(system: str, path: Path, metrics: dict[str, Any]) -> set[str]:
    completed: set[str] = set()
    if not path.exists():
        return completed
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        question_id = entry.get("question_id")
        if question_id:
            completed.add(str(question_id))
        status = entry.get("status")
        if status == "scored":
            question_type = str(entry["question_type"])
            metrics["total"] += 1
            metrics["by_type"].setdefault(question_type, {"total": 0, "hits": {}})
            metrics["by_type"][question_type]["total"] += 1
            for key, hit in entry.get("hits", {}).items():
                if hit:
                    metrics["recall_at_k"][key] = metrics["recall_at_k"].get(key, 0) + 1
                    hits = metrics["by_type"][question_type]["hits"]
                    hits[key] = hits.get(key, 0) + 1
        elif status == "abstention":
            metrics["skipped_abstention"] += 1
        elif status == "invalid":
            metrics["skipped_invalid"] += 1
            metrics["failures"].append(entry)
    metrics["system"] = system
    return completed


def metrics_from_checkpoint(system: str, path: Path) -> dict[str, Any]:
    metrics = empty_metrics(system)
    load_checkpoint(system, path, metrics)
    return metrics


def write_checkpoint(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def require_env(name: str) -> None:
    if not os.environ.get(name):
        raise SystemExit(f"{name} is required")


if __name__ == "__main__":
    raise SystemExit(main())
