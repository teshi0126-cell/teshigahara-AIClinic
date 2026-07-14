@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [AIClinic] 初回設定を開始します。

if not exist "venv\Scripts\python.exe" (
    echo エラー: venvが見つかりません。
    echo C:\AIClinicで仮想環境を確認してください。
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
echo [AIClinic] 初回設定が完了しました。
echo 次回から start_aiclinic.bat を使用してください。
pause
exit /b 0

:failed
echo.
echo [AIClinic] 設定中にエラーが発生しました。
echo 画面を閉じず、表示内容を確認してください。
pause
exit /b 1
