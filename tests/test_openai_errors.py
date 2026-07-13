"""API error message mapping."""

from __future__ import annotations

from jira_agent.openai_client import _format_api_error


def test_format_api_error_insufficient_balance() -> None:
    msg = _format_api_error(
        402,
        '{"error":{"message":"Insufficient Balance"}}',
        "deepseek",
    )
    assert "недостаточно средств" in msg
    assert "platform.deepseek.com" in msg
