from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_mcp_stdio_lists_and_calls_health_tool(tmp_path) -> None:
    async def run_client() -> None:
        env = os.environ.copy()
        env["CLARK_DB_PATH"] = str(tmp_path / "memory.db")
        env.pop("CLARK_DATABASE_URL", None)

        server = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from clark.cli import main; main(['mcp'])"],
            env=env,
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                assert {"clark_health", "clark_stats", "clark_query", "clark_remember"} <= tool_names

                result = await session.call_tool("clark_health", {})
                text = "".join(getattr(item, "text", "") for item in result.content)
                assert "overall_ok" in text

    asyncio.run(run_client())
