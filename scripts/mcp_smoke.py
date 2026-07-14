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


def _ndjson(message: dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


def _read_any(proc: subprocess.Popen[bytes]) -> dict:
    assert proc.stdout is not None
    first = proc.stdout.readline()
    if not first:
        err = b""
        if proc.stderr:
            err = proc.stderr.read()
        raise RuntimeError(f"MCP server closed stdout. stderr={err!r}")
    if first.lstrip().startswith(b"{"):
        return json.loads(first.decode("utf-8"))
    headers: dict[str, str] = {}
    text = first.decode("utf-8").rstrip("\r\n")
    key, value = text.split(":", 1)
    headers[key.strip().lower()] = value.strip()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout")
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("utf-8").rstrip("\r\n")
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    body = proc.stdout.read(length)
    return json.loads(body.decode("utf-8"))


def _run_session(send_bytes: bytes, expect_tools: bool = True) -> set[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("JIRA_BASE_URL", "https://jira.example.com")
    env.setdefault("JIRA_USERNAME", "u")
    env.setdefault("JIRA_PASSWORD", "p")
    env.setdefault("LLM_PROVIDER", "deepseek")
    env.setdefault("DEEPSEEK_API_KEY", "unused")

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run_mcp.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(ROOT),
        env=env,
    )
    assert proc.stdin and proc.stdout
    try:
        proc.stdin.write(send_bytes)
        proc.stdin.flush()
        init = _read_any(proc)
        assert init.get("result", {}).get("serverInfo", {}).get("name") == "jira-dc-agent"
        if not expect_tools:
            return set()
        # second message already in send_bytes batch or send tools/list
        tools = _read_any(proc)
        return {t["name"] for t in tools["result"]["tools"]}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "0"},
        },
    }
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    tools_list = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }

    # Content-Length session
    framed = _frame(init) + _frame(initialized) + _frame(tools_list)
    names = _run_session(framed)
    assert "search_issues" in names
    print("MCP framed OK:", ", ".join(sorted(names)))

    # NDJSON session (Cursor/Windows sometimes)
    nd = _ndjson(init) + _ndjson(initialized) + _ndjson(tools_list)
    names2 = _run_session(nd)
    assert "search_issues" in names2
    print("MCP ndjson OK:", ", ".join(sorted(names2)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
