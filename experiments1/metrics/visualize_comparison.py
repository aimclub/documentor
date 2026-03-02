"""
Модуль для визуализации сравнения предсказанных и ground truth элементов с bbox.

Создает изображения страниц PDF с отрисованными bbox для анализа метрик.
"""

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from documentor.domain.models import Element


def render_pdf_page(
    pdf_path: Path,
    page_num: int,
    render_scale: float = 2.0
) -> Image.Image:
    """
    Рендерит страницу PDF как изображение.
    
    Args:
        pdf_path: Путь к PDF файлу
        page_num: Номер страницы (0-based)
        render_scale: Масштаб рендеринга
        
    Returns:
        PIL Image
    """
    pdf_doc = fitz.open(str(pdf_path))
    try:
        if page_num < 0 or page_num >= len(pdf_doc):
            return None
        
        page = pdf_doc[page_num]
        mat = fitz.Matrix(render_scale, render_scale)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Отладочная информация: проверяем размеры
        page_width_pts = page.rect.width
        page_height_pts = page.rect.height
        expected_width = page_width_pts * render_scale
        expected_height = page_height_pts * render_scale
        
        # Если размеры не совпадают, это может быть проблемой
        if abs(pix.width - expected_width) > 1 or abs(pix.height - expected_height) > 1:
            print(f"  [WARNING] Page {page_num + 1}: размеры не совпадают!")
            print(f"    Ожидалось: {expected_width} x {expected_height}")
            print(f"    Получено: {pix.width} x {pix.height}")
        
        return img
    finally:
        pdf_doc.close()


def draw_bbox(
    img: Image.Image,
    bbox: List[float],
    color: str,
    label: str = "",
    width: int = 2
) -> Image.Image:
    """
    Рисует bbox на изображении.
    
    Args:
        img: PIL Image
        bbox: Координаты [x1, y1, x2, y2]
        color: Цвет в формате "red", "green", "blue" или RGB tuple
        label: Текстовая метка
        width: Толщина линии
        
    Returns:
        Изображение с нарисованным bbox
    """
    if len(bbox) < 4:
        return img
    
    draw = ImageDraw.Draw(img)
    
    # Конвертируем цвет в RGB tuple если нужно
    color_map = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "orange": (255, 165, 0),
        "purple": (128, 0, 128)
    }
    
    if isinstance(color, str):
        rgb_color = color_map.get(color.lower(), (255, 0, 0))
    else:
        rgb_color = color
    
    x1, y1, x2, y2 = bbox
    
    # Рисуем прямоугольник
    draw.rectangle([x1, y1, x2, y2], outline=rgb_color, width=width)
    
    # Рисуем метку, если указана
    if label:
        try:
            # Пытаемся использовать системный шрифт
            font = ImageFont.truetype("arial.ttf", 12)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            except:
                font = ImageFont.load_default()
        
        # Фон для текста
        text_bbox = draw.textbbox((x1, y1 - 20), label, font=font)
        if text_bbox:
            draw.rectangle(text_bbox, fill=(255, 255, 255, 200))
        
        draw.text((x1, y1 - 20), label, fill=rgb_color, font=font)
    
    return img


def visualize_comparison(
    pdf_path: Path,
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    bbox_matches: Dict[str, str],
    output_dir: Path,
    render_scale: float = 2.0
) -> List[Path]:
    """
    Создает визуализацию сравнения предсказанных и ground truth элементов.
    
    Для каждой страницы создает 3 изображения:
    1. Предсказанные элементы (зеленые bbox)
    2. Ground truth элементы (красные bbox)
    3. Сопоставленные элементы (синие bbox для matched, желтые для unmatched)
    
    Args:
        pdf_path: Путь к PDF файлу
        predicted: Список предсказанных элементов
        ground_truth: Список ground truth элементов
        bbox_matches: Словарь сопоставлений pred_id -> gt_id
        output_dir: Директория для сохранения изображений
        render_scale: Масштаб рендеринга
        
    Returns:
        Список путей к созданным изображениям
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Открываем PDF
    pdf_doc = fitz.open(str(pdf_path))
    total_pages = len(pdf_doc)
    pdf_doc.close()
    
    saved_images = []
    
    # Группируем элементы по страницам
    pred_by_page = defaultdict(list)
    gt_by_page = defaultdict(list)
    
    for pred_elem in predicted:
        # В predicted может быть page_num (0-based) или page_number (1-based)
        page_num = pred_elem.metadata.get('page_num')
        if page_num is None:
            page_num = pred_elem.metadata.get('page_number', 1) - 1  # Конвертируем в 0-based
        if 'bbox' in pred_elem.metadata and len(pred_elem.metadata['bbox']) >= 4:
            pred_by_page[page_num].append(pred_elem)
    
    for gt_elem in ground_truth:
        # В ground truth page_number всегда 1-based
        page_num = gt_elem.get('page_number', 1) - 1  # Конвертируем в 0-based
        if 'bbox' in gt_elem and len(gt_elem['bbox']) >= 4:
            gt_by_page[page_num].append(gt_elem)
    
    # Обрабатываем каждую страницу
    for page_num in range(total_pages):
        # Рендерим страницу
        page_img = render_pdf_page(pdf_path, page_num, render_scale)
        if page_img is None:
            continue
        
        # Получаем элементы для этой страницы
        page_pred = pred_by_page.get(page_num, [])
        page_gt = gt_by_page.get(page_num, [])
        
        if not page_pred and not page_gt:
            continue  # Пропускаем страницы без элементов
        
        # Создаем 3 изображения для сравнения
        
        # 1. Предсказанные элементы (зеленые)
        img_pred = page_img.copy()
        for pred_elem in page_pred:
            bbox = pred_elem.metadata.get('bbox', [])
            elem_type = pred_elem.type.value
            label = f"{elem_type} {pred_elem.id}"
            img_pred = draw_bbox(img_pred, bbox, "green", label, width=2)
        
        pred_img_path = output_dir / f"page_{page_num + 1}_predicted.png"
        img_pred.save(pred_img_path)
        saved_images.append(pred_img_path)
        
        # 2. Ground truth элементы (красные)
        img_gt = page_img.copy()
        for gt_elem in page_gt:
            bbox = gt_elem.get('bbox', [])
            elem_type = gt_elem.get('type', 'unknown')
            elem_id = gt_elem.get('id', 'unknown')
            label = f"{elem_type} {elem_id}"
            
            # Проверяем, что координаты в пределах изображения
            if len(bbox) >= 4:
                img_width, img_height = img_gt.size
                if bbox[2] > img_width or bbox[3] > img_height:
                    print(f"  [WARNING] GT элемент {elem_id} на странице {page_num + 1}: координаты выходят за пределы!")
                    print(f"    bbox: {bbox}, размер изображения: {img_width} x {img_height}")
                    # Ограничиваем координаты размерами изображения
                    bbox = [
                        max(0, min(bbox[0], img_width)),
                        max(0, min(bbox[1], img_height)),
                        max(bbox[0], min(bbox[2], img_width)),
                        max(bbox[1], min(bbox[3], img_height))
                    ]
            
            img_gt = draw_bbox(img_gt, bbox, "red", label, width=2)
        
        gt_img_path = output_dir / f"page_{page_num + 1}_ground_truth.png"
        img_gt.save(gt_img_path)
        saved_images.append(gt_img_path)
        
        # 3. Сопоставленные элементы
        # Синие - сопоставленные, желтые - не сопоставленные
        img_matched = page_img.copy()
        
        # Создаем множества сопоставленных ID
        matched_pred_ids = set(bbox_matches.keys())
        matched_gt_ids = set(bbox_matches.values())
        
        # Рисуем предсказанные элементы
        for pred_elem in page_pred:
            bbox = pred_elem.metadata.get('bbox', [])
            elem_type = pred_elem.type.value
            elem_id = pred_elem.id
            
            if elem_id in matched_pred_ids:
                # Сопоставленный - синий
                label = f"{elem_type} {elem_id} (matched)"
                img_matched = draw_bbox(img_matched, bbox, "blue", label, width=3)
            else:
                # Не сопоставленный - желтый
                label = f"{elem_type} {elem_id} (unmatched)"
                img_matched = draw_bbox(img_matched, bbox, "yellow", label, width=2)
        
        # Рисуем ground truth элементы
        for gt_elem in page_gt:
            bbox = gt_elem.get('bbox', [])
            elem_type = gt_elem.get('type', 'unknown')
            elem_id = gt_elem.get('id', 'unknown')
            
            if elem_id in matched_gt_ids:
                # Сопоставленный - синий (пунктирная линия)
                label = f"{elem_type} {elem_id} (matched)"
                img_matched = draw_bbox(img_matched, bbox, "cyan", label, width=2)
            else:
                # Не сопоставленный - оранжевый
                label = f"{elem_type} {elem_id} (unmatched)"
                img_matched = draw_bbox(img_matched, bbox, "orange", label, width=2)
        
        matched_img_path = output_dir / f"page_{page_num + 1}_matched.png"
        img_matched.save(matched_img_path)
        saved_images.append(matched_img_path)
    
    return saved_images
