"""Загрузка переменных окружения из .env файла."""

import os
from pathlib import Path
from typing import Optional


def load_env_file(env_file: Optional[Path] = None) -> None:
    """
    Загружает переменные окружения из .env файла.
    
    Args:
        env_file: Путь к .env файлу. Если None, ищет .env в текущей директории и родительских.
    """
    if env_file is None:
        # Поиск .env файла в текущей директории и родительских
        current_dir = Path.cwd()
        for parent in [current_dir] + list(current_dir.parents):
            env_file = parent / ".env"
            if env_file.exists():
                break
        else:
            # .env файл не найден
            return
    
    if not env_file.exists():
        return
    
    # Загрузка .env файла
    with open(env_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Пропускаем пустые строки и комментарии
            if not line or line.startswith('#'):
                continue
            
            # Парсинг пар key=value
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Удаляем кавычки, если есть
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # Устанавливаем переменную окружения, если она ещё не установлена
                if key not in os.environ:
                    os.environ[key] = value
            else:
                print(f"Warning: Invalid line {line_num} in {env_file}: {line}")
