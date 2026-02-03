"""
Layout detection для PDF через Dots.OCR.

Содержит классы для определения структуры страниц PDF
с использованием Dots.OCR через DotsOCRManager или прямой вызов API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PIL import Image

from documentor.ocr.base import BaseLayoutDetector
from .dots_ocr_client import process_layout_detection

# Ленивый импорт для избежания циклических зависимостей
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from documentor.ocr.manager import DotsOCRManager, TaskStatus


class PdfLayoutDetector(BaseLayoutDetector):
    """
    Детектор layout для PDF через Dots.OCR.
    
    Поддерживает два режима работы:
    1. Через DotsOCRManager (асинхронная очередь)
    2. Прямой вызов API (синхронный, как в pdf_pipeline_dots_ocr.py)
    """
    
    def __init__(
        self,
        ocr_manager: Optional[Any] = None,
        use_direct_api: bool = True,
    ) -> None:
        """
        Инициализация детектора.
        
        Args:
            ocr_manager: Экземпляр DotsOCRManager. Если None и use_direct_api=False, 
                        автоматически создается из .env.
            use_direct_api: Если True, использует прямой вызов API (как в pdf_pipeline_dots_ocr.py).
                          Если False, использует DotsOCRManager.
        """
        self.use_direct_api = use_direct_api
        
        if use_direct_api:
            self.ocr_manager = None
            self._own_manager = False
        else:
            if ocr_manager is None:
                # Ленивый импорт для избежания циклических зависимостей
                from documentor.ocr.manager import DotsOCRManager
                self.ocr_manager = DotsOCRManager(auto_load_models=True)
                self._own_manager = True
            else:
                self.ocr_manager = ocr_manager
                self._own_manager = False
    
    def detect_layout(
        self,
        image: Image.Image,
        origin_image: Optional[Image.Image] = None,
    ) -> List[Dict[str, Any]]:
        """
        Определяет layout страницы через Dots.OCR.
        
        Args:
            image: Изображение страницы PDF (уже подготовленное через smart_resize)
            origin_image: Оригинальное изображение (для post_process_output)
        
        Returns:
            List[Dict[str, Any]]: Список элементов layout с полями:
                - bbox: [x1, y1, x2, y2]
                - category: тип элемента
                - text: текст элемента (если доступен)
        """
        if self.use_direct_api:
            # Прямой вызов API (как в pdf_pipeline_dots_ocr.py)
            layout_cells, raw_response, success = process_layout_detection(
                image=image,
                origin_image=origin_image,
            )
            
            if not success or layout_cells is None:
                raise RuntimeError(
                    f"Ошибка layout detection: не удалось получить результат. "
                    f"Raw response: {raw_response[:200] if raw_response else 'None'}"
                )
            
            return layout_cells
        else:
            # Использование DotsOCRManager (асинхронная очередь)
            task_id = self.ocr_manager.submit_task(
                image=image,
                task_format="Layout",
                prompt_mode="prompt_layout_only_en"
            )
            
            # Ожидаем результат
            from documentor.ocr.manager import TaskStatus
            task = self.ocr_manager.wait_for_task(task_id, timeout=300)
            
            if task.status != TaskStatus.COMPLETED:
                raise RuntimeError(f"Ошибка layout detection: {task.error}")
            
            result = task.result
            
            # Нормализуем результат в список элементов
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                # Если результат - словарь с ключом 'elements'
                if 'elements' in result:
                    return result['elements']
                # Если результат - один элемент
                return [result]
            else:
                raise ValueError(f"Неожиданный формат результата: {type(result)}")
    
    def __enter__(self) -> PdfLayoutDetector:
        """Поддержка контекстного менеджера."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Очистка при выходе из контекстного менеджера."""
        if self._own_manager and self.ocr_manager is not None:
            self.ocr_manager.__exit__(exc_type, exc_val, exc_tb)
