"""OpenAI-compatible cloud LLM client (OpenAI, OpenRouter, DeepSeek, Azure, …)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jira_agent.config import Settings


class OpenAICompatibleError(RuntimeError):
    pass


class OpenAICompatibleClient:
    """
    POST {base}/chat/completions

    Works with any OpenAI-compatible API:
      - OpenAI:      https://api.openai.com/v1
      - OpenRouter:  https://openrouter.ai/api/v1
      - DeepSeek:    https://api.deepseek.com
      - Groq:        https://api.groq.com/openai/v1
      - Together, Fireworks, local vLLM/llama.cpp server, etc.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.openai_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY (or OPENAI_API_KEY) is required for cloud LLM. "
                "Get a key at https://platform.deepseek.com/api_keys"
            )
        base = settings.openai_base_url.rstrip("/")
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        if settings.openai_org_id:
            headers["OpenAI-Organization"] = settings.openai_org_id
        if "openrouter.ai" in base:
            headers.setdefault("HTTP-Referer", "https://github.com/jira-dc-agent")
            headers.setdefault("X-Title", "Jira DC Agent")

        self._client = httpx.Client(
            base_url=base,
            headers=headers,
            timeout=settings.openai_timeout_seconds,
            verify=settings.llm_http_verify(),
        )

    @property
    def provider_name(self) -> str:
        base = self.settings.openai_base_url.lower()
        if "deepseek" in base or self.settings.llm_provider == "deepseek":
            return "deepseek"
        if "openrouter" in base:
            return "openrouter"
        return "openai"

    @property
    def model_name(self) -> str:
        return self.settings.openai_model

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenAICompatibleClient":
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
        response = self._client.get("/models")
        if response.status_code >= 400:
            # Some gateways hide /models — not fatal
            return [self.settings.openai_model]
        data = response.json()
        items = data.get("data") or []
        names = [m.get("id", "") for m in items if m.get("id")]
        return names or [self.settings.openai_model]

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.settings.openai_model,
            "messages": [_to_openai_message(m) for m in messages],
            "temperature": self.settings.llm_temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = self._client.post("/chat/completions", json=payload)
        if response.status_code >= 400:
            raise OpenAICompatibleError(
                _format_api_error(response.status_code, response.text, self.provider_name)
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise OpenAICompatibleError(f"Unexpected OpenAI response: {data!r}")
        message = choices[0].get("message") or {}
        return _normalize_openai_assistant(message)


def _format_api_error(status_code: int, body: str, provider: str) -> str:
    text = (body or "")[:1500]
    lower = text.lower()
    if status_code == 402 or "insufficient balance" in lower:
        return (
            f"{provider}: недостаточно средств на балансе API (HTTP 402). "
            "Пополните счёт: https://platform.deepseek.com/usage "
            "или проверьте биллинг в кабинете провайдера."
        )
    if status_code == 401:
        return (
            f"{provider}: неверный API-ключ (HTTP 401). "
            "Проверьте DEEPSEEK_API_KEY в .env "
            "(https://platform.deepseek.com/api_keys)."
        )
    if status_code == 429:
        return f"{provider}: лимит запросов (HTTP 429). Подождите и повторите."
    return f"{provider} chat failed: {status_code} {text}"


def _to_openai_message(message: dict[str, Any]) -> dict[str, Any]:
    role = message.get("role")
    if role == "tool":
        out: dict[str, Any] = {
            "role": "tool",
            "content": message.get("content") or "",
            "tool_call_id": message.get("tool_call_id")
            or message.get("id")
            or "tool_call",
        }
        name = message.get("name") or message.get("tool_name")
        if name:
            out["name"] = name
        return out

    out = {
        "role": role or "user",
        "content": message.get("content") if message.get("content") is not None else "",
    }
    tool_calls = message.get("tool_calls")
    if tool_calls:
        converted = []
        for call in tool_calls:
            fn = call.get("function") or {}
            args = fn.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args or {}, ensure_ascii=False)
            converted.append(
                {
                    "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "type": call.get("type") or "function",
                    "function": {
                        "name": fn.get("name") or call.get("name") or "",
                        "arguments": args,
                    },
                }
            )
        out["tool_calls"] = converted
        # OpenAI rejects null content with tool_calls on some models
        if out["content"] is None:
            out["content"] = ""
    return out


def _normalize_openai_assistant(message: dict[str, Any]) -> dict[str, Any]:
    tool_calls = message.get("tool_calls") or []
    normalized_calls = []
    for call in tool_calls:
        fn = call.get("function") or {}
        args = fn.get("arguments")
        # Keep arguments as string or dict — ToolRegistry accepts both
        normalized_calls.append(
            {
                "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": fn.get("name") or "",
                    "arguments": args if args is not None else {},
                },
            }
        )
    result: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content") or "",
    }
    if normalized_calls:
        result["tool_calls"] = normalized_calls
    return result
