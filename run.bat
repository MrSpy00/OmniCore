@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
::  OmniCore Quick Launcher
::  Usage: run.bat [mode] [options]
::  Modes: cli (default), web, voice, rest, telegram, mcp, hud
:: ============================================================

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

:: Parse arguments (default to web GUI when launched with no args)
set "MODE=%~1"
if "%MODE%"=="" set "MODE=web"


:: Extract remaining arguments
set "EXTRA_ARGS="
for /f "tokens=1,* delims= " %%a in ("%*") do (
    set "EXTRA_ARGS=%%b"
)

:: Validate mode
if /i "%MODE%"=="cli" goto launch
if /i "%MODE%"=="web" goto launch
if /i "%MODE%"=="voice" goto launch
if /i "%MODE%"=="rest" goto launch
if /i "%MODE%"=="telegram" goto launch
if /i "%MODE%"=="mcp" goto launch
if /i "%MODE%"=="hud" goto launch
if /i "%MODE%"=="--help" goto help
if /i "%MODE%"=="-h" goto help

:: If argument doesn't match standard modes, treat as cli option
if "%MODE:~0,1%"=="-" (
    set "EXTRA_ARGS=%*"
    set "MODE=cli"
    goto launch
)

echo Unknown mode: %MODE%
echo.
goto help

:help
echo.
echo  OmniCore Quick Launcher
echo  =======================
echo.
echo  Usage: run.bat [mode] [options]
echo.
echo  Modes:
echo    cli       Interactive terminal (default)
echo    web       Web Dashboard ^& Browser Voice (http://localhost:8080)
echo    voice     Duplex voice engine
echo    rest      REST API on port 8000
echo    telegram  Telegram bot
echo    mcp       MCP JSON-RPC server
echo    hud       Cyberpunk HUD
echo.
echo  Examples:
echo    run.bat              — Launch CLI
echo    run.bat web          — Launch Web Dashboard
echo    run.bat voice        — Launch Voice Assistant
echo    run.bat rest         — Launch REST API
echo    run.bat cli --debug  — Launch CLI with debug logging
echo.
goto :eof

:launch
echo.
echo  ======================================================
echo    Starting OmniCore [%MODE%]...
echo    (Press Ctrl+C to stop)
echo  ======================================================
echo.

:: Tier 1: Try uv package manager
where uv >nul 2>&1
if not errorlevel 1 (
    uv run omnicore --mode %MODE% %EXTRA_ARGS%
    goto finish
)

:: Tier 2: Try .venv console script
if exist "%PROJECT_DIR%\.venv\Scripts\omnicore.exe" (
    "%PROJECT_DIR%\.venv\Scripts\omnicore.exe" --mode %MODE% %EXTRA_ARGS%
    goto finish
)

:: Tier 3: Try dist\OmniCore.exe standalone
if exist "%PROJECT_DIR%\dist\OmniCore.exe" (
    "%PROJECT_DIR%\dist\OmniCore.exe" --mode %MODE% %EXTRA_ARGS%
    goto finish
)

:: Tier 4: Try virtualenv python
if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    "%PROJECT_DIR%\.venv\Scripts\python.exe" scripts\run.py --mode %MODE% %EXTRA_ARGS%
    goto finish
)

:: Tier 5: Try system python
where python >nul 2>&1
if not errorlevel 1 (
    python scripts\run.py --mode %MODE% %EXTRA_ARGS%
    goto finish
)

echo.
echo  [ERROR] Could not find 'uv', virtual environment, or standalone EXE.
echo  Please run setup.bat to install dependencies.
echo.
pause
goto :eof

:finish
if errorlevel 1 (
    echo.
    echo  OmniCore exited with an error code: %errorlevel%
    echo  Try: setup.bat ^> Health Check
    echo.
)
