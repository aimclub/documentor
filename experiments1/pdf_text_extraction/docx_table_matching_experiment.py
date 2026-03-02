"""
Эксперимент по сопоставлению таблиц из DOTS OCR с таблицами из DOCX.

Процесс:
1. Извлекаем таблицы из DOCX через DOTS OCR (layout detection)
2. Для каждой найденной таблицы:
   - Вырезаем изображение таблицы из PDF
   - Преобразуем в markdown через Qwen
   - Находим похожую таблицу в DOCX XML
   - Сохраняем результаты сравнения
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO

from PIL import Image

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Импорты из docx_hybrid_pipeline
from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
    extract_tables_from_docx_xml,
    extract_image_from_pdf_by_bbox,
)

# Используем 2x увеличение для DOTS OCR (как просил пользователь)
RENDER_SCALE = 2.0  # Увеличение в 2 раза для DOTS OCR

# Импорты из documentor
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer
from documentor.processing.parsers.pdf.ocr.qwen_table_parser import parse_table_with_qwen
from documentor.utils.ocr_image_utils import fetch_image

# Проверка зависимостей
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("Ошибка: PyMuPDF не установлен")

try:
    from docx import Document as PythonDocxDocument
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False
    print("Ошибка: python-docx не установлен")


def docx_table_to_markdown(docx_table: Dict[str, Any]) -> str:
    """
    Преобразует таблицу из DOCX в markdown формат.
    
    Args:
        docx_table: Таблица из DOCX (результат extract_tables_from_docx_xml)
    
    Returns:
        Markdown строка с таблицей
    """
    if "data" not in docx_table:
        return ""
    
    markdown_lines = []
    data = docx_table["data"]
    
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


def normalize_markdown_table(markdown: str) -> str:
    """
    Нормализует markdown таблицу для сравнения.
    Удаляет лишние пробелы, приводит к нижнему регистру.
    """
    if not markdown:
        return ""
    
    lines = [line.strip() for line in markdown.split("\n") if line.strip()]
    # Удаляем разделитель (строку с |---|---|)
    filtered_lines = []
    for line in lines:
        if not (line.startswith("|") and all(c in "-|: " for c in line)):
            filtered_lines.append(line.lower())
    
    return "\n".join(filtered_lines)


def compare_markdown_tables(markdown1: str, markdown2: str) -> Dict[str, Any]:
    """
    Сравнивает две markdown таблицы и возвращает метрики схожести.
    
    Args:
        markdown1: Первая markdown таблица
        markdown2: Вторая markdown таблица
    
    Returns:
        Словарь с метриками сравнения
    """
    norm1 = normalize_markdown_table(markdown1)
    norm2 = normalize_markdown_table(markdown2)
    
    if not norm1 and not norm2:
        return {
            "similarity": 1.0,
            "method": "both_empty",
            "details": "Обе таблицы пустые"
        }
    
    if not norm1 or not norm2:
        return {
            "similarity": 0.0,
            "method": "one_empty",
            "details": "Одна таблица пустая"
        }
    
    # Простое сравнение строк
    lines1 = set(norm1.split("\n"))
    lines2 = set(norm2.split("\n"))
    
    intersection = len(lines1 & lines2)
    union = len(lines1 | lines2)
    
    jaccard_similarity = intersection / union if union > 0 else 0.0
    
    # Сравнение по словам
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    word_intersection = len(words1 & words2)
    word_union = len(words1 | words2)
    
    word_similarity = word_intersection / word_union if word_union > 0 else 0.0
    
    # Комбинированная метрика
    combined_similarity = (jaccard_similarity * 0.4 + word_similarity * 0.6)
    
    return {
        "similarity": combined_similarity,
        "jaccard_similarity": jaccard_similarity,
        "word_similarity": word_similarity,
        "method": "markdown_comparison",
        "details": {
            "lines1_count": len(lines1),
            "lines2_count": len(lines2),
            "common_lines": intersection,
            "words1_count": len(words1),
            "words2_count": len(words2),
            "common_words": word_intersection,
        }
    }


def find_similar_table_in_docx(
    ocr_markdown: str,
    docx_tables: List[Dict[str, Any]],
    threshold: float = 0.3
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Находит похожую таблицу в DOCX по markdown из OCR.
    
    Args:
        ocr_markdown: Markdown таблица из OCR (Qwen)
        docx_tables: Список таблиц из DOCX
        threshold: Минимальный порог схожести
    
    Returns:
        Кортеж (docx_table, comparison_metrics) или None
    """
    if not ocr_markdown or not docx_tables:
        return None
    
    best_match = None
    best_similarity = 0.0
    best_metrics = None
    
    for docx_table in docx_tables:
        docx_markdown = docx_table_to_markdown(docx_table)
        metrics = compare_markdown_tables(ocr_markdown, docx_markdown)
        
        similarity = metrics.get("similarity", 0.0)
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = docx_table
            best_metrics = metrics
    
    if best_similarity >= threshold:
        return (best_match, best_metrics)
    
    return None


def process_table_experiment(
    docx_path: Path,
    output_dir: Path,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Основная функция эксперимента по сопоставлению таблиц.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        limit: Ограничение на количество обрабатываемых таблиц (None = все)
    
    Returns:
        Словарь с результатами эксперимента
    """
    print(f"\n{'='*80}")
    print(f"Эксперимент по сопоставлению таблиц")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    images_dir = output_dir / "table_images"
    images_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Конвертируем DOCX в PDF
    print("Шаг 1: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        return {"error": str(e)}
    
    # Шаг 2: Извлекаем таблицы из DOCX XML
    print("\nШаг 2: Извлечение таблиц из DOCX XML...")
    docx_tables = extract_tables_from_docx_xml(docx_path)
    print(f"  ✓ Найдено таблиц в DOCX: {len(docx_tables)}")
    
    # Шаг 3: Layout detection через DOTS OCR
    print("\nШаг 3: Layout detection через DOTS OCR...")
    if not HAS_PYMUPDF:
        print("  ✗ PyMuPDF не установлен")
        return {"error": "PyMuPDF не установлен"}
    
    # Открываем PDF только для определения количества страниц
    pdf_document = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_document)
    pdf_document.close()
    
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    ocr_table_elements = []
    
    for page_num in range(total_pages):
        print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        # Рендерим страницу (render_page сам открывает и закрывает файл)
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
    
    # Шаг 4: Обработка каждой таблицы из OCR
    print(f"\nШаг 4: Обработка таблиц из OCR (лимит: {limit or 'нет'})...")
    
    results = []
    processed_count = 0
    
    for table_idx, ocr_table in enumerate(ocr_table_elements):
        if limit and processed_count >= limit:
            break
        
        processed_count += 1
        print(f"\n  Таблица {processed_count}/{len(ocr_table_elements)}:")
        
        table_bbox = ocr_table.get("bbox", [])
        page_num = ocr_table.get("page_num", 0)
        
        if not table_bbox or len(table_bbox) != 4:
            print(f"    ✗ Некорректные координаты bbox")
            continue
        
        print(f"    BBox: {table_bbox}, Страница: {page_num + 1}")
        
        # 4.1: Извлекаем изображение таблицы из PDF
        try:
            page_image = renderer.render_page(temp_pdf_path, page_num)
            table_image = extract_image_from_pdf_by_bbox(
                temp_pdf_path,
                table_bbox,
                page_num,
                RENDER_SCALE,
                rendered_page_image=page_image
            )
            
            if table_image is None:
                print(f"    ✗ Не удалось извлечь изображение таблицы")
                continue
            
            # Сохраняем изображение
            table_image_path = images_dir / f"table_{table_idx + 1}_page_{page_num + 1}.png"
            table_image.save(table_image_path)
            print(f"    ✓ Изображение сохранено: {table_image_path.name}")
            
        except Exception as e:
            print(f"    ✗ Ошибка при извлечении изображения: {e}")
            continue
        
        # 4.2: Увеличиваем изображение в 2 раза перед отправкой в Qwen
        print(f"    Увеличение изображения в 2x для Qwen...")
        table_image_2x = table_image.resize(
            (table_image.width * 2, table_image.height * 2),
            Image.Resampling.LANCZOS
        )
        print(f"    ✓ Изображение увеличено: {table_image.width}x{table_image.height} → {table_image_2x.width}x{table_image_2x.height}")
        
        # 4.3: Преобразуем в markdown через Qwen (с увеличенным изображением)
        print(f"    Преобразование в markdown через Qwen...")
        ocr_markdown = ""
        try:
            ocr_markdown, ocr_dataframe, success = parse_table_with_qwen(
                table_image_2x,  # Используем увеличенное изображение
                method="markdown"
            )
            
            if not success:
                print(f"    ✗ Qwen вернул success=False")
                if ocr_markdown:
                    print(f"    Но markdown получен: {len(ocr_markdown)} символов")
                else:
                    print(f"    И markdown пустой")
                ocr_markdown = ocr_markdown or ""
            elif not ocr_markdown:
                print(f"    ✗ Qwen вернул success=True, но markdown пустой")
                ocr_markdown = ""
            else:
                print(f"    ✓ Markdown получен (длина: {len(ocr_markdown)} символов)")
                # Показываем первые 200 символов для отладки
                preview = ocr_markdown[:200].replace('\n', '\\n')
                print(f"    Предпросмотр: {preview}...")
                
        except Exception as e:
            print(f"    ✗ Ошибка при преобразовании через Qwen: {e}")
            import traceback
            print(f"    Детали: {traceback.format_exc()}")
            ocr_markdown = ""
        
        # 4.4: Ищем похожую таблицу в DOCX
        print(f"    Поиск похожей таблицы в DOCX...")
        match_result = find_similar_table_in_docx(ocr_markdown, docx_tables, threshold=0.3)
        
        if match_result:
            docx_table, comparison_metrics = match_result
            similarity = comparison_metrics.get("similarity", 0.0)
            print(f"    ✓ Найдено совпадение! Схожесть: {similarity:.2%}")
            
            docx_markdown = docx_table_to_markdown(docx_table)
            match_status = "matched"
        else:
            print(f"    ✗ Совпадение не найдено")
            docx_table = None
            docx_markdown = ""
            comparison_metrics = {"similarity": 0.0, "method": "no_match"}
            match_status = "not_found"
        
        # 4.5: Сохраняем результаты
        result = {
            "table_index": table_idx + 1,
            "page_num": page_num + 1,
            "bbox": table_bbox,
            "ocr_markdown": ocr_markdown,
            "ocr_image_size": f"{table_image.width}x{table_image.height}",
            "ocr_image_2x_size": f"{table_image_2x.width}x{table_image_2x.height}",
            "docx_table_index": docx_table.get("index") if docx_table else None,
            "docx_markdown": docx_markdown,
            "match_status": match_status,
            "similarity": comparison_metrics.get("similarity", 0.0),
            "comparison_metrics": comparison_metrics,
            "table_image_path": str(table_image_path.relative_to(output_dir)),
        }
        
        results.append(result)
        
        # Сохраняем детальный результат для каждой таблицы
        table_result_file = tables_dir / f"table_{table_idx + 1}_result.json"
        with open(table_result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"    ✓ Результат сохранен: {table_result_file.name}")
    
    # Шаг 5: Создаем итоговый отчет
    print(f"\nШаг 5: Создание итогового отчета...")
    
    summary = {
        "total_ocr_tables": len(ocr_table_elements),
        "total_docx_tables": len(docx_tables),
        "processed_tables": len(results),
        "matched_tables": sum(1 for r in results if r["match_status"] == "matched"),
        "not_found_tables": sum(1 for r in results if r["match_status"] == "not_found"),
        "average_similarity": sum(r["similarity"] for r in results) / len(results) if results else 0.0,
        "results": results,
    }
    
    summary_file = output_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"  ✓ Итоговый отчет сохранен: {summary_file}")
    
    # Выводим статистику
    print(f"\n{'='*80}")
    print(f"ИТОГОВАЯ СТАТИСТИКА:")
    print(f"  Таблиц найдено в OCR: {summary['total_ocr_tables']}")
    print(f"  Таблиц найдено в DOCX: {summary['total_docx_tables']}")
    print(f"  Обработано таблиц: {summary['processed_tables']}")
    print(f"  Совпадений найдено: {summary['matched_tables']}")
    print(f"  Совпадений не найдено: {summary['not_found_tables']}")
    print(f"  Средняя схожесть: {summary['average_similarity']:.2%}")
    print(f"{'='*80}\n")
    
    # Удаляем временный PDF
    if temp_pdf_path.exists():
        temp_pdf_path.unlink()
        print(f"  ✓ Временный PDF удален")
    
    return summary


def main():
    """Главная функция для запуска из командной строки."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Эксперимент по сопоставлению таблиц из DOTS OCR с таблицами из DOCX"
    )
    parser.add_argument(
        "docx_path",
        type=Path,
        help="Путь к DOCX файлу"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Выходная директория (по умолчанию: experiments/pdf_text_extraction/results/table_matching/<docx_name>)"
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Ограничение на количество обрабатываемых таблиц"
    )
    
    args = parser.parse_args()
    
    if not args.docx_path.exists():
        print(f"Ошибка: файл {args.docx_path} не существует")
        sys.exit(1)
    
    # Определяем выходную директорию
    if args.output:
        output_dir = args.output
    else:
        base_output = Path(__file__).parent / "results" / "table_matching"
        output_dir = base_output / args.docx_path.stem
    
    # Запускаем эксперимент
    result = process_table_experiment(
        args.docx_path,
        output_dir,
        limit=args.limit
    )
    
    if "error" in result:
        print(f"\nОшибка: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
