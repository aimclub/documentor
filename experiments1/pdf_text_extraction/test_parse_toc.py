"""
Тестовый скрипт для парсинга содержания (Table of Contents) из DOCX XML.

Проверяет три способа представления содержания:
1. Специальные поля TOC (w:fldChar, w:instrText)
2. Параграфы со стилями TOC1, TOC2, TOC3
3. Обычные параграфы между "СОДЕРЖАНИЕ" и следующим разделом
"""

import sys
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

# Namespaces для DOCX XML
NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_xml_parser import (
    extract_all_elements_from_docx_xml_ordered,
    extract_text_from_element,
    NAMESPACES as DOCX_NAMESPACES
)


def get_paragraph_text(p: ET.Element) -> str:
    """Извлекает весь текст из параграфа, включая табуляции и пробелы."""
    texts = []
    # Проходим по всем элементам в параграфе, сохраняя структуру
    for elem in p.iter():
        if elem.tag == f'{{{NAMESPACES["w"]}}}t':
            # Обычный текст
            if elem.text:
                texts.append(elem.text)
        elif elem.tag == f'{{{NAMESPACES["w"]}}}tab':
            # Табуляция - заменяем на табуляцию
            texts.append('\t')
        elif elem.tag == f'{{{NAMESPACES["w"]}}}br':
            # Разрыв строки - заменяем на пробел
            texts.append(' ')
        elif elem.tag == f'{{{NAMESPACES["w"]}}}noBreakHyphen':
            # Неразрывный дефис
            texts.append('-')
        elif elem.tag == f'{{{NAMESPACES["w"]}}}softHyphen':
            # Мягкий перенос
            texts.append('-')
    return ''.join(texts).strip()


def get_paragraph_style(p: ET.Element) -> Optional[str]:
    """Получает стиль параграфа."""
    p_pr = p.find('w:pPr', NAMESPACES)
    if p_pr is not None:
        p_style = p_pr.find('w:pStyle', NAMESPACES)
        if p_style is not None:
            return p_style.get(f'{{{NAMESPACES["w"]}}}val') or p_style.get('val')
    return None


def find_bookmark_text(root: ET.Element, bookmark_name: str) -> Optional[Dict[str, Any]]:
    """
    Находит закладку по имени и извлекает текст заголовка рядом с ней.
    
    Args:
        root: Корневой элемент XML
        bookmark_name: Имя закладки (например, "_Toc211012744")
    
    Returns:
        Словарь с информацией о заголовке или None
    """
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return None
    
    # Ищем параграф, который содержит закладку с нужным именем
    for para in body.findall('w:p', NAMESPACES):
        # Проверяем, содержит ли параграф эту закладку
        bookmark_starts = para.findall('.//w:bookmarkStart', NAMESPACES)
        for bs in bookmark_starts:
            bs_name = bs.get(f'{{{NAMESPACES["w"]}}}name') or bs.get('name')
            if bs_name == bookmark_name:
                # Нашли параграф с закладкой! Извлекаем текст заголовка
                title = get_paragraph_text(para)
                
                if not title or not title.strip():
                    continue
                
                # Определяем уровень заголовка по стилю
                level = 1
                style = get_paragraph_style(para)
                if style:
                    if style.isdigit():
                        level = int(style)
                    elif style.upper().startswith('HEADING'):
                        try:
                            level = int(style.replace('Heading', '').replace('heading', '').strip())
                        except:
                            pass
                
                # Также проверяем нумерацию в тексте
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


def extract_toc_text_from_field_result(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Извлекает текст из результата TOC поля (статическое содержимое между separate и end).
    Работает даже если поле заблокировано - извлекает текст, который виден в документе.
    
    Структура TOC поля:
    - w:fldChar с w:fldCharType="begin"
    - w:instrText с текстом "TOC ..."
    - w:fldChar с w:fldCharType="separate"
    - содержимое TOC (параграфы с текстом, гиперссылки, номера страниц)
    - w:fldChar с w:fldCharType="end"
    """
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    all_paras = list(body.findall('w:p', NAMESPACES))
    toc_start_idx = -1
    toc_end_idx = -1
    
    # Ищем начало и конец TOC поля
    # Сначала ищем параграф с TOC инструкцией и fldChar separate
    for i, para in enumerate(all_paras):
        # Проверяем, есть ли TOC инструкция в этом параграфе
        instr_texts = para.findall('.//w:instrText', NAMESPACES)
        has_toc_instr = False
        for instr in instr_texts:
            if instr.text and 'TOC' in instr.text.upper():
                has_toc_instr = True
                break
        
        if has_toc_instr:
            # Ищем fldChar в этом параграфе
            fld_chars = para.findall('.//w:fldChar', NAMESPACES)
            for fld_char in fld_chars:
                fld_type = fld_char.get(f'{{{NAMESPACES["w"]}}}fldCharType') or fld_char.get('fldCharType')
                if fld_type == 'separate':
                    # Начало содержимого TOC
                    toc_start_idx = i
                elif fld_type == 'end' and toc_start_idx >= 0:
                    # Конец TOC поля
                    toc_end_idx = i
                    break
        
        if toc_end_idx >= 0:
            break
    
    # Если не нашли через инструкцию, ищем по структуре поля (fldChar может быть в разных параграфах)
    if toc_start_idx < 0:
        in_toc_field = False
        for i, para in enumerate(all_paras):
            # Проверяем наличие TOC инструкции
            instr_texts = para.findall('.//w:instrText', NAMESPACES)
            has_toc = False
            for instr in instr_texts:
                if instr.text and 'TOC' in instr.text.upper():
                    has_toc = True
                    break
            
            if has_toc:
                fld_chars = para.findall('.//w:fldChar', NAMESPACES)
                for fld_char in fld_chars:
                    fld_type = fld_char.get(f'{{{NAMESPACES["w"]}}}fldCharType') or fld_char.get('fldCharType')
                    if fld_type == 'separate':
                        toc_start_idx = i
                        in_toc_field = True
                    elif fld_type == 'end' and in_toc_field:
                        toc_end_idx = i
                        break
            
            if toc_end_idx >= 0:
                break
        
        # Если всё ещё не нашли, ищем fldChar separate в следующем параграфе после TOC инструкции
        if toc_start_idx < 0:
            for i, para in enumerate(all_paras):
                instr_texts = para.findall('.//w:instrText', NAMESPACES)
                for instr in instr_texts:
                    if instr.text and 'TOC' in instr.text.upper():
                        # Ищем fldChar separate в следующих параграфах
                        for j in range(i + 1, min(i + 10, len(all_paras))):
                            next_para = all_paras[j]
                            fld_chars = next_para.findall('.//w:fldChar', NAMESPACES)
                            for fld_char in fld_chars:
                                fld_type = fld_char.get(f'{{{NAMESPACES["w"]}}}fldCharType') or fld_char.get('fldCharType')
                                if fld_type == 'separate':
                                    toc_start_idx = j
                                    break
                                elif fld_type == 'end' and toc_start_idx >= 0:
                                    toc_end_idx = j
                                    break
                            if toc_start_idx >= 0:
                                break
                        break
                if toc_start_idx >= 0:
                    break
    
    # Если нашли TOC поле, извлекаем текст из параграфов между separate и end
    if toc_start_idx >= 0 and toc_end_idx >= 0:
        for i in range(toc_start_idx + 1, toc_end_idx):
            para = all_paras[i]
            
            # Пропускаем параграфы с fldChar (границы поля)
            fld_chars_in_para = para.findall('.//w:fldChar', NAMESPACES)
            if fld_chars_in_para:
                continue
            
            # Извлекаем текст из параграфа (включая гиперссылки)
            para_text = get_paragraph_text(para)
            
            # Также проверяем, есть ли гиперссылки в параграфе
            hyperlinks = para.findall('.//w:hyperlink', NAMESPACES)
            if hyperlinks:
                # Если есть гиперссылки, извлекаем текст из них
                hlink_texts = []
                for hlink in hyperlinks:
                    hlink_text = get_paragraph_text(hlink)
                    if hlink_text and hlink_text.strip():
                        hlink_texts.append(hlink_text.strip())
                
                # Используем текст из гиперссылок, если он есть
                if hlink_texts:
                    para_text = ' '.join(hlink_texts)
            
            if not para_text or not para_text.strip():
                continue
            
            # Пропускаем заголовок "Содержание"
            text_lower = para_text.lower().strip()
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                continue
            
            # Извлекаем номер страницы (если есть в конце)
            page_num = None
            title = para_text
            
            # Ищем номер страницы в конце (может быть с разделителями)
            page_match = re.search(r'[.\s\-]+?(\d+)\s*$', para_text)
            if not page_match:
                # Пробуем без разделителей
                page_match = re.search(r'(\d+)\s*$', para_text)
            
            if page_match:
                page_num = int(page_match.group(1))
                # Убираем номер страницы и разделители
                title = re.sub(r'[.\s\-]+?\d+\s*$', '', para_text).strip()
            
            # Определяем уровень по нумерации
            level = 1
            level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
            if level_match:
                if level_match.group(3):
                    level = 3
                elif level_match.group(2):
                    level = 2
                else:
                    level = 1
                # Убираем нумерацию из заголовка
                title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\s+', '', title).strip()
            
            # Фильтруем слишком короткие заголовки
            if len(title) < 3:
                continue
            
            # Проверяем, что заголовок содержит хотя бы одну букву
            if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                continue
            
            # Пропускаем технические термины
            is_camel_case = bool(re.match(r'^[a-z]+[A-Z]', title))
            is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                    not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
            
            if (title.lower() in ['int', 'varchar', 'pk', 'fk'] or 
                'http' in title.lower() or
                is_camel_case or
                is_technical_term):
                continue
            
            # Дополнительная проверка на технические термины
            if (not re.search(r'[а-яё]', title, re.IGNORECASE) and 
                ' ' not in title and 
                not re.match(r'^\d+', title) and
                len(title) < 30):
                continue
            
            toc_entries.append({
                'title': title.strip(),
                'page': page_num,
                'level': level,
                'raw_text': para_text
            })
    
    # Если не нашли через fldChar, пробуем найти TOC по заголовку "Содержание" и следующим параграфам
    # Это для статического текста оглавления
    if not toc_entries:
        toc_header_found = False
        for i, para in enumerate(all_paras):
            para_text = get_paragraph_text(para)
            text_lower = para_text.lower().strip()
            
            # Ищем заголовок "Содержание" (может быть в обычном тексте или в гиперссылке)
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                toc_header_found = True
                continue
            
            # Также проверяем гиперссылки в параграфе
            hlink_in_para = para.find('.//w:hyperlink', NAMESPACES)
            if hlink_in_para is not None:
                hlink_text = get_paragraph_text(hlink_in_para)
                hlink_text_lower = hlink_text.lower().strip()
                if hlink_text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                    toc_header_found = True
                    continue
            
            # После заголовка собираем следующие параграфы до следующего крупного заголовка
            if toc_header_found:
                # Проверяем, не является ли это следующим крупным заголовком
                if (re.match(r'^(введение|introduction|1\.|1\s|глава|часть)', text_lower, re.IGNORECASE) and
                    len(toc_entries) > 0):
                    break
                
                # Пропускаем пустые параграфы
                if not para_text or not para_text.strip():
                    continue
                
                # Извлекаем текст из параграфа (может быть в гиперссылке или обычном тексте)
                text_to_parse = para_text
                
                # Если есть гиперссылки, используем их текст
                if hlink_in_para is not None:
                    hlink_text = get_paragraph_text(hlink_in_para)
                    if hlink_text and hlink_text.strip():
                        text_to_parse = hlink_text
                
                # Извлекаем номер страницы (может быть в конце строки или в отдельном элементе)
                page_num = None
                title = text_to_parse
                
                # Ищем номер страницы в конце (может быть с разделителями: "....5" или просто "5")
                page_match = re.search(r'[.\s\-]+?(\d+)\s*$', text_to_parse)
                if not page_match:
                    page_match = re.search(r'(\d+)\s*$', text_to_parse)
                
                if page_match:
                    page_num = int(page_match.group(1))
                    # Убираем номер страницы и разделители
                    title = re.sub(r'[.\s\-]+?\d+\s*$', '', text_to_parse).strip()
                
                # Определяем уровень по нумерации
                level = 1
                level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                if level_match:
                    if level_match.group(3):
                        level = 3
                    elif level_match.group(2):
                        level = 2
                    else:
                        level = 1
                    # Убираем нумерацию из заголовка
                    title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\s+', '', title).strip()
                
                # Фильтруем слишком короткие заголовки
                if len(title) < 3:
                    continue
                
                # Проверяем, что заголовок содержит хотя бы одну букву
                if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                    continue
                
                # Проверяем, есть ли разделители или нумерация (признаки TOC записи)
                has_separators = bool(re.search(r'[.\-]{3,}', text_to_parse))
                has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', text_to_parse))
                
                # Если нет признаков TOC, но есть номер страницы - всё равно добавляем
                if not has_separators and not has_numbering:
                    if page_num is None:
                        continue
                
                # Пропускаем технические термины
                is_camel_case = bool(re.match(r'^[a-z]+[A-Z]', title))
                is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                        not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                
                if (title.lower() in ['int', 'varchar', 'pk', 'fk'] or 
                    'http' in title.lower() or
                    is_camel_case or
                    is_technical_term):
                    continue
                
                toc_entries.append({
                    'title': title.strip(),
                    'page': page_num,
                    'level': level,
                    'raw_text': text_to_parse
                })
    
    return toc_entries


def parse_toc_from_field(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Парсит содержание из специальных полей TOC (w:fldChar, w:instrText).
    Использует PAGEREF ссылки для поиска закладок и извлечения текста заголовков.
    
    TOC поле имеет структуру:
    - w:fldChar с w:fldCharType="begin"
    - w:instrText с текстом "TOC ..."
    - w:fldChar с w:fldCharType="separate"
    - содержимое TOC (параграфы с текстом и PAGEREF)
    - w:fldChar с w:fldCharType="end"
    """
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    # Ищем все параграфы
    all_paras = list(body.findall('w:p', NAMESPACES))
    
    # Сначала собираем все PAGEREF ссылки из всех w:instrText элементов
    pageref_bookmarks = []  # Список (bookmark_name, para_idx, para_text, page_num)
    
    # Ищем все w:instrText элементы во всём документе, которые содержат PAGEREF
    all_instr_texts = root.findall('.//w:instrText', NAMESPACES)
    
    for instr in all_instr_texts:
        if instr.text and 'PAGEREF' in instr.text.upper():
                # Извлекаем имя закладки из PAGEREF
                # Формат: "PAGEREF _Toc211012744 \h" или " PAGEREF _Toc211012744 \h"
                bookmark_match = re.search(r'PAGEREF\s+(_Toc\d+)', instr.text, re.IGNORECASE)
                if bookmark_match:
                    bookmark_name = bookmark_match.group(1)
                    
                    # Ищем родительский параграф для получения текста и номера страницы
                    parent_para = None
                    for para in all_paras:
                        if instr in para.findall('.//w:instrText', NAMESPACES):
                            parent_para = para
                            break
                    
                    para_text = ""
                    page_num = None
                    para_idx = -1
                    
                    if parent_para is not None:
                        para_text = get_paragraph_text(parent_para)
                        para_idx = all_paras.index(parent_para)
                        # Ищем число в конце текста параграфа
                        page_match = re.search(r'(\d+)\s*$', para_text)
                        if page_match:
                            page_num = int(page_match.group(1))
                    
                    pageref_bookmarks.append({
                        'bookmark_name': bookmark_name,
                        'para_idx': para_idx,
                        'para_text': para_text,
                        'page_num': page_num
                    })
    
    # Теперь для каждой PAGEREF ссылки находим соответствующую закладку и заголовок
    for pageref_info in pageref_bookmarks:
        bookmark_name = pageref_info['bookmark_name']
        page_num = pageref_info['page_num']
        
        # Ищем закладку и заголовок
        bookmark_data = find_bookmark_text(root, bookmark_name)
        
        if bookmark_data:
            title = bookmark_data['title']
            level = bookmark_data['level']
            
            # Если номер страницы не был найден в TOC параграфе, пытаемся найти его в тексте
            if page_num is None:
                page_match = re.search(r'(\d+)\s*$', pageref_info['para_text'])
                if page_match:
                    page_num = int(page_match.group(1))
            
            toc_entries.append({
                'title': title,
                'page': page_num,
                'level': level,
                'bookmark_name': bookmark_name,
                'style': bookmark_data.get('style'),
                'raw_text': pageref_info['para_text']
            })
        else:
            # Если закладка не найдена, используем текст из TOC параграфа
            para_text = pageref_info['para_text']
            if para_text and para_text.strip():
                # Убираем номер страницы и разделители
                title = re.sub(r'[.\s\-]+?\d+\s*$', '', para_text).strip()
                if title:
                    toc_entries.append({
                        'title': title,
                        'page': page_num,
                        'level': 1,  # По умолчанию
                        'bookmark_name': bookmark_name,
                        'raw_text': para_text
                    })
    
    return toc_entries


def parse_toc_from_styles(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Парсит содержание из параграфов со стилями TOC1, TOC2, TOC3 и т.д.
    """
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    in_toc_section = False
    toc_start_found = False
    
    for para in body.findall('w:p', NAMESPACES):
        text = get_paragraph_text(para)
        style = get_paragraph_style(para)
        
        # Проверяем, начинается ли содержание
        if not toc_start_found:
            text_lower = text.lower().strip()
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                toc_start_found = True
                in_toc_section = True
                pass  # Убираем debug вывод
                continue
        
        # Если мы в секции содержания
        if in_toc_section:
            # Проверяем, является ли это стилем TOC
            if style and style.upper().startswith('TOC'):
                level = 1
                if len(style) > 3:
                    try:
                        level = int(style[3:])
                    except:
                        pass
                
                # Пытаемся извлечь заголовок и номер страницы
                # Формат обычно: "Заголовок ................... 5"
                page_num = None
                title = text
                
                # Ищем номер страницы в конце (последнее число)
                page_match = re.search(r'(\d+)\s*$', text)
                if page_match:
                    page_num = int(page_match.group(1))
                    # Убираем номер страницы и точки/тире
                    title = re.sub(r'[.\s\-]+?\d+\s*$', '', text).strip()
                    
                    # Проверяем, что заголовок не слишком короткий
                    if len(title) < 2:
                        continue
                
                # Пропускаем пустые записи
                if not title or not title.strip():
                    continue
                
                toc_entries.append({
                    'title': title.strip(),
                    'page': page_num,
                    'level': level,
                    'style': style,
                    'raw_text': text
                })
                pass  # Убираем debug вывод
            
            # Проверяем, закончилось ли содержание (найден следующий крупный заголовок)
            elif text and len(text) > 0:
                # Если это не пустой параграф и не TOC стиль, возможно это конец содержания
                # Но нужно проверить, не является ли это обычным текстом
                text_lower = text.lower().strip()
                if text_lower in ['введение', 'introduction', '1.', '1 ', 'глава', 'часть']:
                    # Это начало следующего раздела
                    if len(toc_entries) > 0:
                        pass  # Убираем debug вывод
                        break
    
    return toc_entries


def parse_toc_from_paragraphs_between_headers(
    all_elements: List[Dict[str, Any]],
    toc_header_xml_pos: int,
    next_header_xml_pos: int
) -> List[Dict[str, Any]]:
    """
    Парсит содержание из обычных параграфов между заголовком "СОДЕРЖАНИЕ" 
    и следующим крупным заголовком.
    """
    toc_entries = []
    
    # Ищем все элементы между заголовками
    for elem in all_elements:
        xml_pos = elem.get('xml_position', -1)
        if toc_header_xml_pos < xml_pos < next_header_xml_pos:
            elem_type = elem.get('type', '')
            text = elem.get('text', '').strip()
            
            if elem_type == 'paragraph' and text:
                # Пропускаем заголовок "Содержание" если он попал в диапазон
                text_lower = text.lower().strip()
                if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                    continue
                
                # Пытаемся определить, является ли это записью содержания
                # Формат: "Заголовок ................... 5" или "1. Заголовок ................... 5"
                
                # Улучшенный парсинг: сначала убираем точки-разделители и заменяем на табуляцию
                clean_text = re.sub(r'\.{2,}', '\t', text)
                # Разделяем по табуляции или множественным пробелам
                parts = re.split(r'\t|\s{3,}', clean_text.strip())
                
                if len(parts) >= 2:
                    # Есть разделение на части - вероятно, это запись оглавления
                    title_part = parts[0].strip()
                    page_part = parts[-1].strip()
                    
                    # Извлекаем номер раздела и название
                    match = re.match(r'^(\d+(?:\.\d+)*)\.?\s+(.+)$', title_part)
                    if match:
                        number = match.group(1)
                        title = match.group(2).strip()
                        title = title.rstrip('\t.').strip()
                        
                        # Определяем уровень по количеству точек в номере
                        level = number.count('.') + 1
                        
                        # Извлекаем номер страницы
                        page_num = None
                        try:
                            page_num = int(page_part)
                        except ValueError:
                            # Пробуем найти номер страницы в конце исходного текста
                            page_match = re.search(r'(\d+)\s*$', text)
                            if page_match:
                                try:
                                    page_num = int(page_match.group(1))
                                except ValueError:
                                    pass
                        
                        # Фильтруем слишком короткие заголовки
                        if len(title) < 3:
                            continue
                        
                        # Проверяем, что заголовок содержит буквы
                        if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                            continue
                        
                        # Пропускаем технические термины
                        is_camel_case = bool(re.match(r'^[a-z]+[A-Z]', title))
                        is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                                not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                        
                        if (title.lower() in ['int', 'varchar', 'pk', 'fk'] or 
                            'http' in title.lower() or
                            is_camel_case or
                            is_technical_term):
                            continue
                        
                        toc_entries.append({
                            'title': title,
                            'page': page_num,
                            'level': level,
                            'number': number,
                            'xml_position': xml_pos,
                            'raw_text': text
                        })
                        continue
                
                # Если не удалось разделить на части, пробуем стандартный метод
                # Ищем номер страницы в конце
                page_match = re.search(r'(\d+)\s*$', text)
                if page_match:
                    page_num = int(page_match.group(1))
                    
                    # Убираем номер страницы и разделители
                    title_with_separators = re.sub(r'[.\s\-]+?\d+\s*$', '', text).strip()
                    
                    # Проверяем, есть ли разделители (точки или тире) между текстом и номером страницы
                    # Это важный признак записи оглавления
                    has_separators = bool(re.search(r'[.\-]{3,}', text)) or bool(re.search(r'\.\s+\.', text))
                    
                    # Также проверяем, что текст не слишком короткий и не является просто числом
                    if len(title_with_separators) < 3:
                        continue
                    
                    # Если нет разделителей, но есть нумерация в начале - тоже может быть записью
                    has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', title_with_separators))
                    
                    # Пропускаем, если нет ни разделителей, ни нумерации (вероятно, это не запись оглавления)
                    if not has_separators and not has_numbering:
                        continue
                    
                    # Определяем уровень по нумерации
                    level = 1
                    level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title_with_separators)
                    if level_match:
                        if level_match.group(3):
                            level = 3
                        elif level_match.group(2):
                            level = 2
                        else:
                            level = 1
                        # Убираем нумерацию из заголовка
                        title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\s+', '', title_with_separators).strip()
                    else:
                        title = title_with_separators
                    
                    # Пропускаем слишком короткие заголовки
                    if len(title) < 3:
                        continue
                    
                    # Проверяем, что заголовок содержит буквы (кириллицу или латиницу)
                    # и не является просто техническим термином (одно слово на латинице без пробелов)
                    has_letters = bool(re.search(r'[а-яёА-ЯЁa-zA-Z]', title))
                    is_single_word = len(title.split()) == 1
                    is_latin_only = bool(re.match(r'^[a-zA-Z]+$', title))
                    
                    # Пропускаем, если это одно слово на латинице без кириллицы (вероятно, технический термин)
                    if not has_letters or (is_single_word and is_latin_only):
                        continue
                    
                    toc_entries.append({
                        'title': title,
                        'page': page_num,
                        'level': level,
                        'xml_position': xml_pos,
                        'raw_text': text
                    })
    
    return toc_entries


def parse_toc_from_table(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Парсит содержание из таблицы (если содержание оформлено как таблица).
    """
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    in_toc_section = False
    
    for elem in body:
        # Проверяем, начинается ли содержание
        if elem.tag == f'{{{NAMESPACES["w"]}}}p':
            text = get_paragraph_text(elem)
            text_lower = text.lower().strip()
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                in_toc_section = True
                continue
        
        # Если мы в секции содержания и нашли таблицу
        if in_toc_section and elem.tag == f'{{{NAMESPACES["w"]}}}tbl':
            # Парсим таблицу
            rows = elem.findall('.//w:tr', NAMESPACES)
            for row in rows:
                cells = row.findall('.//w:tc', NAMESPACES)
                if len(cells) >= 2:
                    # Первая ячейка - заголовок, вторая - номер страницы
                    title = get_paragraph_text(cells[0])
                    page_text = get_paragraph_text(cells[1])
                    
                    page_num = None
                    try:
                        page_num = int(page_text.strip())
                    except:
                        pass
                    
                    if title:
                        toc_entries.append({
                            'title': title,
                            'page': page_num,
                            'level': 1,  # Упрощённо
                            'raw_text': f"{title} {page_text}"
                        })
                        pass  # Убираем debug вывод
            
            # После таблицы содержание обычно заканчивается
            break
    
    return toc_entries


def parse_toc_from_hyperlinks(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Парсит содержание из гиперссылок (w:hyperlink) или статического текста.
    В некоторых файлах оглавление хранится как гиперссылки, которые ссылаются на закладки.
    В других файлах оглавление - это статический текст после заголовка "Содержание".
    """
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    all_paras = list(body.findall('w:p', NAMESPACES))
    
    # Сначала пробуем найти статический текст оглавления по заголовку "Содержание"
    # Используем улучшенный метод парсинга статического текста
    toc_header_found = False
    toc_started = False
    
    # Стоп-паттерны для определения конца оглавления
    stop_patterns = [
        r'^введение\s*$',
        r'^introduction\s*$',
        r'^\d+\.\s+\S',  # Начало главы: "1. Описание..."
        r'^заключение\s*$',
        r'^список литературы\s*$',
        r'^приложени[яе]\s*$',
        r'^глава\s+\d+',
        r'^часть\s+\d+'
    ]
    
    for i, para in enumerate(all_paras):
        para_text = get_paragraph_text(para)
        text_lower = para_text.lower().strip()
        
        # Ищем заголовок "Содержание"
        if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
            toc_header_found = True
            toc_started = True
            continue
        
        # Также проверяем гиперссылки
        hlink_in_para = para.find('.//w:hyperlink', NAMESPACES)
        if hlink_in_para is not None:
            hlink_text = get_paragraph_text(hlink_in_para)
            hlink_text_lower = hlink_text.lower().strip()
            if hlink_text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                toc_header_found = True
                toc_started = True
                continue
        
        # После заголовка собираем следующие параграфы
        if toc_header_found and toc_started:
            # Проверяем конец оглавления
            if any(re.match(pat, text_lower, re.IGNORECASE) for pat in stop_patterns):
                if len(toc_entries) > 0:
                    break
            
            # Пропускаем пустые параграфы
            if not para_text or not para_text.strip():
                continue
            
            # Извлекаем текст (может быть в гиперссылке или обычном тексте)
            text_to_parse = para_text
            if hlink_in_para is not None:
                hlink_text = get_paragraph_text(hlink_in_para)
                if hlink_text and hlink_text.strip():
                    text_to_parse = hlink_text
            
            # Улучшенный парсинг строки оглавления
            # Убираем точки-разделители и заменяем на табуляцию
            clean_text = re.sub(r'\.{2,}', '\t', text_to_parse)
            # Разделяем по табуляции или множественным пробелам
            parts = re.split(r'\t|\s{3,}', clean_text.strip())
            
            if len(parts) >= 2:
                title_part = parts[0].strip()
                page_part = parts[-1].strip()
                
                # Извлекаем номер раздела и название
                # Паттерн: "3.1. База данных" или "3.1 База данных"
                match = re.match(r'^(\d+(?:\.\d+)*)\.?\s+(.+)$', title_part)
                if match:
                    number = match.group(1)
                    title = match.group(2).strip()
                    
                    # Убираем лишние символы из названия (табуляции, точки в конце)
                    title = title.rstrip('\t.').strip()
                    
                    # Определяем уровень по количеству точек в номере
                    level = number.count('.') + 1
                    
                    # Извлекаем номер страницы
                    page_num = None
                    try:
                        page_num = int(page_part)
                    except ValueError:
                        # Пробуем найти номер страницы в конце строки
                        page_match = re.search(r'(\d+)\s*$', text_to_parse)
                        if page_match:
                            try:
                                page_num = int(page_match.group(1))
                            except ValueError:
                                pass
                    
                    # Фильтруем слишком короткие заголовки
                    if len(title) < 3:
                        continue
                    
                    # Проверяем, что заголовок содержит буквы
                    if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                        continue
                    
                    # Пропускаем технические термины
                    is_camel_case = bool(re.match(r'^[a-z]+[A-Z]', title))
                    is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                            not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                    
                    if (title.lower() in ['int', 'varchar', 'pk', 'fk'] or 
                        'http' in title.lower() or
                        is_camel_case or
                        is_technical_term):
                        continue
                    
                    toc_entries.append({
                        'title': title,
                        'page': page_num,
                        'level': level,
                        'number': number,
                        'raw_text': text_to_parse
                    })
            else:
                # Если не удалось разделить на части, пробуем стандартный метод
                # Извлекаем номер страницы
                page_num = None
                title = text_to_parse
                
                page_match = re.search(r'[.\s\-]+?(\d+)\s*$', text_to_parse)
                if not page_match:
                    page_match = re.search(r'(\d+)\s*$', text_to_parse)
                
                if page_match:
                    page_num = int(page_match.group(1))
                    title = re.sub(r'[.\s\-]+?\d+\s*$', '', text_to_parse).strip()
                
                # Определяем уровень
                level = 1
                level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                if level_match:
                    if level_match.group(3):
                        level = 3
                    elif level_match.group(2):
                        level = 2
                    else:
                        level = 1
                    number = level_match.group(0)
                    title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\.?\s+', '', title).strip()
                else:
                    number = None
                
                # Фильтруем
                if len(title) < 3:
                    continue
                
                if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                    continue
                
                # Проверяем признаки TOC записи
                has_separators = bool(re.search(r'[.\-]{3,}', text_to_parse))
                has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', text_to_parse))
                
                if not has_separators and not has_numbering:
                    if page_num is None:
                        continue
                
                # Пропускаем технические термины
                is_camel_case = bool(re.match(r'^[a-z]+[A-Z]', title))
                is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                        not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                
                if (title.lower() in ['int', 'varchar', 'pk', 'fk'] or 
                    'http' in title.lower() or
                    is_camel_case or
                    is_technical_term):
                    continue
                
                toc_entries.append({
                    'title': title.strip(),
                    'page': page_num,
                    'level': level,
                    'number': number,
                    'raw_text': text_to_parse
                })
    
    # Если нашли статический текст, возвращаем его
    if toc_entries:
        return toc_entries
    
    # Если не нашли статический текст, пробуем найти через гиперссылки
    # Сначала ищем заголовок "Содержание" в обычных параграфах или в гиперссылках
    toc_start_found = False
    hyperlink_count = 0
    
    # Проходим по всем параграфам
    for i, para in enumerate(all_paras):
        para_text = get_paragraph_text(para)
        text_lower = para_text.lower().strip()
        
        # Проверяем, является ли это заголовком оглавления (в обычном тексте или в гиперссылке)
        if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
            toc_start_found = True
            continue
        
        # Также проверяем, есть ли "Содержание" внутри гиперссылки в этом параграфе
        hlink_in_para = para.find('.//w:hyperlink', NAMESPACES)
        if hlink_in_para is not None:
            hlink_text_in_para = get_paragraph_text(hlink_in_para)
            hlink_text_lower = hlink_text_in_para.lower().strip()
            # Проверяем точное совпадение или начало с "Содержание"
            if (hlink_text_lower in ['содержание', 'оглавление', 'contents', 'table of contents'] or
                hlink_text_lower.startswith('содержание') or
                'содержание' in hlink_text_lower):
                toc_start_found = True
                # Если "Содержание" - это не весь текст, а часть (например, "Содержание5"),
                # то это может быть первая запись TOC
                if hlink_text_lower != 'содержание':
                    # Пробуем извлечь запись из этой гиперссылки
                    page_num = None
                    title = hlink_text_in_para
                    
                    # Ищем номер страницы
                    page_match = re.search(r'(\d+)\s*$', hlink_text_in_para)
                    if page_match:
                        page_num = int(page_match.group(1))
                        title = re.sub(r'\s*\d+\s*$', '', hlink_text_in_para).strip()
                    
                    # Убираем "Содержание" из начала, если оно там есть
                    if title.lower().startswith('содержание'):
                        title = title[len('содержание'):].strip()
                    
                    if title and len(title) >= 3:
                        level = 1
                        level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                        if level_match:
                            if level_match.group(3):
                                level = 3
                            elif level_match.group(2):
                                level = 2
                            else:
                                level = 1
                            title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\s+', '', title).strip()
                        
                        if re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                            toc_entries.append({
                                'title': title.strip(),
                                'page': page_num,
                                'level': level,
                                'raw_text': hlink_text_in_para
                            })
                continue
        
        # Если нашли начало оглавления, ищем гиперссылки
        if toc_start_found:
            # Проверяем, есть ли в параграфе гиперссылка
            hlink = para.find('.//w:hyperlink', NAMESPACES)
            if hlink is not None:
                hlink_text = get_paragraph_text(hlink)
                
                if not hlink_text or not hlink_text.strip():
                    continue
                
                # Извлекаем номер страницы (если есть в конце)
                page_num = None
                title = hlink_text
                
                # Ищем номер страницы в конце (последнее число)
                page_match = re.search(r'(\d+)\s*$', hlink_text)
                if page_match:
                    page_num = int(page_match.group(1))
                    # Убираем номер страницы
                    title = re.sub(r'\s*\d+\s*$', '', hlink_text).strip()
                
                # Определяем уровень по нумерации
                level = 1
                level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                if level_match:
                    if level_match.group(3):
                        level = 3
                    elif level_match.group(2):
                        level = 2
                    else:
                        level = 1
                
                # Фильтруем слишком короткие заголовки
                if len(title) < 3:
                    continue
                
                # Проверяем, что заголовок содержит хотя бы одну букву
                if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                    continue
                
                # Пропускаем URL-ы и технические термины
                # Проверяем camelCase (начинается с маленькой буквы, затем большая)
                is_camel_case = bool(re.match(r'^[a-z]+[A-Z]', title))
                # Проверяем, что это не технический термин (только латинские буквы, без пробелов, без кириллицы)
                is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                
                if (title.lower() in ['int', 'varchar', 'pk', 'fk', 'numberprofstandart', 
                                      'codeprofstandart', 'nameprofstandart'] or 
                    'http' in title.lower() or
                    is_camel_case or
                    is_technical_term):
                    continue
                
                # Дополнительная проверка: если заголовок не содержит кириллицу и не содержит пробелов, 
                # и при этом не начинается с цифры - вероятно, это технический термин
                if (not re.search(r'[а-яё]', title, re.IGNORECASE) and 
                    ' ' not in title and 
                    not re.match(r'^\d+', title) and
                    len(title) < 30):
                    continue
                
                # Убираем нумерацию из заголовка, если она есть
                if level_match:
                    title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\s+', '', title).strip()
                
                # Проверяем, не закончилось ли оглавление
                if not page_num and len(toc_entries) > 0:
                    # Проверяем, не является ли это началом следующего раздела
                    if (title.lower() in ['введение', 'introduction', 'заключение', 'список литературы'] or
                        (level == 1 and not re.search(r'^\d+\.', title))):
                        break
                
                toc_entries.append({
                    'title': title.strip(),
                    'page': page_num,
                    'level': level,
                    'raw_text': hlink_text
                })
                hyperlink_count += 1
            else:
                # Если в параграфе нет гиперссылки, но есть текст - тоже может быть записью TOC
                if para_text and para_text.strip() and len(toc_entries) > 0:
                    # Проверяем, не является ли это следующим крупным заголовком
                    text_lower = para_text.lower().strip()
                    if (re.match(r'^(введение|introduction|1\.|1\s|глава|часть)', text_lower, re.IGNORECASE)):
                        break
                    
                    # Извлекаем номер страницы
                    page_num = None
                    title = para_text
                    
                    page_match = re.search(r'[.\s\-]+?(\d+)\s*$', para_text)
                    if not page_match:
                        page_match = re.search(r'(\d+)\s*$', para_text)
                    
                    if page_match:
                        page_num = int(page_match.group(1))
                        title = re.sub(r'[.\s\-]+?\d+\s*$', '', para_text).strip()
                    
                    # Определяем уровень
                    level = 1
                    level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                    if level_match:
                        if level_match.group(3):
                            level = 3
                        elif level_match.group(2):
                            level = 2
                        else:
                            level = 1
                        title = re.sub(r'^\d+(?:\.\d+)*(?:\.\d+)?\s+', '', title).strip()
                    
                    # Фильтруем
                    if len(title) < 3:
                        continue
                    
                    if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                        continue
                    
                    # Проверяем, есть ли разделители или нумерация (признаки TOC записи)
                    has_separators = bool(re.search(r'[.\-]{3,}', para_text))
                    has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', title))
                    
                    if not has_separators and not has_numbering:
                        if page_num is None:
                            continue
                    
                    toc_entries.append({
                        'title': title.strip(),
                        'page': page_num,
                        'level': level,
                        'raw_text': para_text
                    })
                elif len(toc_entries) > 0 and para_text.strip():
                    # Если это не пустой параграф и не содержит разделителей (точек/тире),
                    # возможно, это начало следующего раздела
                    if not re.search(r'[.\-]{3,}', para_text):
                        # Проверяем, является ли это заголовком
                        if (re.match(r'^\d+[.\s]', para_text) or 
                            para_text.lower() in ['введение', 'introduction', 'глава', 'часть']):
                            break
    
    # Если не нашли через параграфы, пробуем найти все гиперссылки подряд
    if not toc_entries:
        hyperlinks = body.findall('.//w:hyperlink', NAMESPACES)
        in_toc_section = False
        first_hyperlink_processed = False
        
        for hlink in hyperlinks:
            hlink_text = get_paragraph_text(hlink)
            
            if not hlink_text or not hlink_text.strip():
                continue
            
            # Проверяем, начинается ли оглавление
            text_lower = hlink_text.lower().strip()
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                in_toc_section = True
                first_hyperlink_processed = True
                continue
            
            # Если это первая гиперссылка и она содержит "Содержание" в начале, начинаем парсинг
            if not first_hyperlink_processed and 'содержание' in text_lower:
                in_toc_section = True
                first_hyperlink_processed = True
                # Если "Содержание" - это не весь текст, а часть, то это может быть первая запись
                if text_lower != 'содержание':
                    # Это может быть "Содержание5" или подобное - начинаем парсинг с этой записи
                    pass
                continue
            
            # Если мы в секции оглавления
            if in_toc_section:
                # Извлекаем номер страницы (если есть в конце)
                page_num = None
                title = hlink_text
                
                # Ищем номер страницы в конце (последнее число)
                page_match = re.search(r'(\d+)\s*$', hlink_text)
                if page_match:
                    page_num = int(page_match.group(1))
                    # Убираем номер страницы
                    title = re.sub(r'\s*\d+\s*$', '', hlink_text).strip()
                
                # Определяем уровень по нумерации
                level = 1
                level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                if level_match:
                    if level_match.group(3):
                        level = 3
                    elif level_match.group(2):
                        level = 2
                    else:
                        level = 1
                
                # Фильтруем слишком короткие заголовки и технические термины
                if len(title) < 3:
                    continue
                
                # Проверяем, что заголовок содержит хотя бы одну букву
                if not re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                    continue
                
                # Пропускаем URL-ы и технические термины
                # Проверяем camelCase (начинается с маленькой буквы, затем большая)
                is_camel_case = bool(re.match(r'^[a-z]+[A-Z]', title))
                # Проверяем, что это не технический термин (только латинские буквы, без пробелов, без кириллицы)
                is_technical_term = bool(re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title)
                
                if (title.lower() in ['int', 'varchar', 'pk', 'fk', 'numberprofstandart', 
                                      'codeprofstandart', 'nameprofstandart'] or 
                    'http' in title.lower() or
                    is_camel_case or
                    is_technical_term):
                    continue
                
                # Дополнительная проверка: если заголовок не содержит кириллицу и не содержит пробелов, 
                # и при этом не начинается с цифры - вероятно, это технический термин
                if (not re.search(r'[а-яё]', title, re.IGNORECASE) and 
                    ' ' not in title and 
                    not re.match(r'^\d+', title) and
                    len(title) < 30):
                    continue
                
                # Проверяем, не закончилось ли оглавление
                if not page_num and level == 1 and len(toc_entries) > 0:
                    if title.lower() in ['введение', 'introduction', 'заключение', 'список литературы']:
                        break
                
                toc_entries.append({
                    'title': title.strip(),
                    'page': page_num,
                    'level': level,
                    'raw_text': hlink_text
                })
    
    return toc_entries


def detect_toc_type(root: ET.Element) -> str:
    """
    Определяет тип оглавления в документе.
    
    Returns:
        'dynamic_field' - динамическое TOC поле с PAGEREF
        'static_field_result' - статическое содержимое TOC поля (заблокированное поле)
        'static_hyperlinks' - статические гиперссылки (без TOC поля)
        'mixed' - смешанный тип
        'unknown' - тип не определён
    """
    # Проверяем наличие TOC полей
    fld_chars = root.findall('.//w:fldChar', NAMESPACES)
    instr_texts = root.findall('.//w:instrText', NAMESPACES)
    has_toc_field = False
    
    for instr in instr_texts:
        if instr.text and 'TOC' in instr.text.upper():
            has_toc_field = True
            break
    
    # Проверяем наличие PAGEREF ссылок
    has_pageref = False
    for instr in instr_texts:
        if instr.text and 'PAGEREF' in instr.text.upper():
            has_pageref = True
            break
    
    # Проверяем наличие гиперссылок
    hyperlinks = root.findall('.//w:hyperlink', NAMESPACES)
    has_hyperlinks = len(hyperlinks) > 0
    
    # Проверяем наличие w:fldChar separate (результат TOC поля)
    # Ищем параграфы, которые содержат и TOC инструкцию, и fldChar separate
    has_field_result = False
    body = root.find('w:body', NAMESPACES)
    if body is not None:
        all_paras = body.findall('w:p', NAMESPACES)
        for para in all_paras:
            # Проверяем, есть ли TOC инструкция в параграфе
            instr_texts = para.findall('.//w:instrText', NAMESPACES)
            has_toc_instr = False
            for instr in instr_texts:
                if instr.text and 'TOC' in instr.text.upper():
                    has_toc_instr = True
                    break
            
            if has_toc_instr:
                # Проверяем, есть ли fldChar separate в этом же параграфе или в следующем
                fld_chars_in_para = para.findall('.//w:fldChar', NAMESPACES)
                for fld_char in fld_chars_in_para:
                    fld_type = fld_char.get(f'{{{NAMESPACES["w"]}}}fldCharType') or fld_char.get('fldCharType')
                    if fld_type == 'separate':
                        has_field_result = True
                        break
                if has_field_result:
                    break
    
    if has_toc_field and has_pageref:
        return 'dynamic_field'
    elif has_toc_field and has_field_result and not has_pageref:
        # TOC поле есть, но нет PAGEREF - значит это статическое содержимое поля
        return 'static_field_result'
    elif has_hyperlinks and not has_toc_field:
        return 'static_hyperlinks'
    elif has_toc_field and has_hyperlinks:
        return 'mixed'
    else:
        return 'unknown'


def parse_toc_from_file(docx_path: Path) -> List[Dict[str, Any]]:
    """Парсит содержание из одного файла и возвращает список заголовков."""
    if not docx_path.exists():
        print(f"[WARNING] Файл не найден: {docx_path}", file=sys.stderr)
        return []
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # Определяем тип оглавления
            toc_type = detect_toc_type(root)
            
            # Выбираем метод парсинга в зависимости от типа
            if toc_type == 'dynamic_field':
                # Для динамических полей сначала пробуем PAGEREF
                toc_from_fields = parse_toc_from_field(root)
                if toc_from_fields:
                    return toc_from_fields
            elif toc_type == 'static_field_result':
                # Для статического содержимого TOC поля извлекаем текст напрямую
                toc_from_field_result = extract_toc_text_from_field_result(root)
                if toc_from_field_result:
                    return toc_from_field_result
                # Если не получилось, пробуем через гиперссылки
                toc_from_hyperlinks = parse_toc_from_hyperlinks(root)
                if toc_from_hyperlinks:
                    return toc_from_hyperlinks
            elif toc_type == 'static_hyperlinks':
                # Для статических гиперссылок используем их напрямую
                toc_from_hyperlinks = parse_toc_from_hyperlinks(root)
                if toc_from_hyperlinks:
                    return toc_from_hyperlinks
            elif toc_type == 'mixed':
                # Для смешанного типа пробуем оба метода
                toc_from_fields = parse_toc_from_field(root)
                if toc_from_fields:
                    return toc_from_fields
                toc_from_field_result = extract_toc_text_from_field_result(root)
                if toc_from_field_result:
                    return toc_from_field_result
                toc_from_hyperlinks = parse_toc_from_hyperlinks(root)
                if toc_from_hyperlinks:
                    return toc_from_hyperlinks
            
            # Если тип не определён или методы не сработали, пробуем все методы
            toc_from_hyperlinks = parse_toc_from_hyperlinks(root)
            if toc_from_hyperlinks:
                return toc_from_hyperlinks
            
            toc_from_fields = parse_toc_from_field(root)
            toc_from_styles = parse_toc_from_styles(root)
            toc_from_table = parse_toc_from_table(root)
            
            # Если нашли через поля - используем их (самый надёжный метод)
            if toc_from_fields:
                return toc_from_fields
            
            # Если нашли через стили - используем их
            if toc_from_styles:
                return toc_from_styles
            
            # Если нашли через таблицу - используем её
            if toc_from_table:
                return toc_from_table
            
            # Если ничего не нашли, пробуем парсить через all_elements
            try:
                all_elements = extract_all_elements_from_docx_xml_ordered(docx_path)
                
                # Ищем заголовок "Содержание" или "Оглавление"
                toc_header_pos = None
                next_header_pos = None
                
                for i, elem in enumerate(all_elements):
                    text = elem.get('text', '').strip().lower()
                    # Более гибкий поиск заголовка оглавления
                    if (text in ['содержание', 'оглавление', 'contents', 'table of contents'] or
                        text.startswith('содержание') or text.startswith('оглавление')):
                        toc_header_pos = elem.get('xml_position', -1)
                        # Ищем следующий крупный заголовок
                        # Пропускаем несколько элементов после заголовка оглавления (само оглавление)
                        toc_entries_found = 0
                        for j in range(i + 1, min(i + 100, len(all_elements))):  # Увеличиваем лимит до 100
                            next_elem = all_elements[j]
                            next_text = next_elem.get('text', '').strip()
                            
                            # Пропускаем пустые элементы
                            if not next_text:
                                continue
                            
                            # Проверяем, является ли это записью оглавления
                            has_page_num = bool(re.search(r'\d+\s*$', next_text))
                            has_separators = bool(re.search(r'[.\-]{3,}', next_text))
                            has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', next_text))
                            is_toc_entry = has_page_num and (has_separators or has_numbering)
                            
                            if is_toc_entry:
                                toc_entries_found += 1
                                continue  # Это запись оглавления, пропускаем
                            
                            # Если мы нашли хотя бы несколько записей оглавления, и теперь встретили что-то другое,
                            # это может быть конец оглавления
                            if toc_entries_found > 0:
                                # Это может быть следующий заголовок, если:
                                # 1. Начинается с числа и точки/пробела
                                # 2. Является ключевым словом (Введение, Глава и т.д.)
                                # 3. Имеет длину больше 3 символов
                                # 4. НЕ является записью оглавления (нет номера страницы в конце или нет разделителей)
                                if (len(next_text) > 3 and
                                    (re.match(r'^\d+[.\s]', next_text) or 
                                     next_text.lower() in ['введение', 'introduction', 'глава', 'часть', 'раздел', 'заключение'] or
                                     next_text.lower().startswith('глава ') or
                                     next_text.lower().startswith('часть ')) and
                                    not (has_page_num and has_separators)):
                                    next_header_pos = next_elem.get('xml_position', -1)
                                    break
                            
                            # Если мы ещё не нашли записей оглавления, но встретили явный заголовок - это конец
                            if toc_entries_found == 0 and len(next_text) > 3:
                                if (re.match(r'^\d+[.\s]', next_text) or 
                                    next_text.lower() in ['введение', 'introduction', 'глава', 'часть', 'раздел']):
                                    # Это не оглавление, а сам документ начинается
                                    break
                        
                        if toc_header_pos is not None:
                            break
                
                if toc_header_pos is not None:
                    toc_from_paragraphs = parse_toc_from_paragraphs_between_headers(
                        all_elements,
                        toc_header_pos,
                        next_header_pos if next_header_pos else 999999
                    )
                    if toc_from_paragraphs:
                        return toc_from_paragraphs
            except Exception as e:
                pass  # Игнорируем ошибки при парсинге через all_elements
            
            return []
            
    except Exception as e:
        print(f"[ERROR] Ошибка при обработке {docx_path.name}: {e}", file=sys.stderr)
        return []


def main():
    """Основная функция для тестирования парсинга содержания из нескольких файлов."""
    # Определяем путь относительно директории скрипта
    script_dir = Path(__file__).parent
    test_folder = script_dir / "test_folder"
    
    # Список файлов для обработки
    docx_files = [
        test_folder / "Диплом.docx",
        test_folder / "Diplom2024.docx",
        test_folder / "02_Отчет_Этап_2_полный_замечания_эксперта.docx",
        test_folder / "Методическая-консультация.docx",
        test_folder / "Отчёт_ГОСТ.docx",
        test_folder / "Отчёт_НИР.docx"
    ]
    
    all_results = []
    
    for docx_path in docx_files:
        toc_entries = parse_toc_from_file(docx_path)
        all_results.append({
            'file': docx_path.name,
            'entries': toc_entries
        })
    
    # Выводим результаты: сначала название файла, потом все заголовки
    for i, result in enumerate(all_results):
        file_name = result['file']
        entries = result['entries']
        
        # Добавляем пустую строку перед каждым файлом (кроме первого)
        if i > 0:
            print()
        
        print(file_name)
        if entries:
            for entry in entries:
                title = entry.get('title', '').strip()
                if title:  # Пропускаем пустые заголовки
                    print(title)


if __name__ == '__main__':
    main()
