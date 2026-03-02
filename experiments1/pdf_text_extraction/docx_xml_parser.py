"""
Парсер DOCX через прямое чтение XML (без python-docx).

Извлекает изображения и таблицы напрямую из XML с сохранением позиций.
"""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO
import hashlib
from PIL import Image

# Namespaces для DOCX XML
NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'rels': 'http://schemas.openxmlformats.org/package/2006/relationships'
}


def load_image_relationships(docx_path: Path) -> Dict[str, str]:
    """
    Загружает связи изображений из word/_rels/document.xml.rels.
    
    Returns:
        Словарь {rId: image_path}, например {'rId5': 'media/image1.png'}
    """
    rels = {}
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            try:
                rels_xml = zip_file.read('word/_rels/document.xml.rels')
                root = ET.fromstring(rels_xml)
                
                for rel in root.findall('.//{*}Relationship'):
                    rel_type = rel.get('Type', '')
                    if 'image' in rel_type.lower():
                        rel_id = rel.get('Id')
                        target = rel.get('Target')
                        if rel_id and target:
                            rels[rel_id] = target
            except KeyError:
                # Файл связей может отсутствовать
                pass
    except Exception as e:
        print(f"Предупреждение: не удалось загрузить связи изображений: {e}")
    
    return rels


def extract_text_from_element(elem: ET.Element, namespaces: Dict[str, str]) -> str:
    """
    Извлекает весь текст из элемента (параграфа, ячейки и т.д.).
    """
    texts = []
    for text_elem in elem.findall('.//w:t', namespaces):
        if text_elem.text:
            texts.append(text_elem.text)
    return ''.join(texts).strip()


def extract_images_from_docx_xml(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Извлекает все изображения из DOCX через прямое чтение XML.
    
    Args:
        docx_path: Путь к DOCX файлу
    
    Returns:
        Список изображений с данными, включая позицию в XML
    """
    images_data = []
    
    # 1. Загружаем связи изображений
    rels = load_image_relationships(docx_path)
    
    if not rels:
        print("  Предупреждение: не найдено связей изображений")
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            # 2. Читаем document.xml
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # 3. Находим body
            body = root.find('w:body', NAMESPACES)
            if body is None:
                return []
            
            # 4. Собираем все элементы в порядке появления
            all_elements = list(body)
            
            # 5. Находим все параграфы
            paragraphs = body.findall('.//w:p', NAMESPACES)
            
            image_counter = 0
            
            for para_idx, para in enumerate(paragraphs):
                # 6. Ищем изображения в параграфе
                # Вариант 1: Через a:blip (современный формат)
                blips = para.findall('.//a:blip', NAMESPACES)
                
                for blip in blips:
                    # Получаем r:embed
                    r_embed = blip.get(f'{{{NAMESPACES["r"]}}}embed')
                    if not r_embed:
                        continue
                    
                    # Получаем путь к изображению из связей
                    image_path = rels.get(r_embed)
                    if not image_path:
                        print(f"  Предупреждение: не найдена связь для rId {r_embed}")
                        continue
                    
                    # Читаем изображение из архива
                    try:
                        # Путь может быть "media/image1.png" или "word/media/image1.png"
                        if not image_path.startswith('word/'):
                            zip_path = f'word/{image_path}'
                        else:
                            zip_path = image_path
                        
                        image_bytes = zip_file.read(zip_path)
                        
                        if not image_bytes or len(image_bytes) == 0:
                            print(f"  Предупреждение: пустое изображение {image_path}")
                            continue
                        
                        # Получаем размеры из PIL
                        try:
                            image = Image.open(BytesIO(image_bytes))
                            if image.mode != 'RGB':
                                image = image.convert('RGB')
                            width, height = image.size
                        except Exception as e:
                            print(f"  Предупреждение: не удалось открыть изображение {image_path}: {e}")
                            width, height = None, None
                        
                        # Пытаемся получить размеры из XML (если есть)
                        extents = para.findall('.//a:ext', NAMESPACES)
                        xml_width = None
                        xml_height = None
                        if extents:
                            cx = extents[0].get('cx')
                            cy = extents[0].get('cy')
                            if cx and cy:
                                # Конвертируем из EMU в пиксели (9525 EMU ≈ 1 пиксель при 96 DPI)
                                xml_width = int(cx) // 9525
                                xml_height = int(cy) // 9525
                        
                        # Используем размеры из XML, если они есть, иначе из PIL
                        final_width = xml_width if xml_width else width
                        final_height = xml_height if xml_height else height
                        
                        # Создаем хеш для сравнения
                        image_hash = hashlib.md5(image_bytes).hexdigest()
                        
                        # Находим позицию параграфа в all_elements
                        # ВАЖНО: Используем тот же метод, что и в extract_all_elements_from_docx_xml_ordered
                        xml_position = None
                        for idx, elem in enumerate(all_elements):
                            if elem == para:
                                xml_position = idx
                                break
                        
                        # Если не нашли через прямое сравнение, используем альтернативный метод
                        if xml_position is None:
                            # Ищем по тексту параграфа (менее надежно, но может помочь)
                            para_text = extract_text_from_element(para, NAMESPACES)
                            for idx, elem in enumerate(all_elements):
                                if elem.tag.endswith('}p'):
                                    elem_text = extract_text_from_element(elem, NAMESPACES)
                                    if elem_text == para_text and para_text.strip():
                                        xml_position = idx
                                        break
                        
                        # Извлекаем текст параграфа (может быть подписью)
                        para_text = extract_text_from_element(para, NAMESPACES)
                        
                        images_data.append({
                            'index': image_counter,
                            'order_in_document': image_counter,
                            'paragraph_index': para_idx,
                            'xml_position': xml_position,
                            'r_embed': r_embed,
                            'image_path': image_path,
                            'image_bytes': image_bytes,
                            'image_hash': image_hash,
                            'width': final_width,
                            'height': final_height,
                            'format': 'PNG',  # Будем конвертировать в PNG
                            'paragraph_text': para_text,
                            'matched': False
                        })
                        
                        image_counter += 1
                    
                    except KeyError as e:
                        print(f"  Предупреждение: изображение не найдено в архиве: {image_path} ({e})")
                        continue
                    except Exception as e:
                        print(f"  Ошибка при чтении изображения {image_path}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
            
            print(f"  ✓ Извлечено изображений: {len(images_data)}")
    
    except Exception as e:
        print(f"  ✗ Ошибка при извлечении изображений: {e}")
        import traceback
        traceback.print_exc()
    
    return images_data


def find_cell_in_column(row_elem: ET.Element, target_col: int, namespaces: Dict[str, str]) -> Optional[ET.Element]:
    """
    Находит ячейку в указанной колонке с учетом colspan предыдущих ячеек.
    """
    cells = row_elem.findall('.//w:tc', namespaces)
    current_col = 0
    
    for cell_elem in cells:
        cell_props = cell_elem.find('w:tcPr', namespaces)
        colspan = 1
        
        if cell_props is not None:
            grid_span = cell_props.find('w:gridSpan', namespaces)
            if grid_span is not None:
                val = grid_span.get(f'{{{NAMESPACES["w"]}}}val') or grid_span.get('val')
                if val:
                    colspan = int(val)
        
        if current_col <= target_col < current_col + colspan:
            return cell_elem
        
        current_col += colspan
    
    return None


def has_vmerge_continue(cell_elem: ET.Element, namespaces: Dict[str, str]) -> bool:
    """
    Проверяет, является ли ячейка продолжением объединения (vMerge без val="restart").
    """
    cell_props = cell_elem.find('w:tcPr', namespaces)
    if cell_props is None:
        return False
    
    v_merge = cell_props.find('w:vMerge', namespaces)
    if v_merge is None:
        return False
    
    val = v_merge.get(f'{{{NAMESPACES["w"]}}}val') or v_merge.get('val')
    return val != 'restart'  # Если нет val или val != "restart", это продолжение


def calculate_rowspan(
    table_elem: ET.Element,
    row_idx: int,
    col_idx: int,
    namespaces: Dict[str, str]
) -> int:
    """
    Вычисляет rowspan для ячейки с vMerge val="restart".
    """
    rows = table_elem.findall('.//w:tr', namespaces)
    rowspan = 1
    
    # Ищем следующие строки
    for next_row_idx in range(row_idx + 1, len(rows)):
        next_row = rows[next_row_idx]
        next_cell = find_cell_in_column(next_row, col_idx, namespaces)
        
        if next_cell and has_vmerge_continue(next_cell, namespaces):
            rowspan += 1
        else:
            break
    
    return rowspan


def extract_tables_from_docx_xml(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Извлекает все таблицы из DOCX через прямое чтение XML.
    Правильно вычисляет rowspan и colspan.
    
    Args:
        docx_path: Путь к DOCX файлу
    
    Returns:
        Список таблиц с полной структурой
    """
    tables_data = []
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            # 1. Читаем document.xml
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # 2. Находим body
            body = root.find('w:body', NAMESPACES)
            if body is None:
                return []
            
            # 3. ⭐ ВАЖНО: Собираем все элементы в порядке появления
            all_elements = list(body)
            
            # 4. Находим все таблицы
            tables = body.findall('.//w:tbl', NAMESPACES)
            
            print(f"  Найдено таблиц в XML: {len(tables)}")
            
            for table_idx, table_elem in enumerate(tables):
                # 5. Находим позицию таблицы в all_elements
                table_xml_position = None
                for idx, elem in enumerate(all_elements):
                    if elem == table_elem:
                        table_xml_position = idx
                        break
                
                table_info = {
                    'index': table_idx,
                    'xml_position': table_xml_position,
                    'rows': [],
                    'rows_count': 0,
                    'cols_count': 0,
                    'style': None,
                    'merged_cells': [],
                    'estimated_page': 1,
                }
                
                # 6. Получаем стиль таблицы
                tbl_pr = table_elem.find('w:tblPr', NAMESPACES)
                if tbl_pr is not None:
                    tbl_style = tbl_pr.find('w:tblStyle', NAMESPACES)
                    if tbl_style is not None:
                        style_val = tbl_style.get(f'{{{NAMESPACES["w"]}}}val') or tbl_style.get('val')
                        if style_val:
                            table_info['style'] = style_val
                
                # 7. Обрабатываем строки
                rows = table_elem.findall('.//w:tr', NAMESPACES)
                table_info['rows_count'] = len(rows)
                
                max_cols = 0
                
                for row_idx, row_elem in enumerate(rows):
                    row_data = {
                        'row_index': row_idx,
                        'cells': [],
                        'cells_count': 0,
                    }
                    
                    # 8. Обрабатываем ячейки
                    cells = row_elem.findall('.//w:tc', NAMESPACES)
                    col_idx = 0
                    
                    for cell_elem in cells:
                        # 8.1 Извлекаем текст из ячейки
                        cell_text = extract_text_from_element(cell_elem, NAMESPACES)
                        
                        # 8.2 Проверяем свойства ячейки
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
                                    rowspan = 0  # Не учитываем в структуре
                                    is_merged = True
                        
                        # 8.3 Создаем информацию о ячейке
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
                        
                        # 8.4 Учитываем colspan при переходе к следующей колонке
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
                        
                        # Если rowspan = 0, ячейка не учитывается (продолжение объединения)
                    
                    row_data['cells_count'] = len([c for c in row_data['cells'] if c['rowspan'] > 0])
                    table_info['rows'].append(row_data)
                
                table_info['cols_count'] = max_cols
                
                # 9. Определяем приблизительный номер страницы
                if table_xml_position is not None:
                    # Эвристика: ~50 элементов на страницу
                    table_info['estimated_page'] = max(1, (table_xml_position // 50) + 1)
                
                tables_data.append(table_info)
            
            print(f"  ✓ Извлечено таблиц: {len(tables_data)}")
    
    except Exception as e:
        print(f"  ✗ Ошибка при извлечении таблиц: {e}")
        import traceback
        traceback.print_exc()
    
    return tables_data


def extract_tables_with_context_xml(
    docx_path: Path,
    context_paragraphs: int = 3
) -> List[Dict[str, Any]]:
    """
    Извлекает таблицы из DOCX XML с текстовым контекстом до/после.
    
    Args:
        docx_path: Путь к DOCX файлу
        context_paragraphs: Количество параграфов до/после для контекста
    
    Returns:
        Список таблиц с контекстом
    """
    # 1. Извлекаем таблицы
    tables = extract_tables_from_docx_xml(docx_path)
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            # 2. Читаем document.xml
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # 3. Находим body
            body = root.find('w:body', NAMESPACES)
            if body is None:
                return tables
            
            # 4. Собираем все элементы в порядке появления
            all_elements = list(body)
            
            # 5. Для каждой таблицы извлекаем контекст
            for table_idx, table in enumerate(tables):
                xml_position = table.get('xml_position')
                if xml_position is None:
                    table['text_before'] = ''
                    table['text_after'] = ''
                    table['paragraph_index'] = None
                    continue
                
                # 6. Текст до таблицы - ищем параграфы перед таблицей
                text_before = []
                for i in range(xml_position - 1, max(-1, xml_position - context_paragraphs - 1), -1):
                    elem = all_elements[i]
                    if elem.tag.endswith('}p'):  # Параграф
                        text = extract_text_from_element(elem, NAMESPACES)
                        if text.strip():
                            text_before.insert(0, text.strip())  # Добавляем в начало
                            if len(text_before) >= context_paragraphs:
                                break
                    elif elem.tag.endswith('}tbl'):  # Другая таблица - останавливаемся
                        break
                
                # 7. Текст после таблицы - ищем параграфы после таблицы
                text_after = []
                for i in range(xml_position + 1, min(len(all_elements), xml_position + context_paragraphs + 1)):
                    elem = all_elements[i]
                    if elem.tag.endswith('}p'):  # Параграф
                        text = extract_text_from_element(elem, NAMESPACES)
                        if text.strip():
                            text_after.append(text.strip())
                            if len(text_after) >= context_paragraphs:
                                break
                    elif elem.tag.endswith('}tbl'):  # Следующая таблица - останавливаемся
                        break
                
                # 8. Добавляем контекст к таблице
                table['text_before'] = ' | '.join(text_before[-context_paragraphs:])
                table['text_after'] = ' | '.join(text_after[:context_paragraphs])
                table['paragraph_index'] = xml_position
                table['table_number'] = table_idx + 1
    
    except Exception as e:
        print(f"  Предупреждение: не удалось извлечь контекст для таблиц: {e}")
        # Возвращаем таблицы без контекста
        for i, table in enumerate(tables):
            table['text_before'] = ''
            table['text_after'] = ''
            table['paragraph_index'] = None
            table['table_number'] = i + 1
    
    return tables


if __name__ == "__main__":
    # Тестирование
    import sys
    
    if len(sys.argv) < 2:
        print("Использование: python docx_xml_parser.py <docx_path>")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    
    print("=" * 80)
    print("ТЕСТИРОВАНИЕ ПАРСЕРА DOCX XML")
    print("=" * 80)
    print(f"Файл: {docx_path}\n")
    
    # Тест извлечения изображений
    print("1. Извлечение изображений:")
    print("-" * 80)
    images = extract_images_from_docx_xml(docx_path)
    print(f"Всего изображений: {len(images)}")
    if images:
        print(f"Первое изображение: {images[0]}")
    
def extract_all_elements_from_docx_xml_ordered(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Извлекает ВСЕ элементы из DOCX XML в порядке появления с полной информацией.
    Извлекает максимально полный текст без обрезания.
    
    Returns:
        Список элементов с типами: 'paragraph', 'table', 'image'
    """
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
                    texts = []
                    for text_elem in elem.findall('.//w:t', NAMESPACES):
                        if text_elem.text:
                            texts.append(text_elem.text)
                        # Сохраняем пробелы между элементами
                        if text_elem.tail:
                            texts.append(text_elem.tail)
                    
                    # Объединяем весь текст
                    full_text = ''.join(texts)
                    
                    # Проверяем, есть ли в параграфе изображение
                    has_image = elem.find('.//a:blip', NAMESPACES) is not None
                    
                    # Сохраняем параграф, если есть текст ИЛИ изображение
                    # ВАЖНО: Сохраняем все параграфы с изображениями, даже если в них нет текста
                    if full_text.strip() or has_image:
                        elements.append({
                            'type': 'paragraph',
                            'xml_position': elem_idx,
                            'text': full_text,  # Полный текст без обрезания
                            'element': elem,
                            'has_image': has_image  # Флаг наличия изображения
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


    print("\n" + "=" * 80)
    
    # Тест извлечения таблиц
    print("2. Извлечение таблиц:")
    print("-" * 80)
    tables = extract_tables_from_docx_xml(docx_path)
    print(f"Всего таблиц: {len(tables)}")
    if tables:
        first_table = tables[0]
        print(f"Первая таблица:")
        print(f"  Строк: {first_table['rows_count']}")
        print(f"  Колонок: {first_table['cols_count']}")
        print(f"  Объединенных ячеек: {len(first_table['merged_cells'])}")
        if first_table['rows']:
            first_row = first_table['rows'][0]
            print(f"  Ячеек в первой строке: {len(first_row['cells'])}")
    
    print("\n" + "=" * 80)
    
    # Тест извлечения таблиц с контекстом
    print("3. Извлечение таблиц с контекстом:")
    print("-" * 80)
    tables_with_context = extract_tables_with_context_xml(docx_path, context_paragraphs=3)
    if tables_with_context:
        first_table = tables_with_context[0]
        print(f"Первая таблица:")
        print(f"  Текст до: {first_table.get('text_before', '')[:100]}...")
        print(f"  Текст после: {first_table.get('text_after', '')[:100]}...")
    
    print("\n" + "=" * 80)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 80)
