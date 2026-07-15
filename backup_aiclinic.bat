@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo ERROR: The Python virtual environment was not found.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" "scripts\backup_database.py"
if errorlevel 1 (
    echo Database backup failed.
    pause
    exit /b 1
)

pause
