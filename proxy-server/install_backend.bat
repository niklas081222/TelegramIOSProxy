@echo off
REM TranslateGram Backend — NSSM Service Installer
REM Registers and starts the backend as a headless Windows service.
REM Run as Administrator.

setlocal

set SERVICE_NAME=TranslateGramBackend
set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%venv
set NSSM=%SCRIPT_DIR%nssm.exe
set PYTHON=%VENV_DIR%\Scripts\python.exe
set MAIN_PY=%SCRIPT_DIR%main.py
set LOG_DIR=%SCRIPT_DIR%logs

REM Check nssm exists
if not exist "%NSSM%" (
    echo ERROR: nssm.exe not found at %NSSM%
    echo Download from https://nssm.cc/download and place nssm.exe in %SCRIPT_DIR%
    pause
    exit /b 1
)

REM Create logs directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Create isolated virtual environment
if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    echo Installing dependencies...
    "%VENV_DIR%\Scripts\pip.exe" install -r "%SCRIPT_DIR%requirements.txt"
)

REM Remove existing service if present
"%NSSM%" stop %SERVICE_NAME% >nul 2>&1
"%NSSM%" remove %SERVICE_NAME% confirm >nul 2>&1

REM Install service
echo Installing %SERVICE_NAME% service...
"%NSSM%" install %SERVICE_NAME% "%PYTHON%" "%MAIN_PY%"
"%NSSM%" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
"%NSSM%" set %SERVICE_NAME% DisplayName "TranslateGram Backend"
"%NSSM%" set %SERVICE_NAME% Description "TranslateGram translation proxy server"

REM Logging — redirect stdout/stderr to files (no console)
"%NSSM%" set %SERVICE_NAME% AppStdout "%LOG_DIR%\backend_stdout.log"
"%NSSM%" set %SERVICE_NAME% AppStderr "%LOG_DIR%\backend_stderr.log"
"%NSSM%" set %SERVICE_NAME% AppStdoutCreationDisposition 4
"%NSSM%" set %SERVICE_NAME% AppStderrCreationDisposition 4
"%NSSM%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM%" set %SERVICE_NAME% AppRotateBytes 10485760

REM Auto-start on boot, auto-restart on crash
"%NSSM%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM%" set %SERVICE_NAME% AppRestartDelay 3000

REM Start the service
echo Starting %SERVICE_NAME%...
"%NSSM%" start %SERVICE_NAME%

echo.
echo Service %SERVICE_NAME% installed and started.
echo Logs: %LOG_DIR%\backend_stdout.log
echo.
pause
