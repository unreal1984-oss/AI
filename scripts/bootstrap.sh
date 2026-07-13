#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
echo "OK. Activate: source .venv/bin/activate"
echo "Next: cp .env.example .env && jira-agent doctor"
