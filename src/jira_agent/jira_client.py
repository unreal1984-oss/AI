"""HTTP client for Jira Data Center REST API v2."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jira_agent.config import Settings


class JiraAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, body: str = "") -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Jira API {status_code}: {message}")


class JiraClient:
    """Wraps /rest/api/2 endpoints used by the agent."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(
            base_url=settings.jira_base_url,
            headers=settings.auth_headers(),
            auth=settings.basic_auth(),
            verify=settings.jira_verify_ssl,
            timeout=settings.jira_timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        response = self._client.request(method, path, params=params, json=json)
        if response.status_code >= 400:
            raise JiraAPIError(
                response.status_code,
                response.reason_phrase or "error",
                response.text[:2000],
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def list_projects(self) -> list[dict[str, Any]]:
        """GET /rest/api/2/project"""
        data = self._request("GET", "/rest/api/2/project")
        return list(data or [])

    def myself(self) -> dict[str, Any]:
        """GET /rest/api/2/myself — who am I authenticated as."""
        return self._request("GET", "/rest/api/2/myself")

    def search_issues(
        self,
        jql: str,
        *,
        start_at: int = 0,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /rest/api/2/search"""
        payload: dict[str, Any] = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": fields
            or [
                "summary",
                "status",
                "assignee",
                "reporter",
                "priority",
                "issuetype",
                "created",
                "updated",
                "project",
                "labels",
                "components",
                "description",
            ],
        }
        return self._request("POST", "/rest/api/2/search", json=payload)

    def search_issues_by_projects(
        self,
        project_keys: list[str],
        *,
        extra_jql: str = "",
        max_results: int | None = None,
    ) -> dict[str, Any]:
        if not project_keys:
            raise ValueError("project_keys must not be empty")
        keys = ", ".join(project_keys)
        jql = f"project in ({keys})"
        if extra_jql.strip():
            jql = f"{jql} AND ({extra_jql.strip()})"
        jql = f"{jql} ORDER BY updated DESC"
        limit = max_results if max_results is not None else self.settings.agent_max_issues
        return self.search_issues(jql, max_results=limit)

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/rest/api/2/issue/{issue_key}",
            params={
                "fields": "summary,status,assignee,reporter,priority,issuetype,"
                "created,updated,project,labels,components,description,comment"
            },
        )
