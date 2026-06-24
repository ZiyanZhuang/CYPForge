@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "PYTHONPATH=%PROJECT_ROOT%src"
python -m cypforge_core.cli %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
