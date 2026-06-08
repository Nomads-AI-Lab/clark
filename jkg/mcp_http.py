"""Authenticated Streamable HTTP MCP app for production deployments."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Awaitable, Callable

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount

from .mcp_server import mcp


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        token = os.environ.get("JKG_MCP_AUTH_TOKEN") or os.environ.get("JKG_AUTH_TOKEN")
        if not token:
            if os.environ.get("JKG_ENV") == "production":
                return JSONResponse(
                    {"detail": "JKG_MCP_AUTH_TOKEN or JKG_AUTH_TOKEN is required in production"},
                    status_code=503,
                )
            return await call_next(request)

        if request.headers.get("authorization") != f"Bearer {token}":
            return JSONResponse(
                {"detail": "invalid or missing bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


mcp.settings.streamable_http_path = "/"

app = Starlette(
    routes=[Mount("/mcp", app=mcp.streamable_http_app())],
    lifespan=lifespan,
)
app.add_middleware(BearerAuthMiddleware)
