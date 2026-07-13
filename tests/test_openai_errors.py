"""API error message mapping."""

from __future__ import annotations

from jira_agent.config import Settings
from jira_agent.openai_client import _format_api_error, _format_transport_error


def test_format_api_error_insufficient_balance() -> None:
    msg = _format_api_error(
        402,
        '{"error":{"message":"Insufficient Balance"}}',
        "deepseek",
    )
    assert "недостаточно средств" in msg
    assert "platform.deepseek.com" in msg


def test_format_transport_ssl_hint() -> None:
    settings = Settings(jira_base_url="https://jira.test", llm_verify_ssl=True)
    msg = _format_transport_error(
        Exception("[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate"),
        settings,
    )
    assert "LLM_VERIFY_SSL=false" in msg
    assert "--insecure" in msg
