@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

if exist "%CD%\.venv\Scripts\python.exe" (
  "%CD%\.venv\Scripts\python.exe" -m jira_agent.mcp_server
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -m jira_agent.mcp_server
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python -m jira_agent.mcp_server
  exit /b %ERRORLEVEL%
)

echo [jira-dc MCP] Python not found. Run: scripts\setup_cursor_mcp.ps1 1>&2
exit /b 1
