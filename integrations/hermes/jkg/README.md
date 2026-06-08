# JKG Hermes Memory Provider

This plugin connects Hermes Agent to a running JKG HTTP API.

It does not start JKG, create a local fake store, or silently disable memory. If `JKG_API_URL` or `JKG_AUTH_TOKEN` is missing, the provider reports unavailable.

## Install

```bash
mkdir -p "$HERMES_HOME/plugins/memory"
cp -R integrations/hermes/jkg "$HERMES_HOME/plugins/memory/jkg"
```

## Configure

```bash
export JKG_API_URL=http://127.0.0.1:8000
export JKG_AUTH_TOKEN=replace-with-your-token
```

Start JKG:

```bash
uv run jkg serve 8000
```

Then select `jkg` in Hermes through `hermes memory setup` or the Hermes plugin menu.

## Tools

- `jkg_search_memory`
- `jkg_remember_memory`

## Lifecycle

- `prefetch()` queries JKG and returns formatted recall context.
- `sync_turn()` stores completed user/assistant turns.
- `on_memory_write()` mirrors built-in Hermes memory writes into JKG.
