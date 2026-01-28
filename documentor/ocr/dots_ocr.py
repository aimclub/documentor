"""
Интеграция с Dots.OCR для layout detection.

Содержит классы для:
- Определения структуры страницы (layout detection)
- Определения типов элементов (Text, Picture, Caption, Table и т.д.)
- Получения координат элементов (bbox)

Использует строгие промпты из официальной документации Dots.OCR.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
from PIL import Image
import yaml

from ..processing.parsers.docx.ocr.layout_dots import LayoutTypeDotsOCR


# Строгие промпты из Dots.OCR (официальные)
DOTS_OCR_PROMPTS = {
    # Полное извлечение layout с текстом в JSON формате
    "prompt_layout_all_en": """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object.
""",

    # Только определение layout без текста
    "prompt_layout_only_en": """Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format.""",

    # Извлечение текста из изображения (кроме Page-header и Page-footer)
    "prompt_ocr": """Extract the text content from this image.""",

    # Извлечение текста из заданного bounding box
    "prompt_grounding_ocr": """Extract text from the given bounding box on the image (format: [x1, y1, x2, y2]).
Bounding Box:
""",
}


def load_prompts_from_config(config_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Загрузить промпты из конфигурационного файла.
    
    Args:
        config_path: Путь к ocr_config.yaml (если None - используется стандартный)
    
    Returns:
        Dict[str, str]: Словарь промптов
    """
    if config_path is None:
        # Стандартный путь к конфигурации
        config_path = Path(__file__).parent.parent / "config" / "ocr_config.yaml"
    
    if not config_path.exists():
        # Если конфигурации нет, возвращаем стандартные промпты
        return DOTS_OCR_PROMPTS.copy()
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Извлекаем промпты из конфигурации
    dots_ocr_config = config.get("dots_ocr", {})
    prompts_config = dots_ocr_config.get("prompts", {})
    
    # Объединяем с стандартными промптами (конфигурация имеет приоритет)
    prompts = DOTS_OCR_PROMPTS.copy()
    prompts.update(prompts_config)
    
    return prompts


def get_system_prompt(image_width: int, image_height: int) -> str:
    """
    Возвращает system prompt для layout detection.
    
    Args:
        image_width: Ширина изображения в пикселях
        image_height: Высота изображения в пикселях
    
    Returns:
        str: System prompt с информацией о размере изображения
    """
    return f"You are a precise document layout analyzer. The input image is exactly {image_width}x{image_height} pixels."


class DotsOCRLayoutDetector:
    """
    Детектор layout для Dots.OCR.
    
    Использует строгие промпты из официальной документации Dots.OCR
    для определения структуры страницы.
    
    Промпты можно загрузить из конфигурации (ocr_config.yaml) или использовать стандартные.
    """
    
    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: int = 60,
        prompt_mode: str = "prompt_layout_all_en",
        prompts: Optional[Dict[str, str]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        """
        Инициализация детектора.
        
        Args:
            endpoint: URL или путь к сервису Dots.OCR (если None - локальный)
            timeout: Таймаут запроса в секундах
            prompt_mode: Режим промпта (prompt_layout_all_en, prompt_layout_only_en, prompt_ocr, prompt_grounding_ocr)
            prompts: Кастомные промпты (если None - загружаются из конфигурации или используются стандартные)
            config_path: Путь к конфигурационному файлу (если None - используется стандартный)
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.prompt_mode = prompt_mode
        
        # Загружаем промпты: сначала из config_path, потом из prompts, потом стандартные
        if prompts is None:
            self.prompts = load_prompts_from_config(config_path)
        else:
            self.prompts = prompts
    
    def get_prompt(self, mode: Optional[str] = None) -> str:
        """
        Получить промпт для указанного режима.
        
        Args:
            mode: Режим промпта (если None - используется self.prompt_mode)
        
        Returns:
            str: Текст промпта
        """
        mode = mode or self.prompt_mode
        if mode not in self.prompts:
            raise ValueError(f"Неизвестный режим промпта: {mode}. Доступные: {list(self.prompts.keys())}")
        return self.prompts[mode]
    
    def detect_layout(
        self,
        image: Image.Image,
        mode: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Определить layout страницы.
        
        Args:
            image: Изображение страницы
            mode: Режим промпта (если None - используется self.prompt_mode)
        
        Returns:
            List[Dict[str, Any]]: Список элементов layout с полями:
                - bbox: [x1, y1, x2, y2]
                - category: тип элемента (LayoutTypeDotsOCR)
                - text: текст элемента (если доступен)
        
        TODO: Реализовать вызов API Dots.OCR
        """
        prompt = self.get_prompt(mode)
        # TODO: Реализовать вызов API Dots.OCR с использованием prompt
        # TODO: Парсинг JSON ответа
        # TODO: Валидация и нормализация результатов
        raise NotImplementedError("Метод detect_layout() требует реализации")
    
    def get_element_types(self, layout_result: List[Dict[str, Any]]) -> List[LayoutTypeDotsOCR]:
        """
        Получить типы элементов из результата layout detection.
        
        Args:
            layout_result: Результат detect_layout()
        
        Returns:
            List[LayoutTypeDotsOCR]: Список типов элементов
        """
        types = []
        for element in layout_result:
            category = element.get("category", "Unknown")
            try:
                # Маппинг строки в LayoutTypeDotsOCR
                layout_type = LayoutTypeDotsOCR(category)
                types.append(layout_type)
            except ValueError:
                types.append(LayoutTypeDotsOCR.UNKNOWN)
        return types
    
    def get_bboxes(self, layout_result: List[Dict[str, Any]]) -> List[List[int]]:
        """
        Получить координаты элементов из результата layout detection.
        
        Args:
            layout_result: Результат detect_layout()
        
        Returns:
            List[List[int]]: Список bbox в формате [[x1, y1, x2, y2], ...]
        """
        bboxes = []
        for element in layout_result:
            bbox = element.get("bbox", [])
            if len(bbox) == 4:
                bboxes.append(bbox)
        return bboxes
