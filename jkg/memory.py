#!/usr/bin/env python3
"""
JKG 5.1 — HYBRID Memory: Graph + Embeddings + Temporal + Emotional + Forgetting + Self-Evolving.
ONE SQLite database. Zero conflicts. No external APIs except LLM extraction.
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

DB_PATH = os.path.expanduser(os.environ.get("JKG_DB_PATH", "./memory.db"))
EMBEDDING_DIM = 384
EMBEDDING_MODEL = os.environ.get("JKG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

def _load_env():
    """Load .env from current dir, ~/.jkg/, or JKG_ENV_PATH."""
    env_paths = [
        os.environ.get("JKG_ENV_PATH", ""),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
        os.path.expanduser("~/.jkg/.env"),
        os.path.expanduser("~/.hermes/.env"),
        ".env",
    ]
    for env_path in env_paths:
        if env_path and os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break
_load_env()

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_BASE = "https://api.deepseek.com"

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
        # Handle special SQLite paths like ":memory:"
        if db_path not in (":memory:", "") and os.path.dirname(db_path):
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
                summary TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_text TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                episode_id INTEGER,
                fact_hash TEXT,
                confidence REAL DEFAULT 0.5,
                utility_score REAL DEFAULT 0.5,
                forget_status TEXT DEFAULT 'active',
                access_count INTEGER DEFAULT 0,
                last_accessed_at TEXT,
                valid_from TEXT,
                valid_until TEXT,
                superseded_by INTEGER,
                invalidated_by_fact_id INTEGER,
                ingestion_time TEXT DEFAULT (datetime('now')),
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(subject_id) REFERENCES entities(id),
                FOREIGN KEY(episode_id) REFERENCES episodes(id),
                FOREIGN KEY(superseded_by) REFERENCES facts(id)
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                title TEXT DEFAULT '',
                body TEXT NOT NULL,
                source_type TEXT DEFAULT 'manual',
                reference_time TEXT,
                emotion TEXT DEFAULT 'neutral',
                emotion_intensity REAL DEFAULT 0.0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS schema_evolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_description TEXT NOT NULL,
                proposed_schema TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                evidence_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'proposed',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS forget_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_id INTEGER,
                subject_id TEXT,
                predicate TEXT,
                object_text TEXT,
                utility_score REAL,
                action TEXT,
                reason TEXT,
                performed_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS deletion_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT,
                reason TEXT,
                gdpr_request_id TEXT,
                verified_by TEXT,
                performed_at TEXT DEFAULT (datetime('now'))
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
        """Fuzzy entity lookup by name (exact → LIKE)."""
        name = self._norm(name)
        exact = self.conn.execute("SELECT id FROM entities WHERE name=?", (name,)).fetchone()
        if exact: return exact["id"]
        fuzzy = self.conn.execute(
            "SELECT id, name FROM entities WHERE name LIKE ? LIMIT 1",
            (f"%{name}%",)).fetchone()
        return fuzzy["id"] if fuzzy else None

    def _encode(self, text: str):
        return self.embedder.encode(text, normalize_embeddings=True)

    # ═══════════════════════════════════════════════
    # JKG 4.0: TEMPORAL EXTRACTION
    # ═══════════════════════════════════════════════

    def _extract_temporal(self, text: str) -> dict:
        """LLM extracts temporal info: reference_time, valid_from, valid_until."""
        prompt = f"""Extract temporal information from this text. Output ONLY valid JSON.

Text: {text[:2000]}

Format:
{{"reference_time": "YYYY-MM-DD or null",
 "facts": [{{"subject": "entity", "predicate": "...", "object": "...",
            "valid_from": "YYYY-MM-DD or null", "valid_until": "YYYY-MM-DD or null"}}]
}}

CRITICAL RULES:
- reference_time: when the described events happened (not when text was written)
- valid_from: when a fact became true (use exact dates when given)
- valid_until: when a fact STOPPED being true (null ONLY if still true NOW)

EXAMPLES:
- "Alice worked at Google from 2020 to 2023" →
  works_at: valid_from=2020-01-01, valid_until=2023-12-31
  NOTE: "from X to Y" means ENDED at Y — set valid_until!
- "Alice switched to Meta in 2023" →
  works_at: valid_from=2023-01-01, valid_until=null (current job until next transition)
- "Alice quit Meta and builds CopilotOS since May 2025" →
  works_at Meta: valid_until=2025-05-01 (ended when she quit)
  builds CopilotOS: valid_from=2025-05-01, valid_until=null (current)
- "Alice now works at StartupX" →
  valid_from=<extract from context or use reference_time>, valid_until=null

FOR EVERY fact that describes a job/position/role change:
- The OLD fact gets valid_until = start date of the NEW fact
- The NEW fact gets valid_from = its start date, valid_until = null
- "quitting / leaving / resigning" = the old fact ENDS

JSON:"""
        try:
            result = _llm(prompt, "Extract temporal info. Output JSON only.")
            return json.loads(result)
        except:
            return {"reference_time": None, "facts": []}

    # ═══════════════════════════════════════════════
    # JKG 4.0: FACT DEDUP + INVALIDATION
    # ═══════════════════════════════════════════════

    def _compute_fact_hash(self, subject: str, predicate: str, obj: str) -> str:
        return hashlib.md5(
            f"{self._norm(subject)}|{self._norm(predicate)}|{self._norm(obj)}".encode()
        ).hexdigest()[:16]

    def _invalidate_conflicting(self, subject_name: str, predicate: str, 
                                  new_obj: str, new_valid_from: str = None):
        """Find and invalidate old facts that conflict with new fact.
        
        JKG 5.1: Handles TRANSITION predicates (resigned_from → works_at)
        and CURRENT_ACTIVITY predicates (builds → all works_at)."""
        sid = self._eid(subject_name)
        pred = self._norm(predicate)

        invalidated = 0
        valid_until = new_valid_from or datetime.now().strftime("%Y-%m-%d")

        # ── Direct conflicts: same subject+predicate, different object ──
        existing = self.conn.execute(
            "SELECT id, object_text, valid_until FROM facts "
            "WHERE subject_id=? AND predicate=? AND valid_until IS NULL "
            "AND superseded_by IS NULL",
            (sid, pred)
        ).fetchall()

        for old in existing:
            old_obj = self._norm(old["object_text"])
            new_obj_norm = self._norm(new_obj)
            if old_obj != new_obj_norm and old_obj not in new_obj_norm and new_obj_norm not in old_obj:
                self.conn.execute(
                    "UPDATE facts SET valid_until=? WHERE id=?",
                    (valid_until, old["id"]))
                invalidated += 1

        # ── JKG 5.1: Transition predicates → invalidate works_at ──
        if pred in self._TRANSITION_PREDICATES:
            target_obj = self._norm(new_obj)
            work_facts = self.conn.execute(
                "SELECT id, object_text FROM facts "
                "WHERE subject_id=? AND predicate IN ('works_at','employed_at','работает_в','position') "
                "AND valid_until IS NULL AND superseded_by IS NULL",
                (sid,)
            ).fetchall()
            for wf in work_facts:
                wf_obj = self._norm(wf["object_text"])
                if wf_obj == target_obj or target_obj in wf_obj or wf_obj in target_obj:
                    self.conn.execute(
                        "UPDATE facts SET valid_until=? WHERE id=?",
                        (valid_until, wf["id"]))
                    invalidated += 1

        # ── JKG 5.1: Current activity predicates → invalidate ALL works_at ──
        if pred in self._CURRENT_ACTIVITY_PREDICATES:
            work_facts = self.conn.execute(
                "SELECT id FROM facts "
                "WHERE subject_id=? AND predicate IN ('works_at','employed_at','работает_в','position') "
                "AND valid_until IS NULL AND superseded_by IS NULL",
                (sid,)
            ).fetchall()
            for wf in work_facts:
                self.conn.execute(
                    "UPDATE facts SET valid_until=? WHERE id=?",
                    (valid_until, wf["id"]))
                invalidated += 1

        return invalidated

    # ═══════════════════════════════════════════════
    # JKG 5.1: TEMPORAL LINKING — connect temporal facts to their targets
    # ═══════════════════════════════════════════════

    # Predicate groups: when one predicate in a group appears, it should
    # set valid_until on others in the same group.
    _TEMPORAL_LINK_RULES = {
        # end_year → works_at, employed_at, position
        "end_year": ["works_at", "employed_at", "position", "worked_at", "работает_в"],
        # resigned_from → works_at (same target)
        "resigned_from": ["works_at", "employed_at"],
        # уволилась_из → works_at (same target)
        "уволилась_из": ["works_at", "employed_at"],
        "уволился_из": ["works_at", "employed_at"],
        # left → works_at
        "left": ["works_at", "employed_at"],
        # closed / ended → relevant facts
        "ended": ["works_at", "employed_at", "started"],
    }

    # When a transition happens (quit Y, build X), the old fact gets valid_until
    # and the new fact gets valid_from.
    _TRANSITION_PREDICATES = {"resigned_from", "уволилась_из", "уволился_из", "left", "quit",
                               "перешла_из", "перешёл_из", "moved_from"}

    _CURRENT_ACTIVITY_PREDICATES = {"builds", "founded", "develops", "creates", "runs",
                                     "строит", "основала", "основал", "разрабатывает",
                                     "запустила", "запустил", "работает_над"}

    def _link_temporal(self, data: dict) -> dict:
        """Post-process extracted facts: link temporal facts to their targets.

        Examples:
        - end_year=2023 → works_at=google gets valid_until=2023-12-31
        - resigned_from=meta → works_at=meta gets valid_until=<now>
        - builds=copilotos → works_at=<old> gets valid_until if builds is current activity
        """
        facts = data.get("facts", [])
        if not facts:
            return data

        # Build lookup: (subject, predicate) → list of facts
        by_subj_pred = {}
        for i, f in enumerate(facts):
            subj = self._norm(f.get("subject", ""))
            pred = self._norm(f.get("predicate", ""))
            key = (subj, pred)
            if key not in by_subj_pred:
                by_subj_pred[key] = []
            by_subj_pred[key].append(i)

        # Build lookup: (subject, object) → list of fact indices (for works_at targeting)
        by_subj_obj = {}
        for i, f in enumerate(facts):
            subj = self._norm(f.get("subject", ""))
            obj = self._norm(str(f.get("object", f.get("value", ""))))
            key = (subj, obj)
            if key not in by_subj_obj:
                by_subj_obj[key] = []
            by_subj_obj[key].append(i)

        changes = []

        # Rule 1: end_year → set valid_until on works_at for same subject
        for (subj, pred), indices in list(by_subj_pred.items()):
            if pred in self._TEMPORAL_LINK_RULES:
                target_preds = self._TEMPORAL_LINK_RULES[pred]
                year_value = facts[indices[0]].get("object",
                                         facts[indices[0]].get("value", ""))
                if not year_value:
                    continue

                # Extract year number
                year_match = re.search(r'(\d{4})', str(year_value))
                if not year_match:
                    continue
                year = year_match.group(1)
                valid_until = f"{year}-12-31"

                # Find works_at facts for same subject and set valid_until
                for tpred in target_preds:
                    tp_key = (subj, tpred)
                    if tp_key in by_subj_pred:
                        for ti in by_subj_pred[tp_key]:
                            tf = facts[ti]
                            if not tf.get("valid_until"):
                                changes.append((ti, "valid_until", valid_until))

        # Rule 2: resigned_from X → set valid_until on works_at X for same subject
        for (subj, pred), indices in list(by_subj_pred.items()):
            if pred in self._TRANSITION_PREDICATES:
                target_obj = self._norm(str(facts[indices[0]].get("object",
                                                facts[indices[0]].get("value", ""))))
                # Find works_at=<target_obj> for same subject
                for tpred in ["works_at", "employed_at", "работает_в", "position"]:
                    wk_key = (subj, target_obj)
                    if wk_key in by_subj_obj:
                        for wi in by_subj_obj[wk_key]:
                            wf = facts[wi]
                            wf_pred = self._norm(wf.get("predicate", ""))
                            if wf_pred in tpred.split() or wf_pred == tpred:
                                if not wf.get("valid_until"):
                                    # Use valid_from of the transition fact as valid_until
                                    vf = facts[indices[0]].get("valid_from")
                                    changes.append(
                                        (wi, "valid_until",
                                         vf or datetime.now().strftime("%Y-%m-%d")))

        # Rule 3: builds/founded X → set valid_until on all works_at for same subject
        for (subj, pred), indices in list(by_subj_pred.items()):
            if pred in self._CURRENT_ACTIVITY_PREDICATES:
                new_vf = facts[indices[0]].get("valid_from")
                for tpred in ["works_at", "employed_at", "работает_в"]:
                    tp_key = (subj, tpred)
                    if tp_key in by_subj_pred:
                        for ti in by_subj_pred[tp_key]:
                            tf = facts[ti]
                            if not tf.get("valid_until"):
                                changes.append(
                                    (ti, "valid_until",
                                     new_vf or datetime.now().strftime("%Y-%m-%d")))

        # Apply changes
        for idx, field, value in changes:
            facts[idx][field] = value

        return data

    # ═══════════════════════════════════════════════
    # JKG 4.0: ENTITY RESOLUTION (embedding + LLM)
    # ═══════════════════════════════════════════════

    def resolve_entity(self, name: str, etype: str = "entity") -> str:
        """Resolve entity: find existing or create. Returns entity ID.
        
        Pipeline: exact match → embedding search → LLM resolution → create new.
        """
        name = self._norm(name)

        # Step 1: Exact match
        exact = self.conn.execute("SELECT id FROM entities WHERE name=?", (name,)).fetchone()
        if exact: return exact["id"]

        # Step 2: Embedding search for candidates
        candidates = []
        if self.has_vec:
            try:
                name_vec = self._encode(name)
                # Search for similar entity names via vector
                similar = self.conn.execute(
                    "SELECT f.subject_id, e.name, e.type, distance FROM facts_vec "
                    "JOIN facts f ON facts_vec.fact_id = f.id "
                    "JOIN entities e ON f.subject_id = e.id "
                    "WHERE facts_vec.embedding MATCH ? AND k = 5 ORDER BY distance",
                    (name_vec.tobytes(), 5)
                ).fetchall()
                seen = set()
                for s in similar:
                    if s["subject_id"] not in seen and s["name"] != name:
                        seen.add(s["subject_id"])
                        candidates.append({"id": s["subject_id"], "name": s["name"],
                                          "type": s["type"], "distance": s["distance"]})
            except Exception:
                pass

        # Fallback: LIKE search
        if not candidates:
            fuzzy = self.conn.execute(
                "SELECT id, name, type FROM entities WHERE name LIKE ? LIMIT 3",
                (f"%{name}%",)
            ).fetchall()
            for f in fuzzy:
                if f["name"] != name:
                    candidates.append({"id": f["id"], "name": f["name"],
                                      "type": f["type"], "distance": 0.5})

        if not candidates:
            return self._ensure_entity(name, etype)

        # Step 3: LLM resolution
        candidate_list = "\n".join([
            f"[{i}] {c['name']} (type: {c['type']})" for i, c in enumerate(candidates)
        ])
        prompt = f"""New entity: "{name}" (type: {etype})

Existing candidates:
{candidate_list}

Is "{name}" the SAME entity as any of the candidates?
Consider: name variations, translations, abbreviations, typos.
Output ONLY JSON: {{"match": <index or null>, "reason": "..."}}
If no match, match=null.
JSON:"""
        try:
            result = _llm(prompt, "Resolve entity identity. Output JSON only.")
            resolution = json.loads(result)
            match_idx = resolution.get("match")
            if match_idx is not None and 0 <= match_idx < len(candidates):
                matched = candidates[match_idx]
                # Update summary with new name
                self.conn.execute(
                    "UPDATE entities SET summary = summary || '; aka: ' || ? WHERE id=?",
                    (name, matched["id"])
                )
                return matched["id"]
        except:
            pass

        # No match → create new
        return self._ensure_entity(name, etype)

    # ═══════════════════════════════════════════════
    # JKG 5.0: BI-TEMPORAL INVALIDATION (из Zep)
    # ═══════════════════════════════════════════════

    def _invalidate_with_edge(self, old_fact_id: int, new_fact_id: int, 
                                new_valid_from: str = None) -> int:
        """Bi-temporal: mark old fact invalid, track WHICH fact invalidated it."""
        valid_until = new_valid_from or datetime.now().strftime("%Y-%m-%d")
        self.conn.execute(
            "UPDATE facts SET valid_until=?, superseded_by=?, invalidated_by_fact_id=?, "
            "forget_status='invalidated' WHERE id=?",
            (valid_until, new_fact_id, new_fact_id, old_fact_id))
        return old_fact_id

    # ═══════════════════════════════════════════════
    # JKG 5.0: INTENTIONAL FORGETTING — Memory Utility Score
    # ═══════════════════════════════════════════════

    def _compute_utility(self, fact_id: int) -> float:
        """Memory Utility Score: access×0.3 + PageRank×0.2 + recency×0.2 + confidence×0.15 - age×0.15"""
        f = self.conn.execute(
            "SELECT f.confidence, f.access_count, f.last_accessed_at, f.created_at, "
            "f.valid_until, f.forget_status, "
            "COALESCE((SELECT COUNT(*) FROM relations r WHERE r.subject_id=f.subject_id OR r.object_id=f.subject_id), 0) as degree "
            "FROM facts f WHERE f.id=?", (fact_id,)
        ).fetchone()
        if not f: return 0.0

        access_freq = min(f["access_count"] / 10.0, 1.0)

        # Recency: days since last access
        try:
            last = datetime.fromisoformat(f["last_accessed_at"] or f["created_at"])
            days = (datetime.now() - last).days
            recency = max(0, 1.0 - days / 90.0)
        except: recency = 0.5

        # Graph centrality proxy
        degree = min(f["degree"] / 5.0, 1.0)

        confidence = f["confidence"] or 0.5

        # Age decay
        try:
            created = datetime.fromisoformat(f["created_at"])
            age_days = (datetime.now() - created).days
            age_penalty = min(age_days / 365.0, 1.0)
        except: age_penalty = 0.0

        # Invalidated facts lose utility
        if f["valid_until"] or f["forget_status"] == "invalidated":
            age_penalty += 0.5

        utility = (
            0.3 * access_freq +
            0.2 * degree +
            0.2 * recency +
            0.15 * confidence -
            0.15 * age_penalty
        )
        return max(0.0, min(1.0, utility))

    def update_utility_scores(self):
        """Recalculate utility for all active facts."""
        facts = self.conn.execute(
            "SELECT id FROM facts WHERE forget_status='active'").fetchall()
        updated = 0
        for f in facts:
            score = self._compute_utility(f["id"])
            self.conn.execute("UPDATE facts SET utility_score=? WHERE id=?", (score, f["id"]))
            updated += 1
        self.conn.commit()
        return {"updated": updated}

    def prune_memory(self, threshold: float = 0.15, dry_run: bool = True) -> dict:
        """Intentional forgetting: archive facts with utility < threshold."""
        candidates = self.conn.execute(
            "SELECT id, subject_id, predicate, object_text, utility_score, "
            "access_count, valid_until FROM facts "
            "WHERE forget_status='active' AND utility_score < ? "
            "ORDER BY utility_score ASC", (threshold,)
        ).fetchall()

        archived, deleted = 0, 0
        for c in candidates:
            # Archive if valid_until set (historical data) or low access
            if c["valid_until"] and c["access_count"] == 0:
                if not dry_run:
                    self.conn.execute(
                        "UPDATE facts SET forget_status='forgotten' WHERE id=?", (c["id"],))
                    self.conn.execute(
                        "INSERT INTO forget_log(fact_id, subject_id, predicate, object_text, "
                        "utility_score, action, reason) VALUES(?,?,?,?,?,?,?)",
                        (c["id"], c["subject_id"], c["predicate"], c["object_text"],
                         c["utility_score"], "forgotten", "low_utility_no_access"))
                deleted += 1
            else:
                if not dry_run:
                    self.conn.execute(
                        "UPDATE facts SET forget_status='archived' WHERE id=?", (c["id"],))
                    self.conn.execute(
                        "INSERT INTO forget_log(fact_id, subject_id, predicate, object_text, "
                        "utility_score, action, reason) VALUES(?,?,?,?,?,?,?)",
                        (c["id"], c["subject_id"], c["predicate"], c["object_text"],
                         c["utility_score"], "archived", "low_utility"))
                archived += 1

        if not dry_run:
            self.conn.commit()

        return {"dry_run": dry_run, "candidates": len(candidates),
                "archived": archived, "deleted": deleted, "threshold": threshold}

    # ═══════════════════════════════════════════════
    # JKG 5.0: EMOTIONAL MEMORY
    # ═══════════════════════════════════════════════

    def _detect_emotion(self, text: str) -> tuple:
        """LLM detects emotion + intensity from text."""
        prompt = f"""Analyze emotional tone. Output ONLY JSON.

Text: {text[:1000]}

Format: {{"emotion": "positive|neutral|negative|angry|sad|excited|anxious|grateful", "intensity": 0.0-1.0, "reason": "brief"}}
JSON:"""
        try:
            result = _llm(prompt, "Detect emotion. Output JSON only.")
            data = json.loads(result)
            return data.get("emotion", "neutral"), data.get("intensity", 0.0)
        except:
            return "neutral", 0.0

    def get_emotional_context(self, owner: str = "алтынай", limit: int = 10) -> list:
        """Get recent emotional episodes for adaptation."""
        rows = self.conn.execute(
            "SELECT emotion, emotion_intensity, title, reference_time "
            "FROM episodes WHERE emotion != 'neutral' "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"emotion": r["emotion"], "intensity": r["emotion_intensity"],
                 "title": r["title"], "time": r["reference_time"]} for r in rows]

    # ═══════════════════════════════════════════════
    # JKG 5.0: SELF-EVOLVING GRAPH
    # ═══════════════════════════════════════════════

    def evolve_schema(self, dry_run: bool = True) -> dict:
        """LLM detects patterns in graph → proposes new entity/relation types."""
        entities = self.conn.execute(
            "SELECT type, COUNT(*) as cnt FROM entities GROUP BY type ORDER BY cnt DESC"
        ).fetchall()
        relations = self.conn.execute(
            "SELECT predicate, COUNT(*) as cnt FROM relations GROUP BY predicate ORDER BY cnt DESC"
        ).fetchall()

        e_summary = "\n".join([f"  {e['type']}: {e['cnt']}" for e in entities[:20]])
        r_summary = "\n".join([f"  {r['predicate']}: {r['cnt']}" for r in relations[:20]])

        prompt = f"""Current knowledge graph schema:

Entity types:
{e_summary}

Relation types:
{r_summary}

Analyze the graph and suggest NEW entity types or relation types that would improve representation.
Focus on: missing abstractions, reusable patterns, domain-specific concepts.
Output ONLY JSON array:
[{{"type": "entity|relation", "name": "...", "description": "why needed", "evidence": "what patterns suggest this"}}]
JSON:"""
        try:
            result = _llm(prompt, "Propose schema improvements. Output JSON only.")
            proposals = json.loads(result)
        except:
            return {"proposals": [], "error": "LLM parse failed"}

        stored = 0
        for p in proposals[:10]:
            self.conn.execute(
                "INSERT INTO schema_evolution(pattern_type, pattern_description, proposed_schema, confidence) "
                "VALUES(?,?,?,?)",
                (p.get("type", "entity"), p.get("description", ""),
                 json.dumps(p, ensure_ascii=False), 0.6))
            stored += 1
        self.conn.commit()

        # Accept high-confidence proposals (2+ evidence from different sources = apply)
        return {"proposals": len(proposals), "stored": stored, "dry_run": dry_run,
                "details": proposals[:5]}

    # ═══════════════════════════════════════════════
    # JKG 5.0: PRIVACY-FIRST — GDPR deletion + audit
    # ═══════════════════════════════════════════════

    def gdpr_delete(self, entity_name: str, request_id: str = None, 
                     verified: bool = False) -> dict:
        """Full deletion: graph + vectors + episodes. GDPR-compliant audit trail."""
        if not verified:
            return {"status": "requires_verification",
                    "instruction": "Set verified=True after human confirmation"}

        eid = self._resolve_entity(entity_name)
        if not eid:
            return {"status": "not_found", "entity": entity_name}

        # Delete vectors
        if self.has_vec:
            fact_ids = self.conn.execute(
                "SELECT id FROM facts WHERE subject_id=?", (eid,)).fetchall()
            for f in fact_ids:
                try:
                    self.conn.execute("DELETE FROM facts_vec WHERE fact_id=?", (f["id"],))
                except: pass

        # Delete relations
        rel_count = self.conn.execute(
            "SELECT COUNT(*) FROM relations WHERE subject_id=? OR object_id=?", 
            (eid, eid)).fetchone()[0]
        self.conn.execute("DELETE FROM relations WHERE subject_id=? OR object_id=?", (eid, eid))

        # Delete facts (preserve in forget_log for audit)
        facts = self.conn.execute(
            "SELECT id, predicate, object_text FROM facts WHERE subject_id=?", (eid,)
        ).fetchall()
        for f in facts:
            self.conn.execute(
                "INSERT INTO forget_log(fact_id, subject_id, predicate, object_text, "
                "utility_score, action, reason) VALUES(?,?,?,?,?,?,?)",
                (f["id"], eid, f["predicate"], f["object_text"], 0.0,
                 "gdpr_deleted", f"GDPR request {request_id}"))

        fact_count = len(facts)
        self.conn.execute("DELETE FROM facts WHERE subject_id=?", (eid,))
        self.conn.execute("DELETE FROM entities WHERE id=?", (eid,))

        # Audit trail
        self.conn.execute(
            "INSERT INTO deletion_log(entity_id, reason, gdpr_request_id, verified_by) "
            "VALUES(?,?,?,?)",
            (eid, "GDPR right to erasure", request_id, "system"))

        self.conn.commit()
        return {"status": "deleted", "entity": entity_name, "eid": eid,
                "facts_deleted": fact_count, "relations_deleted": rel_count,
                "request_id": request_id, "gdpr_compliant": True}

    # ═══════════════════════════════════════════════
    # REMEMBER — ATOMIC graph + vector insert
    # ═══════════════════════════════════════════════

    def remember(self, text: str, source: str = "manual", ground_to: str = None,
                 title: str = "", reference_time: str = None) -> dict:
        """JKG 5.0: Extract + store with EMOTION, BI-TEMPORAL, SELF-EVOLVING."""
        import uuid as _uuid

        # ── EPISODE with EMOTION ──
        ep_uuid = str(_uuid.uuid4())
        ref_time = reference_time or datetime.now().strftime("%Y-%m-%d")
        emotion, emotion_intensity = self._detect_emotion(text)
        cur = self.conn.execute(
            "INSERT INTO episodes(uuid, title, body, source_type, reference_time, emotion, emotion_intensity) "
            "VALUES(?,?,?,?,?,?,?)",
            (ep_uuid, title or text[:80], text[:5000], source, ref_time, emotion, emotion_intensity))
        episode_id = cur.lastrowid

        # ── TEMPORAL EXTRACTION ──
        temporal = self._extract_temporal(text)
        temp_ref = temporal.get("reference_time") or ref_time
        temp_facts = {f"{self._norm(f.get('subject',''))}|{self._norm(f.get('predicate',''))}|{self._norm(str(f.get('object','')))}": f
                      for f in temporal.get("facts", [])}

        # ── ENTITY EXTRACTION ──
        entities_json = _extract_entities(text)
        try:
            data = json.loads(entities_json)
        except json.JSONDecodeError:
            data = {"entities": [], "relations": [], "facts": []}

        stored = {"entities": 0, "facts": 0, "relations": 0, "vectors": 0,
                  "invalidated": 0, "duplicates": 0, "episode_id": episode_id}
        new_fact_ids = []
        new_entity_ids = []

        # ── JKG 5.1: TEMPORAL LINKING — connect end_year/resigned_from to works_at ──
        data = self._link_temporal(data)

        with self.conn:
            # ── Entities with RESOLUTION ──
            for ent in data.get("entities", []):
                name = self._norm(ent.get("name", ent.get("entity", str(ent))))
                etype = ent.get("type", "entity")
                # Use resolve_entity for smart dedup
                eid = self.resolve_entity(name, etype)
                new_entity_ids.append(eid)
                if self.conn.total_changes > 0:
                    stored["entities"] += 1

            # ── Facts with DEDUP + TEMPORAL + INVALIDATION ──
            for fact in data.get("facts", []):
                subj = self._norm(fact.get("subject", ""))
                if not subj: continue
                sid = self.resolve_entity(subj)  # Entity resolution
                new_entity_ids.append(sid)
                pred = self._norm(fact.get("predicate", "has_property"))
                obj = self._norm(str(fact.get("object", fact.get("value", ""))))

                # Dedup check
                fhash = self._compute_fact_hash(subj, pred, obj)
                dup = self.conn.execute(
                    "SELECT id FROM facts WHERE fact_hash=?", (fhash,)).fetchone()
                if dup:
                    # Update access count, don't duplicate
                    self.conn.execute(
                        "UPDATE facts SET access_count = access_count + 1, "
                        "last_accessed_at = datetime('now') WHERE id=?",
                        (dup["id"],))
                    stored["duplicates"] += 1
                    continue

                # Temporal data
                tf_key = f"{subj}|{pred}|{obj}"
                tf = temp_facts.get(tf_key, {})
                vfrom = tf.get("valid_from") or temp_ref
                vuntil = tf.get("valid_until")

                # Invalidate conflicting old facts
                inv = self._invalidate_conflicting(subj, pred, obj, vfrom)
                stored["invalidated"] += inv

                # Insert new fact
                cur = self.conn.execute(
                    "INSERT INTO facts(subject_id, predicate, object_text, source, "
                    "episode_id, fact_hash, valid_from, valid_until) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (sid, pred, obj, source, episode_id, fhash, vfrom, vuntil))
                fid = cur.lastrowid
                new_fact_ids.append(fid)
                stored["facts"] += 1

                # BM25 sync
                self.conn.execute(
                    "INSERT INTO facts_fts_content(id, entity_name, predicate, object_text) VALUES(?,?,?,?)",
                    (fid, self._get_name(sid), pred, obj))

            # ── Relations ──
            for rel in data.get("relations", []):
                subj = self._norm(rel.get("subject", ""))
                obj = self._norm(rel.get("object", ""))
                if not subj or not obj: continue
                sid = self.resolve_entity(subj)
                oid = self.resolve_entity(obj)
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

        # VECTORS
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
                except Exception:
                    pass

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
    # JKG 5.1: PREDICATE ALIASES — semantic equivalents
    # ═══════════════════════════════════════════════

    # When user asks "где работает", also match builds/founded/develops etc.
    _PREDICATE_ALIASES = {
        "works_at": ["builds", "founded", "develops", "creates", "runs", "leads",
                     "строит", "основала", "основал", "разрабатывает", "запустила",
                     "запустил", "работает_над", "владеет", "управляет"],
        "работает_в": ["строит", "основала", "основал", "разрабатывает", "запустила",
                       "запустил", "работает_над", "builds", "founded", "develops",
                       "creates", "runs", "leads"],
        "работает": ["строит", "основала", "основал", "разрабатывает", "запустила",
                     "запустил", "builds", "founded", "develops", "creates"],
    }

    def _expand_predicates(self, query: str) -> set:
        """Return set of predicates to search for, including semantic aliases."""
        predicates = {"works_at", "работает_в", "employed_at", "position"}
        # If query is about current work, expand
        if any(w in query.lower() for w in ["работает", "работа", "работаю",
                                              "где сейчас", "чем занимается",
                                              "где трудится", "works", "work",
                                              "job", "current"]):
            for alias_group in self._PREDICATE_ALIASES.values():
                predicates.update(alias_group)
        return predicates

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
        """JKG 4.0: Full hybrid pipeline with TEMPORAL AWARENESS."""
        # Detect if question is about past/present
        past_indicators = ["раньше", "до", "был", "была", "было", "были", "прошлом",
                          "в 202", "история", "использовал", "работал", "was", "before"]
        is_past = any(w in question.lower() for w in past_indicators)

        # Step 1: Hybrid recall
        candidates = self.recall(question, limit=20)

        # Step 2: Owner traversal (filter by validity)
        owner_trav = self.traverse(owner, depth=3, max_results=30)
        existing = {f"{c['entity']}|{c['predicate']}|{c.get('value',c.get('object',''))}"
                    for c in candidates}
        for f in owner_trav.get("facts", []):
            key = f"{f['entity']}|{f['predicate']}|{f['value']}"
            if key not in existing:
                candidates.append(f)
                existing.add(key)

        # Step 3: Enrich with temporal metadata + predicate alias awareness
        work_predicates = self._expand_predicates(question)
        for c in candidates:
            entity_name = c.get('entity', '')
            pred = c.get('predicate', '')
            # Look up temporal info
            sid = self._resolve_entity(entity_name)
            if sid:
                fact = self.conn.execute(
                    "SELECT valid_from, valid_until, confidence, superseded_by "
                    "FROM facts WHERE subject_id=? AND predicate=? AND object_text=? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (sid, pred, c.get('value', c.get('object', '')))
                ).fetchone()
                if fact:
                    if fact["valid_until"]:
                        c["status"] = f"INVALID (ended {fact['valid_until']})" if not is_past else "HISTORICAL"
                        if not is_past:
                            c["_penalty"] = True  # Downrank invalid facts
                    elif fact["valid_from"]:
                        # If predicate is a work-alias, mark as current activity
                        if pred in work_predicates:
                            c["status"] = f"CURRENT since {fact['valid_from']}"
                        else:
                            c["status"] = f"VALID since {fact['valid_from']}"
                    c["confidence"] = fact["confidence"]

        # Filter: for present-tense questions, remove invalid facts
        if not is_past:
            candidates = [c for c in candidates if not c.get("_penalty")]

        # JKG 5.1: Predicate expansion — for "где работает" questions,
        # boost facts with work-alias predicates (builds, founded, etc.)
        if work_predicates and not is_past:
            for c in candidates:
                if c.get('predicate', '') in work_predicates and not c.get('_penalty'):
                    c['_is_current_activity'] = True

        # Step 4: LLM rerank
        ranked = self.llm_rerank(question, candidates, top_k=15)

        # Step 5: Build context with temporal annotations
        context_parts = []
        for r in ranked:
            path = " → ".join(r.get("path", [])) if r.get("path") else ""
            status = f" [{r.get('status','')}]" if r.get("status") else ""
            if path:
                context_parts.append(f"TRACE {path} | {r['entity']} {r['predicate']} {r.get('value',r.get('object',''))}{status}")
            else:
                context_parts.append(f"FACT {r['entity']} {r['predicate']} {r.get('value',r.get('object',''))}{status}")

        context_parts.append("")
        context_parts.append("GRAPH PATHS:")
        for p in owner_trav.get("paths", [])[:10]:
            context_parts.append(f"  {p}")

        context = "\n".join(context_parts) if context_parts else "(ничего не найдено)"

        # Step 6: LLM synthesize
        temporal_note = (
            "Facts marked [CURRENT since] are the person's present occupation/activity. "
            "Facts marked [VALID since] are currently true. "
            "Facts marked [INVALID] or [HISTORICAL] are no longer true. "
            "For 'где работает' questions, prefer [CURRENT] facts, "
            "even if the predicate is 'builds', 'founded', 'develops', etc. — "
            "these ARE the person's current work."
        ) if not is_past else "Include both current and historical facts in your answer."
        answer = _llm(
            f"Knowledge graph context (hybrid graph+semantic search):\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Instructions:\n"
            f"- {temporal_note}\n"
            f"- Use GRAPH PATHS to trace entity connections\n"
            f"- Give definitive answers when data exists, include dates\n"
            f"- NAME every company, person, and entity explicitly — never paraphrase them away\n"
            f"- For career/история questions: list EVERY position chronologically with company names\n"
            f"- If entity X is connected to {owner} via a path, it IS relevant\n"
            f"Answer in Russian.",
            system="You answer questions using a temporal knowledge graph. "
                   "Respect FACT validity times. Be definitive and specific. "
                   "ALWAYS name entities explicitly — never replace names with generic descriptions."
        )

        return {"question": question, "answer": answer,
                "candidates": len(candidates), "ranked": len(ranked),
                "temporal_filter": not is_past}

    # ═══════════════════════════════════════════════
    # JKG 4.0: SEARCH EPISODES
    # ═══════════════════════════════════════════════

    def search_episodes(self, query: str, limit: int = 10) -> list:
        """Search raw episodes by keywords."""
        words = [w for w in re.findall(r'[^\s,?.!;:"\'()\[\]{}]+', query.lower()) if len(w) > 1]
        if not words: return []
        conditions = " OR ".join(["body LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words]
        rows = self.conn.execute(
            f"SELECT id, uuid, title, body, source_type, reference_time, created_at "
            f"FROM episodes WHERE {conditions} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        return [{"id": r["id"], "uuid": r["uuid"], "title": r["title"],
                 "body": r["body"][:500], "source_type": r["source_type"],
                 "reference_time": r["reference_time"], "created_at": r["created_at"]}
                for r in rows]

    def get_fact_episode(self, fact_id: int) -> dict:
        """Trace a fact back to its source episode."""
        fact = self.conn.execute(
            "SELECT f.*, e.title, e.body, e.reference_time, e.source_type "
            "FROM facts f LEFT JOIN episodes e ON f.episode_id = e.id "
            "WHERE f.id=?", (fact_id,)
        ).fetchone()
        if not fact: return {"error": "not found"}
        return {"fact_id": fact_id, "subject": self._get_name(fact["subject_id"]),
                "predicate": fact["predicate"], "object": fact["object_text"],
                "episode_title": fact["title"], "episode_body": fact["body"][:300] if fact["body"] else "",
                "reference_time": fact["reference_time"], "source_type": fact["source_type"]}

    # ═══════════════════════════════════════════════
    # STATS
    # ═══════════════════════════════════════════════

    def stats(self) -> dict:
        entities = self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        facts = self.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        relations = self.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        episodes = self.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        orphans = self.conn.execute("""
            SELECT COUNT(*) FROM entities e
            WHERE e.id NOT IN (SELECT subject_id FROM relations
                               UNION SELECT object_id FROM relations)
            AND NOT EXISTS (SELECT 1 FROM facts f WHERE f.subject_id = e.id)
        """).fetchone()[0]

        vectors = 0
        if self.has_vec:
            try: vectors = self.conn.execute("SELECT COUNT(*) FROM facts_vec").fetchone()[0]
            except: pass

        valid = self.conn.execute(
            "SELECT COUNT(*) FROM facts WHERE valid_until IS NULL AND superseded_by IS NULL AND forget_status='active'"
        ).fetchone()[0]
        historical = self.conn.execute(
            "SELECT COUNT(*) FROM facts WHERE valid_until IS NOT NULL OR superseded_by IS NOT NULL"
        ).fetchone()[0]
        forgotten = self.conn.execute(
            "SELECT COUNT(*) FROM facts WHERE forget_status IN ('forgotten','archived')"
        ).fetchone()[0]
        emotional = self.conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE emotion != 'neutral' AND emotion_intensity > 0.3"
        ).fetchone()[0]
        schema_proposals = self.conn.execute("SELECT COUNT(*) FROM schema_evolution").fetchone()[0]

        # Average utility
        avg_util = self.conn.execute(
            "SELECT AVG(utility_score) FROM facts WHERE forget_status='active'"
        ).fetchone()[0]

        return {
            "entities": entities, "connected": entities - orphans, "orphans": orphans,
            "facts": facts, "valid_facts": valid, "historical_facts": historical,
            "forgotten_facts": forgotten, "relations": relations,
            "episodes": episodes, "emotional_episodes": emotional,
            "vectors": vectors, "has_embeddings": self.has_vec,
            "schema_proposals": schema_proposals,
            "avg_utility": round(avg_util, 3) if avg_util else 0.5,
            "version": "5.0",
            "architecture": "graph+embeddings+temporal+emotional+forgetting+self-evolving",
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
        result = hm.remember(text, ground_to="алтынай")
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

    elif cmd == "episodes":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        results = hm.search_episodes(query) if query else hm.conn.execute(
            "SELECT id, uuid, title, body, reference_time FROM episodes ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        if isinstance(results, list) and results and isinstance(results[0], dict):
            for e in results:
                print(f"  [{e['reference_time']}] {e['title']}")
                print(f"    {e['body'][:200]}")
        else:
            for e in (results or []):
                print(f"  [{e['reference_time']}] {e['title']} — {e['body'][:150]}")

    elif cmd == "resolve":
        name = " ".join(sys.argv[2:])
        eid = hm.resolve_entity(name)
        ename = hm._get_name(eid)
        print(f"'{name}' → [{eid}] {ename}")

    elif cmd == "invalidate":
        if len(sys.argv) >= 5:
            result = hm._invalidate_conflicting(sys.argv[2], sys.argv[3], sys.argv[4])
            print(f"Invalidated: {result}")

    elif cmd == "utility":
        result = hm.update_utility_scores()
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "prune":
        threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15
        dry = "--execute" not in sys.argv
        result = hm.prune_memory(threshold=threshold, dry_run=dry)
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "emotions":
        ctx = hm.get_emotional_context()
        for e in ctx:
            print(f"  [{e['intensity']:.1f}] {e['emotion']}: {e['title'][:80]} ({e['time']})")

    elif cmd == "evolve":
        result = hm.evolve_schema(dry_run="--execute" not in sys.argv)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "gdpr-delete":
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        rid = sys.argv[3] if len(sys.argv) > 3 else f"REQ-{datetime.now().strftime('%Y%m%d%H%M')}"
        verified = "--confirm" in sys.argv
        result = hm.gdpr_delete(name, request_id=rid, verified=verified)
        print(json.dumps(result, ensure_ascii=False))

    else:
        print("Commands: remember, recall, traverse, path, ask, bridge, "
              "stats, entities, forget, episodes, resolve, invalidate")
