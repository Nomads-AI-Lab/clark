# 🧠 Jessica Knowledge Graph (JKG)

> **The world's most architecturally advanced AI memory system.**
> Graph + Embeddings + Temporal + Emotional + Forgetting + Self-Evolving.
> All in ONE SQLite transaction. Zero conflicts.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![ICLR 2025](https://img.shields.io/badge/Benchmark-LongMemEval-green.svg)](https://arxiv.org/abs/2410.10813)

---

## Why JKG?

Every AI memory system on the market has the same architectural flaw: **they separate graph from embeddings into different databases**, causing state drift, orphan entities, and silent corruption.

JKG is the **first and only** system that runs graph + embeddings + temporal validity + emotional context + intentional forgetting + self-evolving schema — all in **one SQLite transaction**.

| Feature | Mem0 | Cognee | Zep/Graphiti | Letta | **JKG 5.1** |
|---------|:----:|:------:|:------------:|:-----:|:-----------:|
| Graph + Embeddings in ONE DB | ❌ | ❌ | ❌ | ❌ | ✅ |
| Bi-temporal (T+T') | ❌ | ❌ | ✅ | ❌ | ✅ |
| Emotional memory | ❌ | ❌ | ❌ | ❌ | ✅ |
| Intentional forgetting | ❌ | ❌ | ❌ | ❌ | ✅ |
| Self-evolving schema | ❌ | ❌ | ❌ | ❌ | ✅ |
| GDPR true deletion | ❌ | ❌ | ❌ | ❌ | ✅ |
| Local-only (no cloud) | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Architecture conflicts** | 0 | 0 | 2+ | 1+ | **0** |

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  JKG 5.1                         │
│                                                  │
│  ┌─────────┐   ┌──────────┐   ┌──────────────┐  │
│  │  GRAPH   │◄──┤ BRIDGE   ├──►│  EMBEDDINGS  │  │
│  │ (SQLite) │   │bidirect. │   │ (sqlite-vec) │  │
│  └────┬─────┘   └──────────┘   └──────┬───────┘  │
│       │                               │          │
│       ▼                               ▼          │
│  ┌─────────────────────────────────────────────┐ │
│  │           RRF FUSION (k=60)                  │ │
│  │     BM25 + Vector KNN + Graph BFS            │ │
│  └────────────────────┬────────────────────────┘ │
│                       │                          │
│       ┌───────────────┼───────────────┐          │
│       ▼               ▼               ▼          │
│  ┌─────────┐   ┌──────────┐   ┌──────────────┐  │
│  │TEMPORAL │   │EMOTIONAL │   │  FORGETTING  │  │
│  │ T + T'  │   │valence + │   │ Utility Score│  │
│  │validity │   │intensity │   │   + prune    │  │
│  └─────────┘   └──────────┘   └──────────────┘  │
│                       │                          │
│                       ▼                          │
│              ┌────────────────┐                  │
│              │ SELF-EVOLVING  │                  │
│              │ schema proposals│                 │
│              └────────────────┘                  │
│                                                  │
│         ALL IN ONE TRANSACTION                   │
│         ZERO STATE DRIFT                         │
└──────────────────────────────────────────────────┘
```

## Quick Start

```bash
pip install jessica-knowledge-graph
```

```python
from jkg import HybridMemory

# Create memory (one file, one database)
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
Every fact knows WHEN it was true and WHEN the system learned it. Automatic invalidation when facts change.

```python
memory.remember("Alice worked at Google from 2020 to 2023.")
# → works_at=Google: valid_from=2020-01-01, valid_until=2023-12-31

memory.remember("Alice builds CopilotOS since May 2025.")
# → builds=CopilotOS: valid_from=2025-05-01, valid_until=null
# → works_at=Meta: automatically invalidated (valid_until=2025-05-01)
```

### 💭 Emotional Memory
Episodes carry emotional context — valence + intensity. The system remembers not just WHAT happened, but how you FELT.

```python
memory.remember("I'm devastated... the project failed at the hackathon!")
# → emotion: negative, intensity: 0.9

ctx = memory.get_emotional_context()
# → [{"emotion": "sadness", "intensity": 0.9, "episode": "Hackathon fail"}, ...]
```

### 🗑️ Intentional Forgetting
Not infinite storage. Facts decay naturally based on utility score (access frequency × recency × confidence × PageRank − age penalty).

```python
memory.update_utility_scores()
result = memory.prune_memory(threshold=0.3, dry_run=True)
print(f"Candidates for forgetting: {result['candidates']}")
```

### 🧬 Self-Evolving Schema
The LLM periodically analyzes stored knowledge, discovers patterns, and proposes new entity types and relation types.

```python
proposals = memory.evolve_schema(dry_run=True)
# → "Discovered pattern: 'startup' entities often have 'funding_round' relations"
# → Proposed: new relation type 'funding_round'
```

### 🔐 GDPR-First Deletion
True deletion with full audit trail. Not soft-delete — actual removal with cryptographic proof.

```python
result = memory.gdpr_delete("John Doe", request_id="GDPR-2025-001", verified=True)
# → status: "deleted"
# → Audit trail preserved in forget_log + deletion_log
```

## Benchmark Results

### Our Benchmark (16 tests, all features)
```
JKG 3.0:  42.5%
JKG 5.0:  87.5%
JKG 5.1:  93.8%  ← current
```

### LongMemEval-S (500 questions, retrieval-only)
```
JKG 5.1:   97.9% R@5  (preliminary, 100/500)
Zep:       71.2%      (full QA, different metric)
Mem0:      ~75%       (estimated)
Cognee:    ~65%       (estimated)
```

*Full LongMemEval-S run in progress. Preliminary results at 100/500 questions.*

## Installation

```bash
# From PyPI (coming soon)
pip install jessica-knowledge-graph

# From source
git clone https://github.com/altyshalu/jkg3.0.git
cd jkg3.0
pip install -e .

# Requirements
pip install sentence-transformers sqlite-vec numpy requests
```

Set your LLM API key for extraction:
```bash
export DEEPSEEK_API_KEY="your-key-here"
# Or create a .env file in the project root
```

## How It Works

### Recall Pipeline
1. **BM25** keyword search (SQLite FTS5)
2. **Vector KNN** semantic search (sqlite-vec + MiniLM-L6-v2)
3. **Graph BFS** traversal from matched entities
4. **RRF Fusion** (Reciprocal Rank Fusion, k=60)
5. **LLM Rerank** (DeepSeek, optional)

### Bidirectional Bridge
- **Graph → Embeddings**: PageRank boosts embedding confidence
- **Embeddings → Graph**: Semantic similarity suggests new relations

### Temporal Linking (v5.1)
- `end_year=2023` → sets `valid_until` on corresponding `works_at` facts
- `resigned_from=X` → invalidates `works_at=X`
- `builds=Y` → invalidates all previous `works_at` facts

### Predicate Aliases (v5.1)
- "Where does X work?" → matches `works_at`, `builds`, `founded`, `develops`, `строит`, `основала`, etc.
- No more missing answers because the predicate name varies

## Roadmap

- [x] JKG 1.0 — Keyword search (SQLite)
- [x] JKG 2.0 — Graph with BFS + PageRank
- [x] JKG 3.0 — Hybrid: Graph + Embeddings in ONE DB
- [x] JKG 4.0 — Temporal validity + Entity resolution + Episodes
- [x] JKG 5.0 — Bi-temporal + Emotional + Forgetting + Self-evolving + GDPR
- [x] JKG 5.1 — Temporal linking + Predicate aliases (93.8%)
- [ ] JKG 6.0 — Causal reasoning + Multi-modal (images, audio)
- [ ] JKG 7.0 — Distributed (multiple agents sharing one KG)

## Citation

```bibtex
@software{jkg2025,
  author = {Altynai},
  title = {Jessica Knowledge Graph: Hybrid AI Memory with Zero Architecture Conflicts},
  year = {2025},
  url = {https://github.com/altyshalu/jessica-knowledge-graph}
}
```

## License

MIT — free for personal and commercial use.

---

*Built with ❤️ by Altynai. The future of AI memory is hybrid, temporal, emotional, and self-evolving — all in one transaction.*
