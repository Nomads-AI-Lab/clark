# Contributing to Clark

Thanks for helping improve Clark. This project is intended to become reliable infrastructure for personal agents, so contributions should favor correctness, clear failure modes, and real integration tests over broad but unverified feature surface.

## Development Setup

Use `uv`:

```bash
uv sync --extra test --extra server --extra mcp --extra postgres
uv run pytest
```

Install editable if needed:

```bash
uv pip install -e ".[test,server,mcp,postgres]"
```

## Contribution Rules

- Do not add silent fallbacks, fake providers, fake embeddings, or demo-only behavior.
- If an integration cannot run without credentials, fail explicitly and document the missing input.
- Keep credentials out of code, tests, logs, fixtures, and docs.
- Prefer small pull requests with one behavioral change.
- Add or update tests for every production behavior change.
- Use Postgres/pgvector for server-grade storage work.
- Keep SQLite compatibility for local development unless the change intentionally removes it.

## Testing Expectations

Run the base suite:

```bash
uv run pytest
```

Provider changes must run real contract tests:

```bash
GEMINI_API_KEY=... DEEPSEEK_API_KEY=... uv run pytest tests/test_provider_contracts.py
```

Storage changes must run real Postgres/pgvector tests:

```bash
CLARK_DATABASE_URL=postgresql://... GEMINI_API_KEY=... uv run pytest tests/test_postgres_backend.py
```

## Commit Style

Use Conventional Commits:

```text
feat: add provider registry
fix: reject missing Gemini embeddings
test: cover Postgres vector search
docs: update Docker setup
```

## Pull Request Checklist

- The change has a focused scope.
- The real path is tested.
- No credentials, database dumps, or personal memory exports are included.
- Public docs are updated when behavior changes.
- Any skipped test explains the missing real dependency.
