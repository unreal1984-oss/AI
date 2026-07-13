#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "== Jira DC MCP setup for Cursor =="

if (-not (Test-Path .venv\Scripts\python.exe)) {
  Write-Host "Creating .venv ..."
  python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -e .

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "Created .env — fill JIRA_* (DEEPSEEK_API_KEY not needed for MCP)"
} else {
  Write-Host ".env already exists"
}

New-Item -ItemType Directory -Force -Path .cursor | Out-Null
Copy-Item .cursor\mcp.json.example .cursor\mcp.json -Force
Write-Host "Wrote .cursor\mcp.json (Windows venv python)"

Write-Host ""
Write-Host "Smoke test:"
& .\.venv\Scripts\python.exe scripts\mcp_smoke.py

Write-Host ""
Write-Host "NEXT in Cursor:"
Write-Host "  1) Open this folder as workspace"
Write-Host "  2) Settings -> MCP -> enable server 'jira-dc'"
Write-Host "  3) Command Palette -> Reload Window"
Write-Host "  4) Open Agent chat and ask about Jira projects/assets"
Write-Host "Do NOT use .\jira-agent.cmd chat (that still needs DeepSeek balance)."
