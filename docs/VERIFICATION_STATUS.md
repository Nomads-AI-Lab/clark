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
  - Started Clark API in production mode with bearer auth.
  - Ran `clark migrate` inside the API container.
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
  - Latest artifact path on the test server: `/opt/clark-production-ready-test/benchmark/results/remote-longmemeval-batch-smoke.json`.
- Remote LongMemEval-S bounded run:
  - Scored questions: 5.
  - Result: recall@1/3/5/10/20 = 0.8.
  - Elapsed: 11.061 seconds.
  - Artifact path on the test server: `/opt/clark-production-ready-test/benchmark/results/remote-longmemeval-batch5.json`.
- Remote LongMemEval-S full run attempt:
  - Full 500-question run completed after checkpoint/resume and slower request pacing.
  - Checkpoint: `/opt/clark-production-ready-test/benchmark/results/remote-longmemeval-full.checkpoint.jsonl`.
  - Final artifact: `/opt/clark-production-ready-test/benchmark/results/remote-longmemeval-full-resume-slow-timeout.json`.
  - Dataset: `/opt/clark-bench-data/longmemeval_s_cleaned.json`.
  - Scored: 500/500, skipped abstention: 0, skipped invalid: 0.
  - Result: recall@1 = 446/500, recall@3 = 486/500, recall@5 = 493/500, recall@10 = 497/500, recall@20 = 498/500.
  - Elapsed: 4963.962 seconds.
  - Resume support, checkpoint summary, and Gemini retry/backoff are implemented.
- Remote provider comparison:
  - Providers: Clark Postgres/pgvector and Mem0 OSS.
  - Shared credentials/providers: Gemini embeddings and DeepSeek LLM.
  - Dataset slice: first real LongMemEval-S question.
  - Result: both providers recall@1/3/5/10/20 = 1.0.
  - Elapsed: Clark 2.341 seconds, Mem0 260.276 seconds.
  - Artifact path on the test server: `/opt/clark-production-ready-test/benchmark/results/provider-comparison-clark-mem0-q1.json`.
- External published baselines collected:
  - MemPalace published raw LongMemEval Recall@5: 96.6%.
  - agentmemory published LongMemEval-S retrieval R@5: 95.2%.
  - Mem0 official research published LongMemEval score: 93.4.
  - These are not reproduced locally and are documented separately from verified Clark runs.
- Local MCP stdio handshake:
  - Starts the real `clark mcp` server over stdio through the official MCP Python SDK.
  - Runs initialize, list tools, and `clark_health`.
- Local authenticated MCP Streamable HTTP:
  - Starts the real ASGI MCP app through `uvicorn`.
  - Missing bearer token returns `401` with `WWW-Authenticate: Bearer`.
  - Authorized official MCP Python SDK streamable HTTP client initializes and lists tools.

## Not Yet Fully Verified

- Competitive benchmark runs against top memory providers.
  - Published external baselines have been collected.
  - Full local reproduction across providers remains incomplete because Mem0's real extraction path is too slow for multi-question runs under the current budget/time constraints.
- Real Claude Code, Codex, Cursor, and Gemini CLI MCP handshakes on the remote server.
  - The server currently does not have `claude`, `codex`, `cursor`, or `gemini` CLIs installed.
  - Template parsing is covered by tests, but client runtime connection is not.
- Real Hermes plugin lifecycle inside Hermes.
  - The plugin compiles, but Hermes is not installed on the test server.
- OAuth 2.1 resource server metadata for public multi-tenant MCP.
  - Current implementation supports bearer-token authenticated Streamable HTTP.
  - Public multi-tenant deployments should still front Clark with a proper OAuth gateway.
