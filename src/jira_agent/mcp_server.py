"""Minimal MCP stdio server for Cursor — Jira DC + Assets tools.

Protocol: JSON-RPC 2.0 over stdio with Content-Length framing.
Clients are created lazily on first tools/call so initialize/tools/list stay fast.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from jira_agent.assets_client import AssetsClient
from jira_agent.config import Settings, get_settings
from jira_agent.jira_client import JiraClient
from jira_agent.tools import ToolRegistry, ollama_tool_schemas

SERVER_NAME = "jira-dc-agent"
SERVER_VERSION = "1.4.1"


def _log(msg: str) -> None:
    print(f"[jira-dc-mcp] {msg}", file=sys.stderr, flush=True)


def mcp_tool_defs() -> list[dict[str, Any]]:
    tools = []
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
        headers: dict[str, str] = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if ":" not in text:
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
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header + raw)
        sys.stdout.buffer.flush()

    def _dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        msg_id = message.get("id", _MISSING)
        method = message.get("method")
        params = message.get("params") or {}

        if method == "initialize":
            return self._ok(
                msg_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return self._ok(msg_id, {})
        if method == "tools/list":
            # Fast path: no Jira connection required
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
            text = self._ensure_tools().execute(name, arguments)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            _log(f"tool error {name}: {exc}")
            return {"content": [{"type": "text", "text": err}], "isError": True}

    @staticmethod
    def _ok(msg_id: Any, result: Any) -> dict[str, Any] | None:
        if msg_id is _MISSING:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}


_MISSING = object()


def main() -> None:
    try:
        get_settings.cache_clear()
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        _log(f"config error: {exc}")
        raise SystemExit(1) from exc

    _log(
        f"ready jira={settings.jira_base_url} "
        f"schema={settings.assets_object_schema_id} "
        f"projects={','.join(settings.jira_project_keys) or '-'}"
    )
    McpServer(settings).run()


if __name__ == "__main__":
    main()
