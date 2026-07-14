#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -e .

python -c "from jira_agent.cli import app; print('import ok:', app)"
echo
echo "OK. Activate: source .venv/bin/activate"
echo "Next: cp .env.example .env && jira-agent doctor"
echo "Or without install: python run.py doctor"
