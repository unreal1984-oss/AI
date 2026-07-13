#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Write-Error "Python not found in PATH. Install Python 3.12+ from https://www.python.org/downloads/ (enable 'Add to PATH')."
}

Write-Host "Python:" (& python --version)

if (-not (Test-Path .venv)) {
  python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -e .
python -c "from jira_agent.cli import app; print('import ok')"

Write-Host ""
Write-Host "OK. Next:"
Write-Host "  copy .env.example .env"
Write-Host "  .\jira-agent.cmd doctor"
Write-Host "  .\jira-agent.cmd chat -p ITSM"
Write-Host "Or after Activate.ps1: jira-agent doctor"
