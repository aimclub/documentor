"""
Пайплайн для DOCX: DOTS OCR (структура) + XML (данные) с построением иерархии.

Идея:
1. DOTS OCR определяет ТОЛЬКО структуру (Section-header, Caption) - для определения позиций
2. ВСЕ данные (текст, таблицы, изображения) извлекаются из XML
3. Сопоставляем OCR заголовки/подписи с XML для точного позиционирования
4. Строится иерархия на основе заголовков из OCR (но текст берется из XML)
5. Извлекаются элементы из XML с сохранением структуры:
   - Текстовые блоки (группируются параграфы, если < 10000 символов) - ВСЕ из XML
   - Заголовки (текст из XML, позиция из OCR)
   - Подписи к таблицам/изображениям (текст из XML, определение через OCR)
   - Таблицы (полная структура из XML)
   - Изображения (полные данные из XML)

Принцип: OCR для структуры, XML для данных!
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import re

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
MAX_TEXT_BLOCK_SIZE = 3000  # Максимальный размер текстового блока (разумный размер для обработки)
MIN_PARAGRAPHS_PER_BLOCK = 1  # Минимальное количество параграфов в блоке
MAX_PARAGRAPHS_PER_BLOCK = 10  # Максимальное количество параграфов в блоке (для логического разбиения)


def extract_all_elements_from_docx_xml_ordered(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Извлекает ВСЕ элементы из DOCX XML в порядке появления с полной информацией.
    Извлекает максимально полный текст без обрезания.
    
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
                    # Извлекаем весь текст максимально полно
                    # Используем более детальное извлечение для сохранения структуры
                    texts = []
                    for text_elem in elem.findall('.//w:t', NAMESPACES):
                        if text_elem.text:
                            texts.append(text_elem.text)
                        # Сохраняем пробелы между элементами
                        if text_elem.tail:
                            texts.append(text_elem.tail)
                    
                    # Объединяем весь текст
                    full_text = ''.join(texts)
                    
                    # Сохраняем параграф, если есть хоть какой-то текст
                    # (даже если это только пробелы - они могут быть важны)
                    if full_text.strip():  # Есть непустой текст
                        elements.append({
                            'type': 'paragraph',
                            'xml_position': elem_idx,
                            'text': full_text,  # Полный текст без обрезания
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


def find_headers_in_xml(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Находит все заголовки в DOCX XML.
    
    Returns:
        Список заголовков с текстом и позицией
    """
    import zipfile
    import xml.etree.ElementTree as ET
    
    headers = []
    
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
                    # Проверяем стиль заголовка
                    pPr = elem.find('w:pPr', NAMESPACES)
                    if pPr is not None:
                        pStyle = pPr.find('w:pStyle', NAMESPACES)
                        if pStyle is not None:
                            style_val = pStyle.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                            if 'Heading' in style_val or 'heading' in style_val.lower():
                                text = extract_text_from_element(elem, NAMESPACES)
                                if text.strip():
                                    # Определяем уровень заголовка
                                    level = 1
                                    if style_val:
                                        match = re.search(r'(\d+)', style_val)
                                        if match:
                                            level = int(match.group(1))
                                    
                                    headers.append({
                                        'xml_position': elem_idx,
                                        'text': text.strip(),
                                        'level': level,
                                        'style': style_val
                                    })
    
    except Exception as e:
        print(f"  Ошибка при поиске заголовков в XML: {e}")
    
    return headers


def match_ocr_header_to_xml_header(
    ocr_header: Dict[str, Any],
    xml_headers: List[Dict[str, Any]],
    pdf_doc: fitz.Document
) -> Optional[Dict[str, Any]]:
    """
    Сопоставляет заголовок из OCR с заголовком из XML.
    Использует OCR только для определения позиции, текст берется из XML.
    
    Args:
        ocr_header: Заголовок из OCR (только для определения позиции)
        xml_headers: Список заголовков из XML (источник полного текста)
        pdf_doc: PDF документ (для извлечения текста из OCR для сопоставления)
    
    Returns:
        Сопоставленный заголовок из XML или None
    """
    try:
        page = pdf_doc[ocr_header.get('page_num', 0)]
        header_bbox = ocr_header.get('bbox', [])
        
        if header_bbox and len(header_bbox) >= 4:
            # Расширяем область для извлечения текста
            expanded_rect = fitz.Rect(
                max(0, header_bbox[0] - 100),
                max(0, header_bbox[1] - 30),
                min(page.rect.width, header_bbox[2] + 100),
                min(page.rect.height, header_bbox[3] + 30)
            )
            
            ocr_text = page.get_text("text", clip=expanded_rect).strip()
            
            # Если текст все еще пустой, пробуем извлечь через слова
            if not ocr_text or len(ocr_text) < 3:
                text_dict = page.get_text("dict")
                words = []
                for block in text_dict.get("blocks", []):
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line.get("spans", []):
                                span_bbox = span.get("bbox", [])
                                if span_bbox and len(span_bbox) >= 4:
                                    if not (span_bbox[2] < header_bbox[0] or span_bbox[0] > header_bbox[2] or
                                            span_bbox[3] < header_bbox[1] or span_bbox[1] > header_bbox[3]):
                                        words.append(span.get("text", ""))
                
                if words:
                    ocr_text = " ".join(words).strip()
            
            # Если все еще пусто, используем исходную область
            if not ocr_text:
                rect = fitz.Rect(header_bbox)
                ocr_text = page.get_text("text", clip=rect).strip()
            
            # Нормализуем текст для сравнения
            ocr_text_normalized = re.sub(r'\s+', ' ', ocr_text.lower().strip())
            
            # Ищем наиболее похожий заголовок в XML
            best_match = None
            best_score = 0.0
            
            for xml_header in xml_headers:
                xml_text_normalized = re.sub(r'\s+', ' ', xml_header['text'].lower().strip())
                
                # Простое сравнение (можно улучшить через fuzzy matching)
                if ocr_text_normalized == xml_text_normalized:
                    return xml_header
                
                # Частичное совпадение
                if ocr_text_normalized in xml_text_normalized or xml_text_normalized in ocr_text_normalized:
                    score = min(len(ocr_text_normalized), len(xml_text_normalized)) / max(len(ocr_text_normalized), len(xml_text_normalized))
                    if score > best_score:
                        best_score = score
                        best_match = xml_header
            
            if best_score > 0.7:  # Порог схожести
                return best_match
    
    except Exception as e:
        print(f"    Предупреждение: ошибка сопоставления заголовка: {e}")
    
    return None


def is_table_caption(text: str) -> bool:
    """
    Проверяет, является ли текст подписью к таблице.
    
    Args:
        text: Текст для проверки
    
    Returns:
        True, если это подпись к таблице
    """
    text_lower = text.lower().strip()
    patterns = [
        r'таблица\s+\d+',
        r'table\s+\d+',
        r'табл\.\s+\d+',
        r'tbl\.\s+\d+'
    ]
    
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def is_image_caption(text: str) -> bool:
    """
    Проверяет, является ли текст подписью к изображению.
    
    Args:
        text: Текст для проверки
    
    Returns:
        True, если это подпись к изображению
    """
    text_lower = text.lower().strip()
    patterns = [
        r'рисунок\s+\d+',
        r'рис\.\s+\d+',
        r'figure\s+\d+',
        r'fig\.\s+\d+',
        r'изображение\s+\d+'
    ]
    
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def find_table_caption_in_xml(
    all_xml_elements: List[Dict[str, Any]],
    table_xml_position: int,
    start_idx: int
) -> Optional[Dict[str, Any]]:
    """
    Находит подпись таблицы в XML перед таблицей.
    
    Args:
        all_xml_elements: Все элементы из XML
        table_xml_position: Позиция таблицы в XML
        start_idx: Индекс начала поиска
    
    Returns:
        Информация о подписи или None
    """
    # Ищем подпись перед таблицей (до 5 элементов назад)
    for i in range(max(0, start_idx - 5), start_idx):
        elem = all_xml_elements[i]
        if elem.get('type') == 'paragraph':
            text = elem.get('text', '')
            if is_table_caption(text):
                return {
                    'text': text,
                    'xml_position': elem.get('xml_position')
                }
    return None


def find_image_caption_in_xml(
    all_xml_elements: List[Dict[str, Any]],
    image_xml_position: int,
    start_idx: int
) -> Optional[Dict[str, Any]]:
    """
    Находит подпись изображения в XML перед изображением.
    
    Args:
        all_xml_elements: Все элементы из XML
        image_xml_position: Позиция изображения в XML
        start_idx: Индекс начала поиска
    
    Returns:
        Информация о подписи или None
    """
    # Ищем подпись перед изображением (до 5 элементов назад)
    for i in range(max(0, start_idx - 5), start_idx):
        elem = all_xml_elements[i]
        if elem.get('type') == 'paragraph':
            text = elem.get('text', '')
            if is_image_caption(text):
                return {
                    'text': text,
                    'xml_position': elem.get('xml_position')
                }
    return None


def extract_structured_elements_from_xml(
    docx_path: Path,
    ocr_headers: List[Dict[str, Any]],
    ocr_captions: List[Dict[str, Any]],
    pdf_doc: fitz.Document
) -> List[Dict[str, Any]]:
    """
    Извлекает структурированные элементы из XML DOCX.
    Использует OCR ТОЛЬКО для определения заголовков и подписей, весь текст берется из XML.
    
    Args:
        docx_path: Путь к DOCX файлу
        ocr_headers: Заголовки из OCR (только для определения позиций)
        ocr_captions: Подписи из OCR (только для определения позиций)
        pdf_doc: PDF документ (для сопоставления)
    
    Returns:
        Список структурированных элементов
    """
    # Получаем все элементы из XML (ВСЕ данные из XML)
    all_xml_elements = extract_all_elements_from_docx_xml_ordered(docx_path)
    xml_headers = find_headers_in_xml(docx_path)
    
    # Получаем таблицы и изображения из XML
    docx_tables = extract_tables_from_docx_xml(docx_path)
    docx_images = extract_images_from_docx_xml(docx_path)
    
    # Создаем словари для быстрого поиска
    tables_by_position = {t.get('xml_position'): t for t in docx_tables}
    images_by_position = {img.get('xml_position'): img for img in docx_images}
    
    # Сопоставляем заголовки OCR с XML (используем OCR только для определения позиций)
    matched_headers = {}
    unmatched_ocr_headers = []
    for ocr_header in ocr_headers:
        matched = match_ocr_header_to_xml_header(ocr_header, xml_headers, pdf_doc)
        if matched:
            matched_headers[matched['xml_position']] = {
                'ocr': ocr_header,
                'xml': matched
            }
        else:
            unmatched_ocr_headers.append(ocr_header)
    
    # Логируем статистику сопоставления
    print(f"  ✓ Сопоставлено заголовков OCR→XML: {len(matched_headers)}/{len(ocr_headers)}")
    if unmatched_ocr_headers:
        print(f"  ⚠ Не сопоставлено заголовков: {len(unmatched_ocr_headers)}")
    
    # Извлекаем структурированные элементы из XML
    # ВСЕ данные (текст, таблицы, изображения) берутся из XML
    # OCR используется ТОЛЬКО для определения позиций заголовков и подписей
    structured_elements = []
    current_text_block = []
    current_text_positions = []
    current_text_size = 0
    
    for idx, elem in enumerate(all_xml_elements):
        elem_pos = elem.get('xml_position')
        elem_type = elem.get('type')
        
        # Функция для сохранения текущего текстового блока
        def save_text_block():
            nonlocal current_text_block, current_text_positions, current_text_size
            if current_text_block:
                # Объединяем текст с сохранением структуры
                full_text = '\n\n'.join(current_text_block)
                structured_elements.append({
                    'type': 'text_block',
                    'text': full_text,  # Полный текст из XML без обрезания
                    'size': len(full_text),
                    'xml_positions': current_text_positions.copy()
                })
                current_text_block = []
                current_text_positions = []
                current_text_size = 0
        
        # Проверяем, является ли это заголовком (определено через OCR→XML сопоставление)
        if elem_pos in matched_headers:
            save_text_block()
            
            # Добавляем заголовок (текст из XML - полный)
            header_info = matched_headers[elem_pos]
            structured_elements.append({
                'type': 'header',
                'level': header_info['xml']['level'],
                'text': header_info['xml']['text'],  # Полный текст из XML
                'xml_position': elem_pos,
                'ocr_page': header_info['ocr'].get('page_num', 0),  # Только для справки
                'ocr_bbox': header_info['ocr'].get('bbox', [])  # Только для справки
            })
            continue
        
        # Проверяем, является ли это таблицей
        if elem_type == 'table' and elem_pos in tables_by_position:
            save_text_block()
            
            # Ищем подпись к таблице в XML перед ней
            caption_info = find_table_caption_in_xml(all_xml_elements, elem_pos, idx)
            
            # Добавляем подпись, если найдена (текст из XML)
            if caption_info:
                structured_elements.append({
                    'type': 'table_caption',
                    'text': caption_info['text'],  # Полный текст из XML
                    'xml_position': caption_info['xml_position']
                })
            
            # Добавляем таблицу (полные данные из XML)
            table_data = tables_by_position[elem_pos]
            structured_elements.append({
                'type': 'table',
                'table_data': table_data,  # Полная структура из XML
                'xml_position': elem_pos
            })
            continue
        
        # Проверяем, является ли это изображением
        if elem_pos in images_by_position:
            save_text_block()
            
            # Ищем подпись к изображению в XML перед ним
            caption_info = find_image_caption_in_xml(all_xml_elements, elem_pos, idx)
            
            # Добавляем подпись, если найдена (текст из XML)
            if caption_info:
                structured_elements.append({
                    'type': 'image_caption',
                    'text': caption_info['text'],  # Полный текст из XML
                    'xml_position': caption_info['xml_position']
                })
            
            # Добавляем изображение (полные данные из XML)
            image_data = images_by_position[elem_pos]
            structured_elements.append({
                'type': 'image',
                'image_data': image_data,  # Полные данные из XML
                'xml_position': elem_pos
            })
            continue
        
        # Обрабатываем параграфы (ВСЕ данные из XML)
        if elem_type == 'paragraph':
            text = elem.get('text', '')  # Полный текст из XML
            text_size = len(text)
            
            # Проверяем, является ли это подписью (определяем по тексту из XML)
            if is_table_caption(text) or is_image_caption(text):
                # Подпись будет обработана вместе с таблицей/изображением
                # Пока сохраняем текущий блок
                save_text_block()
                continue
            
            # Определяем, нужно ли сохранить текущий блок и начать новый
            should_save = False
            
            # Условие 1: Превышен максимальный размер
            if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE:
                should_save = True
            
            # Условие 2: Превышено максимальное количество параграфов (логическое разбиение)
            # Это предотвращает создание огромных блоков с текстом с нескольких страниц
            if len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
                should_save = True
            
            # Условие 3: Текущий параграф очень большой (больше половины лимита) - сохраняем предыдущий
            if text_size > MAX_TEXT_BLOCK_SIZE // 2 and current_text_block:
                should_save = True
            
            if should_save:
                save_text_block()
            
            # Добавляем в текущий текстовый блок
            current_text_block.append(text)  # Полный текст из XML
            current_text_positions.append(elem_pos)
            current_text_size += text_size
            
            # Дополнительная проверка: если текущий блок стал слишком большим после добавления
            if current_text_size > MAX_TEXT_BLOCK_SIZE:
                # Сохраняем все кроме последнего параграфа
                if len(current_text_block) > 1:
                    # Сохраняем все кроме последнего
                    temp_block = current_text_block[:-1]
                    temp_positions = current_text_positions[:-1]
                    temp_size = sum(len(t) for t in temp_block)
                    
                    if temp_block:
                        structured_elements.append({
                            'type': 'text_block',
                            'text': '\n\n'.join(temp_block),
                            'size': temp_size,
                            'xml_positions': temp_positions
                        })
                    
                    # Начинаем новый блок с последнего параграфа
                    current_text_block = [text]
                    current_text_positions = [elem_pos]
                    current_text_size = text_size
                else:
                    # Если один параграф больше лимита, сохраняем его отдельно
                    save_text_block()
    
    # Сохраняем последний текстовый блок
    save_text_block()
    
    # Элементы уже в правильном порядке из XML
    # Структура начинается с заголовков (если они есть) или с текстовых блоков
    return structured_elements


def build_hierarchy_from_ocr_headers(
    ocr_headers: List[Dict[str, Any]], 
    pdf_doc: fitz.Document,
    xml_headers: Optional[List[Dict[str, Any]]] = None,
    matched_headers: Optional[Dict[int, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Строит иерархию на основе заголовков из OCR.
    Использует текст из XML (через matched_headers), а не из OCR.
    OCR используется ТОЛЬКО для определения структуры (позиции, уровни).
    
    Args:
        ocr_headers: Список заголовков из OCR (только для структуры)
        pdf_doc: PDF документ (для координат)
        xml_headers: Список заголовков из XML
        matched_headers: Словарь сопоставленных заголовков OCR→XML {xml_position: {ocr, xml}}
    
    Returns:
        Иерархия заголовков с текстом из XML
    """
    hierarchy = {
        'sections': [],
        'levels': {}
    }
    
    current_section = None
    previous_level = 0
    
    # Создаем обратный словарь: OCR заголовок (по bbox+page) -> XML заголовок
    ocr_to_xml = {}
    if matched_headers:
        for xml_pos, match_info in matched_headers.items():
            ocr_header = match_info['ocr']
            # Создаем уникальный ключ из bbox и page
            ocr_bbox = ocr_header.get('bbox', [])
            ocr_page = ocr_header.get('page_num', 0)
            ocr_key = (ocr_page, tuple(ocr_bbox) if ocr_bbox else ())
            ocr_to_xml[ocr_key] = match_info['xml']
    
    for header in ocr_headers:
        try:
            header_bbox = header.get('bbox', [])
            page_num = header.get('page_num', 0)
            
            # Ищем сопоставленный XML заголовок по ключу
            ocr_key = (page_num, tuple(header_bbox) if header_bbox else ())
            xml_header = ocr_to_xml.get(ocr_key)
            
            # Если не нашли по ключу, пробуем найти по содержимому в matched_headers
            if not xml_header and matched_headers:
                for xml_pos, match_info in matched_headers.items():
                    match_ocr = match_info['ocr']
                    match_bbox = match_ocr.get('bbox', [])
                    match_page = match_ocr.get('page_num', 0)
                    # Сравниваем по bbox и page
                    if (match_page == page_num and 
                        match_bbox == header_bbox):
                        xml_header = match_info['xml']
                        break
            
            # Используем текст из XML, если найден
            if xml_header:
                header_text = xml_header['text']  # Полный текст из XML
                level = xml_header.get('level', 1)
                xml_pos = xml_header.get('xml_position')
                text_source = 'xml'
            else:
                # Если не нашли в XML, используем OCR только для структуры
                # (текст будет неполным, но это лучше, чем ничего)
                page = pdf_doc[page_num]
                if header_bbox and len(header_bbox) >= 4:
                    expanded_rect = fitz.Rect(
                        max(0, header_bbox[0] - 100),
                        max(0, header_bbox[1] - 30),
                        min(page.rect.width, header_bbox[2] + 100),
                        min(page.rect.height, header_bbox[3] + 30)
                    )
                    header_text = page.get_text("text", clip=expanded_rect).strip()
                else:
                    header_text = ""
                
                # Определяем уровень по нумерации
                level = 1
                if re.match(r'^\d+\s+[A-ZА-ЯЁ]', header_text):
                    level = 1
                elif re.match(r'^\d+\.\d+\s+', header_text):
                    level = 2
                elif re.match(r'^\d+\.\d+\.\d+\s+', header_text):
                    level = 3
                elif re.match(r'^\d+\.\d+\.\d+\.\d+\s+', header_text):
                    level = 4
                
                xml_pos = None
                text_source = 'ocr'
            
            if not header_text:
                continue
            
            # Определяем позицию слева (левее = выше уровень)
            x_pos = header_bbox[0] if header_bbox and len(header_bbox) >= 4 else 0
            
            # Если уровень меньше предыдущего, закрываем текущую секцию
            if current_section and level <= previous_level:
                hierarchy['sections'].append(current_section)
                current_section = None
            
            # Создаем новую секцию или добавляем в текущую
            section_data = {
                'level': level,
                'text': header_text,  # Текст из XML (полный) или из OCR (может быть обрезан)
                'page': page_num,
                'bbox': header_bbox,
                'x_position': x_pos,
                'xml_position': xml_pos,
                'text_source': text_source
            }
            
            if current_section is None:
                current_section = {
                    'header': section_data,
                    'children': []
                }
            else:
                current_section['children'].append(section_data)
            
            previous_level = level
                
        except Exception as e:
            print(f"    Предупреждение: ошибка обработки заголовка: {e}")
            continue
    
    if current_section:
        hierarchy['sections'].append(current_section)
    
    return hierarchy


def process_docx_structure_pipeline(
    docx_path: Path,
    output_dir: Path,
    skip_first_table: bool = False
) -> Dict[str, Any]:
    """
    Основной пайплайн для обработки DOCX с построением структуры.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        skip_first_table: Пропустить первую таблицу (для Diplom2024)
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*80}")
    print(f"ПАЙПЛАЙН: DOTS OCR (структура) + XML (данные)")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    structure_dir = output_dir / "structure"
    structure_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Конвертируем DOCX в PDF
    print("Шаг 1: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}\n")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        return {"error": str(e)}
    
    # Шаг 2: Layout detection через DOTS OCR
    print("Шаг 2: Layout detection через DOTS OCR...")
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_doc)
    
    ocr_headers = []
    ocr_captions = []
    ocr_tables = []
    ocr_images = []
    ocr_formulas = []
    
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
                        ocr_formulas.append(element)
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
    
    # Шаг 3: Построение иерархии из OCR заголовков (с текстом из XML)
    print("Шаг 3: Построение иерархии из OCR заголовков (текст из XML)...")
    # Получаем XML заголовки для использования полного текста
    xml_headers = find_headers_in_xml(docx_path)
    
    # Предварительно сопоставляем заголовки для получения полного текста
    matched_headers_for_hierarchy = {}
    for ocr_header in ocr_headers:
        matched = match_ocr_header_to_xml_header(ocr_header, xml_headers, pdf_doc)
        if matched:
            matched_headers_for_hierarchy[matched['xml_position']] = {
                'ocr': ocr_header,
                'xml': matched
            }
    
    hierarchy = build_hierarchy_from_ocr_headers(
        ocr_headers, 
        pdf_doc, 
        xml_headers,
        matched_headers_for_hierarchy
    )
    print(f"  ✓ Построена иерархия: {len(hierarchy['sections'])} секций\n")
    
    # Шаг 4: Извлечение структурированных элементов из XML
    print("Шаг 4: Извлечение структурированных элементов из XML...")
    structured_elements = extract_structured_elements_from_xml(
        docx_path,
        ocr_headers,
        ocr_captions,
        pdf_doc
    )
    
    # Фильтруем первую таблицу, если нужно
    if skip_first_table:
        filtered_elements = []
        table_count = 0
        for elem in structured_elements:
            if elem.get('type') == 'table':
                table_count += 1
                if table_count == 1:
                    continue  # Пропускаем первую таблицу
            filtered_elements.append(elem)
        structured_elements = filtered_elements
        print(f"  ⚠ Пропущена первая таблица")
    
    print(f"  ✓ Извлечено элементов: {len(structured_elements)}")
    
    # Статистика по типам элементов
    element_types = {}
    for elem in structured_elements:
        elem_type = elem.get('type', 'unknown')
        element_types[elem_type] = element_types.get(elem_type, 0) + 1
    
    print(f"  Статистика:")
    for elem_type, count in element_types.items():
        print(f"    - {elem_type}: {count}")
    print()
    
    # Шаг 5: Сохранение результатов
    print("Шаг 5: Сохранение результатов...")
    
    results = {
        'docx_file': str(docx_path),
        'hierarchy': hierarchy,
        'elements': structured_elements,
        'statistics': {
            'ocr_headers': len(ocr_headers),
            'ocr_captions': len(ocr_captions),
            'ocr_tables': len(ocr_tables),
            'ocr_images': len(ocr_images),
            'ocr_formulas': len(ocr_formulas),
            'structured_elements': len(structured_elements),
            'element_types': element_types
        }
    }
    
    results_json_path = structure_dir / "structure.json"
    with open(results_json_path, 'w', encoding='utf-8') as f:
        # Используем ensure_ascii=False для сохранения полного текста
        json.dump(results, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
    
    print(f"  ✓ Результаты сохранены: {results_json_path}")
    
    # Создаем текстовый отчет
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("СТРУКТУРА ДОКУМЕНТА")
    report_lines.append("=" * 80)
    report_lines.append(f"\nDOCX файл: {docx_path.name}")
    report_lines.append(f"\nИЕРАРХИЯ (из DOTS OCR):")
    report_lines.append(f"  Секций: {len(hierarchy['sections'])}")
    report_lines.append(f"\nЭЛЕМЕНТЫ (из XML):")
    report_lines.append(f"  Всего: {len(structured_elements)}")
    for elem_type, count in element_types.items():
        report_lines.append(f"  {elem_type}: {count}")
    
    report_path = structure_dir / "report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"  ✓ Отчет сохранен: {report_path}\n")
    
    pdf_doc.close()
    
    print(f"{'='*80}")
    print(f"ИТОГО:")
    print(f"  Заголовков из OCR: {len(ocr_headers)}")
    print(f"  Секций в иерархии: {len(hierarchy['sections'])}")
    print(f"  Структурированных элементов: {len(structured_elements)}")
    print(f"{'='*80}\n")
    
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python docx_structure_pipeline.py <docx_path> [output_dir] [--skip-first-table]")
        print("\nПримеры:")
        print("  python docx_structure_pipeline.py test_folder/Диплом.docx")
        print("  python docx_structure_pipeline.py test_folder/Diplom2024.docx --skip-first-table")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    # Определяем выходную директорию
    if len(sys.argv) >= 3 and not sys.argv[2].startswith('--'):
        output_dir = Path(sys.argv[2])
    else:
        output_dir = Path(__file__).parent / "results" / "structure_pipeline" / docx_path.stem
    
    # Проверяем флаг --skip-first-table
    skip_first_table = '--skip-first-table' in sys.argv or 'Diplom2024' in docx_path.name
    
    result = process_docx_structure_pipeline(docx_path, output_dir, skip_first_table=skip_first_table)
    
    if "error" in result:
        print(f"\n✗ Ошибка: {result['error']}")
        sys.exit(1)
    
    print(f"\n✓ Пайплайн завершен успешно!")
