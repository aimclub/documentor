"""
Финальный пайплайн для DOCX: DOTS OCR для структуры, XML для данных.

Идея:
1. DOTS OCR определяет структуру (Section-header, подписи к таблицам/изображениям)
2. Все данные (текст, таблицы, изображения) парсятся напрямую из XML в правильном порядке
3. Строится иерархия на основе заголовков из OCR
4. Сопоставление таблиц/изображений через подписи из OCR
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO
import re

from PIL import Image
import fitz  # PyMuPDF

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_xml_parser import (
    extract_images_from_docx_xml,
    extract_tables_from_docx_xml,
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


def extract_all_elements_from_docx_xml(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Извлекает ВСЕ элементы из DOCX XML в порядке появления.
    
    Returns:
        Список элементов с типами: 'paragraph', 'table', 'image'
    """
    import zipfile
    import xml.etree.ElementTree as ET
    
    elements = []
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            body = root.find('w:body', NAMESPACES)
            if body is None:
                return []
            
            all_elements = list(body)
            
            for elem_idx, elem in enumerate(all_elements):
                if elem.tag.endswith('}p'):  # Параграф
                    text = extract_text_from_element(elem, NAMESPACES)
                    if text.strip():
                        elements.append({
                            'type': 'paragraph',
                            'xml_position': elem_idx,
                            'text': text.strip(),
                            'element': elem
                        })
                elif elem.tag.endswith('}tbl'):  # Таблица
                    elements.append({
                        'type': 'table',
                        'xml_position': elem_idx,
                        'element': elem
                    })
                # Изображения находятся внутри параграфов, их обрабатываем отдельно
    
    except Exception as e:
        print(f"  Ошибка при извлечении элементов из XML: {e}")
    
    return elements


def find_table_caption_in_ocr_headers(
    ocr_headers: List[Dict[str, Any]],
    ocr_captions: List[Dict[str, Any]],
    table_bbox: List[float],
    table_page: int,
    pdf_doc: fitz.Document
) -> Optional[Dict[str, Any]]:
    """
    Находит подпись таблицы в Section-header или Caption из OCR.
    
    Args:
        ocr_headers: Список заголовков из OCR
        ocr_captions: Список подписей из OCR
        table_bbox: Координаты таблицы
        table_page: Номер страницы таблицы
        pdf_doc: PDF документ
    
    Returns:
        Информация о подписи или None
    """
    if not table_bbox or len(table_bbox) < 4:
        return None
    
    # Сначала ищем в Caption (более точно)
    all_candidates = ocr_captions + ocr_headers
    
    # Ищем ближайший Caption/Section-header перед таблицей
    matching_element = None
    min_distance = float('inf')
    
    for candidate in all_candidates:
        candidate_page = candidate.get('page_num')
        if candidate_page <= table_page and candidate_page >= max(0, table_page - 2):
            candidate_bbox = candidate.get('bbox', [])
            if candidate_bbox and len(candidate_bbox) >= 4:
                if candidate_page == table_page:
                    # На той же странице - проверяем позицию
                    if candidate_bbox[3] < table_bbox[1]:  # Элемент выше таблицы
                        # Вычисляем расстояние
                        distance = table_bbox[1] - candidate_bbox[3]
                        if distance < min_distance:
                            min_distance = distance
                            matching_element = candidate
                else:
                    # На предыдущей странице - приоритет ниже
                    if matching_element is None or matching_element.get('page_num') == table_page:
                        matching_element = candidate
    
    if matching_element:
        try:
            element_page_num = matching_element.get('page_num')
            page = pdf_doc[element_page_num]
            element_bbox = matching_element.get('bbox', [])
            
            if element_bbox and len(element_bbox) >= 4:
                rect = fitz.Rect(element_bbox)
                element_text = page.get_text("text", clip=rect).strip()
                
                # Если текст пустой, расширяем область
                if not element_text:
                    expanded_rect = fitz.Rect(
                        max(0, element_bbox[0] - 50),
                        max(0, element_bbox[1] - 20),
                        min(page.rect.width, element_bbox[2] + 50),
                        min(page.rect.height, element_bbox[3] + 20)
                    )
                    element_text = page.get_text("text", clip=expanded_rect).strip()
                
                # Ищем упоминание таблицы
                table_match = re.search(r'(таблица|table)\s*(\d+)', element_text, re.IGNORECASE)
                if table_match:
                    table_number = int(table_match.group(2))
                    return {
                        'text': element_text,
                        'table_number': table_number,
                        'bbox': element_bbox,
                        'page': element_page_num,
                        'type': 'caption' if matching_element in ocr_captions else 'header'
                    }
        except Exception:
            pass
    
    return None


def find_image_caption_in_ocr_headers(
    ocr_headers: List[Dict[str, Any]],
    ocr_captions: List[Dict[str, Any]],
    image_bbox: List[float],
    image_page: int,
    pdf_doc: fitz.Document
) -> Optional[Dict[str, Any]]:
    """
    Находит подпись изображения в Section-header или Caption из OCR.
    
    Args:
        ocr_headers: Список заголовков из OCR
        ocr_captions: Список подписей из OCR
        image_bbox: Координаты изображения
        image_page: Номер страницы изображения
        pdf_doc: PDF документ
    
    Returns:
        Информация о подписи или None
    """
    if not image_bbox or len(image_bbox) < 4:
        return None
    
    # Сначала ищем в Caption (более точно)
    all_candidates = ocr_captions + ocr_headers
    
    # Ищем ближайший Caption/Section-header перед/после изображения
    matching_element = None
    min_distance = float('inf')
    
    for candidate in all_candidates:
        candidate_page = candidate.get('page_num')
        if candidate_page == image_page:
            candidate_bbox = candidate.get('bbox', [])
            if candidate_bbox and len(candidate_bbox) >= 4:
                # Элемент может быть выше или ниже изображения
                if candidate_bbox[3] < image_bbox[1]:  # Выше изображения
                    distance = image_bbox[1] - candidate_bbox[3]
                elif candidate_bbox[1] > image_bbox[3]:  # Ниже изображения
                    distance = candidate_bbox[1] - image_bbox[3]
                else:
                    continue  # Пересекается - пропускаем
                
                if distance < min_distance:
                    min_distance = distance
                    matching_element = candidate
    
    if matching_element:
        try:
            element_page_num = matching_element.get('page_num')
            page = pdf_doc[element_page_num]
            element_bbox = matching_element.get('bbox', [])
            
            if element_bbox and len(element_bbox) >= 4:
                rect = fitz.Rect(element_bbox)
                element_text = page.get_text("text", clip=rect).strip()
                
                if not element_text:
                    expanded_rect = fitz.Rect(
                        max(0, element_bbox[0] - 50),
                        max(0, element_bbox[1] - 20),
                        min(page.rect.width, element_bbox[2] + 50),
                        min(page.rect.height, element_bbox[3] + 20)
                    )
                    element_text = page.get_text("text", clip=expanded_rect).strip()
                
                # Ищем упоминание рисунка/изображения
                if re.search(r'(рисунок|рис\.|figure|image|изображение)', element_text, re.IGNORECASE):
                    # Пытаемся извлечь номер
                    number_match = re.search(r'(\d+)', element_text)
                    image_number = int(number_match.group(1)) if number_match else None
                    
                    return {
                        'text': element_text,
                        'image_number': image_number,
                        'bbox': element_bbox,
                        'page': element_page_num,
                        'type': 'caption' if matching_element in ocr_captions else 'header'
                    }
        except Exception:
            pass
    
    return None


def determine_header_level_from_ocr(
    header: Dict[str, Any],
    previous_headers: List[Dict[str, Any]],
    pdf_doc: fitz.Document
) -> int:
    """
    Определяет уровень заголовка на основе OCR данных.
    
    Args:
        header: Заголовок из OCR
        previous_headers: Предыдущие заголовки
        pdf_doc: PDF документ
    
    Returns:
        Уровень заголовка (1-6)
    """
    # Приоритет 1: Анализ нумерации в тексте
    try:
        page = pdf_doc[header.get('page_num', 0)]
        header_bbox = header.get('bbox', [])
        if header_bbox and len(header_bbox) >= 4:
            rect = fitz.Rect(header_bbox)
            header_text = page.get_text("text", clip=rect).strip()
            
            # Нумерация: "1", "1.1", "1.1.1" и т.д.
            if re.match(r'^\d+\s+[A-ZА-ЯЁ]', header_text):
                return 1
            if re.match(r'^\d+\.\d+\s+', header_text):
                return 2
            if re.match(r'^\d+\.\d+\.\d+\s+', header_text):
                return 3
            if re.match(r'^\d+\.\d+\.\d+\.\d+\s+', header_text):
                return 4
    except Exception:
        pass
    
    # Приоритет 2: Размер шрифта (если доступен)
    # TODO: извлечь размер шрифта из PDF
    
    # Приоритет 3: Позиция слева (левее = выше уровень)
    if previous_headers:
        current_x = header.get('bbox', [0])[0] if header.get('bbox') else 0
        for prev_header in reversed(previous_headers):
            prev_x = prev_header.get('bbox', [0])[0] if prev_header.get('bbox') else 0
            prev_level = prev_header.get('level', 1)
            
            if current_x < prev_x - 20:  # Значительное смещение влево
                return max(1, prev_level - 1)
            elif current_x > prev_x + 20:  # Смещение вправо
                return min(6, prev_level + 1)
            else:
                return prev_level
    
    return 1


def process_final_docx_pipeline(
    docx_path: Path,
    output_dir: Path,
    skip_first_table: bool = False
) -> Dict[str, Any]:
    """
    Финальный пайплайн: DOTS OCR для структуры, XML для данных.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        skip_first_table: Пропустить первую таблицу (для Diplom2024)
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*80}")
    print(f"ФИНАЛЬНЫЙ ПАЙПЛАЙН: DOTS OCR (структура) + XML (данные)")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    structure_dir = output_dir / "structure"
    structure_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Извлекаем все данные из DOCX XML
    print("Шаг 1: Извлечение данных из DOCX XML...")
    docx_tables = extract_tables_from_docx_xml(docx_path)
    docx_images = extract_images_from_docx_xml(docx_path)
    docx_elements = extract_all_elements_from_docx_xml(docx_path)
    
    # Фильтруем валидные таблицы
    valid_docx_tables = []
    for table in docx_tables:
        rows = table.get('rows', [])
        if len(rows) >= 2 and table.get('cols_count', 0) >= 2:
            valid_docx_tables.append(table)
    
    if skip_first_table and valid_docx_tables:
        skipped = valid_docx_tables.pop(0)
        print(f"  ⚠ Пропущена первая таблица: #{skipped.get('index') + 1}")
    
    print(f"  ✓ Найдено таблиц в DOCX: {len(valid_docx_tables)}")
    print(f"  ✓ Найдено изображений в DOCX: {len(docx_images)}")
    print(f"  ✓ Найдено элементов в DOCX: {len(docx_elements)}\n")
    
    # Шаг 2: Конвертируем DOCX в PDF
    print("Шаг 2: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}\n")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        return {"error": str(e)}
    
    # Шаг 3: Layout detection через DOTS OCR для структуры
    print("Шаг 3: Layout detection через DOTS OCR (структура)...")
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_doc)
    
    ocr_headers = []  # Section-header для иерархии
    ocr_captions = []  # Caption для подписей
    ocr_tables = []  # Таблицы для сопоставления
    ocr_images = []  # Изображения для сопоставления
    ocr_formulas = []  # Формулы (чтобы исключить их из таблиц)
    
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
                    element["page_num"] = page_num
                    
                    if category == "Section-header":
                        ocr_headers.append(element)
                    elif category == "Caption":
                        ocr_captions.append(element)
                    elif category == "Formula":
                        ocr_formulas.append(element)  # Формулы - не таблицы!
                    elif category == "Table":
                        ocr_tables.append(element)
                    elif category == "Picture":
                        ocr_images.append(element)
        
        except Exception as e:
            print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    print(f"  ✓ Найдено Section-header: {len(ocr_headers)}")
    print(f"  ✓ Найдено Caption: {len(ocr_captions)}")
    print(f"  ✓ Найдено формул: {len(ocr_formulas)}")
    print(f"  ✓ Найдено таблиц: {len(ocr_tables)}")
    print(f"  ✓ Найдено изображений: {len(ocr_images)}\n")
    
    # Шаг 4: Определяем уровни заголовков из OCR
    print("Шаг 4: Определение уровней заголовков из OCR...")
    
    previous_headers = []
    for header in ocr_headers:
        level = determine_header_level_from_ocr(header, previous_headers, pdf_doc)
        header['level'] = level
        previous_headers.append(header)
    
    print(f"  ✓ Определены уровни для {len(ocr_headers)} заголовков\n")
    
    # Шаг 5: Фильтрация таблиц - исключаем формулы и изображения
    print("Шаг 5: Фильтрация таблиц (исключение формул и изображений)...")
    
    # Проверяем, не является ли таблица формулой
    filtered_ocr_tables = []
    for ocr_table in ocr_tables:
        table_page = ocr_table.get('page_num', 0)
        table_bbox = ocr_table.get('bbox', [])
        
        # Проверяем, нет ли рядом формулы
        is_formula = False
        for formula in ocr_formulas:
            formula_page = formula.get('page_num', 0)
            if formula_page == table_page:
                formula_bbox = formula.get('bbox', [])
                if formula_bbox and len(formula_bbox) >= 4 and table_bbox and len(table_bbox) >= 4:
                    # Проверяем пересечение bbox
                    if not (table_bbox[2] < formula_bbox[0] or table_bbox[0] > formula_bbox[2] or
                            table_bbox[3] < formula_bbox[1] or table_bbox[1] > formula_bbox[3]):
                        is_formula = True
                        break
        
        if not is_formula:
            filtered_ocr_tables.append(ocr_table)
        else:
            print(f"  ⚠ Исключена таблица OCR (стр. {table_page + 1}) - это формула")
    
    print(f"  ✓ После фильтрации: {len(filtered_ocr_tables)} таблиц (исключено {len(ocr_tables) - len(filtered_ocr_tables)} формул)\n")
    
    # Шаг 6: Извлечение подписей таблиц из DOCX XML
    print("Шаг 6: Извлечение подписей таблиц из DOCX XML...")
    
    # Предварительно извлекаем подписи для всех таблиц в DOCX
    docx_table_captions = {}  # {docx_index: {'number': X, 'text': '...'}}
    
    import zipfile
    import xml.etree.ElementTree as ET
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            body = root.find('w:body', NAMESPACES)
            if body:
                all_elements = list(body)
                
                for docx_table in valid_docx_tables:
                    docx_idx = docx_table.get('index')
                    table_xml_pos = docx_table.get('xml_position')
                    
                    if table_xml_pos is not None:
                        # Ищем подпись перед таблицей
                        for i in range(max(0, table_xml_pos - 5), table_xml_pos):
                            elem = all_elements[i]
                            if elem.tag.endswith('}p'):
                                text = extract_text_from_element(elem, NAMESPACES).strip()
                                text_lower = text.lower()
                                
                                # Паттерны: "Таблица 1. ...", "Table 1. ..."
                                pattern = r'(таблица|table)\s*(\d+)'
                                match = re.search(pattern, text_lower, re.IGNORECASE)
                                if match:
                                    table_number = int(match.group(2))
                                    docx_table_captions[docx_idx] = {
                                        'number': table_number,
                                        'text': text,
                                        'xml_position': i
                                    }
                                    break
    except Exception as e:
        print(f"  Предупреждение: ошибка при извлечении подписей: {e}")
    
    print(f"  ✓ Найдено подписей в DOCX: {len(docx_table_captions)}\n")
    
    # Шаг 7: Сопоставление таблиц через подписи из OCR
    print("Шаг 7: Сопоставление таблиц через подписи из OCR...")
    
    table_matches = []
    used_docx_tables = set()
    last_matched_table_number = 0
    
    for ocr_idx, ocr_table in enumerate(filtered_ocr_tables):
        page_num = ocr_table.get('page_num', 0)
        table_bbox = ocr_table.get('bbox', [])
        
        # Ищем подпись таблицы в OCR заголовках и подписях
        caption_info = find_table_caption_in_ocr_headers(
            ocr_headers,
            ocr_captions,
            table_bbox,
            page_num,
            pdf_doc
        )
        
        best_table = None
        match_method = None
        
        if caption_info and caption_info.get('table_number'):
            table_number = caption_info['table_number']
            
            # Ищем таблицу с этим номером в DOCX
            for docx_table in valid_docx_tables:
                docx_idx = docx_table.get('index')
                if docx_idx in used_docx_tables:
                    continue
                
                # Проверяем, есть ли подпись с таким номером
                if docx_idx in docx_table_captions:
                    if docx_table_captions[docx_idx]['number'] == table_number:
                        best_table = docx_table
                        match_method = f"подпись (Таблица {table_number})"
                        break
        
        # Если не нашли через подпись, пробуем найти следующую по порядку
        if not best_table:
            expected_number = last_matched_table_number + 1
            for docx_table in valid_docx_tables:
                docx_idx = docx_table.get('index')
                if docx_idx in used_docx_tables:
                    continue
                
                # Проверяем, соответствует ли номер ожидаемому
                if docx_idx in docx_table_captions:
                    if docx_table_captions[docx_idx]['number'] == expected_number:
                        best_table = docx_table
                        match_method = f"ожидаемый номер (Таблица {expected_number})"
                        break
        
        # Если всё ещё не нашли, используем порядок
        if not best_table:
            for docx_table in valid_docx_tables:
                docx_idx = docx_table.get('index')
                if docx_idx not in used_docx_tables:
                    best_table = docx_table
                    match_method = "по порядку"
                    break
        
        if best_table:
            docx_idx = best_table.get('index')
            used_docx_tables.add(docx_idx)
            
            # Обновляем последний сопоставленный номер
            if docx_idx in docx_table_captions:
                last_matched_table_number = docx_table_captions[docx_idx]['number']
            
            caption_text = caption_info['text'] if caption_info else (docx_table_captions.get(docx_idx, {}).get('text', ''))
            table_number = caption_info.get('table_number') if caption_info else docx_table_captions.get(docx_idx, {}).get('number')
            
            print(f"  ✓ Таблица OCR #{ocr_idx + 1} (стр. {page_num + 1}) → DOCX #{docx_idx + 1} ({match_method})")
            
            table_matches.append({
                'ocr_index': ocr_idx + 1,
                'ocr_page': page_num + 1,
                'docx_index': docx_idx + 1,
                'table_number': table_number,
                'caption': caption_text,
                'match_method': match_method,
                'docx_table': best_table
            })
        else:
            print(f"  ⚠ Таблица OCR #{ocr_idx + 1} (стр. {page_num + 1}) → не найдено совпадение")
    
    print()
    
    # Шаг 8: Сопоставление изображений через подписи из OCR
    print("Шаг 8: Сопоставление изображений через подписи из OCR...")
    
    image_matches = []
    used_docx_images = set()
    
    for ocr_idx, ocr_image in enumerate(ocr_images):
        page_num = ocr_image.get('page_num', 0)
        image_bbox = ocr_image.get('bbox', [])
        
        # Ищем подпись изображения
        caption_info = find_image_caption_in_ocr_headers(
            ocr_headers,
            ocr_captions,
            image_bbox,
            page_num,
            pdf_doc
        )
        
        # Простое сопоставление по порядку (можно улучшить через подписи)
        for docx_idx, docx_image in enumerate(docx_images):
            if docx_idx not in used_docx_images:
                used_docx_images.add(docx_idx)
                caption_text = caption_info['text'] if caption_info else None
                match_method = "подпись" if caption_info else "по порядку"
                
                print(f"  ✓ Изображение OCR #{ocr_idx + 1} (стр. {page_num + 1}) → DOCX #{docx_idx + 1} ({match_method})")
                
                image_matches.append({
                    'ocr_index': ocr_idx + 1,
                    'ocr_page': page_num + 1,
                    'docx_index': docx_idx + 1,
                    'caption': caption_text,
                    'image_number': caption_info.get('image_number') if caption_info else None,
                    'match_method': match_method,
                    'docx_image': docx_image
                })
                break
        else:
            print(f"  ⚠ Изображение OCR #{ocr_idx + 1} (стр. {page_num + 1}) → не найдено совпадение")
    
    print()
    
    # Шаг 9: Построение иерархии на основе заголовков из OCR
    print("Шаг 9: Построение иерархии на основе заголовков из OCR...")
    
    hierarchy = []
    current_section = None
    
    for header in ocr_headers:
        level = header.get('level', 1)
        
        # Если уровень меньше или равен предыдущему, закрываем текущую секцию
        if current_section and level <= current_section.get('level', 1):
            hierarchy.append(current_section)
            current_section = None
        
        # Создаем новую секцию
        if current_section is None:
            current_section = {
                'level': level,
                'header': header,
                'children': []
            }
        else:
            # Добавляем как дочерний элемент
            current_section['children'].append({
                'level': level,
                'header': header
            })
    
    if current_section:
        hierarchy.append(current_section)
    
    print(f"  ✓ Построена иерархия: {len(hierarchy)} секций\n")
    
    # Шаг 10: Сохранение результатов
    print("Шаг 10: Сохранение результатов...")
    
    results = {
        'docx_file': str(docx_path),
        'structure': {
            'headers_count': len(ocr_headers),
            'headers': ocr_headers,
            'hierarchy': hierarchy
        },
        'tables': {
            'docx_count': len(valid_docx_tables),
            'ocr_count': len(ocr_tables),
            'ocr_filtered_count': len(filtered_ocr_tables),
            'formulas_excluded': len(ocr_tables) - len(filtered_ocr_tables),
            'matches_count': len(table_matches),
            'matches': table_matches
        },
        'images': {
            'docx_count': len(docx_images),
            'ocr_count': len(ocr_images),
            'matches_count': len(image_matches),
            'matches': image_matches
        },
        'elements': {
            'total': len(docx_elements),
            'paragraphs': len([e for e in docx_elements if e['type'] == 'paragraph']),
            'tables': len([e for e in docx_elements if e['type'] == 'table'])
        }
    }
    
    results_json_path = structure_dir / "final_structure.json"
    with open(results_json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"  ✓ Результаты сохранены: {results_json_path}")
    
    # Создаем текстовый отчет
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("ФИНАЛЬНАЯ СТРУКТУРА ДОКУМЕНТА")
    report_lines.append("=" * 80)
    report_lines.append(f"\nDOCX файл: {docx_path.name}")
    report_lines.append(f"\nСТРУКТУРА (из DOTS OCR):")
    report_lines.append(f"  Заголовков: {len(ocr_headers)}")
    report_lines.append(f"  Секций в иерархии: {len(hierarchy)}")
    report_lines.append(f"\nТАБЛИЦЫ:")
    report_lines.append(f"  В DOCX: {len(valid_docx_tables)}")
    report_lines.append(f"  В OCR (всего): {len(ocr_tables)}")
    report_lines.append(f"  В OCR (после фильтрации формул): {len(filtered_ocr_tables)}")
    report_lines.append(f"  Исключено формул: {len(ocr_tables) - len(filtered_ocr_tables)}")
    report_lines.append(f"  Сопоставлено: {len(table_matches)}")
    report_lines.append(f"\nИЗОБРАЖЕНИЯ:")
    report_lines.append(f"  В DOCX: {len(docx_images)}")
    report_lines.append(f"  В OCR: {len(ocr_images)}")
    report_lines.append(f"  Сопоставлено: {len(image_matches)}")
    report_lines.append(f"\nЭЛЕМЕНТЫ (из XML):")
    report_lines.append(f"  Всего: {len(docx_elements)}")
    report_lines.append(f"  Параграфов: {len([e for e in docx_elements if e['type'] == 'paragraph'])}")
    report_lines.append(f"  Таблиц: {len([e for e in docx_elements if e['type'] == 'table'])}")
    
    report_path = structure_dir / "report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"  ✓ Отчет сохранен: {report_path}\n")
    
    pdf_doc.close()
    
    print(f"{'='*80}")
    print(f"ИТОГО:")
    print(f"  Заголовков: {len(ocr_headers)}")
    print(f"  Формул найдено: {len(ocr_formulas)}")
    print(f"  Таблиц в OCR: {len(ocr_tables)} → после фильтрации: {len(filtered_ocr_tables)}")
    print(f"  Таблиц сопоставлено: {len(table_matches)}/{len(filtered_ocr_tables)}")
    print(f"  Изображений сопоставлено: {len(image_matches)}/{len(ocr_images)}")
    print(f"{'='*80}\n")
    
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python docx_final_pipeline.py <docx_path> [output_dir] [--skip-first-table]")
        print("\nПримеры:")
        print("  python docx_final_pipeline.py test_folder/Диплом.docx")
        print("  python docx_final_pipeline.py test_folder/Diplom2024.docx --skip-first-table")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    # Определяем выходную директорию
    if len(sys.argv) >= 3 and not sys.argv[2].startswith('--'):
        output_dir = Path(sys.argv[2])
    else:
        output_dir = Path(__file__).parent / "results" / "final_pipeline" / docx_path.stem
    
    # Проверяем флаг --skip-first-table
    skip_first_table = '--skip-first-table' in sys.argv or 'Diplom2024' in docx_path.name
    
    result = process_final_docx_pipeline(docx_path, output_dir, skip_first_table=skip_first_table)
    
    if "error" in result:
        print(f"\n✗ Ошибка: {result['error']}")
        sys.exit(1)
    
    print(f"\n✓ Пайплайн завершен успешно!")
