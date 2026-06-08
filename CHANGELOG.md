# Changelog

All notable changes to JKG will be documented in this file.

This project follows Conventional Commits and intends to follow Semantic Versioning once public releases begin.

## Unreleased

- Added installable `jkg` CLI entrypoint.
- Added real provider contracts for DeepSeek LLM extraction and Gemini embeddings.
- Added explicit failure for missing Gemini embedding credentials instead of zero-vector fallback.
- Added diagnostics command with `jkg doctor`.
- Added FastAPI HTTP server with bearer-token auth.
- Added Dockerfile and Docker Compose setup.
- Added MCP server with health, stats, query, and remember tools.
- Added Postgres/pgvector backend and migration command.
- Added production readiness roadmap and open-source contribution documents.
- Added MCP client configuration templates and Hermes memory provider plugin.
- Replaced the old benchmark script with a credential-gated Postgres/pgvector runner.
