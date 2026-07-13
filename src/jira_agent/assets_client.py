"""HTTP client for Jira Insight / Assets REST API 1.0."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jira_agent.config import Settings
from jira_agent.jira_client import JiraAPIError


class AssetsClient:
    """Wraps /rest/assets/1.0 endpoints used by the agent."""

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

    def __enter__(self) -> "AssetsClient":
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

    def get_object_schema(self, schema_id: int | None = None) -> dict[str, Any]:
        """GET /rest/assets/1.0/objectschema/{id}"""
        sid = schema_id if schema_id is not None else self.settings.assets_object_schema_id
        return self._request("GET", f"/rest/assets/1.0/objectschema/{sid}")

    def aql_objects(
        self,
        ql_query: str,
        *,
        start_at: int = 0,
        max_results: int | None = None,
        include_attributes: bool = True,
    ) -> dict[str, Any]:
        """GET /rest/assets/1.0/aql/objects"""
        limit = max_results if max_results is not None else self.settings.agent_max_assets
        params: dict[str, Any] = {
            "qlQuery": ql_query,
            "startAt": start_at,
            "maxResults": limit,
            "includeAttributes": str(include_attributes).lower(),
        }
        return self._request("GET", "/rest/assets/1.0/aql/objects", params=params)

    def navlist_iql(
        self,
        iql: str,
        *,
        object_type_id: int | None = None,
        object_schema_id: int | None = None,
        page: int = 1,
        results_per_page: int | None = None,
        include_attributes: bool = True,
    ) -> dict[str, Any]:
        """POST /rest/assets/1.0/object/navlist/iql"""
        limit = (
            results_per_page
            if results_per_page is not None
            else self.settings.agent_max_assets
        )
        payload: dict[str, Any] = {
            "iql": iql,
            "page": page,
            "resultsPerPage": limit,
            "includeAttributes": include_attributes,
            "objectSchemaId": object_schema_id
            if object_schema_id is not None
            else self.settings.assets_object_schema_id,
        }
        if object_type_id is not None:
            payload["objectTypeId"] = object_type_id
        return self._request(
            "POST",
            "/rest/assets/1.0/object/navlist/iql",
            json=payload,
        )

    def get_object(self, object_id: int | str) -> dict[str, Any]:
        """GET /rest/assets/1.0/object/{id}"""
        return self._request("GET", f"/rest/assets/1.0/object/{object_id}")

    def get_connected_tickets(self, object_id: int | str) -> dict[str, Any]:
        """GET /rest/assets/1.0/objectconnectedtickets/{id}/tickets"""
        return self._request(
            "GET",
            f"/rest/assets/1.0/objectconnectedtickets/{object_id}/tickets",
        )

    def search_assets_for_projects(
        self,
        project_keys: list[str],
        *,
        extra_aql: str = "",
        max_results: int | None = None,
    ) -> dict[str, Any]:
        """
        Heuristic AQL scoped to configured schema.

        Many DC setups store project key as an attribute named Project / Project Key.
        We OR common attribute names and optionally AND user filter.
        """
        schema_id = self.settings.assets_object_schema_id
        clauses: list[str] = [f"objectSchemaId = {schema_id}"]
        if project_keys:
            key_list = ", ".join(f'"{k}"' for k in project_keys)
            project_filter = (
                f'(("Project" IN ({key_list})) OR '
                f'("Project Key" IN ({key_list})) OR '
                f'("Jira Project" IN ({key_list})))'
            )
            clauses.append(project_filter)
        if extra_aql.strip():
            clauses.append(f"({extra_aql.strip()})")
        ql = " AND ".join(clauses)
        return self.aql_objects(ql, max_results=max_results)
