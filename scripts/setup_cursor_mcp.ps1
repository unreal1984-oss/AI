#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== Jira DC MCP setup for Cursor (Windows) =="

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  Write-Host "Creating .venv ..."
  python -m venv .venv
}

& $Python -m pip install -U pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install -e .

$EnvFile = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"
if (-not (Test-Path $EnvFile)) {
  Copy-Item $EnvExample $EnvFile
  Write-Host "Created .env - fill JIRA_* only (no DeepSeek key needed)"
}

$CursorDir = Join-Path $Root ".cursor"
New-Item -ItemType Directory -Force -Path $CursorDir | Out-Null

$McpExample = Join-Path $CursorDir "mcp.json.example"
$McpJson = Join-Path $CursorDir "mcp.json"
Copy-Item $McpExample $McpJson -Force
Write-Host "Wrote .cursor\mcp.json"

$Launcher = Join-Path $Root "jira-agent-mcp.cmd"
if (-not (Test-Path $Launcher)) {
  throw "Missing jira-agent-mcp.cmd in repo root. Run: git pull"
}
if (-not (Test-Path $Python)) {
  throw "Missing .venv\Scripts\python.exe"
}

Write-Host ""
Write-Host "MCP protocol smoke:"
& $Python (Join-Path $Root "scripts\mcp_smoke.py")
if ($LASTEXITCODE -ne 0) {
  throw "mcp_smoke.py failed"
}

Write-Host ""
Write-Host "NEXT:"
Write-Host "  1) Open THIS repo folder as Cursor workspace"
Write-Host "  2) Settings -> MCP -> enable jira-dc (green)"
Write-Host "  3) Command Palette -> Developer: Reload Window"
Write-Host "  4) Ask in Agent (NOT jira-agent.cmd chat)"
Write-Host ""
Write-Host "Check files:"
Write-Host ("  " + $Launcher)
Write-Host ("  " + $Python)
Write-Host ("  " + $McpJson)
