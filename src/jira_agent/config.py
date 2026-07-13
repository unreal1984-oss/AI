"""Application settings loaded from environment / .env (no pydantic)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _parse_project_keys(value: str | None) -> List[str]:
    if not value or not value.strip():
        return []
    return [part.strip().upper() for part in value.split(",") if part.strip()]


@dataclass
class Settings:
    jira_base_url: str
    jira_username: str = ""
    jira_password: str = ""
    jira_pat: str = ""
    jira_verify_ssl: bool = True
    jira_timeout_seconds: float = 60.0
    jira_project_keys: List[str] = field(default_factory=list)

    assets_object_schema_id: int = 8

    # LLM provider: ollama | openai (OpenAI-compatible cloud)
    llm_provider: str = "ollama"

    # Ollama (local)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_temperature: float = 0.2
    ollama_num_ctx: int = 8192
    ollama_timeout_seconds: float = 180.0

    # OpenAI-compatible cloud
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_org_id: str = ""
    openai_timeout_seconds: float = 120.0

    agent_max_tool_rounds: int = 8
    agent_max_issues: int = 50
    agent_max_assets: int = 50
    agent_language: str = "ru"

    @property
    def active_model(self) -> str:
        provider = (self.llm_provider or "ollama").strip().lower()
        if provider in {"openai", "openai_compatible", "cloud", "openrouter", "deepseek"}:
            return self.openai_model
        return self.ollama_model

    def set_active_model(self, model: str) -> None:
        provider = (self.llm_provider or "ollama").strip().lower()
        if provider in {"openai", "openai_compatible", "cloud", "openrouter", "deepseek"}:
            self.openai_model = model
        else:
            self.ollama_model = model

    def auth_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.jira_pat:
            headers["Authorization"] = f"Bearer {self.jira_pat}"
        return headers

    def basic_auth(self) -> tuple[str, str] | None:
        if self.jira_pat:
            return None
        if not self.jira_username:
            raise ValueError("Set JIRA_USERNAME+JIRA_PASSWORD or JIRA_PAT")
        return (self.jira_username, self.jira_password)

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Settings":
        if env_file:
            load_dotenv(env_file, override=False)

        base_url = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        if not base_url:
            raise ValueError(
                "JIRA_BASE_URL is required. Copy .env.example to .env and fill it in."
            )

        return cls(
            jira_base_url=base_url,
            jira_username=os.getenv("JIRA_USERNAME", ""),
            jira_password=os.getenv("JIRA_PASSWORD", ""),
            jira_pat=os.getenv("JIRA_PAT", ""),
            jira_verify_ssl=_env_bool("JIRA_VERIFY_SSL", True),
            jira_timeout_seconds=_env_float("JIRA_TIMEOUT_SECONDS", 60.0),
            jira_project_keys=_parse_project_keys(os.getenv("JIRA_PROJECT_KEYS")),
            assets_object_schema_id=_env_int("ASSETS_OBJECT_SCHEMA_ID", 8),
            llm_provider=(os.getenv("LLM_PROVIDER") or "ollama").strip().lower(),
            ollama_base_url=(os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip(
                "/"
            ),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            ollama_temperature=_env_float("OLLAMA_TEMPERATURE", 0.2),
            ollama_num_ctx=_env_int("OLLAMA_NUM_CTX", 8192),
            ollama_timeout_seconds=_env_float("OLLAMA_TIMEOUT_SECONDS", 180.0),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=(
                os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_org_id=os.getenv("OPENAI_ORG_ID", ""),
            openai_timeout_seconds=_env_float("OPENAI_TIMEOUT_SECONDS", 120.0),
            agent_max_tool_rounds=_env_int("AGENT_MAX_TOOL_ROUNDS", 8),
            agent_max_issues=_env_int("AGENT_MAX_ISSUES", 50),
            agent_max_assets=_env_int("AGENT_MAX_ASSETS", 50),
            agent_language=os.getenv("AGENT_LANGUAGE", "ru"),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
