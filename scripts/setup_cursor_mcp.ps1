#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "== Jira DC MCP setup for Cursor (Windows) =="

if (-not (Test-Path .venv\Scripts\python.exe)) {
  Write-Host "Creating .venv ..."
  python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -e .

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "Created .env — fill JIRA_* only (no DeepSeek key needed)"
}

New-Item -ItemType Directory -Force -Path .cursor | Out-Null
Copy-Item .cursor\mcp.json.example .cursor\mcp.json -Force
Write-Host "Wrote .cursor\mcp.json -> cmd.exe /c jira-agent-mcp.cmd"

Write-Host ""
Write-Host "Testing launcher..."
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/c `"$PWD\jira-agent-mcp.cmd`""
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.WorkingDirectory = "$PWD"
$p = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Milliseconds 800
if (-not $p.HasExited) {
  $p.Kill()
  Write-Host "Launcher starts OK (killed after smoke start)"
} else {
  $err = $p.StandardError.ReadToEnd()
  Write-Host "Launcher exited early. stderr:"
  Write-Host $err
}

Write-Host ""
Write-Host "MCP protocol smoke:"
& .\.venv\Scripts\python.exe scripts\mcp_smoke.py

Write-Host ""
Write-Host "NEXT:"
Write-Host "  1) Open THIS repo folder as Cursor workspace"
Write-Host "  2) Settings -> MCP -> enable jira-dc (should be green)"
Write-Host "  3) Command Palette -> Developer: Reload Window"
Write-Host "  4) Ask in Agent (not jira-agent.cmd chat)"
Write-Host ""
Write-Host "If MCP still fails, check that file exists:"
Write-Host "  $PWD\jira-agent-mcp.cmd"
Write-Host "  $PWD\.venv\Scripts\python.exe"
