from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_mcp_http_rejects_missing_bearer_token() -> None:
    port = _free_port()
    env = os.environ.copy()
    env["JKG_ENV"] = "production"
    env["JKG_MCP_AUTH_TOKEN"] = "secret-token"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "jkg.mcp_http:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_port(port)
        response = httpx.post(f"http://127.0.0.1:{port}/mcp", json={})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_mcp_http_authenticated_client_lists_tools(tmp_path) -> None:
    port = _free_port()
    env = os.environ.copy()
    env["JKG_ENV"] = "production"
    env["JKG_MCP_AUTH_TOKEN"] = "secret-token"
    env["JKG_DB_PATH"] = str(tmp_path / "memory.db")
    env.pop("JKG_DATABASE_URL", None)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "jkg.mcp_http:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_port(port)

        async def run_client() -> None:
            client = httpx.AsyncClient(
                headers={"Authorization": "Bearer secret-token"},
                timeout=httpx.Timeout(30, read=60),
                follow_redirects=True,
            )
            async with client:
                async with streamable_http_client(
                    f"http://127.0.0.1:{port}/mcp",
                    http_client=client,
                ) as (read, write, _get_session_id):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        assert "jkg_health" in {tool.name for tool in tools.tools}

        asyncio.run(run_client())
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _wait_for_port(port: int) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"port {port} did not open")
