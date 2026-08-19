@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Daybook AI is not installed yet. Run install.bat first.
    exit /b 1
)
"%PY%" "%ROOT%run.py" %*
exit /b %ERRORLEVEL%
