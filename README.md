# Clark

Clark is a memory layer for personal agents. It stores profile, factual, episodic, and procedural memory behind one query surface, so tools such as Hermes, Codex, Claude Code, Gemini CLI, Cursor, and MCP-compatible agents can retrieve useful context without stitching several memory systems together.

The repository is being hardened for open-source production use. The current production path is:

- Postgres 16 with `pgvector` for server deployments.
- SQLite plus `sqlite-vec` for local development and single-user experiments.
- DeepSeek for LLM extraction by default.
- Gemini embeddings by default.
- FastAPI HTTP API with bearer-token auth.
- MCP server for agent-native integration.
- `uv` for local development and CI-style commands.

## Status

Clark is ready for public open-source development and production-path evaluation. The local CLI, HTTP API, MCP transports, Docker path, Postgres/pgvector backend, and provider contracts are covered by real tests.

Benchmark claims are intentionally conservative: publish comparative numbers only when they come from the checked-in benchmark runners, real provider credentials, and recorded artifacts.

## Install

```bash
git clone https://github.com/Nomads-AI-Lab/clark.git
cd clark
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
CLARK_ENV=production
CLARK_AUTH_TOKEN=replace-with-a-long-random-token
CLARK_DATABASE_URL=postgresql://clark:strong-password@postgres:5432/clark
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...
```

Important behavior:

- Clark does not silently replace missing providers with fake embeddings or fake LLM output.
- If a required provider key is absent for the code path you run, the operation fails explicitly.
- Server production mode requires `CLARK_AUTH_TOKEN`.

## CLI

```bash
uv run clark doctor
uv run clark migrate
uv run clark stats
uv run clark remember "Alice prefers concise technical answers"
uv run clark query "How should I answer Alice?"
uv run clark session-start
```

`clark migrate` applies the Postgres/pgvector schema when `CLARK_DATABASE_URL` is set. Without `CLARK_DATABASE_URL`, the legacy SQLite schema initializes on first use.

## Docker

```bash
cp .env.example .env
# edit .env and set strong real values
docker compose up --build
```

Then migrate the database:

```bash
docker compose exec clark-api clark migrate
```

Health and API smoke:

```bash
curl http://127.0.0.1:8000/healthz
curl -H "Authorization: Bearer $CLARK_AUTH_TOKEN" http://127.0.0.1:8000/v1/stats
```

## HTTP API

```bash
uv run clark serve 8000
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
  -H "Authorization: Bearer $CLARK_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"Alice is building a production memory layer","source":"api"}'
```

## MCP

Run a stdio MCP server:

```bash
uv run clark mcp
```

Run streamable HTTP transport:

```bash
uv run clark mcp streamable-http
```

Available tools:

- `clark_health`
- `clark_stats`
- `clark_query`
- `clark_remember`

Resource:

- `clark://stats`

When `CLARK_DATABASE_URL` is set, MCP uses the Postgres backend. Otherwise it uses the local SQLite backend.

## Python API

```python
from clark import HybridMemory

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
docker run --rm -d --name clark-pgvector-test \
  -p 15434:5432 \
  -e POSTGRES_DB=clark \
  -e POSTGRES_USER=clark \
  -e POSTGRES_PASSWORD=clark-local-dev-password \
  pgvector/pgvector:pg16

CLARK_DATABASE_URL=postgresql://clark:clark-local-dev-password@127.0.0.1:15434/clark \
GEMINI_API_KEY=... \
uv run pytest tests/test_postgres_backend.py

docker rm -f clark-pgvector-test
```

## Open-Source Documents

- [Production readiness roadmap](docs/PRODUCTION_OPEN_SOURCE_PLAN.md)
- [Agent integrations](docs/INTEGRATIONS.md)
- [Benchmark methodology](docs/BENCHMARKS.md)
- [Verification status](docs/VERIFICATION_STATUS.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [MIT License](LICENSE)

## Security

Do not expose the HTTP API without `CLARK_AUTH_TOKEN`. Do not commit `.env`, database dumps, provider keys, or personal memory exports. Treat memory contents as sensitive user data.
