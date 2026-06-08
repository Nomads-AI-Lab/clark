# JKG Production-Ready Open Source Plan

Date: 2026-06-08
Repo: `altyshalu/jessica-knowledge-graph`
Local path: `/Users/nik1t7n/Projects/jessica-knowledge-graph`

## Executive Summary

JKG is not production-ready yet. The current repo is a promising prototype with a strong product direction, but it is not at the "polish and publish" stage. The honest release path is: first fix installability and trust boundaries, then replace the monolithic SQLite prototype with a real provider/storage architecture, then validate every advertised feature with real tests.

The biggest issue is claim drift. The README positions JKG as a "Unified Memory Fabric" with SQLite, sqlite-vec, CLARK retrieval, GDPR deletion, four-layer memory, LongMemEval results, and broad agent integrations. The repo currently contains one main implementation file (`jkg/memory.py`), no formal test suite, no Docker setup, no MCP server, no Hermes plugin, no Postgres/pgvector, and a broken installed CLI entrypoint.

Open-source launch should wait until these blockers are closed. Shipping this now would create trust debt.

## Current Repo Findings

### What Exists

- Python package `jkg`.
- Public API export: `HybridMemory`.
- Monolithic implementation in `jkg/memory.py`.
- SQLite schema with tables for:
  - profile memory: `memory_profile`
  - factual memory: `entities`, `facts`, `relations`, `episodes`
  - episodic memory: `memory_sessions`
  - procedural memory: `memory_skills`
  - governance: `schema_evolution`, `forget_log`, `deletion_log`
- Optional sqlite-vec table: `facts_vec`.
- FTS5 text search: `facts_fts`, `facts_fts_content`.
- Ad hoc CLI under `if __name__ == "__main__"`.
- MIT license already exists.
- One ad hoc test/evaluation script: `run_tests.py`.
- One benchmark script: `benchmark/run_longmemeval.py`.

### Release Blockers Found

- `pyproject.toml` declares `jkg = "jkg.memory:main_cli"`, but `main_cli` does not exist.
- `memory.py` imports `requests`, `numpy`, `sentence_transformers`, and `scipy`-dependent paths, but `pyproject.toml` only declares `sqlite-vec`, `requests`, and `numpy`.
- Local clean import check showed missing runtime dependencies in the active Python environment: `requests`, `numpy`, `sentence_transformers`, `sqlite_vec`, `scipy`.
- The default DB path is inside the package directory (`jkg/memory_v3.db`), which is wrong for installed packages, Docker, and multi-user servers.
- There are silent fallback paths and swallowed exceptions (`except: pass`) in critical retrieval, vector, GDPR, session, and provider code.
- README claims "optional Gemini embeddings", but code can silently return zero vectors if `GEMINI_API_KEY` is missing in the Gemini path. That must be removed.
- Existing repo notes already admit unresolved failures:
  - temporal reasoning
  - GDPR cascading delete
  - semantic noise isolation
- No formal `tests/` directory, no `pytest`, no CI, no coverage, no real install matrix.
- No Docker, Compose, migrations, server process, health checks, backup/restore, observability, auth, MCP, Hermes plugin, Claude/Codex/Cursor integration packages.

## Product Positioning

Recommended positioning:

> JKG is a production-grade memory system for personal agents: a unified profile, factual, episodic, and procedural memory layer exposed through Python, CLI, MCP, and native agent plugins.

Do not position it as "works everywhere" until these integrations are actually tested:

- Hermes
- Codex
- Claude Code
- Gemini CLI
- Cursor
- OpenAI-compatible local agents
- MCP clients

## Production Target Architecture

### Core Principles

- No hidden fallbacks.
- No fake data in production tests.
- No silent degraded behavior.
- Provider failures must fail explicitly.
- Storage migrations must be versioned.
- Every external integration must have a real contract test.
- Backward compatibility is secondary to a clean production architecture.

### Proposed Package Layout

```text
jkg/
  __init__.py
  config.py
  errors.py
  models.py
  logging.py
  db/
    migrations/
    postgres.py
    sqlite.py
    repository.py
  providers/
    base.py
    llm.py
    embeddings.py
    openai.py
    anthropic.py
    gemini.py
    deepseek.py
    ollama.py
    local.py
  memory/
    service.py
    profile.py
    factual.py
    episodic.py
    procedural.py
    retrieval.py
    temporal.py
    privacy.py
  cli/
    main.py
  mcp/
    server.py
  integrations/
    hermes/
    claude_code/
    codex/
    cursor/
    gemini_cli/
```

### Storage

Primary production storage:

- Postgres 16+.
- pgvector.
- SQLAlchemy 2.x or psycopg 3 with explicit repository layer.
- Alembic migrations.
- `vector`, `jsonb`, `tsvector`, and regular relational indexes.
- HNSW vector indexes for production semantic search.

Development/local storage:

- Optional SQLite adapter only for local development, not the production default.
- SQLite must not silently replace Postgres in production.

Why Postgres + pgvector:

- pgvector stores vectors inside Postgres and keeps relational filtering, transactions, joins, replication, backup, and point-in-time recovery in one operational system.
- pgvector supports HNSW indexes, cosine operator classes, and query-time tuning such as `hnsw.ef_search`.
- pgvector 0.8.0+ supports iterative scans for filtered ANN queries, which matters for tenant/user/time filters.

Recommended production vector choices:

- Use `vector_cosine_ops` for text embeddings.
- Use HNSW as the default production ANN index.
- Use exact search in correctness tests to compare ANN recall.
- Store embedding model name and dimension per vector row.
- Reject inserting a vector with the wrong dimension.

### Schema Direction

Core tables:

- `tenants`
- `identities`
- `memory_items`
- `facts`
- `entities`
- `relations`
- `episodes`
- `skills`
- `embeddings`
- `memory_events`
- `audit_log`
- `deletion_requests`
- `provider_calls`

Important design decisions:

- Every memory row must have `tenant_id` / `owner_id`.
- Every memory row must have `source`, `created_at`, `updated_at`, and `provenance`.
- Every fact must support `valid_from`, `valid_until`, `observed_at`, and `ingested_at`.
- Every embedding row must store `provider`, `model`, `dimension`, and `content_hash`.
- Every destructive action must write an audit event.
- GDPR deletion must delete or cryptographically tombstone every derived artifact, including vectors, FTS rows, summaries, session text, and cache rows.

### Provider Architecture

Implement explicit provider interfaces:

- `LLMProvider`
  - `complete_json(...)`
  - `summarize(...)`
  - `rerank(...)`
  - `extract_facts(...)`
- `EmbeddingProvider`
  - `embed_text(...)`
  - `embed_batch(...)`
  - `dimension`
  - `model`
- `StorageProvider`
  - repository methods, no raw SQL spread through memory services

Provider options to support:

- OpenAI
  - LLM: current OpenAI chat/responses models.
  - embeddings: `text-embedding-3-small`, `text-embedding-3-large`.
- Anthropic
  - LLM only. Anthropic does not provide embeddings as a primary public embedding product, so do not claim Anthropic embeddings unless this changes.
- Gemini
  - LLM and embeddings.
  - `gemini-embedding-001` is generally available in Gemini API.
- DeepSeek
  - LLM via OpenAI-compatible `/chat/completions`.
  - Current docs list `deepseek-v4-flash` and `deepseek-v4-pro`; `deepseek-chat` and `deepseek-reasoner` are marked for deprecation on 2026-07-24.
- Ollama/local
  - LLM via local HTTP API.
  - embeddings via `/api/embed`, e.g. `embeddinggemma`, `qwen3-embedding`, `all-minilm`.
- Local Python
  - Optional explicit install extra for `sentence-transformers`.
  - Never import heavy local ML dependencies unless that provider is selected.

Do not use automatic provider fallback by default. If `openai` is configured and OpenAI fails, JKG should fail with a clear error. User-configured fallback chains can be added later, but they must be explicit and logged.

### Configuration

Use environment variables and config files with one source of truth.

Required:

- `JKG_DATABASE_URL`
- `JKG_LLM_PROVIDER`
- `JKG_LLM_MODEL`
- `JKG_EMBEDDING_PROVIDER`
- `JKG_EMBEDDING_MODEL`
- `JKG_AUTH_TOKEN` or OAuth config for HTTP/MCP server
- `JKG_LOG_LEVEL`
- `JKG_ENV`

Optional:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `OLLAMA_BASE_URL`
- `JKG_ALLOWED_ORIGINS`
- `JKG_RATE_LIMIT_*`
- `JKG_BACKUP_S3_*`

Rules:

- Missing required config fails at startup.
- Missing optional provider credentials only matters if that provider is selected.
- No `.env` auto-loading from unrelated systems such as `~/.hermes/.env` inside core library code. Integrations can load their own config.

## Interfaces To Ship

### Python API

Stable API:

- `remember(text, metadata=None)`
- `remember_profile(text, metadata=None)`
- `remember_session(session_id, transcript, metadata=None)`
- `index_skill(name, description, triggers=None, metadata=None)`
- `query(text, layers=None, limit=10, filters=None)`
- `session_context(owner_id, query=None)`
- `delete_subject(subject, request_id, verified_by)`
- `health()`
- `stats()`

### CLI

Use Typer or Click.

Commands:

- `jkg init`
- `jkg doctor`
- `jkg migrate`
- `jkg serve`
- `jkg mcp`
- `jkg remember`
- `jkg query`
- `jkg session-start`
- `jkg profile`
- `jkg sessions`
- `jkg skills`
- `jkg gdpr-delete`
- `jkg backup`
- `jkg restore`
- `jkg providers test`
- `jkg docker env`

`jkg doctor` must verify:

- package version
- Python version
- DB connection
- migration state
- pgvector extension
- selected LLM provider
- selected embedding provider
- embedding dimension
- write permissions
- MCP/Hermes plugin availability when configured

### HTTP API

Ship a FastAPI service for Docker/server mode:

- `GET /healthz`
- `GET /readyz`
- `POST /v1/memories`
- `POST /v1/query`
- `POST /v1/sessions`
- `POST /v1/skills`
- `POST /v1/context`
- `DELETE /v1/subjects/{subject}`
- `GET /v1/stats`

Security:

- Bearer token minimum for single-user installs.
- OAuth 2.1 resource server support for multi-user or exposed deployments.
- Per-token scopes:
  - `memory:read`
  - `memory:write`
  - `memory:delete`
  - `memory:admin`

### MCP Server

Use the official MCP Python SDK.

Tools:

- `jkg_remember`
- `jkg_query`
- `jkg_profile_get`
- `jkg_session_context`
- `jkg_skill_index`
- `jkg_gdpr_delete`
- `jkg_stats`
- `jkg_health`

Resources:

- `jkg://profile/{owner_id}`
- `jkg://session-context/{owner_id}`
- `jkg://stats`

Prompts:

- `jkg-memory-aware-system-prompt`
- `jkg-session-summary-prompt`

Transports:

- stdio for local agent clients.
- streamable HTTP for server mode.

Security requirements:

- stdio mode must be local-only and must not execute shell commands.
- HTTP mode must require auth.
- All tool inputs must be schema-validated.
- Delete tools must require explicit confirmation fields.
- MCP prompt/tool injection risk must be documented and mitigated with strict tool descriptions, scopes, and audit logs.

### Hermes Plugin

Hermes memory providers are external plugins. Current Hermes docs say providers implement `MemoryProvider` and lifecycle hooks such as:

- `sync_turn(turn_messages)`
- `prefetch(query)`
- `shutdown()`
- optional `post_setup(hermes_home, config)`

Hermes also expects setup through `hermes memory setup`, provider config, context injection, background prefetch, turn sync, session-end extraction, memory mirroring, and provider-specific tools.

Ship a standalone plugin package/repo:

- `jkg-hermes-plugin`
- installable by `pip install jkg-hermes-plugin`
- registers provider name: `jkg`
- implements Hermes `MemoryProvider`
- supports embedded local mode and remote HTTP mode
- writes config through `post_setup`
- exposes Hermes tools:
  - `jkg_remember`
  - `jkg_recall`
  - `jkg_context`
  - `jkg_stats`
  - `jkg_forget`

Required tests:

- install into a clean Hermes home
- `hermes memory setup`
- `hermes memory status`
- one real conversation turn sync
- one real prefetch before turn
- one session-end extraction
- one GDPR/delete path

### Claude Code / Codex / Cursor / Gemini CLI

The lowest-friction integration should be MCP first:

- publish stdio MCP config examples
- publish streamable HTTP MCP config examples
- document how to connect each client
- provide `jkg doctor mcp` to validate configuration

Then add native helpers where worthwhile:

- Claude Code: MCP server config plus optional command installer.
- Codex: MCP server config plus local project instructions.
- Cursor: MCP server config.
- Gemini CLI: MCP or extension path after verifying current Gemini CLI plugin model.

## Docker And Server Setup

### Required Artifacts

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `docker/entrypoint.sh`
- `docker/postgres/init.sql`
- health check endpoint
- migration command
- backup/restore docs

### Recommended Compose Services

- `jkg-api`
- `postgres`
- optional `ollama`
- optional `pgadmin` only under dev profile

### Production Docker Requirements

- non-root container user
- pinned base image
- read-only filesystem where possible
- mounted data volumes
- no secrets baked into image
- health checks
- restart policy
- resource limits
- structured JSON logs
- graceful shutdown
- migration-on-start disabled by default; explicit `jkg migrate` preferred

### One-Server Install Goal

Target UX:

```bash
git clone https://github.com/altyshalu/jessica-knowledge-graph.git
cd jessica-knowledge-graph
cp .env.example .env
docker compose up -d postgres
docker compose run --rm jkg-api jkg migrate
docker compose up -d jkg-api
jkg doctor --url http://localhost:8000
```

## Security Hardening Plan

### P0 Security Fixes

- Remove silent fallbacks and zero-vector behavior.
- Remove `gdpr_compliant: True` until erasure is actually complete.
- Add explicit privacy mode: local-only by default; remote LLM/embedding providers require opt-in.
- Stop loading `.env` from unrelated paths in core library.
- Move Gemini API key usage out of query params and into headers.
- Add explicit auth to HTTP and remote MCP.
- Add input validation with Pydantic.
- Add request size limits.
- Add rate limits for write, query, and provider calls.
- Add SQL migration layer.
- Add tenant/owner isolation.
- Add audit logging for all writes/deletes.
- Add full deletion coverage across raw, derived, vector, FTS, cache, and summary tables.
- Add WAL/checkpoint secure deletion strategy for local SQLite mode.
- Add secrets scanning in CI.
- Add dependency vulnerability scanning.
- Add safe logging that never logs provider API keys or full sensitive transcripts by default.

### P1 Security Fixes

- OAuth 2.1 support for remote MCP / HTTP resource server mode.
- Token scopes.
- Optional encryption at rest guidance.
- Backup encryption guidance.
- SBOM generation.
- Signed release artifacts.
- Docker image vulnerability scan.
- Threat model document.
- Security policy and responsible disclosure process.

### Privacy Requirements

GDPR delete must prove:

- entity row deleted
- facts deleted
- relations deleted
- embeddings deleted
- FTS entries deleted
- `episodes.body` and `episodes.title` deleted or scrubbed
- `forget_log.object_text` deleted or scrubbed
- session text scrubbed or deleted
- generated summaries scrubbed or deleted
- profile rows scrubbed or deleted
- skills scrubbed if they contain subject data
- provider call logs scrubbed
- cache rows scrubbed
- audit log keeps only non-sensitive deletion metadata
- SQLite WAL is checkpointed/truncated if SQLite mode is used

Security review findings to track:

- Critical: current `gdpr_delete()` is incomplete but returns `gdpr_compliant: True`.
- High: raw user/profile/session text is sent to third-party LLM APIs during ingest without an explicit privacy boundary.
- High: no authn/authz or tenant boundary exists if this is wrapped as a service.
- Medium: ambient `.env` loading can pull credentials from unrelated systems and make behavior unpredictable.
- Medium: Gemini key currently appears in URL query string; prefer header auth.
- Medium: local SQLite storage is plaintext and WAL can retain deleted sensitive remnants.
- Medium: dependency audit is incomplete because runtime imports are not fully declared and there is no lockfile.

## Real Test Plan

No mocks as proof. Fixtures are allowed only when named as fixtures for deterministic unit tests, not as substitutes for integration validation.

### Test Tiers

#### Tier 0: Static And Packaging

- `python -m compileall jkg`
- `pip install -e .` in clean venv
- `python -c "from jkg import HybridMemory"`
- installed `jkg --help`
- `jkg doctor`
- dependency metadata check
- `ruff`
- `mypy` or pyright
- license check
- secrets scan

#### Tier 1: Local Real Integration

- fresh Postgres + pgvector container
- real migrations
- real insert/query/delete
- real FTS
- real vector index creation
- exact vector search correctness checks
- ANN recall sanity checks
- backup/restore smoke

#### Tier 2: Provider Contract Tests

Run against real providers with low budgets:

- OpenAI LLM call
- OpenAI embedding call
- Anthropic LLM call
- Gemini LLM call
- Gemini embedding call
- DeepSeek LLM call
- Ollama local LLM call
- Ollama local embedding call

Each test must assert:

- request succeeds
- response schema is valid
- model ID matches expected provider behavior
- timeout is enforced
- errors are surfaced cleanly
- embedding dimension matches configured DB schema

#### Tier 3: Functional Edge Cases

Real tests for:

- empty DB query
- first memory insert
- duplicate fact
- contradictory preference
- temporal transition
- overlapping time intervals
- current vs historical query
- Cyrillic entity
- mixed Cyrillic/English entity
- homonyms (`Apple` fruit/company/music)
- long transcript
- malformed text input
- large batch ingest
- concurrent writes
- concurrent reads while writes happen
- provider timeout
- provider invalid JSON
- vector dimension mismatch
- pgvector unavailable
- migration from SQLite prototype if supported
- GDPR delete idempotency
- prune idempotency
- session context generation with no data
- session context generation with all four layers
- skill trigger search
- profile update supersession

#### Tier 4: Agent E2E

- MCP stdio with a real MCP client.
- MCP HTTP with auth.
- Hermes plugin lifecycle.
- Claude Code MCP config.
- Codex MCP config.
- Cursor MCP config.
- Gemini CLI integration after its current extension/MCP support is verified.

#### Tier 5: Benchmarks

- LongMemEval-S with documented dataset version.
- LoCoMo-style long conversation memory benchmark if licensing allows.
- Real memory-provider comparison suite against top current agent memory providers.
  - Candidates to compare where self-hosted or API access is available: Mem0, Zep/Graphiti, Letta, Cognee, Supermemory, OpenViking, Honcho, Hindsight, Byterover, ClawMem, YantrikDB.
  - Use the same corpus, questions, provider models, embedding settings, and budget caps where possible.
  - Report recall@k, MRR, NDCG, latency, ingest cost, query cost, deletion correctness, and integration effort.
  - Do not compare against marketing claims. Run real benchmark jobs and publish raw result artifacts.
- CLARK-specific ablation suite.
  - JKG BM25 only.
  - JKG vector only.
  - JKG graph traversal only.
  - JKG RRF hybrid.
  - JKG CLARK without confidence update.
  - JKG CLARK with confidence update.
  - JKG CLARK with temporal filtering.
  - JKG CLARK full pipeline.
- latency benchmark:
  - p50/p95 query
  - p50/p95 ingest
  - p50/p95 session context
- storage benchmark:
  - 10k memories
  - 100k memories
  - 1M memories if server resources allow
- quality regression corpus checked into repo.

### Edge Case Matrix

| Area | Edge Case | Expected Behavior |
|---|---|---|
| install | clean venv | install and import succeeds |
| CLI | installed `jkg` | real command works |
| config | missing DB URL | startup fails clearly |
| config | missing selected provider key | startup/provider test fails clearly |
| storage | pgvector missing | migration/doctor fails clearly |
| storage | vector dimension mismatch | insert rejected |
| ingestion | duplicate fact | no duplicate active fact |
| ingestion | contradictory fact | older fact superseded or contradiction recorded |
| temporal | "lived in X in 2023", "moved to Y in 2026" | 2024 query returns X if interval still valid, current returns Y |
| retrieval | homonym query | context-specific result wins |
| retrieval | empty DB | empty result, no crash |
| privacy | GDPR delete | no subject traces in raw or derived tables |
| privacy | repeated delete | idempotent success/not found |
| provider | bad JSON from LLM | surfaced extraction error |
| provider | timeout | surfaced timeout, no fake result |
| concurrency | parallel writes | no corruption, correct transaction isolation |
| MCP | unauth HTTP call | rejected |
| MCP | destructive tool without confirmation | rejected |

## Credentials Needed For Future Full Tests

Provide these later through secure environment variables or a temporary `.env` on the test server. Do not paste long-lived production keys into public docs or commits.

### Required For Minimum Real Release Tests

- `OPENAI_API_KEY`
  - Needed for OpenAI LLM and embedding provider tests.
  - Scope: API key with low spend limit.
  - Budget recommendation: $5-$20 test cap.

- `ANTHROPIC_API_KEY`
  - Needed for Anthropic LLM provider tests.
  - Scope: API key with low spend limit.
  - Budget recommendation: $5-$20 test cap.

- `GEMINI_API_KEY`
  - Needed for Gemini LLM and `gemini-embedding-001` embedding tests.
  - Scope: Google AI Studio/Gemini API key, not broad Google Cloud owner credentials.
  - Budget recommendation: free/low quota if possible.

- `DEEPSEEK_API_KEY`
  - Needed for DeepSeek LLM provider tests.
  - Must support current models such as `deepseek-v4-flash` or `deepseek-v4-pro`.
  - Do not rely on `deepseek-chat` long term because docs mark it for deprecation on 2026-07-24.

### Required For Server/Docker Tests

- SSH access to isolated test host.
  - You provided: `root@82.38.4.10`.
  - For implementation, create a dedicated user instead of long-term root usage.

- Test domain or subdomain, optional.
  - Needed only if we test HTTPS/OAuth flows.
  - Example: `jkg-test.yourdomain.com`.

- DNS provider/API access, optional.
  - Needed only if automating TLS/domain setup.

- SMTP credentials, optional.
  - Needed only if release workflow sends alerts or invites.

- S3-compatible backup credentials, optional but recommended.
  - Needed for backup/restore tests.
  - Minimal permissions: one test bucket/path, read/write/delete only there.

### Required For Agent Integration Tests

- Hermes test installation or permission to install Hermes on the test server.
  - Need real `hermes` binary/CLI available.
  - Need isolated `HERMES_HOME`, not your main personal memory.

- Claude Code test environment.
  - Need permission to modify test MCP config.
  - No Anthropic account credential is needed for MCP config validation unless we run full Claude Code turns.

- Codex test environment.
  - Need permission to add MCP config for a test workspace.

- Cursor test environment.
  - Need access to MCP settings or config location.

- Gemini CLI test environment.
  - Need installed CLI and auth mode for a test account if full agent turn tests are required.

### Required For Publishing

- GitHub token for `altyshalu/jessica-knowledge-graph`.
  - Needed only when creating releases, CI secrets, package publishing, or PR automation.
  - Minimal scopes:
    - repo contents write for PRs/releases
    - actions secrets write only if configuring CI secrets

- PyPI trusted publisher setup or PyPI API token.
  - Needed only if publishing `jkg` package.

- Docker Hub/GHCR token.
  - Needed only if publishing Docker images.

### Credentials Not Needed

- Do not provide personal primary email passwords.
- Do not provide broad cloud admin credentials.
- Do not provide production agent memory databases.
- Do not provide unrestricted GitHub org admin tokens unless a specific publishing task requires it.

## Implementation Roadmap

### Phase 0: Stabilize Current Repo

Goal: make the current package installable and honestly testable.

Tasks:

- [ ] Add real `main_cli` or move CLI to `jkg/cli/main.py`.
- [ ] Fix `pyproject.toml` dependencies and optional extras.
- [ ] Remove unconditional heavy imports.
- [ ] Change default DB path to user data dir or explicit config.
- [ ] Remove zero-vector behavior.
- [ ] Replace silent `except: pass` with typed errors/logging.
- [ ] Add `tests/` with pytest.
- [ ] Add GitHub Actions.
- [ ] Add `jkg doctor`.
- [ ] Update README to match real behavior.

Exit criteria:

- [ ] clean install works
- [ ] installed CLI works
- [ ] local tests pass
- [ ] no hidden fallbacks in core path

### Phase 1: Provider Abstraction

Goal: cleanly support local, OpenAI, Anthropic, Gemini, DeepSeek, and Ollama.

Tasks:

- [ ] Create provider interfaces.
- [ ] Implement OpenAI LLM.
- [ ] Implement OpenAI embeddings.
- [ ] Implement Anthropic LLM.
- [ ] Implement Gemini LLM.
- [ ] Implement Gemini embeddings.
- [ ] Implement DeepSeek LLM.
- [ ] Implement Ollama LLM.
- [ ] Implement Ollama embeddings.
- [ ] Implement explicit provider health checks.
- [ ] Add provider contract tests.

Exit criteria:

- [ ] selected provider works
- [ ] missing credentials fail clearly
- [ ] embedding dimensions are enforced
- [ ] no implicit provider fallback

### Phase 2: Postgres + pgvector

Goal: move production storage to Postgres.

Tasks:

- [ ] Add Postgres repository.
- [ ] Add Alembic migrations.
- [ ] Add pgvector extension migration.
- [ ] Add HNSW indexes.
- [ ] Add full-text indexes.
- [ ] Add tenant/owner scoping.
- [ ] Add transaction boundaries.
- [ ] Add backup/restore docs.
- [ ] Keep SQLite adapter only as explicit local/dev option.

Exit criteria:

- [ ] Docker Postgres starts
- [ ] migrations run
- [ ] ingest/query/delete works against Postgres
- [ ] pgvector search works
- [ ] no SQLite dependency in production mode

### Phase 3: Correctness

Goal: make advertised memory behavior true.

Tasks:

- [ ] Redesign temporal model.
- [ ] Implement contradiction detection and supersession.
- [ ] Implement entity canonicalization.
- [ ] Implement four-layer fusion with explainable scores.
- [ ] Implement full GDPR deletion.
- [ ] Implement session context generation with provenance.
- [ ] Implement confidence updates with guardrails.
- [ ] Add quality regression corpus.

Exit criteria:

- [ ] temporal tests pass
- [ ] contradiction tests pass
- [ ] privacy deletion tests pass
- [ ] semantic noise tests pass
- [ ] fusion tests pass

### Phase 4: Server, Docker, MCP

Goal: make JKG easy to deploy and connect.

Tasks:

- [ ] FastAPI server.
- [ ] Auth.
- [ ] Dockerfile.
- [ ] Compose.
- [ ] Health/readiness endpoints.
- [ ] MCP stdio server.
- [ ] MCP HTTP server.
- [ ] MCP docs.
- [ ] `jkg doctor mcp`.

Exit criteria:

- [ ] `docker compose up` works on clean server
- [ ] MCP stdio works with real client
- [ ] MCP HTTP rejects unauthenticated calls
- [ ] MCP HTTP works with auth

### Phase 5: Agent Integrations

Goal: make JKG actually usable in personal agents.

Tasks:

- [ ] Hermes plugin package.
- [ ] Claude Code MCP guide.
- [ ] Codex MCP guide.
- [ ] Cursor MCP guide.
- [ ] Gemini CLI guide.
- [ ] One-command installers where safe.

Exit criteria:

- [ ] Hermes lifecycle works in isolated `HERMES_HOME`
- [ ] Claude Code can query and write memory through MCP
- [ ] Codex can query and write memory through MCP
- [ ] Cursor can query and write memory through MCP
- [ ] Gemini CLI path verified

### Phase 6: Open Source Release

Goal: publish without embarrassing sharp users.

Tasks:

- [ ] Rewrite README around real architecture.
- [ ] Add `CONTRIBUTING.md`.
- [ ] Add `CODE_OF_CONDUCT.md`.
- [ ] Add `SECURITY.md`.
- [ ] Add `CHANGELOG.md`.
- [ ] Add issue templates.
- [ ] Add PR template.
- [ ] Add architecture docs.
- [ ] Add threat model.
- [ ] Add benchmark methodology.
- [ ] Add real benchmark comparison results against top memory providers.
- [ ] Add CLARK ablation report showing where CLARK improves recall, ranking, temporal correctness, or latency.
- [ ] Add migration guide.
- [ ] Add examples.
- [ ] Tag release.
- [ ] Publish package.
- [ ] Publish Docker image.

Exit criteria:

- [ ] CI green
- [ ] docs match code
- [ ] release artifacts published
- [ ] install guide verified from scratch

## Documentation To Create

- `README.md`
- `docs/architecture.md`
- `docs/configuration.md`
- `docs/providers.md`
- `docs/docker.md`
- `docs/mcp.md`
- `docs/hermes.md`
- `docs/cli.md`
- `docs/testing.md`
- `docs/security.md`
- `docs/privacy.md`
- `docs/benchmarks.md`
- `docs/troubleshooting.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `CODE_OF_CONDUCT.md`
- `CHANGELOG.md`
- `.env.example`

## Research Notes And Sources

- MCP Python SDK: official SDK supports FastMCP, tools, resources, prompts, stdio, streamable HTTP, stateless HTTP, and OAuth 2.1 resource server patterns.
- MCP authorization spec: HTTP MCP authorization is transport-level and based on OAuth 2.1-style mechanisms; authorization must be treated as part of production design, not an afterthought.
- pgvector: official docs support `vector`, HNSW indexes, cosine operator classes, query-time `hnsw.ef_search`, and iterative scans in pgvector 0.8.0+.
- LiteLLM: useful reference for provider breadth, but JKG should avoid default automatic fallbacks because hidden fallback violates the trust boundary.
- DeepSeek: official docs list `deepseek-v4-flash` and `deepseek-v4-pro`; older `deepseek-chat` / `deepseek-reasoner` aliases are marked for deprecation on 2026-07-24.
- Ollama: official API serves locally at `http://localhost:11434/api`; embeddings use `/api/embed` and return normalized vectors.
- OpenAI embeddings: official API supports `text-embedding-3-small` and `text-embedding-3-large`.
- Hermes: current memory provider model expects external plugins implementing `MemoryProvider`, lifecycle hooks, and setup integration rather than adding providers in-tree.

Primary source URLs:

- https://modelcontextprotocol.io/docs/sdk
- https://github.com/modelcontextprotocol/python-sdk
- https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- https://github.com/pgvector/pgvector
- https://docs.litellm.ai/
- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/api/create-chat-completion
- https://developers.openai.com/api/reference/resources/embeddings
- https://ai.google.dev/gemini-api/docs/embeddings
- https://docs.ollama.com/api/introduction
- https://docs.ollama.com/capabilities/embeddings
- https://hermes.dhuar.com/en/user-guide/features/memory-providers/
- https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md

## Final Recommendation

Do not open-source as production-ready until Phase 0 through Phase 4 are complete. A limited "prototype preview" release is possible earlier, but it must say prototype clearly and remove inflated claims.

The strongest path is:

1. Fix installability and test harness.
2. Build provider abstraction with explicit failure.
3. Move production storage to Postgres + pgvector.
4. Prove correctness with real edge-case tests.
5. Ship MCP and Docker.
6. Ship Hermes plugin.
7. Then publish loudly.
