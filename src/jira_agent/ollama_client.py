"""Ollama HTTP client (no extra SDK — only httpx)."""

from __future__ import annotations

import uuid
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

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self.settings.ollama_model

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

        Returns normalized assistant message:
          {role, content, tool_calls?}
        """
        payload: dict[str, Any] = {
            "model": model or self.settings.ollama_model,
            "messages": [_to_ollama_message(m) for m in messages],
            "stream": False,
            "options": {
                "temperature": self.settings.llm_temperature,
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
        return _normalize_ollama_assistant(message)


def _to_ollama_message(message: dict[str, Any]) -> dict[str, Any]:
    role = message.get("role")
    if role == "tool":
        out: dict[str, Any] = {
            "role": "tool",
            "content": message.get("content") or "",
        }
        name = message.get("tool_name") or message.get("name")
        if name:
            out["tool_name"] = name
        return out
    # Pass through assistant/user/system (including tool_calls)
    return dict(message)


def _normalize_ollama_assistant(message: dict[str, Any]) -> dict[str, Any]:
    tool_calls = message.get("tool_calls") or []
    normalized = []
    for call in tool_calls:
        fn = call.get("function") or {}
        normalized.append(
            {
                "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": fn.get("name") or call.get("name") or "",
                    "arguments": fn.get("arguments")
                    if fn.get("arguments") is not None
                    else {},
                },
            }
        )
    result: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content") or "",
    }
    if normalized:
        result["tool_calls"] = normalized
    return result
