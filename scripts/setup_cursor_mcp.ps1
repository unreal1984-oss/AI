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
  Write-Host "Created .env - fill JIRA_* only"
}

$CursorDir = Join-Path $Root ".cursor"
New-Item -ItemType Directory -Force -Path $CursorDir | Out-Null
Copy-Item (Join-Path $CursorDir "mcp.json.example") (Join-Path $CursorDir "mcp.json") -Force
Write-Host "Wrote .cursor\mcp.json (direct python.exe + run_mcp.py)"

$RunMcp = Join-Path $Root "run_mcp.py"
if (-not (Test-Path $RunMcp)) { throw "Missing run_mcp.py" }
if (-not (Test-Path $Python)) { throw "Missing .venv\Scripts\python.exe" }

Write-Host ""
Write-Host "MCP protocol smoke:"
& $Python (Join-Path $Root "scripts\mcp_smoke.py")
if ($LASTEXITCODE -ne 0) { throw "mcp_smoke.py failed" }

Write-Host ""
Write-Host "Manual start test (2 sec)..."
$p = Start-Process -FilePath $Python -ArgumentList $RunMcp -PassThru -WindowStyle Hidden -RedirectStandardError (Join-Path $env:TEMP "jira-mcp-err.txt")
Start-Sleep -Seconds 2
if (-not $p.HasExited) {
  Stop-Process -Id $p.Id -Force
  Write-Host "python run_mcp.py starts OK"
} else {
  Write-Host "python run_mcp.py exited early. See %TEMP%\jira-mcp-err.txt"
  Get-Content (Join-Path $env:TEMP "jira-mcp-err.txt") -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "NEXT in Cursor:"
Write-Host "  1) Settings -> MCP -> disable/enable jira-dc"
Write-Host "  2) Command Palette -> Developer: Reload Window"
Write-Host "  3) Wait until tools are listed (not 'loading')"
Write-Host "  4) Ask in Agent chat"
Write-Host ""
Write-Host "mcp.json must use python.exe + run_mcp.py (NOT cmd.exe)"
