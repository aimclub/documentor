"""
Пайплайн для замены OCR-таблиц на структуру из DOCX XML через текстовый контекст.

Идея:
1. Извлекаем таблицы из DOCX XML с текстовым контекстом (текст до/после таблицы)
2. Во время OCR пайплайна извлекаем текст по страницам через Qwen
3. DOTS OCR находит таблицы на страницах
4. Сопоставляем: "между текстом X и текстом Y должна быть таблица N" → 
   "DOTS OCR нашел таблицу между текстом X и Y" → "это таблица N из DOCX"
5. Заменяем OCR-таблицу на структуру из DOCX XML (markdown/JSON)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO
import re

from PIL import Image
import fitz  # PyMuPDF

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
    extract_tables_from_docx_xml,
    extract_text_from_pdf_by_bbox,
    extract_all_text_from_docx,
)

from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer
from documentor.processing.parsers.pdf.ocr.qwen_ocr import ocr_text_with_qwen
import base64
import os

# Используем 2x увеличение для DOTS OCR
RENDER_SCALE = 2.0


def extract_tables_with_context(docx_path: Path, context_paragraphs: int = 2) -> List[Dict[str, Any]]:
    """
    Извлекает таблицы из DOCX XML с текстовым контекстом до/после.
    
    Args:
        docx_path: Путь к DOCX файлу
        context_paragraphs: Количество параграфов до/после для контекста
    
    Returns:
        Список таблиц с контекстом
    """
    # Используем существующую функцию для извлечения таблиц
    tables = extract_tables_from_docx_xml(docx_path)
    
    # Теперь нужно добавить текстовый контекст
    # Для этого нужно парсить XML напрямую
    import zipfile
    import xml.etree.ElementTree as ET
    
    NAMESPACES = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    }
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # Находим body документа
            body = root.find('w:body', NAMESPACES)
            if body is None:
                print(f"    Предупреждение: не найден body в document.xml")
                return tables
            
            # Собираем все элементы body в порядке появления (параграфы и таблицы)
            all_elements = list(body)
            
            # Находим все таблицы и их позиции
            table_elements = []
            for elem_idx, elem in enumerate(all_elements):
                if elem.tag.endswith('}tbl'):  # Таблица
                    table_elements.append({
                        'element_index': elem_idx,
                        'table_element': elem
                    })
            
            # Для каждой таблицы извлекаем контекст
            for table_index, table_info in enumerate(table_elements):
                if table_index >= len(tables):
                    break
                
                elem_idx = table_info['element_index']
                
                # Текст до таблицы - ищем параграфы перед таблицей
                text_before = []
                for i in range(elem_idx - 1, max(-1, elem_idx - context_paragraphs - 1), -1):
                    elem = all_elements[i]
                    if elem.tag.endswith('}p'):  # Параграф
                        text = _extract_text_from_paragraph(elem, NAMESPACES)
                        if text.strip():
                            text_before.insert(0, text.strip())  # Добавляем в начало, чтобы сохранить порядок
                            if len(text_before) >= context_paragraphs:
                                break
                
                # Текст после таблицы - ищем параграфы после таблицы
                text_after = []
                for i in range(elem_idx + 1, min(len(all_elements), elem_idx + context_paragraphs + 1)):
                    elem = all_elements[i]
                    if elem.tag.endswith('}p'):  # Параграф
                        text = _extract_text_from_paragraph(elem, NAMESPACES)
                        if text.strip():
                            text_after.append(text.strip())
                            if len(text_after) >= context_paragraphs:
                                break
                    elif elem.tag.endswith('}tbl'):  # Следующая таблица - останавливаемся
                        break
                
                # Добавляем контекст к таблице
                tables[table_index]['text_before'] = ' | '.join(text_before[-context_paragraphs:])
                tables[table_index]['text_after'] = ' | '.join(text_after[:context_paragraphs])
                tables[table_index]['paragraph_index'] = elem_idx
                tables[table_index]['table_number'] = table_index + 1
    except Exception as e:
        print(f"    Предупреждение: не удалось извлечь контекст для таблиц: {e}")
        # Возвращаем таблицы без контекста
        for i, table in enumerate(tables):
            table['text_before'] = ''
            table['text_after'] = ''
            table['table_number'] = i + 1
    
    return tables


def _extract_text_from_paragraph(para, namespaces: Dict[str, str]) -> str:
    """Извлекает текст из параграфа."""
    texts = para.findall('.//w:t', namespaces)
    return ''.join(t.text or '' for t in texts)


def extract_text_with_qwen_improved(image: Image.Image, context: str = "") -> Optional[str]:
    """
    Улучшенная функция для извлечения текста через Qwen с более точным промптом.
    
    Args:
        image: Изображение для OCR
        context: Контекст (для отладки)
    
    Returns:
        Извлеченный текст или None
    """
    try:
        import openai
        from documentor.utils.ocr_image_utils import fetch_image
        
        base_url_raw = os.getenv("QWEN_BASE_URL")
        base_url = None
        if base_url_raw:
            for line in base_url_raw.split('\n'):
                for url in line.split(','):
                    url = url.strip()
                    if "#" in url:
                        url = url.split("#")[0].strip()
                    if url:
                        base_url = url
                        break
                if base_url:
                    break
        
        api_key = os.getenv("QWEN_API_KEY")
        temperature = float(os.getenv("QWEN_TEMPERATURE", "0.1"))
        max_tokens = int(os.getenv("QWEN_MAX_TOKENS", "4096"))
        model_name = os.getenv("QWEN_MODEL_NAME")
        timeout = int(os.getenv("QWEN_TIMEOUT", "180"))
        
        if not base_url:
            print(f"      ⚠ QWEN_BASE_URL не установлен")
            return None
        
        if not base_url.endswith("/v1"):
            if base_url.endswith("/"):
                base_url = f"{base_url}v1"
            else:
                base_url = f"{base_url}/v1"
        
        # Улучшенный промпт - более строгий и конкретный
        prompt = """You are a text recognition system. Extract ONLY the visible text from this image.

CRITICAL RULES:
1. Extract ONLY the actual text content visible in the image
2. Do NOT generate, invent, or hallucinate any text
3. Do NOT add explanations, comments, or descriptions
4. Do NOT translate the text
5. Preserve the original language and characters
6. If you see tables, diagrams, or structured data - SKIP them, extract only regular paragraph text
7. If the image is empty or contains no readable text, return empty string
8. Output ONLY the extracted text, nothing else

Extract the text now:"""
        
        # Подготавливаем изображение
        optimized_image = fetch_image(
            image,
            min_pixels=None,
            max_pixels=None,
        )
        
        # Конвертируем в base64
        buffer = BytesIO()
        optimized_image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        image_base64 = f"data:image/png;base64,{encoded}"
        
        client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_base64}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        
        content = response.choices[0].message.content
        if content:
            content = content.strip()
            # Удаляем возможные префиксы/суффиксы от модели
            if content.startswith("```"):
                # Удаляем markdown code blocks если есть
                content = content.strip("```").strip()
            if content.startswith("Extracted text:"):
                content = content.replace("Extracted text:", "").strip()
            if content.startswith("Text:"):
                content = content.replace("Text:", "").strip()
            
            return content
        
        return None
        
    except Exception as e:
        print(f"      Ошибка при извлечении текста через Qwen ({context}): {e}")
        return None


def extract_text_from_pdf_page(pdf_path: Path, page_num: int) -> str:
    """Извлекает текст со страницы PDF."""
    try:
        pdf_doc = fitz.open(str(pdf_path))
        page = pdf_doc.load_page(page_num)
        text = page.get_text()
        pdf_doc.close()
        return text
    except Exception as e:
        print(f"    Ошибка при извлечении текста со страницы {page_num}: {e}")
        return ""


def calculate_text_context_similarity(context1: str, context2: str) -> float:
    """
    Вычисляет схожесть текстовых контекстов через совпадающие слова (Jaccard similarity).
    """
    if not context1 or not context2:
        return 0.0
    
    words1 = set(re.findall(r'\b\w+\b', context1.lower()))
    words2 = set(re.findall(r'\b\w+\b', context2.lower()))
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def find_table_position_in_text(
    table: Dict[str, Any],
    page_text: str
) -> Optional[Tuple[int, int, float]]:
    """
    Находит позицию таблицы в тексте страницы через контекст.
    
    Args:
        table: Таблица из DOCX с контекстом
        page_text: Текст со страницы PDF
    
    Returns:
        Кортеж (start_pos, end_pos, score) или None
    """
    text_before = table.get('text_before', '')
    text_after = table.get('text_after', '')
    
    if not text_before and not text_after:
        return None
    
    page_text_lower = page_text.lower()
    
    # Ищем текст до таблицы
    before_pos = -1
    if text_before:
        # Берем последние 50 символов для поиска
        before_search = text_before[-50:].lower()
        before_words = re.findall(r'\b\w+\b', before_search)
        if before_words:
            # Ищем последние 3-5 слов
            search_phrase = ' '.join(before_words[-5:])
            before_pos = page_text_lower.find(search_phrase)
            if before_pos == -1:
                # Пробуем с меньшим количеством слов
                search_phrase = ' '.join(before_words[-3:])
                before_pos = page_text_lower.find(search_phrase)
    
    # Ищем текст после таблицы
    after_pos = -1
    if text_after:
        # Берем первые 50 символов для поиска
        after_search = text_after[:50].lower()
        after_words = re.findall(r'\b\w+\b', after_search)
        if after_words:
            # Ищем первые 3-5 слов
            search_phrase = ' '.join(after_words[:5])
            after_pos = page_text_lower.find(search_phrase)
            if after_pos == -1:
                # Пробуем с меньшим количеством слов
                search_phrase = ' '.join(after_words[:3])
                after_pos = page_text_lower.find(search_phrase)
    
    # Если нашли оба маркера, вычисляем позицию таблицы между ними
    if before_pos != -1 and after_pos != -1 and before_pos < after_pos:
        # Таблица должна быть между before_pos и after_pos
        score = calculate_text_context_similarity(
            f"{text_before} {text_after}",
            page_text[max(0, before_pos-100):after_pos+100]
        )
        return (before_pos, after_pos, score)
    elif before_pos != -1:
        # Нашли только текст до, таблица должна быть после него
        score = calculate_text_context_similarity(
            text_before,
            page_text[max(0, before_pos-100):before_pos+200]
        )
        return (before_pos, before_pos + 200, score)
    elif after_pos != -1:
        # Нашли только текст после, таблица должна быть до него
        score = calculate_text_context_similarity(
            text_after,
            page_text[max(0, after_pos-200):after_pos+100]
        )
        return (after_pos - 200, after_pos, score)
    
    return None


def extract_text_blocks_around_table(
    ocr_table: Dict[str, Any],
    page_image: Image.Image,
    page_num: int,
    temp_pdf_path: Path,
    renderer: PdfPageRenderer,
    all_ocr_tables: List[Dict[str, Any]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Извлекает текстовые блоки до и после таблицы из PDF напрямую через PyMuPDF.
    Это более надежно, чем Qwen OCR.
    
    Args:
        ocr_table: Таблица, найденная через DOTS OCR
        page_image: Изображение страницы (для определения размеров)
        page_num: Номер страницы
        temp_pdf_path: Путь к PDF
        renderer: Рендерер страниц
        all_ocr_tables: Все таблицы на странице (для исключения их областей)
    
    Returns:
        Кортеж (text_before, text_after) или (None, None) при ошибке
    """
    bbox = ocr_table.get('bbox', [])
    if not bbox or len(bbox) != 4:
        return (None, None)
    
    x1, y1, x2, y2 = bbox
    page_width, page_height = page_image.size
    
    # Координаты bbox в масштабе рендеринга (2x), нужно привести к масштабу PDF
    scale_factor = RENDER_SCALE
    
    # Находим ближайшие таблицы до и после текущей
    if all_ocr_tables:
        tables_on_page = [t for t in all_ocr_tables if t.get('page_num') == page_num]
        tables_before = [t for t in tables_on_page if t.get('bbox', [3])[3] < y1]  # Таблицы выше
        tables_after = [t for t in tables_on_page if t.get('bbox', [1])[1] > y2]  # Таблицы ниже
        
        # Находим самую нижнюю таблицу до текущей
        if tables_before:
            last_table_before = max(tables_before, key=lambda t: t.get('bbox', [3])[3])
            y_start_rendered = last_table_before.get('bbox', [3])[3] + 20
        else:
            y_start_rendered = 0
        
        # Находим самую верхнюю таблицу после текущей
        if tables_after:
            first_table_after = min(tables_after, key=lambda t: t.get('bbox', [1])[1])
            y_end_rendered = first_table_after.get('bbox', [1])[1] - 20
        else:
            y_end_rendered = page_height
    else:
        y_start_rendered = 0
        y_end_rendered = page_height
    
    # Приводим координаты к масштабу PDF
    y1_pdf = y1 / scale_factor
    y2_pdf = y2 / scale_factor
    y_start_pdf = y_start_rendered / scale_factor
    y_end_pdf = y_end_rendered / scale_factor
    
    text_before = None
    text_after = None
    
    try:
        pdf_doc = fitz.open(str(temp_pdf_path))
        if page_num >= len(pdf_doc):
            pdf_doc.close()
            return (None, None)
        
        page = pdf_doc.load_page(page_num)
        page_rect = page.rect
        
        # Текст до таблицы: от предыдущей таблицы до текущей
        # Расширяем область поиска немного выше таблицы для надежности
        if y_start_pdf < y1_pdf:
            # Берем немного больше области (50 точек выше таблицы)
            before_y_start = max(0, y_start_pdf - 50)
            before_rect = fitz.Rect(0, before_y_start, page_rect.width, y1_pdf)
            text_before = page.get_text("text", clip=before_rect).strip()
            if not text_before:
                # Пробуем без clip - может быть проблема с координатами
                all_text = page.get_text("text")
                # Ищем текст вручную по координатам
                words = page.get_text("words")
                if words:
                    # Фильтруем слова, которые находятся выше таблицы
                    words_before = [w for w in words if w[3] < y1_pdf and w[1] > before_y_start]
                    if words_before:
                        # Сортируем по позиции и собираем текст
                        words_before.sort(key=lambda w: (w[3], w[0]))  # Сортируем по y, затем по x
                        text_before = ' '.join([w[4] for w in words_before]).strip()
            if text_before:
                text_before = clean_ocr_text(text_before)
        
        # Текст после таблицы: от текущей таблицы до следующей
        # Расширяем область поиска немного ниже таблицы для надежности
        if y2_pdf < y_end_pdf:
            # Берем немного больше области (50 точек ниже таблицы)
            after_y_end = min(page_rect.height, y_end_pdf + 50)
            after_rect = fitz.Rect(0, y2_pdf, page_rect.width, after_y_end)
            text_after = page.get_text("text", clip=after_rect).strip()
            if not text_after:
                # Пробуем без clip - может быть проблема с координатами
                words = page.get_text("words")
                if words:
                    # Фильтруем слова, которые находятся ниже таблицы
                    words_after = [w for w in words if w[1] > y2_pdf and w[3] < after_y_end]
                    if words_after:
                        # Сортируем по позиции и собираем текст
                        words_after.sort(key=lambda w: (w[1], w[0]))  # Сортируем по y, затем по x
                        text_after = ' '.join([w[4] for w in words_after]).strip()
            if text_after:
                text_after = clean_ocr_text(text_after)
        
        pdf_doc.close()
        
    except Exception as e:
        print(f"      Ошибка при извлечении текста из PDF: {e}")
        if 'pdf_doc' in locals():
            pdf_doc.close()
    
    return (text_before, text_after)


def clean_ocr_text(text: str) -> str:
    """
    Очищает текст из OCR от лишнего (тестовые строки, таблицы и т.д.).
    """
    if not text:
        return ""
    
    # Удаляем известные тестовые строки
    test_strings = [
        "the quick brown fox jumps over the lazy dog",
        "lorem ipsum",
    ]
    
    text_lower = text.lower()
    for test_str in test_strings:
        if test_str in text_lower:
            # Удаляем эту строку и все после неё
            idx = text_lower.find(test_str)
            text = text[:idx].strip()
            text_lower = text.lower()
    
    # Удаляем строки, которые выглядят как начало таблицы или содержимое таблицы
    lines = text.split('\n')
    cleaned_lines = []
    skip_next_lines = 0
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Пропускаем строки, которые выглядят как заголовки таблиц или содержимое таблиц
        if any(keyword in line_lower for keyword in [
            'таблица', 'table', 'название атрибута', 'домен', 'ключ', 'описание',
            'tblgeneralized', 'tblprofession', 'tbllabor', 'tblnecessary',
            'idgenlaborfunc', 'idprofession', 'idlaborfunc', 'idlaboraction',
            'varchar', 'int pk', 'int fk', 'pk идентификатор', 'идентификатор'
        ]):
            skip_next_lines = 2  # Пропускаем следующие 2 строки (вероятно, тоже из таблицы)
            continue
        
        # Пропускаем строки после заголовков таблиц
        if skip_next_lines > 0:
            skip_next_lines -= 1
            continue
        
        # Пропускаем очень короткие строки (вероятно, артефакты)
        if len(line.strip()) < 3:
            continue
        
        # Пропускаем строки, которые выглядят как данные таблицы (много пробелов, разделители)
        if line.count('|') > 2 or line.count('\t') > 2:
            continue
        
        cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    
    # Если после очистки осталось мало текста, возвращаем пустую строку
    if len(result) < 10:
        return ""
    
    return result


def find_table_between_texts_in_docx(
    text_before: str,
    text_after: str,
    docx_tables: List[Dict[str, Any]],
    docx_all_text: List[Dict[str, Any]],
    docx_path: Path,
    debug: bool = False
) -> Optional[Tuple[Dict[str, Any], float]]:
    """
    Находит таблицу в DOCX между двумя текстовыми блоками.
    
    Args:
        text_before: Текст до таблицы (из OCR через Qwen)
        text_after: Текст после таблицы (из OCR через Qwen)
        docx_tables: Список таблиц из DOCX
        docx_all_text: Весь текст из DOCX (параграфы)
        debug: Включить отладочный вывод
    
    Returns:
        Кортеж (docx_table, score) или None
    """
    # Очищаем текст от лишнего
    text_before = clean_ocr_text(text_before)
    text_after = clean_ocr_text(text_after)
    
    if not text_before and not text_after:
        if debug:
            print(f"      ⚠ Нет текста для поиска (до и после пустые)")
        return None
    
    # Нормализуем тексты для поиска
    text_before_lower = text_before.lower().strip() if text_before else ""
    text_after_lower = text_after.lower().strip() if text_after else ""
    
    if debug:
        print(f"      Очищенный текст до: {text_before_lower[:150]}...")
        print(f"      Очищенный текст после: {text_after_lower[:150]}...")
    
    # Ищем текст до в DOCX - пробуем разные варианты поиска
    before_positions = []
    if text_before_lower:
        # Пробуем найти последние 5, 4, 3, 2 слова
        before_words = re.findall(r'\b\w+\b', text_before_lower)
        for word_count in [5, 4, 3, 2]:
            if len(before_words) >= word_count:
                search_phrase_before = ' '.join(before_words[-word_count:])
                
                for para_idx, para in enumerate(docx_all_text):
                    para_text = para.get('text', '').lower()
                    # Пробуем точное совпадение
                    if search_phrase_before in para_text:
                        before_positions.append(para_idx)
                        if debug:
                            print(f"      Найден текст до в параграфе {para_idx}: '{search_phrase_before}'")
                    # Также пробуем найти отдельные слова (более гибкий поиск)
                    elif word_count <= 3:
                        # Для коротких фраз пробуем найти все слова по отдельности
                        words_found = sum(1 for word in before_words[-word_count:] if word in para_text)
                        if words_found >= word_count - 1:  # Хотя бы все слова кроме одного
                            before_positions.append(para_idx)
                            if debug:
                                print(f"      Найден текст до в параграфе {para_idx} (частичное совпадение): '{search_phrase_before}'")
                if before_positions:
                    break
    
    # Ищем текст после в DOCX - пробуем разные варианты поиска
    after_positions = []
    if text_after_lower:
        # Пробуем найти первые 5, 4, 3, 2 слова
        after_words = re.findall(r'\b\w+\b', text_after_lower)
        for word_count in [5, 4, 3, 2]:
            if len(after_words) >= word_count:
                search_phrase_after = ' '.join(after_words[:word_count])
                
                for para_idx, para in enumerate(docx_all_text):
                    para_text = para.get('text', '').lower()
                    # Пробуем точное совпадение
                    if search_phrase_after in para_text:
                        after_positions.append(para_idx)
                        if debug:
                            print(f"      Найден текст после в параграфе {para_idx}: '{search_phrase_after}'")
                    # Также пробуем найти отдельные слова (более гибкий поиск)
                    elif word_count <= 3:
                        # Для коротких фраз пробуем найти все слова по отдельности
                        words_found = sum(1 for word in after_words[:word_count] if word in para_text)
                        if words_found >= word_count - 1:  # Хотя бы все слова кроме одного
                            after_positions.append(para_idx)
                            if debug:
                                print(f"      Найден текст после в параграфе {para_idx} (частичное совпадение): '{search_phrase_after}'")
                if after_positions:
                    break
    
    # Ищем таблицу между найденными позициями
    # ВАЖНО: paragraph_index в таблицах - это индекс элемента в XML, а не индекс параграфа в docx_all_text
    # Поэтому мы используем схожесть контекста напрямую, без проверки индексов
    best_match = None
    best_score = 0.0
    
    if debug:
        print(f"      Ищем среди {len(docx_tables)} таблиц из DOCX...")
        if before_positions:
            print(f"      Найдено {len(before_positions)} позиций 'до': {before_positions[:5]}")
        if after_positions:
            print(f"      Найдено {len(after_positions)} позиций 'после': {after_positions[:5]}")
        # Показываем примеры контекста из DOCX таблиц
        if docx_tables:
            print(f"      Пример контекста первой DOCX таблицы:")
            first_docx = docx_tables[0]
            print(f"        До: {first_docx.get('text_before', '')[:100]}...")
            print(f"        После: {first_docx.get('text_after', '')[:100]}...")
    
    for docx_table in docx_tables:
        if docx_table.get('matched', False):
            continue
        
        # Вычисляем схожесть контекста напрямую
        docx_before = docx_table.get('text_before', '').lower()
        docx_after = docx_table.get('text_after', '').lower()
        
        score = 0.0
        
        # Если оба текста найдены, проверяем оба контекста
        if text_before_lower and text_after_lower:
            before_similarity = calculate_text_context_similarity(text_before_lower, docx_before) if docx_before else 0.0
            after_similarity = calculate_text_context_similarity(text_after_lower, docx_after) if docx_after else 0.0
            
            # Если хотя бы один контекст совпадает хорошо, считаем это совпадением
            if before_similarity > 0.1 or after_similarity > 0.1:
                score = (before_similarity + after_similarity) / 2.0
        elif text_before_lower:
            # Только текст до
            before_similarity = calculate_text_context_similarity(text_before_lower, docx_before) if docx_before else 0.0
            score = before_similarity
        elif text_after_lower:
            # Только текст после
            after_similarity = calculate_text_context_similarity(text_after_lower, docx_after) if docx_after else 0.0
            score = after_similarity
        
        # Дополнительная проверка: если найдены позиции в docx_all_text, проверяем, что контекст таблицы содержит похожий текст
        if before_positions and docx_before:
            # Проверяем, есть ли совпадение текста из PDF с контекстом таблицы
            for before_idx in before_positions[:3]:  # Берем первые 3 позиции
                para_text = docx_all_text[before_idx].get('text', '').lower()
                # Если текст из PDF содержится в параграфе или наоборот
                if text_before_lower[:50] in para_text or any(word in docx_before for word in text_before_lower.split()[:3]):
                    score += 0.1  # Бонус за позиционное совпадение
                    break
        
        if after_positions and docx_after:
            # Проверяем, есть ли совпадение текста из PDF с контекстом таблицы
            for after_idx in after_positions[:3]:  # Берем первые 3 позиции
                para_text = docx_all_text[after_idx].get('text', '').lower()
                # Если текст из PDF содержится в параграфе или наоборот
                if text_after_lower[:50] in para_text or any(word in docx_after for word in text_after_lower.split()[:3]):
                    score += 0.1  # Бонус за позиционное совпадение
                    break
        
        if score > best_score:
            best_score = score
            best_match = docx_table
            if debug:
                # Показываем все кандидаты, даже с низким score
                print(f"      Кандидат: таблица #{docx_table.get('table_number')}, score: {score:.4f} ({score*100:.2f}%)")
                if text_before_lower:
                    print(f"        PDF до: '{text_before_lower[:80]}...'")
                    print(f"        DOCX до: '{docx_before[:80] if docx_before else '(пусто)'}...'")
                    if docx_before:
                        before_sim = calculate_text_context_similarity(text_before_lower, docx_before)
                        print(f"        Схожесть 'до': {before_sim:.4f}")
                if text_after_lower:
                    print(f"        PDF после: '{text_after_lower[:80]}...'")
                    print(f"        DOCX после: '{docx_after[:80] if docx_after else '(пусто)'}...'")
                    if docx_after:
                        after_sim = calculate_text_context_similarity(text_after_lower, docx_after)
                        print(f"        Схожесть 'после': {after_sim:.4f}")
    
    # Порог для принятия решения (снижен до 0.05 = 5% совпадения для более гибкого поиска)
    if best_score >= 0.05:
        if debug and best_match:
            print(f"      ✓ Найдено совпадение: таблица #{best_match.get('table_number')}, score: {best_score:.2%}")
        return (best_match, best_score)
    
    if debug:
        print(f"      ✗ Лучший score ({best_score:.2%}) ниже порога (0.05)")
    
    return None


def match_ocr_table_to_docx_table(
    ocr_table: Dict[str, Any],
    ocr_page_text: str,
    docx_tables: List[Dict[str, Any]],
    page_image: Image.Image,
    page_num: int,
    temp_pdf_path: Path,
    renderer: PdfPageRenderer,
    docx_all_text: List[Dict[str, Any]],
    debug: bool = False
) -> Optional[Tuple[Dict[str, Any], float]]:
    """
    Сопоставляет OCR-таблицу с таблицей из DOCX через текстовый контекст.
    
    Args:
        ocr_table: Таблица, найденная через DOTS OCR
        ocr_page_text: Текст со страницы, где найдена таблица
        docx_tables: Список таблиц из DOCX с контекстом
        debug: Включить отладочный вывод
    
    Returns:
        Кортеж (docx_table, score) или None
    """
    if not ocr_page_text or not docx_tables:
        return None
    
    best_match = None
    best_score = 0.0
    best_details = None
    
    # Нормализуем текст страницы для поиска
    ocr_page_text_lower = ocr_page_text.lower()
    
    for docx_table in docx_tables:
        if docx_table.get('matched', False):
            continue
        
        text_before = docx_table.get('text_before', '').strip()
        text_after = docx_table.get('text_after', '').strip()
        
        if not text_before and not text_after:
            continue
        
        # Ищем текст до таблицы в странице
        before_found = False
        before_pos = -1
        if text_before:
            # Берем ключевые слова из контекста (последние 3-5 слов)
            before_words = re.findall(r'\b\w+\b', text_before.lower())
            if len(before_words) >= 3:
                # Пробуем найти последние 5 слов, затем 4, затем 3
                for word_count in [5, 4, 3]:
                    search_phrase = ' '.join(before_words[-word_count:])
                    before_pos = ocr_page_text_lower.find(search_phrase)
                    if before_pos != -1:
                        before_found = True
                        break
        
        # Ищем текст после таблицы в странице
        after_found = False
        after_pos = -1
        if text_after:
            # Берем ключевые слова из контекста (первые 3-5 слов)
            after_words = re.findall(r'\b\w+\b', text_after.lower())
            if len(after_words) >= 3:
                # Пробуем найти первые 5 слов, затем 4, затем 3
                for word_count in [5, 4, 3]:
                    search_phrase = ' '.join(after_words[:word_count])
                    after_pos = ocr_page_text_lower.find(search_phrase)
                    if after_pos != -1:
                        after_found = True
                        break
        
        # Вычисляем оценку на основе найденных маркеров
        score = 0.0
        details = {}
        
        if before_found and after_found and before_pos < after_pos:
            # Оба маркера найдены, таблица должна быть между ними
            # Проверяем расстояние между маркерами (не должно быть слишком большим)
            distance = after_pos - before_pos
            if distance < 2000:  # Максимум 2000 символов между маркерами
                # Вычисляем схожесть контекста
                docx_context = f"{text_before} {text_after}".lower()
                ocr_context_snippet = ocr_page_text_lower[max(0, before_pos-200):min(len(ocr_page_text_lower), after_pos+200)]
                context_similarity = calculate_text_context_similarity(docx_context, ocr_context_snippet)
                
                # Оценка основана на схожести контекста и близости маркеров
                score = context_similarity * 0.7 + (1.0 - min(distance / 2000, 1.0)) * 0.3
                details = {
                    'method': 'both_markers',
                    'before_pos': before_pos,
                    'after_pos': after_pos,
                    'distance': distance,
                    'context_similarity': context_similarity
                }
        elif before_found:
            # Найден только маркер "до"
            docx_context = text_before.lower()
            ocr_context_snippet = ocr_page_text_lower[max(0, before_pos-200):min(len(ocr_page_text_lower), before_pos+500)]
            context_similarity = calculate_text_context_similarity(docx_context, ocr_context_snippet)
            score = context_similarity * 0.5  # Снижаем оценку, так как только один маркер
            details = {
                'method': 'before_only',
                'before_pos': before_pos,
                'context_similarity': context_similarity
            }
        elif after_found:
            # Найден только маркер "после"
            docx_context = text_after.lower()
            ocr_context_snippet = ocr_page_text_lower[max(0, after_pos-500):min(len(ocr_page_text_lower), after_pos+200)]
            context_similarity = calculate_text_context_similarity(docx_context, ocr_context_snippet)
            score = context_similarity * 0.5  # Снижаем оценку, так как только один маркер
            details = {
                'method': 'after_only',
                'after_pos': after_pos,
                'context_similarity': context_similarity
            }
        
        if score > best_score:
            best_score = score
            best_match = docx_table
            best_details = details
    
    # Снижаем порог для принятия решения (минимум 0.08 = 8% совпадения)
    # и добавляем отладочный вывод
    if debug and best_match:
        print(f"      Лучшее совпадение: Таблица #{best_match.get('table_number')}, score: {best_score:.2%}")
        if best_details:
            print(f"      Метод: {best_details.get('method')}, детали: {best_details}")
    
    if best_score >= 0.08:  # Снижен порог с 0.15 до 0.08
        return (best_match, best_score)
    
    return None


def table_to_markdown(table: Dict[str, Any]) -> str:
    """Преобразует таблицу из DOCX в markdown формат."""
    if "data" not in table:
        return ""
    
    markdown_lines = []
    data = table["data"]
    
    if not data or len(data) == 0:
        return ""
    
    # Заголовки (первая строка)
    if len(data) > 0:
        header_row = data[0]
        if isinstance(header_row, list):
            header_line = "| " + " | ".join(str(cell) for cell in header_row) + " |"
            markdown_lines.append(header_line)
            
            # Разделитель
            separator = "| " + " | ".join(["---"] * len(header_row)) + " |"
            markdown_lines.append(separator)
            
            # Данные (остальные строки)
            for row in data[1:]:
                if isinstance(row, list):
                    row_line = "| " + " | ".join(str(cell) for cell in row) + " |"
                    markdown_lines.append(row_line)
    
    return "\n".join(markdown_lines)


def process_table_context_replacement(
    docx_path: Path,
    output_dir: Path,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Основная функция пайплайна замены OCR-таблиц на структуру из DOCX.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        limit: Ограничение на количество обрабатываемых таблиц
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*80}")
    print(f"Пайплайн замены OCR-таблиц на структуру из DOCX через контекст")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    replacements_dir = output_dir / "replacements"
    replacements_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Извлекаем таблицы из DOCX с контекстом
    print("Шаг 1: Извлечение таблиц из DOCX с текстовым контекстом...")
    docx_tables = extract_tables_with_context(docx_path, context_paragraphs=3)  # Увеличиваем контекст до 3 параграфов
    print(f"  ✓ Найдено таблиц в DOCX: {len(docx_tables)}")
    
    # Показываем примеры контекста для отладки
    if docx_tables:
        print(f"  Пример контекста для первой таблицы:")
        first_table = docx_tables[0]
        print(f"    До: {first_table.get('text_before', '')[:150]}...")
        print(f"    После: {first_table.get('text_after', '')[:150]}...")
    
    # Шаг 2: Конвертируем DOCX в PDF
    print("\nШаг 2: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        return {"error": str(e)}
    
    # Шаг 3: Извлекаем текст из PDF по страницам
    print("\nШаг 3: Извлечение текста из PDF по страницам...")
    pdf_doc = fitz.open(str(temp_pdf_path))
    page_texts = []
    for page_num in range(len(pdf_doc)):
        text = extract_text_from_pdf_page(temp_pdf_path, page_num)
        page_texts.append({
            'page_num': page_num,
            'text': text
        })
    pdf_doc.close()
    print(f"  ✓ Извлечен текст с {len(page_texts)} страниц")
    
    # Шаг 4: Layout detection через DOTS OCR
    print("\nШаг 4: Layout detection через DOTS OCR...")
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_doc)
    pdf_doc.close()
    
    ocr_table_elements = []
    
    for page_num in range(total_pages):
        print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        # Рендерим страницу
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            continue
        
        # Layout detection
        try:
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image
            )
            
            if success and layout_cells:
                for element in layout_cells:
                    if element.get("category") == "Table":
                        element["page_num"] = page_num
                        ocr_table_elements.append(element)
        except Exception as e:
            print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    print(f"  ✓ Найдено таблиц в OCR: {len(ocr_table_elements)}")
    
    # Шаг 5: Извлекаем весь текст из DOCX для поиска
    print("\nШаг 5: Извлечение всего текста из DOCX...")
    docx_all_text = extract_all_text_from_docx(docx_path)
    print(f"  ✓ Извлечено {len(docx_all_text)} параграфов из DOCX")
    
    # Шаг 6: Сопоставление и замена через текст из PDF
    print(f"\nШаг 6: Сопоставление OCR-таблиц с DOCX таблицами через текстовый контекст из PDF...")
    print(f"  (OCR может найти больше таблиц, чем есть в DOCX - это нормально)")
    
    results = []
    matched_count = 0
    
    for ocr_idx, ocr_table in enumerate(ocr_table_elements):
        if limit and ocr_idx >= limit:
            break
        
        page_num = ocr_table.get('page_num', 0)
        
        print(f"\n  OCR Таблица {ocr_idx + 1}/{len(ocr_table_elements)} (страница {page_num + 1}):")
        
        # Рендерим страницу для извлечения текста через Qwen
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            print(f"    ✗ Не удалось загрузить изображение страницы")
            continue
        
        # Извлекаем текст до и после таблицы из PDF напрямую
        print(f"    Извлечение текста до/после таблицы из PDF...")
        text_before, text_after = extract_text_blocks_around_table(
            ocr_table, page_image, page_num, temp_pdf_path, renderer, ocr_table_elements
        )
        
        if text_before:
            print(f"    ✓ Текст до: {text_before[:100]}...")
        else:
            print(f"    ⚠ Текст до не найден")
        
        if text_after:
            print(f"    ✓ Текст после: {text_after[:100]}...")
        else:
            print(f"    ⚠ Текст после не найден")
        
        # Сопоставляем с таблицей из DOCX
        match_result = find_table_between_texts_in_docx(
            text_before or "",
            text_after or "",
            docx_tables,
            docx_all_text,
            docx_path,
            debug=True
        )
        
        if match_result:
            docx_table, score = match_result
            print(f"    ✓ Найдено совпадение! Таблица #{docx_table.get('table_number')} из DOCX, score: {score:.2%}")
            
            # Помечаем таблицу как сопоставленную
            docx_table['matched'] = True
            
            # Преобразуем DOCX таблицу в markdown
            docx_markdown = table_to_markdown(docx_table)
            
            # Сохраняем замену
            replacement_data = {
                "ocr_table_index": ocr_idx + 1,
                "ocr_page_num": page_num + 1,
                "ocr_bbox": ocr_table.get('bbox', []),
                "docx_table_number": docx_table.get('table_number'),
                "docx_table_index": docx_table.get('index'),
                "match_score": score,
                "docx_markdown": docx_markdown,
                "ocr_text_before_qwen": text_before or "",
                "ocr_text_after_qwen": text_after or "",
                "docx_text_before": docx_table.get('text_before', ''),
                "docx_text_after": docx_table.get('text_after', ''),
            }
            
            replacement_path = replacements_dir / f"replacement_{ocr_idx + 1}.json"
            with open(replacement_path, 'w', encoding='utf-8') as f:
                json.dump(replacement_data, f, ensure_ascii=False, indent=2)
            
            # Сохраняем markdown отдельно
            markdown_path = tables_dir / f"table_{ocr_idx + 1}_from_docx.md"
            with open(markdown_path, 'w', encoding='utf-8') as f:
                f.write(f"# Table {ocr_idx + 1} (from DOCX Table #{docx_table.get('table_number')})\n\n")
                f.write(f"Match Score: {score:.2%}\n\n")
                f.write(f"Text Before: {docx_table.get('text_before', '')}\n\n")
                f.write(f"Text After: {docx_table.get('text_after', '')}\n\n")
                f.write("## Table Content\n\n")
                f.write(docx_markdown)
            
            match_status = "matched"
            matched_count += 1
        else:
            print(f"    ✗ Совпадение не найдено")
            match_status = "not_found"
            docx_table = None
            score = 0.0
        
        results.append({
            "ocr_table_index": ocr_idx + 1,
            "ocr_page_num": page_num + 1,
            "ocr_bbox": ocr_table.get('bbox', []),
            "match_status": match_status,
            "docx_table_number": docx_table.get('table_number') if docx_table else None,
            "match_score": score,
        })
    
    # Сохраняем результаты
    summary = {
        "total_docx_tables": len(docx_tables),
        "total_ocr_tables": len(ocr_table_elements),
        "matched_tables": matched_count,
        "not_found_tables": len(ocr_table_elements) - matched_count,
        "results": results
    }
    
    summary_path = output_dir / "summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*80}")
    print(f"ИТОГИ")
    print(f"{'='*80}")
    print(f"Всего таблиц в DOCX: {len(docx_tables)}")
    print(f"Всего таблиц в OCR: {len(ocr_table_elements)}")
    print(f"Совпадений найдено: {matched_count}")
    print(f"Не найдено: {len(ocr_table_elements) - matched_count}")
    print(f"Результаты сохранены: {summary_path}")
    
    return summary


if __name__ == "__main__":
    # Пример использования
    test_folder = Path(r"E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_folder")
    docx_file = test_folder / "Diplom2024.docx"
    output_dir = Path(__file__).parent / "results" / "table_context_replacement" / docx_file.stem
    
    result = process_table_context_replacement(docx_file, output_dir, limit=10)
    print(f"\nРезультат: {result}")
