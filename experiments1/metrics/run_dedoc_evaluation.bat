@echo off
REM Скрипт для запуска оценки dedoc в Windows
REM Использует виртуальное окружение venv_dedoc

cd /d %~dp0

echo [INFO] Запуск оценки dedoc...
echo [INFO] Используется виртуальное окружение: venv_dedoc

if not exist "venv_dedoc\Scripts\python.exe" (
    echo [ERROR] Виртуальное окружение не найдено!
    echo [INFO] Создайте его командой: python -m venv venv_dedoc
    echo [INFO] Затем установите dedoc: venv_dedoc\Scripts\python.exe -m pip install dedoc
    pause
    exit /b 1
)

venv_dedoc\Scripts\python.exe evaluate_dedoc.py

pause
