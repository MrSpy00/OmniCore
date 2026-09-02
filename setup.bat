@echo off
setlocal EnableDelayedExpansion
title OmniCore Setup & Installation Manager
color 0A
cls

:: ============================================================
::  OmniCore — Comprehensive Setup & Installation Manager
::  Version: 1.0.0
::  Auto-detects system, installs dependencies, configures PATH
:: ============================================================

:: --- Configuration ---
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PYTHON_MIN_VERSION=3.12"
set "LOG_DIR=%PROJECT_DIR%\.omnicore\logs"
set "CONFIG_FILE=%PROJECT_DIR%\.omnicore\config.json"
set "ENV_FILE=%PROJECT_DIR%\.env"

:: --- Ensure log directory exists ---
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\setup_%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%.log"
set "LOG_FILE=%LOG_FILE: =0%"

:: --- Helper functions ---
:log
    echo [%date% %time%] %~1 >> "%LOG_FILE%" 2>nul
    echo [%time:~0,8%] %~1
    goto :eof

:log_success
    echo [%time:~0,8%] [OK] %~1
    echo [%date% %time%] OK: %~1 >> "%LOG_FILE%" 2>nul
    goto :eof

:log_error
    echo [%time:~0,8%] [ERROR] %~1
    echo [%date% %time%] ERROR: %~1 >> "%LOG_FILE%" 2>nul
    goto :eof

:log_warning
    echo [%time:~0,8%] [WARN] %~1
    echo [%date% %time%] WARN: %~1 >> "%LOG_FILE%" 2>nul
    goto :eof

:: ============================================================
::  MENU
:: ============================================================
:menu
cls
echo.
echo  ============================================================
echo    OmniCore Setup ^& Installation Manager v1.0
echo  ============================================================
echo.
echo    [1] Full Install (first time setup)
echo    [2] Quick Install (dependencies only)
echo    [3] Update (pull latest + sync)
echo    [4] Uninstall (remove from PATH)
echo    [5] Health Check (diagnose issues)
echo    [6] Launch CLI
echo    [7] Launch REST API
echo    [8] Launch Telegram Bot
echo    [9] Launch HUD
echo   [10] View Logs
echo   [11] Exit
echo.
echo  ============================================================
echo.
set /p "CHOICE=  Select option (1-11): "

if "%CHOICE%"=="1" goto full_install
if "%CHOICE%"=="2" goto quick_install
if "%CHOICE%"=="3" goto update_project
if "%CHOICE%"=="4" goto uninstall
if "%CHOICE%"=="5" goto health_check
if "%CHOICE%"=="6" goto launch_cli
if "%CHOICE%"=="7" goto launch_rest
if "%CHOICE%"=="8" goto launch_telegram
if "%CHOICE%"=="9" goto launch_hud
if "%CHOICE%"=="10" goto view_logs
if "%CHOICE%"=="11" goto exit
echo Invalid option. Press any key to try again...
pause >nul
goto menu

:: ============================================================
::  FULL INSTALL
:: ============================================================
:full_install
cls
call :log "=== Full Installation Started ==="
echo.
echo  [1/6] Checking Python...
call :check_python
if errorlevel 1 goto menu

echo.
echo  [2/6] Checking uv package manager...
call :check_uv
if errorlevel 1 goto menu

echo.
echo  [3/6] Installing dependencies...
call :log "Installing dependencies with uv sync..."
cd /d "%PROJECT_DIR%"
uv sync >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log_error "uv sync failed. Check %LOG_FILE%"
    pause
    goto menu
)
call :log_success "Dependencies installed"

echo.
echo  [4/6] Installing Playwright browsers...
uv run playwright install chromium >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log_warning "Playwright install failed (non-critical)"
) else (
    call :log_success "Playwright chromium installed"
)

echo.
echo  [5/6] Setting up PATH...
call :setup_path
if errorlevel 1 goto menu

echo.
echo  [6/6] Verifying installation...
uv run omnicore --help >nul 2>&1
if errorlevel 1 (
    call :log_error "Installation verification failed"
    pause
    goto menu
)
call :log_success "Installation verified — 'omnicore' command works"

echo.
echo  ============================================================
echo    SETUP COMPLETE!
echo  ============================================================
echo.
echo    You can now run:
echo      omnicore              — Launch CLI mode
echo      omnicore --mode rest  — Launch REST API
echo      omnicore --mode hud   — Launch HUD
echo      omnicore --help       — Show all options
echo.
echo    Log: %LOG_FILE%
echo  ============================================================
echo.
pause
goto menu

:: ============================================================
::  QUICK INSTALL
:: ============================================================
:quick_install
cls
call :log "=== Quick Install ==="
echo.
echo  Installing dependencies only...
cd /d "%PROJECT_DIR%"
uv sync >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log_error "uv sync failed"
) else (
    call :log_success "Dependencies installed"
)
echo.
pause
goto menu

:: ============================================================
::  UPDATE
:: ============================================================
:update_project
cls
call :log "=== Update Started ==="
echo.
echo  [1/3] Pulling latest changes...
cd /d "%PROJECT_DIR%"
git pull origin main >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log_warning "git pull failed (not a git repo or no remote)"
) else (
    call :log_success "Latest changes pulled"
)

echo.
echo  [2/3] Syncing dependencies...
uv sync >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log_error "uv sync failed after update"
) else (
    call :log_success "Dependencies synced"
)

echo.
echo  [3/3] Running tests...
uv run pytest --tb=short -q >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log_warning "Some tests failed after update"
) else (
    call :log_success "All tests passed"
)

echo.
call :log_success "Update complete"
pause
goto menu

:: ============================================================
::  UNINSTALL
:: ============================================================
:uninstall
cls
call :log "=== Uninstall ==="
echo.
echo  Removing from PATH...
call :remove_path
echo.
call :log_success "OmniCore removed from PATH"
echo  (Project files are kept — delete manually if needed)
echo.
pause
goto menu

:: ============================================================
::  HEALTH CHECK
:: ============================================================
:health_check
cls
call :log "=== Health Check ==="
echo.
echo  ============================================================
echo    OmniCore Health Check
echo  ============================================================
echo.

echo  [1/7] Python version...
call :check_python
echo.

echo  [2/7] uv package manager...
call :check_uv
echo.

echo  [3/7] Dependencies...
cd /d "%PROJECT_DIR%"
uv pip check >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log_error "Dependency issues found"
) else (
    call :log_success "All dependencies OK"
)
echo.

echo  [4/7] Environment file...
if exist "%ENV_FILE%" (
    call :log_success ".env file exists"
) else (
    call :log_warning ".env file missing — copy from .env.example"
    if exist "%PROJECT_DIR%\.env.example" (
        copy "%PROJECT_DIR%\.env.example" "%ENV_FILE%" >nul
        call :log_success "Created .env from .env.example"
    )
)
echo.

echo  [5/7] API keys configured...
if exist "%ENV_FILE%" (
    findstr /C:"GOOGLE_API_KEY=your" "%ENV_FILE%" >nul 2>&1
    if not errorlevel 1 (
        call :log_warning "GOOGLE_API_KEY not configured"
    ) else (
        call :log_success "GOOGLE_API_KEY configured"
    )
    findstr /C:"GROQ_API_KEY=your" "%ENV_FILE%" >nul 2>&1
    if not errorlevel 1 (
        call :log_warning "GROQ_API_KEY not configured"
    ) else (
        call :log_success "GROQ_API_KEY configured"
    )
) else (
    call :log_warning "No .env file to check"
)
echo.

echo  [6/7] Console script...
uv run omnicore --help >nul 2>&1
if errorlevel 1 (
    call :log_error "Console script not working"
) else (
    call :log_success "Console script OK"
)
echo.

echo  [7/7] Tool count...
uv run python -c "from tools.registry import discover_tool_classes; from pathlib import Path; print(f'  {len(discover_tool_classes(Path(\"tools\")))} tools registered')" 2>nul
echo.

echo  ============================================================
echo    Health check complete. Log: %LOG_FILE%
echo  ============================================================
echo.
pause
goto menu

:: ============================================================
::  LAUNCH MODES
:: ============================================================
:launch_cli
cls
call :log "Launching CLI mode..."
cd /d "%PROJECT_DIR%"
uv run omnicore --mode cli
goto menu

:launch_rest
cls
call :log "Launching REST API..."
cd /d "%PROJECT_DIR%"
echo.
echo  OmniCore REST API starting on http://localhost:8000
echo  Health: http://localhost:8000/health
echo  Chat:   POST http://localhost:8000/chat
echo.
uv run omnicore --mode rest
goto menu

:launch_telegram
cls
call :log "Launching Telegram Bot..."
cd /d "%PROJECT_DIR%"
uv run omnicore --mode telegram
goto menu

:launch_hud
cls
call :log "Launching HUD..."
cd /d "%PROJECT_DIR%"
uv run omnicore --mode hud
goto menu

:: ============================================================
::  VIEW LOGS
:: ============================================================
:view_logs
cls
echo.
echo  Recent setup logs:
echo  ------------------
if exist "%LOG_DIR%" (
    for /f "tokens=*" %%f in ('dir /b /o-d "%LOG_DIR%\setup_*.log" 2^>nul') do (
        echo  %%f
    )
) else (
    echo  No logs found.
)
echo.
echo  Enter log filename to view (or press Enter to go back):
set /p "LOGNAME=  "
if not "%LOGNAME%"=="" (
    if exist "%LOG_DIR%\%LOGNAME%" (
        echo.
        type "%LOG_DIR%\%LOGNAME%"
        echo.
    ) else (
        echo  Log not found.
    )
)
echo.
pause
goto menu

:: ============================================================
::  SYSTEM CHECKS
:: ============================================================
:check_python
    python --version >nul 2>&1
    if errorlevel 1 (
        call :log_error "Python not found. Install Python 3.12+ from https://python.org"
        call :log_error "Make sure 'Add to PATH' is checked during installation"
        exit /b 1
    )
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    call :log_success "Python found: %PY_VER%"
    exit /b 0

:check_uv
    where uv >nul 2>&1
    if errorlevel 1 (
        call :log_warning "uv not found. Installing..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" >> "%LOG_FILE%" 2>&1
        if errorlevel 1 (
            call :log_error "Failed to install uv. Install manually: https://docs.astral.sh/uv/"
            exit /b 1
        )
        call :log_success "uv installed successfully"
        :: Refresh PATH
        set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
    ) else (
        call :log_success "uv found"
    )
    exit /b 0

:: ============================================================
::  PATH MANAGEMENT
:: ============================================================
:setup_path
    :: Check if already in PATH
    echo %PATH% | findstr /C:"%PROJECT_DIR%" >nul 2>&1
    if not errorlevel 1 (
        call :log_success "Already in PATH"
        exit /b 0
    )

    :: Add to user PATH via registry
    call :log "Adding to user PATH..."
    powershell -Command "[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path', 'User') + ';%PROJECT_DIR%', 'User')" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        call :log_error "Failed to add to PATH"
        exit /b 1
    )

    :: Also update current session PATH
    set "PATH=%PATH%;%PROJECT_DIR%"

    call :log_success "Added to PATH (restart terminal to take effect)"
    exit /b 0

:remove_path
    powershell -Command "$p = [Environment]::GetEnvironmentVariable('Path', 'User'); $p = ($p -split ';' | Where-Object { $_ -ne '%PROJECT_DIR%' }) -join ';'; [Environment]::SetEnvironmentVariable('Path', $p, 'User')" >> "%LOG_FILE%" 2>&1
    call :log_success "Removed from PATH"
    exit /b 0

:: ============================================================
::  EXIT
:: ============================================================
:exit
call :log "Setup manager closed"
endlocal
exit /b 0
