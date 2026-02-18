"""
Универсальный тестовый скрипт для запуска парсеров из documentor.

Поддерживает обработку:
- DOCX файлов (DocxParser)
- Обычных PDF файлов (PdfParser)
- Сканированных PDF файлов (PdfParser с OCR)

Обрабатывает документы и сохраняет результаты, включая визуализацию bbox.
"""

from __future__ import annotations

import json
import sys
import time
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

from langchain_core.documents import Document
from tqdm import tqdm
from PIL import Image, ImageDraw, ImageFont
import base64
from io import BytesIO
import fitz
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# Добавляем путь к корню проекта в sys.path если нужно
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Импортируем напрямую из модулей
from documentor.domain.models import ParsedDocument, ElementType
from documentor.processing.parsers.docx.docx_parser import DocxParser
from documentor.processing.parsers.pdf.pdf_parser import PdfParser
from documentor.processing.parsers.docx.converter import convert_docx_to_pdf


class DocumentType(Enum):
    """Тип документа для обработки."""
    DOCX = "docx"
    PDF_REGULAR = "pdf_regular"
    PDF_SCANNED = "pdf_scanned"


def _base64_to_image(base64_str: str) -> Optional[Image.Image]:
    """Конвертирует base64 строку в PIL Image."""
    try:
        if base64_str.startswith("data:image"):
            base64_str = base64_str.split(",")[1]
        img_data = base64.b64decode(base64_str)
        return Image.open(BytesIO(img_data))
    except Exception as e:
        logger.error(f"Ошибка при декодировании base64 изображения: {e}")
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
    source_path: Path,
    parsed_doc: ParsedDocument,
    output_dir: Path,
    render_scale: float = 2.0,
    is_docx: bool = False,
) -> int:
    """
    Сохраняет полные страницы с нарисованными bbox для всех элементов layout.
    
    Args:
        source_path: Путь к исходному файлу (DOCX или PDF)
        parsed_doc: Распарсенный документ
        output_dir: Директория для сохранения
        render_scale: Масштаб рендеринга
        is_docx: Если True, конвертирует DOCX в PDF для визуализации
    
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
    
    # Для DOCX конвертируем в PDF
    pdf_path = source_path
    temp_pdf_path = None
    
    if is_docx:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            temp_pdf_path = Path(tmp_pdf.name)
        
        try:
            convert_docx_to_pdf(source_path, temp_pdf_path)
            if not temp_pdf_path.exists():
                return 0
            pdf_path = temp_pdf_path
        except Exception as e:
            logger.error(f"Ошибка при конвертации DOCX в PDF: {e}")
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
                logger.error(f"Ошибка при сохранении страницы {page_num + 1}: {e}")
                continue
    
    finally:
        pdf_document.close()
        # Удаляем временный PDF файл для DOCX
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
            except:
                pass
    
    return saved_count


def process_document(
    file_path: Path,
    parser: Any,
    output_dir: Path,
    doc_type: DocumentType,
) -> Dict[str, Any]:
    """
    Обрабатывает один документ (DOCX или PDF).
    
    Args:
        file_path: Путь к файлу
        parser: Экземпляр парсера (DocxParser или PdfParser)
        output_dir: Директория для сохранения результатов
        doc_type: Тип документа
    
    Returns:
        Словарь с результатами обработки
    """
    doc_type_name = {
        DocumentType.DOCX: "DOCX",
        DocumentType.PDF_REGULAR: "PDF (обычный)",
        DocumentType.PDF_SCANNED: "PDF (сканированный)",
    }.get(doc_type, "Unknown")
    
    print(f"\n{'='*80}")
    print(f"Обработка {doc_type_name}: {file_path.name}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        # Создаем LangChain Document
        document = Document(
            page_content="",
            metadata={"source": str(file_path.absolute())}
        )
        
        # Парсим документ
        parsed_doc: ParsedDocument = parser.parse(document)
        
        processing_time = time.time() - start_time
        
        # Создаем директорию для результатов
        doc_output_dir = output_dir / file_path.stem
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем метаданные
        metadata_file = doc_output_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(parsed_doc.metadata, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем структуру документа
        structure_file = doc_output_dir / "structure.json"
        structure = {
            "source": parsed_doc.source,
            "format": parsed_doc.format.value if hasattr(parsed_doc.format, "value") else str(parsed_doc.format),
            "total_elements": len(parsed_doc.elements),
            "elements": []
        }
        
        for element in tqdm(parsed_doc.elements, desc="Обработка элементов", unit="элемент", leave=False):
            element_type_name = element.type.name if hasattr(element.type, "name") else str(element.type)
            
            # Очищаем текст для preview
            cleaned_content = element.content.replace("\n", " ").replace("\r", " ").strip()
            while "  " in cleaned_content:
                cleaned_content = cleaned_content.replace("  ", " ")
            
            elem_data = {
                "id": element.id,
                "type": element_type_name,
                "content_preview": cleaned_content[:200] + "..." if len(cleaned_content) > 200 else cleaned_content,
                "content_length": len(element.content),
                "parent_id": element.parent_id,
                "metadata_keys": list(element.metadata.keys()),
            }
            
            # Добавляем важные метаданные
            if "bbox" in element.metadata:
                elem_data["bbox"] = element.metadata["bbox"]
            if "page_num" in element.metadata:
                elem_data["page_num"] = element.metadata["page_num"]
            if "category" in element.metadata:
                elem_data["category"] = element.metadata["category"]
            if "xml_position" in element.metadata:
                elem_data["xml_position"] = element.metadata["xml_position"]
            
            # Для заголовков
            if element_type_name.startswith("HEADER") or element_type_name == "TITLE":
                if "level" in element.metadata:
                    elem_data["level"] = element.metadata["level"]
                if "from_toc" in element.metadata:
                    elem_data["from_toc"] = element.metadata["from_toc"]
                if "from_ocr" in element.metadata:
                    elem_data["from_ocr"] = element.metadata["from_ocr"]
            
            # Для таблиц
            if element_type_name == "TABLE":
                has_html = bool(element.content and element.content.strip())
                has_image = "image_data" in element.metadata
                elem_data["has_html"] = has_html
                elem_data["has_image"] = has_image
                if has_html:
                    elem_data["html_length"] = len(element.content)
                if "parsing_method" in element.metadata:
                    elem_data["parsing_method"] = element.metadata["parsing_method"]
                if "merged_tables" in element.metadata:
                    elem_data["merged_tables"] = element.metadata["merged_tables"]
                if "table_count" in element.metadata:
                    elem_data["table_count"] = element.metadata["table_count"]
            
            # Для изображений
            if element_type_name == "IMAGE":
                has_image = "image_data" in element.metadata
                
                # Проверяем связанный CAPTION
                if not has_image and element.parent_id:
                    caption_element = next(
                        (e for e in parsed_doc.elements if e.id == element.parent_id and e.type.name == "CAPTION"),
                        None
                    )
                    if caption_element and "image_data" in caption_element.metadata:
                        has_image = True
                        elem_data["image_data"] = caption_element.metadata["image_data"]
                
                elem_data["has_image"] = has_image
                if has_image and "image_data" not in elem_data:
                    elem_data["image_data"] = element.metadata["image_data"]
                if "caption" in element.metadata:
                    elem_data["caption"] = element.metadata["caption"]
            
            # Для CAPTION
            if element_type_name == "CAPTION":
                has_image = "image_data" in element.metadata
                elem_data["has_image"] = has_image
                if has_image:
                    image_data_value = element.metadata["image_data"]
                    if image_data_value:
                        elem_data["image_data"] = image_data_value
                        elem_data["image_data_size"] = len(image_data_value) if isinstance(image_data_value, str) else 0
            
            structure["elements"].append(elem_data)
        
        with open(structure_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем полный текст документа
        full_text_file = doc_output_dir / "full_text.txt"
        with open(full_text_file, "w", encoding="utf-8") as f:
            for element in parsed_doc.elements:
                if element.content:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"ID: {element.id}\n")
                    f.write(f"Type: {element.type.name if hasattr(element.type, 'name') else element.type}\n")
                    f.write(f"Parent: {element.parent_id}\n")
                    f.write(f"{'='*80}\n")
                    f.write(element.content)
                    f.write("\n")
        
        # Сохраняем таблицы
        tables = parsed_doc.get_tables()
        if tables:
            tables_dir = doc_output_dir / "tables"
            tables_dir.mkdir(exist_ok=True)
            
            for i, table in enumerate(tqdm(tables, desc="Сохранение таблиц", unit="таблица", leave=False), start=1):
                # Для DOCX используем markdown, для PDF - JSON
                if doc_type == DocumentType.DOCX:
                    table_file = tables_dir / f"table_{i}.md"
                    with open(table_file, "w", encoding="utf-8") as f:
                        f.write(f"# Table {i}\n\n")
                        f.write(f"ID: {table.id}\n")
                        f.write(f"Page: {table.metadata.get('page_num', 'N/A')}\n")
                        f.write(f"BBox: {table.metadata.get('bbox', [])}\n\n")
                        f.write("## HTML Table\n\n")
                        f.write(table.content if table.content else "(empty)")
                        f.write("\n\n")
                else:
                    table_file = tables_dir / f"table_{i}.json"
                    with open(table_file, "w", encoding="utf-8") as f:
                        table_data = {
                            "id": table.id,
                            "page": table.metadata.get("page_num", "N/A"),
                            "bbox": table.metadata.get("bbox", []),
                            "html": table.content if table.content else "",
                            "html_length": len(table.content) if table.content else 0,
                        }
                        
                        json.dump(table_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем изображения
        # Images are stored only in base64 format in metadata, no local file saving
        
        # Сохраняем полные страницы с layout
        render_scale = 2.0
        saved_pages = _save_full_pages_with_layout(
            file_path,
            parsed_doc,
            doc_output_dir,
            render_scale=render_scale,
            is_docx=(doc_type == DocumentType.DOCX),
        )
        
        # Статистика
        processing_method = {
            DocumentType.DOCX: "DOCX (Dots OCR + XML + TOC parsing)",
            DocumentType.PDF_REGULAR: "PDF (OCR layout + PyMuPDF text)",
            DocumentType.PDF_SCANNED: "PDF (OCR full extraction)",
        }.get(doc_type, "Unknown")
        
        stats = {
            "processing_time_seconds": processing_time,
            "total_elements": len(parsed_doc.elements),
            "headers": len([e for e in parsed_doc.elements if e.type.name.startswith("HEADER")]),
            "text_blocks": len([e for e in parsed_doc.elements if e.type.name == "TEXT"]),
            "tables": len(tables),
            "images": len([e for e in parsed_doc.elements if e.type.name == "IMAGE"]),
            "captions": len([e for e in parsed_doc.elements if e.type.name == "CAPTION"]),
            "saved_pages_with_layout": saved_pages,
            "processing_method": processing_method,
        }
        
        stats_file = doc_output_dir / "stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        print(f"Успешно обработан за {processing_time:.2f} сек")
        print(f"  Метод обработки: {stats['processing_method']}")
        print(f"  Элементов: {stats['total_elements']}")
        print(f"  Заголовков: {stats['headers']}")
        print(f"  Текстовых блоков: {stats['text_blocks']}")
        print(f"  Таблиц: {stats['tables']}")
        print(f"  Изображений: {stats['images']}")
        print(f"  Результаты сохранены в: {doc_output_dir}")
        
        return {
            "success": True,
            "processing_time": processing_time,
            "stats": stats,
            "output_dir": str(doc_output_dir),
        }
    
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Ошибка при обработке {file_path.name}: {e}"
        print(f"Ошибка: {error_msg}")
        import traceback
        traceback.print_exc()
        
        return {
            "success": False,
            "processing_time": processing_time,
            "error": str(e),
        }


def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Тестирование парсеров documentor")
    parser.add_argument(
        "--type",
        type=str,
        choices=["docx", "pdf", "pdf_scanned"],
        default="docx",
        help="Тип документа для обработки (docx, pdf, pdf_scanned)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Путь к файлу для обработки"
    )
    parser.add_argument(
        "--folder",
        type=str,
        help="Путь к папке с файлами для обработки"
    )
    
    args = parser.parse_args()
    
    # Определяем тип документа
    if args.type == "docx":
        doc_type = DocumentType.DOCX
        parser_class = DocxParser
        default_folder = Path("E:/easy/documentor/documentor_langchain/experiments/pdf_text_extraction/test_folder")
        default_file = None
        file_ext = ".docx"
    elif args.type == "pdf_scanned":
        doc_type = DocumentType.PDF_SCANNED
        parser_class = PdfParser
        default_folder = None
        default_file = Path("E:/easy/documentor/documentor_langchain/experiments/pdf_text_extraction/test_files/2507.06920v1.pdf")
        file_ext = ".pdf"
    else:  # pdf
        doc_type = DocumentType.PDF_REGULAR
        parser_class = PdfParser
        default_folder = None
        default_file = Path("E:/easy/documentor/documentor_langchain/experiments/pdf_text_extraction/test_files/2507.06920v1.pdf")
        file_ext = ".pdf"
    
    # Определяем файлы для обработки
    files_to_process = []
    
    if args.file:
        file_path = Path(args.file)
        if file_path.exists():
            files_to_process = [file_path]
        else:
            print(f"Файл не найден: {file_path}")
            return
    elif args.folder:
        folder_path = Path(args.folder)
        if folder_path.exists():
            files_to_process = list(folder_path.glob(f"*{file_ext}"))
        else:
            print(f"Папка не найдена: {folder_path}")
            return
    else:
        # Используем значения по умолчанию
        if default_file and default_file.exists():
            files_to_process = [default_file]
        elif default_folder and default_folder.exists():
            files_to_process = list(default_folder.glob(f"*{file_ext}"))
        else:
            print(f"Не найдены файлы для обработки. Используйте --file или --folder")
            return
    
    if not files_to_process:
        print(f"Файлы не найдены")
        return
    
    print(f"Найдено файлов: {len(files_to_process)}")
    for file in files_to_process:
        print(f"  - {file.name}")
    
    # Пути относительно корня проекта
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "experiments" / "pdf_text_extraction" / "results" / args.type
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nВыходная директория: {output_dir}")
    
    # Создаем парсер
    print(f"\nИнициализация {parser_class.__name__}...")
    doc_parser = parser_class()
    print(f"{parser_class.__name__} инициализирован")
    
    # Обрабатываем файлы
    results = []
    for i, file_path in enumerate(files_to_process, 1):
        print(f"\n{'='*80}")
        print(f"Обработка файла {i}/{len(files_to_process)}: {file_path.name}")
        print(f"{'='*80}")
        
        result = process_document(file_path, doc_parser, output_dir, doc_type)
        result["file_name"] = file_path.name
        results.append(result)
    
    # Выводим итоги
    print(f"\n{'='*80}")
    print("ИТОГИ ОБРАБОТКИ")
    print(f"{'='*80}")
    
    successful = [r for r in results if r.get("success", False)]
    failed = [r for r in results if not r.get("success", False)]
    
    print(f"\nУспешно обработано: {len(successful)}/{len(results)}")
    if successful:
        print("\nУспешно обработанные файлы:")
        for result in successful:
            print(f"  ✓ {result['file_name']}")
            print(f"    Время обработки: {result.get('processing_time', 0):.2f} сек")
            if "stats" in result:
                stats = result["stats"]
                print(f"    Элементов: {stats.get('total_elements', 0)}")
                print(f"    Заголовков: {stats.get('headers', 0)}")
                print(f"    Текстовых блоков: {stats.get('text_blocks', 0)}")
                print(f"    Таблиц: {stats.get('tables', 0)}")
                print(f"    Изображений: {stats.get('images', 0)}")
            print(f"    Результаты: {result.get('output_dir', 'N/A')}")
            print()
    
    if failed:
        print(f"\nОшибки при обработке: {len(failed)}/{len(results)}")
        print("\nФайлы с ошибками:")
        for result in failed:
            print(f"  ✗ {result['file_name']}")
            print(f"    Ошибка: {result.get('error', 'Unknown error')}")
            print()
    
    # Общая статистика
    if successful:
        total_time = sum(r.get("processing_time", 0) for r in results)
        total_elements = sum(r.get("stats", {}).get("total_elements", 0) for r in successful)
        total_headers = sum(r.get("stats", {}).get("headers", 0) for r in successful)
        total_tables = sum(r.get("stats", {}).get("tables", 0) for r in successful)
        total_images = sum(r.get("stats", {}).get("images", 0) for r in successful)
        
        print(f"\nОбщая статистика:")
        print(f"  Всего файлов: {len(results)}")
        print(f"  Успешно: {len(successful)}")
        print(f"  С ошибками: {len(failed)}")
        print(f"  Общее время обработки: {total_time:.2f} сек")
        print(f"  Всего элементов: {total_elements}")
        print(f"  Всего заголовков: {total_headers}")
        print(f"  Всего таблиц: {total_tables}")
        print(f"  Всего изображений: {total_images}")


if __name__ == "__main__":
    main()
