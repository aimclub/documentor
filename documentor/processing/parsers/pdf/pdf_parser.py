"""
Парсер для PDF документов.

Поддерживает layout-based подход:
- Layout detection через Dots.OCR для всех страниц
- Построение иерархии от Section-header
- Фильтрация лишних элементов (Page-header, боковой текст)
- Извлечение текста через PyMuPDF по координатам
- Склеивание близких текстовых блоков
- Парсинг таблиц через Qwen2.5
- Хранение изображений в метаданных
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz
import yaml
from langchain_core.documents import Document
from PIL import Image
from tqdm import tqdm

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ....exceptions import ParsingError
from ..base import BaseParser
from .ocr.layout_detector import PdfLayoutDetector
from .ocr.page_renderer import PdfPageRenderer
from .ocr.qwen_table_parser import (
    parse_table_with_qwen,
    detect_merged_tables,
    markdown_to_dataframe,
)


logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """
    Парсер для PDF документов.

    Использует layout-based подход:
    - Layout detection через Dots.OCR для всех страниц
    - Построение иерархии от Section-header
    - Фильтрация лишних элементов
    - Извлечение текста через PyMuPDF по координатам
    - Склеивание близких текстовых блоков
    - Парсинг таблиц через Qwen2.5
    """

    format = DocumentFormat.PDF

    def __init__(self, ocr_manager: Optional[Any] = None) -> None:
        """
        Инициализация парсера.
        
        Args:
            ocr_manager: Экземпляр DotsOCRManager для OCR обработки. 
                        Если None, автоматически создается из .env при необходимости.
        """
        super().__init__()
        self.ocr_manager = ocr_manager
        self.layout_detector: Optional[PdfLayoutDetector] = None
        self.page_renderer: Optional[PdfPageRenderer] = None
        self._config: Optional[Dict[str, Any]] = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Загружает конфигурацию из pdf_config.yaml."""
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "pdf_config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                self._config = config.get("pdf_parser", {})
        else:
            self._config = {}
            logger.warning(f"Конфигурационный файл не найден: {config_path}, используются значения по умолчанию")

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Получает значение из конфигурации."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value if value is not None else default
    
    def _get_ocr_manager(self) -> Optional[Any]:
        """
        Получает OCR менеджер, создавая его при необходимости.
        
        Returns:
            DotsOCRManager или None, если .env не настроен
        """
        if self.ocr_manager is None:
            try:
                from ....ocr.manager import DotsOCRManager
                self.ocr_manager = DotsOCRManager(auto_load_models=True)
                logger.debug("DotsOCRManager автоматически создан из .env")
            except Exception as e:
                logger.warning(f"Не удалось создать DotsOCRManager из .env: {e}")
                return None
        return self.ocr_manager

    def parse(self, document: Document) -> ParsedDocument:
        """
        Парсит PDF документ используя layout-based подход.

        Процесс:
        1. Проверка выделяемого текста
        2. Layout detection через Dots.OCR для всех страниц
        3. Построение иерархии от Section-header
        4. Фильтрация лишних элементов
        5. Извлечение текста через PyMuPDF по координатам
        6. Склеивание близких текстовых блоков
        7. Создание элементов и построение иерархии
        8. Хранение изображений в метаданных
        9. Парсинг таблиц через Qwen2.5

        Args:
            document: LangChain Document с PDF контентом.

        Returns:
            ParsedDocument: Структурированное представление документа.

        Raises:
            ValidationError: Если входные данные невалидны.
            UnsupportedFormatError: Если формат документа не поддерживается.
            ParsingError: Если произошла ошибка при парсинге.
        """
        self._validate_input(document)

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            # Проверяем выделяемый ли текст
            is_text_extractable = self._is_text_extractable(source)
            
            if not is_text_extractable:
                logger.warning(
                    f"Текст не выделяется из PDF, используем layout-based подход (источник: {source})"
                )
            
            # Layout-based подход (всегда используем, даже если текст выделяется)
            # Шаг 1: Layout Detection для всех страниц
            layout_elements = self._detect_layout_for_all_pages(source)
            
            # Шаг 2: Фильтрация лишних элементов
            filtered_elements = self._filter_layout_elements(layout_elements)
            
            # Шаг 3: Анализ уровней заголовков (сначала определяем уровни)
            analyzed_elements = self._analyze_header_levels_from_elements(filtered_elements, source)
            
            # Шаг 4: Построение иерархии от Section-header (с учетом уровней)
            hierarchy = self._build_hierarchy_from_section_headers(analyzed_elements)
            
            # Шаг 5: Извлечение текста через PyMuPDF
            text_elements = self._extract_text_by_bboxes(source, analyzed_elements)
            
            # Шаг 6: Склеивание подряд идущих Text элементов
            merged_text_elements = self._merge_nearby_text_blocks(text_elements, max_chunk_size=3000)
            
            # Шаг 7: Создание элементов из иерархии
            elements = self._create_elements_from_hierarchy(hierarchy, merged_text_elements, analyzed_elements)
            
            # Шаг 8: Хранение изображений в метаданных
            elements = self._store_images_in_metadata(elements, source)
            
            # Шаг 9: Парсинг таблиц через Qwen2.5
            elements = self._parse_tables_with_qwen(elements, source)
            
            # Создание ParsedDocument
            parsed_document = ParsedDocument(
                source=source,
                format=self.format,
                elements=elements,
                metadata={
                    "parser": "pdf",
                    "status": "completed",
                    "processing_method": "layout_based",
                    "total_pages": self._get_page_count(source),
                    "elements_count": len(elements),
                    "headers_count": len([e for e in elements if e.type.name.startswith("HEADER")]),
                    "tables_count": len([e for e in elements if e.type == ElementType.TABLE]),
                    "images_count": len([e for e in elements if e.type == ElementType.IMAGE]),
                },
            )

            self._validate_parsed_document(parsed_document)
            self._log_parsing_end(source, len(elements))

            return parsed_document

        except Exception as e:
            error_msg = f"Ошибка при парсинге PDF документа (источник: {source})"
            logger.error(f"{error_msg}. Исходная ошибка: {e}")
            raise ParsingError(error_msg, source=source, original_error=e) from e

    def _is_text_extractable(self, source: str) -> bool:
        """
        Определяет, можно ли извлечь текст из PDF.

        Args:
            source: Путь к PDF файлу.

        Returns:
            True, если текст можно извлечь, False иначе.
        """
        try:
            pdf_document = fitz.open(source)
            try:
                # Проверяем первую страницу
                if len(pdf_document) == 0:
                    return False
                
                page = pdf_document.load_page(0)
                text = page.get_text("text")
                
                return len(text.strip()) >= 100
            finally:
                pdf_document.close()
        except Exception as e:
            logger.warning(f"Ошибка при проверке выделяемого текста: {e}")
            return False

    def _get_page_count(self, source: str) -> int:
        """Возвращает количество страниц в PDF."""
        pdf_document = fitz.open(source)
        try:
            return len(pdf_document)
        finally:
            pdf_document.close()

    def _detect_layout_for_all_pages(self, source: str) -> List[Dict[str, Any]]:
        """
        Выполняет layout detection для всех страниц PDF.

        Args:
            source: Путь к PDF файлу.

        Returns:
            Список элементов layout с полями bbox, category, page_num.
        """
        if self.page_renderer is None:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            optimize_for_ocr = self._get_config("layout_detection.optimize_for_ocr", True)
            self.page_renderer = PdfPageRenderer(
                render_scale=render_scale,
                optimize_for_ocr=optimize_for_ocr,
            )
        
        if self.layout_detector is None:
            use_direct_api = self._get_config("layout_detection.use_direct_api", True)
            
            if use_direct_api:
                # При использовании прямого API менеджер не нужен
                ocr_manager = None
            else:
                # При использовании DotsOCRManager нужен менеджер
                ocr_manager = self._get_ocr_manager()
                if ocr_manager is None:
                    raise RuntimeError(
                        "OCR обработка недоступна: DotsOCRManager не может быть создан. "
                        "Проверьте настройки в .env файле"
                    )
            
            self.layout_detector = PdfLayoutDetector(ocr_manager=ocr_manager, use_direct_api=use_direct_api)
        
        pdf_path = Path(source)
        total_pages = self.page_renderer.get_page_count(pdf_path)
        all_layout_elements: List[Dict[str, Any]] = []
        
        logger.info(f"Начинаем layout detection для {total_pages} страниц")
        
        for page_num in tqdm(range(total_pages), desc="Layout detection", unit="страница"):
            try:
                original_image, optimized_image = self.page_renderer.render_page(
                    pdf_path, page_num, return_original=True
                )
                
                layout = self.layout_detector.detect_layout(optimized_image, origin_image=original_image)
                
                # Добавляем номер страницы к каждому элементу
                for element in layout:
                    element["page_num"] = page_num
                    all_layout_elements.append(element)
                
                logger.debug(f"Layout detection для страницы {page_num + 1}/{total_pages}: найдено {len(layout)} элементов")
            except Exception as e:
                logger.error(f"Ошибка при layout detection для страницы {page_num + 1}: {e}")
                continue
        
        logger.info(f"Layout detection завершен: всего найдено {len(all_layout_elements)} элементов")
        return all_layout_elements

    def _filter_layout_elements(self, layout_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Фильтрует лишние элементы (Page-header, Page-footer, боковой текст).

        Args:
            layout_elements: Список элементов layout.

        Returns:
            Отфильтрованный список элементов.
        """
        filtered: List[Dict[str, Any]] = []
        
        remove_page_headers = self._get_config("filtering.remove_page_headers", True)
        remove_page_footers = self._get_config("filtering.remove_page_footers", True)
        
        for element in layout_elements:
            category = element.get("category", "")
            
            # Удаляем Page-header и Page-footer
            if remove_page_headers and category == "Page-header":
                continue
            if remove_page_footers and category == "Page-footer":
                continue
            
            filtered.append(element)
        
        logger.debug(f"Фильтрация: {len(layout_elements)} -> {len(filtered)} элементов")
        return filtered

    def _build_hierarchy_from_section_headers(
        self, layout_elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Строит иерархию элементов, группируя их по Section-header.

        Args:
            layout_elements: Список элементов layout.

        Returns:
            Список секций с заголовками и дочерними элементами.
        """
        # Сортируем элементы по странице и Y координате
        sorted_elements = sorted(
            layout_elements,
            key=lambda e: (e.get("page_num", 0), e.get("bbox", [1, 0])[1] if len(e.get("bbox", [])) >= 2 else 0)
        )
        
        sections: List[Dict[str, Any]] = []
        current_section: Optional[Dict[str, Any]] = None
        
        for element in sorted_elements:
            category = element.get("category", "")
            
            if category == "Section-header":
                # Сохраняем предыдущую секцию
                if current_section is not None:
                    sections.append(current_section)
                
                # Создаем новую секцию
                current_section = {
                    "header": element,
                    "children": [],
                }
            else:
                # Добавляем элемент к текущей секции
                if current_section is not None:
                    current_section["children"].append(element)
                else:
                    # Элементы до первого заголовка - создаем секцию без заголовка
                    current_section = {
                        "header": None,
                        "children": [element],
                    }
        
        # Добавляем последнюю секцию
        if current_section is not None:
            sections.append(current_section)
        
        logger.debug(f"Построена иерархия: {len(sections)} секций")
        return sections

    def _analyze_header_levels_from_elements(
        self, layout_elements: List[Dict[str, Any]], source: str
    ) -> List[Dict[str, Any]]:
        """
        Анализирует уровни заголовков из списка элементов (до построения иерархии).

        Args:
            layout_elements: Список элементов layout.
            source: Путь к PDF файлу.

        Returns:
            Список элементов с определенными уровнями заголовков.
        """
        pdf_document = fitz.open(source)
        try:
            analyzed_elements: List[Dict[str, Any]] = []
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            for element in layout_elements:
                category = element.get("category", "")
                
                if category == "Section-header":
                    # Извлекаем текст заголовка через PyMuPDF
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    
                    if len(bbox) >= 4 and page_num < len(pdf_document):
                        try:
                            page = pdf_document.load_page(page_num)
                            # Приводим координаты к масштабу оригинального PDF
                            x1, y1, x2, y2 = (
                                bbox[0] / render_scale,
                                bbox[1] / render_scale,
                                bbox[2] / render_scale,
                                bbox[3] / render_scale,
                            )
                            rect = fitz.Rect(x1, y1, x2, y2)
                            text = page.get_text("text", clip=rect).strip()
                            
                            # Определяем уровень заголовка
                            level = self._determine_header_level(text, element, page, rect)
                            element_type = getattr(ElementType, f"HEADER_{level}", ElementType.HEADER_1)
                            
                            element["text"] = text
                            element["level"] = level
                            element["element_type"] = element_type
                        except Exception as e:
                            logger.warning(f"Ошибка при анализе заголовка: {e}")
                            element["level"] = 1
                            element["element_type"] = ElementType.HEADER_1
                    else:
                        element["level"] = 1
                        element["element_type"] = ElementType.HEADER_1
                
                analyzed_elements.append(element)
            
            return analyzed_elements
        finally:
            pdf_document.close()

    def _analyze_header_levels(
        self, hierarchy: List[Dict[str, Any]], source: str
    ) -> List[Dict[str, Any]]:
        """
        Анализирует уровни заголовков в уже построенной иерархии (legacy метод).

        Args:
            hierarchy: Список секций с заголовками.
            source: Путь к PDF файлу.

        Returns:
            Список секций с определенными уровнями заголовков.
        """
        # Если заголовки уже проанализированы, просто возвращаем иерархию
        for section in hierarchy:
            header = section.get("header")
            if header is not None and "level" not in header:
                # Заголовок не проанализирован - используем старую логику
                pdf_document = fitz.open(source)
                try:
                    bbox = header.get("bbox", [])
                    page_num = header.get("page_num", 0)
                    
                    if len(bbox) >= 4 and page_num < len(pdf_document):
                        try:
                            page = pdf_document.load_page(page_num)
                            render_scale = self._get_config("layout_detection.render_scale", 2.0)
                            x1, y1, x2, y2 = (
                                bbox[0] / render_scale,
                                bbox[1] / render_scale,
                                bbox[2] / render_scale,
                                bbox[3] / render_scale,
                            )
                            rect = fitz.Rect(x1, y1, x2, y2)
                            text = page.get_text("text", clip=rect).strip()
                            
                            level = self._determine_header_level(text, header, page, rect)
                            element_type = getattr(ElementType, f"HEADER_{level}", ElementType.HEADER_1)
                            
                            header["text"] = text
                            header["level"] = level
                            header["element_type"] = element_type
                        except Exception as e:
                            logger.warning(f"Ошибка при анализе заголовка: {e}")
                            header["level"] = 1
                            header["element_type"] = ElementType.HEADER_1
                    else:
                        header["level"] = 1
                        header["element_type"] = ElementType.HEADER_1
                finally:
                    pdf_document.close()
        
        return hierarchy

    def _determine_header_level(
        self, text: str, header: Dict[str, Any], page: fitz.Page, rect: fitz.Rect
    ) -> int:
        """
        Определяет уровень заголовка на основе текста, стиля и позиции.

        Args:
            text: Текст заголовка.
            header: Словарь с информацией о заголовке.
            page: Страница PDF.
            rect: Прямоугольник заголовка.

        Returns:
            Уровень заголовка (1-6).
        """
        # Анализ нумерации
        # Заголовки вида "1", "2", "3" -> HEADER_1
        if re.match(r'^\d+\s+[A-Z]', text):
            return 1
        # Заголовки вида "1.1", "1.2" -> HEADER_2
        if re.match(r'^\d+\.\d+\s+', text):
            return 2
        # Заголовки вида "1.1.1", "1.1.2" -> HEADER_3
        if re.match(r'^\d+\.\d+\.\d+\s+', text):
            return 3
        
        # Анализ позиции (левее = выше уровень)
        bbox = header.get("bbox", [])
        if len(bbox) >= 4:
            x1 = bbox[0]
            # Эвристика: заголовки слева (x < 400) обычно HEADER_1
            if x1 < 400:
                return 1
            # Заголовки в центре (400 < x < 600) обычно HEADER_2
            if x1 < 600:
                return 2
            # Остальные - HEADER_3
            return 3
        
        # По умолчанию HEADER_1
        return 1

    def _extract_text_by_bboxes(
        self, source: str, layout_elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Извлекает текст через PyMuPDF по координатам из layout elements.

        Args:
            source: Путь к PDF файлу.
            layout_elements: Список элементов layout с bbox.

        Returns:
            Список элементов с извлеченным текстом.
        """
        pdf_document = fitz.open(source)
        try:
            text_elements: List[Dict[str, Any]] = []
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            for element in layout_elements:
                category = element.get("category", "")
                bbox = element.get("bbox", [])
                page_num = element.get("page_num", 0)
                
                # Извлекаем текст только для текстовых элементов
                if category not in ["Text", "Section-header", "Title", "Caption"]:
                    text_elements.append(element)
                    continue
                
                if len(bbox) >= 4 and page_num < len(pdf_document):
                    try:
                        page = pdf_document.load_page(page_num)
                        # Приводим координаты к масштабу оригинального PDF
                        x1, y1, x2, y2 = (
                            bbox[0] / render_scale,
                            bbox[1] / render_scale,
                            bbox[2] / render_scale,
                            bbox[3] / render_scale,
                        )
                        rect = fitz.Rect(x1, y1, x2, y2)
                        text = page.get_text("text", clip=rect).strip()
                        
                        element["text"] = text
                    except Exception as e:
                        logger.warning(f"Ошибка при извлечении текста для элемента: {e}")
                        element["text"] = ""
                else:
                    element["text"] = ""
                
                text_elements.append(element)
            
            return text_elements
        finally:
            pdf_document.close()

    def _merge_nearby_text_blocks(
        self, text_elements: List[Dict[str, Any]], max_chunk_size: int
    ) -> List[Dict[str, Any]]:
        """
        Склеивает подряд идущие Text элементы.

        Если по очереди text, потом опять text - склеиваем их.

        Args:
            text_elements: Список текстовых элементов.
            max_chunk_size: Максимальный размер блока в символах.

        Returns:
            Список склеенных элементов.
        """
        if not text_elements:
            return []
        
        merged: List[Dict[str, Any]] = []
        current_block: Optional[Dict[str, Any]] = None
        
        # Сортируем по странице и Y координате
        sorted_elements = sorted(
            text_elements,
            key=lambda e: (
                e.get("page_num", 0),
                e.get("bbox", [1, 0])[1] if len(e.get("bbox", [])) >= 2 else 0,
            ),
        )
        
        for element in sorted_elements:
            category = element.get("category", "")
            text = element.get("text", "")
            
            # Склеиваем только Text элементы
            if category != "Text":
                if current_block is not None:
                    merged.append(current_block)
                    current_block = None
                merged.append(element)
                continue
            
            if current_block is None:
                current_block = element.copy()
                continue
            
            # Если текущий блок - Text и следующий элемент - тоже Text, склеиваем
            current_text = current_block.get("text", "")
            combined_text = f"{current_text} {text}".strip()
            
            # Проверяем размер
            if len(combined_text) <= max_chunk_size:
                current_block["text"] = combined_text
                # Обновляем bbox
                current_bbox = current_block.get("bbox", [])
                element_bbox = element.get("bbox", [])
                if len(current_bbox) >= 4 and len(element_bbox) >= 4:
                    current_block["bbox"] = [
                        min(current_bbox[0], element_bbox[0]),
                        min(current_bbox[1], element_bbox[1]),
                        max(current_bbox[2], element_bbox[2]),
                        max(current_bbox[3], element_bbox[3]),
                    ]
                continue
            
            # Не можем склеить (превышен размер) - сохраняем текущий блок и начинаем новый
            merged.append(current_block)
            current_block = element.copy()
        
        # Добавляем последний блок
        if current_block is not None:
            merged.append(current_block)
        
        logger.debug(f"Склеивание текста: {len(text_elements)} -> {len(merged)} элементов")
        return merged

    def _create_elements_from_hierarchy(
        self,
        hierarchy: List[Dict[str, Any]],
        merged_text_elements: List[Dict[str, Any]],
        layout_elements: List[Dict[str, Any]],
    ) -> List[Element]:
        """
        Создает элементы из иерархии.

        Args:
            hierarchy: Список секций с заголовками.
            merged_text_elements: Список склеенных текстовых элементов.
            layout_elements: Все элементы layout (для поиска текста).

        Returns:
            Список элементов Element.
        """
        elements: List[Element] = []
        header_stack: List[Tuple[int, str]] = []  # (уровень, element_id)
        
        # Создаем индекс текстовых элементов по bbox для быстрого поиска
        text_elements_by_bbox: Dict[Tuple[int, int, int, int, int], Dict[str, Any]] = {}
        for elem in merged_text_elements:
            bbox = elem.get("bbox", [])
            page_num = elem.get("page_num", 0)
            if len(bbox) >= 4:
                # Используем округленные координаты для поиска
                key = (page_num, int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                text_elements_by_bbox[key] = elem
        
        # Также создаем индекс для всех layout элементов
        layout_elements_by_bbox: Dict[Tuple[int, int, int, int, int], Dict[str, Any]] = {}
        for elem in layout_elements:
            bbox = elem.get("bbox", [])
            page_num = elem.get("page_num", 0)
            if len(bbox) >= 4:
                key = (page_num, int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                layout_elements_by_bbox[key] = elem
        
        for section in hierarchy:
            header = section.get("header")
            children = section.get("children", [])
            
            # Создаем элемент заголовка
            if header is not None:
                level = header.get("level", 1)
                element_type = header.get("element_type", ElementType.HEADER_1)
                text = header.get("text", "")
                
                # Обновляем стек заголовков
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                
                parent_id = header_stack[-1][1] if header_stack else None
                
                header_element = self._create_element(
                    type=element_type,
                    content=text,
                    parent_id=parent_id,
                    metadata={
                        "bbox": header.get("bbox", []),
                        "page_num": header.get("page_num", 0),
                        "category": header.get("category", ""),
                    },
                )
                elements.append(header_element)
                header_stack.append((level, header_element.id))
                current_parent_id = header_element.id
            else:
                current_parent_id = header_stack[-1][1] if header_stack else None
            
            # Создаем элементы для дочерних элементов
            for child in children:
                category = child.get("category", "")
                bbox = child.get("bbox", [])
                page_num = child.get("page_num", 0)
                
                if category == "Text":
                    # Ищем текст в merged_text_elements (склеенных блоках)
                    text = ""
                    if len(bbox) >= 4:
                        # Пытаемся найти точное совпадение
                        key = (page_num, int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                        merged_elem = text_elements_by_bbox.get(key)
                        if merged_elem:
                            text = merged_elem.get("text", "")
                        else:
                            # Если точного совпадения нет, используем текст из child
                            text = child.get("text", "")
                    else:
                        text = child.get("text", "")
                    
                    if text:
                        element = self._create_element(
                            type=ElementType.TEXT,
                            content=text,
                            parent_id=current_parent_id,
                            metadata={
                                "bbox": bbox,
                                "page_num": page_num,
                                "category": category,
                            },
                        )
                        elements.append(element)
                elif category == "Table":
                    # Таблицы будут обработаны позже через Qwen
                    element = self._create_element(
                        type=ElementType.TABLE,
                        content="",  # будет заполнено при парсинге
                        parent_id=current_parent_id,
                        metadata={
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        },
                    )
                    elements.append(element)
                elif category == "Picture":
                    element = self._create_element(
                        type=ElementType.IMAGE,
                        content="",  # изображение будет в метаданных
                        parent_id=current_parent_id,
                        metadata={
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        },
                    )
                    elements.append(element)
                elif category == "Caption":
                    text = child.get("text", "")
                    element = self._create_element(
                        type=ElementType.CAPTION,
                        content=text,
                        parent_id=current_parent_id,
                        metadata={
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        },
                    )
                    elements.append(element)
                elif category == "Title":
                    text = child.get("text", "")
                    element = self._create_element(
                        type=ElementType.TITLE,
                        content=text,
                        parent_id=None,  # Title не имеет родителя
                        metadata={
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        },
                    )
                    elements.append(element)
        
        return elements

    def _store_images_in_metadata(
        self, elements: List[Element], source: str
    ) -> List[Element]:
        """
        Сохраняет изображения в метаданных Caption элементов.
        
        Логика:
        - Находит IMAGE элементы
        - Находит соответствующие CAPTION элементы (по близости bbox)
        - Сохраняет изображение в метаданных CAPTION
        - CAPTION уже привязан к Header через parent_id

        Args:
            elements: Список элементов.
            source: Путь к PDF файлу.

        Returns:
            Список элементов с обновленными метаданными.
        """
        pdf_document = fitz.open(source)
        try:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            image_elements = [e for e in elements if e.type == ElementType.IMAGE]
            caption_elements = [e for e in elements if e.type == ElementType.CAPTION]
            
            for image_element in tqdm(image_elements, desc="Обработка изображений", unit="изображение", leave=False):
                image_bbox = image_element.metadata.get("bbox", [])
                image_page = image_element.metadata.get("page_num", 0)
                
                if len(image_bbox) < 4 or image_page >= len(pdf_document):
                    continue
                
                try:
                    # Извлекаем изображение
                    page = pdf_document.load_page(image_page)
                    x1, y1, x2, y2 = (
                        image_bbox[0] / render_scale,
                        image_bbox[1] / render_scale,
                        image_bbox[2] / render_scale,
                        image_bbox[3] / render_scale,
                    )
                    rect = fitz.Rect(x1, y1, x2, y2)
                    pix = page.get_pixmap(clip=rect)
                    img_data = pix.tobytes("png")
                    import base64
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    
                    # Ищем соответствующий Caption элемент
                    # Ищем ближайший Caption на той же странице
                    best_caption = None
                    min_distance = float('inf')
                    
                    for caption_element in caption_elements:
                        caption_bbox = caption_element.metadata.get("bbox", [])
                        caption_page = caption_element.metadata.get("page_num", 0)
                        
                        if caption_page != image_page or len(caption_bbox) < 4:
                            continue
                        
                        # Проверяем близость: Caption обычно ниже изображения
                        # Расстояние по вертикали между нижним краем изображения и верхним краем Caption
                        distance = abs(caption_bbox[1] - image_bbox[3])
                        
                        # Caption должен быть ниже изображения (или очень близко)
                        if caption_bbox[1] >= image_bbox[1] - 50 and distance < min_distance:
                            min_distance = distance
                            best_caption = caption_element
                    
                    # Если нашли Caption, сохраняем изображение в его метаданных
                    if best_caption is not None:
                        best_caption.metadata["image_data"] = f"data:image/png;base64,{img_base64}"
                        logger.debug(f"Изображение сохранено в метаданных Caption {best_caption.id}")
                    else:
                        # Если Caption не найден, сохраняем в метаданных IMAGE (fallback)
                        image_element.metadata["image_data"] = f"data:image/png;base64,{img_base64}"
                        logger.warning(f"Caption не найден для изображения {image_element.id}, изображение сохранено в IMAGE")
                        
                except Exception as e:
                    logger.warning(f"Ошибка при извлечении изображения {image_element.id}: {e}")
        
        finally:
            pdf_document.close()
        
        return elements

    def _parse_tables_with_qwen(
        self, elements: List[Element], source: str
    ) -> List[Element]:
        """
        Парсит таблицы через Qwen2.5.

        Args:
            elements: Список элементов.
            source: Путь к PDF файлу.

        Returns:
            Список элементов с распарсенными таблицами.
        """
        table_elements = [e for e in elements if e.type == ElementType.TABLE]
        
        if not table_elements:
            return elements
        
        method = self._get_config("table_parsing.method", "markdown")
        detect_merged = self._get_config("table_parsing.detect_merged_tables", True)
        
        pdf_document = fitz.open(source)
        try:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            for element in tqdm(table_elements, desc="Парсинг таблиц", unit="таблица", leave=False):
                bbox = element.metadata.get("bbox", [])
                page_num = element.metadata.get("page_num", 0)
                
                if len(bbox) < 4 or page_num >= len(pdf_document):
                    logger.warning(f"Пропуск таблицы с невалидным bbox или page_num: {element.id}")
                    continue
                
                try:
                    page = pdf_document.load_page(page_num)
                    # Приводим координаты к масштабу оригинального PDF
                    x1, y1, x2, y2 = (
                        bbox[0] / render_scale,
                        bbox[1] / render_scale,
                        bbox[2] / render_scale,
                        bbox[3] / render_scale,
                    )
                    rect = fitz.Rect(x1, y1, x2, y2)
                    
                    # Рендерим область таблицы
                    mat = fitz.Matrix(2.0, 2.0)  # Увеличиваем для лучшего качества
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    img_data = pix.tobytes("png")
                    
                    # Сохраняем изображение таблицы в base64 (как для обычных изображений)
                    import base64
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    element.metadata["image_data"] = f"data:image/png;base64,{img_base64}"
                    
                    # Конвертируем для парсинга через Qwen
                    table_image = Image.open(BytesIO(img_data)).convert("RGB")
                    
                    # Парсим таблицу через Qwen
                    markdown_content, dataframe, success = parse_table_with_qwen(
                        table_image,
                        method=method,
                    )
                    
                    if not success:
                        logger.warning(f"Не удалось распарсить таблицу {element.id}")
                        element.content = ""
                        element.metadata["parsing_error"] = "Failed to parse table with Qwen"
                        continue
                    
                    # Обработка склеенных таблиц
                    if detect_merged and markdown_content:
                        tables = detect_merged_tables(markdown_content)
                        
                        if len(tables) > 1:
                            # Несколько таблиц склеены - создаем отдельные элементы
                            logger.info(f"Обнаружено {len(tables)} склеенных таблиц в элементе {element.id}")
                            
                            # Обновляем первый элемент
                            element.content = tables[0]
                            if dataframe is not None:
                                element.metadata["dataframe"] = dataframe
                            element.metadata["parsing_method"] = method
                            element.metadata["merged_tables"] = True
                            element.metadata["table_count"] = len(tables)
                            # Изображение уже сохранено выше
                            
                            # Создаем дополнительные элементы для остальных таблиц
                            parent_id = element.parent_id
                            for i, table_md in enumerate(tables[1:], start=1):
                                # Парсим каждую таблицу отдельно
                                table_df = markdown_to_dataframe(table_md) if method == "markdown" else None
                                
                                new_element = self._create_element(
                                    type=ElementType.TABLE,
                                    content=table_md,
                                    parent_id=parent_id,
                                    metadata={
                                        "bbox": bbox,  # Тот же bbox, так как таблицы склеены
                                        "page_num": page_num,
                                        "category": "Table",
                                        "parsing_method": method,
                                        "merged_tables": True,
                                        "table_index": i,
                                        "image_data": f"data:image/png;base64,{img_base64}",  # То же изображение
                                    },
                                )
                                if table_df is not None:
                                    new_element.metadata["dataframe"] = table_df
                                
                                # Вставляем после текущего элемента
                                element_idx = elements.index(element)
                                elements.insert(element_idx + i, new_element)
                        else:
                            # Одна таблица
                            element.content = markdown_content
                            if dataframe is not None:
                                element.metadata["dataframe"] = dataframe
                            element.metadata["parsing_method"] = method
                    else:
                        # Без обработки склеенных таблиц
                        element.content = markdown_content
                        if dataframe is not None:
                            element.metadata["dataframe"] = dataframe
                        element.metadata["parsing_method"] = method
                    
                    logger.debug(f"Таблица {element.id} успешно распарсена")
                
                except Exception as e:
                    logger.error(f"Ошибка при парсинге таблицы {element.id}: {e}")
                    element.content = ""
                    element.metadata["parsing_error"] = str(e)
                    continue
        
        finally:
            pdf_document.close()
        
        return elements
