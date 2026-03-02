"""
Скрипт для определения типа TOC и извлечения текста из статических TOC полей.
"""
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.test_parse_toc import (
    detect_toc_type,
    extract_toc_text_from_field_result,
    parse_toc_from_hyperlinks,
    parse_toc_from_field,
    NAMESPACES
)

def analyze_toc_type(docx_path: Path):
    """Анализирует тип TOC в файле и извлекает заголовки."""
    print(f"\n{'='*80}")
    print(f"Анализ файла: {docx_path.name}")
    print(f"{'='*80}\n")
    
    if not docx_path.exists():
        print(f"[ERROR] Файл не найден: {docx_path}")
        return
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # Определяем тип TOC
            toc_type = detect_toc_type(root)
            print(f"Тип TOC: {toc_type}\n")
            
            # Извлекаем заголовки в зависимости от типа
            toc_entries = []
            
            if toc_type == 'dynamic_field':
                print("Используем метод: parse_toc_from_field (PAGEREF)")
                toc_entries = parse_toc_from_field(root)
            elif toc_type == 'static_field_result':
                print("Используем метод: extract_toc_text_from_field_result (статическое содержимое поля)")
                toc_entries = extract_toc_text_from_field_result(root)
                if not toc_entries:
                    print("Пробуем альтернативный метод: parse_toc_from_hyperlinks")
                    toc_entries = parse_toc_from_hyperlinks(root)
            elif toc_type == 'static_hyperlinks':
                print("Используем метод: parse_toc_from_hyperlinks")
                toc_entries = parse_toc_from_hyperlinks(root)
            elif toc_type == 'mixed':
                print("Используем метод: parse_toc_from_field (сначала), затем extract_toc_text_from_field_result")
                toc_entries = parse_toc_from_field(root)
                if not toc_entries:
                    toc_entries = extract_toc_text_from_field_result(root)
                if not toc_entries:
                    toc_entries = parse_toc_from_hyperlinks(root)
            else:
                print("Пробуем все методы по порядку...")
                toc_entries = parse_toc_from_field(root)
                if not toc_entries:
                    toc_entries = extract_toc_text_from_field_result(root)
                if not toc_entries:
                    toc_entries = parse_toc_from_hyperlinks(root)
            
            print(f"\nНайдено заголовков: {len(toc_entries)}\n")
            
            if toc_entries:
                print("Заголовки:")
                for i, entry in enumerate(toc_entries, 1):
                    title = entry.get('title', '').strip()
                    page = entry.get('page', '?')
                    level = entry.get('level', 1)
                    print(f"  {i}. [{level}] {title} (стр. {page})")
            else:
                print("[WARNING] Заголовки не найдены")
                
    except Exception as e:
        print(f"[ERROR] Ошибка при обработке: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    script_dir = Path(__file__).parent
    test_folder = script_dir / "test_folder"
    
    # Тестируем файлы
    files_to_test = [
        test_folder / "Diplom2024.docx",
        test_folder / "Диплом.docx",
        test_folder / "Отчёт_ГОСТ.docx",
    ]
    
    for docx_path in files_to_test:
        if docx_path.exists():
            analyze_toc_type(docx_path)
        else:
            print(f"[WARNING] Файл не найден: {docx_path}")
