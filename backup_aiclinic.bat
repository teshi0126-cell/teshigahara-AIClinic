@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo エラー: venvが見つかりません。
    pause
    exit /b 1
)

"venv\Scripts\python.exe" "scripts\backup_database.py"
if errorlevel 1 (
    echo バックアップに失敗しました。
    pause
    exit /b 1
)

pause
