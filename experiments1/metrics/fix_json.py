#!/usr/bin/env python3
"""Скрипт для проверки и исправления JSON файлов разметки."""

import json
import sys
from pathlib import Path

def check_json_file(file_path: Path):
    """Проверяет JSON файл на ошибки."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Пытаемся распарсить
        try:
            data = json.loads(content)
            print(f"OK: File {file_path.name} is valid")
            return True
        except json.JSONDecodeError as e:
            print(f"ERROR in file {file_path.name}:")
            print(f"  Строка {e.lineno}, колонка {e.colno}: {e.msg}")
            print(f"  Позиция: {e.pos}")
            
            # Показываем контекст
            lines = content.split('\n')
            if e.lineno <= len(lines):
                line = lines[e.lineno - 1]
                print(f"  Проблемная строка: {line[:100]}...")
                if e.colno:
                    print(f"  {' ' * (e.colno - 1)}^")
            
            return False
            
    except Exception as e:
        print(f"ERROR reading file {file_path.name}: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python fix_json.py <path_to_json_file>")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Файл не найден: {file_path}")
        sys.exit(1)
    
    check_json_file(file_path)
