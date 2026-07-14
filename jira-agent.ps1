#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$runPy = Join-Path $PSScriptRoot "run.py"

if (Test-Path $venvPython) {
  & $venvPython $runPy @args
  exit $LASTEXITCODE
}

$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
  & python $runPy @args
  exit $LASTEXITCODE
}

Write-Error @"
Python not found. From repo root run:
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  pip install -e .
  .\jira-agent.cmd doctor
"@
