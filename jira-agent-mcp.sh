#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m jira_agent.mcp_server
fi
exec python3 -m jira_agent.mcp_server
