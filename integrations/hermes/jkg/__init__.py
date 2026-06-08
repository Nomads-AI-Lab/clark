"""Hermes memory provider for Jessica Knowledge Graph."""

from __future__ import annotations

import json
import os
from typing import Any

import requests
from agent.memory_provider import MemoryProvider


class JKGMemoryProvider(MemoryProvider):
    """Hermes MemoryProvider implementation backed by the JKG HTTP API."""

    def __init__(self) -> None:
        self._api_url = ""
        self._token = ""
        self._session_id = ""
        self._timeout = 10.0

    @property
    def name(self) -> str:
        return "jkg"

    def is_available(self) -> bool:
        return bool(os.environ.get("JKG_API_URL") and os.environ.get("JKG_AUTH_TOKEN"))

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        api_url = os.environ.get("JKG_API_URL")
        token = os.environ.get("JKG_AUTH_TOKEN")
        if not api_url:
            raise RuntimeError("JKG_API_URL is required for the JKG Hermes provider")
        if not token:
            raise RuntimeError("JKG_AUTH_TOKEN is required for the JKG Hermes provider")

        self._api_url = api_url.rstrip("/")
        self._token = token
        self._session_id = session_id
        self._timeout = float(os.environ.get("JKG_HTTP_TIMEOUT_SECONDS", "10"))

        self._request("GET", "/healthz")

    def system_prompt_block(self) -> str:
        return (
            "JKG memory provider is active. Use jkg_search_memory for durable recall "
            "and jkg_remember_memory for explicit user-approved memory writes."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not query.strip():
            return ""
        result = self._query(query, limit=5)
        rows = result.get("results", [])
        if not rows:
            return ""

        lines = ["Relevant JKG memories:"]
        for row in rows:
            text = row.get("text") or row.get("content") or row.get("value") or str(row)
            score = row.get("score")
            if isinstance(score, int | float):
                lines.append(f"- score={score:.3f}: {text}")
            else:
                lines.append(f"- {text}")
        return "\n".join(lines)

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        session = session_id or self._session_id
        text = f"User: {user_content}\nAssistant: {assistant_content}"
        self._remember(text, source=f"hermes:{session}" if session else "hermes")

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "jkg_search_memory",
                "description": "Search durable JKG memory for relevant profile, factual, episodic, and procedural context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The memory search query."},
                        "limit": {"type": "number", "description": "Maximum number of memories to return."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "jkg_remember_memory",
                "description": "Store an explicit memory in JKG. Use only when the user asks to remember something or the turn contains durable preference/project context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Memory text to store."},
                        "source": {"type": "string", "description": "Optional source label."},
                    },
                    "required": ["text"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> str:
        if tool_name == "jkg_search_memory":
            result = self._query(str(args["query"]), limit=int(args.get("limit", 10)))
            return json.dumps(result, ensure_ascii=False)
        if tool_name == "jkg_remember_memory":
            result = self._remember(str(args["text"]), source=str(args.get("source", "hermes-tool")))
            return json.dumps(result, ensure_ascii=False)
        raise NotImplementedError(f"Provider {self.name} does not handle tool {tool_name}")

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if action not in {"add", "replace"}:
            return
        source = f"hermes:{target}:{action}"
        if metadata and metadata.get("session_id"):
            source = f"{source}:{metadata['session_id']}"
        self._remember(content, source=source)

    def get_config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "api_url",
                "description": "JKG HTTP API base URL.",
                "required": True,
                "default": "http://127.0.0.1:8000",
                "env_var": "JKG_API_URL",
            },
            {
                "key": "auth_token",
                "description": "Bearer token for the JKG HTTP API.",
                "secret": True,
                "required": True,
                "env_var": "JKG_AUTH_TOKEN",
            },
        ]

    def shutdown(self) -> None:
        return None

    def _query(self, text: str, *, limit: int) -> dict[str, Any]:
        return self._request("POST", "/v1/query", json_body={"text": text, "limit": limit})

    def _remember(self, text: str, *, source: str) -> dict[str, Any]:
        return self._request("POST", "/v1/memories", json_body={"text": text, "source": source})

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._api_url or not self._token:
            raise RuntimeError("JKG Hermes provider has not been initialized")

        response = requests.request(
            method,
            f"{self._api_url}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            json=json_body,
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"JKG API request failed: {response.status_code} {response.text}")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("JKG API returned a non-object response")
        return data


def register() -> JKGMemoryProvider:
    return JKGMemoryProvider()
