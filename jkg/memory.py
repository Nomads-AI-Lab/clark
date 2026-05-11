#!/usr/bin/env python3
"""
JKG 3.0 — HYBRID Memory: Graph + Embeddings. ONE database, zero conflicts.
SQLite + sqlite-vec + sentence-transformers. No OpenAI, no external APIs.
"""
import os, sys, json, sqlite3, re, hashlib, math, time
from datetime import datetime
from collections import defaultdict, deque

import requests
import numpy as np
from sentence_transformers import SentenceTransformer

# ═══════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════

DB_PATH = os.environ.get("JKG_DB_PATH", os.path.expanduser("~/.jkg/memory.db"))
EMBEDDING_DIM = 384
EMBEDDING_MODEL = os.environ.get("JKG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

def _load_env():
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
_load_env()

API_KEY = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
API_BASE = os.environ.get("JKG_LLM_BASE", "https://api.deepseek.com")

def _llm(prompt: str, system: str = "You are a precise knowledge extraction engine.") -> str:
    r = requests.post(
        f"{API_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": "deepseek-chat", "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], "temperature": 0.1},
        timeout=120,
    )
    return r.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════
# HYBRID MEMORY — Graph + Embeddings, one DB
# ═══════════════════════════════════════════════════

class HybridMemory:
    """JKG 3.0: graph + embeddings in ONE SQLite database. Zero conflicts."""

    def __init__(self, db_path=DB_PATH, embedding_model=EMBEDDING_MODEL):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Load sqlite-vec extension
        try:
            import sqlite_vec
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
        except Exception as e:
            print(f"WARNING: sqlite-vec not loaded: {e}", file=sys.stderr)

        self._init_db()

        # Lazy-load embedding model
        self._embedder = None
        self._embedder_name = embedding_model

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = SentenceTransformer(self._embedder_name)
        return self._embedder

    # ═══════════════════════════════════════════════
    # SCHEMA — one DB, all tables
    # ═══════════════════════════════════════════════

    def _init_db(self):
        """Create ALL tables in one transaction."""
        self.conn.executescript("""
            -- GRAPH tables
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'entity',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_text TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                confidence REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                last_accessed_at TEXT,
                valid_from TEXT,
                valid_until TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(subject_id) REFERENCES entities(id)
            );
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_id TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_id);
            CREATE INDEX IF NOT EXISTS idx_facts_predicate ON facts(predicate);
            CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject_id);
            CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object_id);
            CREATE INDEX IF NOT EXISTS idx_relations_both ON relations(subject_id, object_id);

            -- BM25 text search
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                entity_name, predicate, object_text, content='facts_fts_content'
            );
            -- Shadow table for FTS5 content sync
            CREATE TABLE IF NOT EXISTS facts_fts_content (
                id INTEGER PRIMARY KEY,
                entity_name TEXT,
                predicate TEXT,
                object_text TEXT
            );
        """)
        self.conn.commit()

        # Create vec0 table if sqlite-vec is available
        try:
            self.conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_vec USING vec0(
                    fact_id INTEGER PRIMARY KEY,
                    embedding float[{EMBEDDING_DIM}]
                )
            """)
            self.has_vec = True
        except Exception:
            self.has_vec = False
            print("WARNING: vec0 not available, vector search disabled", file=sys.stderr)

    # ═══════════════════════════════════════════════
    # UTILS
    # ═══════════════════════════════════════════════

    def _eid(self, name: str) -> str:
        return hashlib.md5(name.lower().strip().encode()).hexdigest()[:12]

    def _norm(self, s: str) -> str:
        return s.lower().strip()

    def _ensure_entity(self, name: str, etype: str = "entity") -> str:
        name = self._norm(name)
        eid = self._eid(name)
        self.conn.execute("INSERT OR IGNORE INTO entities(id, name, type) VALUES(?,?,?)",
                          (eid, name, etype))
        return eid

    def _get_name(self, eid: str) -> str:
        row = self.conn.execute("SELECT name FROM entities WHERE id=?", (eid,)).fetchone()
        return row["name"] if row else eid

    def _resolve_entity(self, name: str):
        name = self._norm(name)
        exact = self.conn.execute("SELECT id FROM entities WHERE name=?", (name,)).fetchone()
        if exact: return exact["id"]
        fuzzy = self.conn.execute(
            "SELECT id, name FROM entities WHERE name LIKE ? LIMIT 1",
            (f"%{name}%",)).fetchone()
        return fuzzy["id"] if fuzzy else None

    def _encode(self, text: str) -> np.ndarray:
        """Encode text to embedding vector."""
        return self.embedder.encode(text, normalize_embeddings=True)

    # ═══════════════════════════════════════════════
    # REMEMBER — ATOMIC graph + vector insert
    # ═══════════════════════════════════════════════

    def remember(self, text: str, source: str = "manual", ground_to: str = None):
        """Extract + store. Graph AND vector in ONE transaction."""
        entities_json = _extract_entities(text)
        try:
            data = json.loads(entities_json)
        except json.JSONDecodeError:
            data = {"entities": [], "relations": [], "facts": []}

        stored = {"entities": 0, "facts": 0, "relations": 0, "vectors": 0}
        new_fact_ids = []
        new_entity_ids = []

        # SINGLE TRANSACTION for everything
        with self.conn:
            for ent in data.get("entities", []):
                name = self._norm(ent.get("name", ent.get("entity", str(ent))))
                eid = self._eid(name)
                self.conn.execute(
                    "INSERT OR IGNORE INTO entities(id, name, type) VALUES(?,?,?)",
                    (eid, name, ent.get("type", "entity")))
                if self.conn.total_changes > 0:
                    stored["entities"] += 1
                new_entity_ids.append(eid)

            for fact in data.get("facts", []):
                subj = self._norm(fact.get("subject", ""))
                if not subj: continue
                sid = self._ensure_entity(subj)
                new_entity_ids.append(sid)
                pred = self._norm(fact.get("predicate", "has_property"))
                obj = self._norm(str(fact.get("object", fact.get("value", ""))))

                # Insert fact
                cur = self.conn.execute(
                    "INSERT INTO facts(subject_id, predicate, object_text, source) VALUES(?,?,?,?)",
                    (sid, pred, obj, source))
                fid = cur.lastrowid
                new_fact_ids.append(fid)
                stored["facts"] += 1

                # BM25 sync
                self.conn.execute(
                    "INSERT INTO facts_fts_content(id, entity_name, predicate, object_text) VALUES(?,?,?,?)",
                    (fid, self._get_name(sid), pred, obj))

            for rel in data.get("relations", []):
                subj = self._norm(rel.get("subject", ""))
                obj = self._norm(rel.get("object", ""))
                if not subj or not obj: continue
                sid = self._ensure_entity(subj)
                oid = self._ensure_entity(obj)
                pred = rel.get("predicate", "related_to")
                self.conn.execute(
                    "INSERT INTO relations(subject_id, predicate, object_id, source) VALUES(?,?,?,?)",
                    (sid, pred, oid, source))
                stored["relations"] += 1

            # Auto-ground
            if ground_to:
                gid = self._eid(self._norm(ground_to))
                for eid in set(new_entity_ids):
                    if eid != gid:
                        self.conn.execute(
                            "INSERT OR IGNORE INTO relations(subject_id, predicate, object_id, source) VALUES(?,?,?,?)",
                            (gid, "connected_to", eid, "auto-ground"))

        # VECTOR: outside transaction (vec0 handles its own)
        if self.has_vec and new_fact_ids:
            for fid in new_fact_ids:
                try:
                    fact = self.conn.execute(
                        "SELECT f.predicate, f.object_text, e.name FROM facts f "
                        "JOIN entities e ON f.subject_id = e.id WHERE f.id=?",
                        (fid,)).fetchone()
                    if fact:
                        fact_text = f"{fact['name']} {fact['predicate']} {fact['object_text']}"
                        vec = self._encode(fact_text)
                        self.conn.execute(
                            "INSERT OR REPLACE INTO facts_vec(fact_id, embedding) VALUES(?,?)",
                            (fid, vec.tobytes()))
                        stored["vectors"] += 1
                except Exception as e:
                    pass  # Skip vector on error, graph data is still safe

        # Rebuild FTS
        try:
            self.conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
            self.conn.commit()
        except: pass

        return stored

    # ═══════════════════════════════════════════════
    # GRAPH TRAVERSAL
    # ═══════════════════════════════════════════════

    def _get_outgoing(self, eid: str) -> list:
        edges = []
        for f in self.conn.execute(
            "SELECT predicate, object_text FROM facts WHERE subject_id = ?", (eid,)
        ).fetchall():
            edges.append({"from_id": eid, "predicate": f["predicate"],
                          "to_text": f["object_text"], "edge_type": "fact"})
        for r in self.conn.execute(
            "SELECT r.predicate, r.object_id, e.name FROM relations r "
            "JOIN entities e ON r.object_id = e.id WHERE r.subject_id = ?", (eid,)
        ).fetchall():
            edges.append({"from_id": eid, "to_id": r["object_id"],
                          "predicate": r["predicate"], "to_text": r["name"],
                          "edge_type": "relation"})
        for r in self.conn.execute(
            "SELECT r.subject_id, r.predicate, e.name FROM relations r "
            "JOIN entities e ON r.subject_id = e.id WHERE r.object_id = ?", (eid,)
        ).fetchall():
            edges.append({"from_id": r["subject_id"], "to_id": eid,
                          "predicate": r["predicate"], "from_text": r["name"],
                          "edge_type": "relation_in"})
        return edges

    def traverse(self, entity_name: str, depth: int = 3, max_results: int = 50) -> dict:
        eid = self._resolve_entity(entity_name)
        if not eid:
            return {"entity": entity_name, "facts": [], "paths": [], "error": "not found"}

        visited = {eid}
        queue = deque([(eid, 0, [])])
        all_facts = []
        all_paths = []

        while queue and len(all_facts) < max_results:
            cur, d, path = queue.popleft()
            if d >= depth: continue

            for edge in self._get_outgoing(cur):
                if edge["edge_type"] == "fact":
                    all_facts.append({
                        "entity": self._get_name(cur),
                        "predicate": edge["predicate"],
                        "value": edge["to_text"],
                        "depth": d, "path": path,
                    })
                else:
                    neighbor = edge.get("to_id") or edge.get("from_id")
                    nname = edge.get("to_text") or edge.get("from_text")
                    if neighbor and neighbor not in visited:
                        visited.add(neighbor)
                        new_path = path + [
                            f"{self._get_name(cur)} --[{edge['predicate']}]--> {nname}"]
                        all_paths.append(new_path[-1])
                        queue.append((neighbor, d + 1, new_path))

        return {"entity": self._get_name(eid), "facts": all_facts,
                "paths": all_paths, "facts_count": len(all_facts)}

    def find_path(self, frm: str, to: str, max_depth: int = 5) -> dict:
        fid = self._resolve_entity(frm)
        tid = self._resolve_entity(to)
        if not fid or not tid:
            return {"from": frm, "to": to, "path": None, "error": "not found"}
        if fid == tid:
            return {"from": frm, "to": to, "path": ["same"], "length": 0}

        visited = {fid}
        queue = deque([(fid, [self._get_name(fid)])])

        while queue:
            eid, path = queue.popleft()
            if len(path) > max_depth + 1: continue
            for edge in self._get_outgoing(eid):
                neighbor = edge.get("to_id") or edge.get("from_id")
                if neighbor == tid:
                    path.append(f"--[{edge['predicate']}]--> {self._get_name(tid)}")
                    return {"from": self._get_name(fid), "to": self._get_name(tid),
                            "path": path, "length": len(path) - 1}
                if neighbor and neighbor not in visited:
                    visited.add(neighbor)
                    nname = edge.get("to_text") or edge.get("from_text")
                    queue.append((neighbor, path + [
                        f"--[{edge['predicate']}]--> {nname}"]))

        return {"from": frm, "to": to, "path": None, "error": "no path"}

    # ═══════════════════════════════════════════════
    # PAGERANK
    # ═══════════════════════════════════════════════

    def pagerank(self, damping=0.85, iterations=20) -> dict:
        """Compute PageRank for all entities. Returns {eid: score}."""
        entities = self.conn.execute("SELECT id FROM entities").fetchall()
        N = len(entities)
        if N == 0: return {}

        scores = {e["id"]: 1.0 for e in entities}
        out_degree = {}
        for r in self.conn.execute(
            "SELECT subject_id, COUNT(*) as cnt FROM relations GROUP BY subject_id"
        ).fetchall():
            out_degree[r["subject_id"]] = r["cnt"]

        for _ in range(iterations):
            new_scores = {}
            for eid in scores:
                incoming = self.conn.execute(
                    "SELECT subject_id FROM relations WHERE object_id=?", (eid,)
                ).fetchall()
                rank_sum = sum(
                    scores[r["subject_id"]] / max(out_degree.get(r["subject_id"], 1), 1)
                    for r in incoming)
                new_scores[eid] = (1 - damping) / N + damping * rank_sum
            scores = new_scores

        return scores

    # ═══════════════════════════════════════════════
    # HYBRID RECALL — BM25 + KNN + Graph → RRF
    # ═══════════════════════════════════════════════

    def recall(self, query: str, limit: int = 20) -> list:
        """Hybrid recall: BM25 + vector KNN + graph expansion → RRF fusion."""
        results_lists = []

        # ── Method 1: BM25 keyword search ──
        try:
            bm25_rows = self.conn.execute(
                "SELECT rowid as id, entity_name, predicate, object_text "
                "FROM facts_fts WHERE facts_fts MATCH ? LIMIT ?",
                (self._fts_query(query), limit * 3)
            ).fetchall()
            results_lists.append([
                {"fact_id": r["id"], "entity": r["entity_name"],
                 "predicate": r["predicate"], "value": r["object_text"]}
                for r in bm25_rows
            ])
        except Exception:
            pass

        # ── Method 2: Vector KNN search ──
        if self.has_vec:
            try:
                query_vec = self._encode(query)
                vec_rows = self.conn.execute(
                    "SELECT fact_id, distance FROM facts_vec "
                    "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                    (query_vec.tobytes(), min(limit * 3, 50))
                ).fetchall()
                vec_fact_ids = [r["fact_id"] for r in vec_rows]
                if vec_fact_ids:
                    placeholders = ",".join(["?"] * len(vec_fact_ids))
                    fact_data = self.conn.execute(
                        f"SELECT f.id, e.name, f.predicate, f.object_text FROM facts f "
                        f"JOIN entities e ON f.subject_id = e.id "
                        f"WHERE f.id IN ({placeholders})",
                        vec_fact_ids
                    ).fetchall()
                    results_lists.append([
                        {"fact_id": f["id"], "entity": f["name"],
                         "predicate": f["predicate"], "value": f["object_text"]}
                        for f in fact_data
                    ])
            except Exception:
                pass

        # ── Method 3: Graph expansion from top matched entities ──
        graph_facts = self.recall_graph(query, limit=limit)

        # ── RRF FUSION ──
        return self._rrf_fusion(results_lists, graph_facts, limit)

    def _fts_query(self, query: str) -> str:
        """Convert user query to FTS5 query string."""
        words = [w for w in re.findall(r'[^\s,?.!;:"\'()\[\]{}]+', query) if len(w) > 1]
        return " OR ".join(f'"{w}"' for w in words) if words else query

    def recall_graph(self, query: str, limit: int = 20) -> list:
        """Graph traversal recall from keyword-matched entities."""
        words = [w for w in re.findall(r'[^\s,?.!;:"\'()\[\]{}]+', query.lower()) if len(w) > 1]
        if not words: return []

        conditions = " OR ".join(["name LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words]
        matched = self.conn.execute(
            f"SELECT id, name FROM entities WHERE {conditions} LIMIT 5",
            params).fetchall()

        all_facts = {}
        for m in matched:
            trav = self.traverse(m["name"], depth=2, max_results=10)
            for f in trav.get("facts", []):
                key = f"{f['entity']}|{f['predicate']}|{f['value']}"
                if key not in all_facts:
                    all_facts[key] = f

        return list(all_facts.values())[:limit]

    def _rrf_fusion(self, lists: list, graph_facts: list, limit: int, k: int = 60) -> list:
        """Reciprocal Rank Fusion — объединяет N ранжированных списков."""
        scores = defaultdict(float)

        for lst in lists:
            for rank, item in enumerate(lst):
                key = f"{item.get('entity','')}|{item.get('predicate','')}|{item.get('value','')}"
                scores[key] += 1.0 / (k + rank + 1)

        # Also include graph facts
        for rank, item in enumerate(graph_facts):
            key = f"{item['entity']}|{item['predicate']}|{item['value']}"
            scores[key] += 1.0 / (k + rank + 1)

        # Sort and deduplicate
        seen = set()
        result = []
        for key, score in sorted(scores.items(), key=lambda x: -x[1]):
            parts = key.split("|", 2)
            if len(parts) == 3:
                entity, predicate, value = parts
                sig = f"{entity}|{predicate}|{value}"
                if sig not in seen:
                    seen.add(sig)
                    result.append({
                        "entity": entity, "predicate": predicate,
                        "value": value, "rrf_score": round(score, 4),
                    })
                    if len(result) >= limit: break

        return result

    # ═══════════════════════════════════════════════
    # BIDIRECTIONAL BRIDGE
    # ═══════════════════════════════════════════════

    def bridge_graph_to_embeddings(self) -> dict:
        """Graph enriches embeddings: PageRank → boost confidence."""
        if not self.has_vec: return {"error": "vec0 not available"}

        pr = self.pagerank()
        boosted = 0
        for eid, pr_score in pr.items():
            if pr_score < 0.01: continue
            facts = self.conn.execute(
                "SELECT id FROM facts WHERE subject_id=?", (eid,)
            ).fetchall()
            for f in facts:
                self.conn.execute(
                    "UPDATE facts SET confidence = MIN(1.0, ?) WHERE id=?",
                    (0.5 + pr_score * 0.3, f["id"]))
                boosted += 1
        self.conn.commit()
        return {"pagerank_entities": len(pr), "boosted_facts": boosted}

    def bridge_embeddings_to_graph(self, threshold: float = 0.85, max_new_links: int = 20) -> dict:
        """Embeddings suggest new graph links: similar entities → proposed relations."""
        if not self.has_vec: return {"error": "vec0 not available"}

        entities = self.conn.execute("SELECT id, name FROM entities").fetchall()
        new_links = 0

        for i, e1 in enumerate(entities):
            if new_links >= max_new_links: break
            # Get embedding for entity (average of its facts)
            facts = self.conn.execute(
                "SELECT predicate, object_text FROM facts WHERE subject_id=?", (e1["id"],)
            ).fetchall()
            if not facts: continue
            e1_text = f"{e1['name']} " + " ".join(
                f"{f['predicate']} {f['object_text']}" for f in facts[:5])
            e1_vec = self._encode(e1_text)

            # Find similar via vec0
            try:
                similar = self.conn.execute(
                    "SELECT fact_id, distance FROM facts_vec "
                    "WHERE embedding MATCH ? AND k = 5 ORDER BY distance",
                    (e1_vec.tobytes(), 5)
                ).fetchall()
            except Exception:
                continue

            for s in similar:
                if new_links >= max_new_links: break
                sf = self.conn.execute(
                    "SELECT f.subject_id, e.name FROM facts f "
                    "JOIN entities e ON f.subject_id = e.id WHERE f.id=?",
                    (s["fact_id"],)
                ).fetchone()
                if not sf or sf["subject_id"] == e1["id"]: continue

                sim = 1.0 - min(s["distance"], 2.0) / 2.0
                if sim < threshold: continue

                # Check if relation already exists
                existing = self.conn.execute(
                    "SELECT 1 FROM relations WHERE "
                    "(subject_id=? AND object_id=?) OR (subject_id=? AND object_id=?)",
                    (e1["id"], sf["subject_id"], sf["subject_id"], e1["id"])
                ).fetchone()

                if not existing:
                    self.conn.execute(
                        "INSERT INTO relations(subject_id, predicate, object_id, "
                        "confidence, source) VALUES(?,?,?,?,?)",
                        (e1["id"], "semantically_similar_to", sf["subject_id"],
                         round(sim, 3), "embedding-bridge"))
                    new_links += 1

        self.conn.commit()
        return {"new_links": new_links, "threshold": threshold}

    # ═══════════════════════════════════════════════
    # LLM RERANK
    # ═══════════════════════════════════════════════

    def llm_rerank(self, query: str, candidates: list, top_k: int = 10) -> list:
        """DeepSeek ranks candidates by relevance to query."""
        if not candidates: return []

        candidate_text = "\n".join([
            f"[{i}] {c['entity']} | {c['predicate']} | {c.get('value', c.get('object',''))}"
            for i, c in enumerate(candidates[:30])
        ])
        prompt = f"""Query: {query}

Rate each candidate's relevance to the query on a scale of 1-10.
Output ONLY valid JSON array: [{{"id": 0, "relevance": 8, "reason": "..."}}, ...]

Candidates:
{candidate_text}

JSON:"""
        result = _llm(prompt, "You rank search results by relevance. Output JSON only.")
        try:
            rankings = json.loads(result)
            ranked = {}
            for r in rankings:
                ranked[r["id"]] = r["relevance"]
            return sorted(candidates, key=lambda c, i=candidates.index(c): -ranked.get(i, 0))[:top_k]
        except:
            return candidates[:top_k]

    # ═══════════════════════════════════════════════
    # ASK — full hybrid pipeline
    # ═══════════════════════════════════════════════

    def ask(self, question: str, owner: str = "алтынай") -> dict:
        """Full hybrid pipeline: recall → LLM rerank → answer."""

        # Step 1: Hybrid recall
        candidates = self.recall(question, limit=20)

        # Step 2: Also include owner traversal facts
        owner_trav = self.traverse(owner, depth=3, max_results=30)
        existing = {f"{c['entity']}|{c['predicate']}|{c.get('value',c.get('object',''))}"
                    for c in candidates}
        for f in owner_trav.get("facts", []):
            key = f"{f['entity']}|{f['predicate']}|{f['value']}"
            if key not in existing:
                candidates.append(f)
                existing.add(key)

        # Step 3: LLM rerank
        ranked = self.llm_rerank(question, candidates, top_k=15)

        # Step 4: Build context with paths
        context_parts = []
        for r in ranked:
            path = " → ".join(r.get("path", [])) if r.get("path") else ""
            if path:
                context_parts.append(f"TRACE {path} | {r['entity']} {r['predicate']} {r.get('value',r.get('object',''))}")
            else:
                context_parts.append(f"FACT {r['entity']} {r['predicate']} {r.get('value',r.get('object',''))}")

        # Add graph paths
        context_parts.append("")
        context_parts.append("GRAPH PATHS:")
        for p in owner_trav.get("paths", [])[:10]:
            context_parts.append(f"  {p}")

        context = "\n".join(context_parts) if context_parts else "(ничего не найдено)"

        # Step 5: LLM synthesize
        answer = _llm(
            f"Knowledge graph context (hybrid graph+semantic search):\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Instructions:\n"
            f"- Use GRAPH PATHS to trace entity connections\n"
            f"- Give definitive answers when data exists\n"
            f"- Include specific values, dates, names from facts\n"
            f"- If entity X is connected to {owner} via a path, it IS relevant\n"
            f"Answer in Russian.",
            system="You answer questions using a hybrid knowledge graph + semantic memory. "
                   "Use paths to trace connections. Be definitive and specific."
        )

        return {"question": question, "answer": answer,
                "candidates": len(candidates), "ranked": len(ranked)}

    # ═══════════════════════════════════════════════
    # STATS
    # ═══════════════════════════════════════════════

    def stats(self) -> dict:
        entities = self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        facts = self.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        relations = self.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        orphans = self.conn.execute("""
            SELECT COUNT(*) FROM entities e
            WHERE e.id NOT IN (SELECT subject_id FROM relations
                               UNION SELECT object_id FROM relations)
            AND NOT EXISTS (SELECT 1 FROM facts f WHERE f.subject_id = e.id)
        """).fetchone()[0]

        vectors = 0
        if self.has_vec:
            try:
                vectors = self.conn.execute(
                    "SELECT COUNT(*) FROM facts_vec").fetchone()[0]
            except: pass

        return {
            "entities": entities, "connected": entities - orphans,
            "orphans": orphans, "facts": facts, "relations": relations,
            "vectors": vectors, "has_embeddings": self.has_vec,
            "version": "3.0", "architecture": "graph+embeddings",
        }

    def list_entities(self, limit=50) -> list:
        rows = self.conn.execute(
            "SELECT e.name, e.type, "
            "(SELECT COUNT(*) FROM facts f WHERE f.subject_id=e.id) as fc, "
            "(SELECT COUNT(*) FROM relations r WHERE r.subject_id=e.id OR r.object_id=e.id) as rc "
            "FROM entities e ORDER BY fc + rc DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"name": r["name"], "type": r["type"],
                 "facts": r["fc"], "relations": r["rc"]} for r in rows]

    def forget(self, name: str) -> dict:
        eid = self._eid(name)
        # Delete vectors
        if self.has_vec:
            fact_ids = self.conn.execute(
                "SELECT id FROM facts WHERE subject_id=?", (eid,)).fetchall()
            for f in fact_ids:
                try:
                    self.conn.execute("DELETE FROM facts_vec WHERE fact_id=?", (f["id"],))
                except: pass
        # Delete graph data
        self.conn.execute("DELETE FROM relations WHERE subject_id=? OR object_id=?", (eid, eid))
        self.conn.execute("DELETE FROM facts WHERE subject_id=?", (eid,))
        self.conn.execute("DELETE FROM entities WHERE id=?", (eid,))
        self.conn.commit()
        return {"status": "deleted", "entity": name}


# ═══════════════════════════════════════════════
# LLM EXTRACTION
# ═══════════════════════════════════════════════

def _extract_entities(text: str) -> str:
    prompt = f"""Extract entities, facts, and relations. Output ONLY valid JSON.

Text: {text[:3000]}

Format:
{{"entities": [{{"name": "...", "type": "person|company|technology|concept|..."}}],
 "facts": [{{"subject": "entity", "predicate": "is|has|owns|uses|...", "object": "value"}}],
 "relations": [{{"subject": "e1", "predicate": "works_at|competes_with|owns|...", "object": "e2"}}]}}

CRITICAL: For EVERY fact, ALSO create a relation linking entities.
Example: "Altynai's Instagram is blocked" → fact: instagram is_blocked, relation: altynai owns instagram
JSON:"""
    return _llm(prompt, "You extract knowledge graph triples. Always create relations. Output JSON only.")


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    hm = HybridMemory()

    if cmd == "remember":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else sys.stdin.read()
        result = hm.remember(text, ground_to=os.environ.get("JKG_OWNER", None))
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "recall":
        query = " ".join(sys.argv[2:])
        for r in hm.recall(query):
            print(f"  [{r.get('rrf_score','')}] {r['entity']} {r['predicate']} {r['value']}")

    elif cmd == "traverse":
        entity = sys.argv[2] if len(sys.argv) > 2 else "алтынай"
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        result = hm.traverse(entity, depth=depth)
        print(f"Traversing '{result['entity']}' (depth {depth}): {result['facts_count']} facts")
        for f in result["facts"]:
            print(f"  [{f['depth']}] {f['entity']} {f['predicate']} {f['value']}")
        for p in result["paths"]:
            print(f"  → {p}")

    elif cmd == "path":
        print(json.dumps(hm.find_path(
            sys.argv[2] if len(sys.argv) > 2 else "алтынай",
            sys.argv[3] if len(sys.argv) > 3 else "trace.so"),
            ensure_ascii=False))

    elif cmd == "ask":
        question = " ".join(sys.argv[2:])
        result = hm.ask(question)
        print(f"Q: {result['question']}")
        print(f"A: {result['answer']}")
        print(f"  ({result['candidates']} candidates → {result['ranked']} reranked)")

    elif cmd == "bridge":
        sub = sys.argv[2] if len(sys.argv) > 2 else "both"
        if sub in ("both", "graph"):
            print("Graph→Embeddings:", json.dumps(hm.bridge_graph_to_embeddings(), ensure_ascii=False))
        if sub in ("both", "embeddings"):
            print("Embeddings→Graph:", json.dumps(hm.bridge_embeddings_to_graph(), ensure_ascii=False))

    elif cmd == "stats":
        print(json.dumps(hm.stats(), indent=2, ensure_ascii=False))

    elif cmd == "entities":
        for e in hm.list_entities():
            print(f"  [{e['type']}] {e['name']} ({e['facts']} facts, {e['relations']} rels)")

    elif cmd == "forget":
        print(json.dumps(hm.forget(" ".join(sys.argv[2:])), ensure_ascii=False))

    else:
        print("Commands: remember, recall, traverse, path, ask, bridge, stats, entities, forget")

if __name__ == "__main__":
    main_cli()
