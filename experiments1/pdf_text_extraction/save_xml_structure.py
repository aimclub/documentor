"""
Скрипт для сохранения полной структуры XML документа DOCX.

Сохраняет все элементы (параграфы, таблицы) с их свойствами, текстом и позициями
для детального анализа структуры документа.
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_xml_parser import (
    extract_all_elements_from_docx_xml_ordered,
    extract_text_from_element,
    NAMESPACES
)
from experiments.pdf_text_extraction.docx_complete_pipeline import (
    extract_paragraph_properties_from_xml
)


def save_xml_structure(docx_path: Path, output_path: Path):
    """
    Сохраняет полную структуру XML документа.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_path: Путь для сохранения JSON файла со структурой
    """
    print(f"Анализ структуры XML: {docx_path}")
    print(f"Результат будет сохранен в: {output_path}\n")
    
    # Извлекаем все элементы из XML
    print("Извлечение элементов из XML...")
    all_elements = extract_all_elements_from_docx_xml_ordered(docx_path)
    print(f"  ✓ Найдено элементов: {len(all_elements)}\n")
    
    # Собираем полную информацию о каждом элементе
    structure = []
    
    for idx, elem in enumerate(all_elements):
        elem_type = elem.get('type', 'unknown')
        xml_pos = elem.get('xml_position', idx)
        text = elem.get('text', '')
        
        element_info = {
            'index': idx,
            'xml_position': xml_pos,
            'type': elem_type,
            'text': text,
            'text_length': len(text),
            'has_image': elem.get('has_image', False),
        }
        
        # Если это параграф, извлекаем все свойства
        if elem_type == 'paragraph':
            properties = extract_paragraph_properties_from_xml(docx_path, xml_pos)
            element_info['properties'] = {
                'font_name': properties.get('font_name'),
                'font_size': properties.get('font_size'),
                'is_bold': properties.get('is_bold', False),
                'is_italic': properties.get('is_italic', False),
                'is_heading_style': properties.get('is_heading_style', False),
                'is_list_item': properties.get('is_list_item', False),
                'list_type': properties.get('list_type'),
                'style': properties.get('style'),
                'alignment': properties.get('alignment'),
                'level': properties.get('level'),
            }
            
            # Проверяем паттерны нумерации
            text_stripped = text.strip()
            numbered_patterns = [
                r'^\d+\.\s+[А-ЯЁA-Z]',  # "1. Заголовок"
                r'^\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1. Заголовок"
                r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1.1. Заголовок"
            ]
            import re
            is_numbered_header = any(re.match(pattern, text_stripped) for pattern in numbered_patterns)
            element_info['is_numbered_header'] = is_numbered_header
            
            # Проверяем, является ли это caption
            if text_stripped.lower().startswith('таблица') or text_stripped.lower().startswith('table'):
                element_info['is_table_caption'] = True
            elif text_stripped.lower().startswith('рис') or text_stripped.lower().startswith('рисунок') or text_stripped.lower().startswith('figure'):
                element_info['is_image_caption'] = True
            
            # Проверяем, заканчивается ли на ":"
            if text_stripped.endswith(':'):
                element_info['ends_with_colon'] = True
        
        # Если это таблица, сохраняем информацию о таблице
        elif elem_type == 'table':
            element_info['table_info'] = {
                'element_exists': elem.get('element') is not None,
            }
        
        structure.append(element_info)
        
        # Прогресс
        if (idx + 1) % 100 == 0:
            print(f"  Обработано: {idx + 1}/{len(all_elements)}")
    
    print(f"\n  ✓ Обработано всех элементов: {len(structure)}\n")
    
    # Статистика
    paragraphs = [e for e in structure if e['type'] == 'paragraph']
    tables = [e for e in structure if e['type'] == 'table']
    
    headers_by_style = [e for e in paragraphs if e.get('properties', {}).get('is_heading_style', False)]
    headers_by_numbering = [e for e in paragraphs if e.get('is_numbered_header', False)]
    list_items = [e for e in paragraphs if e.get('properties', {}).get('is_list_item', False)]
    captions = [e for e in paragraphs if e.get('is_table_caption') or e.get('is_image_caption')]
    ends_with_colon = [e for e in paragraphs if e.get('ends_with_colon', False)]
    
    print("Статистика:")
    print(f"  Всего элементов: {len(structure)}")
    print(f"  Параграфов: {len(paragraphs)}")
    print(f"  Таблиц: {len(tables)}")
    print(f"  Заголовков по стилю: {len(headers_by_style)}")
    print(f"  Заголовков по нумерации: {len(headers_by_numbering)}")
    print(f"  Элементов списка: {len(list_items)}")
    print(f"  Подписей (captions): {len(captions)}")
    print(f"  Заканчивающихся на ':': {len(ends_with_colon)}")
    print()
    
    # Сохраняем структуру
    output_data = {
        'source': str(docx_path),
        'total_elements': len(structure),
        'statistics': {
            'paragraphs': len(paragraphs),
            'tables': len(tables),
            'headers_by_style': len(headers_by_style),
            'headers_by_numbering': len(headers_by_numbering),
            'list_items': len(list_items),
            'captions': len(captions),
            'ends_with_colon': len(ends_with_colon),
        },
        'elements': structure
    }
    
    print(f"Сохранение структуры в {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"  ✓ Структура сохранена: {output_path}")
    print(f"  Размер файла: {output_path.stat().st_size / 1024:.1f} KB")


if __name__ == '__main__':
    import argparse
    import traceback
    
    try:
        parser = argparse.ArgumentParser(description='Сохранение полной структуры XML документа DOCX')
        parser.add_argument('docx_path', type=Path, help='Путь к DOCX файлу')
        parser.add_argument('-o', '--output', type=Path, help='Путь для сохранения JSON (по умолчанию: xml_structure.json в той же директории)')
        
        args = parser.parse_args()
        
        docx_path = Path(args.docx_path)
        if not docx_path.exists():
            print(f"Ошибка: файл не найден: {docx_path}")
            sys.exit(1)
        
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = docx_path.parent / f"{docx_path.stem}_xml_structure.json"
        
        save_xml_structure(docx_path, output_path)
    except Exception as e:
        print(f"Ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
