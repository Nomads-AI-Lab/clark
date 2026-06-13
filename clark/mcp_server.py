"""Model Context Protocol server for Clark."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .db import PostgresMemory
from .doctor import collect_diagnostics
from .memory import HybridMemory


mcp = FastMCP("clark", json_response=True)


def _memory() -> Any:
    if os.environ.get("CLARK_DATABASE_URL"):
        return PostgresMemory.from_env()
    return HybridMemory()


@mcp.tool()
def clark_health() -> dict:
    """Return local Clark diagnostics without exposing secret values."""
    return collect_diagnostics()


@mcp.tool()
def clark_stats() -> dict:
    """Return memory database statistics."""
    return _memory().stats()


@mcp.tool()
def clark_query(text: str, limit: int = 10) -> dict:
    """Query Clark memory across profile, factual, episodic, and procedural layers."""
    return _memory().query(text, limit=limit)


@mcp.tool()
def clark_remember(text: str, source: str = "mcp") -> dict:
    """Store a memory through the configured real extraction providers."""
    return _memory().remember(text, source=source)


@mcp.resource("clark://stats")
def stats_resource() -> str:
    """Expose memory stats as an MCP resource."""
    return str(_memory().stats())


def main(transport: str = "stdio") -> None:
    if transport not in {"stdio", "streamable-http"}:
        raise ValueError("transport must be 'stdio' or 'streamable-http'")
    mcp.run(transport=transport)
