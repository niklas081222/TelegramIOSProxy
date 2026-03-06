@echo off
REM TranslateGram Watchdog — NSSM Service Installer
REM Registers and starts the watchdog as a headless Windows service.
REM The watchdog checks backend health every cycle and restarts it if frozen.
REM Run as Administrator.

setlocal

set SERVICE_NAME=TranslateGramWatchdog
set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%venv
set NSSM=%SCRIPT_DIR%nssm.exe
set PYTHON=%VENV_DIR%\Scripts\python.exe
set WATCHDOG_PY=%SCRIPT_DIR%watchdog.py
set LOG_DIR=%SCRIPT_DIR%logs

REM Check nssm exists
if not exist "%NSSM%" (
    echo ERROR: nssm.exe not found at %NSSM%
    pause
    exit /b 1
)

REM Create logs directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Ensure venv exists (should have been created by install_backend.bat)
if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
)

REM Remove existing service if present
"%NSSM%" stop %SERVICE_NAME% >nul 2>&1
"%NSSM%" remove %SERVICE_NAME% confirm >nul 2>&1

REM Install service
echo Installing %SERVICE_NAME% service...
"%NSSM%" install %SERVICE_NAME% "%PYTHON%" "%WATCHDOG_PY%"
"%NSSM%" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
"%NSSM%" set %SERVICE_NAME% DisplayName "TranslateGram Watchdog"
"%NSSM%" set %SERVICE_NAME% Description "Health monitor for TranslateGram backend"

REM Logging
"%NSSM%" set %SERVICE_NAME% AppStdout "%LOG_DIR%\watchdog_stdout.log"
"%NSSM%" set %SERVICE_NAME% AppStderr "%LOG_DIR%\watchdog_stderr.log"
"%NSSM%" set %SERVICE_NAME% AppStdoutCreationDisposition 4
"%NSSM%" set %SERVICE_NAME% AppStderrCreationDisposition 4
"%NSSM%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM%" set %SERVICE_NAME% AppRotateBytes 1048576

REM Auto-start on boot, restart on ANY exit (this is the cycle mechanism)
"%NSSM%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM%" set %SERVICE_NAME% AppRestartDelay 0

REM Start the service
echo Starting %SERVICE_NAME%...
"%NSSM%" start %SERVICE_NAME%

echo.
echo Service %SERVICE_NAME% installed and started.
echo Cycle: sleep 5s, check /health, exit, NSSM restarts, repeat.
echo.
pause
