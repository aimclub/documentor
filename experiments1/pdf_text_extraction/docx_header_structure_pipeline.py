"""
Пайплайн для сохранения структуры заголовков из DOTS OCR с распределением по уровням.

Идея:
1. DOTS OCR находит заголовки (Section-header, Title) на страницах PDF
2. Извлекаем заголовки из DOCX XML с уровнями (Heading 1-6, Title)
3. Сопоставляем заголовки из OCR с заголовками из DOCX по тексту
4. Присваиваем уровни заголовкам из OCR на основе DOCX
5. Если сопоставление не найдено, используем эвристики (нумерация, размер шрифта, позиция)
6. Сохраняем структуру заголовков с уровнями (HEADER_1, HEADER_2, и т.д.)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import re

import fitz  # PyMuPDF

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
    extract_all_text_from_docx,
)

from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer

# Используем 2x увеличение для DOTS OCR
RENDER_SCALE = 2.0


def extract_headers_from_docx(docx_path: Path) -> List[Dict[str, Any]]:
    """
    Извлекает заголовки из DOCX с уровнями из стилей.
    
    Args:
        docx_path: Путь к DOCX файлу
    
    Returns:
        Список заголовков с уровнями
    """
    docx_paragraphs = extract_all_text_from_docx(docx_path)
    
    headers = []
    for idx, para in enumerate(docx_paragraphs):
        style = para.get("style", "")
        text = para.get("text", "").strip()
        
        if not text:
            continue
        
        # Проверяем, является ли параграф заголовком
        is_heading = False
        level = None
        
        if style.startswith("Heading"):
            # Heading 1, Heading 2, и т.д.
            try:
                level = int(style.split()[-1])
                is_heading = True
            except (ValueError, IndexError):
                pass
        elif style == "Title":
            # Title считается заголовком уровня 1
            level = 1
            is_heading = True
        
        if is_heading and level:
            headers.append({
                "text": text,
                "level": level,
                "style": style,
                "paragraph_index": idx,
                "formatting": para.get("formatting", {}),
            })
    
    return headers


def normalize_text_for_matching(text: str) -> str:
    """
    Нормализует текст для сопоставления.
    
    Args:
        text: Исходный текст
    
    Returns:
        Нормализованный текст
    """
    # Убираем лишние пробелы, приводим к нижнему регистру
    text = re.sub(r'\s+', ' ', text.strip().lower())
    # Убираем знаки препинания на конце
    text = re.sub(r'[.,;:!?]+$', '', text)
    return text


def match_ocr_header_to_docx_header(
    ocr_text: str,
    docx_headers: List[Dict[str, Any]],
    threshold: float = 0.8
) -> Optional[Tuple[Dict[str, Any], float]]:
    """
    Сопоставляет заголовок из OCR с заголовком из DOCX по тексту.
    
    Args:
        ocr_text: Текст заголовка из OCR
        docx_headers: Список заголовков из DOCX
        threshold: Порог схожести (0-1)
    
    Returns:
        Кортеж (docx_header, similarity) или None
    """
    ocr_normalized = normalize_text_for_matching(ocr_text)
    
    best_match = None
    best_similarity = 0.0
    
    for docx_header in docx_headers:
        docx_text = docx_header.get("text", "")
        docx_normalized = normalize_text_for_matching(docx_text)
        
        # Простое сравнение: точное совпадение или вхождение
        if ocr_normalized == docx_normalized:
            return (docx_header, 1.0)
        
        # Проверяем, содержит ли один текст другой
        if ocr_normalized in docx_normalized or docx_normalized in ocr_normalized:
            similarity = min(len(ocr_normalized), len(docx_normalized)) / max(len(ocr_normalized), len(docx_normalized))
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = docx_header
        
        # Jaccard similarity по словам
        ocr_words = set(ocr_normalized.split())
        docx_words = set(docx_normalized.split())
        
        if ocr_words and docx_words:
            intersection = len(ocr_words & docx_words)
            union = len(ocr_words | docx_words)
            if union > 0:
                similarity = intersection / union
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = docx_header
    
    if best_match and best_similarity >= threshold:
        return (best_match, best_similarity)
    
    return None


def determine_header_level_from_numbering(text: str) -> Optional[int]:
    """
    Определяет уровень заголовка по нумерации.
    
    Args:
        text: Текст заголовка
    
    Returns:
        Уровень заголовка (1-6) или None
    """
    # Заголовки вида "1", "2", "3" -> HEADER_1
    if re.match(r'^\d+\s+[A-ZА-ЯЁ]', text):
        return 1
    # Заголовки вида "1.1", "1.2" -> HEADER_2
    if re.match(r'^\d+\.\d+\s+', text):
        return 2
    # Заголовки вида "1.1.1", "1.1.2" -> HEADER_3
    if re.match(r'^\d+\.\d+\.\d+\s+', text):
        return 3
    # Заголовки вида "1.1.1.1" -> HEADER_4
    if re.match(r'^\d+\.\d+\.\d+\.\d+\s+', text):
        return 4
    # Заголовки вида "1.1.1.1.1" -> HEADER_5
    if re.match(r'^\d+\.\d+\.\d+\.\d+\.\d+\s+', text):
        return 5
    
    return None


def determine_header_level_heuristic(
    text: str,
    previous_headers: List[Dict[str, Any]],
    bbox: Optional[List[float]] = None,
    page: Optional[fitz.Page] = None
) -> int:
    """
    Определяет уровень заголовка эвристически (если нет сопоставления с DOCX).
    
    Args:
        text: Текст заголовка
        previous_headers: Список предыдущих заголовков
        bbox: Координаты заголовка [x1, y1, x2, y2]
        page: Страница PDF для анализа размера шрифта
    
    Returns:
        Уровень заголовка (1-6)
    """
    # Приоритет 1: Нумерация
    level_from_numbering = determine_header_level_from_numbering(text)
    if level_from_numbering:
        return level_from_numbering
    
    # Приоритет 2: Размер шрифта (если доступен)
    if page and bbox:
        try:
            rect = fitz.Rect(bbox)
            words = page.get_text("words", clip=rect)
            if words:
                # Берем средний размер шрифта
                font_sizes = [w[4] for w in words if len(w) > 4]  # w[4] - размер шрифта
                if font_sizes:
                    current_size = sum(font_sizes) / len(font_sizes)
                    
                    # Сравниваем с предыдущими заголовками
                    for header in reversed(previous_headers):
                        header_bbox = header.get("bbox")
                        if header_bbox and page:
                            try:
                                header_rect = fitz.Rect(header_bbox)
                                header_words = page.get_text("words", clip=header_rect)
                                if header_words:
                                    header_font_sizes = [w[4] for w in header_words if len(w) > 4]
                                    if header_font_sizes:
                                        header_size = sum(header_font_sizes) / len(header_font_sizes)
                                        header_level = header.get("level", 1)
                                        
                                        if current_size >= header_size + 2:
                                            return max(1, header_level - 1)
                                        elif current_size <= header_size - 2:
                                            return min(6, header_level + 1)
                                        else:
                                            return header_level
                            except Exception:
                                pass
        except Exception:
            pass
    
    # Приоритет 3: Позиция слева (левее = выше уровень)
    if bbox and previous_headers:
        x1 = bbox[0]
        for header in reversed(previous_headers):
            header_bbox = header.get("bbox")
            if header_bbox:
                header_x1 = header_bbox[0]
                header_level = header.get("level", 1)
                
                # Если текущий заголовок левее предыдущего, уровень выше
                if x1 < header_x1 - 20:  # Значительное смещение влево
                    return max(1, header_level - 1)
                # Если текущий заголовок правее предыдущего, уровень ниже
                elif x1 > header_x1 + 20:
                    return min(6, header_level + 1)
    
    # По умолчанию: следующий уровень после последнего
    if previous_headers:
        last_level = previous_headers[-1].get("level", 1)
        return min(6, last_level + 1)
    
    return 1


def process_header_structure_pipeline(
    docx_path: Path,
    output_dir: Path,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Основная функция пайплайна сохранения структуры заголовков.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        limit: Ограничение на количество обрабатываемых страниц
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*80}")
    print(f"Пайплайн сохранения структуры заголовков из DOTS OCR")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    headers_dir = output_dir / "headers"
    headers_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Извлекаем заголовки из DOCX с уровнями
    print("Шаг 1: Извлечение заголовков из DOCX с уровнями...")
    docx_headers = extract_headers_from_docx(docx_path)
    print(f"  ✓ Найдено заголовков в DOCX: {len(docx_headers)}")
    
    # Показываем примеры
    if docx_headers:
        print(f"  Примеры заголовков:")
        for i, header in enumerate(docx_headers[:5]):
            print(f"    {i+1}. [{header['level']}] {header['text'][:60]}...")
    
    # Шаг 2: Конвертируем DOCX в PDF
    print("\nШаг 2: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        return {"error": str(e)}
    
    # Шаг 3: Layout detection через DOTS OCR
    print("\nШаг 3: Layout detection через DOTS OCR...")
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_doc)
    if limit:
        total_pages = min(total_pages, limit)
    
    ocr_headers = []
    previous_headers = []  # Для определения уровней эвристически
    
    for page_num in range(total_pages):
        print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        # Рендерим страницу
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            continue
        
        page = pdf_doc[page_num]
        
        # Layout detection
        try:
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image
            )
            
            if success and layout_cells:
                for element in layout_cells:
                    category = element.get("category", "")
                    
                    # Обрабатываем заголовки
                    if category in ["Section-header", "Title"]:
                        bbox = element.get("bbox", [])
                        
                        # Извлекаем текст заголовка из PDF
                        try:
                            if bbox:
                                rect = fitz.Rect(bbox)
                                text = page.get_text("text", clip=rect).strip()
                            else:
                                text = ""
                        except Exception:
                            text = ""
                        
                        if not text:
                            continue
                        
                        # Пытаемся сопоставить с заголовком из DOCX
                        match_result = match_ocr_header_to_docx_header(text, docx_headers)
                        docx_header = None
                        
                        if match_result:
                            docx_header, similarity = match_result
                            level = docx_header.get("level", 1)
                            match_method = "docx_match"
                            print(f"    ✓ Заголовок сопоставлен: [{level}] {text[:50]}... (similarity: {similarity:.2%})")
                        else:
                            # Используем эвристики
                            level = determine_header_level_heuristic(
                                text, previous_headers, bbox, page
                            )
                            match_method = "heuristic"
                            print(f"    ⚠ Заголовок определен эвристически: [{level}] {text[:50]}...")
                        
                        header_info = {
                            "text": text,
                            "level": level,
                            "category": category,
                            "bbox": bbox,
                            "page_num": page_num,
                            "match_method": match_method,
                            "docx_header": docx_header,
                        }
                        
                        ocr_headers.append(header_info)
                        previous_headers.append(header_info)
        
        except Exception as e:
            print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    pdf_doc.close()
    
    print(f"\n  ✓ Найдено заголовков в OCR: {len(ocr_headers)}")
    
    # Шаг 4: Сохраняем результаты
    print("\nШаг 4: Сохранение результатов...")
    
    # Сохраняем структуру заголовков
    headers_structure = {
        "docx_headers_count": len(docx_headers),
        "ocr_headers_count": len(ocr_headers),
        "headers": ocr_headers,
    }
    
    headers_json_path = headers_dir / "headers_structure.json"
    with open(headers_json_path, "w", encoding="utf-8") as f:
        json.dump(headers_structure, f, ensure_ascii=False, indent=2)
    
    print(f"  ✓ Структура заголовков сохранена: {headers_json_path}")
    
    # Создаем текстовый отчет
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("СТРУКТУРА ЗАГОЛОВКОВ ИЗ DOTS OCR")
    report_lines.append("=" * 80)
    report_lines.append(f"\nВсего заголовков в DOCX: {len(docx_headers)}")
    report_lines.append(f"Всего заголовков в OCR: {len(ocr_headers)}")
    report_lines.append("\n" + "=" * 80)
    report_lines.append("ЗАГОЛОВКИ ИЗ OCR (с уровнями):")
    report_lines.append("=" * 80 + "\n")
    
    for i, header in enumerate(ocr_headers, 1):
        level = header.get("level", 1)
        text = header.get("text", "")
        page_num = header.get("page_num", 0)
        match_method = header.get("match_method", "unknown")
        
        report_lines.append(f"{i}. [HEADER_{level}] (страница {page_num + 1}, метод: {match_method})")
        report_lines.append(f"   {text}")
        report_lines.append("")
    
    report_path = headers_dir / "headers_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    
    print(f"  ✓ Отчет сохранен: {report_path}")
    
    # Статистика
    match_methods = {}
    for header in ocr_headers:
        method = header.get("match_method", "unknown")
        match_methods[method] = match_methods.get(method, 0) + 1
    
    print(f"\n  Статистика:")
    print(f"    Сопоставлено с DOCX: {match_methods.get('docx_match', 0)}")
    print(f"    Определено эвристически: {match_methods.get('heuristic', 0)}")
    
    # Распределение по уровням
    level_distribution = {}
    for header in ocr_headers:
        level = header.get("level", 1)
        level_distribution[level] = level_distribution.get(level, 0) + 1
    
    print(f"    Распределение по уровням:")
    for level in sorted(level_distribution.keys()):
        count = level_distribution[level]
        print(f"      HEADER_{level}: {count}")
    
    return {
        "docx_headers_count": len(docx_headers),
        "ocr_headers_count": len(ocr_headers),
        "match_methods": match_methods,
        "level_distribution": level_distribution,
        "headers_json_path": str(headers_json_path),
        "report_path": str(report_path),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python docx_header_structure_pipeline.py <docx_path> [output_dir] [limit]")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    if len(sys.argv) >= 3:
        output_dir = Path(sys.argv[2])
    else:
        output_dir = Path(__file__).parent / "results" / "header_structure" / docx_path.stem
    
    limit = None
    if len(sys.argv) >= 4:
        limit = int(sys.argv[3])
    
    result = process_header_structure_pipeline(docx_path, output_dir, limit)
    
    if "error" in result:
        print(f"\n✗ Ошибка: {result['error']}")
        sys.exit(1)
    
    print(f"\n✓ Пайплайн завершен успешно!")
    print(f"  Заголовков в DOCX: {result['docx_headers_count']}")
    print(f"  Заголовков в OCR: {result['ocr_headers_count']}")
