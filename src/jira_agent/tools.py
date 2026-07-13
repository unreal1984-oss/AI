"""Tool definitions and executors for the ReAct / native-tools agent loop."""

from __future__ import annotations

import json
from typing import Any, Callable

from jira_agent.assets_client import AssetsClient
from jira_agent.config import Settings
from jira_agent.jira_client import JiraClient
from jira_agent.serializers import (
    summarize_asset,
    summarize_assets_payload,
    summarize_issue,
    summarize_issues_payload,
    summarize_projects,
    summarize_schema,
    summarize_tickets,
)


ToolHandler = Callable[[dict[str, Any]], str]


def ollama_tool_schemas() -> list[dict[str, Any]]:
    """OpenAI-compatible tool schemas accepted by Ollama."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_projects",
                "description": (
                    "List Jira projects available on the Data Center instance "
                    "(GET /rest/api/2/project). Use to discover project keys."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_issues",
                "description": (
                    "Search Jira issues with JQL via POST /rest/api/2/search. "
                    "If project_keys is given, automatically scopes JQL to those projects."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Project keys, e.g. [\"ITSM\", \"PROJ\"]",
                        },
                        "jql": {
                            "type": "string",
                            "description": (
                                "Extra JQL fragment (without project clause), "
                                'e.g. status != Done AND assignee = currentUser()'
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max issues to return (default from settings)",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_issue",
                "description": "Get a single Jira issue by key (e.g. ITSM-123).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "issue_key": {
                            "type": "string",
                            "description": "Issue key like PROJ-42",
                        }
                    },
                    "required": ["issue_key"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_object_schema",
                "description": (
                    "Get Insight/Assets object schema metadata "
                    "(GET /rest/assets/1.0/objectschema/{id}). Default schema id from config."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "schema_id": {
                            "type": "integer",
                            "description": "Object schema id (default ASSETS_OBJECT_SCHEMA_ID)",
                        }
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_assets_aql",
                "description": (
                    "Search Insight/Assets objects with AQL "
                    "(GET /rest/assets/1.0/aql/objects). "
                    "Prefer this for modern Assets AQL."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ql_query": {
                            "type": "string",
                            "description": 'AQL query, e.g. objectSchemaId = 8 AND Name LIKE "server"',
                        },
                        "max_results": {"type": "integer"},
                    },
                    "required": ["ql_query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_assets_iql",
                "description": (
                    "Search Insight objects with IQL via navlist "
                    "(POST /rest/assets/1.0/object/navlist/iql)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "iql": {
                            "type": "string",
                            "description": "IQL query string",
                        },
                        "object_type_id": {"type": "integer"},
                        "object_schema_id": {"type": "integer"},
                        "results_per_page": {"type": "integer"},
                    },
                    "required": ["iql"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_assets_by_projects",
                "description": (
                    "Search assets related to given Jira project keys inside the configured "
                    "object schema (heuristic AQL on Project / Project Key attributes)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "extra_aql": {
                            "type": "string",
                            "description": "Additional AQL AND fragment",
                        },
                        "max_results": {"type": "integer"},
                    },
                    "required": ["project_keys"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_asset",
                "description": "Get a single Insight/Assets object by id (GET /rest/assets/1.0/object/{id}).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "object_id": {
                            "type": "string",
                            "description": "Numeric object id as string or int",
                        }
                    },
                    "required": ["object_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_asset_tickets",
                "description": (
                    "List Jira tickets connected to an Insight/Assets object "
                    "(GET /rest/assets/1.0/objectconnectedtickets/{id}/tickets)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "object_id": {"type": "string"},
                    },
                    "required": ["object_id"],
                    "additionalProperties": False,
                },
            },
        },
    ]


class ToolRegistry:
    def __init__(
        self,
        settings: Settings,
        jira: JiraClient,
        assets: AssetsClient,
        default_project_keys: list[str] | None = None,
    ) -> None:
        self.settings = settings
        self.jira = jira
        self.assets = assets
        self.default_project_keys = default_project_keys or list(settings.jira_project_keys)
        self._handlers: dict[str, ToolHandler] = {
            "list_projects": self._list_projects,
            "search_issues": self._search_issues,
            "get_issue": self._get_issue,
            "get_object_schema": self._get_object_schema,
            "search_assets_aql": self._search_assets_aql,
            "search_assets_iql": self._search_assets_iql,
            "search_assets_by_projects": self._search_assets_by_projects,
            "get_asset": self._get_asset,
            "get_asset_tickets": self._get_asset_tickets,
        }

    def names(self) -> list[str]:
        return sorted(self._handlers)

    def execute(self, name: str, arguments: dict[str, Any] | str | None) -> str:
        if name not in self._handlers:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
        args = self._normalize_args(arguments)
        try:
            return self._handlers[name](args)
        except Exception as exc:  # noqa: BLE001 — surface tool errors to the LLM
            return json.dumps(
                {"error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            )

    @staticmethod
    def _normalize_args(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
        if arguments is None:
            return {}
        if isinstance(arguments, str):
            text = arguments.strip()
            if not text:
                return {}
            return json.loads(text)
        return dict(arguments)

    def _resolve_projects(self, project_keys: list[str] | None) -> list[str]:
        keys = [k.strip().upper() for k in (project_keys or []) if str(k).strip()]
        return keys or self.default_project_keys

    def _list_projects(self, _: dict[str, Any]) -> str:
        projects = self.jira.list_projects()
        return summarize_projects(projects)

    def _search_issues(self, args: dict[str, Any]) -> str:
        keys = self._resolve_projects(args.get("project_keys"))
        jql = str(args.get("jql") or "")
        max_results = args.get("max_results")
        if keys:
            data = self.jira.search_issues_by_projects(
                keys,
                extra_jql=jql,
                max_results=int(max_results) if max_results is not None else None,
            )
        else:
            if not jql.strip():
                return json.dumps(
                    {"error": "Provide project_keys or jql"},
                    ensure_ascii=False,
                )
            data = self.jira.search_issues(
                jql,
                max_results=int(max_results)
                if max_results is not None
                else self.settings.agent_max_issues,
            )
        return summarize_issues_payload(data)

    def _get_issue(self, args: dict[str, Any]) -> str:
        issue = self.jira.get_issue(str(args["issue_key"]))
        return summarize_issue(issue)

    def _get_object_schema(self, args: dict[str, Any]) -> str:
        schema_id = args.get("schema_id")
        data = self.assets.get_object_schema(
            int(schema_id) if schema_id is not None else None
        )
        return summarize_schema(data)

    def _search_assets_aql(self, args: dict[str, Any]) -> str:
        max_results = args.get("max_results")
        data = self.assets.aql_objects(
            str(args["ql_query"]),
            max_results=int(max_results) if max_results is not None else None,
        )
        return summarize_assets_payload(data)

    def _search_assets_iql(self, args: dict[str, Any]) -> str:
        data = self.assets.navlist_iql(
            str(args["iql"]),
            object_type_id=int(args["object_type_id"])
            if args.get("object_type_id") is not None
            else None,
            object_schema_id=int(args["object_schema_id"])
            if args.get("object_schema_id") is not None
            else None,
            results_per_page=int(args["results_per_page"])
            if args.get("results_per_page") is not None
            else None,
        )
        return summarize_assets_payload(data)

    def _search_assets_by_projects(self, args: dict[str, Any]) -> str:
        keys = self._resolve_projects(args.get("project_keys"))
        if not keys:
            return json.dumps(
                {"error": "project_keys required (or set JIRA_PROJECT_KEYS)"},
                ensure_ascii=False,
            )
        max_results = args.get("max_results")
        data = self.assets.search_assets_for_projects(
            keys,
            extra_aql=str(args.get("extra_aql") or ""),
            max_results=int(max_results) if max_results is not None else None,
        )
        return summarize_assets_payload(data)

    def _get_asset(self, args: dict[str, Any]) -> str:
        obj = self.assets.get_object(args["object_id"])
        return summarize_asset(obj)

    def _get_asset_tickets(self, args: dict[str, Any]) -> str:
        data = self.assets.get_connected_tickets(args["object_id"])
        return summarize_tickets(data)
