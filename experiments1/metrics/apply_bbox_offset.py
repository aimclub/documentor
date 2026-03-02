"""
Скрипт для применения рассчитанного смещения bbox к scanned аннотации.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


def apply_bbox_offset_to_scanned(
    scanned_annotation_path: Path,
    offset_data: Dict[str, Any],
    output_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Применяет смещение bbox к scanned аннотации.
    
    Args:
        scanned_annotation_path: Путь к scanned аннотации
        offset_data: Данные о смещении из bbox_offsets_results.json
        output_path: Путь для сохранения результата (если None, перезаписывает исходный файл)
    
    Returns:
        Обновленная аннотация
    """
    # Загружаем scanned аннотацию
    with open(scanned_annotation_path, 'r', encoding='utf-8') as f:
        scanned_annotation = json.load(f)
    
    # Получаем среднее смещение
    avg_offset = offset_data.get('average_offset', {})
    dx1 = avg_offset.get('x1', 0.0)
    dy1 = avg_offset.get('y1', 0.0)
    dx2 = avg_offset.get('x2', 0.0)
    dy2 = avg_offset.get('y2', 0.0)
    
    print(f"Применяем смещение:")
    print(f"  X1: {dx1:.2f}, Y1: {dy1:.2f}")
    print(f"  X2: {dx2:.2f}, Y2: {dy2:.2f}")
    
    # Применяем смещение к каждому элементу
    updated_count = 0
    for elem in scanned_annotation.get('elements', []):
        bbox = elem.get('bbox', [])
        
        if len(bbox) >= 4:
            # Добавляем смещение к scanned bbox
            # (так как offset = scanned - pdf, то scanned = pdf + offset)
            new_bbox = [
                bbox[0] + dx1,
                bbox[1] + dy1,
                bbox[2] + dx2,
                bbox[3] + dy2
            ]
            
            elem['bbox'] = new_bbox
            updated_count += 1
    
    print(f"Обновлено bbox для {updated_count} элементов")
    
    # Сохраняем результат
    if output_path is None:
        output_path = scanned_annotation_path
    
    # Создаем резервную копию
    backup_path = scanned_annotation_path.with_suffix('.json.backup')
    if not backup_path.exists():
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(scanned_annotation, f, ensure_ascii=False, indent=2)
        print(f"Создана резервная копия: {backup_path}")
    
    # Сохраняем обновленную аннотацию
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(scanned_annotation, f, ensure_ascii=False, indent=2)
    
    print(f"Сохранено в: {output_path}")
    
    return scanned_annotation


def main():
    """Основная функция."""
    script_dir = Path(__file__).parent
    annotations_dir = script_dir / "annotations"
    offsets_file = script_dir / "bbox_offsets_results.json"
    
    # Загружаем данные о смещениях
    with open(offsets_file, 'r', encoding='utf-8') as f:
        offsets_data = json.load(f)
    
    # Файл для обработки
    scanned_file = "journal-10-67-5-721-729_scanned_annotation.json"
    pdf_file_key = "journal-10-67-5-721-729.pdf_annotation.json"
    
    scanned_path = annotations_dir / scanned_file
    
    if not scanned_path.exists():
        print(f"Файл не найден: {scanned_path}")
        return
    
    if pdf_file_key not in offsets_data:
        print(f"Данные о смещении не найдены для: {pdf_file_key}")
        return
    
    offset_data = offsets_data[pdf_file_key]
    
    print("=" * 80)
    print(f"ПРИМЕНЕНИЕ СМЕЩЕНИЯ BBOX К {scanned_file}")
    print("=" * 80)
    print()
    
    apply_bbox_offset_to_scanned(scanned_path, offset_data)


if __name__ == "__main__":
    main()
