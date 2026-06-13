"""DeepSeek LLM provider."""

from __future__ import annotations

import os

import requests


class DeepSeekLLMProvider:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        api_base: str = "https://api.deepseek.com",
        timeout: int = 120,
    ) -> None:
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required for DeepSeek LLM calls")
        self.api_key = api_key
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "DeepSeekLLMProvider":
        return cls(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            model=os.environ.get("CLARK_LLM_MODEL", "deepseek-v4-flash"),
            api_base=os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        )

    def complete(self, prompt: str, system: str) -> str:
        response = requests.post(
            f"{self.api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        except Exception as exc:
            body = (response.text or "")[:300]
            raise RuntimeError(f"DeepSeek LLM request failed: {exc}; body={body}") from exc

