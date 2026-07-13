"""Assets auth helpers for Jira DC Insight/Assets."""

from __future__ import annotations

import pytest

from jira_agent.config import Settings


def test_assets_basic_auth_prefers_password() -> None:
    settings = Settings(
        jira_base_url="https://jira.test.local",
        jira_username="user",
        jira_password="secret",
        jira_pat="pat-token",
    )
    assert settings.assets_basic_auth() == ("user", "secret")


def test_assets_basic_auth_uses_pat_as_password() -> None:
    settings = Settings(
        jira_base_url="https://jira.test.local",
        jira_username="user",
        jira_pat="pat-token",
    )
    assert settings.assets_basic_auth() == ("user", "pat-token")


def test_assets_basic_auth_requires_username() -> None:
    settings = Settings(
        jira_base_url="https://jira.test.local",
        jira_pat="pat-only",
    )
    with pytest.raises(ValueError, match="Basic auth"):
        settings.assets_basic_auth()
