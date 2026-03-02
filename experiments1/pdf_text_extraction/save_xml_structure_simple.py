"""Скрипт для сохранения полной структуры XML документа DOCX."""
import sys
import json
import re
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_xml_parser import (
    extract_all_elements_from_docx_xml_ordered,
)
from experiments.pdf_text_extraction.docx_complete_pipeline import (
    extract_paragraph_properties_from_xml
)

def main():
    docx_path = Path("experiments/pdf_text_extraction/test_folder/Отчёт_ГОСТ.docx")
    output_path = Path("experiments/pdf_text_extraction/results/complete_pipeline/Отчёт_ГОСТ/structure/xml_structure.json")
    
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
            try:
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
                is_numbered_header = any(re.match(pattern, text_stripped) for pattern in numbered_patterns)
                element_info['is_numbered_header'] = is_numbered_header
                
                # Проверяем, является ли это caption
                text_lower = text_stripped.lower()
                if text_lower.startswith('таблица') or text_lower.startswith('table'):
                    element_info['is_table_caption'] = True
                elif text_lower.startswith('рис') or text_lower.startswith('рисунок') or text_lower.startswith('figure'):
                    element_info['is_image_caption'] = True
                
                # Проверяем, заканчивается ли на ":"
                if text_stripped.endswith(':'):
                    element_info['ends_with_colon'] = True
            except Exception as e:
                element_info['properties_error'] = str(e)
        
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
    main()
