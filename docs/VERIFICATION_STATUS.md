# Verification Status

Last updated: 2026-06-08.

This file tracks real verification runs for the production-readiness branch. It is not a substitute for CI.

## Passed

- Local provider contracts with real Gemini and DeepSeek credentials:
  - `tests/test_provider_contracts.py`
  - Validated Gemini embeddings and DeepSeek JSON extraction.
- Local Postgres/pgvector storage:
  - `tests/test_postgres_backend.py`
  - Used a real `pgvector/pgvector:pg16` container and Gemini embeddings.
- Remote server Python test suite:
  - `uv sync --extra test --extra server --extra mcp --extra postgres`
  - `uv run pytest`
  - `uv run pytest tests/test_provider_contracts.py`
- Remote Docker production smoke:
  - Built the Docker image on `82.38.4.10`.
  - Started a real `pgvector/pgvector:pg16` container.
  - Started JKG API in production mode with bearer auth.
  - Ran `jkg migrate` inside the API container.
  - Wrote memory through `POST /v1/memories`.
  - Retrieved it through `POST /v1/query`.
- Remote LongMemEval-S smoke:
  - Dataset: `LIXINYI33/longmemeval-s/longmemeval_s_cleaned.json` from Hugging Face.
  - Size: 500 questions, 265 MB downloaded on the test server.
  - Bounded run: first 1 question, 53 haystack sessions.
  - Backend: real Postgres/pgvector and Gemini embeddings.
  - Result: recall@1/3/5/10/20 = 1.0 for the single scored question.
  - Initial per-item embedding run: 21.089 seconds.
  - Batch Gemini embedding run: 2.106 seconds.
  - Latest artifact path on the test server: `/opt/jkg-production-ready-test/benchmark/results/remote-longmemeval-batch-smoke.json`.
- Remote LongMemEval-S bounded run:
  - Scored questions: 5.
  - Result: recall@1/3/5/10/20 = 0.8.
  - Elapsed: 11.061 seconds.
  - Artifact path on the test server: `/opt/jkg-production-ready-test/benchmark/results/remote-longmemeval-batch5.json`.
- Local MCP stdio handshake:
  - Starts the real `jkg mcp` server over stdio through the official MCP Python SDK.
  - Runs initialize, list tools, and `jkg_health`.

## Not Yet Fully Verified

- Full LongMemEval-S run across all 500 questions.
  - Batch embedding is implemented, but the full run still needs cost/progress controls and a deliberate run window.
- Competitive benchmark runs against top memory providers.
  - Requires installing and configuring those providers in the same environment.
- Real Claude Code, Codex, Cursor, and Gemini CLI MCP handshakes on the remote server.
  - The server currently does not have `claude`, `codex`, `cursor`, or `gemini` CLIs installed.
  - Template parsing is covered by tests, but client runtime connection is not.
- Real Hermes plugin lifecycle inside Hermes.
  - The plugin compiles, but Hermes is not installed on the test server.
- Remote authenticated MCP over HTTP.
  - Stdio MCP exists; production remote MCP auth still needs a gateway/OAuth design before public exposure.
