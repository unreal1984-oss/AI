"""Agent loop with mocked Ollama tool calling."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest
import respx

os.environ["JIRA_BASE_URL"] = "https://jira.test.local"
os.environ["JIRA_USERNAME"] = "user"
os.environ["JIRA_PASSWORD"] = "pass"
os.environ["OLLAMA_MODEL"] = "qwen2.5:7b"

from jira_agent.agent import JiraAgent  # noqa: E402
from jira_agent.assets_client import AssetsClient  # noqa: E402
from jira_agent.config import Settings  # noqa: E402
from jira_agent.jira_client import JiraClient  # noqa: E402
from jira_agent.ollama_client import OllamaClient  # noqa: E402
from jira_agent.tools import ToolRegistry  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(
        jira_base_url="https://jira.test.local",
        jira_username="user",
        jira_password="pass",
        jira_project_keys=["ITSM"],
        assets_object_schema_id=8,
        ollama_base_url="http://ollama.test.local",
        ollama_model="qwen2.5:7b",
        agent_max_tool_rounds=4,
    )


def test_agent_tool_then_answer(settings: Settings) -> None:
    chat_calls: list[dict[str, Any]] = []

    def ollama_side_effect(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        chat_calls.append(payload)
        if len(chat_calls) == 1:
            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "list_projects",
                                    "arguments": {},
                                }
                            }
                        ],
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "Найден проект ITSM.",
                }
            },
        )

    with respx.mock(assert_all_called=False) as router:
        router.get("https://jira.test.local/rest/api/2/project").mock(
            return_value=httpx.Response(
                200,
                json=[{"key": "ITSM", "name": "ITSM", "projectTypeKey": "service_desk"}],
            )
        )
        router.post("http://ollama.test.local/api/chat").mock(side_effect=ollama_side_effect)

        with (
            JiraClient(settings) as jira,
            AssetsClient(settings) as assets,
            OllamaClient(settings) as ollama,
        ):
            tools = ToolRegistry(settings, jira, assets)
            agent = JiraAgent(settings, ollama, tools, project_keys=["ITSM"])
            result = agent.ask("Какие проекты есть?")

    assert "ITSM" in result.answer
    assert result.tool_calls == 1
    assert len(chat_calls) == 2
    roles = [m.get("role") for m in chat_calls[1]["messages"]]
    assert "tool" in roles
