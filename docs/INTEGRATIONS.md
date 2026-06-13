# Agent Integrations

Clark exposes two integration paths:

- MCP for Codex, Claude Code, Cursor, Gemini CLI, and any MCP-compatible client.
- A Hermes memory provider plugin that talks to the Clark HTTP API.

## MCP Stdio

Use stdio for local single-user agents. The agent starts the Clark MCP process and talks to it over stdin/stdout.

```json
{
  "mcpServers": {
    "clark": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/clark", "clark", "mcp"],
      "env": {
        "CLARK_DATABASE_URL": "postgresql://clark:strong-password@127.0.0.1:5432/clark",
        "GEMINI_API_KEY": "${env:GEMINI_API_KEY}",
        "DEEPSEEK_API_KEY": "${env:DEEPSEEK_API_KEY}"
      }
    }
  }
}
```

If the client does not support `${env:...}` expansion, put credentials in the shell environment that launches the client.

## MCP Streamable HTTP

Use Streamable HTTP for remote clients and service deployments. Production mode requires a bearer token.

```bash
CLARK_ENV=production \
CLARK_MCP_AUTH_TOKEN=replace-with-a-long-random-token \
uv run clark mcp streamable-http 8001
```

Clients must send this header on every MCP HTTP request:

```text
Authorization: Bearer <CLARK_MCP_AUTH_TOKEN>
```

The MCP endpoint is:

```text
http://host:8001/mcp
```

## Codex

Codex CLI stores MCP configuration in `~/.codex/config.toml`. You can also add a server with the CLI:

```bash
codex mcp add clark -- uv run --directory /absolute/path/to/clark clark mcp
codex mcp list
```

Template: [integrations/codex/config.toml](../integrations/codex/config.toml)

## Claude Code

Claude Code supports project `.mcp.json` files. Put the template at the root of the project where you want Claude Code to use Clark.

Template: [integrations/claude-code/.mcp.json](../integrations/claude-code/.mcp.json)

## Cursor

Cursor supports project `.cursor/mcp.json` and global `~/.cursor/mcp.json` configuration.

Template: [integrations/cursor/mcp.json](../integrations/cursor/mcp.json)

## Gemini CLI

Gemini CLI reads `mcpServers` from `settings.json`.

Template: [integrations/gemini-cli/settings.json](../integrations/gemini-cli/settings.json)

## Hermes

Hermes memory providers live in `plugins/memory/<name>/`. The Clark provider is in [integrations/hermes/clark](../integrations/hermes/clark).

Install into a Hermes checkout or Hermes home:

```bash
mkdir -p "$HERMES_HOME/plugins/memory"
cp -R integrations/hermes/clark "$HERMES_HOME/plugins/memory/clark"
```

Configure:

```bash
export CLARK_API_URL=http://127.0.0.1:8000
export CLARK_AUTH_TOKEN=replace-with-your-token
```

Then set the active Hermes memory provider to `clark` using `hermes memory setup` or the Hermes plugin configuration flow.

The Hermes provider requires a running Clark HTTP server. It does not start a server or create a fake local store.

## Verification

Minimum local checks:

```bash
uv run clark doctor
uv run clark mcp
CLARK_ENV=production CLARK_MCP_AUTH_TOKEN=test-token uv run clark mcp streamable-http 8001
```

Minimum server checks:

```bash
uv run clark serve 8000
curl http://127.0.0.1:8000/healthz
curl -H "Authorization: Bearer $CLARK_AUTH_TOKEN" http://127.0.0.1:8000/v1/stats
```

Full verification requires real provider credentials and a real Postgres/pgvector database.
