"""
Пайплайн для сопоставления layout detection (DOTS OCR) с данными из DOCX XML.

Идея:
1. Layout detection через DOTS OCR находит элементы (таблицы, изображения) на страницах PDF
2. Извлекаем таблицы и изображения из DOCX XML в порядке появления
3. Сопоставляем результаты layout detection с данными из DOCX XML
4. Учитываем подписи таблиц (например, "Таблица 1. ...")
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO

from PIL import Image
import fitz  # PyMuPDF

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_xml_parser import (
    extract_images_from_docx_xml,
    extract_tables_from_docx_xml,
    extract_tables_with_context_xml,
    extract_text_from_element,
    NAMESPACES
)
from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
)
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer

# Используем 2x увеличение для DOTS OCR
RENDER_SCALE = 2.0


def find_table_caption_before_table(
    docx_path: Path,
    table_xml_position: int
) -> Optional[Dict[str, Any]]:
    """
    Находит подпись таблицы (например, "Таблица 1. ...") перед таблицей в DOCX XML.
    
    Args:
        docx_path: Путь к DOCX файлу
        table_xml_position: Позиция таблицы в XML
    
    Returns:
        Словарь с информацией о подписи {'text': '...', 'number': 1} или None
    """
    import zipfile
    import xml.etree.ElementTree as ET
    import re
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            body = root.find('w:body', NAMESPACES)
            if body is None:
                return None
            
            all_elements = list(body)
            
            # Ищем параграфы перед таблицей (до 5 параграфов назад)
            for i in range(max(0, table_xml_position - 5), table_xml_position):
                elem = all_elements[i]
                if elem.tag.endswith('}p'):  # Параграф
                    text = extract_text_from_element(elem, NAMESPACES).strip()
                    text_lower = text.lower()
                    
                    # Проверяем, является ли это подписью таблицы
                    # Паттерны: "Таблица 1. ...", "Table 1. ...", "Таблица 1", и т.д.
                    pattern = r'(таблица|table)\s*(\d+)'
                    match = re.search(pattern, text_lower, re.IGNORECASE)
                    if match:
                        table_number = int(match.group(2))
                        return {
                            'text': text,
                            'number': table_number,
                            'xml_position': i
                        }
    
    except Exception as e:
        print(f"  Предупреждение: не удалось найти подпись таблицы: {e}")
    
    return None


def is_valid_table(table_data: Dict[str, Any], table_caption: Optional[str] = None) -> bool:
    """
    Проверяет, является ли таблица валидной.
    
    Args:
        table_data: Данные таблицы
        table_caption: Подпись таблицы
    
    Returns:
        True, если таблица валидная
    """
    rows = table_data.get('rows', [])
    
    # Таблица должна иметь хотя бы 2 строки
    if len(rows) < 2:
        return False
    
    # Таблица должна иметь хотя бы 2 колонки
    cols_count = table_data.get('cols_count', 0)
    if cols_count < 2:
        return False
    
    # Проверяем, есть ли хотя бы одна ячейка с текстом
    has_text = False
    for row in rows:
        cells = row.get('cells', [])
        for cell in cells:
            if cell.get('text', '').strip():
                has_text = True
                break
        if has_text:
            break
    
    if not has_text:
        return False
    
    return True


def match_ocr_table_to_docx_table(
    ocr_table: Dict[str, Any],
    docx_tables: List[Dict[str, Any]],
    page_num: int,
    used_docx_tables: set,
    ocr_table_index: int  # Порядковый номер таблицы в OCR (0-based)
) -> Optional[Tuple[Dict[str, Any], float]]:
    """
    Сопоставляет таблицу из OCR с таблицей из DOCX.
    
    Args:
        ocr_table: Таблица из OCR
        docx_tables: Список таблиц из DOCX
        page_num: Номер страницы
        used_docx_tables: Множество уже использованных индексов таблиц из DOCX
        ocr_table_index: Порядковый номер таблицы в OCR (0-based)
    
    Returns:
        Кортеж (docx_table, score) или None
    """
    best_match = None
    best_score = 0.0
    
    estimated_page = ocr_table.get('page_num', page_num)
    
    for docx_table in docx_tables:
        docx_idx = docx_table.get('index')
        if docx_idx in used_docx_tables:
            continue
        
        score = 0.0
        details = {}
        
        # 1. Сопоставление по порядку (если это первая таблица OCR, ищем первую доступную DOCX)
        # Учитываем, что первая таблица могла быть пропущена
        docx_order = len([t for t in docx_tables if t.get('index') < docx_idx and t.get('index') not in used_docx_tables])
        order_diff = abs(ocr_table_index - docx_order)
        if order_diff == 0:
            score += 0.4
            details['order_match'] = True
        elif order_diff == 1:
            score += 0.2  # Бонус за близость по порядку
            details['order_close'] = True
        
        # 2. Сопоставление по странице
        docx_estimated_page = docx_table.get('estimated_page', 1)
        page_diff = abs(estimated_page - docx_estimated_page)
        if page_diff == 0:
            score += 0.4
            details['page_exact'] = True
        elif page_diff == 1:
            score += 0.2
            details['page_close'] = True
        
        # 3. Бонус за подпись таблицы (если есть номер в подписи)
        caption_number = docx_table.get('caption_number')
        if caption_number is not None:
            # Если номер в подписи совпадает с порядковым номером (с учетом пропущенной первой)
            expected_number = ocr_table_index + 1  # OCR таблицы нумеруются с 1
            if caption_number == expected_number:
                score += 0.2
                details['caption_match'] = True
        
        # 4. Бонус за близость по позиции в XML (если таблицы идут подряд)
        if best_match is None or score > best_score:
            best_score = score
            best_match = (docx_table, score, details)
    
    # Снижаем порог, если таблиц в OCR больше, чем в DOCX (OCR может находить лишние)
    min_threshold = 0.25 if len(docx_tables) < len([t for t in docx_tables]) * 2 else 0.3
    
    if best_match and best_score >= min_threshold:
        return (best_match[0], best_score)
    
    return None


def match_ocr_image_to_docx_image(
    ocr_image: Dict[str, Any],
    docx_images: List[Dict[str, Any]],
    page_num: int,
    used_docx_images: set,
    ocr_image_index: int  # Порядковый номер изображения в OCR (0-based)
) -> Optional[Tuple[Dict[str, Any], float]]:
    """
    Сопоставляет изображение из OCR с изображением из DOCX.
    
    Args:
        ocr_image: Изображение из OCR
        docx_images: Список изображений из DOCX
        page_num: Номер страницы
        used_docx_images: Множество уже использованных индексов изображений из DOCX
        ocr_image_index: Порядковый номер изображения в OCR (0-based)
    
    Returns:
        Кортеж (docx_image, score) или None
    """
    best_match = None
    best_score = 0.0
    
    for docx_idx, docx_image in enumerate(docx_images):
        if docx_idx in used_docx_images:
            continue
        
        score = 0.0
        
        # 1. Сопоставление по порядку
        docx_order = len([img for i, img in enumerate(docx_images) if i < docx_idx and i not in used_docx_images])
        if ocr_image_index == docx_order:
            score += 0.5
        
        # 2. Сопоставление по странице (эвристика: ~50 элементов на страницу)
        docx_estimated_page = docx_image.get('xml_position', 0) // 50 + 1
        page_diff = abs(page_num + 1 - docx_estimated_page)
        if page_diff == 0:
            score += 0.3
        elif page_diff == 1:
            score += 0.15
        
        # 3. Бонус за близость по позиции в XML
        if docx_idx == ocr_image_index:
            score += 0.2
        
        if score > best_score:
            best_score = score
            best_match = (docx_image, score)
    
    if best_match and best_score >= 0.3:  # Минимальный порог
        return best_match
    
    return None


def process_layout_matching_pipeline(
    docx_path: Path,
    output_dir: Path,
    skip_first_table: bool = False  # Для Diplom2024
) -> Dict[str, Any]:
    """
    Основная функция пайплайна сопоставления layout detection с DOCX XML.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        skip_first_table: Пропустить первую таблицу (для Diplom2024)
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*80}")
    print(f"ПАЙПЛАЙН СОПОСТАВЛЕНИЯ LAYOUT DETECTION С DOCX XML")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    matches_dir = output_dir / "matches"
    matches_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Извлекаем таблицы и изображения из DOCX XML
    print("Шаг 1: Извлечение таблиц и изображений из DOCX XML...")
    docx_tables = extract_tables_from_docx_xml(docx_path)
    docx_images = extract_images_from_docx_xml(docx_path)
    
    # Фильтруем валидные таблицы и находим подписи
    valid_docx_tables = []
    for table in docx_tables:
        table_caption_info = find_table_caption_before_table(docx_path, table.get('xml_position'))
        table_caption_text = table_caption_info.get('text') if table_caption_info else None
        table_caption_number = table_caption_info.get('number') if table_caption_info else None
        
        if is_valid_table(table, table_caption_text):
            table['caption'] = table_caption_text
            table['caption_number'] = table_caption_number
            table['caption_info'] = table_caption_info
            valid_docx_tables.append(table)
        else:
            print(f"  ⚠ Пропущена невалидная таблица #{table.get('index') + 1}")
    
    # Пропускаем первую таблицу, если нужно
    if skip_first_table and valid_docx_tables:
        skipped = valid_docx_tables.pop(0)
        print(f"  ⚠ Пропущена первая таблица (по запросу): #{skipped.get('index') + 1}")
    
    print(f"  ✓ Найдено таблиц в DOCX: {len(valid_docx_tables)}")
    print(f"  ✓ Найдено изображений в DOCX: {len(docx_images)}\n")
    
    # Шаг 2: Конвертируем DOCX в PDF
    print("Шаг 2: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}\n")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        return {"error": str(e)}
    
    # Шаг 3: Layout detection через DOTS OCR
    print("Шаг 3: Layout detection через DOTS OCR...")
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_doc)
    
    ocr_tables = []
    ocr_images = []
    ocr_headers = []  # Section-header из OCR
    
    for page_num in range(total_pages):
        print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            continue
        
        try:
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image
            )
            
            if success and layout_cells:
                for element in layout_cells:
                    category = element.get("category", "")
                    bbox = element.get("bbox", [])
                    
                    if category == "Table":
                        element["page_num"] = page_num
                        ocr_tables.append(element)
                    elif category == "Picture":
                        element["page_num"] = page_num
                        ocr_images.append(element)
                    elif category == "Section-header":
                        element["page_num"] = page_num
                        ocr_headers.append(element)
        
        except Exception as e:
            print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    pdf_doc.close()
    
    print(f"  ✓ Найдено таблиц в OCR: {len(ocr_tables)}")
    print(f"  ✓ Найдено изображений в OCR: {len(ocr_images)}")
    print(f"  ✓ Найдено Section-header в OCR: {len(ocr_headers)}\n")
    
    # Извлекаем весь текст из DOCX для поиска
    import zipfile
    import xml.etree.ElementTree as ET
    import re
    
    docx_all_text = []
    docx_text_positions = []  # Позиции текста в XML
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            body = root.find('w:body', NAMESPACES)
            if body is not None:
                all_elements = list(body)
                for elem_idx, elem in enumerate(all_elements):
                    if elem.tag.endswith('}p'):
                        text = extract_text_from_element(elem, NAMESPACES)
                        if text.strip():
                            docx_all_text.append(text.strip())
                            docx_text_positions.append(elem_idx)
    except Exception as e:
        print(f"  Предупреждение: не удалось извлечь текст из DOCX: {e}")
    
    # Шаг 4: Сопоставление таблиц через Section-header
    print("Шаг 4: Сопоставление таблиц OCR с DOCX через Section-header...")
    
    table_matches = []
    used_docx_tables = set()
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    
    for ocr_idx, ocr_table in enumerate(ocr_tables):
        page_num = ocr_table.get('page_num', 0)
        table_bbox = ocr_table.get('bbox', [])
        
        if not table_bbox or len(table_bbox) < 4:
            continue
        
        # Ищем ближайший Section-header перед этой таблицей на той же странице
        # Также проверяем предыдущие страницы (до 2 страниц назад)
        matching_header = None
        header_text = None
        
        for header in ocr_headers:
            header_page = header.get('page_num')
            # Проверяем текущую страницу и предыдущие (до 2 страниц назад)
            if header_page <= page_num and header_page >= max(0, page_num - 2):
                header_bbox = header.get('bbox', [])
                if header_bbox and len(header_bbox) >= 4:
                    # Если заголовок на той же странице, проверяем позицию
                    if header_page == page_num:
                        # Проверяем, что заголовок выше таблицы
                        if header_bbox[3] < table_bbox[1]:  # y2 заголовка < y1 таблицы
                            if matching_header is None or header_bbox[3] > matching_header.get('bbox', [])[3]:
                                matching_header = header
                    else:
                        # Если заголовок на предыдущей странице, берем его (если еще не нашли на текущей)
                        if matching_header is None or matching_header.get('page_num') == page_num:
                            matching_header = header
        
        # Если нашли заголовок, извлекаем текст и ищем упоминание таблицы
        if matching_header:
            try:
                header_page_num = matching_header.get('page_num')
                page = pdf_doc[header_page_num]
                header_bbox = matching_header.get('bbox', [])
                if header_bbox and len(header_bbox) >= 4:
                    rect = fitz.Rect(header_bbox)
                    header_text = page.get_text("text", clip=rect).strip()
                    
                    # Если текст пустой, пробуем извлечь без ограничения по bbox (весь текст страницы)
                    if not header_text:
                        # Пробуем найти текст в области заголовка с небольшим расширением
                        expanded_rect = fitz.Rect(
                            max(0, header_bbox[0] - 50),
                            max(0, header_bbox[1] - 20),
                            min(page.rect.width, header_bbox[2] + 50),
                            min(page.rect.height, header_bbox[3] + 20)
                        )
                        header_text = page.get_text("text", clip=expanded_rect).strip()
                    
                    # Ищем упоминание таблицы в заголовке (например, "Таблица 1", "Table 1")
                    table_match = re.search(r'(таблица|table)\s*(\d+)', header_text, re.IGNORECASE)
                    if table_match:
                        table_number = int(table_match.group(2))
                        
                        # Ищем этот текст в DOCX
                        search_text = f"Таблица {table_number}"
                        search_text_alt = f"Table {table_number}"
                        
                        # Ищем в тексте DOCX
                        found_text_idx = None
                        for text_idx, text in enumerate(docx_all_text):
                            if search_text in text or search_text_alt in text:
                                found_text_idx = text_idx
                                break
                        
                        if found_text_idx is not None:
                            # Ищем ближайшую таблицу после этого текста
                            found_xml_position = docx_text_positions[found_text_idx]
                            
                            best_table = None
                            min_distance = float('inf')
                            
                            # ⭐ ВАЖНО: Сначала ищем таблицу с точным номером в подписи
                            for docx_table in valid_docx_tables:
                                docx_idx = docx_table.get('index')
                                if docx_idx in used_docx_tables:
                                    continue
                                
                                # Проверяем, совпадает ли номер в подписи
                                docx_caption_number = docx_table.get('caption_number')
                                if docx_caption_number == table_number:
                                    # Точное совпадение номера - это наша таблица!
                                    best_table = docx_table
                                    min_distance = 0
                                    break
                            
                            # Если не нашли по номеру, ищем ближайшую после текста
                            if best_table is None:
                                for docx_table in valid_docx_tables:
                                    docx_idx = docx_table.get('index')
                                    if docx_idx in used_docx_tables:
                                        continue
                                    
                                    # Получаем позицию таблицы в XML
                                    table_xml_pos = docx_table.get('xml_position')
                                    if table_xml_pos is not None and table_xml_pos > found_xml_position:
                                        # Таблица должна быть после текста
                                        distance = table_xml_pos - found_xml_position
                                        if distance < min_distance:
                                            min_distance = distance
                                            best_table = docx_table
                            
                            if best_table and min_distance < 50:  # Максимальное расстояние (50 элементов)
                                docx_idx = best_table.get('index')
                                used_docx_tables.add(docx_idx)
                                
                                table_caption = best_table.get('caption', 'нет подписи')
                                table_caption_number = best_table.get('caption_number')
                                
                                match_method = 'section_header_exact' if min_distance == 0 else 'section_header'
                                print(f"  ✓ Таблица OCR #{ocr_idx + 1} (стр. {page_num + 1}) → DOCX #{docx_idx + 1} (через Section-header: '{header_text[:60]}...', номер: {table_number})")
                                if table_caption:
                                    caption_display = table_caption[:80] + "..." if len(table_caption) > 80 else table_caption
                                    print(f"    Подпись: {caption_display}")
                                
                                table_matches.append({
                                    'ocr_index': ocr_idx + 1,
                                    'ocr_page': page_num + 1,
                                    'ocr_bbox': ocr_table.get('bbox'),
                                    'docx_index': docx_idx + 1,
                                    'docx_xml_position': best_table.get('xml_position'),
                                    'docx_caption': table_caption,
                                    'docx_caption_number': table_caption_number,
                                    'score': 0.95,  # Высокий score для совпадения через заголовок
                                    'match_method': match_method,
                                    'section_header_text': header_text,
                                    'expected_table_number': table_number,
                                    'docx_table': best_table
                                })
                                continue  # Переходим к следующей таблице OCR
            except Exception as e:
                print(f"    Предупреждение: ошибка при обработке заголовка: {e}")
        
        # Если не нашли через Section-header, используем улучшенный метод
        # Сначала пытаемся найти по порядку с учетом уже найденных таблиц
        match_result = None
        
        # Определяем ожидаемый номер таблицы на основе уже найденных
        expected_table_number = None
        if table_matches:
            # Находим последнюю найденную таблицу с номером
            last_match = table_matches[-1]
            last_caption_number = last_match.get('docx_caption_number')
            if last_caption_number is not None:
                expected_table_number = last_caption_number + 1
        
        # Если есть ожидаемый номер, ищем таблицу с этим номером
        if expected_table_number is not None:
            for docx_table in valid_docx_tables:
                docx_idx = docx_table.get('index')
                if docx_idx in used_docx_tables:
                    continue
                
                docx_caption_number = docx_table.get('caption_number')
                if docx_caption_number == expected_table_number:
                    # Нашли таблицу с ожидаемым номером!
                    match_result = (docx_table, 0.85)  # Высокий score за точное совпадение номера
                    break
        
        # Если не нашли по номеру, используем старый метод
        if match_result is None:
            match_result = match_ocr_table_to_docx_table(
                ocr_table,
                valid_docx_tables,
                page_num,
                used_docx_tables,
                ocr_idx
            )
        
        if match_result:
            docx_table, score = match_result
            docx_idx = docx_table.get('index')
            used_docx_tables.add(docx_idx)
            
            table_caption = docx_table.get('caption', 'нет подписи')
            table_caption_number = docx_table.get('caption_number')
            
            match_method = 'expected_number' if expected_table_number and table_caption_number == expected_table_number else 'order_and_page'
            
            print(f"  ✓ Таблица OCR #{ocr_idx + 1} (стр. {page_num + 1}) → DOCX #{docx_idx + 1} (score: {score:.2%}, метод: {match_method})")
            if table_caption:
                caption_display = table_caption[:80] + "..." if len(table_caption) > 80 else table_caption
                print(f"    Подпись: {caption_display}")
            if table_caption_number:
                print(f"    Номер таблицы: {table_caption_number}")
            if expected_table_number and table_caption_number != expected_table_number:
                print(f"    ⚠ Ожидался номер {expected_table_number}, но найден {table_caption_number}")
            
            table_matches.append({
                'ocr_index': ocr_idx + 1,
                'ocr_page': page_num + 1,
                'ocr_bbox': ocr_table.get('bbox'),
                'docx_index': docx_idx + 1,
                'docx_xml_position': docx_table.get('xml_position'),
                'docx_caption': table_caption,
                'docx_caption_number': table_caption_number,
                'score': score,
                'match_method': match_method,
                'expected_table_number': expected_table_number,
                'docx_table': docx_table
            })
        else:
            print(f"  ⚠ Таблица OCR #{ocr_idx + 1} (стр. {page_num + 1}) → не найдено совпадение")
            if expected_table_number:
                print(f"    Ожидался номер таблицы: {expected_table_number}")
    
    pdf_doc.close()
    print()
    
    # Шаг 5: Сопоставление изображений
    print("Шаг 5: Сопоставление изображений OCR с DOCX...")
    
    image_matches = []
    used_docx_images = set()
    
    for ocr_idx, ocr_image in enumerate(ocr_images):
        page_num = ocr_image.get('page_num', 0)
        
        match_result = match_ocr_image_to_docx_image(
            ocr_image,
            docx_images,
            page_num,
            used_docx_images,
            ocr_idx  # Порядковый номер изображения в OCR
        )
        
        if match_result:
            docx_image, score = match_result
            docx_idx = docx_images.index(docx_image)
            used_docx_images.add(docx_idx)
            
            print(f"  ✓ Изображение OCR #{ocr_idx + 1} (стр. {page_num + 1}) → DOCX #{docx_idx + 1} (score: {score:.2%})")
            
            image_matches.append({
                'ocr_index': ocr_idx + 1,
                'ocr_page': page_num + 1,
                'ocr_bbox': ocr_image.get('bbox'),
                'docx_index': docx_idx + 1,
                'docx_xml_position': docx_image.get('xml_position'),
                'docx_image_path': docx_image.get('image_path'),
                'score': score,
                'docx_image': docx_image
            })
        else:
            print(f"  ⚠ Изображение OCR #{ocr_idx + 1} (стр. {page_num + 1}) → не найдено совпадение")
    
    print()
    
    # Шаг 6: Сохранение результатов
    print("Шаг 6: Сохранение результатов...")
    
    results = {
        'docx_file': str(docx_path),
        'docx_tables_count': len(valid_docx_tables),
        'docx_images_count': len(docx_images),
        'ocr_tables_count': len(ocr_tables),
        'ocr_images_count': len(ocr_images),
        'table_matches_count': len(table_matches),
        'image_matches_count': len(image_matches),
        'table_matches': table_matches,
        'image_matches': image_matches
    }
    
    results_json_path = matches_dir / "matches.json"
    with open(results_json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"  ✓ Результаты сохранены: {results_json_path}")
    
    # Создаем отчет
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("ОТЧЕТ О СОПОСТАВЛЕНИИ LAYOUT DETECTION С DOCX XML")
    report_lines.append("=" * 80)
    report_lines.append(f"\nDOCX файл: {docx_path.name}")
    report_lines.append(f"Таблиц в DOCX: {len(valid_docx_tables)}")
    report_lines.append(f"Изображений в DOCX: {len(docx_images)}")
    report_lines.append(f"Таблиц в OCR: {len(ocr_tables)}")
    report_lines.append(f"Изображений в OCR: {len(ocr_images)}")
    report_lines.append(f"Сопоставлено таблиц: {len(table_matches)}")
    report_lines.append(f"Сопоставлено изображений: {len(image_matches)}")
    report_lines.append("\n" + "=" * 80)
    report_lines.append("СОПОСТАВЛЕНИЯ ТАБЛИЦ:")
    report_lines.append("=" * 80 + "\n")
    
    for match in table_matches:
        report_lines.append(f"OCR Таблица #{match['ocr_index']} (стр. {match['ocr_page']}) → DOCX Таблица #{match['docx_index']}")
        if match['docx_caption']:
            report_lines.append(f"  Подпись: {match['docx_caption']}")
        report_lines.append(f"  Score: {match['score']:.2%}")
        report_lines.append("")
    
    report_lines.append("=" * 80)
    report_lines.append("СОПОСТАВЛЕНИЯ ИЗОБРАЖЕНИЙ:")
    report_lines.append("=" * 80 + "\n")
    
    for match in image_matches:
        report_lines.append(f"OCR Изображение #{match['ocr_index']} (стр. {match['ocr_page']}) → DOCX Изображение #{match['docx_index']}")
        report_lines.append(f"  Путь в DOCX: {match['docx_image_path']}")
        report_lines.append("")
    
    report_path = matches_dir / "report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"  ✓ Отчет сохранен: {report_path}\n")
    
    print(f"{'='*80}")
    print(f"ИТОГО:")
    print(f"  Таблиц сопоставлено: {len(table_matches)}/{len(ocr_tables)}")
    print(f"  Изображений сопоставлено: {len(image_matches)}/{len(ocr_images)}")
    print(f"{'='*80}\n")
    
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python docx_layout_matching_pipeline.py <docx_path> [output_dir] [--skip-first-table]")
        print("\nПримеры:")
        print("  python docx_layout_matching_pipeline.py test_folder/Диплом.docx")
        print("  python docx_layout_matching_pipeline.py test_folder/Diplom2024.docx --skip-first-table")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    # Определяем выходную директорию
    if len(sys.argv) >= 3 and not sys.argv[2].startswith('--'):
        output_dir = Path(sys.argv[2])
    else:
        output_dir = Path(__file__).parent / "results" / "layout_matching" / docx_path.stem
    
    # Проверяем флаг --skip-first-table
    skip_first_table = '--skip-first-table' in sys.argv or 'Diplom2024' in docx_path.name
    
    result = process_layout_matching_pipeline(docx_path, output_dir, skip_first_table=skip_first_table)
    
    if "error" in result:
        print(f"\n✗ Ошибка: {result['error']}")
        sys.exit(1)
    
    print(f"\n✓ Пайплайн завершен успешно!")
