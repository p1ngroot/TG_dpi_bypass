@echo off
REM Telegram Unblock - Windows Launcher

echo ====================================
echo Telegram Unblock - DPI Bypass Tool
echo ====================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python не найден. Установите Python 3.7+
    pause
    exit /b 1
)

echo [*] Запуск Telegram Unblock...
echo.

python telegram_unblock.py

pause
