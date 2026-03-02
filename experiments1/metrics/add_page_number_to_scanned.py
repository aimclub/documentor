"""
Скрипт для добавления page_number (1-based) в scanned PDF аннотации
на основе page_num (0-based).
"""

import json
from pathlib import Path


def add_page_number_to_annotation(annotation_path: Path) -> None:
    """
    Добавляет page_number (1-based) для всех элементов в аннотации.
    
    Args:
        annotation_path: Путь к scanned аннотации
    """
    # Загружаем аннотацию
    with open(annotation_path, 'r', encoding='utf-8') as f:
        annotation = json.load(f)
    
    elements = annotation.get('elements', [])
    
    print(f"Обработка: {annotation_path.name}")
    print(f"  Элементов: {len(elements)}")
    
    # Добавляем page_number для всех элементов
    updated_count = 0
    
    for elem in elements:
        page_num = elem.get('page_num')
        
        if page_num is not None:
            # Конвертируем page_num (0-based) в page_number (1-based)
            page_number = page_num + 1
            elem['page_number'] = page_number
            updated_count += 1
        elif 'page_number' not in elem:
            # Если нет ни page_num, ни page_number, устанавливаем по умолчанию
            elem['page_number'] = 1
            elem['page_num'] = 0
            updated_count += 1
    
    print(f"  Обновлено элементов: {updated_count}")
    
    # Сохраняем обновленную аннотацию
    with open(annotation_path, 'w', encoding='utf-8') as f:
        json.dump(annotation, f, ensure_ascii=False, indent=2)
    
    print(f"  Сохранено: {annotation_path}")


def main():
    """Обрабатывает все scanned аннотации."""
    script_dir = Path(__file__).parent
    annotations_dir = script_dir / "annotations"
    
    # Список scanned аннотаций
    scanned_files = [
        "2412.19495v2_scanned_annotation.json",
        "2508.19267v1_scanned_annotation.json",
        "journal-10-67-5-676-697_scanned_annotation.json",
        "journal-10-67-5-721-729_scanned_annotation.json",
    ]
    
    for scanned_name in scanned_files:
        scanned_path = annotations_dir / scanned_name
        
        if not scanned_path.exists():
            print(f"Пропуск: {scanned_name} не найден")
            continue
        
        try:
            add_page_number_to_annotation(scanned_path)
            print()
        except Exception as e:
            print(f"Ошибка при обработке {scanned_name}: {e}\n")
            continue
    
    print("Готово!")


if __name__ == "__main__":
    main()
