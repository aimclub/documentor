"""
Пайплайн для оценки качества парсинга документов.

Обрабатывает все размеченные файлы и вычисляет метрики:
- CER (Character Error Rate)
- WER (Word Error Rate)
- Время на страницу
- Время на документ
- TEDS для документа
- TEDS для иерархии
- Точность детекции классов
"""

import json
import time
import io
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF

from documentor import Pipeline
from documentor.domain.models import ParsedDocument, Element, ElementType
from documentor.processing.parsers.docx.converter import convert_docx_to_pdf
from langchain_core.documents import Document

import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

from evaluation_metrics import (
    load_annotation,
    match_elements,
    calculate_ordering_accuracy,
    calculate_hierarchy_accuracy,
    normalize_content
)
from visualize_comparison import visualize_comparison
from teds_analysis import create_teds_visualizations_and_report


def _create_docx_comparison_images(
    docx_path: Path,
    predicted: List[Element],
    output_dir: Path,
    render_scale: float = 2.0
) -> int:
    """
    Создает комбинированные изображения для DOCX файлов: оригинал + с разметкой модели.
    
    Args:
        docx_path: Путь к DOCX файлу
        predicted: Список предсказанных элементов
        output_dir: Директория для сохранения изображений
        render_scale: Масштаб рендеринга
        
    Returns:
        Количество сохраненных изображений
    """
    if not docx_path.exists():
        print(f"  [ERROR] DOCX файл не существует: {docx_path}")
        return 0
    
    temp_pdf_path = None
    try:
        # Создаем временный PDF файл
        temp_dir = tempfile.gettempdir()
        temp_pdf_path = Path(temp_dir) / f"{docx_path.stem}_temp_{int(time.time())}.pdf"
        
        # Конвертируем DOCX в PDF
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        
        if not temp_pdf_path.exists():
            print(f"  [ERROR] Не удалось конвертировать DOCX в PDF")
            return 0
        
        # Открываем PDF
        pdf_doc = fitz.open(str(temp_pdf_path))
        total_pages = len(pdf_doc)
        
        if total_pages == 0:
            pdf_doc.close()
            return 0
        
        saved_count = 0
        scale = render_scale
        
        # Группируем элементы по страницам
        pred_by_page = defaultdict(list)
        for pred_elem in predicted:
            # В predicted может быть page_num (0-based) или page_number (1-based)
            page_num = pred_elem.metadata.get('page_num')
            if page_num is None:
                page_num = pred_elem.metadata.get('page_number', 1) - 1  # Конвертируем в 0-based
            if 'bbox' in pred_elem.metadata and len(pred_elem.metadata['bbox']) >= 4:
                pred_by_page[page_num].append(pred_elem)
        
        # Цвета для типов элементов
        element_colors = {
            'title': (255, 0, 0),
            'header_1': (255, 102, 0),
            'header_2': (255, 153, 0),
            'header_3': (255, 204, 0),
            'header_4': (255, 255, 0),
            'header_5': (204, 255, 0),
            'header_6': (153, 255, 0),
            'text': (0, 204, 255),
            'table': (153, 0, 255),
            'image': (255, 0, 255),
            'list_item': (0, 255, 153),
            'caption': (255, 0, 153),
            'formula': (0, 153, 255),
            'link': (0, 255, 0),
            'code_block': (102, 102, 102),
        }
        
        for page_num in range(total_pages):
            try:
                page = pdf_doc[page_num]
                
                # Рендерим оригинальную страницу
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat)
                
                # Конвертируем в PIL Image
                img_data = pix.tobytes("ppm")
                original_img = Image.open(io.BytesIO(img_data))
                
                # Создаем копию для рисования разметки
                annotated_img = original_img.copy()
                draw = ImageDraw.Draw(annotated_img)
                
                # Получаем размеры PDF страницы
                pdf_width_pts = page.rect.width
                pdf_height_pts = page.rect.height
                
                # Коэффициенты масштабирования для bbox
                scale_x = scale / render_scale
                scale_y = scale / render_scale
                
                # Получаем элементы для текущей страницы
                page_elements = pred_by_page.get(page_num, [])
                
                # Рисуем bbox для каждого элемента
                for pred_elem in page_elements:
                    bbox = pred_elem.metadata.get('bbox', [])
                    if not bbox or len(bbox) < 4:
                        continue
                    
                    x0_bbox, y0_bbox, x1_bbox, y1_bbox = bbox
                    
                    # Конвертируем координаты
                    x0 = x0_bbox * scale_x
                    y0 = y0_bbox * scale_y
                    x1 = x1_bbox * scale_x
                    y1 = y1_bbox * scale_y
                    
                    # Ограничиваем координаты
                    x0 = max(0, min(x0, annotated_img.width))
                    y0 = max(0, min(y0, annotated_img.height))
                    x1 = max(0, min(x1, annotated_img.width))
                    y1 = max(0, min(y1, annotated_img.height))
                    
                    if x1 <= x0 or y1 <= y0:
                        continue
                    
                    # Получаем цвет для типа элемента
                    elem_type = pred_elem.type.value.lower()
                    color = element_colors.get(elem_type, (255, 0, 0))
                    
                    # Рисуем прямоугольник
                    draw.rectangle(
                        [int(x0), int(y0), int(x1), int(y1)],
                        outline=color,
                        width=3
                    )
                    
                    # Добавляем подпись
                    label = f"{elem_type} ({pred_elem.id})"
                    try:
                        font = ImageFont.truetype("arial.ttf", 14)
                    except:
                        try:
                            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
                        except:
                            font = ImageFont.load_default()
                    
                    # Фон для текста
                    text_bbox = draw.textbbox((int(x0), int(y0) - 18), label, font=font)
                    draw.rectangle(text_bbox, fill=color, outline=color)
                    draw.text((int(x0), int(y0) - 18), label, fill=(255, 255, 255), font=font)
                
                # Создаем комбинированное изображение: оригинал слева, с разметкой справа
                img_width = original_img.width
                img_height = original_img.height
                
                # Создаем новое изображение для комбинации
                combined_img = Image.new('RGB', (img_width * 2, img_height), (255, 255, 255))
                combined_img.paste(original_img, (0, 0))
                combined_img.paste(annotated_img, (img_width, 0))
                
                # Добавляем подписи
                draw_combined = ImageDraw.Draw(combined_img)
                try:
                    title_font = ImageFont.truetype("arial.ttf", 20)
                except:
                    try:
                        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
                    except:
                        title_font = ImageFont.load_default()
                
                # Подпись для оригинального изображения
                draw_combined.text((10, 10), "Оригинал", fill=(0, 0, 0), font=title_font)
                # Подпись для изображения с разметкой
                draw_combined.text((img_width + 10, 10), "Разметка модели", fill=(0, 0, 0), font=title_font)
                
                # Сохраняем комбинированное изображение
                output_image_path = output_dir / f"page_{page_num + 1:03d}_comparison.png"
                combined_img.save(output_image_path, "PNG")
                saved_count += 1
                
            except Exception as e:
                # Продолжаем обработку других страниц при ошибке
                print(f"  [ERROR] Ошибка при обработке страницы {page_num + 1}: {e}")
                continue
        
        pdf_doc.close()
        return saved_count
        
    except Exception as e:
        print(f"  [ERROR] Критическая ошибка при создании изображений для DOCX: {e}")
        return 0
    finally:
        # Удаляем временный PDF файл
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
            except:
                pass


def calculate_cer(reference: str, hypothesis: str) -> float:
    """
    Вычисляет Character Error Rate (CER).
    
    Args:
        reference: Эталонный текст
        hypothesis: Распознанный текст
    
    Returns:
        CER (0.0 = идеально, 1.0 = все символы неверны)
    """
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    # Нормализуем тексты
    ref_norm = normalize_content(reference).lower()
    hyp_norm = normalize_content(hypothesis).lower()
    
    if not ref_norm:
        return 1.0 if hyp_norm else 0.0
    
    # Простая реализация расстояния Левенштейна для символов
    ref_chars = list(ref_norm)
    hyp_chars = list(hyp_norm)
    
    m, n = len(ref_chars), len(hyp_chars)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_chars[i-1] == hyp_chars[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    # Нормализуем по длине эталона
    return min(1.0, edit_distance / len(ref_chars))


def calculate_wer(reference: str, hypothesis: str) -> float:
    """
    Вычисляет Word Error Rate (WER).
    
    Args:
        reference: Эталонный текст
        hypothesis: Распознанный текст
    
    Returns:
        WER (0.0 = идеально, 1.0 = все слова неверны)
    """
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    # Нормализуем тексты
    ref_norm = normalize_content(reference).lower()
    hyp_norm = normalize_content(hypothesis).lower()
    
    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    
    # Простая реализация расстояния Левенштейна для слов
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    # Нормализуем по количеству слов в эталоне
    return min(1.0, edit_distance / len(ref_words))


def calculate_hierarchy_teds(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> float:
    """
    Вычисляет TEDS для иерархии элементов.
    
    Сравнивает структуру дерева элементов (parent-child отношения).
    Игнорирует ошибки родителей для HEADER_1.
    """
    if not matches:
        return 0.0
    
    # Создаём словари для быстрого доступа
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    # Создаём обратный маппинг (gt_id -> pred_id)
    gt_to_pred = {gt_id: pred_id for pred_id, gt_id in matches.items()}
    
    # Считаем совпадения в иерархии
    correct_parents = 0
    total_checked = 0
    
    for pred_id, gt_id in matches.items():
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        # Игнорируем ошибки родителей для HEADER_1
        if gt_elem.get('type', '').lower() == 'header_1':
            continue
        
        # parent_id хранится как атрибут Element
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        total_checked += 1
        
        # Сопоставляем родителей через matches
        if pred_parent and gt_parent:
            # Проверяем, сопоставлен ли pred_parent с gt_parent
            pred_parent_gt = gt_to_pred.get(pred_parent)  # Получаем gt_id для pred_parent
            if pred_parent_gt is None:
                # pred_parent не сопоставлен, ищем напрямую
                for p_id, g_id in matches.items():
                    if p_id == pred_parent:
                        pred_parent_gt = g_id
                        break
            
            if pred_parent_gt == gt_parent:
                correct_parents += 1
        elif not pred_parent and not gt_parent:
            # Оба без родителей - правильно
            correct_parents += 1
    
    if total_checked == 0:
        return 1.0  # Нет элементов для проверки
    
    return correct_parents / total_checked


def calculate_class_detection_accuracy(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Dict[str, Dict[str, float]]:
    """
    Вычисляет точность детекции классов.
    
    Returns:
        Dict с метриками для каждого класса:
        {
            'class_name': {
                'precision': float,
                'recall': float,
                'f1': float,
                'count_gt': int,
                'count_pred': int,
                'count_matched': int
            }
        }
    """
    # Группируем элементы по классам
    gt_by_class = defaultdict(list)
    pred_by_class = defaultdict(list)
    matched_by_class = defaultdict(int)
    
    for gt_elem in ground_truth:
        elem_type = gt_elem.get('type', '').lower()
        gt_by_class[elem_type].append(gt_elem['id'])
    
    for pred_elem in predicted:
        elem_type = pred_elem.type.value.lower()
        pred_by_class[elem_type].append(pred_elem.id)
    
    # Считаем совпадения по классам
    # Важно: учитываем, что несколько pred элементов могут соответствовать одному GT элементу
    # Для правильного подсчета recall нужно считать уникальные GT элементы, а не pred элементы
    matched_gt_by_class = defaultdict(set)  # class_name -> set of gt_ids
    
    for pred_id, gt_id in matches.items():
        pred_elem = next((e for e in predicted if e.id == pred_id), None)
        gt_elem = next((e for e in ground_truth if e['id'] == gt_id), None)
        
        if pred_elem and gt_elem:
            pred_type = pred_elem.type.value.lower()
            gt_type = gt_elem.get('type', '').lower()
            
            if pred_type == gt_type:
                # Добавляем GT элемент в множество для этого класса
                matched_gt_by_class[pred_type].add(gt_id)
                # Также считаем pred элемент для precision
                matched_by_class[pred_type] += 1
    
    # Вычисляем метрики для каждого класса
    results = {}
    
    all_classes = set(list(gt_by_class.keys()) + list(pred_by_class.keys()))
    
    for class_name in all_classes:
        count_gt = len(gt_by_class[class_name])
        count_pred = len(pred_by_class[class_name])
        # Для precision считаем количество сопоставленных pred элементов
        count_matched_pred = matched_by_class[class_name]
        # Для recall считаем количество уникальных сопоставленных GT элементов
        count_matched_gt = len(matched_gt_by_class[class_name])
        
        precision = count_matched_pred / count_pred if count_pred > 0 else 0.0
        recall = count_matched_gt / count_gt if count_gt > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        # Для вывода используем count_matched_gt (количество уникальных GT элементов)
        count_matched = count_matched_gt
        
        results[class_name] = {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'count_gt': count_gt,
            'count_pred': count_pred,
            'count_matched': count_matched
        }
    
    return results


def calculate_type_substitutions(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Dict[str, Any]:
    """
    Вычисляет метрики по заменам типов элементов.
    
    Returns:
        Dict с информацией о заменах:
        {
            'total_substitutions': int,  # Общее количество замен
            'substitution_rate': float,  # Доля замен от общего количества сопоставленных элементов
            'substitutions_by_type': Dict[str, Dict[str, int]],  # Замены по типам: gt_type -> {pred_type: count}
            'substitution_matrix': Dict[str, Dict[str, int]]  # Матрица замен: gt_type -> {pred_type: count}
        }
    """
    substitutions_by_type = defaultdict(lambda: defaultdict(int))
    total_substitutions = 0
    total_matched = len(matches)
    
    # Создаем словари для быстрого доступа
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    # Группируем pred элементы по их GT соответствию (для обработки объединений)
    pred_by_gt = defaultdict(list)
    for pred_id, gt_id in matches.items():
        pred_by_gt[gt_id].append(pred_id)
    
    # Обрабатываем каждый GT элемент
    for gt_id, pred_ids in pred_by_gt.items():
        gt_elem = gt_dict.get(gt_id)
        if not gt_elem:
            continue
        
        gt_type = gt_elem.get('type', '').lower()
        
        # Для объединенных элементов берем тип первого pred элемента
        if pred_ids:
            first_pred_id = pred_ids[0]
            pred_elem = pred_dict.get(first_pred_id)
            if pred_elem:
                pred_type = pred_elem.type.value.lower()
                
                if pred_type != gt_type:
                    total_substitutions += 1
                    substitutions_by_type[gt_type][pred_type] += 1
    
    substitution_rate = total_substitutions / total_matched if total_matched > 0 else 0.0
    
    return {
        'total_substitutions': total_substitutions,
        'substitution_rate': substitution_rate,
        'substitutions_by_type': dict(substitutions_by_type),
        'substitution_matrix': dict(substitutions_by_type)
    }


def calculate_header_level_substitutions(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Dict[str, Any]:
    """
    Вычисляет метрики по заменам уровней заголовков.
    
    Считает только заголовки (header_1 - header_6) и анализирует замены одного уровня на другой.
    
    Returns:
        Dict с информацией о заменах уровней заголовков:
        {
            'total_header_substitutions': int,  # Общее количество замен уровней заголовков
            'header_substitution_rate': float,  # Доля замен от общего количества заголовков
            'substitutions_by_level': Dict[str, Dict[str, int]],  # Замены по уровням: gt_level -> {pred_level: count}
            'header_count_gt': Dict[str, int],  # Количество заголовков каждого уровня в GT
            'header_count_pred': Dict[str, int],  # Количество заголовков каждого уровня в предсказаниях
            'header_count_matched': Dict[str, int]  # Количество сопоставленных заголовков каждого уровня
        }
    """
    substitutions_by_level = defaultdict(lambda: defaultdict(int))
    header_count_gt = defaultdict(int)
    header_count_pred = defaultdict(int)
    header_count_matched = defaultdict(int)
    total_header_substitutions = 0
    total_headers_matched = 0
    
    # Создаем словари для быстрого доступа
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    # Подсчитываем заголовки в GT и предсказаниях
    for gt_elem in ground_truth:
        gt_type = gt_elem.get('type', '').lower()
        if gt_type.startswith('header_'):
            header_count_gt[gt_type] += 1
    
    for pred_elem in predicted:
        pred_type = pred_elem.type.value.lower()
        if pred_type.startswith('header_'):
            header_count_pred[pred_type] += 1
    
    # Группируем pred элементы по их GT соответствию
    pred_by_gt = defaultdict(list)
    for pred_id, gt_id in matches.items():
        pred_by_gt[gt_id].append(pred_id)
    
    # Обрабатываем каждый GT элемент
    for gt_id, pred_ids in pred_by_gt.items():
        gt_elem = gt_dict.get(gt_id)
        if not gt_elem:
            continue
        
        gt_type = gt_elem.get('type', '').lower()
        
        # Интересуют только заголовки
        if not gt_type.startswith('header_'):
            continue
        
        total_headers_matched += 1
        header_count_matched[gt_type] += 1
        
        # Для объединенных элементов берем тип первого pred элемента
        if pred_ids:
            first_pred_id = pred_ids[0]
            pred_elem = pred_dict.get(first_pred_id)
            if pred_elem:
                pred_type = pred_elem.type.value.lower()
                
                # Если pred тоже заголовок, проверяем уровень
                if pred_type.startswith('header_'):
                    if pred_type != gt_type:
                        total_header_substitutions += 1
                        substitutions_by_level[gt_type][pred_type] += 1
    
    header_substitution_rate = total_header_substitutions / total_headers_matched if total_headers_matched > 0 else 0.0
    
    return {
        'total_header_substitutions': total_header_substitutions,
        'header_substitution_rate': header_substitution_rate,
        'substitutions_by_level': dict(substitutions_by_level),
        'header_count_gt': dict(header_count_gt),
        'header_count_pred': dict(header_count_pred),
        'header_count_matched': dict(header_count_matched)
    }


@dataclass
class DocumentErrors:
    """Детальная информация об ошибках для анализа."""
    # Не найденные элементы (есть в GT, но нет в предсказаниях)
    missing_elements: List[Dict[str, Any]] = field(default_factory=list)
    
    # Лишние элементы (есть в предсказаниях, но нет в GT)
    extra_elements: List[Dict[str, Any]] = field(default_factory=list)
    
    # Ошибки в порядке элементов
    ordering_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # Ошибки в иерархии (неправильные parent_id)
    hierarchy_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # Элементы с высоким CER/WER
    high_error_elements: List[Dict[str, Any]] = field(default_factory=list)
    
    # Элементы с неправильным типом
    type_mismatch_elements: List[Dict[str, Any]] = field(default_factory=list)


def collect_errors(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> DocumentErrors:
    """
    Собирает детальную информацию об ошибках для анализа.
    """
    errors = DocumentErrors()
    
    # Создаём словари для быстрого доступа
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    # Обратный маппинг (gt_id -> pred_id)
    gt_to_pred = {gt_id: pred_id for pred_id, gt_id in matches.items()}
    
    # Находим не найденные элементы (есть в GT, но нет в предсказаниях)
    # Учитываем, что несколько pred элементов могут соответствовать одному GT
    matched_gt_ids = set(matches.values())
    for gt_elem in ground_truth:
        gt_id = gt_elem['id']
        if gt_id not in matched_gt_ids:
            errors.missing_elements.append({
                'id': gt_id,
                'type': gt_elem.get('type', 'unknown'),
                'content_preview': (gt_elem.get('content', '') or '')[:100],
                'page_number': gt_elem.get('page_number', 0),
                'order': gt_elem.get('order', 0)
            })
    
    # Находим лишние элементы (есть в предсказаниях, но нет в GT)
    # НЕ считаем лишними элементы, которые объединены с другими (несколько pred -> один GT)
    matched_pred_ids = set(matches.keys())
    
    # Группируем pred элементы по их GT соответствию
    pred_by_gt = {}
    for pred_id, gt_id in matches.items():
        if gt_id not in pred_by_gt:
            pred_by_gt[gt_id] = []
        pred_by_gt[gt_id].append(pred_id)
    
    # Элемент считается лишним только если он не сопоставлен И не является частью группы
    for pred_elem in predicted:
        pred_id = pred_elem.id
        if pred_id not in matched_pred_ids:
            # Проверяем, может ли этот элемент быть частью группы для какого-то GT
            # (это уже обработано в match_elements, так что если не сопоставлен - значит лишний)
            errors.extra_elements.append({
                'id': pred_id,
                'type': pred_elem.type.value,
                'content_preview': (pred_elem.content or '')[:100],
                'page_number': pred_elem.metadata.get('page_number', 0),
                'order': pred_elem.metadata.get('order', 0)
            })
    
    # Ошибки в порядке элементов
    # Сортируем элементы по order
    pred_with_order = [(pred_id, pred_dict[pred_id]) for pred_id in matches.keys()]
    pred_with_order.sort(key=lambda x: x[1].metadata.get('order', 0))
    
    gt_with_order = [(gt_id, gt_dict[gt_id]) for gt_id in matches.values()]
    gt_with_order.sort(key=lambda x: x[1].get('order', 0))
    
    # Проверяем порядок
    for i, (pred_id, pred_elem) in enumerate(pred_with_order):
        if i < len(gt_with_order):
            gt_id, gt_elem = gt_with_order[i]
            if pred_id in matches and matches[pred_id] != gt_id:
                # Порядок нарушен
                errors.ordering_errors.append({
                    'predicted_id': pred_id,
                    'predicted_type': pred_elem.type.value,
                    'predicted_order': pred_elem.metadata.get('order', 0),
                    'expected_id': gt_id,
                    'expected_type': gt_elem.get('type', 'unknown'),
                    'expected_order': gt_elem.get('order', 0),
                    'position': i
                })
    
    # Ошибки в иерархии
    for pred_id, gt_id in matches.items():
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        # Игнорируем ошибки родителей для HEADER_1
        if gt_elem.get('type', '').lower() == 'header_1':
            continue
        
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        # Сопоставляем родителей через matches
        pred_parent_gt = None
        if pred_parent:
            pred_parent_gt = gt_to_pred.get(pred_parent)
        
        if pred_parent_gt != gt_parent:
            errors.hierarchy_errors.append({
                'element_id': pred_id,
                'element_type': pred_elem.type.value,
                'predicted_parent_id': pred_parent,
                'predicted_parent_gt_id': pred_parent_gt,
                'expected_parent_id': gt_parent,
                'page_number': pred_elem.metadata.get('page_number', 0)
            })
    
    # Группируем pred элементы по их GT соответствию для обработки объединений
    pred_by_gt = {}
    for pred_id, gt_id in matches.items():
        if gt_id not in pred_by_gt:
            pred_by_gt[gt_id] = []
        pred_by_gt[gt_id].append(pred_id)
    
    # Обрабатываем каждый GT элемент (может соответствовать нескольким pred)
    processed_gt = set()
    for gt_id, pred_ids in pred_by_gt.items():
        if gt_id in processed_gt:
            continue
        processed_gt.add(gt_id)
        
        gt_elem = gt_dict.get(gt_id)
        if not gt_elem:
            continue
        
        # Берем первый pred элемент для проверки типа
        first_pred_id = pred_ids[0]
        pred_elem = pred_dict.get(first_pred_id)
        if not pred_elem:
            continue
        
        # Проверяем тип (для объединенных элементов все должны быть одного типа)
        pred_type = pred_elem.type.value.lower()
        gt_type = gt_elem.get('type', '').lower()
        
        if pred_type != gt_type:
            # Для объединенных элементов указываем все ID
            if len(pred_ids) > 1:
                errors.type_mismatch_elements.append({
                    'predicted_ids': pred_ids,
                    'predicted_type': pred_type,
                    'expected_type': gt_type,
                    'content_preview': (pred_elem.content or '')[:100],
                    'page_number': pred_elem.metadata.get('page_number', 0),
                    'is_combined': True
                })
            else:
                errors.type_mismatch_elements.append({
                    'predicted_id': first_pred_id,
                    'predicted_type': pred_type,
                    'expected_type': gt_type,
                    'content_preview': (pred_elem.content or '')[:100],
                    'page_number': pred_elem.metadata.get('page_number', 0),
                    'is_combined': False
                })
        
        # Проверяем CER/WER для текстовых элементов
        elem_type = gt_type
        if elem_type in ('text', 'title', 'header_1', 'header_2', 'header_3', 
                        'header_4', 'header_5', 'header_6', 'caption', 'list_item'):
            gt_content = gt_elem.get('content', '') or ""
            
            if gt_content:
                # Если несколько pred элементов соответствуют одному GT, объединяем их контент
                if len(pred_ids) > 1:
                    pred_contents = []
                    for pid in pred_ids:
                        pe = pred_dict.get(pid)
                        if pe and pe.content:
                            pred_contents.append(pe.content)
                    pred_content = " ".join(pred_contents)
                else:
                    pred_content = pred_elem.content or ""
                
                if pred_content:
                    cer = calculate_cer(gt_content, pred_content)
                    wer = calculate_wer(gt_content, pred_content)
                    
                    # Если ошибка высокая (CER > 0.1 или WER > 0.15)
                    if cer > 0.1 or wer > 0.15:
                        errors.high_error_elements.append({
                            'element_id': first_pred_id if len(pred_ids) == 1 else f"{len(pred_ids)}_combined",
                            'element_ids': pred_ids if len(pred_ids) > 1 else None,
                            'element_type': pred_type,
                            'cer': cer,
                            'wer': wer,
                            'content_preview_gt': gt_content[:100],
                            'content_preview_pred': pred_content[:100],
                            'page_number': pred_elem.metadata.get('page_number', 0),
                            'is_combined': len(pred_ids) > 1,
                            'combined_count': len(pred_ids) if len(pred_ids) > 1 else None
                        })
    
    return errors


@dataclass
class DocumentMetrics:
    """Метрики для одного документа."""
    document_id: str
    source_file: str
    document_format: str
    
    # Текст метрики
    cer: float = 0.0
    wer: float = 0.0
    
    # Время
    time_per_page: float = 0.0  # секунды
    time_per_document: float = 0.0  # секунды
    total_pages: int = 0
    
    # TEDS
    document_teds: float = 0.0
    hierarchy_teds: float = 0.0
    
    # Детекция классов
    class_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Статистика
    total_elements_gt: int = 0
    total_elements_pred: int = 0
    matched_elements: int = 0
    
    # Ошибки для анализа
    errors: DocumentErrors = field(default_factory=DocumentErrors)
    
    # Метрики по bbox
    bbox_precision: float = 0.0
    bbox_recall: float = 0.0
    bbox_f1: float = 0.0
    bbox_matched_count: int = 0
    
    # Метрики по заменам типов
    type_substitutions: Dict[str, Any] = field(default_factory=dict)
    
    # Метрики по заменам уровней заголовков
    header_level_substitutions: Dict[str, Any] = field(default_factory=dict)


def process_document(
    annotation_path: Path,
    pipeline: Pipeline
) -> DocumentMetrics:
    """
    Обрабатывает один документ и вычисляет метрики.
    """
    # Загружаем аннотацию
    annotation = load_annotation(annotation_path)
    source_file = Path(annotation['source_file'])
    document_id = annotation.get('document_id', source_file.stem)
    document_format = annotation.get('document_format', 'unknown')
    ground_truth = annotation.get('elements', [])
    
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    # Парсим документ и замеряем время
    # Создаём LangChain Document
    langchain_doc = Document(page_content="", metadata={"source": str(source_file)})
    
    start_time = time.time()
    parsed_doc = pipeline.parse(langchain_doc)
    end_time = time.time()
    
    processing_time = end_time - start_time
    
    # Получаем количество страниц из metadata
    total_pages = parsed_doc.metadata.get('total_pages', 1) if parsed_doc.metadata else 1
    if total_pages == 0:
        total_pages = 1
    
    time_per_page = processing_time / total_pages
    
    # Сопоставляем элементы
    predicted = parsed_doc.elements
    matches = match_elements(predicted, ground_truth)
    
    # Для DOCX файлов не вычисляем метрики Precision/Recall по bbox,
    # так как большинство элементов не имеют bbox (только заголовки и captions из OCR)
    if source_file.suffix.lower() == '.docx':
        # Пропускаем вычисление bbox метрик для DOCX
        bbox_matches = {}
        bbox_precision = 0.0
        bbox_recall = 0.0
        bbox_f1 = 0.0
        bbox_matched_count = 0
    else:
        # Сопоставляем элементы по bbox (только для PDF файлов)
        from evaluation_metrics import match_elements_by_bbox
        
        # Фильтруем элементы: учитываем только те, у которых есть bbox
        predicted_with_bbox = [e for e in predicted if len(e.metadata.get('bbox', [])) >= 4]
        ground_truth_with_bbox = [e for e in ground_truth if len(e.get('bbox', [])) >= 4]
        
        # Определяем порог IoU в зависимости от типа документа
        # Для scanned PDF используем более низкий порог из-за ошибок округления в post_process_cells
        if document_format == 'scanned_pdf' or 'scanned' in str(source_file).lower():
            initial_iou_threshold = 0.2  # Более низкий порог для scanned PDF
            fallback_thresholds = [0.1, 0.05]  # Еще более низкие пороги для fallback
        else:
            initial_iou_threshold = 0.5  # Стандартный порог для обычного PDF
            fallback_thresholds = [0.3, 0.1]  # Стандартные fallback пороги
        
        pdf_path_for_bbox = source_file if source_file.suffix.lower() == '.pdf' else None
        
        # Пробуем разные пороги IoU, если с начальным не находит совпадений
        bbox_matches = match_elements_by_bbox(
            predicted_with_bbox, 
            ground_truth_with_bbox, 
            iou_threshold=initial_iou_threshold,
            normalize_coordinates=True,
            pdf_path=pdf_path_for_bbox,
            render_scale=2.0
        )
        
        # Если не нашли совпадений, пробуем более низкие пороги
        for fallback_threshold in fallback_thresholds:
            if len(bbox_matches) == 0 and predicted_with_bbox and ground_truth_with_bbox:
                bbox_matches = match_elements_by_bbox(
                    predicted_with_bbox, 
                    ground_truth_with_bbox, 
                    iou_threshold=fallback_threshold,
                    normalize_coordinates=True,
                    pdf_path=pdf_path_for_bbox,
                    render_scale=2.0
                )
                if len(bbox_matches) > 0:
                    break  # Если нашли совпадения, прекращаем попытки
        
        # Вычисляем метрики по bbox
        # Важно: считаем метрики только для элементов с bbox
        bbox_matched_count = len(bbox_matches)
        bbox_precision = bbox_matched_count / len(predicted_with_bbox) if predicted_with_bbox else 0.0
        bbox_recall = bbox_matched_count / len(ground_truth_with_bbox) if ground_truth_with_bbox else 0.0
        bbox_f1 = 2 * (bbox_precision * bbox_recall) / (bbox_precision + bbox_recall) if (bbox_precision + bbox_recall) > 0 else 0.0
    
    # Собираем информацию об ошибках
    errors = collect_errors(predicted, ground_truth, matches)
    
    # Вычисляем CER и WER для текстовых элементов
    # Учитываем объединение: несколько pred элементов могут соответствовать одному GT
    cer_scores = []
    wer_scores = []
    
    # Группируем pred элементы по их GT соответствию
    pred_by_gt = {}
    for pred_id, gt_id in matches.items():
        if gt_id not in pred_by_gt:
            pred_by_gt[gt_id] = []
        pred_by_gt[gt_id].append(pred_id)
    
    # Для каждого GT элемента вычисляем метрики
    for gt_id, pred_ids in pred_by_gt.items():
        gt_elem = next((e for e in ground_truth if e['id'] == gt_id), None)
        if not gt_elem:
            continue
        
        # Считаем CER/WER только для текстовых элементов
        elem_type = gt_elem.get('type', '').lower()
        if elem_type in ('text', 'title', 'header_1', 'header_2', 'header_3', 
                       'header_4', 'header_5', 'header_6', 'caption', 'list_item'):
            gt_content = gt_elem.get('content', '') or ""
            
            if gt_content:  # Только если есть эталонный текст
                # Если несколько pred элементов соответствуют одному GT, объединяем их контент
                if len(pred_ids) > 1:
                    # Объединяем контент всех pred элементов
                    pred_contents = []
                    for pred_id in pred_ids:
                        pred_elem = next((e for e in predicted if e.id == pred_id), None)
                        if pred_elem and pred_elem.content:
                            pred_contents.append(pred_elem.content)
                    pred_content = " ".join(pred_contents)
                else:
                    # Один к одному
                    pred_elem = next((e for e in predicted if e.id == pred_ids[0]), None)
                    pred_content = pred_elem.content or "" if pred_elem else ""
                
                if pred_content:
                    cer = calculate_cer(gt_content, pred_content)
                    wer = calculate_wer(gt_content, pred_content)
                    cer_scores.append(cer)
                    wer_scores.append(wer)
    
    avg_cer = statistics.mean(cer_scores) if cer_scores else 0.0
    avg_wer = statistics.mean(wer_scores) if wer_scores else 0.0
    
    # Вычисляем TEDS для документа (упрощенная версия)
    ordering_acc, _ = calculate_ordering_accuracy(predicted, ground_truth, matches)
    # Для hierarchy accuracy нужно использовать функцию, которая игнорирует HEADER_1
    # Используем нашу собственную функцию calculate_hierarchy_teds
    hierarchy_acc = calculate_hierarchy_teds(predicted, ground_truth, matches)
    doc_teds = (ordering_acc + hierarchy_acc) / 2.0
    
    # Вычисляем TEDS для иерархии (игнорируя HEADER_1)
    hierarchy_teds = calculate_hierarchy_teds(predicted, ground_truth, matches)
    
    # Создаём детальный анализ TEDS с визуализациями и JSON отчетом
    try:
        # Определяем директорию для сохранения анализа TEDS
        # Используем уникальный путь на основе имени аннотации для избежания конфликтов
        annotations_dir = annotation_path.parent
        annotation_name = annotation_path.stem  # Имя файла без расширения
        teds_analysis_dir = annotations_dir.parent / "teds_analysis" / annotation_name
        teds_analysis_dir.mkdir(parents=True, exist_ok=True)
        
        # Создаём визуализации и отчет
        json_path, image_paths = create_teds_visualizations_and_report(
            predicted=predicted,
            ground_truth=ground_truth,
            matches=matches,
            document_id=document_id,
            document_teds=doc_teds,
            hierarchy_teds=hierarchy_teds,
            ordering_accuracy=ordering_acc,
            output_dir=teds_analysis_dir,
            document_format=document_format
        )
        
        print(f"  Создан анализ TEDS: {json_path}")
        if image_paths:
            png_count = len([p for p in image_paths if p.suffix == '.png'])
            md_count = len([p for p in image_paths if p.suffix == '.md'])
            if png_count > 0:
                print(f"  Создано {png_count} PNG визуализаций иерархии")
            if md_count > 0:
                print(f"  Создано {md_count} Markdown файлов с деревьями")
    except Exception as e:
        print(f"  Предупреждение: не удалось создать анализ TEDS: {e}")
    
    # Вычисляем метрики детекции классов
    class_metrics = calculate_class_detection_accuracy(predicted, ground_truth, matches)
    
    # Вычисляем метрики по заменам типов элементов
    type_substitutions = calculate_type_substitutions(predicted, ground_truth, matches)
    
    # Вычисляем метрики по заменам уровней заголовков
    header_level_substitutions = calculate_header_level_substitutions(predicted, ground_truth, matches)
    
    # Создаем визуализацию сравнения с bbox
    # Только для PDF файлов (не для DOCX)
    try:
        if source_file.suffix.lower() == '.pdf':
            # Определяем директорию для сохранения визуализаций
            annotations_dir = annotation_path.parent
            visualizations_dir = annotations_dir.parent / "visualizations" / document_id
            visualizations_dir.mkdir(parents=True, exist_ok=True)
            
            # Создаем визуализацию
            saved_images = visualize_comparison(
                pdf_path=source_file,
                predicted=predicted,
                ground_truth=ground_truth,
                bbox_matches=bbox_matches,
                output_dir=visualizations_dir,
                render_scale=2.0
            )
            
            print(f"  Создано {len(saved_images)} изображений визуализации в {visualizations_dir}")
        elif source_file.suffix.lower() == '.docx':
            # Для DOCX создаем комбинированные изображения (оригинал + разметка модели)
            try:
                # Определяем директорию для сохранения изображений
                annotations_dir = annotation_path.parent
                visualizations_dir = annotations_dir.parent / "visualizations" / document_id
                visualizations_dir.mkdir(parents=True, exist_ok=True)
                
                # Создаем комбинированные изображения
                images_saved = _create_docx_comparison_images(
                    docx_path=source_file,
                    predicted=predicted,
                    output_dir=visualizations_dir,
                    render_scale=2.0
                )
                
                if images_saved > 0:
                    print(f"  Создано {images_saved} комбинированных изображений для DOCX в {visualizations_dir}")
                else:
                    print(f"  Предупреждение: не удалось создать изображения для DOCX")
            except Exception as e:
                print(f"  Предупреждение: не удалось создать изображения для DOCX: {e}")
    except Exception as e:
        print(f"  Предупреждение: не удалось создать визуализацию: {e}")
    
    return DocumentMetrics(
        document_id=document_id,
        source_file=str(source_file),
        document_format=document_format,
        cer=avg_cer,
        wer=avg_wer,
        time_per_page=time_per_page,
        time_per_document=processing_time,
        total_pages=total_pages,
        document_teds=doc_teds,
        hierarchy_teds=hierarchy_teds,
        class_metrics=class_metrics,
        total_elements_gt=len(ground_truth),
        total_elements_pred=len(predicted),
        matched_elements=len(matches),
        errors=errors,
        bbox_precision=bbox_precision,
        bbox_recall=bbox_recall,
        bbox_f1=bbox_f1,
        bbox_matched_count=bbox_matched_count,
        type_substitutions=type_substitutions,
        header_level_substitutions=header_level_substitutions
    )


def run_evaluation_pipeline(
    annotations_dir: Path,
    output_file: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Запускает пайплайн оценки для всех аннотаций.
    
    Args:
        annotations_dir: Директория с аннотациями
        output_file: Путь для сохранения результатов (JSON)
    
    Returns:
        Словарь с результатами
    """
    # Инициализируем пайплайн
    pipeline = Pipeline()
    
    # Преобразуем в Path если это строка
    if isinstance(annotations_dir, str):
        annotations_dir = Path(annotations_dir)
    
    # Проверяем, что директория существует
    if not annotations_dir.exists():
        raise ValueError(f"Annotations directory does not exist: {annotations_dir}")
    
    if not annotations_dir.is_dir():
        raise ValueError(f"Annotations path is not a directory: {annotations_dir}")
    
    # Находим все аннотации
    annotation_files = sorted(annotations_dir.glob("*_annotation.json"))
    
    if not annotation_files:
        raise ValueError(f"No annotation files found in {annotations_dir}. Files in directory: {list(annotations_dir.iterdir())}")
    
    print(f"Найдено {len(annotation_files)} файлов аннотаций")
    
    # Обрабатываем каждый документ
    all_metrics = []
    
    for i, ann_file in enumerate(annotation_files, 1):
        print(f"\n[{i}/{len(annotation_files)}] Обработка: {ann_file.name}")
        
        try:
            metrics = process_document(ann_file, pipeline)
            all_metrics.append(metrics)
            print(f"  ✓ CER: {metrics.cer:.4f}, WER: {metrics.wer:.4f}")
            print(f"  ✓ Время: {metrics.time_per_document:.2f}s (документ), {metrics.time_per_page:.2f}s/страница (страниц: {metrics.total_pages})")
            print(f"  ✓ TEDS документ: {metrics.document_teds:.4f}, иерархия: {metrics.hierarchy_teds:.4f}")
            # Для DOCX файлов не выводим метрики bbox, так как они не вычисляются
            if metrics.document_format != 'docx':
                print(f"  ✓ Bbox: Precision={metrics.bbox_precision:.4f}, Recall={metrics.bbox_recall:.4f}, F1={metrics.bbox_f1:.4f} (найдено {metrics.bbox_matched_count}/{metrics.total_elements_gt})")
            
            # Метрики по заменам типов элементов
            type_subs = metrics.type_substitutions
            if type_subs:
                total_subs = type_subs.get('total_substitutions', 0)
                sub_rate = type_subs.get('substitution_rate', 0.0)
                print(f"  ✓ Замены типов: {total_subs} (доля: {sub_rate:.4f})")
            
            # Метрики по заменам уровней заголовков
            header_subs = metrics.header_level_substitutions
            if header_subs:
                total_header_subs = header_subs.get('total_header_substitutions', 0)
                header_sub_rate = header_subs.get('header_substitution_rate', 0.0)
                header_count_gt = header_subs.get('header_count_gt', {})
                header_count_pred = header_subs.get('header_count_pred', {})
                header_count_matched = header_subs.get('header_count_matched', {})
                
                print(f"  ✓ Замены уровней заголовков: {total_header_subs} (доля: {header_sub_rate:.4f})")
                
                # Выводим статистику по уровням заголовков
                if header_count_gt or header_count_pred:
                    header_levels_info = []
                    all_levels = set(list(header_count_gt.keys()) + list(header_count_pred.keys()))
                    for level in sorted(all_levels):
                        gt_count = header_count_gt.get(level, 0)
                        pred_count = header_count_pred.get(level, 0)
                        matched_count = header_count_matched.get(level, 0)
                        header_levels_info.append(f"{level}: GT={gt_count}, Pred={pred_count}, Matched={matched_count}")
                    if header_levels_info:
                        print(f"    Уровни заголовков: {', '.join(header_levels_info)}")
        except Exception as e:
            print(f"  ✗ Ошибка: {e}")
            continue
    
    # Вычисляем агрегированные метрики
    if not all_metrics:
        raise ValueError("No documents processed successfully")
    
    # Группируем метрики по типу документа
    # Разделяем PDF на обычные и сканированные
    metrics_by_format = defaultdict(list)
    for m in all_metrics:
        # Определяем, является ли PDF сканированным
        format_name = m.document_format
        # Проверяем, является ли это scanned PDF
        is_scanned = (
            format_name == 'scanned_pdf' or
            '_scanned' in m.source_file.lower() or
            '_scanned' in str(m.document_id).lower()
        )
        
        if format_name == 'pdf' or format_name == 'pdf_regular' or format_name == 'scanned_pdf':
            if is_scanned:
                format_name = 'scanned_pdf'
            else:
                format_name = 'pdf_regular'
        metrics_by_format[format_name].append(m)
    
    # Средние метрики (общие)
    avg_cer = statistics.mean([m.cer for m in all_metrics])
    avg_wer = statistics.mean([m.wer for m in all_metrics])
    avg_time_per_page = statistics.mean([m.time_per_page for m in all_metrics])
    avg_time_per_doc = statistics.mean([m.time_per_document for m in all_metrics])
    avg_doc_teds = statistics.mean([m.document_teds for m in all_metrics])
    avg_hierarchy_teds = statistics.mean([m.hierarchy_teds for m in all_metrics])
    
    # Агрегируем метрики по заменам типов
    total_type_substitutions = sum([m.type_substitutions.get('total_substitutions', 0) for m in all_metrics])
    avg_substitution_rate = statistics.mean([m.type_substitutions.get('substitution_rate', 0.0) for m in all_metrics])
    
    # Агрегируем метрики по заменам уровней заголовков
    total_header_substitutions = sum([m.header_level_substitutions.get('total_header_substitutions', 0) for m in all_metrics])
    avg_header_substitution_rate = statistics.mean([m.header_level_substitutions.get('header_substitution_rate', 0.0) for m in all_metrics])
    
    # Метрики по типам документов
    format_metrics = {}
    for format_name, format_metrics_list in metrics_by_format.items():
        if format_metrics_list:
            format_metrics[format_name] = {
                'count': len(format_metrics_list),
                'avg_cer': statistics.mean([m.cer for m in format_metrics_list]),
                'avg_wer': statistics.mean([m.wer for m in format_metrics_list]),
                'avg_time_per_page': statistics.mean([m.time_per_page for m in format_metrics_list]),
                'avg_time_per_document': statistics.mean([m.time_per_document for m in format_metrics_list]),
                'avg_document_teds': statistics.mean([m.document_teds for m in format_metrics_list]),
                'avg_hierarchy_teds': statistics.mean([m.hierarchy_teds for m in format_metrics_list]),
                'avg_bbox_precision': statistics.mean([m.bbox_precision for m in format_metrics_list]),
                'avg_bbox_recall': statistics.mean([m.bbox_recall for m in format_metrics_list]),
                'avg_bbox_f1': statistics.mean([m.bbox_f1 for m in format_metrics_list]),
                'total_type_substitutions': sum([m.type_substitutions.get('total_substitutions', 0) for m in format_metrics_list]),
                'avg_substitution_rate': statistics.mean([m.type_substitutions.get('substitution_rate', 0.0) for m in format_metrics_list]),
                'total_header_substitutions': sum([m.header_level_substitutions.get('total_header_substitutions', 0) for m in format_metrics_list]),
                'avg_header_substitution_rate': statistics.mean([m.header_level_substitutions.get('header_substitution_rate', 0.0) for m in format_metrics_list])
            }
    
    # Агрегируем метрики классов (общие)
    all_class_metrics = defaultdict(lambda: {
        'precision': [],
        'recall': [],
        'f1': [],
        'count_gt': 0,
        'count_pred': 0,
        'count_matched': 0
    })
    
    # Агрегируем метрики классов по типам документов
    class_metrics_by_format = defaultdict(lambda: defaultdict(lambda: {
        'precision': [],
        'recall': [],
        'f1': [],
        'count_gt': 0,
        'count_pred': 0,
        'count_matched': 0
    }))
    
    for m in all_metrics:
        # Определяем формат для этого документа (используем ту же логику, что и выше)
        format_name = m.document_format
        is_scanned = (
            format_name == 'scanned_pdf' or
            '_scanned' in m.source_file.lower() or
            '_scanned' in str(m.document_id).lower()
        )
        
        if format_name == 'pdf' or format_name == 'pdf_regular' or format_name == 'scanned_pdf':
            if is_scanned:
                format_name = 'scanned_pdf'
            else:
                format_name = 'pdf_regular'
        
        # Агрегируем общие метрики
        for class_name, class_data in m.class_metrics.items():
            all_class_metrics[class_name]['precision'].append(class_data['precision'])
            all_class_metrics[class_name]['recall'].append(class_data['recall'])
            all_class_metrics[class_name]['f1'].append(class_data['f1'])
            all_class_metrics[class_name]['count_gt'] += class_data['count_gt']
            all_class_metrics[class_name]['count_pred'] += class_data['count_pred']
            all_class_metrics[class_name]['count_matched'] += class_data['count_matched']
        
        # Агрегируем метрики по форматам
        for class_name, class_data in m.class_metrics.items():
            class_metrics_by_format[format_name][class_name]['precision'].append(class_data['precision'])
            class_metrics_by_format[format_name][class_name]['recall'].append(class_data['recall'])
            class_metrics_by_format[format_name][class_name]['f1'].append(class_data['f1'])
            class_metrics_by_format[format_name][class_name]['count_gt'] += class_data['count_gt']
            class_metrics_by_format[format_name][class_name]['count_pred'] += class_data['count_pred']
            class_metrics_by_format[format_name][class_name]['count_matched'] += class_data['count_matched']
    
    # Вычисляем средние для классов (общие)
    aggregated_class_metrics = {}
    for class_name, data in all_class_metrics.items():
        if data['precision']:  # Если есть данные
            aggregated_class_metrics[class_name] = {
                'precision': statistics.mean(data['precision']),
                'recall': statistics.mean(data['recall']),
                'f1': statistics.mean(data['f1']),
                'count_gt': data['count_gt'],
                'count_pred': data['count_pred'],
                'count_matched': data['count_matched']
            }
    
    # Вычисляем средние для классов по форматам
    aggregated_class_metrics_by_format = {}
    for format_name, format_class_metrics in class_metrics_by_format.items():
        aggregated_class_metrics_by_format[format_name] = {}
        for class_name, data in format_class_metrics.items():
            if data['precision']:  # Если есть данные
                aggregated_class_metrics_by_format[format_name][class_name] = {
                    'precision': statistics.mean(data['precision']),
                    'recall': statistics.mean(data['recall']),
                    'f1': statistics.mean(data['f1']),
                    'count_gt': data['count_gt'],
                    'count_pred': data['count_pred'],
                    'count_matched': data['count_matched']
                }
    
    # Формируем результаты
    results = {
        'summary': {
            'total_documents': len(all_metrics),
            'avg_cer': avg_cer,
            'avg_wer': avg_wer,
            'avg_time_per_page': avg_time_per_page,
            'avg_time_per_document': avg_time_per_doc,
            'avg_document_teds': avg_doc_teds,
            'avg_hierarchy_teds': avg_hierarchy_teds,
            'avg_bbox_precision': statistics.mean([m.bbox_precision for m in all_metrics]),
            'avg_bbox_recall': statistics.mean([m.bbox_recall for m in all_metrics]),
            'avg_bbox_f1': statistics.mean([m.bbox_f1 for m in all_metrics]),
            'total_type_substitutions': total_type_substitutions,
            'avg_substitution_rate': avg_substitution_rate,
            'total_header_substitutions': total_header_substitutions,
            'avg_header_substitution_rate': avg_header_substitution_rate
        },
        'by_format': format_metrics,
        'per_document': [
            {
                'document_id': m.document_id,
                'source_file': m.source_file,
                'format': m.document_format,
                'cer': m.cer,
                'wer': m.wer,
                'time_per_page': m.time_per_page,
                'time_per_document': m.time_per_document,
                'total_pages': m.total_pages,
                'document_teds': m.document_teds,
                'hierarchy_teds': m.hierarchy_teds,
                'total_elements_gt': m.total_elements_gt,
                'total_elements_pred': m.total_elements_pred,
                'matched_elements': m.matched_elements,
                'bbox_precision': m.bbox_precision,
                'bbox_recall': m.bbox_recall,
                'bbox_f1': m.bbox_f1,
                'bbox_matched_count': m.bbox_matched_count,
                'class_metrics': m.class_metrics,
                'type_substitutions': m.type_substitutions,
                'header_level_substitutions': m.header_level_substitutions
            }
            for m in all_metrics
        ],
        'class_metrics': aggregated_class_metrics,
        'class_metrics_by_format': aggregated_class_metrics_by_format
    }
    
    # Сохраняем отдельный файл с ошибками
    if output_file:
        errors_file = output_file.parent / f"{output_file.stem}_errors.json"
        errors_data = {
            'total_documents': len(all_metrics),
            'errors_by_document': {
                m.document_id: {
                    'source_file': m.source_file,
                    'format': m.document_format,
                    'summary': {
                        'missing_elements_count': len(m.errors.missing_elements),
                        'extra_elements_count': len(m.errors.extra_elements),
                        'ordering_errors_count': len(m.errors.ordering_errors),
                        'hierarchy_errors_count': len(m.errors.hierarchy_errors),
                        'high_error_elements_count': len(m.errors.high_error_elements),
                        'type_mismatch_count': len(m.errors.type_mismatch_elements)
                    },
                    'details': {
                        'missing_elements': m.errors.missing_elements,
                        'extra_elements': m.errors.extra_elements,
                        'ordering_errors': m.errors.ordering_errors,
                        'hierarchy_errors': m.errors.hierarchy_errors,
                        'high_error_elements': m.errors.high_error_elements,
                        'type_mismatch_elements': m.errors.type_mismatch_elements
                    }
                }
                for m in all_metrics
            }
        }
        
        with open(errors_file, 'w', encoding='utf-8') as f:
            json.dump(errors_data, f, ensure_ascii=False, indent=2)
        print(f"✓ Детальная информация об ошибках сохранена в: {errors_file}")
    
    # Сохраняем результаты
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n✓ Результаты сохранены в: {output_file}")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Пайплайн оценки качества парсинга документов")
    # Определяем пути по умолчанию относительно скрипта
    script_dir = Path(__file__).parent
    default_annotations_dir = script_dir / "annotations"
    default_output = script_dir / "evaluation_results.json"
    
    parser.add_argument(
        "--annotations-dir",
        type=str,
        default=str(default_annotations_dir),
        help="Директория с аннотациями"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(default_output),
        help="Файл для сохранения результатов"
    )
    
    args = parser.parse_args()
    
    annotations_dir = Path(args.annotations_dir)
    output_file = Path(args.output)
    
    results = run_evaluation_pipeline(annotations_dir, output_file)
    
    # Выводим сводку
    print("\n" + "="*80)
    print("СВОДКА МЕТРИК")
    print("="*80)
    summary = results['summary']
    print(f"Всего документов: {summary['total_documents']}")
    print(f"Средний CER: {summary['avg_cer']:.4f}")
    print(f"Средний WER: {summary['avg_wer']:.4f}")
    print(f"Среднее время на страницу: {summary['avg_time_per_page']:.2f}s")
    print(f"Среднее время на документ: {summary['avg_time_per_document']:.2f}s")
    print(f"Средний TEDS документа: {summary['avg_document_teds']:.4f}")
    print(f"Средний TEDS иерархии: {summary['avg_hierarchy_teds']:.4f}")
    print(f"\nМетрики по bbox (IoU >= 0.5):")
    print(f"  Precision: {summary['avg_bbox_precision']:.4f}")
    print(f"  Recall: {summary['avg_bbox_recall']:.4f}")
    print(f"  F1: {summary['avg_bbox_f1']:.4f}")
    print(f"\nМетрики по заменам типов элементов:")
    print(f"  Всего замен: {summary['total_type_substitutions']}")
    print(f"  Средняя доля замен: {summary['avg_substitution_rate']:.4f}")
    print(f"\nМетрики по заменам уровней заголовков:")
    print(f"  Всего замен уровней: {summary['total_header_substitutions']}")
    print(f"  Средняя доля замен уровней: {summary['avg_header_substitution_rate']:.4f}")
    
    print("\n" + "="*80)
    print("МЕТРИКИ ПО ТИПАМ ДОКУМЕНТОВ")
    print("="*80)
    # Маппинг названий форматов для читаемого вывода
    format_display_names = {
        'pdf_regular': 'PDF (обычные)',
        'scanned_pdf': 'PDF (сканированные)',
        'pdf': 'PDF',
        'docx': 'DOCX',
    }
    for format_name, format_data in sorted(results['by_format'].items()):
        display_name = format_display_names.get(format_name, format_name.upper())
        print(f"\n{display_name}:")
        print(f"  Документов: {format_data['count']}")
        print(f"  Средний CER: {format_data['avg_cer']:.4f}")
        print(f"  Средний WER: {format_data['avg_wer']:.4f}")
        print(f"  Среднее время на страницу: {format_data['avg_time_per_page']:.2f}s")
        print(f"  Среднее время на документ: {format_data['avg_time_per_document']:.2f}s")
        print(f"  Средний TEDS документа: {format_data['avg_document_teds']:.4f}")
        print(f"  Средний TEDS иерархии: {format_data['avg_hierarchy_teds']:.4f}")
        print(f"  Bbox Precision: {format_data['avg_bbox_precision']:.4f}")
        print(f"  Bbox Recall: {format_data['avg_bbox_recall']:.4f}")
        print(f"  Bbox F1: {format_data['avg_bbox_f1']:.4f}")
        print(f"  Замен типов: {format_data['total_type_substitutions']} (доля: {format_data['avg_substitution_rate']:.4f})")
        print(f"  Замен уровней заголовков: {format_data['total_header_substitutions']} (доля: {format_data['avg_header_substitution_rate']:.4f})")
    
    print("\n" + "="*80)
    print("МЕТРИКИ ДЕТЕКЦИИ КЛАССОВ")
    print("="*80)
    
    # Выводим метрики классов по типам документов
    for format_name in sorted(results['class_metrics_by_format'].keys()):
        display_name = format_display_names.get(format_name, format_name.upper())
        print(f"\n{display_name}:")
        format_class_metrics = results['class_metrics_by_format'][format_name]
        if format_class_metrics:
            for class_name, metrics in sorted(format_class_metrics.items()):
                print(f"  {class_name:20s} | Precision: {metrics['precision']:.4f} | "
                      f"Recall: {metrics['recall']:.4f} | F1: {metrics['f1']:.4f} | "
                      f"GT: {metrics['count_gt']:3d} | Pred: {metrics['count_pred']:3d} | "
                      f"Matched: {metrics['count_matched']:3d}")
        else:
            print("  (нет данных)")
    
    # Выводим общие метрики классов (если нужно)
    print("\n" + "-"*80)
    print("ОБЩИЕ МЕТРИКИ ДЕТЕКЦИИ КЛАССОВ (все документы):")
    print("-"*80)
    for class_name, metrics in sorted(results['class_metrics'].items()):
        print(f"{class_name:20s} | Precision: {metrics['precision']:.4f} | "
              f"Recall: {metrics['recall']:.4f} | F1: {metrics['f1']:.4f} | "
              f"GT: {metrics['count_gt']:3d} | Pred: {metrics['count_pred']:3d} | "
              f"Matched: {metrics['count_matched']:3d}")
