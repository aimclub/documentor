"""
Тестовый скрипт для запуска PDF parser из documentor на сканированных PDF файлах.

Обрабатывает все PDF файлы из experiments/pdf_text_extraction/test_files/ и сохраняет результаты.
Использует OCR через Qwen2.5 для извлечения текста из сканированных документов.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from tqdm import tqdm
from PIL import Image, ImageDraw, ImageFont
import base64
from io import BytesIO
import fitz
from collections import defaultdict

# Добавляем путь к корню проекта в sys.path если нужно
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Импортируем напрямую из модулей
from documentor.domain.models import ParsedDocument, ElementType
from documentor.processing.parsers.pdf.pdf_parser import PdfParser


def _base64_to_image(base64_str: str) -> Optional[Image.Image]:
    """Конвертирует base64 строку в PIL Image."""
    try:
        if base64_str.startswith("data:image"):
            base64_str = base64_str.split(",")[1]
        img_data = base64.b64decode(base64_str)
        return Image.open(BytesIO(img_data))
    except Exception as e:
        print(f"Ошибка при декодировании base64 изображения: {e}")
        return None


def _get_element_color(element_type: str) -> str:
    """Возвращает цвет для типа элемента."""
    color_map = {
        "TEXT": "green",
        "IMAGE": "magenta",
        "CAPTION": "orange",
        "HEADER_1": "cyan",
        "HEADER_2": "cyan",
        "HEADER_3": "cyan",
        "HEADER_4": "cyan",
        "HEADER_5": "cyan",
        "HEADER_6": "cyan",
        "TITLE": "red",
        "TABLE": "pink",
        "FORMULA": "gray",
        "LIST_ITEM": "blue",
        "PAGE_HEADER": "green",
        "PAGE_FOOTER": "purple",
    }
    return color_map.get(element_type, "red")


def _draw_bbox_on_image(image: Image.Image, bbox: List[float], label: str = "", color: str = "red") -> Image.Image:
    """
    Рисует bbox на изображении.
    
    Примечание: изображение уже обрезано по bbox, поэтому рисуем рамку по краям.
    """
    img_copy = image.copy()
    draw = ImageDraw.Draw(img_copy)
    
    width, height = img_copy.size
    
    # Рисуем рамку по краям изображения (так как изображение уже обрезано)
    draw.rectangle([0, 0, width - 1, height - 1], outline=color, width=3)
    
    # Добавляем подпись, если есть
    if label:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 16)
            except:
                font = ImageFont.load_default()
        
        # Фон для текста
        text_bbox = draw.textbbox((5, 5), label, font=font)
        # Расширяем bbox для фона
        text_bbox = (text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 2, text_bbox[3] + 2)
        draw.rectangle(text_bbox, fill=color)
        draw.text((5, 5), label, fill="white", font=font)
    
    return img_copy


def _draw_bbox_on_full_page(image: Image.Image, bbox: List[float], label: str = "", color: str = "red") -> Image.Image:
    """Рисует bbox на полной странице."""
    img_copy = image.copy()
    draw = ImageDraw.Draw(img_copy)
    
    if len(bbox) >= 4:
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        
        # Рисуем прямоугольник
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        
        # Добавляем подпись, если есть
        if label:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", 12)
                except:
                    font = ImageFont.load_default()
            
            # Фон для текста
            text_bbox = draw.textbbox((x1, y1 - 15), label, font=font)
            text_bbox = (text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 2, text_bbox[3] + 2)
            draw.rectangle(text_bbox, fill=color)
            draw.text((x1, y1 - 15), label, fill="white", font=font)
    
    return img_copy


def _save_full_pages_with_layout(
    pdf_path: Path,
    parsed_doc: ParsedDocument,
    output_dir: Path,
    render_scale: float = 2.0,
) -> int:
    """
    Сохраняет полные сканы страниц с нарисованными bbox для всех элементов layout.
    
    Args:
        pdf_path: Путь к PDF файлу
        parsed_doc: Распарсенный документ
        output_dir: Директория для сохранения
        render_scale: Масштаб рендеринга (должен совпадать с тем, что используется в парсере)
    
    Returns:
        Количество сохраненных страниц
    """
    pages_dir = output_dir / "pages_with_layout"
    pages_dir.mkdir(exist_ok=True)
    
    # Группируем элементы по страницам
    elements_by_page: Dict[int, List[Any]] = defaultdict(list)
    for element in parsed_doc.elements:
        page_num = element.metadata.get("page_num", 0)
        if "bbox" in element.metadata and len(element.metadata["bbox"]) >= 4:
            elements_by_page[page_num].append(element)
    
    if not elements_by_page:
        return 0
    
    # Рендерим каждую страницу и рисуем bbox
    pdf_document = fitz.open(str(pdf_path))
    saved_count = 0
    
    try:
        for page_num in tqdm(sorted(elements_by_page.keys()), desc="Сохранение страниц с layout", unit="страница", leave=False):
            if page_num >= len(pdf_document):
                continue
            
            try:
                # Рендерим страницу
                page = pdf_document.load_page(page_num)
                mat = fitz.Matrix(render_scale, render_scale)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("ppm")
                page_image = Image.open(BytesIO(img_data)).convert("RGB")
                
                # Рисуем bbox для всех элементов на странице
                for element in elements_by_page[page_num]:
                    element_type_name = element.type.name if hasattr(element.type, "name") else str(element.type)
                    bbox = element.metadata.get("bbox", [])
                    color = _get_element_color(element_type_name)
                    label = f"{element_type_name} {element.id}"
                    
                    page_image = _draw_bbox_on_full_page(page_image, bbox, label, color)
                
                # Сохраняем страницу
                page_file = pages_dir / f"page_{page_num + 1}_with_layout.png"
                page_image.save(page_file, "PNG")
                saved_count += 1
                
            except Exception as e:
                print(f"Ошибка при сохранении страницы {page_num + 1}: {e}")
                continue
    
    finally:
        pdf_document.close()
    
    return saved_count


def process_pdf_file(pdf_path: Path, parser: PdfParser, output_dir: Path) -> Dict[str, Any]:
    """
    Обрабатывает один сканированный PDF файл.
    
    Args:
        pdf_path: Путь к PDF файлу
        parser: Экземпляр PdfParser
        output_dir: Директория для сохранения результатов
    
    Returns:
        Словарь с результатами обработки
    """
    print(f"\n{'='*80}")
    print(f"Обработка сканированного PDF: {pdf_path.name}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        # Создаем LangChain Document
        document = Document(
            page_content="",
            metadata={"source": str(pdf_path.absolute())}
        )
        
        # Парсим PDF (автоматически определит, что текст не выделяется, и использует OCR)
        parsed_doc: ParsedDocument = parser.parse(document)
        
        processing_time = time.time() - start_time
        
        # Создаем директорию для результатов
        pdf_output_dir = output_dir / pdf_path.stem
        pdf_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем метаданные
        metadata_file = pdf_output_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(parsed_doc.metadata, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем структуру документа
        structure_file = pdf_output_dir / "structure.json"
        structure = {
            "source": parsed_doc.source,
            "format": parsed_doc.format.value if hasattr(parsed_doc.format, "value") else str(parsed_doc.format),
            "total_elements": len(parsed_doc.elements),
            "processing_method": "OCR (scanned PDF)",
            "elements": []
        }
        
        for element in tqdm(parsed_doc.elements, desc="Обработка элементов", unit="элемент", leave=False):
            element_type_name = element.type.name if hasattr(element.type, "name") else str(element.type)
            
            elem_data = {
                "id": element.id,
                "type": element_type_name,
                "content_preview": element.content[:200] + "..." if len(element.content) > 200 else element.content,
                "content_length": len(element.content),
                "parent_id": element.parent_id,
                "metadata_keys": list(element.metadata.keys()),
            }
            
            # Добавляем важные метаданные в зависимости от типа элемента
            if "bbox" in element.metadata:
                elem_data["bbox"] = element.metadata["bbox"]
            if "page_num" in element.metadata:
                elem_data["page_num"] = element.metadata["page_num"]
            if "category" in element.metadata:
                elem_data["category"] = element.metadata["category"]
            
            # Для заголовков добавляем уровень
            if element_type_name.startswith("HEADER") or element_type_name == "TITLE":
                if "level" in element.metadata:
                    elem_data["level"] = element.metadata["level"]
            
            # Для таблиц добавляем информацию о DataFrame и изображении
            if element_type_name == "TABLE":
                has_dataframe = "dataframe" in element.metadata
                has_image = "image_data" in element.metadata
                elem_data["has_dataframe"] = has_dataframe
                elem_data["has_image"] = has_image
                if has_dataframe:
                    df = element.metadata["dataframe"]
                    if df is not None:
                        elem_data["dataframe_shape"] = f"{df.shape[0]}x{df.shape[1]}"
                        elem_data["dataframe_columns"] = list(df.columns) if hasattr(df, "columns") else []
                if "parsing_method" in element.metadata:
                    elem_data["parsing_method"] = element.metadata["parsing_method"]
                if "merged_tables" in element.metadata:
                    elem_data["merged_tables"] = element.metadata["merged_tables"]
                if "table_count" in element.metadata:
                    elem_data["table_count"] = element.metadata["table_count"]
            
            # Для изображений добавляем информацию о caption
            if element_type_name == "IMAGE":
                has_image = "image_data" in element.metadata
                elem_data["has_image"] = has_image
                if "caption" in element.metadata:
                    elem_data["caption"] = element.metadata["caption"]
            
            # Для Caption добавляем информацию об изображении
            if element_type_name == "CAPTION":
                has_image = "image_data" in element.metadata
                elem_data["has_image"] = has_image
            
            structure["elements"].append(elem_data)
        
        with open(structure_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем полный текст документа
        full_text_file = pdf_output_dir / "full_text.txt"
        with open(full_text_file, "w", encoding="utf-8") as f:
            f.write("# Полный текст документа (извлечен через OCR)\n\n")
            for element in parsed_doc.elements:
                if element.content:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"ID: {element.id}\n")
                    f.write(f"Type: {element.type.name if hasattr(element.type, 'name') else element.type}\n")
                    f.write(f"Parent: {element.parent_id}\n")
                    f.write(f"{'='*80}\n")
                    f.write(element.content)
                    f.write("\n")
        
        # Сохраняем таблицы отдельно
        tables = parsed_doc.get_tables()
        if tables:
            tables_dir = pdf_output_dir / "tables"
            tables_dir.mkdir(exist_ok=True)
            
            for i, table in enumerate(tqdm(tables, desc="Сохранение таблиц", unit="таблица", leave=False), start=1):
                table_file = tables_dir / f"table_{i}.md"
                with open(table_file, "w", encoding="utf-8") as f:
                    f.write(f"# Table {i}\n\n")
                    f.write(f"ID: {table.id}\n")
                    f.write(f"Page: {table.metadata.get('page_num', 'N/A')}\n")
                    f.write(f"BBox: {table.metadata.get('bbox', [])}\n")
                    f.write(f"Parsing Method: {table.metadata.get('parsing_method', 'N/A')}\n\n")
                    f.write("## Markdown Table\n\n")
                    f.write(table.content)
                    f.write("\n\n")
                    
                    # Информация о DataFrame
                    if "dataframe" in table.metadata:
                        df = table.metadata["dataframe"]
                        if df is not None:
                            f.write("## DataFrame Info\n\n")
                            f.write(f"Shape: {df.shape}\n")
                            f.write(f"Columns: {list(df.columns)}\n\n")
                            f.write("### DataFrame Preview\n\n")
                            f.write(df.head(10).to_markdown())
                            f.write("\n")
        
        # Сохраняем изображения с bbox
        images_dir = pdf_output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        
        image_count = 0
        for element in tqdm(parsed_doc.elements, desc="Сохранение изображений", unit="изображение", leave=False):
            element_type_name = element.type.name if hasattr(element.type, "name") else str(element.type)
            
            # Проверяем, есть ли изображение в метаданных (для CAPTION или IMAGE или TABLE)
            image_data = None
            bbox = None
            
            if element_type_name == "CAPTION" and "image_data" in element.metadata:
                image_data = element.metadata["image_data"]
                bbox = element.metadata.get("bbox", [])
            elif element_type_name == "IMAGE" and "image_data" in element.metadata:
                image_data = element.metadata["image_data"]
                bbox = element.metadata.get("bbox", [])
            elif element_type_name == "TABLE" and "image_data" in element.metadata:
                image_data = element.metadata["image_data"]
                bbox = element.metadata.get("bbox", [])
            
            if image_data:
                image_count += 1
                img = _base64_to_image(image_data)
                if img:
                    # Рисуем bbox на изображении
                    label = f"{element_type_name} {element.id}"
                    color = _get_element_color(element_type_name)
                    img_with_bbox = _draw_bbox_on_image(img, bbox, label, color)
                    
                    # Сохраняем изображение
                    image_file = images_dir / f"image_{image_count}_{element.id}.png"
                    img_with_bbox.save(image_file, "PNG")
        
        # Сохраняем полные сканы страниц с layout и bbox
        render_scale = 2.0  # Должно совпадать с настройкой в парсере
        saved_pages = _save_full_pages_with_layout(
            pdf_path,
            parsed_doc,
            pdf_output_dir,
            render_scale=render_scale,
        )
        
        # Статистика
        stats = {
            "processing_time_seconds": processing_time,
            "total_elements": len(parsed_doc.elements),
            "headers": len([e for e in parsed_doc.elements if e.type.name.startswith("HEADER")]),
            "text_blocks": len([e for e in parsed_doc.elements if e.type.name == "TEXT"]),
            "tables": len(tables),
            "images": len([e for e in parsed_doc.elements if e.type.name == "IMAGE"]),
            "captions": len([e for e in parsed_doc.elements if e.type.name == "CAPTION"]),
            "saved_images": image_count,
            "saved_pages_with_layout": saved_pages,
            "processing_method": "OCR (scanned PDF)",
        }
        
        stats_file = pdf_output_dir / "stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Успешно обработан за {processing_time:.2f} сек")
        print(f"  Элементов: {stats['total_elements']}")
        print(f"  Заголовков: {stats['headers']}")
        print(f"  Текстовых блоков: {stats['text_blocks']}")
        print(f"  Таблиц: {stats['tables']}")
        print(f"  Изображений: {stats['images']}")
        print(f"  Результаты сохранены в: {pdf_output_dir}")
        
        return {
            "success": True,
            "processing_time": processing_time,
            "stats": stats,
            "output_dir": str(pdf_output_dir),
        }
    
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Ошибка при обработке {pdf_path.name}: {e}"
        print(f"✗ {error_msg}")
        import traceback
        traceback.print_exc()
        
        return {
            "success": False,
            "processing_time": processing_time,
            "error": str(e),
        }


def main():
    """Основная функция."""
    # Пути относительно корня проекта
    project_root = Path(__file__).resolve().parents[2]
    test_files_dir = project_root / "experiments" / "pdf_text_extraction" / "test_files"
    output_dir = project_root / "experiments" / "pdf_text_extraction" / "results" / "scanned_pdf_parser"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Находим все PDF файлы (можно фильтровать по имени, например только scanned_*.pdf)
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    # Фильтруем только сканированные PDF (по имени файла)
    scanned_pdf_files = [f for f in pdf_files if "scanned" in f.name.lower()]
    
    if not scanned_pdf_files:
        print(f"Не найдено сканированных PDF файлов в {test_files_dir}")
        print(f"Ищем файлы с 'scanned' в имени")
        return
    
    print(f"Найдено сканированных PDF файлов: {len(scanned_pdf_files)}")
    print(f"Выходная директория: {output_dir}")
    
    # Создаем парсер
    print("\nИнициализация PdfParser...")
    parser = PdfParser()
    print("✓ PdfParser инициализирован")
    print("  Парсер автоматически определит сканированные PDF и использует OCR")
    
    # Обрабатываем каждый файл
    results: List[Dict[str, Any]] = []
    total_start_time = time.time()
    
    for pdf_file in tqdm(scanned_pdf_files, desc="Обработка сканированных PDF", unit="файл"):
        result = process_pdf_file(pdf_file, parser, output_dir)
        results.append({
            "file": pdf_file.name,
            **result
        })
    
    total_time = time.time() - total_start_time
    
    # Сохраняем общую статистику
    summary = {
        "total_files": len(scanned_pdf_files),
        "successful": len([r for r in results if r.get("success", False)]),
        "failed": len([r for r in results if not r.get("success", False)]),
        "total_processing_time_seconds": total_time,
        "average_processing_time_seconds": total_time / len(scanned_pdf_files) if scanned_pdf_files else 0,
        "processing_method": "OCR (scanned PDF)",
        "results": results,
    }
    
    summary_file = output_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    
    # Выводим итоги
    print(f"\n{'='*80}")
    print("ИТОГИ ОБРАБОТКИ СКАНИРОВАННЫХ PDF")
    print(f"{'='*80}")
    print(f"Всего файлов: {summary['total_files']}")
    print(f"Успешно: {summary['successful']}")
    print(f"Ошибок: {summary['failed']}")
    print(f"Общее время: {total_time:.2f} сек")
    print(f"Среднее время на файл: {summary['average_processing_time_seconds']:.2f} сек")
    print(f"Метод обработки: {summary['processing_method']}")
    print(f"\nДетальная статистика сохранена в: {summary_file}")
    
    if summary['failed'] > 0:
        print("\nФайлы с ошибками:")
        for result in results:
            if not result.get("success", False):
                print(f"  - {result['file']}: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
