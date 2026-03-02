"""
Скрипт для извлечения всех таблиц из DOCX файла в порядке появления.

Находит все таблицы, получает их в порядке, как они отмечены в тексте,
и сохраняет под именами 1.json, 2.json, 3.json и т.д. (или 1.md, 2.md)
"""

import sys
import json
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_xml_parser import extract_tables_from_docx_xml


def table_to_markdown(table_data: dict) -> str:
    """
    Конвертирует таблицу из DOCX в Markdown формат.
    
    Args:
        table_data: Словарь с данными таблицы
    
    Returns:
        Строка в формате Markdown
    """
    markdown_lines = []
    
    rows = table_data.get('rows', [])
    if not rows:
        return ""
    
    # Определяем максимальное количество колонок
    max_cols = table_data.get('cols_count', 0)
    if max_cols == 0:
        # Вычисляем из первой строки
        if rows:
            first_row = rows[0]
            cells = first_row.get('cells', [])
            max_cols = max(len(cells), 1)
    
    # Обрабатываем строки
    for row_data in rows:
        cells = row_data.get('cells', [])
        
        # Создаем массив для строки markdown
        row_cells = []
        
        for cell in cells:
            # Пропускаем ячейки с rowspan=0 (продолжение объединения)
            if cell.get('rowspan', 1) == 0:
                continue
            
            text = cell.get('text', '').strip()
            # Заменяем переносы строк на <br> для markdown
            text = text.replace('\n', '<br>')
            # Экранируем символы |
            text = text.replace('|', '\\|')
            row_cells.append(text)
        
        # Если ячеек меньше, чем max_cols, дополняем пустыми
        while len(row_cells) < max_cols:
            row_cells.append('')
        
        # Создаем строку markdown
        row_line = "| " + " | ".join(row_cells) + " |"
        markdown_lines.append(row_line)
        
        # Добавляем разделитель после первой строки (заголовок)
        if len(markdown_lines) == 1:
            separator = "| " + " | ".join(["---"] * max_cols) + " |"
            markdown_lines.append(separator)
    
    return "\n".join(markdown_lines)


def table_to_simple_data(table_data: dict) -> dict:
    """
    Конвертирует таблицу в простую структуру данных (список списков).
    
    Args:
        table_data: Словарь с данными таблицы
    
    Returns:
        Словарь с простой структурой таблицы
    """
    rows = table_data.get('rows', [])
    data = []
    
    for row_data in rows:
        cells = row_data.get('cells', [])
        row = []
        
        for cell in cells:
            # Пропускаем ячейки с rowspan=0 (продолжение объединения)
            if cell.get('rowspan', 1) == 0:
                continue
            
            cell_info = {
                'text': cell.get('text', '').strip(),
                'colspan': cell.get('colspan', 1),
                'rowspan': cell.get('rowspan', 1),
            }
            row.append(cell_info)
        
        data.append(row)
    
    return {
        'index': table_data.get('index'),
        'xml_position': table_data.get('xml_position'),
        'rows_count': table_data.get('rows_count', len(data)),
        'cols_count': table_data.get('cols_count', max(len(row) for row in data) if data else 0),
        'style': table_data.get('style'),
        'merged_cells': table_data.get('merged_cells', []),
        'data': data
    }


def save_tables_from_docx(docx_path: Path, output_dir: Path, format: str = 'both') -> None:
    """
    Извлекает все таблицы из DOCX и сохраняет их с последовательными номерами.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения таблиц
        format: Формат сохранения ('json', 'markdown', 'both')
    """
    print("=" * 80)
    print("ИЗВЛЕЧЕНИЕ ТАБЛИЦ ИЗ DOCX")
    print("=" * 80)
    print(f"DOCX файл: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"Формат: {format}")
    print("=" * 80 + "\n")
    
    # Создаем выходную директорию
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Извлекаем таблицы из DOCX XML
    print("Шаг 1: Извлечение таблиц из DOCX XML...")
    tables = extract_tables_from_docx_xml(docx_path)
    
    if not tables:
        print("  ✗ Таблицы не найдены")
        return
    
    print(f"  ✓ Найдено таблиц: {len(tables)}\n")
    
    # 2. Сохраняем таблицы в порядке появления
    print("Шаг 2: Сохранение таблиц...")
    
    saved_count = 0
    
    for table_idx, table_data in enumerate(tables, start=1):
        try:
            xml_position = table_data.get('xml_position', '?')
            rows_count = table_data.get('rows_count', 0)
            cols_count = table_data.get('cols_count', 0)
            style = table_data.get('style', 'нет стиля')
            merged_cells_count = len(table_data.get('merged_cells', []))
            
            # Сохраняем в JSON
            if format in ['json', 'both']:
                simple_data = table_to_simple_data(table_data)
                json_path = output_dir / f"{table_idx}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(simple_data, f, ensure_ascii=False, indent=2)
                print(f"  ✓ Сохранено JSON: {table_idx}.json")
            
            # Сохраняем в Markdown
            if format in ['markdown', 'both']:
                markdown = table_to_markdown(table_data)
                md_path = output_dir / f"{table_idx}.md"
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                print(f"  ✓ Сохранено Markdown: {table_idx}.md")
            
            print(f"     Позиция в XML: {xml_position}, Строк: {rows_count}, Колонок: {cols_count}, Объединенных ячеек: {merged_cells_count}, Стиль: {style}")
            print()
            
            saved_count += 1
        
        except Exception as e:
            print(f"  ✗ Ошибка при сохранении таблицы {table_idx}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"{'='*80}")
    print(f"ИТОГО: Сохранено {saved_count} из {len(tables)} таблиц")
    print(f"Директория: {output_dir}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python extract_tables_from_docx.py <docx_path> [output_dir] [format]")
        print("\nФорматы: json, markdown, both (по умолчанию: both)")
        print("\nПримеры:")
        print("  python extract_tables_from_docx.py test_folder/Диплом.docx")
        print("  python extract_tables_from_docx.py test_folder/Диплом.docx output/tables")
        print("  python extract_tables_from_docx.py test_folder/Диплом.docx output/tables json")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    # Определяем выходную директорию
    if len(sys.argv) >= 3:
        output_dir = Path(sys.argv[2])
    else:
        # По умолчанию: output/tables/<имя_файла>/
        output_dir = Path(__file__).parent / "output" / "tables" / docx_path.stem
    
    # Определяем формат
    format = 'both'
    if len(sys.argv) >= 4:
        format = sys.argv[3].lower()
        if format not in ['json', 'markdown', 'both']:
            print(f"Предупреждение: неизвестный формат '{format}', используем 'both'")
            format = 'both'
    
    save_tables_from_docx(docx_path, output_dir, format)
