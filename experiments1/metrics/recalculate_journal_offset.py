"""
Скрипт для пересчета смещения bbox для journal-10-67-5-676-697.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import statistics


def normalize_text(text: str) -> str:
    """Нормализует текст для сравнения."""
    if not text:
        return ""
    return text.strip().lower().replace("\n", " ").replace("\r", " ")


def find_matching_scanned_element(
    pdf_elem: Dict[str, Any],
    scanned_elements: List[Dict[str, Any]],
    used_indices: set
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """
    Находит соответствующий элемент в scanned аннотации для PDF элемента.
    
    Returns:
        Tuple (index, element) или None
    """
    pdf_type = pdf_elem.get('type', '').lower()
    pdf_content = normalize_text(pdf_elem.get('content', ''))
    pdf_page = pdf_elem.get('page_number') or pdf_elem.get('page_num', 0)
    if pdf_page == 0 and 'page_num' in pdf_elem:
        pdf_page = pdf_elem.get('page_num', 0) + 1
    
    best_match = None
    best_score = 0.0
    best_idx = None
    
    for idx, scanned_elem in enumerate(scanned_elements):
        if idx in used_indices:
            continue
        
        scanned_type = scanned_elem.get('type', '').lower()
        scanned_content = normalize_text(scanned_elem.get('content', ''))
        scanned_page = scanned_elem.get('page_number') or scanned_elem.get('page_num', 0)
        if scanned_page == 0 and 'page_num' in scanned_elem:
            scanned_page = scanned_elem.get('page_num', 0) + 1
        
        # Вычисляем score совпадения
        score = 0.0
        
        # Тип должен совпадать
        if pdf_type == scanned_type:
            score += 0.3
        elif pdf_type in ['text', 'header_1', 'header_2'] and scanned_type in ['text', 'header_1', 'header_2']:
            score += 0.1
        else:
            continue
        
        # Страница должна совпадать
        if pdf_page == scanned_page:
            score += 0.2
        elif abs(pdf_page - scanned_page) <= 1:
            score += 0.1
        else:
            continue  # Строже проверяем страницы
        
        # Содержимое должно совпадать
        if pdf_content and scanned_content:
            if pdf_content == scanned_content:
                score += 0.5
            elif pdf_content in scanned_content or scanned_content in pdf_content:
                score += 0.3
            elif len(pdf_content) > 20 and len(scanned_content) > 20:
                if pdf_content[:50] == scanned_content[:50]:
                    score += 0.2
                elif pdf_content[:30] == scanned_content[:30]:
                    score += 0.15
                elif pdf_content[:20] == scanned_content[:20]:
                    score += 0.1
        
        if score > best_score:
            best_score = score
            best_match = scanned_elem
            best_idx = idx
    
    # Минимальный порог для совпадения
    if best_score >= 0.3:
        return (best_idx, best_match)
    
    return None


def calculate_bbox_offset(
    pdf_elements: List[Dict[str, Any]],
    scanned_elements: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Вычисляет среднее смещение bbox между PDF и scanned аннотациями.
    
    Returns:
        Dict с результатами расчета или None
    """
    offsets = []
    
    # Сортируем для сопоставления
    pdf_sorted = sorted(pdf_elements, key=lambda e: (e.get('page_number', e.get('page_num', 0)), e.get('order', 0)))
    scanned_sorted = sorted(scanned_elements, key=lambda e: (e.get('page_number', e.get('page_num', 0)), e.get('order', 0)))
    
    scanned_matched = set()
    
    print(f"\nДетальное сопоставление элементов:")
    print(f"{'PDF order':<10} {'PDF page':<10} {'PDF type':<15} {'Scanned order':<15} {'Scanned page':<15} {'Offset X1':<12} {'Offset Y1':<12}")
    print("-" * 100)
    
    for pdf_elem in pdf_sorted:
        match = find_matching_scanned_element(pdf_elem, scanned_sorted, scanned_matched)
        
        if match:
            scanned_idx, scanned_elem = match
            scanned_matched.add(scanned_idx)
            
            pdf_bbox = pdf_elem.get('bbox', [])
            scanned_bbox = scanned_elem.get('bbox', [])
            
            if len(pdf_bbox) >= 4 and len(scanned_bbox) >= 4:
                # Вычисляем смещение: scanned - pdf
                offset_x1 = scanned_bbox[0] - pdf_bbox[0]
                offset_y1 = scanned_bbox[1] - pdf_bbox[1]
                offset_x2 = scanned_bbox[2] - pdf_bbox[2]
                offset_y2 = scanned_bbox[3] - pdf_bbox[3]
                
                pdf_order = pdf_elem.get('order', 0)
                pdf_page = pdf_elem.get('page_number') or pdf_elem.get('page_num', 0)
                scanned_order = scanned_elem.get('order', 0)
                scanned_page = scanned_elem.get('page_number') or scanned_elem.get('page_num', 0)
                pdf_type = pdf_elem.get('type', '')
                
                print(f"{pdf_order:<10} {pdf_page:<10} {pdf_type:<15} {scanned_order:<15} {scanned_page:<15} {offset_x1:<12.2f} {offset_y1:<12.2f}")
                
                offset = {
                    'x1': offset_x1,
                    'y1': offset_y1,
                    'x2': offset_x2,
                    'y2': offset_y2,
                    'pdf_bbox': pdf_bbox,
                    'scanned_bbox': scanned_bbox,
                    'pdf_type': pdf_elem.get('type', ''),
                    'pdf_content_preview': (pdf_elem.get('content', '') or '')[:50],
                    'pdf_order': pdf_order,
                    'scanned_order': scanned_order
                }
                offsets.append(offset)
    
    if not offsets:
        return None
    
    # Вычисляем среднее смещение
    avg_offset = {
        'x1': sum(o['x1'] for o in offsets) / len(offsets),
        'y1': sum(o['y1'] for o in offsets) / len(offsets),
        'x2': sum(o['x2'] for o in offsets) / len(offsets),
        'y2': sum(o['y2'] for o in offsets) / len(offsets)
    }
    
    # Вычисляем стандартное отклонение
    std_dev = {
        'x1': statistics.stdev([o['x1'] for o in offsets]) if len(offsets) > 1 else 0.0,
        'y1': statistics.stdev([o['y1'] for o in offsets]) if len(offsets) > 1 else 0.0,
        'x2': statistics.stdev([o['x2'] for o in offsets]) if len(offsets) > 1 else 0.0,
        'y2': statistics.stdev([o['y2'] for o in offsets]) if len(offsets) > 1 else 0.0
    }
    
    # Минимум и максимум
    min_offset = {
        'x1': min(o['x1'] for o in offsets),
        'y1': min(o['y1'] for o in offsets),
        'x2': min(o['x2'] for o in offsets),
        'y2': min(o['y2'] for o in offsets)
    }
    
    max_offset = {
        'x1': max(o['x1'] for o in offsets),
        'y1': max(o['y1'] for o in offsets),
        'x2': max(o['x2'] for o in offsets),
        'y2': max(o['y2'] for o in offsets)
    }
    
    return {
        'average_offset': avg_offset,
        'std_deviation': std_dev,
        'min_offset': min_offset,
        'max_offset': max_offset,
        'matched_elements_count': len(offsets),
        'all_offsets': offsets
    }


def main():
    """Основная функция."""
    script_dir = Path(__file__).parent
    annotations_dir = script_dir / "annotations"
    
    pdf_file = "journal-10-67-5-676-697.pdf_annotation.json"
    scanned_file = "journal-10-67-5-676-697_scanned_annotation.json"
    
    pdf_path = annotations_dir / pdf_file
    scanned_path = annotations_dir / scanned_file
    
    print("=" * 80)
    print("ПЕРЕСЧЕТ СМЕЩЕНИЙ BBOX ДЛЯ journal-10-67-5-676-697")
    print("=" * 80)
    print()
    
    if not pdf_path.exists():
        print(f"Ошибка: {pdf_file} не найден")
        return
    
    if not scanned_path.exists():
        print(f"Ошибка: {scanned_file} не найден")
        return
    
    print(f"Обработка: {pdf_file} <-> {scanned_file}")
    
    # Загружаем аннотации
    with open(pdf_path, 'r', encoding='utf-8') as f:
        pdf_annotation = json.load(f)
    
    with open(scanned_path, 'r', encoding='utf-8') as f:
        scanned_annotation = json.load(f)
    
    pdf_elements = pdf_annotation.get('elements', [])
    scanned_elements = scanned_annotation.get('elements', [])
    
    print(f"PDF элементов: {len(pdf_elements)}")
    print(f"Scanned элементов: {len(scanned_elements)}")
    print()
    
    try:
        # Вычисляем смещение
        offset_result = calculate_bbox_offset(pdf_elements, scanned_elements)
    except Exception as e:
        print(f"Ошибка при расчете смещения: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if offset_result:
        avg = offset_result['average_offset']
        std = offset_result['std_deviation']
        min_off = offset_result['min_offset']
        max_off = offset_result['max_offset']
        matched = offset_result['matched_elements_count']
        
        print()
        print("=" * 80)
        print("РЕЗУЛЬТАТЫ РАСЧЕТА СМЕЩЕНИЙ")
        print("=" * 80)
        print(f"Сопоставлено элементов: {matched}")
        print(f"Среднее смещение:")
        print(f"  X1: {avg['x1']:.2f} (std: {std['x1']:.2f}, min: {min_off['x1']:.2f}, max: {max_off['x1']:.2f})")
        print(f"  Y1: {avg['y1']:.2f} (std: {std['y1']:.2f}, min: {min_off['y1']:.2f}, max: {max_off['y1']:.2f})")
        print(f"  X2: {avg['x2']:.2f} (std: {std['x2']:.2f}, min: {min_off['x2']:.2f}, max: {max_off['x2']:.2f})")
        print(f"  Y2: {avg['y2']:.2f} (std: {std['y2']:.2f}, min: {min_off['y2']:.2f}, max: {max_off['y2']:.2f})")
        
        # Обновляем результаты в основном файле
        results_path = script_dir / "bbox_offsets_results.json"
        if results_path.exists():
            with open(results_path, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
        else:
            all_results = {}
        
        all_results[pdf_file] = {
            'pdf_file': pdf_file,
            'scanned_file': scanned_file,
            'pdf_elements_count': len(pdf_elements),
            'scanned_elements_count': len(scanned_elements),
            **offset_result
        }
        
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        
        print(f"\nРезультаты обновлены в: {results_path}")
    else:
        print("Не удалось вычислить смещение (нет сопоставленных элементов)")


if __name__ == "__main__":
    main()
