#!/bin/bash
# Скрипт для запуска оценки dedoc в Linux/Mac
# Использует виртуальное окружение venv_dedoc

cd "$(dirname "$0")"

echo "[INFO] Запуск оценки dedoc..."
echo "[INFO] Используется виртуальное окружение: venv_dedoc"

if [ ! -f "venv_dedoc/bin/python" ]; then
    echo "[ERROR] Виртуальное окружение не найдено!"
    echo "[INFO] Создайте его командой: python -m venv venv_dedoc"
    echo "[INFO] Затем установите dedoc: venv_dedoc/bin/pip install dedoc"
    exit 1
fi

venv_dedoc/bin/python evaluate_dedoc.py
