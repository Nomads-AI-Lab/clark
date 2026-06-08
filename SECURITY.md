# Security Policy

JKG stores personal memory. Treat all memory records, database backups, logs, and exports as sensitive data.

## Supported Versions

JKG is pre-1.0 hardening work. Security fixes should target the default branch and any active release branch once releases begin.

## Reporting a Vulnerability

Do not open a public issue for a vulnerability that exposes secrets, private memory, auth bypasses, or remote code execution risk.

Report privately to the repository owner through GitHub private vulnerability reporting when available, or contact the maintainer directly.

Include:

- Affected version or commit.
- Steps to reproduce.
- Impact.
- Whether credentials, memory contents, or user data can be exposed.
- Suggested fix if known.

## Security Requirements

- Production HTTP deployments must set `JKG_AUTH_TOKEN`.
- Provider credentials must be supplied through environment variables or secret managers.
- `.env`, database files, memory exports, and logs containing user data must not be committed.
- Docker deployments should use strong Postgres passwords, private networks, and TLS at the reverse proxy or platform edge.
- Public Streamable HTTP MCP deployments must set `JKG_MCP_AUTH_TOKEN` or `JKG_AUTH_TOKEN`. Stdio MCP is intended for local agent use.

## Current Limitations

- Fine-grained authorization and multi-tenant policy enforcement are still being expanded.
- Benchmark and integration runs require real provider keys and should be executed in isolated environments.
- Legacy SQLite mode is best suited for local single-user use, not shared production servers.
