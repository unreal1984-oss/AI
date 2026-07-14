"""Settings defaults for DeepSeek Cloud."""

from __future__ import annotations

import pytest

from jira_agent.config import Settings, get_settings


def test_settings_default_to_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.test.local")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    settings = Settings.from_env(env_file=None)
    assert settings.llm_provider == "deepseek"
    assert settings.openai_base_url == "https://api.deepseek.com"
    assert settings.openai_model == "deepseek-chat"
    assert settings.openai_api_key == "sk-deepseek"
    assert settings.is_cloud is True
