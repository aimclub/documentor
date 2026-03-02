import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional

def calculate_bbox_offset(scanned_bbox: List[float], pdf_bbox: List[float]) -> List[float]:
    """Вычисляет смещение bbox: scanned - pdf"""
    if len(scanned_bbox) != 4 or len(pdf_bbox) != 4:
        return None
    return [
        scanned_bbox[0] - pdf_bbox[0],  # x1 offset
        scanned_bbox[1] - pdf_bbox[1],  # y1 offset
        scanned_bbox[2] - pdf_bbox[2],  # x2 offset
        scanned_bbox[3] - pdf_bbox[3]   # y2 offset
    ]

def load_annotation(file_path: str) -> Dict:
    """Загружает аннотацию из JSON файла"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def match_elements(scanned_elements: List[Dict], pdf_elements: List[Dict]) -> Dict[str, Tuple[Dict, Dict]]:
    """Сопоставляет элементы между scanned и pdf версиями по id"""
    scanned_dict = {elem['id']: elem for elem in scanned_elements}
    pdf_dict = {elem['id']: elem for elem in pdf_elements}
    
    matched = {}
    for elem_id in scanned_dict:
        if elem_id in pdf_dict:
            matched[elem_id] = (scanned_dict[elem_id], pdf_dict[elem_id])
    
    return matched

def calculate_offsets_for_pair(scanned_file: str, pdf_file: str, output_file: str):
    """Вычисляет смещения bbox для пары файлов"""
    print(f"Обработка: {os.path.basename(scanned_file)} vs {os.path.basename(pdf_file)}")
    
    scanned_data = load_annotation(scanned_file)
    pdf_data = load_annotation(pdf_file)
    
    scanned_elements = scanned_data.get('elements', [])
    pdf_elements = pdf_data.get('elements', [])
    
    matched = match_elements(scanned_elements, pdf_elements)
    
    offsets = {
        "scanned_file": scanned_file,
        "pdf_file": pdf_file,
        "scanned_document_id": scanned_data.get('document_id'),
        "pdf_document_id": pdf_data.get('document_id'),
        "total_matched_elements": len(matched),
        "total_scanned_elements": len(scanned_elements),
        "total_pdf_elements": len(pdf_elements),
        "element_offsets": []
    }
    
    for elem_id, (scanned_elem, pdf_elem) in matched.items():
        scanned_bbox = scanned_elem.get('bbox')
        pdf_bbox = pdf_elem.get('bbox')
        
        if scanned_bbox and pdf_bbox:
            offset = calculate_bbox_offset(scanned_bbox, pdf_bbox)
            if offset:
                offsets["element_offsets"].append({
                    "element_id": elem_id,
                    "type": scanned_elem.get('type'),
                    "page_number": scanned_elem.get('page_number'),
                    "scanned_bbox": scanned_bbox,
                    "pdf_bbox": pdf_bbox,
                    "offset": offset,
                    "offset_x1": offset[0],
                    "offset_y1": offset[1],
                    "offset_x2": offset[2],
                    "offset_y2": offset[3]
                })
    
    # Вычисляем статистику смещений
    if offsets["element_offsets"]:
        x1_offsets = [o["offset_x1"] for o in offsets["element_offsets"]]
        y1_offsets = [o["offset_y1"] for o in offsets["element_offsets"]]
        x2_offsets = [o["offset_x2"] for o in offsets["element_offsets"]]
        y2_offsets = [o["offset_y2"] for o in offsets["element_offsets"]]
        
        offsets["statistics"] = {
            "mean_offset_x1": sum(x1_offsets) / len(x1_offsets),
            "mean_offset_y1": sum(y1_offsets) / len(y1_offsets),
            "mean_offset_x2": sum(x2_offsets) / len(x2_offsets),
            "mean_offset_y2": sum(y2_offsets) / len(y2_offsets),
            "min_offset_x1": min(x1_offsets),
            "min_offset_y1": min(y1_offsets),
            "min_offset_x2": min(x2_offsets),
            "min_offset_y2": min(y2_offsets),
            "max_offset_x1": max(x1_offsets),
            "max_offset_y1": max(y1_offsets),
            "max_offset_x2": max(x2_offsets),
            "max_offset_y2": max(y2_offsets),
            "std_offset_x1": (sum((x - sum(x1_offsets)/len(x1_offsets))**2 for x in x1_offsets) / len(x1_offsets))**0.5 if len(x1_offsets) > 1 else 0,
            "std_offset_y1": (sum((y - sum(y1_offsets)/len(y1_offsets))**2 for y in y1_offsets) / len(y1_offsets))**0.5 if len(y1_offsets) > 1 else 0,
            "std_offset_x2": (sum((x - sum(x2_offsets)/len(x2_offsets))**2 for x in x2_offsets) / len(x2_offsets))**0.5 if len(x2_offsets) > 1 else 0,
            "std_offset_y2": (sum((y - sum(y2_offsets)/len(y2_offsets))**2 for y in y2_offsets) / len(y2_offsets))**0.5 if len(y2_offsets) > 1 else 0
        }
    
    # Сохраняем результаты
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(offsets, f, ensure_ascii=False, indent=2)
    
    print(f"  Сохранено: {output_file}")
    print(f"  Сопоставлено элементов: {len(matched)}")
    if offsets.get("statistics"):
        stats = offsets["statistics"]
        print(f"  Среднее смещение X: {stats['mean_offset_x1']:.2f}, Y: {stats['mean_offset_y1']:.2f}")
    print()

def main():
    annotations_dir = Path("experiments/metrics/annotations")
    
    # Пары файлов для обработки
    file_pairs = [
        ("2508.19267v1_scanned_annotation.json", "2508.19267v1.pdf_annotation.json"),
        ("2412.19495v2_scanned_annotation.json", "2412.19495v2.pdf_annotation.json"),
        ("journal-10-67-5-676-697_scanned_annotation.json", "journal-10-67-5-676-697.pdf_annotation.json"),
        ("journal-10-67-5-721-729_scanned_annotation.json", "journal-10-67-5-721-729.pdf_annotation.json")
    ]
    
    output_dir = annotations_dir / "bbox_offsets"
    output_dir.mkdir(exist_ok=True)
    
    for scanned_name, pdf_name in file_pairs:
        scanned_path = annotations_dir / scanned_name
        pdf_path = annotations_dir / pdf_name
        
        if not scanned_path.exists():
            print(f"Файл не найден: {scanned_path}")
            continue
        if not pdf_path.exists():
            print(f"Файл не найден: {pdf_path}")
            continue
        
        # Имя выходного файла
        base_name = scanned_name.replace("_scanned_annotation.json", "")
        output_file = output_dir / f"{base_name}_bbox_offset.json"
        
        calculate_offsets_for_pair(str(scanned_path), str(pdf_path), str(output_file))
    
    print("Обработка завершена!")

if __name__ == "__main__":
    main()
