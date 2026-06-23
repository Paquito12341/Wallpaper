$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PythonCandidates = @()

if ($env:VIRTUAL_ENV) {
    $PythonCandidates += Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
}

$PythonCandidates += ".\.venv\Scripts\python.exe"
$PythonCandidates += "python"
$PythonCandidates += "py"

$Python = $null
foreach ($Candidate in $PythonCandidates) {
    try {
        & $Candidate -c "import sys; print(sys.executable)" *> $null
        if ($LASTEXITCODE -eq 0) {
            $Python = $Candidate
            break
        }
    } catch {
    }
}

if (-not $Python) {
    throw "No usable Python executable was found. Activate your virtual environment and rerun this script."
}

Write-Host "Using Python: $Python"

& $Python -m pip install --upgrade pyinstaller

$IconArgs = @()
$IconPath = Join-Path $ProjectRoot "assets\logo.ico"
if (Test-Path $IconPath) {
    $IconArgs = @("--icon", $IconPath)
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name PersonalWallpaper `
    @IconArgs `
    --add-data "config.json;." `
    --add-data "wallpapers;wallpapers" `
    --add-data "assets;assets" `
    main.py

$DistRoot = Join-Path $ProjectRoot "dist\PersonalWallpaper"
Copy-Item -Path "config.json" -Destination $DistRoot -Force
Copy-Item -Path "wallpapers" -Destination $DistRoot -Recurse -Force
Copy-Item -Path "assets" -Destination $DistRoot -Recurse -Force
$OpenSettingsBat = @"
@echo off
start "" "%~dp0PersonalWallpaper.exe" --settings
"@
Set-Content -Path (Join-Path $DistRoot "Open Settings.bat") -Value $OpenSettingsBat -Encoding ASCII

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $DistRoot\PersonalWallpaper.exe"
