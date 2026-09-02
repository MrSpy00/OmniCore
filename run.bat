@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  OmniCore Quick Launcher
::  Usage: run.bat [mode]
::  Modes: cli (default), rest, telegram, mcp, hud, voice
:: ============================================================

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

:: Parse arguments
set "MODE=%~1"
if "%MODE%"=="" set "MODE=cli"

:: Validate mode
if /i "%MODE%"=="cli" goto launch
if /i "%MODE%"=="rest" goto launch
if /i "%MODE%"=="telegram" goto launch
if /i "%MODE%"=="mcp" goto launch
if /i "%MODE%"=="hud" goto launch
if /i "%MODE%"=="voice" goto launch
if /i "%MODE%"=="--help" goto help
if /i "%MODE%"=="-h" goto help

echo Unknown mode: %MODE%
echo.
goto help

:help
echo.
echo  OmniCore Quick Launcher
echo  =======================
echo.
echo  Usage: run.bat [mode]
echo.
echo  Modes:
echo    cli       Interactive terminal (default)
echo    rest      REST API on port 8000
echo    telegram  Telegram bot
echo    mcp       MCP JSON-RPC server
echo    hud       Cyberpunk HUD
echo    voice     Duplex voice engine
echo.
echo  Examples:
echo    run.bat              — Launch CLI
echo    run.bat rest         — Launch REST API
echo    run.bat hud          — Launch HUD
echo.
goto :eof

:launch
echo.
echo  Starting OmniCore [%MODE%]...
echo  (Press Ctrl+C to stop)
echo.
uv run omnicore --mode %MODE%
if errorlevel 1 (
    echo.
    echo  OmniCore exited with errors.
    echo  Try: setup.bat ^> Health Check
)
