@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\waitress-serve.exe" (
    echo エラー: 運用サーバーが未設定です。
    echo 先に setup_aiclinic.bat を実行してください。
    pause
    exit /b 1
)

if not exist "staticfiles" (
    echo エラー: 画面用ファイルが準備されていません。
    echo 先に setup_aiclinic.bat を実行してください。
    pause
    exit /b 1
)

set DJANGO_PRODUCTION=true
set DJANGO_DEBUG=false
set DJANGO_HTTPS=false
set DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

echo [AIClinic] http://127.0.0.1:8000/ で起動します。
echo 終了するときは、この画面で Ctrl+C を押してください。
start "" "http://127.0.0.1:8000/"

"venv\Scripts\waitress-serve.exe" ^
  --listen=127.0.0.1:8000 ^
  --threads=4 ^
  --channel-timeout=300 ^
  --no-expose-tracebacks ^
  clinic.wsgi:application

echo.
echo [AIClinic] サーバーを終了しました。
pause
