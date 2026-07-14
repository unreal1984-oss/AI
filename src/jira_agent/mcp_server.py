"""Minimal MCP stdio server for Cursor — Jira DC + Assets tools.

Supports both:
  - Content-Length framing (LSP-style)
  - Newline-delimited JSON (some Cursor/Windows builds)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from jira_agent.assets_client import AssetsClient
from jira_agent.config import Settings, get_settings
from jira_agent.jira_client import JiraClient
from jira_agent.tools import ToolRegistry, ollama_tool_schemas

SERVER_NAME = "jira-dc-agent"
SERVER_VERSION = "1.4.2"


def _log(msg: str) -> None:
    print(f"[jira-dc-mcp] {msg}", file=sys.stderr, flush=True)


def mcp_tool_defs() -> list[dict[str, Any]]:
    tools = [
        {
            "name": "jira_health",
            "description": (
                "Quick health check: Jira URL, visible project count, Assets schema id. "
                "Call this first if unsure whether Jira MCP works."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        }
    ]
    for item in ollama_tool_schemas():
        fn = item.get("function") or {}
        tools.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "inputSchema": fn.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return tools


class McpServer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jira: JiraClient | None = None
        self._assets: AssetsClient | None = None
        self._tools: ToolRegistry | None = None
        self._use_content_length = True

    def _ensure_tools(self) -> ToolRegistry:
        if self._tools is None:
            _log("creating Jira/Assets clients (first tool call)")
            self._jira = JiraClient(self.settings)
            self._assets = AssetsClient(self.settings)
            self._tools = ToolRegistry(self.settings, self._jira, self._assets)
        return self._tools

    def close(self) -> None:
        if self._jira is not None:
            self._jira.close()
        if self._assets is not None:
            self._assets.close()

    def run(self) -> None:
        _log("stdio loop started")
        try:
            while True:
                message = self._read_message()
                if message is None:
                    _log("stdin closed")
                    break
                method = message.get("method")
                _log(f"recv method={method!r} id={message.get('id')!r}")
                response = self._dispatch(message)
                if response is not None:
                    self._write_message(response)
                    _log(f"sent response id={response.get('id')!r}")
        finally:
            self.close()

    def _read_message(self) -> dict[str, Any] | None:
        """Read one JSON-RPC message (Content-Length or NDJSON)."""
        line = sys.stdin.buffer.readline()
        if not line:
            return None

        # NDJSON: first line is already a JSON object
        stripped = line.lstrip()
        if stripped.startswith(b"{"):
            self._use_content_length = False
            return json.loads(line.decode("utf-8"))

        # Content-Length framing
        self._use_content_length = True
        headers: dict[str, str] = {}
        first = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if ":" in first:
            key, value = first.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        while True:
            next_line = sys.stdin.buffer.readline()
            if not next_line:
                return None
            if next_line in (b"\r\n", b"\n"):
                break
            text = next_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if ":" not in text:
                # Unexpected: treat as NDJSON payload
                if text.lstrip().startswith("{"):
                    self._use_content_length = False
                    return json.loads(text)
                continue
            key, value = text.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        length_raw = headers.get("content-length")
        if not length_raw:
            return None
        length = int(length_raw)
        body = sys.stdin.buffer.read(length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def _write_message(self, message: dict[str, Any]) -> None:
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        if self._use_content_length:
            header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
            sys.stdout.buffer.write(header + raw)
        else:
            sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()

    def _dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        msg_id = message.get("id", _MISSING)
        method = message.get("method")
        params = message.get("params") or {}

        if method == "initialize":
            client_version = params.get("protocolVersion") or "2024-11-05"
            return self._ok(
                msg_id,
                {
                    "protocolVersion": client_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return self._ok(msg_id, {})
        if method == "tools/list":
            return self._ok(msg_id, {"tools": mcp_tool_defs()})
        if method == "tools/call":
            return self._ok(msg_id, self._call_tool(params))
        if method == "shutdown":
            return self._ok(msg_id, {})
        if msg_id is _MISSING:
            return None
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        try:
            if name == "jira_health":
                text = self._health()
            else:
                text = self._ensure_tools().execute(name, arguments)
            text = _truncate(text, 12000)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            _log(f"tool error {name}: {exc}")
            return {
                "content": [{"type": "text", "text": _truncate(err, 2000)}],
                "isError": True,
            }

    def _health(self) -> str:
        """Lightweight check — no huge payloads."""
        try:
            tools = self._ensure_tools()
            projects = json.loads(tools.execute("list_projects", {}))
            count = projects.get("count", 0)
            return json.dumps(
                {
                    "ok": True,
                    "jira": self.settings.jira_base_url,
                    "projects_visible": count,
                    "schema_id": self.settings.assets_object_schema_id,
                    "default_projects": self.settings.jira_project_keys,
                },
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {"ok": False, "error": str(exc), "jira": self.settings.jira_base_url},
                ensure_ascii=False,
            )

    @staticmethod
    def _ok(msg_id: Any, result: Any) -> dict[str, Any] | None:
        if msg_id is _MISSING:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}


_MISSING = object()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…[truncated]…"


def main() -> None:
    try:
        get_settings.cache_clear()
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        _log(f"config error: {exc}")
        # Still start server so initialize works; tool calls will fail clearly
        settings = Settings(
            jira_base_url="https://invalid.local",
            jira_username="unset",
            jira_password="unset",
        )
        _log("started with placeholder settings — fix .env / envFile")

    _log(
        f"ready jira={settings.jira_base_url} "
        f"schema={settings.assets_object_schema_id} "
        f"projects={','.join(settings.jira_project_keys) or '-'}"
    )
    McpServer(settings).run()


if __name__ == "__main__":
    main()
