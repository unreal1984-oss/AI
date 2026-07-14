"""Compact JSON serializers for LLM context (avoid dumping huge payloads)."""

from __future__ import annotations

import json
from typing import Any


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _user_name(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None
    return user.get("displayName") or user.get("name") or user.get("key")


def _attr_map(obj: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for entry in obj.get("attributes") or []:
        name = (
            (entry.get("objectTypeAttribute") or {}).get("name")
            or entry.get("name")
            or f"attr_{entry.get('id')}"
        )
        values = []
        for v in entry.get("objectAttributeValues") or []:
            if "displayValue" in v:
                values.append(v["displayValue"])
            elif "value" in v:
                values.append(v["value"])
            elif "referencedObject" in v:
                ref = v["referencedObject"] or {}
                values.append(ref.get("label") or ref.get("name") or ref.get("id"))
        if len(values) == 1:
            attrs[name] = values[0]
        elif values:
            attrs[name] = values
    return attrs


def summarize_projects(projects: list[dict[str, Any]]) -> str:
    rows = [
        {
            "key": p.get("key"),
            "name": p.get("name"),
            "id": p.get("id"),
            "projectTypeKey": p.get("projectTypeKey"),
        }
        for p in projects
    ]
    return _dumps({"count": len(rows), "projects": rows})


def summarize_issue(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    issuetype = fields.get("issuetype") or {}
    priority = fields.get("priority") or {}
    project = fields.get("project") or {}
    return _dumps(
        {
            "key": issue.get("key"),
            "id": issue.get("id"),
            "summary": fields.get("summary"),
            "status": status.get("name"),
            "type": issuetype.get("name"),
            "priority": priority.get("name"),
            "assignee": _user_name(fields.get("assignee")),
            "reporter": _user_name(fields.get("reporter")),
            "project": project.get("key"),
            "labels": fields.get("labels") or [],
            "components": [c.get("name") for c in (fields.get("components") or [])],
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "description": _trim(fields.get("description"), 800),
        }
    )


def summarize_issues_payload(payload: dict[str, Any]) -> str:
    issues = payload.get("issues") or []
    rows = []
    for issue in issues:
        fields = issue.get("fields") or {}
        rows.append(
            {
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": (fields.get("status") or {}).get("name"),
                "type": (fields.get("issuetype") or {}).get("name"),
                "priority": (fields.get("priority") or {}).get("name"),
                "assignee": _user_name(fields.get("assignee")),
                "project": (fields.get("project") or {}).get("key"),
                "updated": fields.get("updated"),
            }
        )
    return _dumps(
        {
            "total": payload.get("total", len(rows)),
            "returned": len(rows),
            "startAt": payload.get("startAt", 0),
            "issues": rows,
        }
    )


def summarize_schema(schema: dict[str, Any]) -> str:
    return _dumps(
        {
            "id": schema.get("id"),
            "name": schema.get("name"),
            "objectSchemaKey": schema.get("objectSchemaKey") or schema.get("key"),
            "status": schema.get("status"),
            "description": _trim(schema.get("description"), 400),
        }
    )


def summarize_asset(obj: dict[str, Any]) -> str:
    return _dumps(
        {
            "id": obj.get("id"),
            "label": obj.get("label") or obj.get("name"),
            "objectKey": obj.get("objectKey"),
            "objectType": (obj.get("objectType") or {}).get("name"),
            "objectSchemaId": (obj.get("objectType") or {})
            .get("objectSchemaId", obj.get("objectSchemaId")),
            "created": obj.get("created"),
            "updated": obj.get("updated"),
            "attributes": _attr_map(obj),
        }
    )


def summarize_assets_payload(payload: dict[str, Any]) -> str:
    # AQL response uses objectEntries; navlist often uses objectEntries or values
    entries = (
        payload.get("objectEntries")
        or payload.get("values")
        or payload.get("objects")
        or []
    )
    rows = []
    for obj in entries:
        rows.append(
            {
                "id": obj.get("id"),
                "label": obj.get("label") or obj.get("name"),
                "objectKey": obj.get("objectKey"),
                "objectType": (obj.get("objectType") or {}).get("name"),
                "attributes": _attr_map(obj),
            }
        )
    return _dumps(
        {
            "total": payload.get("totalFilterCount")
            or payload.get("totalCount")
            or payload.get("total")
            or len(rows),
            "returned": len(rows),
            "objects": rows,
        }
    )


def summarize_tickets(payload: dict[str, Any]) -> str:
    tickets = payload.get("tickets") or payload.get("issues") or payload
    if isinstance(tickets, dict):
        # Some versions nest under ticketKeys / ticketIds
        if "tickets" in tickets:
            tickets = tickets["tickets"]
        elif "issues" in tickets:
            tickets = tickets["issues"]
    rows: list[Any] = []
    if isinstance(tickets, list):
        for t in tickets:
            if isinstance(t, str):
                rows.append({"key": t})
            elif isinstance(t, dict):
                rows.append(
                    {
                        "key": t.get("key") or t.get("ticketKey"),
                        "summary": t.get("summary")
                        or (t.get("fields") or {}).get("summary"),
                        "status": t.get("status")
                        or ((t.get("fields") or {}).get("status") or {}).get("name"),
                    }
                )
    return _dumps({"count": len(rows), "tickets": rows, "raw_keys": payload.get("ticketKeys")})


def _trim(value: Any, limit: int) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
