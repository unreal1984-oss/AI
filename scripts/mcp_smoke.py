#!/usr/bin/env python3
"""Smoke-test MCP initialize + tools/list over stdio (no Cursor required)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _frame(message: dict) -> bytes:
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def _read(proc: subprocess.Popen[bytes]) -> dict:
    headers: dict[str, str] = {}
    assert proc.stdout is not None
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout")
        text = line.decode("utf-8").rstrip("\r\n")
        if text == "":
            break
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    body = proc.stdout.read(length)
    return json.loads(body.decode("utf-8"))


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("JIRA_BASE_URL", "https://jira.example.com")
    env.setdefault("JIRA_USERNAME", "u")
    env.setdefault("JIRA_PASSWORD", "p")
    # MCP server only needs Jira settings; LLM not used
    env.setdefault("LLM_PROVIDER", "deepseek")
    env.setdefault("DEEPSEEK_API_KEY", "unused")

    proc = subprocess.Popen(
        [sys.executable, "-m", "jira_agent.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(ROOT),
        env=env,
    )
    assert proc.stdin and proc.stdout
    try:
        proc.stdin.write(
            _frame(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "smoke", "version": "0"},
                    },
                }
            )
        )
        proc.stdin.flush()
        init = _read(proc)
        assert init.get("result", {}).get("serverInfo", {}).get("name") == "jira-dc-agent"

        proc.stdin.write(
            _frame({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        proc.stdin.flush()

        proc.stdin.write(
            _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        )
        proc.stdin.flush()
        tools = _read(proc)
        names = {t["name"] for t in tools["result"]["tools"]}
        assert "search_issues" in names
        assert "search_assets_aql" in names
        print("MCP smoke OK:", ", ".join(sorted(names)))
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
