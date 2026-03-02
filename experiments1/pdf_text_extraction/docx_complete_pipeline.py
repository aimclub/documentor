"""
Полный пайплайн для DOCX: DOTS OCR → PyMuPDF → XML → Иерархия.

Объединяет все наработки:
1. DOTS OCR находит структуру (Section-header, Caption) и их bbox
2. PyMuPDF извлекает текст из PDF по bbox (быстрее и точнее для текстовых PDF)
3. XML предоставляет весь контент (текст, таблицы, изображения)
4. Правила находят пропущенные заголовки
5. Строится полная иерархия документа
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
    extract_all_elements_from_docx_xml_ordered,
    NAMESPACES
)
import zipfile
import xml.etree.ElementTree as ET
from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
)
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer
from documentor.domain import Element, ElementType, ParsedDocument, DocumentFormat

# Используем 2x увеличение для DOTS OCR
RENDER_SCALE = 2.0


def crop_element_from_page_image(
    page_image: Image.Image,
    bbox: List[float],
    padding: int = 10
) -> Image.Image:
    """Вырезает элемент из изображения страницы по bbox."""
    if not bbox or len(bbox) < 4:
        return page_image
    
    x1, y1, x2, y2 = bbox
    x1_crop = max(0, int(x1) - padding)
    y1_crop = max(0, int(y1) - padding)
    x2_crop = min(page_image.width, int(x2) + padding)
    y2_crop = min(page_image.height, int(y2) + padding)
    
    return page_image.crop((x1_crop, y1_crop, x2_crop, y2_crop))


def extract_text_from_pdf_by_bbox(
    ocr_elements: List[Dict[str, Any]],
    pdf_doc: fitz.Document
) -> List[Dict[str, Any]]:
    """Извлекает текст из PDF по bbox, найденным через DOTS OCR, используя PyMuPDF."""
    results = []
    
    for element in ocr_elements:
        category = element.get("category", "")
        bbox = element.get("bbox", [])
        page_num = element.get("page_num", 0)
        
        if category not in ["Section-header", "Caption"]:
            continue
        
        if not bbox or len(bbox) < 4:
            continue
        
        if page_num >= len(pdf_doc):
            continue
        
        try:
            page = pdf_doc[page_num]
            page_rect = page.rect
            
            # Преобразуем bbox из координат изображения в координаты PDF страницы
            # bbox от DOTS OCR в координатах изображения, отрендеренного с масштабом RENDER_SCALE
            # Поэтому координаты нужно разделить на RENDER_SCALE
            x1, y1, x2, y2 = bbox
            
            # Масштабируем координаты обратно в координаты страницы PDF
            pdf_x1 = x1 / RENDER_SCALE
            pdf_y1 = y1 / RENDER_SCALE
            pdf_x2 = x2 / RENDER_SCALE
            pdf_y2 = y2 / RENDER_SCALE
            
            # Создаем прямоугольник для извлечения текста в координатах PDF
            rect = fitz.Rect(pdf_x1, pdf_y1, pdf_x2, pdf_y2)
            
            # Извлекаем текст из прямоугольника
            text = page.get_textbox(rect)
            
            # Если не получилось через get_textbox, пробуем другой метод
            if not text or len(text.strip()) < 2:
                # Пробуем получить весь текст страницы и найти текст в нужной области
                text_dict = page.get_text("dict")
                text_parts = []
                
                for block in text_dict.get("blocks", []):
                    if "lines" not in block:
                        continue
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            span_bbox = span.get("bbox", [])
                            if len(span_bbox) >= 4:
                                # Проверяем пересечение bbox span с нашим bbox
                                span_rect = fitz.Rect(span_bbox)
                                if rect.intersects(span_rect):
                                    text_parts.append(span.get("text", ""))
                
                text = " ".join(text_parts)
            
            if text and text.strip():
                element_result = {
                    "category": category,
                    "bbox": bbox,
                    "page_num": page_num,
                    "text": text.strip(),
                    "text_length": len(text.strip())
                }
                results.append(element_result)
                print(f"      ✓ Извлечено {len(text.strip())} символов из PDF: '{text.strip()[:50]}...'")
            else:
                print(f"      ⚠ Текст не найден в PDF для {category} (стр. {page_num + 1}, bbox={bbox})")
        except Exception as e:
            print(f"      ✗ Ошибка извлечения текста из PDF: {e}")
            continue
    
    return results


def is_numbered_header(text: str) -> bool:
    """Проверяет, является ли текст нумерованным заголовком (например, '1. Описание задачи')."""
    text_stripped = text.strip()
    # Паттерны для нумерованных заголовков: "1. ", "1.1. ", "2. ", "3.1.2. " и т.д.
    patterns = [
        r'^\d+\.\s+[А-ЯЁA-Z]',  # "1. Заголовок"
        r'^\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1. Заголовок"
        r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1.1. Заголовок"
    ]
    return any(re.match(pattern, text_stripped) for pattern in patterns)


def extract_paragraph_properties_from_xml(
    docx_path: Path,
    xml_position: int
) -> Dict[str, Any]:
    """Извлекает свойства параграфа из XML, включая информацию о списках."""
    import zipfile
    import xml.etree.ElementTree as ET
    
    properties = {
        'font_name': None,
        'font_size': None,
        'is_bold': False,
        'is_italic': False,
        'style': None,
        'level': None,
        'is_list_item': False,  # Является ли элементом списка
        'list_type': None,  # 'numbered' или 'bulleted'
        'is_numbered_header': False,  # Является ли нумерованным заголовком (даже если есть numPr)
        'is_heading_style': False,  # Имеет ли стиль заголовка (Heading, Title)
        'alignment': None,  # Выравнивание: 'left', 'center', 'right', 'both', 'distribute'
    }
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            body = root.find('w:body', NAMESPACES)
            if body is None:
                return properties
            
            all_elements = list(body)
            if xml_position >= len(all_elements):
                return properties
            
            elem = all_elements[xml_position]
            if not elem.tag.endswith('}p'):
                return properties
            
            pPr = elem.find('w:pPr', NAMESPACES)
            if pPr is not None:
                # Извлекаем выравнивание (alignment)
                jc = pPr.find('w:jc', NAMESPACES)
                if jc is not None:
                    alignment_val = jc.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                    if alignment_val:
                        properties['alignment'] = alignment_val  # 'left', 'center', 'right', 'both', 'distribute'
                
                # Проверяем нумерацию (списки)
                numPr = pPr.find('w:numPr', NAMESPACES)
                if numPr is not None:
                    properties['is_list_item'] = True
                    # Определяем тип списка
                    numId = numPr.find('w:numId', NAMESPACES)
                    if numId is not None:
                        # Проверяем, есть ли ilvl (уровень списка)
                        ilvl = numPr.find('w:ilvl', NAMESPACES)
                        if ilvl is not None:
                            properties['list_type'] = 'numbered'
                        else:
                            # Может быть маркированный список
                            properties['list_type'] = 'bulleted'
                
                pStyle = pPr.find('w:pStyle', NAMESPACES)
                if pStyle is not None:
                    style_val = pStyle.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                    properties['style'] = style_val
                    
                    # ВАЖНО: Проверяем, является ли стиль просто числом ("1", "2", "3" и т.д.)
                    # В некоторых документах заголовки имеют стили "1", "2", "3" и т.д., где число указывает на уровень
                    if style_val.isdigit():
                        properties['is_heading_style'] = True
                        properties['level'] = int(style_val)
                    # Проверяем, является ли стиль заголовком
                    elif 'Heading' in style_val or 'heading' in style_val.lower():
                        properties['is_heading_style'] = True
                        match = re.search(r'(\d+)', style_val)
                        if match:
                            properties['level'] = int(match.group(1))
                    elif style_val == 'Title':
                        properties['is_heading_style'] = True
                        properties['level'] = 1
                    # Также проверяем другие возможные стили заголовков
                    elif any(keyword in style_val.lower() for keyword in ['заголовок', 'header', 'title', 'heading']):
                        properties['is_heading_style'] = True
                        # Пытаемся определить уровень из названия стиля
                        match = re.search(r'(\d+)', style_val)
                        if match:
                            properties['level'] = int(match.group(1))
                        else:
                            properties['level'] = 1  # По умолчанию уровень 1
            
            # Проверяем жирность текста (настоящие заголовки должны быть ПОЛНОСТЬЮ жирными)
            bold_runs = 0
            total_runs = 0
            total_text_len = 0
            bold_text_len = 0
            for r in elem.findall('.//w:r', NAMESPACES):
                total_runs += 1
                run_text = ''
                for t_el in r.findall('.//w:t', NAMESPACES):
                    if t_el.text:
                        run_text += t_el.text
                run_len = len(run_text.strip())
                total_text_len += run_len
                
                is_run_bold = False
                rPr = r.find('w:rPr', NAMESPACES)
                if rPr is not None:
                    rFonts = rPr.find('w:rFonts', NAMESPACES)
                    if rFonts is not None:
                        font_name = rFonts.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii', '')
                        if font_name and not properties['font_name']:
                            properties['font_name'] = font_name
                    
                    sz = rPr.find('w:sz', NAMESPACES)
                    if sz is not None:
                        sz_val = sz.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                        if sz_val and not properties['font_size']:
                            properties['font_size'] = int(sz_val) / 2.0
                    
                    b = rPr.find('w:b', NAMESPACES)
                    if b is not None:
                        val_attr = b.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                        if val_attr.lower() not in ['false', '0', 'off']:
                            is_run_bold = True
                    
                    # Также проверяем w:bCs
                    if not is_run_bold:
                        bCs = rPr.find('w:bCs', NAMESPACES)
                        if bCs is not None:
                            val_attr = bCs.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                            if val_attr.lower() not in ['false', '0', 'off']:
                                is_run_bold = True
                    
                    i_el = rPr.find('w:i', NAMESPACES)
                    if i_el is not None:
                        properties['is_italic'] = True
                
                if is_run_bold:
                    bold_runs += 1
                    bold_text_len += run_len
            
            # ВАЖНО: is_bold = True ТОЛЬКО если ВЕСЬ текст жирный (≥95% по длине символов)
            # Определения типа "**Термин** – описание" НЕ считаются жирными
            # Порог 95% (а не 100%) — запас на пустые/пробельные run'ы без явного w:b
            if total_text_len > 0:
                properties['is_bold'] = (bold_text_len / total_text_len) >= 0.95
            elif total_runs > 0:
                properties['is_bold'] = (bold_runs / total_runs) >= 0.95
            else:
                properties['is_bold'] = False
    
    except Exception as e:
        print(f"    Предупреждение: ошибка извлечения свойств параграфа {xml_position}: {e}")
    
    return properties


def find_header_in_xml_by_text(
    header_text: str,
    all_xml_elements: List[Dict[str, Any]],
    start_from: int = 0,
    docx_path: Path = None,
    header_rules: Dict[str, Any] = None
) -> Optional[int]:
    """Находит заголовок в XML по тексту. Использует гибкое сопоставление."""
    header_text_normalized = re.sub(r'\s+', ' ', header_text.lower().strip())
    
    # Для очень коротких текстов (< 3 символов) — только точное совпадение
    if len(header_text_normalized) < 3:
        for elem in all_xml_elements:
            if elem.get('xml_position', 0) < start_from:
                continue
            if elem.get('type') == 'paragraph':
                xml_text = elem.get('text', '')
                xml_text_normalized = re.sub(r'\s+', ' ', xml_text.lower().strip())
                if header_text_normalized == xml_text_normalized:
                    return elem.get('xml_position')
        return None
    
    # Извлекаем ключевые слова из заголовка (первые 3-5 слов)
    header_words = header_text_normalized.split()[:5]
    header_keywords = ' '.join(header_words) if header_words else header_text_normalized
    
    best_match = None
    best_score = 0
    
    # Минимальная длина для startswith сравнения — не менее 5 символов
    min_startswith_len = max(5, min(30, len(header_text_normalized)))
    
    for elem in all_xml_elements:
        # ВАЖНО: start_from — это xml_position, НЕ индекс в списке!
        if elem.get('xml_position', 0) < start_from:
            continue
        if elem.get('type') == 'paragraph':
            xml_text = elem.get('text', '')
            xml_text_normalized = re.sub(r'\s+', ' ', xml_text.lower().strip())
            
            if not xml_text_normalized:
                continue
            
            # Точное совпадение
            if header_text_normalized == xml_text_normalized:
                return elem.get('xml_position')
            
            # Начинается с заголовка или заголовок начинается с текста
            # Используем min_startswith_len для предотвращения ложных совпадений коротких текстов
            if (xml_text_normalized.startswith(header_text_normalized[:min_startswith_len]) or
                header_text_normalized.startswith(xml_text_normalized[:min_startswith_len])):
                return elem.get('xml_position')
            
            # Гибкое сопоставление по ключевым словам
            if len(header_keywords) > 10:  # Только для достаточно длинных заголовков
                xml_words = xml_text_normalized.split()[:5]
                xml_keywords = ' '.join(xml_words) if xml_words else xml_text_normalized
                
                # Вычисляем схожесть по ключевым словам
                header_set = set(header_keywords.split())
                xml_set = set(xml_keywords.split())
                
                if header_set and xml_set:
                    intersection = len(header_set & xml_set)
                    union = len(header_set | xml_set)
                    similarity = intersection / union if union > 0 else 0
                    
                    # Если схожесть > 0.7, считаем это совпадением
                    if similarity > 0.7 and similarity > best_score:
                        best_score = similarity
                        best_match = elem.get('xml_position')
    
    # Если нашли хорошее совпадение, возвращаем его
    if best_match and best_score > 0.7:
        return best_match
    
    return None


def build_header_rules_from_found_headers(
    docx_path: Path,
    header_positions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Строит правила для поиска заголовков на основе найденных заголовков."""
    rules = {
        'by_level': {},
        'common_properties': {}
    }
    
    if not header_positions:
        return rules
    
    all_properties = []
    for header_info in header_positions:
        xml_pos = header_info.get('xml_position')
        if xml_pos is None:
            continue
        
        properties = extract_paragraph_properties_from_xml(docx_path, xml_pos)
        
        # ВАЖНО: Если параграф имеет стиль заголовка - это приоритетный признак
        is_heading_style = properties.get('is_heading_style', False)
        
        # ВАЖНО: Если это нумерованный заголовок (найден через OCR), 
        # он может иметь numPr, но это всё равно заголовок
        is_numbered_header = header_info.get('is_numbered_header', False)
        
        # Если это элемент списка, но НЕ нумерованный заголовок и НЕ заголовок по стилю - пропускаем
        if properties.get('is_list_item') and not is_numbered_header and not is_heading_style:
            continue  # Пропускаем элементы списка
        
        # ВАЖНО: Настоящие заголовки должны быть жирными (кроме нумерованных заголовков из OCR и заголовков по стилю)
        if not properties.get('is_bold') and not is_numbered_header and not is_heading_style:
            continue  # Пропускаем нежирный текст
        
        level = properties.get('level')
        
        if not level:
            text = header_info.get('text', '')
            # ВАЖНО: Определяем уровень из нумерации (3.3 -> уровень 2, 3.3.1 -> уровень 3)
            match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if match:
                if match.group(3):  # Есть третья цифра (например, "3.3.1")
                    level = 3
                elif match.group(2):  # Есть вторая цифра (например, "3.3")
                    level = 2
                elif match.group(1):  # Только первая цифра (например, "3")
                    level = 1
        
        if not level:
            level = 'unknown'
        
        properties['xml_position'] = xml_pos
        properties['text'] = header_info.get('text', '')
        properties['detected_level'] = level
        all_properties.append(properties)
        
        level_key = str(level)
        if level_key not in rules['by_level']:
            rules['by_level'][level_key] = []
        rules['by_level'][level_key].append(properties)
    
    for level, props_list in rules['by_level'].items():
        if not props_list:
            continue
        
        font_names = [p.get('font_name') for p in props_list if p.get('font_name')]
        font_sizes = [p.get('font_size') for p in props_list if p.get('font_size')]
        bold_count = sum(1 for p in props_list if p.get('is_bold'))
        italic_count = sum(1 for p in props_list if p.get('is_italic'))
        styles = [p.get('style') for p in props_list if p.get('style')]
        heading_style_count = sum(1 for p in props_list if p.get('is_heading_style'))
        
        # Находим наиболее частый стиль (как для font_name)
        most_common_style = None
        if styles:
            most_common_style = max(set(styles), key=styles.count)
        
        level_rules = {
            'font_name': max(set(font_names), key=font_names.count) if font_names else None,
            'font_size': sum(font_sizes) / len(font_sizes) if font_sizes else None,  # Среднее значение
            'font_size_range': (min(font_sizes), max(font_sizes)) if font_sizes else None,
            'is_bold': bold_count > len(props_list) / 2,  # Большинство жирные
            'is_italic': italic_count > len(props_list) / 2,  # Большинство курсивные
            'style_pattern': most_common_style,  # Наиболее частый стиль
            'is_heading_style': heading_style_count > len(props_list) / 2,  # Большинство имеют стиль заголовка
            'count': len(props_list)
        }
        
        rules['by_level'][level] = level_rules
    
    if all_properties and len(rules['by_level']) == 1 and 'unknown' in rules['by_level']:
        all_font_names = [p.get('font_name') for p in all_properties if p.get('font_name')]
        all_font_sizes = [p.get('font_size') for p in all_properties if p.get('font_size')]
        all_bold_count = sum(1 for p in all_properties if p.get('is_bold'))
        all_styles = [p.get('style') for p in all_properties if p.get('style')]
        all_heading_style_count = sum(1 for p in all_properties if p.get('is_heading_style'))
        
        if all_font_names or all_font_sizes or all_styles:
            most_common_style = None
            if all_styles:
                most_common_style = max(set(all_styles), key=all_styles.count)
            
            rules['common_header'] = {
                'font_name': max(set(all_font_names), key=all_font_names.count) if all_font_names else None,
                'font_size': sum(all_font_sizes) / len(all_font_sizes) if all_font_sizes else None,  # Среднее значение
                'font_size_range': (min(all_font_sizes), max(all_font_sizes)) if all_font_sizes else None,
                'is_bold': all_bold_count > len(all_properties) / 2,  # Большинство жирные
                'style_pattern': most_common_style,  # Наиболее частый стиль
                'is_heading_style': all_heading_style_count > len(all_properties) / 2,  # Большинство имеют стиль заголовка
            }
    
    return rules


def find_missing_headers_by_rules(
    docx_path: Path,
    all_xml_elements: List[Dict[str, Any]],
    header_rules: Dict[str, Any],
    found_positions: List[int],
    found_texts: set = None,
    header_positions: List[Dict[str, Any]] = None  # Добавляем для доступа к статистике
) -> List[Dict[str, Any]]:
    """Находит пропущенные заголовки в XML, используя правила."""
    found_headers = []
    found_positions_set = set(found_positions)
    if found_texts is None:
        found_texts = set()
    
    rules_by_level = header_rules.get('by_level', {})
    common_header = header_rules.get('common_header', {})
    
    if not rules_by_level and not common_header:
        return found_headers
    
    for i, elem in enumerate(all_xml_elements):
        if elem.get('type') != 'paragraph':
            continue
        
        xml_pos = elem.get('xml_position')
        if xml_pos in found_positions_set:
            continue
        
        text = elem.get('text', '').strip()
        # ВАЖНО: Вычисляем максимальную длину заголовка на основе статистики найденных заголовков
        # Используем медианную длину найденных заголовков * 2, но не менее 50 и не более 300
        if found_texts:
            # Оцениваем среднюю длину заголовков из найденных текстов
            avg_header_length = sum(len(t) for t in found_texts) / len(found_texts) if found_texts else 100
            max_header_length = max(50, min(int(avg_header_length * 2.5), 300))
        else:
            # Если заголовков еще нет, используем разумное значение по умолчанию
            max_header_length = 200
        
        # ВАЖНО: Не ограничиваем слишком сильно длину текста
        # Есть очень короткие заголовки (например, "Введение" - одно слово)
        # Минимальная длина - 1 символ, максимальная - более либеральный порог
        if not text or len(text) < 1:
            continue
        
        # Увеличиваем максимальную длину для более либеральной проверки
        # Используем более высокий множитель для учета длинных заголовков
        if len(text) > max(max_header_length, 500):  # Максимум 500 символов или адаптивный порог
            continue
        
        # ВАЖНО: Проверяем, не был ли этот заголовок уже найден (по тексту)
        # Нормализуем текст для сравнения
        normalized_text = re.sub(r'\s+', ' ', text.lower().strip())
        if normalized_text in found_texts:
            # Этот заголовок уже был найден, пропускаем
            continue
        
        # ВАЖНО: Если текст заканчивается на ":", это точно не заголовок и не caption
        if text.endswith(':'):
            continue
        
        # ВАЖНО: Пропускаем подписи к таблицам и изображениям - они не являются заголовками
        if is_table_caption(text) or is_image_caption(text):
            continue
        
        # ВАЖНО: Пропускаем определения ("Термин – описание") - они не являются заголовками
        if is_definition_pattern(text):
            continue
        
        # ВАЖНО: Пропускаем разделители ("……………………………………………………….399") - они не являются заголовками
        if is_separator_line(text):
            continue
        
        # ВАЖНО: Пропускаем элементы списка по паттерну ("1) ФИО;", "а) текст", "- пункт")
        if is_list_item_pattern(text):
            continue
        
        # ВАЖНО: Пропускаем метаданные документа ("Отчет 98 с., 1 кн., ...")
        if is_document_metadata(text):
            continue
        
        # ВАЖНО: Пропускаем заголовки списков ("На этапе 1 выполнены следующие работы.")
        if is_list_header(text):
            continue
        
        # ВАЖНО: Проверяем, является ли текущий элемент частью последовательности списка (1., 2., 3., ...)
        # Проверяем соседние элементы в XML
        text_match = re.match(r'^(\d+)\.\s+(.+)$', text)
        if text_match:
            curr_num = int(text_match.group(1))
            
            # Проверяем предыдущий элемент
            if i > 0:
                prev_elem = all_xml_elements[i - 1]
                if prev_elem.get('type') == 'paragraph':
                    prev_text = prev_elem.get('text', '').strip()
                    prev_match = re.match(r'^(\d+)\.\s+(.+)$', prev_text)
                    if prev_match:
                        prev_num = int(prev_match.group(1))
                        # Если предыдущий элемент - это предыдущий номер (1. → 2., 2. → 3., ...)
                        if prev_num == curr_num - 1:
                            # Это часть последовательности списка
                            print(f"  ⚠ Пропущен элемент (часть последовательности списка): '{text[:50]}...' → позиция {xml_pos}")
                            continue
            
            # Проверяем следующий элемент
            if i + 1 < len(all_xml_elements):
                next_elem = all_xml_elements[i + 1]
                if next_elem.get('type') == 'paragraph':
                    next_text = next_elem.get('text', '').strip()
                    next_match = re.match(r'^(\d+)\.\s+(.+)$', next_text)
                    if next_match:
                        next_num = int(next_match.group(1))
                        # Если следующий элемент - это следующий номер (1. → 2., 2. → 3., ...)
                        if next_num == curr_num + 1:
                            # Это часть последовательности списка
                            print(f"  ⚠ Пропущен элемент (часть последовательности списка): '{text[:50]}...' → позиция {xml_pos}")
                            continue
        
        properties = extract_paragraph_properties_from_xml(docx_path, xml_pos)
        
        # ВАЖНО: Если параграф имеет стиль заголовка - это приоритетный признак
        is_heading_style = properties.get('is_heading_style', False)
        heading_level_from_style = properties.get('level') if is_heading_style else None
        
        # ВАЖНО: Короткие жирные тексты (например, "Введение", "Заключение") могут быть заголовками
        # даже если они не найдены через OCR
        # Вычисляем порог для "короткого текста" на основе статистики найденных заголовков
        if found_texts:
            avg_header_length = sum(len(t) for t in found_texts) / len(found_texts) if found_texts else 50
            short_text_threshold = max(30, min(int(avg_header_length * 1.2), 150))
        else:
            short_text_threshold = 100
        
        # Вычисляем минимальный размер шрифта на основе статистики найденных заголовков
        # Используем средний размер шрифта найденных заголовков, но не менее 10
        min_font_size = 10  # Минимальный размер по умолчанию
        if header_rules.get('by_level'):
            # Берем средний размер шрифта из правил
            font_sizes = []
            for level_rules in header_rules['by_level'].values():
                if level_rules.get('font_size'):
                    font_sizes.append(level_rules['font_size'])
            if font_sizes:
                min_font_size = max(10, min(font_sizes) - 2)  # Минимум на 2 пункта меньше среднего
        
        # ВАЖНО: Для нумерованных заголовков не требуем жирность,
        # НО элементы списка (is_list_item) НЕ считаются нумерованными заголовками,
        # если у них нет стиля заголовка (is_heading_style).
        # Пример: "1. Апробация..." — list_item, НЕ заголовок.
        # Пример: "1. Описание задачи" с style="1" — заголовок.
        is_list_item = properties.get('is_list_item', False)
        is_numbered_header = False
        if not is_list_item or is_heading_style:
            is_numbered_header = any(re.match(pattern, text.strip()) for pattern in [
                r'^\d+\.\s+[А-ЯЁA-Z]',  # "1. Заголовок"
                r'^\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1. Заголовок"
                r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1.1. Заголовок"
            ])
        
        # Используем более либеральный порог для коротких жирных текстов
        bold_text_threshold = max(short_text_threshold, 100)
        is_short_bold_text = (
            len(text) <= bold_text_threshold and  # Короткий текст (макс 100 или адаптивный)
            properties.get('is_bold') and  # Жирный
            properties.get('font_size') and properties.get('font_size') >= min_font_size  # Адаптивный размер шрифта
        )
        
        detected_level = None
        # Если есть уровень из стиля, используем его
        if heading_level_from_style:
            detected_level = heading_level_from_style
        match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
        if match:
            if match.group(3):
                detected_level = 3
            elif match.group(2):
                detected_level = 2
            elif match.group(1):
                detected_level = 1
        
        best_match = None
        best_score = 0
        
        for level, level_rules in rules_by_level.items():
            matches = 0
            total_checks = 0
            
            if level_rules.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == level_rules['font_name']:
                    matches += 1
            
            if level_rules.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = level_rules['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            if level_rules.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == level_rules['is_bold']:
                    matches += 1
            
            # ВАЖНО: style_pattern имеет больший вес (scale = 3.0)
            # Если стиль совпадает, это сильный признак заголовка
            if level_rules.get('style_pattern'):
                total_checks += 3  # Увеличиваем вес проверки стиля
                if properties.get('style') == level_rules['style_pattern']:
                    matches += 3  # Увеличиваем вес совпадения стиля
            
            # Проверяем, имеет ли элемент стиль заголовка (если большинство заголовков этого уровня имеют стиль)
            if level_rules.get('is_heading_style') is not None:
                total_checks += 1
                if properties.get('is_heading_style') == level_rules['is_heading_style']:
                    matches += 1
            
            if total_checks > 0:
                score = matches / total_checks
                if detected_level and str(detected_level) == level:
                    score += 0.2
                
                if score > best_score:
                    best_score = score
                    best_match = {
                        'level': level,
                        'score': score,
                        'matches': matches,
                        'total_checks': total_checks
                    }
        
        if not best_match and common_header:
            matches = 0
            total_checks = 0
            
            if common_header.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == common_header['font_name']:
                    matches += 1
            
            if common_header.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = common_header['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            if common_header.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == common_header['is_bold']:
                    matches += 1
            
            if common_header.get('style_pattern'):
                total_checks += 1
                if properties.get('style') == common_header['style_pattern']:
                    matches += 1
            
            if common_header.get('is_heading_style') is not None:
                total_checks += 1
                if properties.get('is_heading_style') == common_header['is_heading_style']:
                    matches += 1
            
            if total_checks > 0:
                score = matches / total_checks
                if detected_level:
                    score += 0.3
                
                if score > best_score:
                    best_score = score
                    best_match = {
                        'level': detected_level if detected_level else 'unknown',
                        'score': score,
                        'matches': matches,
                        'total_checks': total_checks
                    }
        
        # ВАЖНО: Если параграф имеет стиль заголовка - это приоритетный признак
        if is_heading_style and heading_level_from_style:
            best_match = {
                'level': str(heading_level_from_style),
                'score': 1.0,  # Максимальный балл для заголовков по стилю
                'matches': 1,
                'total_checks': 1
            }
        # ВАЖНО: Нумерованные заголовки (например, "1. Описание задачи") могут быть заголовками,
        # НО только если есть дополнительное подтверждение: жирность ИЛИ стиль заголовка.
        # Без этого обычный текст "1. Апробация..." ложно определяется как заголовок.
        elif not best_match and is_numbered_header and (properties.get('is_bold') or is_heading_style):
            # Определяем уровень на основе нумерации
            match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if match:
                if match.group(3):  # Есть третья цифра (например, "3.3.1")
                    detected_level = 3
                elif match.group(2):  # Есть вторая цифра (например, "3.3")
                    detected_level = 2
                elif match.group(1):  # Только первая цифра (например, "3")
                    detected_level = 1
            else:
                detected_level = 1  # По умолчанию уровень 1
            
            best_match = {
                'level': str(detected_level),
                'score': 0.8,  # Высокий балл для нумерованных заголовков
                'matches': 1,
                'total_checks': 1
            }
        # ВАЖНО: Короткие жирные тексты (например, "Введение", "Главная страница") могут быть заголовками
        # даже если score из правил ниже порога
        elif (not best_match or best_match['score'] < 0.5) and is_short_bold_text:
            # Определяем уровень на основе размера шрифта
            # ВАЖНО: Используем статистику из правил для определения порогов размеров шрифта
            font_size = properties.get('font_size', 12)
            
            # Вычисляем пороги на основе статистики найденных заголовков
            if header_rules.get('by_level'):
                font_sizes_by_level = {}
                for level, level_rules in header_rules['by_level'].items():
                    if level_rules.get('font_size'):
                        font_sizes_by_level[int(level)] = level_rules['font_size']
                
                if font_sizes_by_level:
                    # Сортируем уровни по размеру шрифта
                    sorted_levels = sorted(font_sizes_by_level.items(), key=lambda x: x[1], reverse=True)
                    if len(sorted_levels) >= 2:
                        # Используем пороги между уровнями
                        level1_size = sorted_levels[0][1] if len(sorted_levels) > 0 else 16
                        level2_size = sorted_levels[1][1] if len(sorted_levels) > 1 else 14
                        level3_size = sorted_levels[2][1] if len(sorted_levels) > 2 else 12
                        
                        if font_size >= level1_size:
                            detected_level = 1
                        elif font_size >= level2_size:
                            detected_level = 2
                        elif font_size >= level3_size:
                            detected_level = 3
                        else:
                            detected_level = 3
                    else:
                        # Если только один уровень, используем относительные пороги
                        base_size = sorted_levels[0][1]
                        if font_size >= base_size:
                            detected_level = 1
                        elif font_size >= base_size - 2:
                            detected_level = 2
                        else:
                            detected_level = 3
                else:
                    # Fallback: используем абсолютные значения
                    if font_size >= 16:
                        detected_level = 1
                    elif font_size >= 14:
                        detected_level = 2
                    else:
                        detected_level = 3
            else:
                # Fallback: используем абсолютные значения
                if font_size >= 16:
                    detected_level = 1
                elif font_size >= 14:
                    detected_level = 2
                else:
                    detected_level = 3
            
            best_match = {
                'level': str(detected_level),
                'score': 0.8,  # Высокий балл для коротких жирных текстов
                'matches': 3,
                'total_checks': 3
            }
        
        # ВАЖНО: Фильтруем элементы списка и проверяем жирность
        # Нумерованные заголовки могут иметь numPr, но это всё равно заголовки
        if best_match and best_match['score'] >= 0.5:
            # Проверяем, является ли это нумерованным заголовком
            text_stripped = text.strip()
            numbered_patterns = [
                r'^\d+\.\s+[А-ЯЁA-Z]',  # "1. Заголовок"
                r'^\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1. Заголовок"
                r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]',  # "1.1.1. Заголовок"
            ]
            is_numbered_header = any(re.match(pattern, text_stripped) for pattern in numbered_patterns)
            
            # ВАЖНО: Если параграф имеет стиль заголовка - это приоритетный признак
            is_heading_style = properties.get('is_heading_style', False)
            
            # Проверка 1: Если это элемент списка и НЕ заголовок по стилю - пропускаем
            # ВАЖНО: is_numbered_header уже учитывает is_list_item (False для list_item без heading_style)
            if properties.get('is_list_item') and not is_heading_style:
                print(f"  ⚠ Пропущен элемент списка (не заголовок): '{text[:50]}...' → позиция {xml_pos}")
                continue
            
            # Проверка 2: Настоящие заголовки должны быть жирными (кроме нумерованных заголовков, заголовков по стилю и коротких жирных текстов)
            # ВАЖНО: Если это короткий текст и имеет стиль заголовка или большой размер шрифта - это заголовок
            # Вычисляем пороги адаптивно
            if found_texts:
                avg_header_length = sum(len(t) for t in found_texts) / len(found_texts) if found_texts else 50
                short_text_threshold = max(30, min(int(avg_header_length * 1.2), 150))
            else:
                short_text_threshold = 50
            
            min_font_size = 10
            if header_rules.get('by_level'):
                font_sizes = []
                for level_rules in header_rules['by_level'].values():
                    if level_rules.get('font_size'):
                        font_sizes.append(level_rules['font_size'])
                if font_sizes:
                    min_font_size = max(10, min(font_sizes) - 2)
            
            is_short_text_with_style = (
                len(text) <= short_text_threshold and  # Короткий текст (адаптивный порог)
                (is_heading_style or (properties.get('font_size') and properties.get('font_size') >= min_font_size))
            )
            
            if not properties.get('is_bold') and not is_numbered_header and not is_heading_style and not is_short_bold_text and not is_short_text_with_style:
                print(f"  ⚠ Пропущен нежирный текст (не заголовок): '{text[:50]}...' → позиция {xml_pos}")
                continue
            
            # Для нумерованных заголовков НЕ требуем большой размер шрифта
            # Нумерованные заголовки (3.1, 3.2 и т.д.) определяются по паттерну, а не по размеру шрифта
            # Если это нумерованный заголовок, он должен быть принят независимо от размера шрифта
            
            # ВАЖНО: Если текст заканчивается на ":", это точно не заголовок и не caption
            if text.strip().endswith(':'):
                continue
            
            # ВАЖНО: Проверка последовательности нумерации
            # Если предыдущий заголовок был "9.1", а следующий "1." на том же или более высоком уровне - это список
            text_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if text_match:
                curr_num = int(text_match.group(1))
                curr_sub = text_match.group(2)
                # Определяем уровень из нумерации или из best_match
                curr_level_from_match = 1
                if text_match.group(3):
                    curr_level_from_match = 3
                elif text_match.group(2):
                    curr_level_from_match = 2
                
                curr_level = best_match.get('level', curr_level_from_match)
                if isinstance(curr_level, str):
                    try:
                        curr_level = int(curr_level)
                    except:
                        curr_level = curr_level_from_match
                else:
                    curr_level = int(curr_level)
                
                # Находим последний заголовок с нумерацией (из всех заголовков)
                all_prev_headers = []
                if header_positions:
                    all_prev_headers.extend(header_positions)
                all_prev_headers.extend(found_headers)
                all_prev_headers = sorted(all_prev_headers, key=lambda h: h.get('xml_position', 0))
                
                # Ищем последний заголовок с нумерацией перед текущим
                prev_numbered_header = None
                for prev_header in reversed(all_prev_headers):
                    if prev_header.get('xml_position', 0) < xml_pos:
                        prev_text = prev_header.get('text', '').strip()
                        prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text)
                        if prev_match:
                            # Определяем уровень из нумерации или из header
                            prev_level_from_match = 1
                            if prev_match.group(3):
                                prev_level_from_match = 3
                            elif prev_match.group(2):
                                prev_level_from_match = 2
                            
                            prev_level = prev_header.get('level', prev_level_from_match)
                            if isinstance(prev_level, str):
                                try:
                                    prev_level = int(prev_level)
                                except:
                                    prev_level = prev_level_from_match
                            
                            prev_numbered_header = {
                                'text': prev_text,
                                'num': int(prev_match.group(1)),
                                'sub': prev_match.group(2),
                                'level': prev_level,
                                'xml_position': prev_header.get('xml_position', 0)
                            }
                            break
                
                # Если нашли предыдущий нумерованный заголовок
                if prev_numbered_header:
                    prev_num = prev_numbered_header['num']
                    prev_sub = prev_numbered_header['sub']
                    prev_level = prev_numbered_header['level']
                    prev_xml_pos = prev_numbered_header['xml_position']
                    
                    # ВАЖНО: Проверяем, является ли это элементом списка в XML
                    if properties.get('is_list_item'):
                        print(f"  ⚠ Пропущен заголовок (is_list_item в XML): '{text[:50]}...' → позиция {xml_pos}")
                        continue
                    
                    # ВАЖНО: Если элементы идут подряд (9. → 10. на том же уровне, без подуровней) - это список
                    # Проверяем, что xml_position близко (разница <= 10, т.к. между элементами списка может быть текст)
                    # и нет подуровней, и номера последовательные
                    if (curr_level == prev_level and 
                        (xml_pos - prev_xml_pos) <= 10 and
                        not prev_sub and not curr_sub and
                        curr_num == prev_num + 1):
                        # Проверяем, нет ли между ними других заголовков
                        has_other_headers_between = False
                        for other_header in all_prev_headers:
                            other_pos = other_header.get('xml_position', 0)
                            if prev_xml_pos < other_pos < xml_pos:
                                other_text = other_header.get('text', '').strip()
                                other_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', other_text)
                                if other_match:
                                    # Если между ними есть другой нумерованный заголовок - это не список
                                    has_other_headers_between = True
                                    break
                        
                        if not has_other_headers_between:
                            # Это последовательная нумерация списка (9. → 10.)
                            print(f"  ⚠ Пропущен заголовок (последовательная нумерация списка): "
                                  f"'{prev_numbered_header['text'][:30]}...' ({prev_num}.) → "
                                  f"'{text[:30]}...' ({curr_num}.) → позиция {xml_pos}")
                            continue
                    
                    # ВАЖНО: Проверяем нарушение последовательности нумерации
                    # Если последний заголовок был "11.1", а следующий "2.2" - это нарушение, это список
                    # Правила:
                    # 1. Если номер уменьшился (11.1 → 2.2) - это нарушение
                    # 2. Если номер уменьшился значительно (более чем на 1) - это точно нарушение
                    # 3. Если номер тот же, но подуровень уменьшился (11.2 → 11.1) - это нарушение (кроме начала нового раздела)
                    # 4. Если номер сбросился до 1, но предыдущий был > 1 - это нарушение
                    is_sequence_violation = False
                    
                    if curr_num < prev_num:
                        # Номер уменьшился (11.1 → 2.2) - это нарушение
                        # Если уменьшился значительно (более чем на 1) - это точно нарушение
                        if prev_num - curr_num > 1:
                            is_sequence_violation = True
                        elif prev_num - curr_num == 1:
                            # Уменьшился на 1 - может быть нормально, если это переход к новому разделу
                            # Но если есть подуровни - это нарушение (11.1 → 10.2 - нарушение)
                            if prev_sub:
                                is_sequence_violation = True
                    elif curr_num == prev_num:
                        # Номер тот же - проверяем подуровень
                        if prev_sub and curr_sub:
                            prev_sub_num = int(prev_sub)
                            curr_sub_num = int(curr_sub)
                            if curr_sub_num < prev_sub_num:
                                # Подуровень уменьшился (11.2 → 11.1) - это нарушение
                                is_sequence_violation = True
                        elif prev_sub and not curr_sub:
                            # Было "11.1", стало "11" - это может быть нормально (новый раздел)
                            pass
                    elif curr_num == 1 and prev_num > 1:
                        # Номер сбросился до 1 (11.1 → 1.2) - это нарушение
                        is_sequence_violation = True
                    
                    if is_sequence_violation:
                        # Если уровень понижается (11.1 level 2 → 1.2 level 1) - это может быть новый раздел, НЕ список
                        # Если уровень тот же или повышается (11.1 level 2 → 2.2 level 2 или 3) - это список
                        if curr_level >= prev_level:
                            print(f"  ⚠ Пропущен заголовок (нарушение последовательности нумерации): "
                                  f"'{prev_numbered_header['text'][:30]}...' ({prev_num}.{prev_sub or ''}, level {prev_level}) → "
                                  f"'{text[:30]}...' ({curr_num}.{curr_sub or ''}, level {curr_level}) → позиция {xml_pos}")
                            continue
            
            found_headers.append({
                'xml_position': xml_pos,
                'text': text,
                'level': best_match['level'],
                'properties': properties,
                'match_score': best_match['score']
            })
            found_positions_set.add(xml_pos)
            print(f"  ✓ Найден пропущенный заголовок (уровень {best_match['level']}): '{text[:50]}...' → позиция {xml_pos}")
    
    # ========== ПОСТ-ФИЛЬТР: удаляем цепочки из 3+ подряд идущих заголовков одного уровня ==========
    # Если 3+ заголовка одного уровня идут на ПОСЛЕДОВАТЕЛЬНЫХ xml_position (без контента между ними),
    # это список/перечисление, а не настоящие заголовки.
    if found_headers:
        # Объединяем OCR-заголовки и найденные по правилам для полной проверки
        all_header_positions = sorted(found_positions)  # Уже найденные через OCR
        all_candidates = sorted(found_headers, key=lambda h: h['xml_position'])
        
        # Находим цепочки последовательных заголовков одного уровня
        # ВАЖНО: Если "1.", "2.", "3." подряд - это список, НЕ заголовки
        # Но если "1.", "1.1." - это подзаголовки, НЕ список
        positions_to_remove = set()
        i = 0
        while i < len(all_candidates):
            chain = [all_candidates[i]]
            j = i + 1
            while j < len(all_candidates):
                prev_pos = chain[-1]['xml_position']
                curr_pos = all_candidates[j]['xml_position']
                curr_level = all_candidates[j]['level']
                prev_level = chain[-1]['level']
                prev_text = chain[-1]['text']
                curr_text = all_candidates[j]['text']
                
                # Извлекаем нумерацию
                prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text.strip())
                curr_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', curr_text.strip())
                
                # Считаем "подряд" если:
                # 1. Тот же уровень
                # 2. xml_position различается на 1-2 (может быть пустой параграф между ними)
                # 3. Оба нумерованные И последовательные ("1.", "2.") ИЛИ оба не нумерованные
                is_sequential = False
                if prev_match and curr_match:
                    # Оба нумерованные - проверяем последовательность
                    prev_num = int(prev_match.group(1))
                    curr_num = int(curr_match.group(1))
                    prev_sub = prev_match.group(2)
                    curr_sub = curr_match.group(2)
                    
                    # Если тот же уровень и следующий номер - это последовательность (список)
                    if curr_level == prev_level and curr_num == prev_num + 1:
                        # Если нет подуровня (нет "1.1") - это список
                        if not prev_sub and not curr_sub:
                            is_sequential = True
                elif not prev_match and not curr_match:
                    # Оба не нумерованные - проверяем только уровень и позицию
                    is_sequential = (curr_level == prev_level)
                
                if curr_level == prev_level and (curr_pos - prev_pos) <= 2 and is_sequential:
                    chain.append(all_candidates[j])
                    j += 1
                else:
                    break
            
            # Если цепочка >= 2 — это перечисление, НЕ заголовки
            # Правило: если есть "1. что-то" и "2. что-то" подряд - это уже список
            if len(chain) >= 2:
                # Проверяем, является ли это последовательной нумерацией списка (1., 2., 3., ...)
                is_numbered_sequence = True
                for k in range(len(chain) - 1):
                    prev_text = chain[k]['text'].strip()
                    curr_text = chain[k + 1]['text'].strip()
                    prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text)
                    curr_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', curr_text)
                    if prev_match and curr_match:
                        prev_num = int(prev_match.group(1))
                        curr_num = int(curr_match.group(1))
                        prev_sub = prev_match.group(2)
                        curr_sub = curr_match.group(2)
                        # Если не последовательные или есть подуровни - это не список
                        if curr_num != prev_num + 1 or prev_sub or curr_sub:
                            is_numbered_sequence = False
                            break
                    else:
                        is_numbered_sequence = False
                        break
                
                # Если это последовательная нумерация списка - удаляем ВСЕ элементы, включая OCR
                if is_numbered_sequence:
                    for item in chain:
                        positions_to_remove.add(item['xml_position'])
                        print(f"  ⚠ Удалён элемент цепочки (последовательная нумерация списка): "
                              f"уровень {item['level']}, '{item['text'][:50]}...' → позиция {item['xml_position']}")
                else:
                    # Если не последовательная нумерация - удаляем только найденные по правилам
                    for item in chain:
                        if item['xml_position'] not in set(found_positions):
                            positions_to_remove.add(item['xml_position'])
                            print(f"  ⚠ Удалён элемент цепочки (не заголовок, а список): "
                                  f"уровень {item['level']}, '{item['text'][:50]}...' → позиция {item['xml_position']}")
            
            i = j
        
        if positions_to_remove:
            found_headers = [h for h in found_headers if h['xml_position'] not in positions_to_remove]
            print(f"  ✓ Удалено {len(positions_to_remove)} ложных заголовков (цепочки перечислений)")
    
    return found_headers


def is_table_caption(text: str) -> bool:
    """Проверяет, является ли текст подписью к таблице."""
    text_stripped = text.strip()
    # ВАЖНО: Если текст заканчивается на ":", это точно не caption
    if text_stripped.endswith(':'):
        return False
    
    text_lower = text_stripped.lower()
    # ВАЖНО: паттерн должен быть В НАЧАЛЕ текста, иначе "...в таблице 15..." 
    # будет ложно определён как caption
    patterns = [
        r'^таблица\s+\d+',  # "Таблица 1"
        r'^table\s+\d+',  # "Table 1"
        r'^табл\.\s*\d+',  # "Табл. 1"
        r'^tbl\.\s*\d+',  # "Tbl. 1"
    ]
    return any(re.search(pattern, text_lower) for pattern in patterns)


def is_image_caption(text: str) -> bool:
    """Проверяет, является ли текст подписью к изображению."""
    text_stripped = text.strip()
    # ВАЖНО: Если текст заканчивается на ":", это точно не caption
    if text_stripped.endswith(':'):
        return False
    
    text_lower = text_stripped.lower()
    # ВАЖНО: паттерн должен быть В НАЧАЛЕ текста, чтобы не было ложных срабатываний
    patterns = [
        r'^рис\.\s*\d+',
        r'^рисунок\s+\d+',
        r'^figure\s+\d+',
        r'^fig\.\s*\d+',
        r'^изображение\s+\d+',
    ]
    return any(re.search(pattern, text_lower) for pattern in patterns)


def is_structural_keyword(text: str) -> bool:
    """Проверяет, является ли текст ключевым структурным словом (Введение, Заключение и т.д.)."""
    text_stripped = text.strip().lower()
    structural_keywords = [
        'введение',
        'заключение',
        'список литературы',
        'список использованных источников',
        'библиографический список',
        'литература',
        'приложение',
        'приложения',
        'содержание',
        'оглавление',
        'термины и определения',
        'перечень сокращений и обозначений',
        'перечень сокращений',
        'список обозначений и сокращений',
        'обозначения и сокращения',
        'аннотация',
        'реферат',
        'abstract',
        'referat',
        'introduction',
        'conclusion',
        'references',
        'bibliography',
        'appendix',
        'appendices',
        'contents',
        'table of contents',
        'terms and definitions',
        'abbreviations',
    ]
    return text_stripped in structural_keywords


def is_definition_pattern(text: str) -> bool:
    """Проверяет, является ли текст определением вида 'Термин – описание'.
    
    Такие тексты НЕ должны быть заголовками:
    - "Цитата - фрагмент текста из документа."
    - "БД - база данных"
    - "ФН – функциональное направление"
    - "NLP – обработка текста на естественном языке"
    - "Инвентарный номер отчета - ИИ 2023-1"
    
    НЕ считаются определениями:
    - "3.3. Пользовательский интерфейс" (нумерованный заголовок)
    - "Введение" (структурное ключевое слово)
    """
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    # Нумерованные заголовки — точно НЕ определения
    if re.match(r'^\d+', text_stripped):
        return False
    
    # Ищем тире-разделитель (–, —, -)
    # Тире должно быть окружено пробелами: " – ", " — ", " - "
    dash_patterns = [' – ', ' — ', ' - ']
    for dash in dash_patterns:
        idx = text_stripped.find(dash)
        if idx > 0:
            term = text_stripped[:idx].strip()
            definition = text_stripped[idx + len(dash):].strip()
            # Термин: 1-5 слов, определение: что-то есть
            term_words = len(term.split())
            if 1 <= term_words <= 5 and len(definition) > 0:
                return True
    
    return False


def is_separator_line(text: str) -> bool:
    """Проверяет, является ли текст разделителем (строка из точек, тире, цифр).
    
    Примеры:
    - "………………………………………………………………………………………………….399"
    - "---"
    - "___"
    """
    text_stripped = text.strip()
    if not text_stripped or len(text_stripped) < 3:
        return False
    
    # Если текст состоит в основном из повторяющихся символов (точки, тире, подчёркивания)
    # или содержит только цифры и разделители
    separator_chars = {'.', '–', '—', '-', '_', '=', '…', ' '}
    non_separator_chars = set(text_stripped) - separator_chars
    
    # Если >80% символов - разделители, это разделитель
    if len(non_separator_chars) == 0:
        return True
    
    # Если только цифры в конце и разделители
    if re.match(r'^[.\-–—_=…\s]+[\d]+$', text_stripped):
        return True
    
    return False


def is_list_item_pattern(text: str) -> bool:
    """Проверяет, является ли текст элементом списка по паттерну.
    
    Примеры list items:
    - "1) ФИО;"
    - "а) удаляется точка"
    - "- загрузка вопросов"
    - "• пункт списка"
    - "1. Классификация предложений..." (если это часть перечисления, а не заголовок)
    
    НЕ list items:
    - "1. Описание задачи" (нумерованный заголовок)
    - "3.3. Пользовательский интерфейс" (нумерованный заголовок)
    """
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    # Паттерны list items:
    list_patterns = [
        r'^[а-яёa-z]\)\s+',  # "а) текст", "б) текст"
        r'^[А-ЯЁA-Z]\)\s+',  # "А) текст", "Б) текст"
        r'^\d+\)\s+',  # "1) текст", "2) текст"
        r'^[-•·▪▫]\s+',  # "- текст", "• текст"
        r'^[ivxlcdm]+\)\s+',  # римские цифры: "i)", "ii)", "iii)"
    ]
    
    # Проверяем паттерны list items
    for pattern in list_patterns:
        if re.match(pattern, text_stripped, re.IGNORECASE):
            return True
    
    # Если начинается с "- " или "• " - это точно list item
    if text_stripped.startswith(('- ', '• ', '· ', '▪ ', '▫ ')):
        return True
    
    return False


def is_numbered_sequence_item(text: str, prev_numbered_text: str = None) -> bool:
    """Проверяет, является ли текст элементом нумерованной последовательности (списка).
    
    Если предыдущий текст был "1. ...", а текущий "2. ..." на том же уровне - это список.
    Если текущий "1.1. ..." - это подзаголовок, НЕ элемент списка.
    
    Args:
        text: Текущий текст
        prev_numbered_text: Предыдущий нумерованный текст (если есть)
    
    Returns:
        True если это элемент последовательности (списка), False если подзаголовок
    """
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    # Извлекаем нумерацию из текущего текста
    match_curr = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text_stripped)
    if not match_curr:
        return False
    
    curr_level = 1 if match_curr.group(3) else (2 if match_curr.group(2) else 1)
    curr_num = int(match_curr.group(1))
    
    # Если есть предыдущий текст
    if prev_numbered_text:
        match_prev = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_numbered_text.strip())
        if match_prev:
            prev_level = 1 if match_prev.group(3) else (2 if match_prev.group(2) else 1)
            prev_num = int(match_prev.group(1))
            
            # Если тот же уровень и следующий номер - это последовательность (список)
            if curr_level == prev_level and curr_num == prev_num + 1:
                return True
    
    return False


def is_document_metadata(text: str) -> bool:
    """Проверяет, является ли текст метаданными документа.
    
    Примеры:
    - "Отчет 98 с., 1 кн., 16 рис., 34 табл., 33 источн., 14 прил."
    - "Отчет X страниц, Y таблиц, Z рисунков"
    - "Документ содержит X страниц"
    """
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    text_lower = text_stripped.lower()
    
    # Паттерны метаданных документа
    metadata_patterns = [
        r'отчет\s+\d+',  # "Отчет 98"
        r'\d+\s+с\.',  # "98 с."
        r'\d+\s+кн\.',  # "1 кн."
        r'\d+\s+рис\.',  # "16 рис."
        r'\d+\s+табл\.',  # "34 табл."
        r'\d+\s+источн\.',  # "33 источн."
        r'\d+\s+прил\.',  # "14 прил."
        r'страниц',  # "X страниц"
        r'таблиц',  # "Y таблиц"
        r'рисунков',  # "Z рисунков"
    ]
    
    # Если текст содержит несколько паттернов метаданных - это метаданные
    matches = sum(1 for pattern in metadata_patterns if re.search(pattern, text_lower))
    if matches >= 2:
        return True
    
    return False


def is_list_header(text: str) -> bool:
    """Проверяет, является ли текст заголовком списка (не настоящим заголовком).
    
    Примеры:
    - "На этапе 1 выполнены следующие работы."
    - "На отчетном этапе выполнены следующие работы."
    - "Выполнены следующие работы:"
    - "Список включает следующие пункты:"
    
    Это НЕ заголовки, а обычный текст, который предшествует списку.
    """
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    text_lower = text_stripped.lower()
    
    # Паттерны заголовков списков
    list_header_patterns = [
        r'на\s+этапе\s+\d+\s+выполнены',  # "На этапе 1 выполнены"
        r'на\s+отчетном\s+этапе\s+выполнены',  # "На отчетном этапе выполнены"
        r'выполнены\s+следующие\s+работы',  # "Выполнены следующие работы"
        r'следующие\s+работы',  # "Следующие работы"
        r'список\s+включает',  # "Список включает"
        r'включает\s+следующие\s+пункты',  # "Включает следующие пункты"
    ]
    
    return any(re.search(pattern, text_lower) for pattern in list_header_patterns)


def get_paragraph_text_from_xml(p: ET.Element) -> str:
    """Извлекает весь текст из параграфа XML, включая табуляции и пробелы."""
    texts = []
    for elem in p.iter():
        if elem.tag == f'{{{NAMESPACES["w"]}}}t':
            if elem.text:
                texts.append(elem.text)
        elif elem.tag == f'{{{NAMESPACES["w"]}}}tab':
            texts.append('\t')
        elif elem.tag == f'{{{NAMESPACES["w"]}}}br':
            texts.append(' ')
    return ''.join(texts).strip()


def get_paragraph_style_from_xml(p: ET.Element) -> Optional[str]:
    """Получает стиль параграфа из XML."""
    p_pr = p.find('w:pPr', NAMESPACES)
    if p_pr is not None:
        p_style = p_pr.find('w:pStyle', NAMESPACES)
        if p_style is not None:
            return p_style.get(f'{{{NAMESPACES["w"]}}}val') or p_style.get('val')
    return None


def find_bookmark_text_in_xml(root: ET.Element, bookmark_name: str) -> Optional[Dict[str, Any]]:
    """Находит закладку по имени и извлекает текст заголовка рядом с ней."""
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return None
    
    for para in body.findall('w:p', NAMESPACES):
        bookmark_starts = para.findall('.//w:bookmarkStart', NAMESPACES)
        for bs in bookmark_starts:
            bs_name = bs.get(f'{{{NAMESPACES["w"]}}}name') or bs.get('name')
            if bs_name == bookmark_name:
                title = get_paragraph_text_from_xml(para)
                if not title or not title.strip():
                    continue
                
                level = 1
                style = get_paragraph_style_from_xml(para)
                if style:
                    if style.isdigit():
                        level = int(style)
                    elif style.upper().startswith('HEADING'):
                        try:
                            level = int(style.replace('Heading', '').replace('heading', '').strip())
                        except:
                            pass
                
                level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                if level_match:
                    if level_match.group(3):
                        level = 3
                    elif level_match.group(2):
                        level = 2
                    else:
                        level = 1
                
                return {
                    'title': title.strip(),
                    'level': level,
                    'style': style,
                    'bookmark_name': bookmark_name
                }
    
    return None


def parse_toc_from_field_simple(root: ET.Element) -> List[Dict[str, Any]]:
    """Парсит содержание из специальных полей TOC (w:fldChar, w:instrText) через PAGEREF."""
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    all_paras = list(body.findall('w:p', NAMESPACES))
    all_instr_texts = root.findall('.//w:instrText', NAMESPACES)
    
    pageref_bookmarks = []
    for instr in all_instr_texts:
        if instr.text and 'PAGEREF' in instr.text.upper():
            bookmark_match = re.search(r'PAGEREF\s+(_Toc\d+)', instr.text, re.IGNORECASE)
            if bookmark_match:
                bookmark_name = bookmark_match.group(1)
                parent_para = None
                for para in all_paras:
                    if instr in para.findall('.//w:instrText', NAMESPACES):
                        parent_para = para
                        break
                
                para_text = ""
                page_num = None
                if parent_para is not None:
                    para_text = get_paragraph_text_from_xml(parent_para)
                    page_match = re.search(r'(\d+)\s*$', para_text)
                    if page_match:
                        page_num = int(page_match.group(1))
                
                pageref_bookmarks.append({
                    'bookmark_name': bookmark_name,
                    'para_text': para_text,
                    'page_num': page_num
                })
    
    for pageref_info in pageref_bookmarks:
        bookmark_name = pageref_info['bookmark_name']
        page_num = pageref_info['page_num']
        bookmark_data = find_bookmark_text_in_xml(root, bookmark_name)
        
        if bookmark_data:
            title = bookmark_data['title']
            level = bookmark_data['level']
            if page_num is None:
                page_match = re.search(r'(\d+)\s*$', pageref_info['para_text'])
                if page_match:
                    page_num = int(page_match.group(1))
            
            # Фильтруем технические термины
            if len(title) >= 3 and re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                        not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                if not is_technical_term:
                    toc_entries.append({
                        'title': title,
                        'page': page_num,
                        'level': level,
                        'bookmark_name': bookmark_name
                    })
    
    return toc_entries


def parse_toc_from_styles_simple(root: ET.Element) -> List[Dict[str, Any]]:
    """Парсит содержание из параграфов со стилями TOC1, TOC2, TOC3."""
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    in_toc_section = False
    toc_start_found = False
    
    for para in body.findall('w:p', NAMESPACES):
        text = get_paragraph_text_from_xml(para)
        style = get_paragraph_style_from_xml(para)
        
        if not toc_start_found:
            text_lower = text.lower().strip()
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                toc_start_found = True
                in_toc_section = True
                continue
        
        if in_toc_section:
            if style and style.upper().startswith('TOC'):
                level = 1
                if len(style) > 3:
                    try:
                        level = int(style[3:])
                    except:
                        pass
                
                page_num = None
                title = text
                page_match = re.search(r'(\d+)\s*$', text)
                if page_match:
                    page_num = int(page_match.group(1))
                    title = re.sub(r'[.\s\-]+?\d+\s*$', '', text).strip()
                
                if title and len(title) >= 3:
                    toc_entries.append({
                        'title': title.strip(),
                        'page': page_num,
                        'level': level,
                        'style': style
                    })
            elif text and len(text) > 0:
                text_lower = text.lower().strip()
                if text_lower in ['введение', 'introduction', '1.', '1 ', 'глава', 'часть']:
                    if len(toc_entries) > 0:
                        break
    
    return toc_entries


def parse_toc_from_paragraphs_simple(
    all_elements: List[Dict[str, Any]],
    toc_header_xml_pos: int,
    next_header_xml_pos: int
) -> List[Dict[str, Any]]:
    """Парсит содержание из обычных параграфов между заголовком 'СОДЕРЖАНИЕ' и следующим крупным заголовком."""
    toc_entries = []
    
    for elem in all_elements:
        xml_pos = elem.get('xml_position', -1)
        if toc_header_xml_pos < xml_pos < next_header_xml_pos:
            elem_type = elem.get('type', '')
            text = elem.get('text', '').strip()
            
            if elem_type == 'paragraph' and text:
                text_lower = text.lower().strip()
                if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                    continue
                
                clean_text = re.sub(r'\.{2,}', '\t', text)
                parts = re.split(r'\t|\s{3,}', clean_text.strip())
                
                if len(parts) >= 2:
                    title_part = parts[0].strip()
                    page_part = parts[-1].strip()
                    
                    match = re.match(r'^(\d+(?:\.\d+)*)\.?\s+(.+)$', title_part)
                    if match:
                        number = match.group(1)
                        title = match.group(2).strip().rstrip('\t.').strip()
                        level = number.count('.') + 1
                        
                        page_num = None
                        try:
                            page_num = int(page_part)
                        except ValueError:
                            page_match = re.search(r'(\d+)\s*$', text)
                            if page_match:
                                try:
                                    page_num = int(page_match.group(1))
                                except ValueError:
                                    pass
                        
                        if len(title) >= 3 and re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                            is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                                    not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                            if not is_technical_term:
                                toc_entries.append({
                                    'title': title,
                                    'page': page_num,
                                    'level': level,
                                    'number': number
                                })
                else:
                    page_match = re.search(r'[.\s\-]+?(\d+)\s*$', text)
                    if not page_match:
                        page_match = re.search(r'(\d+)\s*$', text)
                    
                    if page_match:
                        page_num = int(page_match.group(1))
                        title = re.sub(r'[.\s\-]+?\d+\s*$', '', text).strip()
                        
                        level = 1
                        level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                        if level_match:
                            if level_match.group(3):
                                level = 3
                            elif level_match.group(2):
                                level = 2
                            else:
                                level = 1
                            title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\.?\s+', '', title).strip()
                        
                        has_separators = bool(re.search(r'[.\-]{3,}', text))
                        has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', text))
                        
                        if (has_separators or has_numbering) and len(title) >= 3:
                            if re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                                is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                                        not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                                if not is_technical_term:
                                    toc_entries.append({
                                        'title': title.strip(),
                                        'page': page_num,
                                        'level': level
                                    })
    
    return toc_entries


def parse_toc_from_docx(docx_path: Path, all_xml_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Парсит оглавление из DOCX файла, используя несколько методов.
    Возвращает список заголовков из оглавления для использования в пайплайне.
    """
    toc_entries = []
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # Метод 1: Парсинг через PAGEREF (динамические поля)
            toc_from_field = parse_toc_from_field_simple(root)
            if toc_from_field:
                return toc_from_field
            
            # Метод 2: Парсинг через стили TOC
            toc_from_styles = parse_toc_from_styles_simple(root)
            if toc_from_styles:
                return toc_from_styles
            
            # Метод 3: Парсинг через параграфы между заголовками
            toc_header_pos = None
            next_header_pos = None
            
            for i, elem in enumerate(all_xml_elements):
                text = elem.get('text', '').strip().lower()
                if (text in ['содержание', 'оглавление', 'contents', 'table of contents'] or
                    text.startswith('содержание') or text.startswith('оглавление')):
                    toc_header_pos = elem.get('xml_position', -1)
                    toc_entries_found = 0
                    for j in range(i + 1, min(i + 100, len(all_xml_elements))):
                        next_elem = all_xml_elements[j]
                        next_text = next_elem.get('text', '').strip()
                        
                        if not next_text:
                            continue
                        
                        has_page_num = bool(re.search(r'\d+\s*$', next_text))
                        has_separators = bool(re.search(r'[.\-]{3,}', next_text))
                        has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', next_text))
                        is_toc_entry = has_page_num and (has_separators or has_numbering)
                        
                        if is_toc_entry:
                            toc_entries_found += 1
                            continue
                        
                        if toc_entries_found > 0:
                            if (len(next_text) > 3 and
                                (re.match(r'^\d+[.\s]', next_text) or 
                                 next_text.lower() in ['введение', 'introduction', 'глава', 'часть', 'раздел', 'заключение']) and
                                not (has_page_num and has_separators)):
                                next_header_pos = next_elem.get('xml_position', -1)
                                break
                        
                        if toc_entries_found == 0 and len(next_text) > 3:
                            if (re.match(r'^\d+[.\s]', next_text) or 
                                next_text.lower() in ['введение', 'introduction', 'глава', 'часть', 'раздел']):
                                break
                    
                    if toc_header_pos is not None:
                        break
            
            if toc_header_pos is not None:
                toc_from_paragraphs = parse_toc_from_paragraphs_simple(
                    all_xml_elements,
                    toc_header_pos,
                    next_header_pos if next_header_pos else 999999
                )
                if toc_from_paragraphs:
                    return toc_from_paragraphs
    except Exception as e:
        print(f"  ⚠ Ошибка при парсинге оглавления: {e}")
    
    return toc_entries


def build_caption_rules_from_found_captions(
    docx_path: Path,
    caption_positions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Строит правила для поиска captions на основе найденных captions."""
    rules = {
        'alignment': None,  # Наиболее частое выравнивание
        'font_size': None,  # Средний размер шрифта
        'font_name': None,  # Наиболее частый шрифт
        'is_bold': False,  # Большинство жирные?
        'is_italic': False,  # Большинство курсивные?
    }
    
    if not caption_positions:
        return rules
    
    alignments = []
    font_sizes = []
    font_names = []
    bold_count = 0
    italic_count = 0
    
    for caption_info in caption_positions:
        xml_pos = caption_info.get('xml_position')
        if xml_pos is None:
            continue
        
        properties = extract_paragraph_properties_from_xml(docx_path, xml_pos)
        
        if properties.get('alignment'):
            alignments.append(properties['alignment'])
        if properties.get('font_size'):
            font_sizes.append(properties['font_size'])
        if properties.get('font_name'):
            font_names.append(properties['font_name'])
        if properties.get('is_bold'):
            bold_count += 1
        if properties.get('is_italic'):
            italic_count += 1
    
    if alignments:
        rules['alignment'] = max(set(alignments), key=alignments.count)
    if font_sizes:
        rules['font_size'] = sum(font_sizes) / len(font_sizes)
    if font_names:
        rules['font_name'] = max(set(font_names), key=font_names.count)
    rules['is_bold'] = bold_count > len(caption_positions) / 2
    rules['is_italic'] = italic_count > len(caption_positions) / 2
    
    return rules


def find_caption_before_element(
    all_xml_elements: List[Dict[str, Any]],
    element_xml_pos: int,
    docx_path: Path = None,
    caption_rules: Dict[str, Any] = None,
    max_lookback: int = 3
) -> Optional[Dict[str, Any]]:
    """Ищет подпись перед элементом (таблицей или изображением) в XML."""
    best_match = None
    best_score = 0
    
    # Ищем элементы с xml_position в диапазоне [element_xml_pos - max_lookback, element_xml_pos)
    target_positions = set(range(max(0, element_xml_pos - max_lookback), element_xml_pos))
    
    for elem in all_xml_elements:
        pos = elem.get('xml_position', -1)
        if pos not in target_positions:
            continue
        if elem.get('type') == 'paragraph':
            text = elem.get('text', '').strip()
            
            # Проверяем паттерны captions
            is_table = is_table_caption(text)
            is_image = is_image_caption(text)
            
            if not (is_table or is_image):
                continue
            
            # Если есть правила captions, проверяем дополнительные признаки
            score = 1.0  # Базовый балл за паттерн
            if docx_path and caption_rules:
                properties = extract_paragraph_properties_from_xml(docx_path, pos)
                
                # Проверяем выравнивание (если в правилах указано, что captions по центру)
                if caption_rules.get('alignment') and properties.get('alignment'):
                    if properties['alignment'] == caption_rules['alignment']:
                        score += 0.3  # Бонус за совпадение выравнивания
                
                # Проверяем размер шрифта
                if caption_rules.get('font_size') and properties.get('font_size'):
                    font_size_diff = abs(properties['font_size'] - caption_rules['font_size'])
                    if font_size_diff <= 1.0:
                        score += 0.2  # Бонус за совпадение размера шрифта
                
                # Проверяем жирность
                if caption_rules.get('is_bold') is not None:
                    if properties.get('is_bold') == caption_rules['is_bold']:
                        score += 0.1  # Бонус за совпадение жирности
            
            if score > best_score:
                best_score = score
                best_match = {
                    'text': text,
                    'xml_position': pos,
                    'is_table_caption': is_table,
                    'is_image_caption': is_image,
                    'score': score
                }
    
    return best_match


def find_caption_after_element(
    all_xml_elements: List[Dict[str, Any]],
    element_xml_pos: int,
    docx_path: Path = None,
    caption_rules: Dict[str, Any] = None,
    max_lookahead: int = 3
) -> Optional[Dict[str, Any]]:
    """Ищет подпись после элемента (таблицы или изображения) в XML."""
    best_match = None
    best_score = 0
    
    for i in range(1, max_lookahead + 1):
        check_pos = element_xml_pos + i
        if check_pos < 0 or check_pos >= len(all_xml_elements):
            continue
        
        elem = all_xml_elements[check_pos]
        if elem.get('type') == 'paragraph':
            text = elem.get('text', '').strip()
            
            # Проверяем паттерны captions
            is_table = is_table_caption(text)
            is_image = is_image_caption(text)
            
            if not (is_table or is_image):
                continue
            
            # Если есть правила captions, проверяем дополнительные признаки
            score = 1.0  # Базовый балл за паттерн
            if docx_path and caption_rules:
                properties = extract_paragraph_properties_from_xml(docx_path, check_pos)
                
                # Проверяем выравнивание (если в правилах указано, что captions по центру)
                if caption_rules.get('alignment') and properties.get('alignment'):
                    if properties['alignment'] == caption_rules['alignment']:
                        score += 0.3  # Бонус за совпадение выравнивания
                
                # Проверяем размер шрифта
                if caption_rules.get('font_size') and properties.get('font_size'):
                    font_size_diff = abs(properties['font_size'] - caption_rules['font_size'])
                    if font_size_diff <= 1.0:
                        score += 0.2  # Бонус за совпадение размера шрифта
                
                # Проверяем жирность
                if caption_rules.get('is_bold') is not None:
                    if properties.get('is_bold') == caption_rules['is_bold']:
                        score += 0.1  # Бонус за совпадение жирности
            
            if score > best_score:
                best_score = score
                best_match = {
                    'text': text,
                    'xml_position': check_pos,
                    'is_table_caption': is_table,
                    'is_image_caption': is_image,
                    'score': score
                }
    
    return best_match


def extract_table_from_xml_element(
    table_elem: Any,  # ET.Element
    xml_pos: int,
    docx_path: Path
) -> Optional[Dict[str, Any]]:
    """
    Извлекает данные таблицы напрямую из XML элемента.
    Используется для таблиц, которые были пропущены из docx_tables.
    """
    try:
        from experiments.pdf_text_extraction.docx_xml_parser import (
            extract_text_from_element, find_cell_in_column, has_vmerge_continue,
            calculate_rowspan, NAMESPACES
        )
        
        table_info = {
            'index': 0,  # Будет установлен позже
            'xml_position': xml_pos,
            'rows': [],
            'rows_count': 0,
            'cols_count': 0,
            'style': None,
            'merged_cells': [],
            'estimated_page': 1,
        }
        
        # Получаем стиль таблицы
        tbl_pr = table_elem.find('w:tblPr', NAMESPACES)
        if tbl_pr is not None:
            tbl_style = tbl_pr.find('w:tblStyle', NAMESPACES)
            if tbl_style is not None:
                style_val = tbl_style.get(f'{{{NAMESPACES["w"]}}}val') or tbl_style.get('val')
                if style_val:
                    table_info['style'] = style_val
        
        # Обрабатываем строки
        rows = table_elem.findall('.//w:tr', NAMESPACES)
        table_info['rows_count'] = len(rows)
        
        max_cols = 0
        
        for row_idx, row_elem in enumerate(rows):
            row_data = {
                'row_index': row_idx,
                'cells': [],
                'cells_count': 0,
            }
            
            # Обрабатываем ячейки
            cells = row_elem.findall('.//w:tc', NAMESPACES)
            col_idx = 0
            
            for cell_elem in cells:
                # Извлекаем текст из ячейки
                cell_text = extract_text_from_element(cell_elem, NAMESPACES)
                
                # Проверяем свойства ячейки
                cell_props = cell_elem.find('w:tcPr', NAMESPACES)
                colspan = 1
                rowspan = 1
                vmerge = None
                is_merged = False
                
                if cell_props is not None:
                    # gridSpan - объединение по горизонтали
                    grid_span = cell_props.find('w:gridSpan', NAMESPACES)
                    if grid_span is not None:
                        val = grid_span.get(f'{{{NAMESPACES["w"]}}}val') or grid_span.get('val')
                        if val:
                            colspan = int(val)
                            is_merged = True
                    
                    # vMerge - объединение по вертикали
                    v_merge = cell_props.find('w:vMerge', NAMESPACES)
                    if v_merge is not None:
                        val = v_merge.get(f'{{{NAMESPACES["w"]}}}val') or v_merge.get('val')
                        if val == 'restart':
                            # Начало объединения - вычисляем rowspan
                            vmerge = 'restart'
                            rowspan = calculate_rowspan(table_elem, row_idx, col_idx, NAMESPACES)
                            is_merged = True
                        else:
                            # Продолжение объединения - эта ячейка не должна учитываться
                            vmerge = 'continue'
                            rowspan = 0
                            is_merged = True
                
                # Создаем информацию о ячейке
                cell_info = {
                    'cell_index': col_idx,
                    'row': row_idx,
                    'col': col_idx,
                    'text': cell_text,
                    'text_length': len(cell_text),
                    'is_merged': is_merged,
                    'colspan': colspan,
                    'rowspan': rowspan,
                    'vmerge': vmerge,
                }
                
                row_data['cells'].append(cell_info)
                
                # Учитываем colspan при переходе к следующей колонке
                if rowspan > 0:  # Только если ячейка учитывается
                    col_idx += colspan
                    max_cols = max(max_cols, col_idx)
                    
                    if is_merged:
                        table_info['merged_cells'].append({
                            'row': row_idx,
                            'col': col_idx - colspan,
                            'colspan': colspan,
                            'rowspan': rowspan,
                            'vmerge': vmerge,
                        })
            
            row_data['cells_count'] = len([c for c in row_data['cells'] if c['rowspan'] > 0])
            table_info['rows'].append(row_data)
        
        table_info['cols_count'] = max_cols
        
        # Создаем упрощенную структуру данных
        table_data = []
        for row_info in table_info['rows']:
            row_cells = [cell['text'] for cell in row_info['cells'] if cell['rowspan'] > 0]
            table_data.append(row_cells)
        
        table_info['data'] = table_data
        
        return table_info
    except Exception as e:
        print(f"  ⚠ Ошибка при извлечении таблицы из XML элемента (позиция {xml_pos}): {e}")
        return None


def build_hierarchy_from_headers(
    all_headers: List[Dict[str, Any]],
    all_xml_elements: List[Dict[str, Any]],
    docx_tables: List[Dict[str, Any]],
    docx_images: List[Dict[str, Any]],
    captions_with_text: List[Dict[str, Any]] = None,
    docx_path: Path = None,
    caption_rules: Dict[str, Any] = None,
    saved_images_map: Dict[int, Dict[str, Any]] = None,
    header_rules: Dict[str, Any] = None
) -> List[Element]:
    """
    Строит полную иерархию документа из элементов XML.
    
    КЛЮЧЕВОЙ ПРИНЦИП: обрабатываем ВСЕ элементы XML строго по порядку xml_position.
    Каждый элемент либо добавляется в результат, либо является пустым. Ничего не пропускаем.
    """
    elements: List[Element] = []
    # header_stack: (level, element_id, is_numbered)
    header_stack: List[Tuple[int, str, bool]] = []
    element_id_counter = 1
    
    MAX_TEXT_BLOCK_SIZE = 3000
    MAX_PARAGRAPHS_PER_BLOCK = 10
    
    # ========== ШАГ 1: Построение индексов (всё предвычисляем) ==========
    
    # Индекс заголовков: xml_position -> header_data
    header_by_pos = {}
    for h in all_headers:
        pos = h.get('xml_position')
        if pos is not None:
            header_by_pos[pos] = h
    
    # Индекс таблиц: xml_position -> table_data
    tables_by_position = {t.get('xml_position'): t for t in docx_tables}
    
    # Индекс изображений: xml_position -> image_data
    images_by_position = {img.get('xml_position'): img for img in docx_images}
    
    # Кэш свойств параграфов (чтобы не открывать ZIP повторно)
    properties_cache = {}
    
    def get_properties(pos):
        if pos not in properties_cache:
            properties_cache[pos] = extract_paragraph_properties_from_xml(docx_path, pos)
        return properties_cache[pos]
    
    # Множество позиций, обработанных как caption (чтобы не дублировать)
    caption_positions_set = set()
    
    # Текущий текстовый блок
    current_text_block = []
    current_text_positions = []
    current_text_size = 0
    
    print(f"  Элементов в XML: {len(all_xml_elements)}")
    print(f"  Заголовков (из OCR+правил): {len(header_by_pos)}")
    print(f"  Таблиц: {len(tables_by_position)}")
    print(f"  Изображений: {len(images_by_position)}")
    
    # ========== Вспомогательные функции ==========
    
    def flush_text_block():
        """Сохраняет накопленный текстовый блок как элемент.
        Если блок содержит нумерованные элементы списка (1., 2., 3., ...), разбивает их на list_item."""
        nonlocal current_text_block, current_text_positions, current_text_size, element_id_counter
        if not current_text_block:
            return
        
        # ВАЖНО: Проверяем, содержит ли text блок нумерованные элементы списка
        # ВАЖНО: Сохраняем порядок: текст ДО списка → элементы списка → текст ПОСЛЕ списка
        # Работаем напрямую с current_text_block и current_text_positions
        processed_elements = []  # Список элементов в правильном порядке: (type, content, xml_pos)
        
        i = 0
        while i < len(current_text_block):
            para = current_text_block[i].strip()
            if not para:
                i += 1
                continue
            
            # Проверяем, является ли параграф нумерованным элементом списка
            match = re.match(r'^(\d+)\.\s+(.+)$', para)
            if match:
                item_num = int(match.group(1))
                item_text = match.group(2).strip()
                
                # Проверяем, является ли это частью последовательности (1., 2., 3., ...)
                # Ищем следующие параграфы с последовательной нумерацией
                sequence = [(item_num, item_text, i)]
                j = i + 1
                expected_num = item_num + 1
                
                while j < len(current_text_block):
                    next_para = current_text_block[j].strip()
                    if not next_para:
                        j += 1
                        continue
                    next_match = re.match(r'^(\d+)\.\s+(.+)$', next_para)
                    if next_match and int(next_match.group(1)) == expected_num:
                        sequence.append((expected_num, next_match.group(2).strip(), j))
                        expected_num += 1
                        j += 1
                    else:
                        break
                
                # Если нашли последовательность из 2+ элементов - это список
                if len(sequence) >= 2:
                    # Добавляем все элементы последовательности как list_item в правильном порядке
                    for seq_num, seq_text, seq_idx in sequence:
                        list_item_content = f"{seq_num}. {seq_text}"
                        xml_pos_for_item = current_text_positions[seq_idx] if seq_idx < len(current_text_positions) else (current_text_positions[-1] if current_text_positions else 0)
                        processed_elements.append(('list_item', list_item_content, xml_pos_for_item))
                    i = j
                    continue
            
            # Если не нумерованный элемент списка - добавляем как текст
            xml_pos_for_text = current_text_positions[i] if i < len(current_text_positions) else (current_text_positions[-1] if current_text_positions else 0)
            processed_elements.append(('text', current_text_block[i], xml_pos_for_text))
            i += 1
        
        # Теперь добавляем элементы в правильном порядке
        text_parts = []
        text_positions = []
        
        for elem_type, elem_content, elem_xml_pos in processed_elements:
            if elem_type == 'list_item':
                # Если накопился текст - сначала сохраняем его
                if text_parts:
                    text_content = '\n\n'.join(text_parts)
                    text_element = Element(
                        id=f"{element_id_counter:08d}",
                        type=ElementType.TEXT,
                        content=text_content,
                        parent_id=header_stack[-1][1] if header_stack else None,
                        metadata={
                            'xml_positions': list(text_positions),
                            'text_source': 'xml',
                            'size': len(text_content)
                        }
                    )
                    elements.append(text_element)
                    element_id_counter += 1
                    text_parts = []
                    text_positions = []
                
                # Добавляем list_item
                list_item_element = Element(
                    id=f"{element_id_counter:08d}",
                    type=ElementType.LIST_ITEM,
                    content=elem_content,
                    parent_id=header_stack[-1][1] if header_stack else None,
                    metadata={
                        'xml_position': elem_xml_pos,
                        'text_source': 'xml',
                        'list_type': 'numbered'
                    }
                )
                elements.append(list_item_element)
                element_id_counter += 1
            else:  # text
                # Накопиваем текст
                text_parts.append(elem_content)
                text_positions.append(elem_xml_pos)
        
        # Если остался текст - сохраняем его
        if text_parts:
            text_content = '\n\n'.join(text_parts)
            text_element = Element(
                id=f"{element_id_counter:08d}",
                type=ElementType.TEXT,
                content=text_content,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'xml_positions': list(text_positions),
                    'text_source': 'xml',
                    'size': len(text_content)
                }
            )
            elements.append(text_element)
            element_id_counter += 1
        
        current_text_block = []
        current_text_positions = []
        current_text_size = 0
    
    def add_header_element(text, level, xml_pos, found_by_rules=False, ocr_header=None):
        """Создаёт элемент заголовка и обновляет стек."""
        nonlocal element_id_counter
        flush_text_block()
        
        header_type_map = {
            1: ElementType.HEADER_1, 2: ElementType.HEADER_2,
            3: ElementType.HEADER_3, 4: ElementType.HEADER_4,
            5: ElementType.HEADER_5, 6: ElementType.HEADER_6,
        }
        element_type = header_type_map.get(level, ElementType.HEADER_1)
        
        while header_stack and header_stack[-1][0] >= level:
            header_stack.pop()
        parent_id = header_stack[-1][1] if header_stack else None
        
        ocr_metadata = {}
        if ocr_header:
            ocr_metadata = {
                'ocr_bbox': ocr_header.get('bbox', []),
                'ocr_page': ocr_header.get('page_num', 0),
                'ocr_text': ocr_header.get('text', ''),
                'text_source': 'ocr_then_xml'
            }
        else:
            ocr_metadata = {'text_source': 'xml_only'}
        
        header_element = Element(
            id=f"{element_id_counter:08d}",
            type=element_type,
            content=text,
            parent_id=parent_id,
            metadata={
                'xml_position': xml_pos,
                'level': level,
                'found_by_rules': found_by_rules,
                **ocr_metadata
            }
        )
        elements.append(header_element)
        element_id_counter += 1
        is_numbered = bool(re.match(r'^\d+', text.strip()))
        header_stack.append((level, header_element.id, is_numbered))
    
    def determine_header_level(text, properties, header_data=None):
        """Определяет уровень заголовка по тексту и свойствам."""
        # 0. Структурные ключевые слова = ВСЕГДА уровень 1 (максимальный приоритет)
        # Это важно, чтобы "ВВЕДЕНИЕ", "ЗАКЛЮЧЕНИЕ", "РЕФЕРАТ", "СОДЕРЖАНИЕ" всегда были уровнем 1
        # независимо от header_data.level, header_stack или других факторов
        if is_structural_keyword(text):
            return 1
        
        # 0.3. Паттерны "Глава X", "Часть X", "Раздел X" = ВСЕГДА уровень 1
        # Это важно для заголовков типа "Глава 2. Состояние издательской деятельности..."
        text_lower = text.strip().lower()
        chapter_patterns = [
            r'^глава\s+\d+',
            r'^часть\s+\d+',
            r'^раздел\s+\d+',
            r'^chapter\s+\d+',
            r'^part\s+\d+',
            r'^section\s+\d+',
        ]
        for pattern in chapter_patterns:
            if re.match(pattern, text_lower):
                return 1
        
        # 0.5. Нумерованные заголовки уровня 1 (просто "1", "2", "3" без подуровня) = ВСЕГДА уровень 1
        # Это важно для заголовков типа "1 Литобзор", "2 Методы" и т.д.
        # Проверяем ДО проверки стиля и header_data.level, чтобы гарантировать приоритет
        numbered_match = re.match(r'^(\d+)(?:\s|\.|$)', text.strip())
        if numbered_match:
            # Проверяем, есть ли подуровни (точки после числа)
            full_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if full_match:
                # Если есть подуровни - обрабатываем ниже
                if not full_match.group(2) and not full_match.group(3):
                    # Просто "1", "2", "3" без подуровня - это ВСЕГДА уровень 1
                    return 1
        
        # 1. Если стиль = число ("1", "2", "3") — приоритет
        style = properties.get('style')
        if style and style.isdigit():
            return int(style)
        
        # 2. Стиль Heading/заголовок
        if properties.get('is_heading_style') and properties.get('level'):
            return properties['level']
        
        # 3. Из нумерации — приоритет над header_data.level
        # Нумерация "12.1." = level 2, "12.1.1." = level 3, "12." = level 1
        numbered_level = None
        match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
        if match:
            if match.group(3):
                numbered_level = 3
            elif match.group(2):
                numbered_level = 2
            elif match.group(1):
                numbered_level = 1
        
        # Если нумерация определила уровень 1 (просто "1", без подуровня) — это ВСЕГДА уровень 1
        # независимо от header_data.level, header_stack или других факторов
        # Это важно для заголовков типа "1 Литобзор", "2 Методы" и т.д.
        if numbered_level == 1:
            return 1
        
        # Если нумерация определила уровень 2 или 3 — используем его
        if numbered_level is not None:
            return numbered_level
        
        # 4. Если в header_data есть level — используем как fallback
        # НО: структурные ключевые слова и нумерация уровня 1 уже обработаны выше
        if header_data and header_data.get('level') is not None:
            lvl = header_data.get('level')
            if isinstance(lvl, str):
                try:
                    lvl = int(lvl)
                except:
                    lvl = None
            if lvl and lvl != 'unknown':
                return lvl
        
        # 6. По контексту: ищем ближайший НУМЕРОВАННЫЙ родитель в стеке
        # Это предотвращает каскадное увеличение уровней для жирных ненумерованных заголовков
        # Пример: "3.3." (level 2) → "Главная страница" (level 3) → "Страница со списком..." (level 3, NOT 4)
        # ВАЖНО: Структурные ключевые слова и нумерация уровня 1 уже обработаны выше
        if header_stack:
            is_current_numbered = bool(re.match(r'^\d+', text.strip()))
            if not is_current_numbered:
                # Для ненумерованных: найти ближайший нумерованный/структурный родитель
                for stack_level, _, stack_is_numbered in reversed(header_stack):
                    if stack_is_numbered:
                        return min(stack_level + 1, 6)
                # Если нет нумерованных родителей — использовать уровень последнего заголовка
                return header_stack[-1][0]
            else:
                # Для нумерованных: уровень ниже последнего
                # НО: если нумерация определила уровень 1, мы уже вернули 1 выше
                last_level = header_stack[-1][0]
                return min(last_level + 1, 6)
        
        # 7. Финальная проверка: структурные ключевые слова ВСЕГДА уровень 1
        # Это гарантирует, что даже если предыдущие проверки не сработали, структурные слова будут уровнем 1
        if is_structural_keyword(text):
            return 1
        
        return 1
    
    def is_header_by_properties(text, properties):
        """Проверяет, является ли параграф заголовком по его свойствам XML."""
        text = text.strip()
        if not text or text.endswith(':'):
            return False
        if is_table_caption(text) or is_image_caption(text):
            return False
        if is_definition_pattern(text):
            return False
        if is_separator_line(text):
            return False
        if is_list_item_pattern(text):
            return False
        if is_document_metadata(text):
            return False
        if is_list_header(text):
            return False
        
        # Стиль "1", "2", "3" — однозначно заголовок
        style = properties.get('style')
        if style and style.isdigit():
            return True
        
        # is_heading_style (Heading1, Heading2, Title...)
        if properties.get('is_heading_style'):
            return True
        
        # Нумерованный паттерн — требуем доп. подтверждение: жирность ИЛИ стиль заголовка
        # Без этого обычный текст "1. Апробация..." ложно определяется как заголовок
        if not properties.get('is_list_item'):
            if any(re.match(p, text) for p in [
                r'^\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]'
            ]):
                if properties.get('is_bold') or properties.get('is_heading_style'):
                    return True
        
        # Структурное ключевое слово
        if is_structural_keyword(text):
            return True
        
        # Жирный, короткий, не элемент списка → потенциальный заголовок (уровень 3)
        # Пример: "Главная страница", "Описание алгоритма сравнения профессий"
        # ВАЖНО: is_bold теперь означает, что ВЕСЬ текст жирный (>70% по длине)
        if (properties.get('is_bold') and
            not properties.get('is_list_item') and
            len(text) <= 100):
            return True
        
        # Проверка на Caps Lock (заглавные буквы) - дополнительный признак заголовка
        # Если текст написан заглавными буквами (70%+ букв заглавные), это может быть заголовок
        def is_mostly_uppercase(text: str) -> bool:
            """Проверяет, написано ли большинство букв заглавными (Caps Lock)."""
            if not text or not text.strip():
                return False
            letters = [c for c in text if c.isalpha()]
            if len(letters) < 3:  # Слишком короткий текст
                return False
            uppercase_count = sum(1 for c in letters if c.isupper())
            return uppercase_count / len(letters) >= 0.7  # 70% букв заглавные
        
        if (is_mostly_uppercase(text) and
            not properties.get('is_list_item') and
            len(text) >= 3 and len(text) <= 200):  # Не слишком короткий и не слишком длинный
            return True
        
        return False
    
    # ========== ШАГ 2: Основной цикл — ОДНА итерация по всем элементам ==========
    
    # Отладка: запись в файл
    debug_log = []
    
    for xml_elem in all_xml_elements:
        xml_pos = xml_elem.get('xml_position', 0)
        elem_type = xml_elem.get('type')
        
        # Отладка всех элементов
        txt_preview = xml_elem.get('text', '')[:60].replace('\n', ' ')
        debug_log.append(f"[pos={xml_pos}] type={elem_type}, text='{txt_preview}'")

        
        # ---- ТАБЛИЦА ----
        if elem_type == 'table':
            flush_text_block()
            
            table_data = tables_by_position.get(xml_pos)
            if table_data is None:
                table_elem = xml_elem.get('element')
                if table_elem is not None:
                    table_data = extract_table_from_xml_element(table_elem, xml_pos, docx_path)
                    if table_data:
                        print(f"  ✓ Извлечена пропущенная таблица из XML (позиция {xml_pos})")
            
            if table_data:
                # Проверяем, является ли предыдущий элемент подписью к таблице
                has_caption = (
                    elements and
                    elements[-1].type == ElementType.CAPTION and
                    is_table_caption(elements[-1].content)
                )
                
                elements.append(Element(
                    id=f"{element_id_counter:08d}",
                    type=ElementType.TABLE,
                    content=json.dumps(table_data, ensure_ascii=False, default=str, indent=2),
                    parent_id=header_stack[-1][1] if header_stack else None,
                    metadata={
                        'xml_position': xml_pos,
                        'table_index': table_data.get('index', 0),
                        'rows_count': table_data.get('rows_count', 0),
                        'cols_count': table_data.get('cols_count', 0),
                        'text_source': 'xml',
                        'has_caption': has_caption
                    }
                ))
                element_id_counter += 1
            continue
        
        # ---- ПАРАГРАФ ----
        if elem_type != 'paragraph':
            continue
        
        text = xml_elem.get('text', '').strip()
        text_raw = xml_elem.get('text', '')
        text_size = len(text_raw)
        has_image = xml_elem.get('has_image', False)
        
        # 1. ИЗОБРАЖЕНИЕ (проверяем первым)
        if xml_pos in images_by_position:
            flush_text_block()
            
            image_data = images_by_position[xml_pos]
            
            saved_info = saved_images_map.get(xml_pos) if saved_images_map else None
            if saved_info:
                image_index = saved_info.get('image_index', image_data.get('index', 0))
                page_num = saved_info.get('page_num', 0)
                image_content = f"Image {image_index} (page {page_num + 1})"
                saved_name = saved_info.get('saved_name', '')
            else:
                image_path = image_data.get('image_path', '')
                image_content = Path(image_path).name if image_path else ''
                saved_name = image_content
                page_num = 0
            
            # Проверяем, является ли предыдущий элемент подписью к изображению
            has_caption = (
                elements and
                elements[-1].type == ElementType.CAPTION and
                is_image_caption(elements[-1].content)
            )
            
            elements.append(Element(
                id=f"{element_id_counter:08d}", type=ElementType.IMAGE,
                content=image_content,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'xml_position': xml_pos,
                    'image_index': saved_info.get('image_index', image_data.get('index', 0)) if saved_info else image_data.get('index', 0),
                    'image_path': image_data.get('image_path', ''),
                    'saved_name': saved_name,
                    'page_num': page_num,
                    'width': image_data.get('width'),
                    'height': image_data.get('height'),
                    'text_source': 'xml',
                    'has_caption': has_caption
                }
            ))
            element_id_counter += 1
            continue
        
        # 2. Пропускаем пустые параграфы (если нет изображения)
        if not text and not has_image:
            continue
        
        # 3. Уже обработано как caption
        if xml_pos in caption_positions_set:
            continue
        
        # 4. Получаем свойства параграфа (ОДИН раз, с кэшем)
        props = get_properties(xml_pos)
        
        # 5. ЗАГОЛОВОК (из OCR+правил)
        if xml_pos in header_by_pos:
            header_data = header_by_pos[xml_pos]
            header_text = text if text else header_data.get('text', '').strip()
            
            if not (header_text.endswith(':') or is_table_caption(header_text) or is_image_caption(header_text)):
                # ВАЖНО: Пропускаем метаданные документа и заголовки списков
                if is_document_metadata(header_text):
                    debug_log.append(f"  → skipped header_by_pos (метаданные документа): '{header_text[:60]}'")
                    # Добавляем в text блок
                    text_size = len(text_raw)
                    if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE or len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
                        flush_text_block()
                    current_text_block.append(text_raw)
                    current_text_positions.append(xml_pos)
                    current_text_size += text_size
                    continue
                
                if is_list_header(header_text):
                    debug_log.append(f"  → skipped header_by_pos (заголовок списка): '{header_text[:60]}'")
                    # Добавляем в text блок
                    text_size = len(text_raw)
                    if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE or len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
                        flush_text_block()
                    current_text_block.append(text_raw)
                    current_text_positions.append(xml_pos)
                    current_text_size += text_size
                    continue
                
                # ВАЖНО: Проверяем, не является ли это частью последовательности списка
                is_part_of_list_sequence = False
                header_match = re.match(r'^(\d+)\.\s+(.+)$', header_text)
                if header_match:
                    curr_num = int(header_match.group(1))
                    # Ищем текущий элемент в all_xml_elements
                    current_elem_idx = None
                    for idx, xml_elem in enumerate(all_xml_elements):
                        if xml_elem.get('xml_position') == xml_pos:
                            current_elem_idx = idx
                            break
                    
                    if current_elem_idx is not None:
                        # Ищем ближайшие параграфы с последовательной нумерацией
                        for offset in range(1, min(6, current_elem_idx + 1)):
                            prev_elem = all_xml_elements[current_elem_idx - offset]
                            if prev_elem.get('type') == 'paragraph':
                                prev_text = prev_elem.get('text', '').strip()
                                prev_match = re.match(r'^(\d+)\.\s+(.+)$', prev_text)
                                if prev_match:
                                    prev_num = int(prev_match.group(1))
                                    if prev_num == curr_num - 1:
                                        is_part_of_list_sequence = True
                                        break
                                elif prev_text:
                                    break
                        
                        if not is_part_of_list_sequence:
                            for offset in range(1, min(6, len(all_xml_elements) - current_elem_idx)):
                                next_elem = all_xml_elements[current_elem_idx + offset]
                                if next_elem.get('type') == 'paragraph':
                                    next_text = next_elem.get('text', '').strip()
                                    next_match = re.match(r'^(\d+)\.\s+(.+)$', next_text)
                                    if next_match:
                                        next_num = int(next_match.group(1))
                                        if next_num == curr_num + 1:
                                            is_part_of_list_sequence = True
                                            break
                                    elif next_text:
                                        break
                
                # Если это часть последовательности списка - не заголовок, добавляем в text блок
                if is_part_of_list_sequence:
                    debug_log.append(f"  → TEXT (часть последовательности списка, был header_by_pos): '{header_text[:60]}'")
                    # Добавляем в text блок, он будет обработан в flush_text_block как list_item
                    text_size = len(text_raw)
                    if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE or len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
                        flush_text_block()
                    current_text_block.append(text_raw)
                    current_text_positions.append(xml_pos)
                    current_text_size += text_size
                    continue
                
                # ВАЖНО: Если элемент найден в OCR как заголовок, но в XML он list_item,
                # делаем его list_item, но добавляем в metadata флаг, что OCR определил его как заголовок
                if props.get('is_list_item'):
                    debug_log.append(f"  → LIST_ITEM (OCR определил как заголовок, но в XML это list_item): '{header_text[:60]}'")
                    flush_text_block()
                    level = determine_header_level(header_text, props, header_data)
                    elements.append(Element(
                        id=f"{element_id_counter:08d}", type=ElementType.LIST_ITEM,
                        content=text,
                        parent_id=header_stack[-1][1] if header_stack else None,
                        metadata={
                            'xml_position': xml_pos,
                            'list_type': props.get('list_type', 'unknown'),
                            'text_source': 'xml',
                            'ocr_detected_as_header': True,  # Флаг: OCR определил как заголовок
                            'ocr_header_level': level,  # Уровень, который определил OCR
                            'ocr_bbox': header_data.get('ocr_header', {}).get('bbox', []) if header_data.get('ocr_header') else [],
                            'ocr_page': header_data.get('ocr_header', {}).get('page_num', 0) if header_data.get('ocr_header') else 0,
                            'ocr_text': header_data.get('ocr_header', {}).get('text', '') if header_data.get('ocr_header') else ''
                        }
                    ))
                    element_id_counter += 1
                    continue
                
                level = determine_header_level(header_text, props, header_data)
                
                # ВАЖНО: Проверяем нарушение последовательности нумерации относительно последнего заголовка
                header_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', header_text.strip())
                if header_match and header_stack:
                    curr_num = int(header_match.group(1))
                    curr_sub = header_match.group(2)
                    
                    # Ищем последний нумерованный заголовок в header_stack
                    for stack_level, stack_header_id, stack_is_numbered in reversed(header_stack):
                        if stack_is_numbered:
                            # Находим элемент заголовка по ID
                            for elem in elements:
                                if elem.id == stack_header_id:
                                    prev_text = elem.content.strip()
                                    prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text)
                                    if prev_match:
                                        prev_num = int(prev_match.group(1))
                                        prev_sub = prev_match.group(2)
                                        
                                        # Проверяем нарушение последовательности
                                        is_sequence_violation = False
                                        if curr_num < prev_num:
                                            if prev_num - curr_num > 1:
                                                is_sequence_violation = True
                                            elif prev_num - curr_num == 1 and prev_sub:
                                                is_sequence_violation = True
                                        elif curr_num == prev_num and prev_sub and curr_sub:
                                            if int(curr_sub) < int(prev_sub):
                                                is_sequence_violation = True
                                        elif curr_num == 1 and prev_num > 1:
                                            is_sequence_violation = True
                                        
                                        if is_sequence_violation and level >= stack_level:
                                            debug_log.append(f"  → TEXT (нарушение последовательности нумерации): '{header_text[:60]}'")
                                            # Добавляем в text блок
                                            text_size = len(text_raw)
                                            if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE or len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
                                                flush_text_block()
                                            current_text_block.append(text_raw)
                                            current_text_positions.append(xml_pos)
                                            current_text_size += text_size
                                            continue
                                    break
                            break
                
                debug_log.append(f"  → HEADER (OCR/rules) level={level}: '{header_text[:60]}'")
                add_header_element(
                    header_text, level, xml_pos,
                    found_by_rules=header_data.get('found_by_rules', False),
                    ocr_header=header_data.get('ocr_header')
                )
                continue
            else:
                debug_log.append(f"  → skipped header_by_pos (ends with : or caption): '{header_text[:60]}'")
                print(f"  ⚠ Заголовок пропущен в иерархии (заканчивается на ':' или caption): '{header_text[:60]}'  (pos={xml_pos})")
        
        # 6. ЗАГОЛОВОК (найден по свойствам XML — стиль, нумерация, ключевые слова)
        # ВАЖНО: Перед проверкой заголовка проверяем, не является ли это частью последовательности списка
        is_part_of_list_sequence = False
        text_match = re.match(r'^(\d+)\.\s+(.+)$', text)
        if text_match:
            curr_num = int(text_match.group(1))
            # Ищем текущий элемент в all_xml_elements
            current_elem_idx = None
            for idx, xml_elem in enumerate(all_xml_elements):
                if xml_elem.get('xml_position') == xml_pos:
                    current_elem_idx = idx
                    break
            
            if current_elem_idx is not None:
                # Ищем ближайшие параграфы (не только соседние, т.к. между ними могут быть таблицы/изображения)
                # Проверяем предыдущие элементы (в пределах 5 позиций)
                for offset in range(1, min(6, current_elem_idx + 1)):
                    prev_elem = all_xml_elements[current_elem_idx - offset]
                    if prev_elem.get('type') == 'paragraph':
                        prev_text = prev_elem.get('text', '').strip()
                        prev_match = re.match(r'^(\d+)\.\s+(.+)$', prev_text)
                        if prev_match:
                            prev_num = int(prev_match.group(1))
                            # Если предыдущий элемент - это предыдущий номер (1. → 2., 2. → 3., ...)
                            if prev_num == curr_num - 1:
                                is_part_of_list_sequence = True
                                break
                        elif prev_text:  # Если есть текст, но не нумерованный - прерываем поиск
                            break
                
                # Проверяем следующие элементы (в пределах 5 позиций)
                if not is_part_of_list_sequence:
                    for offset in range(1, min(6, len(all_xml_elements) - current_elem_idx)):
                        next_elem = all_xml_elements[current_elem_idx + offset]
                        if next_elem.get('type') == 'paragraph':
                            next_text = next_elem.get('text', '').strip()
                            next_match = re.match(r'^(\d+)\.\s+(.+)$', next_text)
                            if next_match:
                                next_num = int(next_match.group(1))
                                # Если следующий элемент - это следующий номер (1. → 2., 2. → 3., ...)
                                if next_num == curr_num + 1:
                                    is_part_of_list_sequence = True
                                    break
                            elif next_text:  # Если есть текст, но не нумерованный - прерываем поиск
                                break
        
        # Если это часть последовательности списка - не заголовок, добавляем в text блок
        if is_part_of_list_sequence:
            if xml_pos <= 35:
                debug_log.append(f"  → TEXT (часть последовательности списка): '{text[:60]}'")
            # Добавляем в text блок, он будет обработан в flush_text_block как list_item
            text_size = len(text_raw)
            if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE or len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
                flush_text_block()
            current_text_block.append(text_raw)
            current_text_positions.append(xml_pos)
            current_text_size += text_size
            continue
        
        if is_header_by_properties(text, props):
            level = determine_header_level(text, props)
            
            # ВАЖНО: Проверяем нарушение последовательности нумерации относительно последнего заголовка
            text_match_seq = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if text_match_seq and header_stack:
                curr_num = int(text_match_seq.group(1))
                curr_sub = text_match_seq.group(2)
                
                # Ищем последний нумерованный заголовок в header_stack
                for stack_level, stack_header_id, stack_is_numbered in reversed(header_stack):
                    if stack_is_numbered:
                        # Находим элемент заголовка по ID
                        for elem in elements:
                            if elem.id == stack_header_id:
                                prev_text = elem.content.strip()
                                prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text)
                                if prev_match:
                                    prev_num = int(prev_match.group(1))
                                    prev_sub = prev_match.group(2)
                                    
                                    # Проверяем нарушение последовательности
                                    is_sequence_violation = False
                                    if curr_num < prev_num:
                                        if prev_num - curr_num > 1:
                                            is_sequence_violation = True
                                        elif prev_num - curr_num == 1 and prev_sub:
                                            is_sequence_violation = True
                                    elif curr_num == prev_num and prev_sub and curr_sub:
                                        if int(curr_sub) < int(prev_sub):
                                            is_sequence_violation = True
                                    elif curr_num == 1 and prev_num > 1:
                                        is_sequence_violation = True
                                    
                                    if is_sequence_violation and level >= stack_level:
                                        if xml_pos <= 35:
                                            debug_log.append(f"  → TEXT (нарушение последовательности нумерации): '{text[:60]}'")
                                        # Добавляем в text блок
                                        text_size = len(text_raw)
                                        if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE or len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
                                            flush_text_block()
                                        current_text_block.append(text_raw)
                                        current_text_positions.append(xml_pos)
                                        current_text_size += text_size
                                        continue
                                break
                        break
            
            if xml_pos <= 35:
                debug_log.append(f"  → HEADER (properties) level={level}: '{text[:60]}'")
            add_header_element(text, level, xml_pos, found_by_rules=False)
            continue
        
        # 7. CAPTION по паттерну
        if is_table_caption(text) or is_image_caption(text):
            if xml_pos <= 35:
                debug_log.append(f"  → CAPTION: '{text[:60]}'")
            flush_text_block()
            caption_positions_set.add(xml_pos)
            caption_type = 'table' if is_table_caption(text) else 'image'
            elements.append(Element(
                id=f"{element_id_counter:08d}", type=ElementType.CAPTION,
                content=text,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={'xml_position': xml_pos, 'caption_type': caption_type, 'text_source': 'xml'}
            ))
            element_id_counter += 1
            continue
        
        # 8. ЭЛЕМЕНТ СПИСКА
        if props.get('is_list_item'):
            if xml_pos <= 35:
                debug_log.append(f"  → LIST_ITEM: '{text[:60]}'")
            flush_text_block()
            elements.append(Element(
                id=f"{element_id_counter:08d}", type=ElementType.LIST_ITEM,
                content=text,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'xml_position': xml_pos,
                    'list_type': props.get('list_type', 'unknown'),
                    'text_source': 'xml'
                }
            ))
            element_id_counter += 1
            continue
        
        # 9. ОБЫЧНЫЙ ТЕКСТ — добавляем в текстовый блок
        if xml_pos <= 35:
            debug_log.append(f"  → TEXT: '{text[:60]}' (block_size={current_text_size}, paras={len(current_text_block)})")
        if current_text_size + text_size > MAX_TEXT_BLOCK_SIZE or len(current_text_block) >= MAX_PARAGRAPHS_PER_BLOCK:
            flush_text_block()
        
        current_text_block.append(text_raw)
        current_text_positions.append(xml_pos)
        current_text_size += text_size
    
    # Сохраняем последний текстовый блок
    flush_text_block()
    
    # ========== ШАГ 3: Пост-обработка — связываем изображения и таблицы с подписями ==========
    # Каждый caption может быть привязан только к ОДНОМУ изображению/таблице.
    # Приоритет: сначала ищем caption ПОСЛЕ элемента (обычный порядок в документе: Изображение → Подпись).
    linked_captions = set()  # ID уже привязанных caption
    
    # --- Изображения ---
    for i, elem in enumerate(elements):
        if elem.type == ElementType.IMAGE:
            caption_elem = None
            # Приоритет 1: caption ПОСЛЕ изображения
            if i + 1 < len(elements) and elements[i + 1].type == ElementType.CAPTION and is_image_caption(elements[i + 1].content) and elements[i + 1].id not in linked_captions:
                caption_elem = elements[i + 1]
            # Приоритет 2: caption ДО изображения (если после нет)
            elif i > 0 and elements[i - 1].type == ElementType.CAPTION and is_image_caption(elements[i - 1].content) and elements[i - 1].id not in linked_captions:
                caption_elem = elements[i - 1]
            
            if caption_elem:
                linked_captions.add(caption_elem.id)
                # Изображение принадлежит caption → parent_id = caption.id
                elem.parent_id = caption_elem.id
                # Добавляем метаданные изображения в caption
                caption_elem.metadata['image'] = {
                    'image_path': elem.metadata.get('image_path', ''),
                    'saved_name': elem.metadata.get('saved_name', ''),
                    'image_index': elem.metadata.get('image_index', 0),
                    'page_num': elem.metadata.get('page_num', 0),
                    'width': elem.metadata.get('width'),
                    'height': elem.metadata.get('height'),
                    'content': elem.content
                }
                caption_elem.metadata['has_image'] = True
    
    # --- Таблицы ---
    for i, elem in enumerate(elements):
        if elem.type == ElementType.TABLE:
            caption_elem = None
            # Приоритет 1: caption ДО таблицы (обычный порядок: "Таблица X: ..." → [таблица])
            if i > 0 and elements[i - 1].type == ElementType.CAPTION and is_table_caption(elements[i - 1].content) and elements[i - 1].id not in linked_captions:
                caption_elem = elements[i - 1]
            # Приоритет 2: caption ПОСЛЕ таблицы
            elif i + 1 < len(elements) and elements[i + 1].type == ElementType.CAPTION and is_table_caption(elements[i + 1].content) and elements[i + 1].id not in linked_captions:
                caption_elem = elements[i + 1]
            
            if caption_elem:
                linked_captions.add(caption_elem.id)
                elem.parent_id = caption_elem.id
                caption_elem.metadata['has_table'] = True
                caption_elem.metadata['table_xml_position'] = elem.metadata.get('xml_position')
    
    # ========== ШАГ 4: Пост-обработка — определение содержания (оглавления) ==========
    # Содержание обычно начинается с заголовка "Содержание", "Оглавление" и содержит
    # много заголовков подряд без текста между ними
    # Упрощенная логика: просто помечаем элементы между "Содержание" и первым текстовым блоком
    table_of_contents_keywords = ['содержание', 'оглавление', 'contents', 'table of contents', 'coontent']
    
    toc_start_idx = None
    toc_end_idx = None
    
    # Ищем начало содержания
    for i, elem in enumerate(elements):
        if elem.type in [ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3]:
            content_lower = elem.content.strip().lower()
            if any(keyword in content_lower for keyword in table_of_contents_keywords):
                toc_start_idx = i
                break
    
    # Если нашли начало содержания, определяем его конец - первый текстовый блок или элемент списка
    if toc_start_idx is not None:
        consecutive_headers = 0
        for i in range(toc_start_idx + 1, len(elements)):
            elem = elements[i]
            if elem.type in [ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3, ElementType.HEADER_4, ElementType.HEADER_5, ElementType.HEADER_6]:
                consecutive_headers += 1
            elif elem.type == ElementType.TEXT and elem.content.strip():
                # Нашли текстовый блок - это конец содержания
                toc_end_idx = i
                break
            elif elem.type == ElementType.LIST_ITEM:
                # Элемент списка - это тоже конец содержания
                toc_end_idx = i
                break
            elif elem.type in [ElementType.TABLE, ElementType.IMAGE]:
                # Таблица или изображение - это конец содержания
                toc_end_idx = i
                break
            else:
                # Если встретили что-то другое, но было много заголовков подряд - это конец
                if consecutive_headers >= 3:
                    toc_end_idx = i
                    break
        
        # Если не нашли явный конец, но было много заголовков подряд - считаем их все содержанием
        if toc_end_idx is None and consecutive_headers >= 3:
            # Ищем последний заголовок в последовательности
            for i in range(toc_start_idx + 1, len(elements)):
                if i < len(elements) - 1:
                    if elements[i].type in [ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3, ElementType.HEADER_4, ElementType.HEADER_5, ElementType.HEADER_6]:
                        next_elem = elements[i + 1]
                        if next_elem.type not in [ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3, ElementType.HEADER_4, ElementType.HEADER_5, ElementType.HEADER_6]:
                            toc_end_idx = i + 1
                            break
        
        # Помечаем элементы содержания
        if toc_end_idx is not None:
            for i in range(toc_start_idx, toc_end_idx):
                if i < len(elements):
                    elements[i].metadata['is_table_of_contents'] = True
                    # Если это заголовок содержания, можно также пометить его специально
                    if i == toc_start_idx:
                        elements[i].metadata['is_toc_header'] = True
            print(f"  ✓ Определено содержание: элементы {toc_start_idx}-{toc_end_idx-1} ({toc_end_idx - toc_start_idx} элементов)")
    
    # Сохраняем отладочный лог
    if debug_log and docx_path:
        debug_path = Path(docx_path).parent / "debug_hierarchy.txt"
        try:
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(debug_log))
            print(f"  [DEBUG] Лог сохранен: {debug_path}")
        except:
            pass
    
    return elements


def process_docx_complete_pipeline(
    docx_path: Path,
    output_dir: Path,
    skip_first_table: bool = False
) -> ParsedDocument:
    """
    Полный пайплайн обработки DOCX с построением иерархии.
    
    Returns:
        ParsedDocument с полной структурой документа.
    """
    print(f"\n{'='*80}")
    print(f"ПОЛНЫЙ ПАЙПЛАЙН: DOTS OCR → PyMuPDF → XML → Иерархия")
    print(f"DOCX: {docx_path}")
    print(f"{'='*80}\n")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    structure_dir = output_dir / "structure"
    structure_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Конвертация DOCX → PDF
    print("Шаг 1: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан\n")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        raise
    
    # Шаг 2: Layout detection через DOTS OCR
    print("Шаг 2: Layout detection через DOTS OCR...")
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_doc)
    
    ocr_elements = []
    page_images = {}
    
    for page_num in range(total_pages):
        print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            continue
        
        page_images[page_num] = page_image
        
        try:
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image
            )
            
            if success and layout_cells:
                for element in layout_cells:
                    element["page_num"] = page_num
                    ocr_elements.append(element)
        except Exception as e:
            print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    section_headers = [e for e in ocr_elements if e.get("category") == "Section-header"]
    captions = [e for e in ocr_elements if e.get("category") == "Caption"]
    ocr_images = [e for e in ocr_elements if e.get("category") == "Image" or e.get("category") == "Figure"]
    
    print(f"  ✓ Найдено Section-header: {len(section_headers)}")
    print(f"  ✓ Найдено Caption: {len(captions)}")
    print(f"  ✓ Найдено изображений в OCR: {len(ocr_images)}\n")
    
    # Шаг 3: Извлечение текста из PDF через PyMuPDF
    print("Шаг 3: Извлечение текста из PDF через PyMuPDF...")
    elements_to_extract = section_headers + captions
    pdf_text_results = extract_text_from_pdf_by_bbox(elements_to_extract, pdf_doc)
    
    headers_with_text = [r for r in pdf_text_results if r.get("category") == "Section-header"]
    captions_with_text = [r for r in pdf_text_results if r.get("category") == "Caption"]
    
    print(f"\n  ✓ Извлечено текста из заголовков: {len(headers_with_text)}")
    print(f"  ✓ Извлечено текста из подписей: {len(captions_with_text)}\n")
    
    # Шаг 4: Извлечение всех элементов XML
    print("Шаг 4: Извлечение всех элементов XML...")
    all_xml_elements = extract_all_elements_from_docx_xml_ordered(docx_path)
    
    # Шаг 4.1: Парсинг оглавления для дополнительной проверки заголовков
    print("Шаг 4.1: Парсинг оглавления для дополнительной проверки...")
    toc_entries = parse_toc_from_docx(docx_path, all_xml_elements)
    if toc_entries:
        print(f"  ✓ Найдено заголовков в оглавлении: {len(toc_entries)}")
        # Создаем словарь для быстрого поиска: нормализованный текст -> (level, page)
        toc_headers_map = {}
        for toc_entry in toc_entries:
            title = toc_entry.get('title', '').strip()
            if title:
                normalized_title = re.sub(r'\s+', ' ', title.lower().strip())
                level = toc_entry.get('level', 1)
                toc_headers_map[normalized_title] = {
                    'level': level,
                    'page': toc_entry.get('page'),
                    'original_title': title
                }
        print(f"  ✓ Создан индекс оглавления для проверки заголовков\n")
    else:
        print(f"  ⚠ Оглавление не найдено или не парсится\n")
        toc_headers_map = {}
    
    # Шаг 4.2: Поиск заголовков в XML и построение правил
    print("Шаг 4.2: Поиск заголовков в XML и построение правил...")
    
    sorted_headers = sorted(
        headers_with_text,
        key=lambda h: (h.get('page_num', 0), h.get('bbox', [0, 0, 0, 0])[1] if h.get('bbox') else 0)
    )
    
    header_positions = []
    for header in sorted_headers:
        header_text = header.get('text', '')
        if not header_text:
            continue
        
        # ВАЖНО: Ищем от последней найденной позиции + 1 (простой последовательный поиск)
        # НЕ используем page-based estimation, т.к. она пропускает реальные позиции!
        start_from = header_positions[-1]['xml_position'] + 1 if header_positions else 0
        
        xml_pos = find_header_in_xml_by_text(header_text, all_xml_elements, start_from, docx_path, None)
        
        # Если не нашли, пробуем от начала (заголовок мог быть раньше)
        if xml_pos is None and start_from > 0:
            xml_pos = find_header_in_xml_by_text(header_text, all_xml_elements, 0, docx_path, None)
        
        if xml_pos is not None:
            properties = extract_paragraph_properties_from_xml(docx_path, xml_pos)
            is_heading_style = properties.get('is_heading_style', False)
            
            text_stripped = header_text.strip()
            is_numbered_header = any(re.match(p, text_stripped) for p in [
                r'^\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]'
            ])
            
            # Если это элемент списка, но НЕ нумерованный заголовок и НЕ заголовок по стилю - пропускаем
            if properties.get('is_list_item') and not is_numbered_header and not is_heading_style:
                print(f"  ⚠ Пропущен элемент списка (не заголовок): '{header_text[:50]}...' → позиция {xml_pos}")
                continue
            
            # Если это определение ("Термин – описание"), но НЕ заголовок по стилю - пропускаем
            if is_definition_pattern(header_text) and not is_heading_style:
                print(f"  ⚠ Пропущено определение (не заголовок): '{header_text[:50]}...' → позиция {xml_pos}")
                continue
            
            # Если это разделитель ("……………………………………………………….399"), но НЕ заголовок по стилю - пропускаем
            if is_separator_line(header_text) and not is_heading_style:
                print(f"  ⚠ Пропущен разделитель (не заголовок): '{header_text[:50]}...' → позиция {xml_pos}")
                continue
            
            # Если это элемент списка по паттерну ("1) ФИО;", "а) текст"), но НЕ заголовок по стилю - пропускаем
            if is_list_item_pattern(header_text) and not is_heading_style:
                print(f"  ⚠ Пропущен элемент списка по паттерну (не заголовок): '{header_text[:50]}...' → позиция {xml_pos}")
                continue
            
            # Определяем уровень заголовка
            detected_level = None
            # ВАЖНО: Сначала проверяем оглавление для определения уровня
            normalized_header_text = re.sub(r'\s+', ' ', header_text.lower().strip())
            if normalized_header_text in toc_headers_map:
                toc_info = toc_headers_map[normalized_header_text]
                detected_level = toc_info['level']
                print(f"  ✓ Уровень из оглавления: {detected_level}")
            elif is_heading_style and properties.get('level'):
                detected_level = properties.get('level')
            else:
                match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text_stripped)
                if match:
                    if match.group(3):
                        detected_level = 3
                    elif match.group(2):
                        detected_level = 2
                    elif match.group(1):
                        detected_level = 1
            
            header_positions.append({
                'ocr_header': header,
                'xml_position': xml_pos,
                'text': header_text,
                'is_numbered_header': is_numbered_header,
                'level': detected_level,
                'from_toc': normalized_header_text in toc_headers_map  # Флаг: найден в оглавлении
            })
            print(f"  ✓ Найден заголовок в XML: '{header_text[:50]}...' → позиция {xml_pos}" + 
                  (" (нумерованный)" if is_numbered_header else "") +
                  (" (из оглавления)" if normalized_header_text in toc_headers_map else ""))
        else:
            # ВАЖНО: Если заголовок не найден через OCR, но есть в оглавлении - ищем его в XML
            normalized_header_text = re.sub(r'\s+', ' ', header_text.lower().strip())
            if normalized_header_text in toc_headers_map:
                # Пробуем найти заголовок в XML по тексту из оглавления
                toc_info = toc_headers_map[normalized_header_text]
                original_title = toc_info['original_title']
                
                # Ищем от начала документа
                xml_pos_from_toc = find_header_in_xml_by_text(original_title, all_xml_elements, 0, docx_path, None)
                
                if xml_pos_from_toc is not None:
                    properties = extract_paragraph_properties_from_xml(docx_path, xml_pos_from_toc)
                    detected_level = toc_info['level']
                    
                    header_positions.append({
                        'ocr_header': None,  # Не найден через OCR
                        'xml_position': xml_pos_from_toc,
                        'text': original_title,
                        'is_numbered_header': any(re.match(p, original_title.strip()) for p in [
                            r'^\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]'
                        ]),
                        'level': detected_level,
                        'from_toc': True  # Найден через оглавление
                    })
                    print(f"  ✓ Найден заголовок из оглавления в XML: '{original_title[:50]}...' → позиция {xml_pos_from_toc} (уровень {detected_level})")
                else:
                    print(f"  ⚠ Заголовок из оглавления не найден в XML: '{original_title[:50]}...'")
            else:
                print(f"  ⚠ Заголовок не найден в XML: '{header_text[:50]}...'")
    
    # Построение правил для заголовков
    print("\n  Построение правил для поиска пропущенных заголовков...")
    header_rules = build_header_rules_from_found_headers(docx_path, header_positions)
    
    # Поиск captions в XML и построение правил
    print("\n  Поиск captions в XML и построение правил...")
    caption_positions = []
    for caption in captions_with_text:
        caption_text = caption.get('text', '').strip()
        if not caption_text:
            continue
        # Пропускаем очень короткие тексты (< 5 символов) — скорее всего это номера страниц или шум OCR
        if len(caption_text) < 5:
            print(f"  ⚠ Пропущен слишком короткий caption: '{caption_text}'")
            continue
        
        start_from = caption_positions[-1]['xml_position'] + 1 if caption_positions else 0
        xml_pos = find_header_in_xml_by_text(caption_text, all_xml_elements, start_from)
        
        if xml_pos is not None:
            caption_positions.append({
                'ocr_caption': caption,
                'xml_position': xml_pos,
                'text': caption_text
            })
            print(f"  ✓ Найден caption в XML: '{caption_text[:50]}...' → позиция {xml_pos}")
        else:
            print(f"  ⚠ Caption не найден в XML: '{caption_text[:50]}...'")
    
    # Построение правил для captions
    caption_rules = build_caption_rules_from_found_captions(docx_path, caption_positions)
    if caption_rules.get('alignment'):
        print(f"  ✓ Правила captions: выравнивание={caption_rules['alignment']}, размер шрифта={caption_rules.get('font_size', 'N/A'):.1f}pt" if caption_rules.get('font_size') else f"  ✓ Правила captions: выравнивание={caption_rules['alignment']}")
    
    print(f"  Правила для уровней: {list(header_rules.get('by_level', {}).keys())}")
    for level, rules in header_rules.get('by_level', {}).items():
        font_size_str = f"{rules.get('font_size'):.1f}pt" if rules.get('font_size') else "None"
        print(f"    Уровень {level}: шрифт={rules.get('font_name')}, размер={font_size_str}, жирный={rules.get('is_bold')}")
    
    # Поиск пропущенных заголовков
    print("\n  Поиск пропущенных заголовков по правилам и оглавлению...")
    found_positions = [h['xml_position'] for h in header_positions]
    # ВАЖНО: Также собираем тексты уже найденных заголовков, чтобы избежать дублирования
    found_texts = set()
    for h in header_positions:
        text = h.get('text', '').strip()
        if text:
            # Нормализуем текст для сравнения (убираем лишние пробелы, приводим к нижнему регистру)
            normalized_text = re.sub(r'\s+', ' ', text.lower().strip())
            found_texts.add(normalized_text)
    
    # ВАЖНО: Проверяем оглавление - ищем заголовки, которые есть в оглавлении, но не найдены через OCR
    if toc_headers_map:
        print(f"  Проверка оглавления: ищем пропущенные заголовки...")
        for normalized_title, toc_info in toc_headers_map.items():
            if normalized_title not in found_texts:
                original_title = toc_info['original_title']
                level = toc_info['level']
                
                # Ищем заголовок в XML
                xml_pos_from_toc = find_header_in_xml_by_text(original_title, all_xml_elements, 0, docx_path, None)
                
                if xml_pos_from_toc is not None and xml_pos_from_toc not in found_positions:
                    properties = extract_paragraph_properties_from_xml(docx_path, xml_pos_from_toc)
                    
                    # Проверяем, не является ли это элементом списка или определением
                    if (not properties.get('is_list_item') or properties.get('is_heading_style')):
                        if not is_definition_pattern(original_title) and not is_separator_line(original_title):
                            header_positions.append({
                                'ocr_header': None,
                                'xml_position': xml_pos_from_toc,
                                'text': original_title,
                                'is_numbered_header': any(re.match(p, original_title.strip()) for p in [
                                    r'^\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\s+[А-ЯЁA-Z]', r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]'
                                ]),
                                'level': level,
                                'from_toc': True,
                                'found_by_toc': True  # Найден через оглавление
                            })
                            found_positions.append(xml_pos_from_toc)
                            found_texts.add(normalized_title)
                            print(f"  ✓ Найден пропущенный заголовок из оглавления: '{original_title[:50]}...' → позиция {xml_pos_from_toc} (уровень {level})")
    
    missing_headers = find_missing_headers_by_rules(docx_path, all_xml_elements, header_rules, found_positions, found_texts, header_positions)
    
    for missing_header in missing_headers:
        # ВАЖНО: Проверяем уровень из оглавления, если заголовок есть там
        normalized_missing_text = re.sub(r'\s+', ' ', missing_header['text'].lower().strip())
        if normalized_missing_text in toc_headers_map:
            toc_info = toc_headers_map[normalized_missing_text]
            # Используем уровень из оглавления, если он более точный
            missing_header['level'] = toc_info['level']
            missing_header['from_toc'] = True
        
        header_positions.append({
            'ocr_header': None,
            'xml_position': missing_header['xml_position'],
            'text': missing_header['text'],
            'level': missing_header['level'],
            'found_by_rules': True,
            'from_toc': normalized_missing_text in toc_headers_map if 'from_toc' in missing_header else False
        })
    
    header_positions.sort(key=lambda h: h['xml_position'])
    toc_found_count = sum(1 for h in header_positions if h.get('from_toc', False))
    print(f"\n  ✓ Всего заголовков: {len(header_positions)} (найдено через OCR: {len(headers_with_text)}, найдено по правилам: {len(missing_headers)}, найдено через оглавление: {toc_found_count})\n")
    
    # Шаг 5: Извлечение таблиц и изображений из XML
    print("Шаг 5: Извлечение таблиц и изображений из XML...")
    docx_tables = extract_tables_from_docx_xml(docx_path)
    docx_images = extract_images_from_docx_xml(docx_path)
    
    if skip_first_table and docx_tables:
        docx_tables = docx_tables[1:]
        print(f"  ⚠ Пропущена первая таблица (по запросу)")
    
    print(f"  ✓ Извлечено таблиц: {len(docx_tables)}")
    print(f"  ✓ Извлечено изображений: {len(docx_images)}\n")
    
    # Шаг 6: Сохранение изображений из media
    print("Шаг 6: Сохранение изображений из media...")
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    
    # Создаем словарь для сопоставления XML изображений с OCR изображениями
    # Сопоставляем по порядку появления (пока простое сопоставление)
    ocr_images_by_order = sorted(ocr_images, key=lambda x: (x.get('page_num', 0), x.get('bbox', [0, 0, 0, 0])[1] if x.get('bbox') else 0))
    docx_images_by_order = sorted(docx_images, key=lambda x: x.get('xml_position', 0))
    
    # Сохраняем изображения из media с именами "Image X.png"
    saved_images_map = {}  # {xml_position: {'saved_name': 'Image X.png', 'page_num': Y}}
    
    for img_idx, image_data in enumerate(docx_images_by_order, start=1):
        xml_pos = image_data.get('xml_position')
        image_bytes = image_data.get('image_bytes')
        image_path = image_data.get('image_path', '')
        
        if not image_bytes:
            continue
        
        # Определяем номер страницы из OCR (если есть сопоставление)
        page_num = None
        if img_idx <= len(ocr_images_by_order):
            ocr_img = ocr_images_by_order[img_idx - 1]
            page_num = ocr_img.get('page_num', 0)
        
        # Сохраняем изображение с именем "Image X.png"
        saved_name = f"Image {img_idx}.png"
        saved_path = images_dir / saved_name
        
        try:
            image = Image.open(BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            image.save(saved_path, 'PNG')
            
            saved_images_map[xml_pos] = {
                'saved_name': saved_name,
                'page_num': page_num if page_num is not None else 0,
                'image_index': img_idx
            }
            print(f"  ✓ Сохранено: {saved_name} (из {image_path}, страница {page_num + 1 if page_num is not None else '?'})")
        except Exception as e:
            print(f"  ✗ Ошибка сохранения изображения {img_idx}: {e}")
    
    print(f"  ✓ Сохранено изображений: {len(saved_images_map)}\n")
    
    # Шаг 7: Построение иерархии
    print("Шаг 7: Построение иерархии документа...")
    elements = build_hierarchy_from_headers(
        header_positions,
        all_xml_elements,
        docx_tables,
        docx_images,
        captions_with_text,
        docx_path=docx_path,
        caption_rules=caption_rules,
        saved_images_map=saved_images_map,  # Передаем информацию о сохраненных изображениях
        header_rules=header_rules  # Передаем правила для проверки заголовков в текстовых блоках
    )
    
    print(f"  ✓ Создано элементов: {len(elements)}")
    print(f"    - Заголовков: {sum(1 for e in elements if e.type in [ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3, ElementType.HEADER_4, ElementType.HEADER_5, ElementType.HEADER_6])}")
    print(f"    - Текстовых блоков: {sum(1 for e in elements if e.type == ElementType.TEXT)}")
    print(f"    - Таблиц: {sum(1 for e in elements if e.type == ElementType.TABLE)}")
    print(f"    - Изображений: {sum(1 for e in elements if e.type == ElementType.IMAGE)}\n")
    
    # Шаг 8: Создание ParsedDocument
    print("Шаг 8: Создание структуры документа...")
    parsed_doc = ParsedDocument(
        source=str(docx_path),
        format=DocumentFormat.DOCX,
        elements=elements,
        metadata={
            'total_headers': len(header_positions),
            'total_tables': len(docx_tables),
            'total_images': len(docx_images),
            'total_pages': total_pages
        }
    )
    
    # Шаг 8: Сохранение результатов
    print("Шаг 8: Сохранение результатов...")
    
    # Создаем ocr_info отдельно
    ocr_info = {
        'section_headers_found': len(section_headers),
        'captions_found': len(captions),
        'headers_with_text': len(headers_with_text),
        'captions_with_text': len(captions_with_text),
        'header_examples': [
            {
                'text': h.get('text', ''),  # Полный текст
                'bbox': h.get('bbox', []),
                'page': h.get('page_num', 0) + 1,
                'category': 'Section-header'
            }
            for h in headers_with_text[:10]  # Первые 10 примеров
        ],
        'caption_examples': [
            {
                'text': c.get('text', ''),  # Полный текст
                'bbox': c.get('bbox', []),
                'page': c.get('page_num', 0) + 1,
                'category': 'Caption'
            }
            for c in captions_with_text[:10]  # Первые 10 примеров
        ],
        'description': 'Section-header - заголовки разделов, найденные через DOTS OCR, текст извлечен из PDF через PyMuPDF. Caption - подписи к таблицам и изображениям, найденные через DOTS OCR, текст извлечен из PDF через PyMuPDF.'
    }
    
    # Сохраняем ocr_info в отдельный файл
    ocr_info_path = structure_dir / "ocr_info.json"
    with open(ocr_info_path, 'w', encoding='utf-8') as f:
        json.dump(ocr_info, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✓ OCR информация сохранена: {ocr_info_path}")
    
    # Сохраняем JSON структуру БЕЗ ocr_info
    results_json = {
        'source': str(docx_path),
        'format': 'DOCX',
        'metadata': parsed_doc.metadata,
        'elements': [
            {
                'id': e.id,
                'type': e.type.value,
                'content': e.content,  # ПОЛНЫЙ текст без обрезания
                'parent_id': e.parent_id,
                'metadata': e.metadata
            }
            for e in elements
        ],
        'statistics': {
            'total_elements': len(elements),
            'headers': sum(1 for e in elements if e.type in [ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3, ElementType.HEADER_4, ElementType.HEADER_5, ElementType.HEADER_6]),
            'text_blocks': sum(1 for e in elements if e.type == ElementType.TEXT),
            'tables': sum(1 for e in elements if e.type == ElementType.TABLE),
            'images': sum(1 for e in elements if e.type == ElementType.IMAGE),
            'total_text_length': sum(len(e.content) for e in elements if e.type == ElementType.TEXT)
        }
    }
    
    results_json_path = structure_dir / "complete_structure.json"
    with open(results_json_path, 'w', encoding='utf-8') as f:
        json.dump(results_json, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"  ✓ Результаты сохранены: {results_json_path}")
    
    pdf_doc.close()
    
    print(f"\n{'='*80}")
    print(f"ПАЙПЛАЙН ЗАВЕРШЕН УСПЕШНО")
    print(f"  Элементов: {len(elements)}")
    print(f"  Заголовков: {len(header_positions)}")
    print(f"  Таблиц: {len(docx_tables)}")
    print(f"  Изображений: {len(docx_images)}")
    print(f"{'='*80}\n")
    
    return parsed_doc


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # По умолчанию — Diplom2024.docx
        default_docx = Path(__file__).parent / "test_folder" / "Diplom2024.docx"
        if default_docx.exists():
            docx_path = default_docx
        else:
            print("Использование: python docx_complete_pipeline.py <docx_path> [output_dir] [--skip-first-table]")
            sys.exit(1)
    else:
        docx_path = Path(sys.argv[1])
    
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    if len(sys.argv) >= 3 and not sys.argv[2].startswith('--'):
        output_dir = Path(sys.argv[2])
    else:
        output_dir = Path(__file__).parent / "results" / "complete_pipeline" / docx_path.stem
    
    skip_first_table = '--skip-first-table' in sys.argv or 'Diplom2024' in docx_path.name
    
    result = process_docx_complete_pipeline(docx_path, output_dir, skip_first_table=skip_first_table)
    
    print(f"\n✓ Пайплайн завершен успешно!")
