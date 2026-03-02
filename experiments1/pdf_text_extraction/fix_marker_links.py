"""
Скрипт для исправления неправильно сконвертированных ссылок в markdown файлах от marker.
Исправляет ссылки вида [\\(text](#link) [text\\)](#link) на правильный формат.
"""

import re
from pathlib import Path


def fix_marker_links(text: str) -> str:
    """
    Исправляет неправильно сконвертированные ссылки в markdown.
    
    Проблемы:
    1. [\\(text](#link) -> [text](#link)
    2. [text\\)](#link) -> [text](#link)
    3. [\\(text](#link) [text\\)](#link) -> объединяет в одну ссылку или разделяет правильно
    """
    # Исправляем экранированные скобки в начале ссылок (перед открывающей скобкой ссылки)
    # Паттерн: [\(text -> [text
    text = re.sub(r'\[\\\(', '[', text)
    
    # Исправляем экранированные скобки в конце текста ссылки, но перед закрывающей скобкой markdown ссылки
    # Паттерн: text\)] -> text]
    # Но нужно быть осторожным, чтобы не затронуть скобки внутри URL
    # Ищем паттерн: [text\)](#url) где \) находится внутри текста ссылки
    text = re.sub(r'([^\]]+)\\\)\]\(', r'\1](', text)
    
    # Исправляем случаи, где ссылка разбита на части:
    # [\(text1;](#link1) [text2\)](#link2) -> [text1; text2](#link1) или разделяем правильно
    # Более сложный паттерн для объединения разбитых ссылок
    # Ищем паттерны вида: [text1;](#link1) [text2\)](#link2)
    pattern = r'\[([^\]]+);?\]\(([^\)]+)\)\s*\[([^\]]+)\\?\)\]\(([^\)]+)\)'
    
    def replace_broken_links(match):
        text1 = match.group(1)
        link1 = match.group(2)
        text2 = match.group(3)
        link2 = match.group(4)
        
        # Если ссылки одинаковые, объединяем текст
        if link1 == link2:
            return f"[{text1}; {text2}]({link1})"
        else:
            # Если разные, разделяем правильно
            return f"[{text1}]({link1}) [{text2}]({link2})"
    
    text = re.sub(pattern, replace_broken_links, text)
    
    # Исправляем оставшиеся случаи с экранированными скобками в тексте ссылки
    # [text\( -> [text (но не трогаем скобки в URL)
    text = re.sub(r'\[([^\]]+)\\\(', r'[\1', text)
    
    # Исправляем случаи где закрывающая скобка URL была удалена
    # Ищем паттерны вида: ](#page-X-Y без закрывающей скобки перед пробелом, точкой, запятой и т.д.
    # Паттерн: ](#page-X-Y без закрывающей скобки перед пробелом или другим символом
    text = re.sub(r'\]\(#([^\)\s]+)(\s|\.|,|;|\))', r'](#\1)\2', text)
    
    return text


def fix_markdown_file(file_path: Path):
    """Исправляет markdown файл."""
    print(f"Исправление файла: {file_path.name}")
    
    # Читаем файл
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Исправляем
    fixed_content = fix_marker_links(content)
    
    # Сохраняем обратно
    if fixed_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        print(f"  [OK] Файл исправлен")
        
        # Показываем статистику изменений
        original_errors = len(re.findall(r'\[\\\(|\\\)\]', content))
        fixed_errors = len(re.findall(r'\[\\\(|\\\)\]', fixed_content))
        print(f"  [INFO] Исправлено ошибок: {original_errors - fixed_errors}")
    else:
        print(f"  [INFO] Файл не требует исправлений")


def main():
    """Основная функция."""
    base_dir = Path(__file__).parent
    marker_output_dir = base_dir / "results" / "marker_markdown"
    
    if not marker_output_dir.exists():
        print(f"[ERROR] Директория не найдена: {marker_output_dir}")
        return
    
    # Находим все markdown файлы
    md_files = list(marker_output_dir.glob("*.md"))
    
    if not md_files:
        print(f"[ERROR] Markdown файлы не найдены в {marker_output_dir}")
        return
    
    print(f"Найдено файлов: {len(md_files)}\n")
    
    # Исправляем каждый файл
    for md_file in md_files:
        fix_markdown_file(md_file)
        print()


if __name__ == "__main__":
    main()
