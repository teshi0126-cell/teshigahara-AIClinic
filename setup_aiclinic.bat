@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [AIClinic] Starting first-time setup.

if not exist "venv\Scripts\python.exe" (
    echo ERROR: The Python virtual environment was not found.
    echo Confirm that this file is in C:\AIClinic.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" "scripts\configure_production.py"
if errorlevel 1 goto :failed

"venv\Scripts\python.exe" -m pip install -r requirements-production.txt
if errorlevel 1 goto :failed

set DJANGO_PRODUCTION=true
set DJANGO_DEBUG=false
set DJANGO_HTTPS=false
set DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

"venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto :failed

"venv\Scripts\python.exe" manage.py collectstatic --noinput
if errorlevel 1 goto :failed

"venv\Scripts\python.exe" manage.py check
if errorlevel 1 goto :failed

"venv\Scripts\python.exe" manage.py check --deploy --fail-level ERROR
if errorlevel 1 goto :failed

echo.
echo [AIClinic] First-time setup completed.
echo Use start_aiclinic.bat for normal startup.
pause
exit /b 0

:failed
echo.
echo [AIClinic] Setup failed.
echo Keep this window open and review the error above.
pause
exit /b 1
