"""Unit tests for serializers and tool registry (mocked HTTP)."""

from __future__ import annotations

import json
import os

import httpx
import pytest
import respx

os.environ["JIRA_BASE_URL"] = "https://jira.test.local"
os.environ["JIRA_USERNAME"] = "user"
os.environ["JIRA_PASSWORD"] = "pass"
os.environ["JIRA_PROJECT_KEYS"] = "ITSM,DEMO"
os.environ["ASSETS_OBJECT_SCHEMA_ID"] = "8"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
os.environ["OLLAMA_MODEL"] = "qwen2.5:7b"

from jira_agent.assets_client import AssetsClient  # noqa: E402
from jira_agent.config import Settings, get_settings  # noqa: E402
from jira_agent.jira_client import JiraClient  # noqa: E402
from jira_agent.serializers import (  # noqa: E402
    summarize_asset,
    summarize_issues_payload,
    summarize_projects,
)
from jira_agent.tools import ToolRegistry, ollama_tool_schemas  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    get_settings.cache_clear()
    return Settings(
        jira_base_url="https://jira.test.local",
        jira_username="user",
        jira_password="pass",
        jira_project_keys=["ITSM", "DEMO"],
        assets_object_schema_id=8,
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
    )


def test_summarize_projects() -> None:
    raw = [{"key": "ITSM", "name": "ITSM", "id": "1", "projectTypeKey": "software"}]
    data = json.loads(summarize_projects(raw))
    assert data["count"] == 1
    assert data["projects"][0]["key"] == "ITSM"


def test_summarize_issues_payload() -> None:
    payload = {
        "total": 1,
        "startAt": 0,
        "issues": [
            {
                "key": "ITSM-1",
                "fields": {
                    "summary": "Disk full",
                    "status": {"name": "Open"},
                    "issuetype": {"name": "Bug"},
                    "priority": {"name": "High"},
                    "assignee": {"displayName": "Alice"},
                    "project": {"key": "ITSM"},
                    "updated": "2026-07-13T10:00:00.000+0000",
                },
            }
        ],
    }
    data = json.loads(summarize_issues_payload(payload))
    assert data["returned"] == 1
    assert data["issues"][0]["key"] == "ITSM-1"
    assert data["issues"][0]["assignee"] == "Alice"


def test_summarize_asset() -> None:
    obj = {
        "id": 42,
        "label": "srv-01",
        "objectKey": "IT-42",
        "objectType": {"name": "Server", "objectSchemaId": 8},
        "attributes": [
            {
                "objectTypeAttribute": {"name": "Project"},
                "objectAttributeValues": [{"displayValue": "ITSM"}],
            }
        ],
    }
    data = json.loads(summarize_asset(obj))
    assert data["id"] == 42
    assert data["attributes"]["Project"] == "ITSM"


def test_tool_schemas_cover_required_endpoints() -> None:
    names = {t["function"]["name"] for t in ollama_tool_schemas()}
    assert {
        "list_projects",
        "search_issues",
        "get_issue",
        "get_object_schema",
        "search_assets_aql",
        "search_assets_iql",
        "search_assets_by_projects",
        "get_asset",
        "get_asset_tickets",
    } <= names


def test_parse_project_keys_from_env(settings: Settings) -> None:
    assert "ITSM" in settings.jira_project_keys


def test_jira_list_projects(settings: Settings) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get("https://jira.test.local/rest/api/2/project").mock(
            return_value=httpx.Response(
                200,
                json=[{"key": "ITSM", "name": "IT Service", "id": "100"}],
            )
        )
        with JiraClient(settings) as client:
            projects = client.list_projects()
    assert projects[0]["key"] == "ITSM"


def test_jira_search(settings: Settings) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://jira.test.local/rest/api/2/search").mock(
            return_value=httpx.Response(
                200,
                json={"total": 0, "startAt": 0, "issues": []},
            )
        )
        with JiraClient(settings) as client:
            client.search_issues_by_projects(["ITSM"], extra_jql="status = Open")
    assert route.called
    body = json.loads(route.calls[0].request.content.decode())
    assert "project in (ITSM)" in body["jql"]
    assert "status = Open" in body["jql"]


def test_assets_endpoints(settings: Settings) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get("https://jira.test.local/rest/assets/1.0/objectschema/8").mock(
            return_value=httpx.Response(200, json={"id": 8, "name": "IT Assets"})
        )
        router.get("https://jira.test.local/rest/assets/1.0/aql/objects").mock(
            return_value=httpx.Response(
                200,
                json={"totalFilterCount": 1, "objectEntries": [{"id": 1, "label": "a"}]},
            )
        )
        router.post("https://jira.test.local/rest/assets/1.0/object/navlist/iql").mock(
            return_value=httpx.Response(
                200,
                json={"objectEntries": [{"id": 2, "label": "b"}]},
            )
        )
        router.get("https://jira.test.local/rest/assets/1.0/object/99").mock(
            return_value=httpx.Response(200, json={"id": 99, "label": "host"})
        )
        router.get(
            "https://jira.test.local/rest/assets/1.0/objectconnectedtickets/99/tickets"
        ).mock(return_value=httpx.Response(200, json={"tickets": [{"key": "ITSM-9"}]}))

        with AssetsClient(settings) as assets:
            schema = assets.get_object_schema()
            aql = assets.aql_objects("objectSchemaId = 8")
            iql = assets.navlist_iql('Name LIKE "host"')
            obj = assets.get_object(99)
            tickets = assets.get_connected_tickets(99)

    assert schema["name"] == "IT Assets"
    assert aql["objectEntries"][0]["id"] == 1
    assert iql["objectEntries"][0]["id"] == 2
    assert obj["id"] == 99
    assert tickets["tickets"][0]["key"] == "ITSM-9"


def test_tool_registry_search_issues(settings: Settings) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.post("https://jira.test.local/rest/api/2/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 1,
                    "issues": [
                        {
                            "key": "DEMO-1",
                            "fields": {
                                "summary": "Test",
                                "status": {"name": "To Do"},
                                "issuetype": {"name": "Task"},
                                "priority": {"name": "Low"},
                                "assignee": None,
                                "project": {"key": "DEMO"},
                                "updated": "2026-07-01T00:00:00.000+0000",
                            },
                        }
                    ],
                },
            )
        )
        with JiraClient(settings) as jira, AssetsClient(settings) as assets:
            registry = ToolRegistry(settings, jira, assets)
            raw = registry.execute("search_issues", {"project_keys": ["DEMO"]})
    data = json.loads(raw)
    assert data["issues"][0]["key"] == "DEMO-1"
