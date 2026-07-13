"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Jira DC
    jira_base_url: str = Field(..., description="Base URL without trailing slash")
    jira_username: str = ""
    jira_password: str = ""
    jira_pat: str = ""
    jira_verify_ssl: bool = True
    jira_timeout_seconds: float = 60.0
    # Comma-separated in .env (NoDecode avoids JSON-only list parsing)
    jira_project_keys: Annotated[List[str], NoDecode] = Field(default_factory=list)

    # Assets / Insight
    assets_object_schema_id: int = 8

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_temperature: float = 0.2
    ollama_num_ctx: int = 8192
    ollama_timeout_seconds: float = 180.0

    # Agent
    agent_max_tool_rounds: int = 8
    agent_max_issues: int = 50
    agent_max_assets: int = 50
    agent_language: str = "ru"

    @field_validator("jira_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("jira_project_keys", mode="before")
    @classmethod
    def parse_project_keys(cls, value: object) -> List[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip().upper() for item in value if str(item).strip()]
        return [
            part.strip().upper()
            for part in str(value).split(",")
            if part.strip()
        ]

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
