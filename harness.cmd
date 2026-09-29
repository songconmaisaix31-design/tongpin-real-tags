@echo off
setlocal
set "HARNESS_PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "HARNESS_PYTHON=%~dp0.venv\Scripts\python.exe"
"%HARNESS_PYTHON%" "%~dp0tools\harness_cli.py" %*
set "HARNESS_EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %HARNESS_EXIT_CODE%
