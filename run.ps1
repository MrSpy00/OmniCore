# ============================================================
#  OmniCore PowerShell Launcher
#  Usage: .\run.ps1 [mode]
#  Modes: cli (default), rest, telegram, mcp, hud, voice
# ============================================================

param(
    [ValidateSet("cli", "rest", "telegram", "mcp", "hud", "voice", "--help", "-h")]
    [string]$Mode = "cli"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Mode -eq "--help" -or $Mode -eq "-h") {
    Write-Host ""
    Write-Host "OmniCore Quick Launcher" -ForegroundColor Cyan
    Write-Host "======================="
    Write-Host ""
    Write-Host "Usage: .\run.ps1 [mode]"
    Write-Host ""
    Write-Host "Modes:" -ForegroundColor Yellow
    Write-Host "  cli       Interactive terminal (default)"
    Write-Host "  rest      REST API on port 8000"
    Write-Host "  telegram  Telegram bot"
    Write-Host "  mcp       MCP JSON-RPC server"
    Write-Host "  hud       Cyberpunk HUD"
    Write-Host "  voice     Duplex voice engine"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  .\run.ps1              # Launch CLI"
    Write-Host "  .\run.ps1 -Mode rest   # Launch REST API"
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "Starting OmniCore [$Mode]..." -ForegroundColor Cyan
Write-Host "(Press Ctrl+C to stop)" -ForegroundColor DarkGray
Write-Host ""

Set-Location $ProjectDir
& uv run omnicore --mode $Mode

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "OmniCore exited with errors." -ForegroundColor Red
    Write-Host "Run .\setup.ps1 to diagnose issues."
}
