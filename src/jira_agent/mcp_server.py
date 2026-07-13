"""Minimal MCP stdio server for Cursor — Jira DC + Assets tools.

Cursor does not expose a public chat/completions API. Instead, run this MCP
server inside Cursor Agent so Cursor's own models call Jira tools (no DeepSeek).

Protocol: JSON-RPC 2.0 over stdio with Content-Length framing (MCP).
No pydantic / mcp SDK — keeps Windows/Python 3.14 install light.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, TextIO

from jira_agent.assets_client import AssetsClient
from jira_agent.config import Settings, get_settings
from jira_agent.jira_client import JiraClient
from jira_agent.tools import ToolRegistry, ollama_tool_schemas


SERVER_NAME = "jira-dc-agent"
SERVER_VERSION = "1.4.0"


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
        self.jira = JiraClient(settings)
        self.assets = AssetsClient(settings)
        self.tools = ToolRegistry(settings, self.jira, self.assets)
        self._stdin: TextIO = sys.stdin
        self._stdout: TextIO = sys.stdout

    def close(self) -> None:
        self.jira.close()
        self.assets.close()

    def run(self) -> None:
        try:
            while True:
                message = self._read_message()
                if message is None:
                    break
                response = self._dispatch(message)
                if response is not None:
                    self._write_message(response)
        finally:
            self.close()

    def _read_message(self) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = self._stdin.readline()
            if line == "":
                return None
            line = line.rstrip("\r\n")
            if line == "":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        length_raw = headers.get("content-length")
        if not length_raw:
            return None
        length = int(length_raw)
        body = self._stdin.read(length)
        if not body:
            return None
        return json.loads(body)

    def _write_message(self, message: dict[str, Any]) -> None:
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        payload = body.encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header + payload)
        sys.stdout.buffer.flush()

    def _dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        # Notifications have no id
        msg_id = message.get("id", _MISSING)
        method = message.get("method")
        params = message.get("params") or {}

        if method == "initialize":
            return self._ok(
                msg_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "capabilities": {"tools": {}},
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
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        try:
            text = self.tools.execute(name, arguments)
            return {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            }
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            return {
                "content": [{"type": "text", "text": err}],
                "isError": True,
            }

    @staticmethod
    def _ok(msg_id: Any, result: Any) -> dict[str, Any] | None:
        if msg_id is _MISSING:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}


_MISSING = object()


def main() -> None:
    # Logs must not go to stdout (MCP framing). Use stderr.
    try:
        get_settings.cache_clear()
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        print(f"jira-dc MCP config error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        f"jira-dc MCP ready schema={settings.assets_object_schema_id} "
        f"projects={','.join(settings.jira_project_keys) or '-'}",
        file=sys.stderr,
    )
    McpServer(settings).run()


if __name__ == "__main__":
    main()
