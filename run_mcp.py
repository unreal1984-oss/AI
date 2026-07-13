#!/usr/bin/env python3
"""Windows/Linux entrypoint for Cursor MCP (no PYTHONPATH required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from jira_agent.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
