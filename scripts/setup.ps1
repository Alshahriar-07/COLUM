<#
.SYNOPSIS
    COLUM Beta 1 - Setup Script for Windows

.DESCRIPTION
    This script sets up the COLUM development environment on Windows.
    It creates a virtual environment, installs dependencies, and prepares the project.

.EXAMPLE
    .\scripts\setup.ps1

.EXAMPLE
    .\scripts\setup.ps1 -SkipVenv
#>

param(
    [switch]$SkipVenv,
    [switch]$Dev,
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  COLUM Beta 1 - Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
try {
    $pythonVersion = & $PythonPath --version 2>&1
    Write-Host "Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Error "Python not found. Please install Python 3.10+ and ensure it's in PATH."
    exit 1
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Create virtual environment
if (-not $SkipVenv) {
    $venvPath = Join-Path $projectRoot ".venv"

    if (-not (Test-Path $venvPath)) {
        Write-Host "Creating virtual environment..." -ForegroundColor Yellow
        & $PythonPath -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create virtual environment"
            exit 1
        }
        Write-Host "Virtual environment created at $venvPath" -ForegroundColor Green
    } else {
        Write-Host "Virtual environment already exists" -ForegroundColor Green
    }

    $pipPath = Join-Path $venvPath "Scripts" "pip.exe"
    $pythonVenv = Join-Path $venvPath "Scripts" "python.exe"
} else {
    $pipPath = "pip"
    $pythonVenv = $PythonPath
}

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
& $pipPath install --upgrade pip

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $pipPath install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install dependencies"
    exit 1
}

# Install dev dependencies if requested
if ($Dev) {
    Write-Host "Installing development dependencies..." -ForegroundColor Yellow
    & $pipPath install -r requirements-dev.txt 2>$null || Write-Warning "requirements-dev.txt not found, skipping"
}

# Copy .env.example to .env if not exists
$envFile = Join-Path $projectRoot ".env"
$envExample = Join-Path $projectRoot ".env.example"

if (-not (Test-Path $envFile)) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item $envExample $envFile
    Write-Host "Created .env - Please edit it and add your OPENROUTER_API_KEY" -ForegroundColor Green
} else {
    Write-Host ".env already exists" -ForegroundColor Green
}

# Create necessary directories
$dirs = @(
    "data\logs",
    "data\cache",
    "data\memory",
    "logs"
)

foreach ($dir in $dirs) {
    $fullPath = Join-Path $projectRoot $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath | Out-Null
        Write-Host "Created directory: $dir" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Edit .env and add your OPENROUTER_API_KEY"
Write-Host "  2. Run COLUM: .\scripts\run.ps1"
Write-Host ""