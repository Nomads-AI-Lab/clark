# Clark Hermes Memory Provider

This plugin connects Hermes Agent to a running Clark HTTP API.

It does not start Clark, create a local fake store, or silently disable memory. If `CLARK_API_URL` or `CLARK_AUTH_TOKEN` is missing, the provider reports unavailable.

## Install

```bash
mkdir -p "$HERMES_HOME/plugins/memory"
cp -R integrations/hermes/clark "$HERMES_HOME/plugins/memory/clark"
```

## Configure

```bash
export CLARK_API_URL=http://127.0.0.1:8000
export CLARK_AUTH_TOKEN=replace-with-your-token
```

Start Clark:

```bash
uv run clark serve 8000
```

Then select `clark` in Hermes through `hermes memory setup` or the Hermes plugin menu.

## Tools

- `clark_search_memory`
- `clark_remember_memory`

## Lifecycle

- `prefetch()` queries Clark and returns formatted recall context.
- `sync_turn()` stores completed user/assistant turns.
- `on_memory_write()` mirrors built-in Hermes memory writes into Clark.
