"""LLM provider abstraction (Ollama local + OpenAI-compatible cloud)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from jira_agent.config import Settings
from jira_agent.ollama_client import OllamaClient
from jira_agent.openai_client import OpenAICompatibleClient


@runtime_checkable
class LLMClient(Protocol):
    def close(self) -> None: ...

    def __enter__(self) -> "LLMClient": ...

    def __exit__(self, *args: object) -> None: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def list_models(self) -> list[str]: ...

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Return normalized assistant message: role/content/tool_calls?."""
        ...


def create_llm_client(settings: Settings) -> LLMClient:
    provider = (settings.llm_provider or "ollama").strip().lower()
    if provider in {"ollama", "local"}:
        return OllamaClient(settings)
    if provider in {"openai", "openai_compatible", "cloud", "openrouter", "deepseek"}:
        return OpenAICompatibleClient(settings)
    raise ValueError(
        f"Unknown LLM_PROVIDER={settings.llm_provider!r}. "
        "Use: ollama | openai (OpenAI-compatible cloud)."
    )
