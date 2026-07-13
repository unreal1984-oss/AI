"""HTTP client for Jira Insight / Assets REST API 1.0."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jira_agent.config import Settings
from jira_agent.jira_client import JiraAPIError

# New name vs legacy Insight on many Data Center installs
_PREFIX_CANDIDATES = ("/rest/assets/1.0", "/rest/insight/1.0")


class AssetsClient:
    """Wraps /rest/assets/1.0 (or legacy /rest/insight/1.0) endpoints."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._prefix = self._resolve_prefix(settings.assets_api_prefix)
        self._client = httpx.Client(
            base_url=settings.jira_base_url,
            headers=settings.assets_auth_headers(),
            auth=settings.assets_basic_auth(),
            verify=settings.jira_verify_ssl,
            timeout=settings.jira_timeout_seconds,
        )

    @staticmethod
    def _resolve_prefix(raw: str) -> str:
        value = (raw or "auto").strip().lower()
        if value in {"auto", ""}:
            return "auto"
        if value in {"assets", "asset"}:
            return "/rest/assets/1.0"
        if value in {"insight", "insights"}:
            return "/rest/insight/1.0"
        if value.startswith("/rest/"):
            return value.rstrip("/")
        raise ValueError(
            f"ASSETS_API_PREFIX={raw!r} invalid. Use auto | assets | insight | /rest/..."
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AssetsClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _prefixes(self) -> tuple[str, ...]:
        if self._prefix == "auto":
            return _PREFIX_CANDIDATES
        return (self._prefix,)

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    def _request_once(
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

    def _request(
        self,
        method: str,
        relative: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """relative like '/objectschema/8' — tried under assets then insight if auto."""
        errors: list[JiraAPIError] = []
        for prefix in self._prefixes():
            path = f"{prefix}{relative}"
            try:
                data = self._request_once(method, path, params=params, json=json)
                # Remember working prefix for subsequent calls in this process
                if self._prefix == "auto":
                    self._prefix = prefix
                return data
            except JiraAPIError as exc:
                errors.append(exc)
                # 404 on wrong product path → try next; 401/403 still try alternate path
                if exc.status_code not in {401, 403, 404}:
                    raise
        last = errors[-1]
        if last.status_code == 401:
            raise JiraAPIError(
                401,
                (
                    "Unauthorized on Assets/Insight. "
                    "Use Basic auth: JIRA_USERNAME + JIRA_PASSWORD "
                    "(or JIRA_USERNAME + JIRA_PAT as password). "
                    "Bearer-only PAT often fails on Assets. "
                    "Also check Assets product access for the user."
                ),
                last.body,
            ) from last
        raise last

    @property
    def api_prefix(self) -> str:
        return self._prefix if self._prefix != "auto" else "/rest/assets/1.0"

    def get_object_schema(self, schema_id: int | None = None) -> dict[str, Any]:
        """GET .../objectschema/{id}"""
        sid = schema_id if schema_id is not None else self.settings.assets_object_schema_id
        return self._request("GET", f"/objectschema/{sid}")

    def aql_objects(
        self,
        ql_query: str,
        *,
        start_at: int = 0,
        max_results: int | None = None,
        include_attributes: bool = True,
    ) -> dict[str, Any]:
        """GET .../aql/objects"""
        limit = max_results if max_results is not None else self.settings.agent_max_assets
        params: dict[str, Any] = {
            "qlQuery": ql_query,
            "startAt": start_at,
            "maxResults": limit,
            "includeAttributes": str(include_attributes).lower(),
        }
        return self._request("GET", "/aql/objects", params=params)

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
        """POST .../object/navlist/iql"""
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
        return self._request("POST", "/object/navlist/iql", json=payload)

    def get_object(self, object_id: int | str) -> dict[str, Any]:
        """GET .../object/{id}"""
        return self._request("GET", f"/object/{object_id}")

    def get_connected_tickets(self, object_id: int | str) -> dict[str, Any]:
        """GET .../objectconnectedtickets/{id}/tickets"""
        return self._request("GET", f"/objectconnectedtickets/{object_id}/tickets")

    def search_assets_for_projects(
        self,
        project_keys: list[str],
        *,
        extra_aql: str = "",
        max_results: int | None = None,
    ) -> dict[str, Any]:
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
