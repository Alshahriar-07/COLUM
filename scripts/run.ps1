<#
.SYNOPSIS
    COLUM Beta 1 - Run Script for Windows

.DESCRIPTION
    This script runs the COLUM application.

.EXAMPLE
    .\scripts\run.ps1

.EXAMPLE
    .\scripts\run.ps1 --debug
#>

param(
    [switch]$Debug,
    [switch]$NoFrontend,
    [string]$Config = "config.yaml"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  COLUM Beta 1 - Starting..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Check for virtual environment
$venvPython = Join-Path $projectRoot ".venv" "Scripts" "python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
    Write-Host "Using virtual environment" -ForegroundColor Green
} else {
    $python = "python"
    Write-Host "Using system Python" -ForegroundColor Yellow
}

# Check .env exists
$envFile = Join-Path $projectRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Warning ".env file not found. Run setup.ps1 first or create .env manually."
    Write-Host "You can copy .env.example to .env and add your OPENROUTER_API_KEY" -ForegroundColor Yellow
}

# Build arguments
$args = @()
if ($Debug) { $args += "--log-level DEBUG" }
if ($NoFrontend) { $args += "--no-frontend" }
$args += "--config $Config"

$env:PYTHONPATH = $projectRoot

Write-Host "Starting COLUM..." -ForegroundColor Yellow
Write-Host ""

try {
    & $python -m app.main @args
} catch {
    Write-Error "Failed to start COLUM: $_"
    exit 1
}