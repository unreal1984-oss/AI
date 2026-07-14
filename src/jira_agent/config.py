"""Application settings loaded from environment / .env (no pydantic)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"
CLOUD_PROVIDERS = {"openai", "openai_compatible", "cloud", "openrouter", "deepseek"}


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
    # /rest/assets/1.0 (new) or /rest/insight/1.0 (legacy DC). "auto" tries both.
    assets_api_prefix: str = "auto"

    # LLM provider: deepseek (default) | openai | ollama
    llm_provider: str = "deepseek"
    llm_temperature: float = 0.2

    # Ollama (local, optional)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_num_ctx: int = 8192
    ollama_timeout_seconds: float = 180.0

    # OpenAI-compatible cloud (DeepSeek by default)
    openai_api_key: str = ""
    openai_base_url: str = DEEPSEEK_DEFAULT_BASE_URL
    openai_model: str = DEEPSEEK_DEFAULT_MODEL
    openai_org_id: str = ""
    openai_timeout_seconds: float = 120.0
    # Corporate SSL inspection / self-signed MITM proxy
    llm_verify_ssl: bool = True
    llm_ca_bundle: str = ""

    agent_max_tool_rounds: int = 8
    agent_max_issues: int = 50
    agent_max_assets: int = 50
    agent_language: str = "ru"

    # Back-compat alias used by older clients
    @property
    def ollama_temperature(self) -> float:
        return self.llm_temperature

    @property
    def is_cloud(self) -> bool:
        return (self.llm_provider or "").strip().lower() in CLOUD_PROVIDERS

    @property
    def active_model(self) -> str:
        if self.is_cloud:
            return self.openai_model
        return self.ollama_model

    def set_active_model(self, model: str) -> None:
        if self.is_cloud:
            self.openai_model = model
        else:
            self.ollama_model = model

    def llm_http_verify(self) -> bool | str:
        """Value for httpx Client(verify=...)."""
        if self.llm_ca_bundle.strip():
            return self.llm_ca_bundle.strip()
        return self.llm_verify_ssl

    def auth_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # Bearer only when we are NOT also sending Basic for the same request.
        # Core Jira REST accepts Bearer PAT; Assets/Insight on DC often does not.
        if self.jira_pat and not self.jira_username:
            headers["Authorization"] = f"Bearer {self.jira_pat}"
        return headers

    def basic_auth(self) -> tuple[str, str] | None:
        """Auth for Jira core REST."""
        if self.jira_username and self.jira_password:
            return (self.jira_username, self.jira_password)
        if self.jira_username and self.jira_pat:
            # DC: PAT can be used as Basic password
            return (self.jira_username, self.jira_pat)
        if self.jira_pat:
            return None  # Bearer via auth_headers
        if not self.jira_username:
            raise ValueError("Set JIRA_USERNAME+JIRA_PASSWORD (or JIRA_USERNAME+JIRA_PAT)")
        return (self.jira_username, self.jira_password)

    def assets_auth_headers(self) -> dict[str, str]:
        """Assets/Insight: never send Bearer — plugin often returns 401 on Bearer PAT."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def assets_basic_auth(self) -> tuple[str, str]:
        """
        Assets/Insight on Jira DC typically requires HTTP Basic.
        Prefer username+password; else username+PAT-as-password.
        """
        if self.jira_username and self.jira_password:
            return (self.jira_username, self.jira_password)
        if self.jira_username and self.jira_pat:
            return (self.jira_username, self.jira_pat)
        raise ValueError(
            "Assets/Insight needs Basic auth: set JIRA_USERNAME and "
            "JIRA_PASSWORD (or JIRA_USERNAME + JIRA_PAT). "
            "Bearer-only JIRA_PAT without username often gives HTTP 401 on Assets."
        )

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Settings":
        _load_dotenv_files(env_file)

        base_url = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        if not base_url:
            raise ValueError(
                "JIRA_BASE_URL is required. Copy .env.example to .env and fill it in."
            )

        provider = (os.getenv("LLM_PROVIDER") or "deepseek").strip().lower()

        # DeepSeek key preferred; OPENAI_API_KEY kept as generic alias
        api_key = (
            os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )

        default_base = DEEPSEEK_DEFAULT_BASE_URL
        default_model = DEEPSEEK_DEFAULT_MODEL
        if provider == "openrouter":
            default_base = "https://openrouter.ai/api/v1"
            default_model = "deepseek/deepseek-chat"
        elif provider == "openai":
            default_base = "https://api.openai.com/v1"
            default_model = "gpt-4o-mini"
        elif provider in {"deepseek", "cloud"}:
            default_base = DEEPSEEK_DEFAULT_BASE_URL
            default_model = DEEPSEEK_DEFAULT_MODEL

        temperature = _env_float(
            "LLM_TEMPERATURE",
            _env_float("OLLAMA_TEMPERATURE", 0.2),
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
            assets_api_prefix=(os.getenv("ASSETS_API_PREFIX") or "auto").strip().lower(),
            llm_provider=provider,
            llm_temperature=temperature,
            ollama_base_url=(os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip(
                "/"
            ),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            ollama_num_ctx=_env_int("OLLAMA_NUM_CTX", 8192),
            ollama_timeout_seconds=_env_float("OLLAMA_TIMEOUT_SECONDS", 180.0),
            openai_api_key=api_key,
            openai_base_url=(os.getenv("OPENAI_BASE_URL") or default_base).rstrip("/"),
            openai_model=os.getenv("OPENAI_MODEL", default_model),
            openai_org_id=os.getenv("OPENAI_ORG_ID", ""),
            openai_timeout_seconds=_env_float("OPENAI_TIMEOUT_SECONDS", 120.0),
            llm_verify_ssl=_env_bool("LLM_VERIFY_SSL", True),
            llm_ca_bundle=(os.getenv("LLM_CA_BUNDLE") or "").strip(),
            agent_max_tool_rounds=_env_int("AGENT_MAX_TOOL_ROUNDS", 8),
            agent_max_issues=_env_int("AGENT_MAX_ISSUES", 50),
            agent_max_assets=_env_int("AGENT_MAX_ASSETS", 50),
            agent_language=os.getenv("AGENT_LANGUAGE", "ru"),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


def _load_dotenv_files(env_file: str | Path | None) -> None:
    """Load .env from cwd and repo root so CLI works from any launch path."""
    candidates: list[Path] = []
    if env_file:
        candidates.append(Path(env_file))
    candidates.append(Path.cwd() / ".env")
    # src/jira_agent/config.py -> repo root
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / ".env")
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        load_dotenv(resolved, override=False)
