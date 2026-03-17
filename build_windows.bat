@echo off
REM Build Windows Executable for Telegram Unblock

echo ====================================
echo Telegram Unblock - Windows Builder
echo ====================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python не найден. Установите Python 3.7+
    pause
    exit /b 1
)

echo [*] Проверка PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [*] PyInstaller не найден. Установка...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [!] Ошибка установки PyInstaller
        pause
        exit /b 1
    )
)

echo [+] PyInstaller найден
echo.
echo [*] Сборка исполняемого файла...
echo.

python -m PyInstaller --onefile --console --name "TelegramUnblock" telegram_unblock.py

if errorlevel 1 (
    echo.
    echo [!] Ошибка сборки
    pause
    exit /b 1
)

echo.
echo ====================================
echo [+] Сборка завершена!
echo ====================================
echo.
echo Исполняемый файл: dist\TelegramUnblock.exe
echo.
pause
