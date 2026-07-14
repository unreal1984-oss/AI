"""Agent loop with mocked Ollama / OpenAI tool calling."""

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
from jira_agent.llm import create_llm_client  # noqa: E402
from jira_agent.tools import ToolRegistry  # noqa: E402


@pytest.fixture
def settings_ollama() -> Settings:
    return Settings(
        jira_base_url="https://jira.test.local",
        jira_username="user",
        jira_password="pass",
        jira_project_keys=["ITSM"],
        assets_object_schema_id=8,
        llm_provider="ollama",
        ollama_base_url="http://ollama.test.local",
        ollama_model="qwen2.5:7b",
        agent_max_tool_rounds=4,
    )


@pytest.fixture
def settings_openai() -> Settings:
    return Settings(
        jira_base_url="https://jira.test.local",
        jira_username="user",
        jira_password="pass",
        jira_project_keys=["ITSM"],
        assets_object_schema_id=8,
        llm_provider="openai",
        openai_api_key="sk-test",
        openai_base_url="https://api.openai.test/v1",
        openai_model="gpt-4o-mini",
        agent_max_tool_rounds=4,
    )


def test_agent_tool_then_answer_ollama(settings_ollama: Settings) -> None:
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
            JiraClient(settings_ollama) as jira,
            AssetsClient(settings_ollama) as assets,
            create_llm_client(settings_ollama) as llm,
        ):
            tools = ToolRegistry(settings_ollama, jira, assets)
            agent = JiraAgent(settings_ollama, llm, tools, project_keys=["ITSM"])
            result = agent.ask("Какие проекты есть?")

    assert "ITSM" in result.answer
    assert result.tool_calls == 1
    assert len(chat_calls) == 2
    roles = [m.get("role") for m in chat_calls[1]["messages"]]
    assert "tool" in roles


def test_agent_tool_then_answer_openai(settings_openai: Settings) -> None:
    chat_calls: list[dict[str, Any]] = []

    def openai_side_effect(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        chat_calls.append(payload)
        if len(chat_calls) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_abc",
                                        "type": "function",
                                        "function": {
                                            "name": "list_projects",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Найден проект ITSM.",
                        }
                    }
                ]
            },
        )

    with respx.mock(assert_all_called=False) as router:
        router.get("https://jira.test.local/rest/api/2/project").mock(
            return_value=httpx.Response(
                200,
                json=[{"key": "ITSM", "name": "ITSM", "projectTypeKey": "service_desk"}],
            )
        )
        router.post("https://api.openai.test/v1/chat/completions").mock(
            side_effect=openai_side_effect
        )

        with (
            JiraClient(settings_openai) as jira,
            AssetsClient(settings_openai) as assets,
            create_llm_client(settings_openai) as llm,
        ):
            tools = ToolRegistry(settings_openai, jira, assets)
            agent = JiraAgent(settings_openai, llm, tools, project_keys=["ITSM"])
            result = agent.ask("Какие проекты есть?")

    assert "ITSM" in result.answer
    assert result.tool_calls == 1
    assert len(chat_calls) == 2
    second_msgs = chat_calls[1]["messages"]
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert tool_msgs
    assert tool_msgs[0]["tool_call_id"] == "call_abc"
