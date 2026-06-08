# Agent Integrations

JKG exposes two integration paths:

- MCP for Codex, Claude Code, Cursor, Gemini CLI, and any MCP-compatible client.
- A Hermes memory provider plugin that talks to the JKG HTTP API.

## MCP Stdio

Use stdio for local single-user agents. The agent starts the JKG MCP process and talks to it over stdin/stdout.

```json
{
  "mcpServers": {
    "jkg": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/jessica-knowledge-graph", "jkg", "mcp"],
      "env": {
        "JKG_DATABASE_URL": "postgresql://jkg:strong-password@127.0.0.1:5432/jkg",
        "GEMINI_API_KEY": "${env:GEMINI_API_KEY}",
        "DEEPSEEK_API_KEY": "${env:DEEPSEEK_API_KEY}"
      }
    }
  }
}
```

If the client does not support `${env:...}` expansion, put credentials in the shell environment that launches the client.

## Codex

Codex CLI stores MCP configuration in `~/.codex/config.toml`. You can also add a server with the CLI:

```bash
codex mcp add jkg -- uv run --directory /absolute/path/to/jessica-knowledge-graph jkg mcp
codex mcp list
```

Template: [integrations/codex/config.toml](../integrations/codex/config.toml)

## Claude Code

Claude Code supports project `.mcp.json` files. Put the template at the root of the project where you want Claude Code to use JKG.

Template: [integrations/claude-code/.mcp.json](../integrations/claude-code/.mcp.json)

## Cursor

Cursor supports project `.cursor/mcp.json` and global `~/.cursor/mcp.json` configuration.

Template: [integrations/cursor/mcp.json](../integrations/cursor/mcp.json)

## Gemini CLI

Gemini CLI reads `mcpServers` from `settings.json`.

Template: [integrations/gemini-cli/settings.json](../integrations/gemini-cli/settings.json)

## Hermes

Hermes memory providers live in `plugins/memory/<name>/`. The JKG provider is in [integrations/hermes/jkg](../integrations/hermes/jkg).

Install into a Hermes checkout or Hermes home:

```bash
mkdir -p "$HERMES_HOME/plugins/memory"
cp -R integrations/hermes/jkg "$HERMES_HOME/plugins/memory/jkg"
```

Configure:

```bash
export JKG_API_URL=http://127.0.0.1:8000
export JKG_AUTH_TOKEN=replace-with-your-token
```

Then set the active Hermes memory provider to `jkg` using `hermes memory setup` or the Hermes plugin configuration flow.

The Hermes provider requires a running JKG HTTP server. It does not start a server or create a fake local store.

## Verification

Minimum local checks:

```bash
uv run jkg doctor
uv run jkg mcp
```

Minimum server checks:

```bash
uv run jkg serve 8000
curl http://127.0.0.1:8000/healthz
curl -H "Authorization: Bearer $JKG_AUTH_TOKEN" http://127.0.0.1:8000/v1/stats
```

Full verification requires real provider credentials and a real Postgres/pgvector database.
