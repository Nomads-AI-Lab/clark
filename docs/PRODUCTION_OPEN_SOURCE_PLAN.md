# Clark Production Open Source Readiness

Clark is a production-path memory layer for personal agents. It exposes profile, factual, episodic, and procedural memory through Python, CLI, HTTP, MCP, Docker, and agent integration templates.

This document is the public readiness contract for the repository. It records what must stay true before public releases and what remains intentionally scoped.

## Release Surface

- Python package: `clark`
- CLI: `clark`
- Local storage: SQLite plus `sqlite-vec`
- Production storage: Postgres 16 plus `pgvector`
- HTTP API: FastAPI with bearer-token auth
- MCP: stdio and Streamable HTTP
- Integrations: Codex, Claude Code, Cursor, Gemini CLI, Hermes templates
- Containers: Dockerfile and Compose for local production-path deployment

## Trust Boundaries

Clark must keep these guarantees:

- No fake provider output in production paths.
- No hidden embedding or LLM fallback.
- Missing credentials fail explicitly.
- Production HTTP mode requires `CLARK_AUTH_TOKEN`.
- Public Streamable HTTP MCP mode requires `CLARK_MCP_AUTH_TOKEN` or `CLARK_AUTH_TOKEN`.
- Raw memory data, database files, provider keys, and `.env` files are never committed.
- Benchmark claims must point to real datasets, provider credentials, and recorded artifacts.

## Verification Gates

Run these gates before publishing release artifacts:

```bash
uv lock --check
uv run python -m compileall clark
uv run pytest
uv run clark doctor
uv run clark migrate
```

Run the real Postgres path when Docker is available:

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

Run real provider contracts only with live credentials:

```bash
GEMINI_API_KEY=... DEEPSEEK_API_KEY=... uv run pytest tests/test_provider_contracts.py
```

## Public Repo Checklist

- README matches real commands and package names.
- `pyproject.toml` package metadata points to `Nomads-AI-Lab/clark`.
- CI runs format-free Python compile and pytest checks.
- Dependabot is enabled for Python and GitHub Actions.
- Secret scanning and push protection are enabled on GitHub.
- Security, contributing, code of conduct, changelog, benchmark, and integration docs are present.
- No old package, repo, env var, tool, or folder names remain in tracked files.

## Current Limitations

- OAuth 2.1 resource metadata is not built into Clark; public multi-tenant deployments should front the MCP HTTP endpoint with an OAuth-aware gateway.
- Provider and benchmark tests require real external credentials and are intentionally not replaced with fake stand-ins.
- SQLite mode is for local single-user use. Shared deployments should use Postgres/pgvector.

## Release Rule

Do not tag a public release unless the local gates pass and any release-specific external gates have current artifacts recorded in [Verification Status](VERIFICATION_STATUS.md).
