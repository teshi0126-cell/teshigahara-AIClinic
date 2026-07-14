@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\waitress-serve.exe" (
    echo ERROR: The clinic server is not installed.
    echo Run setup_aiclinic.bat first.
    pause
    exit /b 1
)

if not exist "staticfiles" (
    echo ERROR: Static files are not prepared.
    echo Run setup_aiclinic.bat first.
    pause
    exit /b 1
)

set DJANGO_PRODUCTION=true
set DJANGO_DEBUG=false
set DJANGO_HTTPS=false
set DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

echo [AIClinic] Starting at http://127.0.0.1:8000/
echo To stop the server, press Ctrl+C once in this window.
start "" "http://127.0.0.1:8000/"

"venv\Scripts\waitress-serve.exe" ^
  --listen=127.0.0.1:8000 ^
  --threads=4 ^
  --channel-timeout=300 ^
  --no-expose-tracebacks ^
  clinic.wsgi:application

echo.
echo [AIClinic] Server stopped.
pause
