@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUNBUFFERED=1"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

if exist "%CD%\.venv\Scripts\python.exe" (
  "%CD%\.venv\Scripts\python.exe" "%CD%\run_mcp.py"
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%CD%\run_mcp.py"
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%CD%\run_mcp.py"
  exit /b %ERRORLEVEL%
)

echo [jira-dc MCP] Python not found. Create .venv first. 1>&2
exit /b 1
