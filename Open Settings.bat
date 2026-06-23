@echo off
setlocal
set "APP_DIR=%~dp0"
set "EXE=%APP_DIR%dist\PersonalWallpaper\PersonalWallpaper.exe"

if exist "%EXE%" (
    start "" "%EXE%" --settings
    exit /b 0
)

if exist "%APP_DIR%.venv\Scripts\python.exe" (
    start "" "%APP_DIR%.venv\Scripts\python.exe" "%APP_DIR%main.py" --settings
    exit /b 0
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    start "" python "%APP_DIR%main.py" --settings
    exit /b 0
)

echo No se encontro Python ni el EXE compilado.
echo Instala Python y ejecuta:
echo python -m venv .venv
echo .\.venv\Scripts\activate
echo pip install -r requirements.txt
pause
