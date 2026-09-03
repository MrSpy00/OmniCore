# ============================================================
#  OmniCore PowerShell Launcher
#  Usage: .\run.ps1 [mode]
#  Modes: cli (default), web, voice, rest, telegram, mcp, hud
# ============================================================

param(
    [ValidateSet("cli", "web", "voice", "rest", "telegram", "mcp", "hud", "--help", "-h")]
    [string]$Mode = "cli",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Enforce UTF-8 across PowerShell streams and Python process
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
chcp 65001 >$null 2>&1

if ($Mode -eq "--help" -or $Mode -eq "-h") {
    Write-Host ""
    Write-Host "OmniCore Quick Launcher" -ForegroundColor Cyan
    Write-Host "======================="
    Write-Host ""
    Write-Host "Usage: .\run.ps1 [mode] [options]"
    Write-Host ""
    Write-Host "Modes:" -ForegroundColor Yellow
    Write-Host "  cli       Interactive terminal (default)"
    Write-Host "  web       Web Dashboard & Browser Voice (http://localhost:8080)"
    Write-Host "  voice     Duplex voice engine"
    Write-Host "  rest      REST API on port 8000"
    Write-Host "  telegram  Telegram bot"
    Write-Host "  mcp       MCP JSON-RPC server"
    Write-Host "  hud       Cyberpunk HUD"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  .\run.ps1              # Launch CLI"
    Write-Host "  .\run.ps1 web          # Launch Web Dashboard"
    Write-Host "  .\run.ps1 voice        # Launch Voice Assistant"
    Write-Host "  .\run.ps1 rest         # Launch REST API"
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  Starting OmniCore [$Mode]..." -ForegroundColor Cyan
Write-Host "  (Press Ctrl+C to stop)" -ForegroundColor DarkGray
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $ProjectDir

# Tier 1: Try uv
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run omnicore --mode $Mode @ExtraArgs
    exit $LASTEXITCODE
}

# Tier 2: Try .venv console script
$VenvScript = Join-Path $ProjectDir ".venv\Scripts\omnicore.exe"
if (Test-Path $VenvScript) {
    & $VenvScript --mode $Mode @ExtraArgs
    exit $LASTEXITCODE
}

# Tier 3: Try dist\OmniCore.exe
$DistExe = Join-Path $ProjectDir "dist\OmniCore.exe"
if (Test-Path $DistExe) {
    & $DistExe --mode $Mode @ExtraArgs
    exit $LASTEXITCODE
}

# Tier 4: Try python
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $ProjectDir "scripts\run.py") --mode $Mode @ExtraArgs
    exit $LASTEXITCODE
}

Write-Host "[ERROR] Could not find uv, virtualenv or OmniCore.exe" -ForegroundColor Red
Write-Host "Run .\setup.bat to configure the environment." -ForegroundColor Yellow
exit 1
