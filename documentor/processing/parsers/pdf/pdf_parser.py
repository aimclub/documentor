"""
Парсер для PDF документов.

Поддерживает два пути обработки:

1. **Извлекаемый текст (selectable text)**:
   - Извлечение текста через PdfPlumber
   - Парсинг ключевых слов для структурных элементов (Table 1, Figure 1, Image 1 и т.д.)
   - Если ключевые слова находятся в таблице → вызов DotsOCR для парсинга структурных элементов
   - Извлечение всех структурных элементов (таблицы, изображения, формулы) через DotsOCR

2. **OCR пайплайн (скан)**:
   - Рендеринг страниц в изображения
   - Dots.OCR layout detection для определения структуры
   - Построение порядка чтения
   - Распознавание текста и структурирование элементов

Текущий статус: Заглушка (базовая обработка текста)
TODO: Реализовать полную логику:
- Определение типа PDF (текст или скан)
- Интеграция с PdfPlumber для извлечения текста и таблиц
- Парсинг ключевых слов (Table/Figure/Image) в тексте
- Определение контекста (находятся ли ключевые слова в таблице)
- Вызов DotsOCR для парсинга структурных элементов при необходимости
- Интеграция с OCR пайплайном (Dots.OCR) для сканов
- Построение иерархии элементов
"""

from __future__ import annotations

from typing import List, Optional

from langchain_core.documents import Document

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ....exceptions import ParsingError
from ....llm.header_detector import HeaderDetector
from ....ocr.manager import DotsOCRManager
from ....utils.text_utils import split_with_overlap
from ..base import BaseParser
from .ocr.layout_detector import PdfLayoutDetector
from .text_extractor import PdfTextExtractor


class PdfParser(BaseParser):
    """
    Парсер для PDF документов.

    Поддерживает два пути обработки:
    
    - **Текстовый путь (selectable text)**:
      - Извлечение текста через PdfPlumber
      - Парсинг ключевых слов (Table 1, Figure 1, Image 1 и т.д.)
      - Если ключевые слова в таблице → вызов DotsOCR для парсинга структурных элементов
      - Извлечение всех структурных элементов через DotsOCR
    
    - **OCR путь (скан)**: 
      - Рендеринг страниц → Dots.OCR layout detection → структурирование

    Текущая реализация - заглушка, которая разбивает текст на параграфы.
    """

    format = DocumentFormat.PDF

    def __init__(self, ocr_manager: Optional[DotsOCRManager] = None) -> None:
        """
        Инициализация парсера.
        
        Args:
            ocr_manager: Экземпляр DotsOCRManager для OCR обработки. 
                        Если None, автоматически создается из .env при необходимости.
        """
        super().__init__()
        self.text_extractor = PdfTextExtractor()
        self.header_detector: Optional[HeaderDetector] = None
        self.ocr_manager = ocr_manager
        self.layout_detector: Optional[PdfLayoutDetector] = None
        # TODO: Инициализировать HeaderDetector при необходимости
    
    def _get_ocr_manager(self) -> Optional[DotsOCRManager]:
        """
        Получает OCR менеджер, создавая его при необходимости.
        
        Returns:
            DotsOCRManager или None, если .env не настроен
        """
        if self.ocr_manager is None:
            try:
                self.ocr_manager = DotsOCRManager(auto_load_models=True)
                self._logger.debug("DotsOCRManager автоматически создан из .env")
            except Exception as e:
                self._logger.warning(f"Не удалось создать DotsOCRManager из .env: {e}")
                return None
        return self.ocr_manager

    def parse(self, document: Document) -> ParsedDocument:
        """
        Парсит PDF документ.

        Определяет тип PDF (текстовый или скан) и выбирает соответствующий путь обработки.

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
            # Определяем тип PDF и выбираем путь обработки
            # TODO: Реализовать определение типа PDF
            # is_text_extractable = self._is_text_extractable(source)
            
            # Временная заглушка: используем базовую обработку
            text = (document.page_content or "").strip()
            elements: List[Element] = []

            if not text:
                self._logger.warning(
                    f"PDF документ пуст или не содержит текста (источник: {source})"
                )
            else:
                for paragraph in self._split_paragraphs(text):
                    element = self._create_element(
                        type=ElementType.TEXT,
                        content=paragraph,
                        metadata={"parser_hint": "basic_text", "status": "skeleton"},
                    )
                    elements.append(element)

            parsed_document = ParsedDocument(
                source=source,
                format=self.format,
                elements=elements,
                metadata={
                    "parser": "pdf",
                    "status": "skeleton",
                    "text_length": len(text),
                    "paragraphs_count": len(elements),
                },
            )

            self._validate_parsed_document(parsed_document)
            self._log_parsing_end(source, len(elements))

            return parsed_document

        except Exception as e:
            error_msg = f"Ошибка при парсинге PDF документа (источник: {source})"
            self._logger.error(f"{error_msg}. Исходная ошибка: {e}")
            raise ParsingError(error_msg, source=source, original_error=e) from e

    def _is_text_extractable(self, source: str) -> bool:
        """
        Определяет, можно ли извлечь текст из PDF.

        Args:
            source: Путь к PDF файлу.

        Returns:
            True, если текст можно извлечь, False иначе.
        """
        # TODO: Реализовать определение типа PDF
        # return self.text_extractor.is_text_extractable(source)
        raise NotImplementedError("Метод _is_text_extractable() требует реализации")

    def _parse_with_text_extraction(self, document: Document) -> ParsedDocument:
        """
        Парсит PDF с извлекаемым текстом (Путь 1: PdfPlumber + парсинг ключевых слов + DotsOCR).

        Процесс:
        1. Извлечение текста через PdfPlumber
        2. Извлечение таблиц через PdfPlumber
        3. Парсинг ключевых слов для структурных элементов:
           - "Table 1", "Table 2", "Таблица 1" и т.д.
           - "Figure 1", "Figure 2", "Рис. 1", "Рисунок 1" и т.д.
           - "Image 1", "Image 2", "Изображение 1" и т.д.
        4. Определение контекста: если ключевые слова находятся в таблице
        5. Вызов DotsOCR для парсинга структурных элементов (если найдены в таблице)
        6. Извлечение всех структурных элементов через DotsOCR:
           - Таблицы с их содержимым
           - Изображения с подписями
           - Формулы
        7. Построение иерархии элементов

        Args:
            document: LangChain Document с PDF контентом.

        Returns:
            ParsedDocument: Структурированное представление документа.
        """
        source = self.get_source(document)
        
        # TODO: Реализовать текстовый путь
        # 1. Извлечь текст через PdfTextExtractor
        # text = self.text_extractor.extract_text(source)
        # 
        # 2. Разбить на чанки с перекрытием
        # chunks = split_with_overlap(text, chunk_size=3000, overlap_size=500)
        # 
        # 3. Детектировать заголовки через LLM
        # all_headers = []
        # previous_headers = None
        # for chunk in chunks:
        #     headers = self.header_detector.detect_headers(chunk, previous_headers)
        #     all_headers.extend(headers)
        #     previous_headers = headers
        # 
        # 4. Объединить заголовки
        # merged_headers = self.header_detector.merge_headers([all_headers])
        # 
        # 5. Построить иерархию элементов
        # elements = self._build_elements_from_text(text, merged_headers)
        # 
        # 6. Создать ParsedDocument
        raise NotImplementedError("Метод _parse_with_text_extraction() требует реализации")

    def _parse_with_ocr(self, document: Document) -> ParsedDocument:
        """
        Парсит PDF через OCR пайплайн (Путь 2: Dots.OCR + Qwen OCR).

        Процесс:
        1. Рендеринг страниц в изображения
        2. Dots.OCR layout detection через DotsOCRManager
        3. Построение порядка чтения
        4. Qwen OCR распознавание текста
        5. Структурирование по layout типам
        6. Построение иерархии элементов

        Args:
            document: LangChain Document с PDF контентом.

        Returns:
            ParsedDocument: Структурированное представление документа.
        """
        source = self.get_source(document)
        
        # Получаем или создаем OCR менеджер
        ocr_manager = self._get_ocr_manager()
        if ocr_manager is None:
            raise RuntimeError(
                "OCR обработка недоступна: DotsOCRManager не может быть создан. "
                "Проверьте настройки в .env файле (DOTS_OCR_BASE_URL, DOTS_OCR_API_KEY и т.д.)"
            )
        
        # Инициализируем layout detector, если еще не инициализирован
        if self.layout_detector is None:
            self.layout_detector = PdfLayoutDetector(ocr_manager=ocr_manager)
        
        # TODO: Реализовать полный OCR путь
        # 1. Рендеринг страниц в изображения
        # page_images = self._render_pages(source)
        # 
        # 2. Dots.OCR layout detection для каждой страницы через менеджер
        # layout_elements = []
        # for page_image in page_images:
        #     layout = self.layout_detector.detect_layout(page_image)
        #     layout_elements.extend(layout)
        # 
        # 3. Построение порядка чтения
        # reading_order = self._build_reading_order(layout_elements)
        # 
        # 4. Qwen OCR распознавание текста
        # ocr_text = self._recognize_text(reading_order)
        # 
        # 5. Структурирование по layout типам
        # elements = self._structure_from_layout(layout_elements, ocr_text)
        # 
        # 6. Создать ParsedDocument
        raise NotImplementedError("Метод _parse_with_ocr() требует реализации")

    def _split_paragraphs(self, text: str) -> List[str]:
        """
        Разбивает текст на параграфы.

        Args:
            text: Текст для разбиения.

        Returns:
            Список параграфов.
        """
        paragraphs = [block.strip() for block in text.split("\n\n")]
        return [paragraph for paragraph in paragraphs if paragraph]