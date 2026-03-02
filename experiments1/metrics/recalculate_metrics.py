"""
Скрипт для пересчета метрик после исключения определенных ошибок.
"""

import json
from pathlib import Path
from typing import Dict, List, Any


def filter_errors(
    analysis_data: Dict[str, Any],
    exclude_content_patterns: List[str],
    exclude_error_types: List[str]
) -> Dict[str, Any]:
    """
    Исключает указанные ошибки из анализа и пересчитывает метрики.
    
    Args:
        analysis_data: Данные анализа из JSON
        exclude_content_patterns: Список паттернов содержимого для исключения
        exclude_error_types: Список типов ошибок для исключения
    
    Returns:
        Обновленные данные анализа
    """
    # Копируем данные
    filtered_data = json.loads(json.dumps(analysis_data))
    
    # Фильтруем hierarchy_errors
    original_hierarchy_errors = filtered_data['hierarchy_errors']
    filtered_hierarchy_errors = []
    
    for error in original_hierarchy_errors:
        # Проверяем тип ошибки
        if error['error_type'] in exclude_error_types:
            continue
        
        # Проверяем содержимое
        content = error.get('element_content_preview', '')
        should_exclude = False
        for pattern in exclude_content_patterns:
            if pattern.lower() in content.lower():
                should_exclude = True
                break
        
        if not should_exclude:
            filtered_hierarchy_errors.append(error)
    
    # Фильтруем structure_errors
    original_structure_errors = filtered_data['structure_errors']
    filtered_structure_errors = []
    
    for error in original_structure_errors:
        # Проверяем тип ошибки
        if error['error_type'] in exclude_error_types:
            continue
        
        # Проверяем содержимое
        content = error.get('element_content_preview', '')
        should_exclude = False
        for pattern in exclude_content_patterns:
            if pattern.lower() in content.lower():
                should_exclude = True
                break
        
        if not should_exclude:
            filtered_structure_errors.append(error)
    
    # Обновляем данные
    filtered_data['hierarchy_errors'] = filtered_hierarchy_errors
    filtered_data['structure_errors'] = filtered_structure_errors
    
    # Пересчитываем статистику
    total_elements = filtered_data['statistics']['total_elements']
    
    # Элементы с правильной иерархией = всего - ошибки иерархии
    # Но нужно учесть, что некоторые ошибки могут быть для одного элемента
    # Упрощенный расчет: считаем уникальные элементы с ошибками
    elements_with_hierarchy_errors = len(set(e['element_id'] for e in filtered_hierarchy_errors))
    elements_with_correct_hierarchy = total_elements - elements_with_hierarchy_errors
    
    # Элементы с правильным порядком
    elements_with_order_errors = len([e for e in filtered_structure_errors 
                                     if e['error_type'] in ['order_mismatch', 'missing', 'extra']])
    elements_with_correct_order = total_elements - elements_with_order_errors
    
    # Обновляем статистику
    filtered_data['statistics']['elements_with_correct_hierarchy'] = elements_with_correct_hierarchy
    filtered_data['statistics']['elements_with_correct_order'] = elements_with_correct_order
    filtered_data['statistics']['hierarchy_accuracy'] = (
        elements_with_correct_hierarchy / total_elements 
        if total_elements > 0 else 0.0
    )
    filtered_data['statistics']['ordering_accuracy'] = (
        elements_with_correct_order / total_elements 
        if total_elements > 0 else 0.0
    )
    
    # Добавляем информацию о фильтрации
    filtered_data['filtering_info'] = {
        'excluded_content_patterns': exclude_content_patterns,
        'excluded_error_types': exclude_error_types,
        'original_hierarchy_errors_count': len(original_hierarchy_errors),
        'filtered_hierarchy_errors_count': len(filtered_hierarchy_errors),
        'original_structure_errors_count': len(original_structure_errors),
        'filtered_structure_errors_count': len(filtered_structure_errors),
        'excluded_hierarchy_errors': len(original_hierarchy_errors) - len(filtered_hierarchy_errors),
        'excluded_structure_errors': len(original_structure_errors) - len(filtered_structure_errors)
    }
    
    return filtered_data


def main():
    # Путь к исходному файлу анализа (от текущей директории скрипта)
    script_dir = Path(__file__).parent
    input_file = script_dir / "teds_analysis/2412.19495v2.pdf_annotation/2412.19495v2_teds_analysis.json"
    
    # Паттерны содержимого для исключения
    exclude_content_patterns = [
        "Carlos Castillo, PhD",
        "arXiv:2412.19495v2"
    ]
    
    # Типы ошибок для исключения
    exclude_error_types = [
        "missing_parent"  # Исключаем все ошибки типа "отсутствует родитель"
    ]
    
    # Загружаем данные
    with open(input_file, 'r', encoding='utf-8') as f:
        analysis_data = json.load(f)
    
    # Фильтруем ошибки
    filtered_data = filter_errors(analysis_data, exclude_content_patterns, exclude_error_types)
    
    # Сохраняем в новый файл
    output_file = input_file.parent / f"{input_file.stem}_filtered.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)
    
    print(f"Оригинальные ошибки иерархии: {len(analysis_data['hierarchy_errors'])}")
    print(f"Отфильтрованные ошибки иерархии: {len(filtered_data['hierarchy_errors'])}")
    print(f"Исключено ошибок иерархии: {filtered_data['filtering_info']['excluded_hierarchy_errors']}")
    print()
    print(f"Оригинальные ошибки структуры: {len(analysis_data['structure_errors'])}")
    print(f"Отфильтрованные ошибки структуры: {len(filtered_data['structure_errors'])}")
    print(f"Исключено ошибок структуры: {filtered_data['filtering_info']['excluded_structure_errors']}")
    print()
    print(f"Оригинальная точность иерархии: {analysis_data['statistics']['hierarchy_accuracy']:.4f}")
    print(f"Новая точность иерархии: {filtered_data['statistics']['hierarchy_accuracy']:.4f}")
    print()
    print(f"Оригинальная точность порядка: {analysis_data['statistics']['ordering_accuracy']:.4f}")
    print(f"Новая точность порядка: {filtered_data['statistics']['ordering_accuracy']:.4f}")
    print()
    print(f"Результаты сохранены в: {output_file}")


if __name__ == "__main__":
    main()
