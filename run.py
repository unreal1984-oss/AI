#!/usr/bin/env python3
"""Run the CLI without requiring an editable install.

Usage:
  python run.py doctor
  python run.py chat -p ITSM
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from jira_agent.cli import app  # noqa: E402


if __name__ == "__main__":
    app()
