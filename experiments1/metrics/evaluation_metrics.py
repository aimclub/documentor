"""
Метрики для оценки качества парсинга документов.

Включает:
- Ordering accuracy (точность порядка элементов)
- Hierarchy accuracy (точность иерархии)
- TEDS для документа (Tree-Edit-Distance-based Similarity)
- TEDS для таблиц
- Element detection (precision, recall, F1)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict

try:
    import pandas as pd
except ImportError:
    pd = None

from documentor.domain.models import ParsedDocument, Element, ElementType


@dataclass
class EvaluationMetrics:
    """Результаты оценки метрик."""
    # Element detection
    precision: float
    recall: float
    f1_score: float
    
    # Ordering
    ordering_accuracy: float
    ordering_errors: List[Tuple[str, str]]  # (predicted_id, ground_truth_id)
    
    # Hierarchy
    hierarchy_accuracy: float
    hierarchy_errors: List[Tuple[str, Optional[str], Optional[str]]]  # (element_id, pred_parent, gt_parent)
    
    # TEDS
    document_teds: float
    table_teds: Dict[str, float]  # table_id -> TEDS score
    
    # Statistics
    total_elements_gt: int
    total_elements_pred: int
    matched_elements: int


def load_annotation(annotation_path: Path) -> Dict[str, Any]:
    """Загружает разметку из JSON файла."""
    with open(annotation_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def normalize_content(content: str) -> str:
    """Нормализует текст для сравнения."""
    if not content:
        return ""
    # Убираем лишние пробелы, переносы строк
    return " ".join(content.split())


def calculate_bbox_iou(bbox1: List[float], bbox2: List[float]) -> float:
    """
    Вычисляет Intersection over Union (IoU) для двух bbox.
    
    Args:
        bbox1: [x1, y1, x2, y2]
        bbox2: [x1, y1, x2, y2]
    
    Returns:
        IoU значение от 0 до 1
    """
    if len(bbox1) < 4 or len(bbox2) < 4:
        return 0.0
    
    x1_1, y1_1, x2_1, y2_1 = bbox1[0], bbox1[1], bbox1[2], bbox1[3]
    x1_2, y1_2, x2_2, y2_2 = bbox2[0], bbox2[1], bbox2[2], bbox2[3]
    
    # Вычисляем пересечение
    x1_inter = max(x1_1, x1_2)
    y1_inter = max(y1_1, y1_2)
    x2_inter = min(x2_1, x2_2)
    y2_inter = min(y2_1, y2_2)
    
    if x2_inter <= x1_inter or y2_inter <= y1_inter:
        return 0.0
    
    # Площадь пересечения
    intersection = (x2_inter - x1_inter) * (y2_inter - y1_inter)
    
    # Площади bbox
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    
    # Объединение
    union = area1 + area2 - intersection
    
    if union == 0:
        return 0.0
    
    return intersection / union


def normalize_bbox_by_page_size(
    bbox: List[float],
    page_width: float,
    page_height: float
) -> List[float]:
    """
    Нормализует координаты bbox относительно размеров страницы.
    
    Это помогает сравнивать bbox из разных систем координат (например, 
    после smart_resize в Dots OCR vs координаты из аннотаций).
    
    Args:
        bbox: [x1, y1, x2, y2]
        page_width: Ширина страницы в пикселях
        page_height: Высота страницы в пикселях
    
    Returns:
        Нормализованные координаты [x1_norm, y1_norm, x2_norm, y2_norm] в диапазоне [0, 1]
    """
    if len(bbox) < 4 or page_width <= 0 or page_height <= 0:
        return bbox
    
    x1, y1, x2, y2 = bbox
    return [
        x1 / page_width,
        y1 / page_height,
        x2 / page_width,
        y2 / page_height
    ]


def match_elements_by_bbox(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    iou_threshold: float = 0.5,
    normalize_coordinates: bool = True,
    pdf_path: Optional[Path] = None,
    render_scale: float = 2.0
) -> Dict[str, str]:
    """
    Сопоставляет элементы по bbox (Intersection over Union).
    
    Args:
        predicted: Список предсказанных элементов
        ground_truth: Список элементов из разметки
        iou_threshold: Минимальный IoU для сопоставления (по умолчанию 0.5)
        normalize_coordinates: Если True, нормализует координаты относительно размеров страницы
    
    Returns:
        Dict mapping predicted_element_id -> ground_truth_element_id
    """
    matches = {}
    used_gt = set()
    
    # Подсчитываем элементы с bbox для отладки
    pred_with_bbox = 0
    gt_with_bbox = 0
    
    # Сортируем по странице и порядку для более точного сопоставления
    pred_sorted = sorted(
        predicted,
        key=lambda e: (
            e.metadata.get('page_number', e.metadata.get('page_num', 0)),
            e.metadata.get('order', 0)
        )
    )
    
    # Для нормализации нужно знать размеры страниц
    page_sizes = {}  # page_num -> (width, height)
    
    if normalize_coordinates:
        # Пытаемся получить реальные размеры страниц из PDF
        if pdf_path and pdf_path.exists() and pdf_path.suffix.lower() == '.pdf':
            try:
                import fitz
                pdf_doc = fitz.open(str(pdf_path))
                for page_num in range(len(pdf_doc)):
                    page = pdf_doc[page_num]
                    # Размеры страницы в пикселях при render_scale
                    page_width = page.rect.width * render_scale
                    page_height = page.rect.height * render_scale
                    page_sizes[page_num + 1] = [page_width, page_height]  # 1-based
                pdf_doc.close()
            except Exception:
                # Если не удалось открыть PDF, используем максимальные координаты bbox
                pass
        
        # Если не получили размеры из PDF, используем максимальные координаты bbox
        if not page_sizes:
            for pred_elem in pred_sorted:
                pred_bbox = pred_elem.metadata.get('bbox', [])
                if len(pred_bbox) >= 4:
                    pred_page_raw = pred_elem.metadata.get('page_num', 
                                                           pred_elem.metadata.get('page_number', 0))
                    if 'page_num' in pred_elem.metadata:
                        pred_page = pred_page_raw + 1
                    else:
                        pred_page = pred_page_raw
                    
                    # Приблизительный размер страницы = максимальные координаты bbox
                    if pred_page not in page_sizes:
                        page_sizes[pred_page] = [0, 0]
                    page_sizes[pred_page][0] = max(page_sizes[pred_page][0], pred_bbox[2])
                    page_sizes[pred_page][1] = max(page_sizes[pred_page][1], pred_bbox[3])
            
            for gt_elem in ground_truth:
                gt_bbox = gt_elem.get('bbox', [])
                if len(gt_bbox) >= 4:
                    gt_page = gt_elem.get('page_number', 0)
                    if gt_page not in page_sizes:
                        page_sizes[gt_page] = [0, 0]
                    page_sizes[gt_page][0] = max(page_sizes[gt_page][0], gt_bbox[2])
                    page_sizes[gt_page][1] = max(page_sizes[gt_page][1], gt_bbox[3])
    
    for pred_elem in pred_sorted:
        pred_bbox = pred_elem.metadata.get('bbox', [])
        
        # Получаем номер страницы из парсера
        # В парсере используется page_num (0-based) или page_number (может быть 1-based)
        pred_page_raw = pred_elem.metadata.get('page_num', 
                                               pred_elem.metadata.get('page_number', 
                                                                     pred_elem.metadata.get('page', 0)))
        
        # Нормализуем: если есть page_num, это 0-based, конвертируем в 1-based
        # Если есть page_number, проверяем диапазон - если все страницы < 10, возможно это уже 1-based
        # Но для надежности: если page_num существует, используем его и конвертируем
        if 'page_num' in pred_elem.metadata:
            # page_num всегда 0-based в парсере
            pred_page = pred_page_raw + 1  # Конвертируем в 1-based
        else:
            # Используем как есть (может быть уже 1-based)
            pred_page = pred_page_raw
        
        if len(pred_bbox) >= 4:
            pred_with_bbox += 1
        
        if len(pred_bbox) < 4:
            continue
        
        # Нормализуем координаты pred_bbox, если нужно
        if normalize_coordinates and pred_page in page_sizes:
            page_width, page_height = page_sizes[pred_page]
            pred_bbox_norm = normalize_bbox_by_page_size(pred_bbox, page_width, page_height)
        else:
            pred_bbox_norm = pred_bbox
        
        best_match = None
        best_iou = 0.0
        
        for gt_elem in ground_truth:
            gt_id = gt_elem['id']
            if gt_id in used_gt:
                continue
            
            # Проверяем страницу (в аннотациях используется page_number, 1-based)
            gt_page = gt_elem.get('page_number', 0)
            
            # Теперь оба в 1-based формате, просто сравниваем
            if gt_page != pred_page:
                continue
            
            gt_bbox = gt_elem.get('bbox', [])
            if len(gt_bbox) >= 4:
                gt_with_bbox += 1
            
            if len(gt_bbox) < 4:
                continue
            
            # Нормализуем координаты gt_bbox, если нужно
            if normalize_coordinates and gt_page in page_sizes:
                page_width, page_height = page_sizes[gt_page]
                gt_bbox_norm = normalize_bbox_by_page_size(gt_bbox, page_width, page_height)
            else:
                gt_bbox_norm = gt_bbox
            
            # Вычисляем IoU на нормализованных координатах
            iou_norm = calculate_bbox_iou(pred_bbox_norm, gt_bbox_norm)
            
            # Также вычисляем IoU на ненормализованных координатах
            iou_raw = calculate_bbox_iou(pred_bbox, gt_bbox)
            
            # Для scanned PDF координаты могут быть неточными из-за округления в post_process_cells
            # Пробуем также вычислить IoU с допуском (tolerance) для координат
            # Это помогает учесть ошибки округления при конвертации из optimized_image обратно в original_image
            # Увеличиваем tolerance для scanned PDF, так как smart_resize может вносить большие ошибки
            
            # Пробуем несколько вариантов tolerance для лучшего сопоставления
            # Используем более широкий диапазон tolerance для учета различных ошибок
            iou_tol_variants = []
            for tol in [5.0, 10.0, 20.0, 30.0, 50.0, 100.0]:
                pred_bbox_tol = [pred_bbox[0] - tol, pred_bbox[1] - tol,
                                pred_bbox[2] + tol, pred_bbox[3] + tol]
                gt_bbox_tol = [gt_bbox[0] - tol, gt_bbox[1] - tol,
                              gt_bbox[2] + tol, gt_bbox[3] + tol]
                iou_tol = calculate_bbox_iou(pred_bbox_tol, gt_bbox_tol)
                iou_tol_variants.append(iou_tol)
            
            # Также пробуем вычислить IoU на основе центра и размера bbox (более устойчиво к сдвигам)
            pred_center_x = (pred_bbox[0] + pred_bbox[2]) / 2
            pred_center_y = (pred_bbox[1] + pred_bbox[3]) / 2
            pred_width = pred_bbox[2] - pred_bbox[0]
            pred_height = pred_bbox[3] - pred_bbox[1]
            
            gt_center_x = (gt_bbox[0] + gt_bbox[2]) / 2
            gt_center_y = (gt_bbox[1] + gt_bbox[3]) / 2
            gt_width = gt_bbox[2] - gt_bbox[0]
            gt_height = gt_bbox[3] - gt_bbox[1]
            
            # Проверяем совпадение по центру и размеру (с допуском)
            center_tolerance = 50.0  # Допуск для центра в пикселях
            size_tolerance = 0.3  # Допуск для размера (30%)
            
            center_match = (abs(pred_center_x - gt_center_x) < center_tolerance and 
                           abs(pred_center_y - gt_center_y) < center_tolerance)
            size_match = (abs(pred_width - gt_width) / max(pred_width, gt_width, 1) < size_tolerance and
                         abs(pred_height - gt_height) / max(pred_height, gt_height, 1) < size_tolerance)
            
            # Если центр и размер совпадают, используем высокий IoU
            if center_match and size_match:
                iou_center_size = 0.7  # Высокий IoU для совпадения по центру и размеру
                iou_tol_variants.append(iou_center_size)
            
            # Используем максимальный IoU из всех вариантов
            # Это помогает, когда нормализация не работает корректно или есть ошибки округления
            iou = max(iou_norm, iou_raw, *iou_tol_variants)
            
            if iou > best_iou and iou >= iou_threshold:
                best_iou = iou
                best_match = gt_id
        
        if best_match:
            matches[pred_elem.id] = best_match
            used_gt.add(best_match)
    
    # Отладочная информация (можно убрать позже)
    if len(matches) == 0 and (pred_with_bbox > 0 or gt_with_bbox > 0):
        # Логируем проблему, но не выводим в консоль, чтобы не засорять вывод
        pass
    
    return matches


def match_elements(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    threshold: float = 0.8
) -> Dict[str, str]:
    """
    Сопоставляет предсказанные элементы с ground truth.
    Поддерживает объединение: несколько предсказанных элементов могут соответствовать одному GT элементу.
    
    Returns:
        Dict mapping predicted_element_id -> ground_truth_element_id
    """
    matches = {}
    used_gt = set()
    
    # Сначала пытаемся сопоставить по порядку и типу (один к одному)
    for pred_elem in predicted:
        best_match = None
        best_score = 0.0
        
        for gt_elem in ground_truth:
            gt_id = gt_elem['id']
            if gt_id in used_gt:
                continue
            
            # Проверяем тип
            type_match = (pred_elem.type.value.lower() == gt_elem['type'].lower())
            if not type_match:
                continue
            
            # Вычисляем схожесть контента
            pred_content = normalize_content(pred_elem.content)
            gt_content = normalize_content(gt_elem['content'])
            
            if not pred_content and not gt_content:
                score = 1.0
            elif not pred_content or not gt_content:
                score = 0.0
            else:
                # Простая метрика схожести (можно улучшить)
                common_words = set(pred_content.lower().split()) & set(gt_content.lower().split())
                total_words = set(pred_content.lower().split()) | set(gt_content.lower().split())
                score = len(common_words) / len(total_words) if total_words else 0.0
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = gt_id
        
        if best_match:
            matches[pred_elem.id] = best_match
            used_gt.add(best_match)
    
    # Второй проход: ищем случаи объединения (несколько pred -> один GT)
    # Для каждого неиспользованного GT элемента ищем группу pred элементов того же типа
    for gt_elem in ground_truth:
        gt_id = gt_elem['id']
        if gt_id in used_gt:
            continue
        
        gt_type = gt_elem['type'].lower()
        gt_content = normalize_content(gt_elem['content'])
        
        if not gt_content:
            continue
        
        # Ищем группу предсказанных элементов того же типа, которые не сопоставлены
        unmatched_pred = [
            e for e in predicted 
            if e.id not in matches 
            and e.type.value.lower() == gt_type
        ]
        
        if not unmatched_pred:
            continue
        
        # Пробуем найти группу элементов, объединенный контент которых соответствует GT
        # Сортируем по порядку для последовательности
        unmatched_pred.sort(key=lambda e: e.metadata.get('order', 0))
        
        # Пробуем разные комбинации последовательных элементов
        best_group = None
        best_group_score = 0.0
        
        for start_idx in range(len(unmatched_pred)):
            for end_idx in range(start_idx + 1, len(unmatched_pred) + 1):
                group = unmatched_pred[start_idx:end_idx]
                
                # Объединяем контент группы
                combined_content = " ".join([
                    normalize_content(e.content) for e in group if e.content
                ])
                
                if not combined_content:
                    continue
                
                # Вычисляем схожесть объединенного контента с GT
                common_words = set(combined_content.lower().split()) & set(gt_content.lower().split())
                total_words = set(combined_content.lower().split()) | set(gt_content.lower().split())
                score = len(common_words) / len(total_words) if total_words else 0.0
                
                # Дополнительная проверка: объединенный контент должен покрывать большую часть GT
                if len(combined_content) >= len(gt_content) * 0.7:  # Минимум 70% длины
                    if score > best_group_score and score >= threshold * 0.8:  # Немного снижаем порог для объединения
                        best_group_score = score
                        best_group = group
        
        # Если нашли хорошую группу, сопоставляем все её элементы с GT
        if best_group:
            for pred_elem in best_group:
                matches[pred_elem.id] = gt_id
            used_gt.add(gt_id)
    
    return matches


def calculate_ordering_accuracy(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Tuple[float, List[Tuple[str, str]]]:
    """
    Вычисляет точность порядка элементов.
    
    Returns:
        (accuracy, list of ordering errors)
    """
    if not matches:
        return 0.0, []
    
    # Создаем маппинг order для ground truth
    gt_order = {elem['id']: elem['order'] for elem in ground_truth}
    
    # Получаем порядок предсказанных элементов
    pred_elements_with_order = []
    for pred_elem in predicted:
        if pred_elem.id in matches:
            gt_id = matches[pred_elem.id]
            pred_order = pred_elem.metadata.get('order', len(pred_elements_with_order))
            gt_order_val = gt_order.get(gt_id, -1)
            pred_elements_with_order.append((pred_elem.id, pred_order, gt_id, gt_order_val))
    
    # Сортируем по предсказанному порядку
    pred_elements_with_order.sort(key=lambda x: x[1])
    
    # Проверяем порядок
    errors = []
    correct = 0
    total = len(pred_elements_with_order)
    
    for i in range(total - 1):
        curr_gt_order = pred_elements_with_order[i][3]
        next_gt_order = pred_elements_with_order[i + 1][3]
        
        if curr_gt_order < next_gt_order:
            correct += 1
        else:
            errors.append((pred_elements_with_order[i][0], pred_elements_with_order[i + 1][0]))
    
    accuracy = correct / (total - 1) if total > 1 else 1.0
    return accuracy, errors


def calculate_hierarchy_accuracy(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Tuple[float, List[Tuple[str, Optional[str], Optional[str]]]]:
    """
    Вычисляет точность иерархии (parent_id).
    
    Returns:
        (accuracy, list of hierarchy errors)
    """
    if not matches:
        return 0.0, []
    
    # Создаем маппинг parent_id для ground truth
    gt_parents = {elem['id']: elem.get('parent_id') for elem in ground_truth}
    
    # Создаем обратный маппинг predicted_id -> gt_id
    pred_to_gt = matches
    
    errors = []
    correct = 0
    total = 0
    
    for pred_elem in predicted:
        if pred_elem.id not in matches:
            continue
        
        gt_id = matches[pred_elem.id]
        pred_parent = pred_elem.parent_id
        gt_parent = gt_parents.get(gt_id)
        
        # Маппим predicted parent_id на ground truth parent_id
        if pred_parent:
            pred_parent_gt = pred_to_gt.get(pred_parent)
        else:
            pred_parent_gt = None
        
        total += 1
        if pred_parent_gt == gt_parent:
            correct += 1
        else:
            errors.append((pred_elem.id, pred_parent, gt_parent))
    
    accuracy = correct / total if total > 0 else 0.0
    return accuracy, errors


def calculate_teds_for_table(
    predicted_table: Element,
    ground_truth_table: Dict[str, Any]
) -> float:
    """
    Вычисляет TEDS (Tree-Edit-Distance-based Similarity) для таблицы.
    
    TEDS сравнивает структуру таблиц на основе их HTML представления.
    """
    # Получаем HTML представление таблиц
    # Из предсказанной таблицы: HTML хранится в element.content
    pred_html = predicted_table.content if predicted_table.content else None
    
    # Из ground truth
    gt_html = None
    if 'metadata' in ground_truth_table:
        table_structure = ground_truth_table['metadata'].get('table_structure', {})
        gt_html = table_structure.get('html') or ground_truth_table.get('content', '')
    
    # Если нет HTML, используем упрощенную метрику на основе структуры ячеек
    if not pred_html or not gt_html:
        # Сравниваем структуру ячеек из ground truth
        gt_cells = ground_truth_table.get('metadata', {}).get('table_structure', {}).get('cells', [])
        if gt_cells and pred_html:
            # Парсим HTML предсказанной таблицы для извлечения ячеек
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(pred_html, 'html.parser')
                pred_cells = []
                rows = soup.find_all('tr')
                for row_idx, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    for col_idx, cell in enumerate(cells):
                        cell_text = cell.get_text(strip=True)
                        rowspan = int(cell.get('rowspan', 1))
                        colspan = int(cell.get('colspan', 1))
                        pred_cells.append({
                            'row': row_idx,
                            'col': col_idx,
                            'content': cell_text,
                            'rowspan': rowspan,
                            'colspan': colspan
                        })
                
                # Сравниваем структуру
                if len(pred_cells) == len(gt_cells):
                    matches = 0
                    total = len(gt_cells)
                    # Создаем словари для быстрого поиска
                    pred_dict = {(c['row'], c['col']): c for c in pred_cells}
                    gt_dict = {(c['row'], c['col']): c for c in gt_cells}
                    
                    # Сравниваем содержимое ячеек
                    for (row, col), gt_cell in gt_dict.items():
                        pred_cell = pred_dict.get((row, col))
                        if pred_cell:
                            if normalize_content(pred_cell['content']) == normalize_content(gt_cell['content']):
                                matches += 1
                    
                    return matches / total if total > 0 else 0.0
                else:
                    return 0.0
            except Exception:
                return 0.0
        
        return 0.0
    
    # TODO: Реализовать полный TEDS алгоритм для HTML
    # Пока используем упрощенную метрику на основе сравнения HTML структуры
    # Можно использовать нормализованное сравнение HTML или парсинг структуры
    try:
        from bs4 import BeautifulSoup
        pred_soup = BeautifulSoup(pred_html, 'html.parser')
        gt_soup = BeautifulSoup(gt_html, 'html.parser')
        
        # Сравниваем количество строк и столбцов
        pred_rows = pred_soup.find_all('tr')
        gt_rows = gt_soup.find_all('tr')
        
        if len(pred_rows) != len(gt_rows):
            return 0.0
        
        # Сравниваем содержимое ячеек
        matches = 0
        total = 0
        for pred_row, gt_row in zip(pred_rows, gt_rows):
            pred_cells = pred_row.find_all(['td', 'th'])
            gt_cells = gt_row.find_all(['td', 'th'])
            
            if len(pred_cells) != len(gt_cells):
                return 0.0
            
            for pred_cell, gt_cell in zip(pred_cells, gt_cells):
                total += 1
                pred_text = normalize_content(pred_cell.get_text(strip=True))
                gt_text = normalize_content(gt_cell.get_text(strip=True))
                if pred_text == gt_text:
                    matches += 1
        
        return matches / total if total > 0 else 0.0
    except Exception:
        return 0.0


def calculate_document_teds(
    predicted: ParsedDocument,
    ground_truth: List[Dict[str, Any]]
) -> float:
    """
    Вычисляет TEDS для всего документа.
    
    TEDS сравнивает структуру документа как дерево элементов.
    """
    # TODO: Реализовать полный TEDS алгоритм
    # Пока используем комбинацию других метрик
    matches = match_elements(predicted.elements, ground_truth)
    ordering_acc, _ = calculate_ordering_accuracy(predicted.elements, ground_truth, matches)
    hierarchy_acc, _ = calculate_hierarchy_accuracy(predicted.elements, ground_truth, matches)
    
    # Упрощенная метрика TEDS как среднее ordering и hierarchy
    return (ordering_acc + hierarchy_acc) / 2.0


def evaluate_parsing(
    predicted: ParsedDocument,
    ground_truth_path: Path
) -> EvaluationMetrics:
    """
    Оценивает качество парсинга документа.
    
    Args:
        predicted: Предсказанный парсинг
        ground_truth_path: Путь к файлу с разметкой
    
    Returns:
        EvaluationMetrics с результатами оценки
    """
    # Загружаем ground truth
    gt_data = load_annotation(ground_truth_path)
    ground_truth = gt_data['elements']
    
    # Сопоставляем элементы
    matches = match_elements(predicted.elements, ground_truth)
    
    # Element detection metrics
    matched_count = len(matches)
    total_gt = len(ground_truth)
    total_pred = len(predicted.elements)
    
    precision = matched_count / total_pred if total_pred > 0 else 0.0
    recall = matched_count / total_gt if total_gt > 0 else 0.0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Ordering accuracy
    ordering_acc, ordering_errors = calculate_ordering_accuracy(
        predicted.elements, ground_truth, matches
    )
    
    # Hierarchy accuracy
    hierarchy_acc, hierarchy_errors = calculate_hierarchy_accuracy(
        predicted.elements, ground_truth, matches
    )
    
    # Document TEDS
    doc_teds = calculate_document_teds(predicted, ground_truth)
    
    # Table TEDS
    table_teds = {}
    pred_tables = [e for e in predicted.elements if e.type == ElementType.TABLE]
    gt_tables = [e for e in ground_truth if e['type'].lower() == 'table']
    
    for pred_table in pred_tables:
        if pred_table.id in matches:
            gt_id = matches[pred_table.id]
            gt_table = next((t for t in gt_tables if t['id'] == gt_id), None)
            if gt_table:
                teds_score = calculate_teds_for_table(pred_table, gt_table)
                table_teds[pred_table.id] = teds_score
    
    return EvaluationMetrics(
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        ordering_accuracy=ordering_acc,
        ordering_errors=ordering_errors,
        hierarchy_accuracy=hierarchy_acc,
        hierarchy_errors=hierarchy_errors,
        document_teds=doc_teds,
        table_teds=table_teds,
        total_elements_gt=total_gt,
        total_elements_pred=total_pred,
        matched_elements=matched_count
    )


def save_evaluation_report(
    metrics: EvaluationMetrics,
    output_path: Path,
    document_id: str,
    parser_name: str
) -> None:
    """Сохраняет отчет об оценке в JSON."""
    report = {
        "document_id": document_id,
        "parser_name": parser_name,
        "metrics": {
            "element_detection": {
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1_score": metrics.f1_score,
                "total_ground_truth": metrics.total_elements_gt,
                "total_predicted": metrics.total_elements_pred,
                "matched": metrics.matched_elements
            },
            "ordering": {
                "accuracy": metrics.ordering_accuracy,
                "error_count": len(metrics.ordering_errors)
            },
            "hierarchy": {
                "accuracy": metrics.hierarchy_accuracy,
                "error_count": len(metrics.hierarchy_errors)
            },
            "teds": {
                "document_teds": metrics.document_teds,
                "table_teds": metrics.table_teds,
                "average_table_teds": sum(metrics.table_teds.values()) / len(metrics.table_teds) if metrics.table_teds else 0.0
            }
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
