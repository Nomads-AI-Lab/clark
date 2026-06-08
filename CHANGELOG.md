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
- Added verification status for real provider, Docker, Postgres, and LongMemEval-S smoke runs.
- Added a real MCP stdio client handshake test.
- Added batch Gemini embeddings and Postgres bulk inserts for benchmark ingestion.
- Recorded a 5-question real LongMemEval-S bounded benchmark run.
- Added bearer-authenticated MCP Streamable HTTP server and tests.
- Added a real provider comparison runner for JKG and Mem0 OSS.
- Recorded the first real JKG-vs-Mem0 LongMemEval-S comparison result.
- Added partial LongMemEval-S artifact preservation for Gemini quota failures.
- Recorded the slow background LongMemEval-S resume job and checkpoint status.
- Added Gemini timeout retry controls and resumed the full LongMemEval-S job.
- Recorded the completed 500-question LongMemEval-S JKG benchmark result.
- Added checkpoint/resume support to the provider comparison runner.
- Added external published memory benchmark baselines with attribution and caveats.
