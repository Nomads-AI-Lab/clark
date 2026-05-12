# 🧠 Jessica Knowledge Graph (JKG)

> **Hybrid AI Memory — Graph + Embeddings in one SQLite transaction.**
> Temporal reasoning, emotional context, intentional forgetting, and self-evolving schema.
> All local. Zero cloud dependencies.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![LongMemEval](https://img.shields.io/badge/LongMemEval--S-96.8%25%20R@5-green.svg)](https://arxiv.org/abs/2410.10813)

---

## Why JKG?

Most AI memory systems keep their knowledge graph and vector embeddings in **separate databases**. This causes state drift — the graph says one thing, embeddings say another.

JKG runs **everything in one SQLite transaction**: graph, embeddings, temporal validity, emotional context, forgetting, and schema evolution — no drift, no orphans.

| Feature | Mem0 | Cognee | Zep | Letta | **JKG** |
|---------|:----:|:------:|:---:|:-----:|:-------:|
| Graph + Embeddings, one DB | — | — | — | — | ✅ |
| Bi-temporal validity (T+T') | — | — | ✅ | — | ✅ |
| Emotional context | — | — | — | — | ✅ |
| Intentional forgetting | — | — | — | — | ✅ |
| Self-evolving schema | — | — | — | — | ✅ |
| GDPR true deletion + audit | — | — | — | — | ✅ |
| Fully local (no cloud APIs*) | — | — | — | — | ✅ |

*\*LLM extraction step is pluggable (DeepSeek by default, works with any OpenAI-compatible API)*

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                    JKG 5.1                        │
│                                                   │
│  ┌─────────┐    ┌──────────┐    ┌──────────────┐ │
│  │  GRAPH   │◄───┤ BRIDGE   ├───►│  EMBEDDINGS  │ │
│  │ (SQLite) │    │bidirect. │    │ (sqlite-vec) │ │
│  └────┬─────┘    └──────────┘    └──────┬───────┘ │
│       │                                 │         │
│       ▼                                 ▼         │
│  ┌──────────────────────────────────────────────┐ │
│  │           RRF FUSION (k=60)                   │ │
│  │      BM25 + Vector KNN + Graph BFS            │ │
│  └────────────────────┬─────────────────────────┘ │
│                       │                           │
│       ┌───────────────┼───────────────┐           │
│       ▼               ▼               ▼           │
│  ┌─────────┐   ┌──────────┐   ┌──────────────┐   │
│  │TEMPORAL │   │EMOTIONAL │   │  FORGETTING  │   │
│  │ T + T'  │   │valence + │   │ Utility Score│   │
│  │validity │   │intensity │   │   + prune    │   │
│  └─────────┘   └──────────┘   └──────────────┘   │
│                       │                           │
│                       ▼                           │
│              ┌────────────────┐                   │
│              │ SELF-EVOLVING  │                   │
│              │schema proposals│                   │
│              └────────────────┘                   │
│                                                   │
│         ONE SQLite. ONE transaction.              │
│         Zero state drift.                         │
└──────────────────────────────────────────────────┘
```

## Quick Start

```bash
pip install jessica-knowledge-graph
```

```python
from jkg import HybridMemory

# One file, one database
memory = HybridMemory("my_memory.db")

# Remember anything — facts, emotions, events
memory.remember("Alice worked at Google from 2020 to 2023.")
memory.remember("Alice switched to Meta in 2023 as Senior Engineer.")
memory.remember("I'm so excited! We won a $50K startup grant!")
memory.remember("Alice quit Meta and builds CopilotOS since May 2025.")

# Ask questions — temporal awareness built in
answer = memory.ask("Where does Alice work now?")
print(answer["answer"])
# → "Alice currently builds CopilotOS since May 2025."

# Ask about the past
answer = memory.ask("Where did Alice work in 2021?")
print(answer["answer"])
# → "Alice worked at Google in 2021."

# Full career timeline
answer = memory.ask("Tell me Alice's entire career")
print(answer["answer"])
# → "Google (2020-2023) → Meta (2023-2025) → CopilotOS (2025-present)"
```

## Features

### 🕐 Temporal Reasoning (Bi-temporal T+T')
Every fact stores both *when it was true* and *when the system learned it*. Automatic invalidation when facts change.

```python
memory.remember("Alice worked at Google from 2020 to 2023.")
# → works_at=Google: valid_from=2020-01-01, valid_until=2023-12-31

memory.remember("Alice builds CopilotOS since May 2025.")
# → builds=CopilotOS: valid_from=2025-05-01, valid_until=null
# → works_at=Meta: auto-invalidated (valid_until=2025-05-01)
```

### 💭 Emotional Memory
Episodes carry emotional context — valence + intensity. Remembers not just what happened, but how you felt.

```python
memory.remember("I'm devastated... the project failed at the hackathon!")
# → emotion: sadness, intensity: 0.9

ctx = memory.get_emotional_context()
# → [{"emotion": "sadness", "intensity": 0.9, ...}, ...]
```

### 🗑️ Intentional Forgetting
Facts decay based on **utility score** (access frequency × recency × confidence × PageRank − age penalty). Old, unused facts are automatically pruned.

```python
memory.update_utility_scores()
result = memory.prune_memory(threshold=0.3, dry_run=True)
print(f"Candidates for forgetting: {result['candidates']}")
```

### 🧬 Self-Evolving Schema
The LLM periodically discovers patterns in stored knowledge and proposes new entity/relation types.

```python
proposals = memory.evolve_schema(dry_run=True)
# → "Discovered: 'startup' entities often have 'funding_round' relations"
```

### 🔐 GDPR-First Deletion
True deletion with full audit trail. Not soft-delete — actual removal from the database.

```python
result = memory.gdpr_delete("John Doe", request_id="GDPR-2025-001", verified=True)
# → status: "deleted", audit trail preserved
```

### 🔗 Temporal Linking (v5.1)
Extracted facts are automatically linked: `end_year=2023` → sets `valid_until` on `works_at`. `builds=Y` → invalidates old `works_at` facts. Career timelines stay consistent.

### 📝 Predicate Aliases (v5.1)
"Where does Alice work?" matches `works_at`, `builds`, `founded`, `develops`, `строит`, `основала`, etc. No missed answers because the predicate name varies.

---

## Benchmarks

### Custom Benchmark (16 tests, all 7 features)
```
JKG 3.0:  42.5%
JKG 5.0:  87.5%
JKG 5.1:  93.8%
```

### LongMemEval-S (470 questions, retrieval-only R@5)
```
knowledge-update           100.0%
single-session-user         98.4%
single-session-assistant    98.2%
multi-session               97.5%
single-session-preference   96.7%
temporal-reasoning          92.9%
─────────────────────────────────
OVERALL R@5:               96.8%
OVERALL R@10:              97.7%
MRR:                       89.0%
```

*Compared to published retrieval-only results on the same benchmark: agentmemory hybrid 95.2%, MemPalace 96.6%.*

---

## Installation

```bash
# From PyPI (coming soon)
pip install jessica-knowledge-graph

# From source
git clone https://github.com/altyshalu/jessica-knowledge-graph.git
cd jessica-knowledge-graph
pip install -e .

# Requirements
pip install sentence-transformers sqlite-vec numpy requests
```

Set your LLM API key for extraction:
```bash
export DEEPSEEK_API_KEY="your-key-here"
# Or any OpenAI-compatible endpoint via OPENAI_API_KEY + OPENAI_BASE_URL
```

---

## How It Works

### Recall Pipeline
1. **BM25** keyword search (SQLite FTS5)
2. **Vector KNN** semantic search (sqlite-vec + MiniLM-L6-v2)
3. **Graph BFS** traversal from matched entities
4. **RRF Fusion** (Reciprocal Rank Fusion, k=60)
5. **LLM Rerank** (DeepSeek or any OpenAI-compatible model)

### Bidirectional Bridge
- **Graph → Embeddings**: PageRank boosts embedding confidence
- **Embeddings → Graph**: Semantic similarity suggests new relations

---

## Roadmap

- [x] JKG 1.0 — Keyword search (SQLite)
- [x] JKG 2.0 — Graph with BFS + PageRank
- [x] JKG 3.0 — Hybrid: Graph + Embeddings in one DB
- [x] JKG 4.0 — Temporal validity + Entity resolution + Episodes
- [x] JKG 5.0 — Bi-temporal + Emotional + Forgetting + Self-evolving + GDPR
- [x] JKG 5.1 — Temporal linking + Predicate aliases
- [ ] JKG 6.0 — Causal reasoning + Multi-modal (images, audio)
- [ ] JKG 7.0 — Distributed (multi-agent shared knowledge graph)

---

## Citation

```bibtex
@software{jkg2025,
  author = {Altynai},
  title = {Jessica Knowledge Graph: Hybrid AI Memory},
  year = {2025},
  url = {https://github.com/altyshalu/jessica-knowledge-graph}
}
```

## License

MIT — free for personal and commercial use.

---

*Built with ❤️ by Altynai*
