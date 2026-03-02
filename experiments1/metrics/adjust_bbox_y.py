"""
Скрипт для корректировки Y координат bbox.
"""

import json
from pathlib import Path
from typing import Optional


def adjust_bbox_y(
    annotation_path: Path,
    y_expand: float = 0.0,
    x_offset: float = 0.0,
    y2_adjust: float = 0.0,
    x_expand: float = 0.0,
    y_offset: float = 0.0,
    output_path: Optional[Path] = None
) -> None:
    """
    Расширяет bbox по вертикали и горизонтали, добавляет смещение по X и Y.
    
    Args:
        annotation_path: Путь к аннотации
        y_expand: Расширение по Y (y1 уменьшается на это значение, y2 увеличивается)
        x_offset: Смещение по X (добавляется к x1 и x2)
        y2_adjust: Дополнительное изменение y2 (добавляется к y2 после y_expand)
        x_expand: Расширение по X (x1 уменьшается на это значение, x2 увеличивается)
        y_offset: Смещение по Y (добавляется к y1 и y2, отрицательное значение поднимает вверх)
        output_path: Путь для сохранения (если None, перезаписывает исходный файл)
    """
    # Загружаем аннотацию
    with open(annotation_path, 'r', encoding='utf-8') as f:
        annotation = json.load(f)
    
    print(f"Применяем расширение Y: {y_expand} (y1 -{y_expand}, y2 +{y_expand}), расширение X: {x_expand} (x1 -{x_expand}, x2 +{x_expand}), смещение X: {x_offset}, смещение Y: {y_offset}, корректировка y2: {y2_adjust}")
    
    # Применяем смещение к каждому элементу
    updated_count = 0
    for elem in annotation.get('elements', []):
        bbox = elem.get('bbox', [])
        
        if len(bbox) >= 4:
            # Расширяем bbox: x1 уменьшаем (влево), x2 увеличиваем (вправо), y1 уменьшаем (вверх), y2 увеличиваем (вниз)
            new_bbox = [
                bbox[0] + x_offset - x_expand,      # x1 + смещение - расширение (влево)
                bbox[1] - y_expand + y_offset,      # y1 - расширение (вверх) + смещение Y
                bbox[2] + x_offset + x_expand,      # x2 + смещение + расширение (вправо)
                bbox[3] + y_expand + y2_adjust + y_offset  # y2 + расширение (вниз) + дополнительная корректировка + смещение Y
            ]
            
            elem['bbox'] = new_bbox
            updated_count += 1
    
    print(f"Обновлено bbox для {updated_count} элементов")
    
    # Сохраняем результат
    if output_path is None:
        output_path = annotation_path
    
    # Сохраняем обновленную аннотацию
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(annotation, f, ensure_ascii=False, indent=2)
    
    print(f"Сохранено в: {output_path}")


def main():
    """Основная функция."""
    script_dir = Path(__file__).parent
    annotations_dir = script_dir / "annotations"
    
    scanned_file = "journal-10-67-5-721-729_scanned_annotation.json"
    scanned_path = annotations_dir / scanned_file
    
    if not scanned_path.exists():
        print(f"Файл не найден: {scanned_path}")
        return
    
    print("=" * 80)
    print(f"КОРРЕКТИРОВКА КООРДИНАТ BBOX В {scanned_file}")
    print("=" * 80)
    print()
    
    # Поднять bbox ещё на 8 пикселей вверх (y_offset = -8)
    adjust_bbox_y(scanned_path, y_expand=0.0, x_offset=0.0, y2_adjust=0.0, x_expand=0.0, y_offset=-8.0)


if __name__ == "__main__":
    main()
