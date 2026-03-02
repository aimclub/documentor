"""
Пайплайн для DOCX: DOTS OCR (структура) → Qwen OCR (текст заголовков/подписей) → XML (блоки между заголовками).

Идея:
1. DOTS OCR находит структуру (Section-header, Caption)
2. Для каждого найденного элемента отправляем изображение в Qwen OCR для получения текста
3. Сохраняем результаты с позициями
4. Используем найденные тексты для поиска в XML
5. Разбиваем XML на блоки между заголовками
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
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
from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
)
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer
from documentor.processing.parsers.pdf.ocr.qwen_ocr import ocr_text_with_qwen

# Используем 2x увеличение для DOTS OCR
RENDER_SCALE = 2.0


def crop_element_from_page_image(
    page_image: Image.Image,
    bbox: List[float],
    padding: int = 10
) -> Image.Image:
    """
    Вырезает элемент из изображения страницы по bbox.
    
    Args:
        page_image: Изображение страницы
        bbox: Координаты [x1, y1, x2, y2]
        padding: Отступ вокруг элемента
    
    Returns:
        Вырезанное изображение
    """
    if not bbox or len(bbox) < 4:
        return page_image
    
    x1, y1, x2, y2 = bbox
    
    # Добавляем отступы
    x1_crop = max(0, int(x1) - padding)
    y1_crop = max(0, int(y1) - padding)
    x2_crop = min(page_image.width, int(x2) + padding)
    y2_crop = min(page_image.height, int(y2) + padding)
    
    # Вырезаем область
    cropped = page_image.crop((x1_crop, y1_crop, x2_crop, y2_crop))
    return cropped


def extract_text_from_ocr_elements_with_qwen(
    ocr_elements: List[Dict[str, Any]],
    page_images: Dict[int, Image.Image]
) -> List[Dict[str, Any]]:
    """
    Извлекает текст из OCR элементов через Qwen OCR.
    
    Args:
        ocr_elements: Список элементов из DOTS OCR
        page_images: Словарь {page_num: Image} с изображениями страниц
    
    Returns:
        Список элементов с извлеченным текстом
    """
    results = []
    
    for element in ocr_elements:
        category = element.get("category", "")
        bbox = element.get("bbox", [])
        page_num = element.get("page_num", 0)
        
        # Обрабатываем только Section-header и Caption
        if category not in ["Section-header", "Caption"]:
            continue
        
        if not bbox or len(bbox) < 4:
            continue
        
        if page_num not in page_images:
            print(f"    ⚠ Изображение страницы {page_num + 1} не найдено")
            continue
        
        page_image = page_images[page_num]
        
        # Вырезаем элемент из изображения
        try:
            cropped_image = crop_element_from_page_image(page_image, bbox)
            
            # OCR через Qwen
            print(f"    OCR через Qwen: {category} (стр. {page_num + 1})...")
            ocr_text = ocr_text_with_qwen(cropped_image)
            
            if ocr_text:
                element_result = {
                    "category": category,
                    "bbox": bbox,
                    "page_num": page_num,
                    "text": ocr_text.strip(),
                    "text_length": len(ocr_text)
                }
                results.append(element_result)
                print(f"      ✓ Извлечено {len(ocr_text)} символов")
            else:
                print(f"      ⚠ Текст не извлечен")
        
        except Exception as e:
            print(f"      ✗ Ошибка OCR: {e}")
            continue
    
    return results


def extract_paragraph_properties_from_xml(
    docx_path: Path,
    xml_position: int
) -> Dict[str, Any]:
    """
    Извлекает свойства параграфа из XML (шрифт, размер, стиль, уровень).
    
    Args:
        docx_path: Путь к DOCX файлу
        xml_position: Позиция параграфа в XML
    
    Returns:
        Словарь с свойствами параграфа
    """
    import zipfile
    import xml.etree.ElementTree as ET
    
    properties = {
        'font_name': None,
        'font_size': None,
        'is_bold': False,
        'is_italic': False,
        'style': None,
        'level': None
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
            
            # Извлекаем стиль параграфа
            pPr = elem.find('w:pPr', NAMESPACES)
            if pPr is not None:
                pStyle = pPr.find('w:pStyle', NAMESPACES)
                if pStyle is not None:
                    style_val = pStyle.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                    properties['style'] = style_val
                    
                    # Определяем уровень заголовка
                    if 'Heading' in style_val or 'heading' in style_val.lower():
                        match = re.search(r'(\d+)', style_val)
                        if match:
                            properties['level'] = int(match.group(1))
                    elif style_val == 'Title':
                        properties['level'] = 1
            
            # Извлекаем свойства шрифта из первого run
            for r in elem.findall('.//w:r', NAMESPACES):
                rPr = r.find('w:rPr', NAMESPACES)
                if rPr is not None:
                    # Шрифт
                    rFonts = rPr.find('w:rFonts', NAMESPACES)
                    if rFonts is not None:
                        font_name = rFonts.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii', '')
                        if font_name:
                            properties['font_name'] = font_name
                    
                    # Размер шрифта
                    sz = rPr.find('w:sz', NAMESPACES)
                    if sz is not None:
                        sz_val = sz.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                        if sz_val:
                            # Размер в половинах пункта, конвертируем в пункты
                            properties['font_size'] = int(sz_val) / 2.0
                    
                    # Жирный
                    b = rPr.find('w:b', NAMESPACES)
                    if b is not None:
                        properties['is_bold'] = True
                    
                    # Курсив
                    i = rPr.find('w:i', NAMESPACES)
                    if i is not None:
                        properties['is_italic'] = True
                
                # Если нашли хотя бы один run с форматированием, выходим
                if properties['font_name'] or properties['font_size']:
                    break
    
    except Exception as e:
        print(f"    Предупреждение: ошибка извлечения свойств параграфа {xml_position}: {e}")
    
    return properties


def find_header_in_xml_by_text(
    header_text: str,
    all_xml_elements: List[Dict[str, Any]],
    start_from: int = 0
) -> Optional[int]:
    """
    Находит заголовок в XML по тексту.
    
    Args:
        header_text: Текст заголовка из OCR
        all_xml_elements: Все элементы из XML
        start_from: Начинать поиск с этой позиции
    
    Returns:
        xml_position найденного заголовка или None
    """
    # Нормализуем текст для сравнения
    header_text_normalized = re.sub(r'\s+', ' ', header_text.lower().strip())
    
    # Ищем в XML элементах
    for i in range(start_from, len(all_xml_elements)):
        elem = all_xml_elements[i]
        if elem.get('type') == 'paragraph':
            xml_text = elem.get('text', '')
            xml_text_normalized = re.sub(r'\s+', ' ', xml_text.lower().strip())
            
            # Проверяем точное совпадение или начало
            if (header_text_normalized == xml_text_normalized or
                xml_text_normalized.startswith(header_text_normalized[:30]) or
                header_text_normalized.startswith(xml_text_normalized[:30])):
                return elem.get('xml_position')
    
    return None


def build_header_rules_from_found_headers(
    docx_path: Path,
    header_positions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Строит правила для поиска заголовков на основе найденных заголовков.
    
    Args:
        docx_path: Путь к DOCX файлу
        header_positions: Список найденных заголовков с их позициями в XML
    
    Returns:
        Словарь с правилами (характеристики заголовков по уровням)
    """
    rules = {
        'by_level': {},  # Правила по уровням
        'common_properties': {}  # Общие свойства всех заголовков
    }
    
    if not header_positions:
        return rules
    
    # Собираем свойства всех найденных заголовков
    all_properties = []
    for header_info in header_positions:
        xml_pos = header_info.get('xml_position')
        if xml_pos is None:
            continue
        
        properties = extract_paragraph_properties_from_xml(docx_path, xml_pos)
        level = properties.get('level')
        
        # Если уровень не определен из стиля, пытаемся определить по тексту (например, "3.1", "3.2")
        if not level:
            text = header_info.get('text', '')
            # Ищем паттерны типа "3.1", "3.2.1" и т.д.
            match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if match:
                # Определяем уровень по количеству точек
                if match.group(3):
                    level = 3
                elif match.group(2):
                    level = 2
                elif match.group(1):
                    level = 1
        
        # Если уровень все еще не определен, используем общие правила
        if not level:
            level = 'unknown'
        
        properties['xml_position'] = xml_pos
        properties['text'] = header_info.get('text', '')
        properties['detected_level'] = level
        all_properties.append(properties)
        
        # Группируем по уровням
        level_key = str(level)
        if level_key not in rules['by_level']:
            rules['by_level'][level_key] = []
        rules['by_level'][level_key].append(properties)
    
    # Вычисляем общие свойства для каждого уровня
    for level, props_list in rules['by_level'].items():
        if not props_list:
            continue
        
        # Находим наиболее частые значения
        font_names = [p.get('font_name') for p in props_list if p.get('font_name')]
        font_sizes = [p.get('font_size') for p in props_list if p.get('font_size')]
        bold_count = sum(1 for p in props_list if p.get('is_bold'))
        italic_count = sum(1 for p in props_list if p.get('is_italic'))
        
        level_rules = {
            'font_name': max(set(font_names), key=font_names.count) if font_names else None,
            'font_size': sum(font_sizes) / len(font_sizes) if font_sizes else None,
            'font_size_range': (min(font_sizes), max(font_sizes)) if font_sizes else None,
            'is_bold': bold_count > len(props_list) / 2,
            'is_italic': italic_count > len(props_list) / 2,
            'style_pattern': props_list[0].get('style', '') if props_list else None,
            'count': len(props_list)
        }
        
        rules['by_level'][level] = level_rules
    
    # Создаем общие правила для всех заголовков (если нет явных уровней)
    if all_properties and len(rules['by_level']) == 1 and 'unknown' in rules['by_level']:
        # Используем общие характеристики всех заголовков
        all_font_names = [p.get('font_name') for p in all_properties if p.get('font_name')]
        all_font_sizes = [p.get('font_size') for p in all_properties if p.get('font_size')]
        all_bold_count = sum(1 for p in all_properties if p.get('is_bold'))
        
        if all_font_names or all_font_sizes:
            rules['common_header'] = {
                'font_name': max(set(all_font_names), key=all_font_names.count) if all_font_names else None,
                'font_size': sum(all_font_sizes) / len(all_font_sizes) if all_font_sizes else None,
                'font_size_range': (min(all_font_sizes), max(all_font_sizes)) if all_font_sizes else None,
                'is_bold': all_bold_count > len(all_properties) / 2,
            }
    
    # Общие свойства всех заголовков
    if all_properties:
        all_font_names = [p.get('font_name') for p in all_properties if p.get('font_name')]
        all_font_sizes = [p.get('font_size') for p in all_properties if p.get('font_size')]
        
        rules['common_properties'] = {
            'common_font_names': list(set(all_font_names)) if all_font_names else [],
            'font_size_range': (min(all_font_sizes), max(all_font_sizes)) if all_font_sizes else None,
            'total_headers': len(all_properties)
        }
    
    return rules


def find_missing_headers_by_rules(
    docx_path: Path,
    all_xml_elements: List[Dict[str, Any]],
    header_rules: Dict[str, Any],
    found_positions: List[int]
) -> List[Dict[str, Any]]:
    """
    Находит пропущенные заголовки в XML, используя правила.
    
    Args:
        docx_path: Путь к DOCX файлу
        all_xml_elements: Все элементы из XML
        header_rules: Правила для поиска заголовков
        found_positions: Список уже найденных позиций
    
    Returns:
        Список найденных заголовков
    """
    found_headers = []
    found_positions_set = set(found_positions)
    
    rules_by_level = header_rules.get('by_level', {})
    common_header = header_rules.get('common_header', {})
    
    if not rules_by_level and not common_header:
        return found_headers
    
    # Проходим по всем параграфам
    for i, elem in enumerate(all_xml_elements):
        if elem.get('type') != 'paragraph':
            continue
        
        xml_pos = elem.get('xml_position')
        if xml_pos in found_positions_set:
            continue  # Уже найден
        
        text = elem.get('text', '').strip()
        if not text or len(text) < 3:
            continue
        
        # Пропускаем слишком длинные тексты (вероятно, не заголовки)
        if len(text) > 200:
            continue
        
        # Извлекаем свойства параграфа
        properties = extract_paragraph_properties_from_xml(docx_path, xml_pos)
        
        # Определяем уровень по тексту (если есть номер)
        detected_level = None
        match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
        if match:
            if match.group(3):
                detected_level = 3
            elif match.group(2):
                detected_level = 2
            elif match.group(1):
                detected_level = 1
        
        # Проверяем соответствие правилам для каждого уровня
        best_match = None
        best_score = 0
        
        for level, level_rules in rules_by_level.items():
            matches = 0
            total_checks = 0
            
            # Проверка шрифта
            if level_rules.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == level_rules['font_name']:
                    matches += 1
            
            # Проверка размера шрифта (с допуском ±1pt)
            if level_rules.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = level_rules['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            # Проверка жирности
            if level_rules.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == level_rules['is_bold']:
                    matches += 1
            
            # Проверка стиля
            if level_rules.get('style_pattern'):
                total_checks += 1
                if properties.get('style') == level_rules['style_pattern']:
                    matches += 1
            
            # Вычисляем score
            if total_checks > 0:
                score = matches / total_checks
                # Бонус, если уровень из текста совпадает с уровнем правил
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
        
        # Если не нашли по уровням, проверяем общие правила
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
            
            if total_checks > 0:
                score = matches / total_checks
                # Бонус, если есть номер в тексте
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
        
        # Если совпадает >= 50% проверок, считаем заголовком
        if best_match and best_match['score'] >= 0.5:
            found_headers.append({
                'xml_position': xml_pos,
                'text': text,
                'level': best_match['level'],
                'properties': properties,
                'match_score': best_match['score']
            })
            found_positions_set.add(xml_pos)
            print(f"  ✓ Найден пропущенный заголовок (уровень {best_match['level']}): '{text[:50]}...' → позиция {xml_pos} (совпадение: {best_match['matches']}/{best_match['total_checks']}, score: {best_match['score']:.2f})")
    
    return found_headers


def split_xml_by_headers(
    docx_path: Path,
    ocr_headers_with_text: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Разбивает XML на блоки между заголовками.
    
    Args:
        docx_path: Путь к DOCX файлу
        ocr_headers_with_text: Список заголовков из OCR с текстом из Qwen
    
    Returns:
        Список блоков между заголовками
    """
    # Получаем все элементы из XML
    all_xml_elements = extract_all_elements_from_docx_xml_ordered(docx_path)
    
    # Сортируем заголовки по позиции (page_num, y координата)
    sorted_headers = sorted(
        ocr_headers_with_text,
        key=lambda h: (h.get('page_num', 0), h.get('bbox', [0, 0, 0, 0])[1] if h.get('bbox') else 0)
    )
    
    # Находим позиции заголовков в XML
    header_positions = []
    for header in sorted_headers:
        header_text = header.get('text', '')
        if not header_text:
            continue
        
        # Ищем в XML (начинаем с последней найденной позиции + 1)
        start_from = header_positions[-1]['xml_position'] + 1 if header_positions else 0
        xml_pos = find_header_in_xml_by_text(header_text, all_xml_elements, start_from)
        
        if xml_pos is not None:
            header_positions.append({
                'ocr_header': header,
                'xml_position': xml_pos,
                'text': header_text
            })
            print(f"  ✓ Найден заголовок в XML: '{header_text[:50]}...' → позиция {xml_pos}")
        else:
            print(f"  ⚠ Заголовок не найден в XML: '{header_text[:50]}...'")
    
    # Шаг 4.1: Строим правила на основе найденных заголовков
    print("\n  Построение правил для поиска пропущенных заголовков...")
    header_rules = build_header_rules_from_found_headers(docx_path, header_positions)
    
    # Выводим статистику правил
    print(f"  Правила для уровней: {list(header_rules.get('by_level', {}).keys())}")
    for level, rules in header_rules.get('by_level', {}).items():
        font_size_str = f"{rules.get('font_size'):.1f}pt" if rules.get('font_size') else "None"
        print(f"    Уровень {level}: шрифт={rules.get('font_name')}, размер={font_size_str}, жирный={rules.get('is_bold')}, стиль={rules.get('style_pattern')}")
    
    # Шаг 4.2: Ищем пропущенные заголовки по правилам
    print("\n  Поиск пропущенных заголовков по правилам...")
    found_positions = [h['xml_position'] for h in header_positions]
    missing_headers = find_missing_headers_by_rules(docx_path, all_xml_elements, header_rules, found_positions)
    
    # Добавляем найденные заголовки к списку
    for missing_header in missing_headers:
        header_positions.append({
            'ocr_header': None,  # Не найден через OCR
            'xml_position': missing_header['xml_position'],
            'text': missing_header['text'],
            'level': missing_header['level'],
            'found_by_rules': True
        })
    
    # Сортируем все заголовки по позиции
    header_positions.sort(key=lambda h: h['xml_position'])
    
    # Разбиваем XML на блоки между заголовками
    blocks = []
    
    # Блок до первого заголовка
    if header_positions:
        first_header_pos = header_positions[0]['xml_position']
        first_block_elements = [e for e in all_xml_elements if e.get('xml_position', 0) < first_header_pos]
        if first_block_elements:
            blocks.append({
                'type': 'text_block',
                'header': None,
                'elements': first_block_elements,
                'start_position': 0,
                'end_position': first_header_pos
            })
    
    # Блоки между заголовками
    for i in range(len(header_positions)):
        header_info = header_positions[i]
        start_pos = header_info['xml_position']
        end_pos = header_positions[i + 1]['xml_position'] if i + 1 < len(header_positions) else len(all_xml_elements)
        
        # Элементы между заголовками
        block_elements = [
            e for e in all_xml_elements
            if start_pos <= e.get('xml_position', 0) < end_pos
        ]
        
        blocks.append({
            'type': 'section',
            'header': header_info['ocr_header'],
            'header_text': header_info['text'],
            'elements': block_elements,
            'start_position': start_pos,
            'end_position': end_pos
        })
    
    # Блок после последнего заголовка
    if header_positions:
        last_header_pos = header_positions[-1]['xml_position']
        last_block_elements = [
            e for e in all_xml_elements
            if e.get('xml_position', 0) > last_header_pos
        ]
        if last_block_elements:
            blocks.append({
                'type': 'text_block',
                'header': None,
                'elements': last_block_elements,
                'start_position': last_header_pos + 1,
                'end_position': len(all_xml_elements)
            })
    else:
        # Если нет заголовков, весь документ - один блок
        blocks.append({
            'type': 'text_block',
            'header': None,
            'elements': all_xml_elements,
            'start_position': 0,
            'end_position': len(all_xml_elements)
        })
    
    return blocks


def process_docx_qwen_ocr_pipeline(
    docx_path: Path,
    output_dir: Path,
    skip_first_table: bool = False
) -> Dict[str, Any]:
    """
    Основной пайплайн: DOTS OCR → Qwen OCR → XML блоки.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        skip_first_table: Пропустить первую таблицу (для Diplom2024)
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*80}")
    print(f"ПАЙПЛАЙН: DOTS OCR → Qwen OCR → XML блоки")
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
    
    ocr_elements = []  # Все элементы из OCR
    page_images = {}  # Изображения страниц для Qwen OCR
    
    for page_num in range(total_pages):
        print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            continue
        
        # Сохраняем изображение страницы для Qwen OCR
        page_images[page_num] = page_image
        
        try:
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image
            )
            
            if success and layout_cells:
                for element in layout_cells:
                    category = element.get("category", "")
                    element["page_num"] = page_num
                    ocr_elements.append(element)
        
        except Exception as e:
            print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    # Фильтруем только Section-header и Caption
    section_headers = [e for e in ocr_elements if e.get("category") == "Section-header"]
    captions = [e for e in ocr_elements if e.get("category") == "Caption"]
    
    print(f"  ✓ Найдено Section-header: {len(section_headers)}")
    print(f"  ✓ Найдено Caption: {len(captions)}\n")
    
    # Шаг 3: Извлечение текста через Qwen OCR
    print("Шаг 3: Извлечение текста через Qwen OCR...")
    print(f"  Обработка {len(section_headers)} заголовков и {len(captions)} подписей...")
    
    # Объединяем заголовки и подписи для обработки
    elements_to_ocr = section_headers + captions
    
    ocr_results = extract_text_from_ocr_elements_with_qwen(elements_to_ocr, page_images)
    
    # Разделяем результаты
    headers_with_text = [r for r in ocr_results if r.get("category") == "Section-header"]
    captions_with_text = [r for r in ocr_results if r.get("category") == "Caption"]
    
    print(f"\n  ✓ Извлечено текста из заголовков: {len(headers_with_text)}")
    print(f"  ✓ Извлечено текста из подписей: {len(captions_with_text)}\n")
    
    # Шаг 4: Разбиение XML на блоки между заголовками
    print("Шаг 4: Разбиение XML на блоки между заголовками...")
    blocks = split_xml_by_headers(docx_path, headers_with_text)
    print(f"  ✓ Создано блоков: {len(blocks)}\n")
    
    # Шаг 5: Обработка блоков (извлечение структурированных элементов)
    print("Шаг 5: Обработка блоков...")
    
    # Получаем таблицы и изображения из XML
    docx_tables = extract_tables_from_docx_xml(docx_path)
    docx_images = extract_images_from_docx_xml(docx_path)
    
    tables_by_position = {t.get('xml_position'): t for t in docx_tables}
    images_by_position = {img.get('xml_position'): img for img in docx_images}
    
    structured_blocks = []
    
    for block_idx, block in enumerate(blocks):
        block_type = block.get('type')
        block_elements = block.get('elements', [])
        header = block.get('header')
        
        print(f"  Блок #{block_idx + 1}: {block_type}, элементов: {len(block_elements)}")
        
        # Обрабатываем элементы блока
        block_content = []
        current_text_block = []
        current_text_size = 0
        MAX_BLOCK_SIZE = 3000
        
        for elem in block_elements:
            elem_type = elem.get('type')
            elem_pos = elem.get('xml_position')
            
            # Функция для сохранения текстового блока
            def save_text():
                nonlocal current_text_block, current_text_size
                if current_text_block:
                    block_content.append({
                        'type': 'text_block',
                        'text': '\n\n'.join(current_text_block),
                        'size': current_text_size
                    })
                    current_text_block = []
                    current_text_size = 0
            
            # Проверяем таблицы
            if elem_type == 'table' and elem_pos in tables_by_position:
                save_text()
                table_data = tables_by_position[elem_pos]
                block_content.append({
                    'type': 'table',
                    'table_data': table_data
                })
                continue
            
            # Проверяем изображения
            if elem_pos in images_by_position:
                save_text()
                image_data = images_by_position[elem_pos]
                block_content.append({
                    'type': 'image',
                    'image_data': image_data
                })
                continue
            
            # Обрабатываем параграфы
            if elem_type == 'paragraph':
                text = elem.get('text', '')
                text_size = len(text)
                
                if current_text_size + text_size <= MAX_BLOCK_SIZE:
                    current_text_block.append(text)
                    current_text_size += text_size
                else:
                    save_text()
                    current_text_block = [text]
                    current_text_size = text_size
        
        # Сохраняем последний текстовый блок
        save_text()
        
        # Формируем структурированный блок
        structured_block = {
            'block_index': block_idx + 1,
            'type': block_type,
            'header': {
                'text': block.get('header_text'),
                'page': header.get('page_num') if header else None,
                'bbox': header.get('bbox') if header else None
            } if header else None,
            'content': block_content,
            'elements_count': len(block_elements)
        }
        
        structured_blocks.append(structured_block)
    
    print(f"  ✓ Обработано блоков: {len(structured_blocks)}\n")
    
    # Шаг 6: Сохранение результатов
    print("Шаг 6: Сохранение результатов...")
    
    results = {
        'docx_file': str(docx_path),
        'ocr_headers': headers_with_text,
        'ocr_captions': captions_with_text,
        'blocks': structured_blocks,
        'statistics': {
            'total_headers': len(headers_with_text),
            'total_captions': len(captions_with_text),
            'total_blocks': len(structured_blocks),
            'total_tables': len(docx_tables),
            'total_images': len(docx_images)
        }
    }
    
    results_json_path = structure_dir / "structure.json"
    with open(results_json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"  ✓ Результаты сохранены: {results_json_path}")
    
    # Создаем текстовый отчет
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("СТРУКТУРА ДОКУМЕНТА (DOTS OCR → Qwen OCR → XML)")
    report_lines.append("=" * 80)
    report_lines.append(f"\nDOCX файл: {docx_path.name}")
    report_lines.append(f"\nOCR РЕЗУЛЬТАТЫ:")
    report_lines.append(f"  Заголовков (Section-header): {len(headers_with_text)}")
    report_lines.append(f"  Подписей (Caption): {len(captions_with_text)}")
    report_lines.append(f"\nБЛОКИ:")
    report_lines.append(f"  Всего блоков: {len(structured_blocks)}")
    for i, block in enumerate(structured_blocks, 1):
        header_text = block.get('header', {}).get('text', 'Нет заголовка') if block.get('header') else 'Нет заголовка'
        report_lines.append(f"  Блок {i}: {header_text[:60]}... ({len(block.get('content', []))} элементов)")
    
    report_path = structure_dir / "report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"  ✓ Отчет сохранен: {report_path}\n")
    
    pdf_doc.close()
    
    print(f"{'='*80}")
    print(f"ИТОГО:")
    print(f"  Заголовков из OCR: {len(headers_with_text)}")
    print(f"  Подписей из OCR: {len(captions_with_text)}")
    print(f"  Блоков: {len(structured_blocks)}")
    print(f"{'='*80}\n")
    
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python docx_qwen_ocr_pipeline.py <docx_path> [output_dir] [--skip-first-table]")
        print("\nПримеры:")
        print("  python docx_qwen_ocr_pipeline.py test_folder/Диплом.docx")
        print("  python docx_qwen_ocr_pipeline.py test_folder/Diplom2024.docx --skip-first-table")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    # Определяем выходную директорию
    if len(sys.argv) >= 3 and not sys.argv[2].startswith('--'):
        output_dir = Path(sys.argv[2])
    else:
        output_dir = Path(__file__).parent / "results" / "qwen_ocr_pipeline" / docx_path.stem
    
    # Проверяем флаг --skip-first-table
    skip_first_table = '--skip-first-table' in sys.argv or 'Diplom2024' in docx_path.name
    
    result = process_docx_qwen_ocr_pipeline(docx_path, output_dir, skip_first_table=skip_first_table)
    
    if "error" in result:
        print(f"\n✗ Ошибка: {result['error']}")
        sys.exit(1)
    
    print(f"\n✓ Пайплайн завершен успешно!")
