"""SSL verify settings for corporate proxies."""

from __future__ import annotations

from jira_agent.config import Settings


def test_llm_http_verify_false() -> None:
    settings = Settings(
        jira_base_url="https://jira.test.local",
        llm_verify_ssl=False,
    )
    assert settings.llm_http_verify() is False


def test_llm_http_verify_ca_bundle() -> None:
    settings = Settings(
        jira_base_url="https://jira.test.local",
        llm_verify_ssl=True,
        llm_ca_bundle=r"C:\certs\corp.pem",
    )
    assert settings.llm_http_verify() == r"C:\certs\corp.pem"
