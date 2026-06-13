"""HTTP API for Clark server deployments."""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .db import PostgresMemory
from .doctor import collect_diagnostics
from .memory import HybridMemory


app = FastAPI(title="Clark", version="7.0.0")


class MemoryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    source: str = Field(default="api", max_length=128)


class QueryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    layers: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=100)


def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
    token = os.environ.get("CLARK_AUTH_TOKEN")
    if not token:
        if os.environ.get("CLARK_ENV") == "production":
            raise HTTPException(status_code=503, detail="CLARK_AUTH_TOKEN is required in production")
        return

    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


def get_memory() -> Any:
    if os.environ.get("CLARK_DATABASE_URL"):
        return PostgresMemory.from_env()
    return HybridMemory()


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict:
    diagnostics = collect_diagnostics()
    if not diagnostics["overall_ok"]:
        raise HTTPException(status_code=503, detail=diagnostics)
    return diagnostics


@app.get("/v1/stats", dependencies=[Depends(require_auth)])
def stats(memory: Any = Depends(get_memory)) -> dict:
    return memory.stats()


@app.post("/v1/query", dependencies=[Depends(require_auth)])
def query(request: QueryRequest, memory: Any = Depends(get_memory)) -> dict:
    return memory.query(request.text, layers=request.layers, limit=request.limit)


@app.post("/v1/memories", dependencies=[Depends(require_auth)])
def remember(request: MemoryRequest, memory: Any = Depends(get_memory)) -> dict:
    return memory.remember(request.text, source=request.source)
