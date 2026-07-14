"""MCP stdio framing: Content-Length and NDJSON."""

from __future__ import annotations

import json
from io import BytesIO

from jira_agent.config import Settings
from jira_agent.mcp_server import McpServer


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self._buf = BytesIO(data)

    @property
    def buffer(self):
        return self._buf


def test_read_ndjson(monkeypatch) -> None:
    settings = Settings(jira_base_url="https://jira.test", jira_username="u", jira_password="p")
    server = McpServer(settings)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    data = (json.dumps(payload) + "\n").encode()
    monkeypatch.setattr("jira_agent.mcp_server.sys.stdin", _FakeStdin(data))
    msg = server._read_message()
    assert msg is not None
    assert msg["method"] == "initialize"
    assert server._use_content_length is False


def test_read_content_length(monkeypatch) -> None:
    settings = Settings(jira_base_url="https://jira.test", jira_username="u", jira_password="p")
    server = McpServer(settings)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    data = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    monkeypatch.setattr("jira_agent.mcp_server.sys.stdin", _FakeStdin(data))
    msg = server._read_message()
    assert msg is not None
    assert msg["method"] == "ping"
    assert server._use_content_length is True
