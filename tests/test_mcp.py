"""MCP tool schema conversion."""

from __future__ import annotations

from jira_agent.mcp_server import mcp_tool_defs


def test_mcp_tool_defs() -> None:
    tools = mcp_tool_defs()
    names = {t["name"] for t in tools}
    assert "list_projects" in names
    assert "search_issues" in names
    assert "get_asset_tickets" in names
    for tool in tools:
        assert "inputSchema" in tool
        assert tool["inputSchema"].get("type") == "object"
