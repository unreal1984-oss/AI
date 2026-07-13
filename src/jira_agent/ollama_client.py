"""Ollama HTTP client (no extra SDK — only httpx)."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jira_agent.config import Settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(
            base_url=settings.ollama_base_url.rstrip("/"),
            timeout=settings.ollama_timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=3),
        reraise=True,
    )
    def list_models(self) -> list[str]:
        response = self._client.get("/api/tags")
        if response.status_code >= 400:
            raise OllamaError(f"Ollama tags failed: {response.status_code} {response.text}")
        models = response.json().get("models") or []
        return [m.get("name", "") for m in models if m.get("name")]

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """
        POST /api/chat

        Returns the assistant message dict:
          {role, content, tool_calls?}
        """
        payload: dict[str, Any] = {
            "model": model or self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "num_ctx": self.settings.ollama_num_ctx,
            },
        }
        if tools:
            payload["tools"] = tools

        response = self._client.post("/api/chat", json=payload)
        if response.status_code >= 400:
            raise OllamaError(
                f"Ollama chat failed: {response.status_code} {response.text[:1500]}"
            )
        data = response.json()
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaError(f"Unexpected Ollama response: {data!r}")
        return message
