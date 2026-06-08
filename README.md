# Jessica Knowledge Graph

Jessica Knowledge Graph (JKG) is a memory layer for personal agents. It stores profile, factual, episodic, and procedural memory behind one query surface, so tools such as Hermes, Codex, Claude Code, Gemini CLI, Cursor, and MCP-compatible agents can retrieve useful context without stitching several memory systems together.

The repository is being hardened for open-source production use. The current production path is:

- Postgres 16 with `pgvector` for server deployments.
- SQLite plus `sqlite-vec` for local development and single-user experiments.
- DeepSeek for LLM extraction by default.
- Gemini embeddings by default.
- FastAPI HTTP API with bearer-token auth.
- MCP server for agent-native integration.
- `uv` for local development and CI-style commands.

## Status

JKG is usable, but not ready for strong public benchmark claims yet. Before publishing comparative numbers, run the real benchmark suite against the intended provider credentials and datasets. Do not rely on older README benchmark tables from previous drafts.

## Install

```bash
git clone https://github.com/altyshalu/jessica-knowledge-graph.git
cd jessica-knowledge-graph
uv sync --extra test --extra server --extra mcp --extra postgres
```

For local editable development:

```bash
uv pip install -e ".[test,server,mcp,postgres]"
```

## Configuration

Create `.env` from `.env.example` and set real credentials:

```bash
cp .env.example .env
```

Required for production server mode:

```bash
JKG_ENV=production
JKG_AUTH_TOKEN=replace-with-a-long-random-token
JKG_DATABASE_URL=postgresql://jkg:strong-password@postgres:5432/jkg
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...
```

Important behavior:

- JKG does not silently replace missing providers with fake embeddings or fake LLM output.
- If a required provider key is absent for the code path you run, the operation fails explicitly.
- Server production mode requires `JKG_AUTH_TOKEN`.

## CLI

```bash
uv run jkg doctor
uv run jkg migrate
uv run jkg stats
uv run jkg remember "Alice prefers concise technical answers"
uv run jkg query "How should I answer Alice?"
uv run jkg session-start
```

`jkg migrate` applies the Postgres/pgvector schema when `JKG_DATABASE_URL` is set. Without `JKG_DATABASE_URL`, the legacy SQLite schema initializes on first use.

## Docker

```bash
cp .env.example .env
# edit .env and set strong real values
docker compose up --build
```

Then migrate the database:

```bash
docker compose exec jkg-api jkg migrate
```

Health and API smoke:

```bash
curl http://127.0.0.1:8000/healthz
curl -H "Authorization: Bearer $JKG_AUTH_TOKEN" http://127.0.0.1:8000/v1/stats
```

## HTTP API

```bash
uv run jkg serve 8000
```

Endpoints:

- `GET /healthz`
- `GET /readyz`
- `GET /v1/stats`
- `POST /v1/memories`
- `POST /v1/query`

Authenticated request:

```bash
curl -X POST http://127.0.0.1:8000/v1/memories \
  -H "Authorization: Bearer $JKG_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"Alice is building a production memory layer","source":"api"}'
```

## MCP

Run a stdio MCP server:

```bash
uv run jkg mcp
```

Run streamable HTTP transport:

```bash
uv run jkg mcp streamable-http
```

Available tools:

- `jkg_health`
- `jkg_stats`
- `jkg_query`
- `jkg_remember`

Resource:

- `jkg://stats`

When `JKG_DATABASE_URL` is set, MCP uses the Postgres backend. Otherwise it uses the local SQLite backend.

## Python API

```python
from jkg import HybridMemory

memory = HybridMemory()
memory.remember("Alice works on agent memory infrastructure")
result = memory.query("What does Alice work on?")
print(result["results"])
```

For production server deployments, prefer the HTTP API or MCP server over importing the legacy SQLite class directly.

## Tests

Run the local suite:

```bash
uv run pytest
```

Run real provider contract tests:

```bash
GEMINI_API_KEY=... DEEPSEEK_API_KEY=... uv run pytest tests/test_provider_contracts.py
```

Run real Postgres/pgvector integration tests:

```bash
docker run --rm -d --name jkg-pgvector-test \
  -p 15434:5432 \
  -e POSTGRES_DB=jkg \
  -e POSTGRES_USER=jkg \
  -e POSTGRES_PASSWORD=jkg-local-dev-password \
  pgvector/pgvector:pg16

JKG_DATABASE_URL=postgresql://jkg:jkg-local-dev-password@127.0.0.1:15434/jkg \
GEMINI_API_KEY=... \
uv run pytest tests/test_postgres_backend.py

docker rm -f jkg-pgvector-test
```

## Open-Source Documents

- [Production readiness roadmap](docs/PRODUCTION_OPEN_SOURCE_PLAN.md)
- [Agent integrations](docs/INTEGRATIONS.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [MIT License](LICENSE)

## Security

Do not expose the HTTP API without `JKG_AUTH_TOKEN`. Do not commit `.env`, database dumps, provider keys, or personal memory exports. Treat memory contents as sensitive user data.
