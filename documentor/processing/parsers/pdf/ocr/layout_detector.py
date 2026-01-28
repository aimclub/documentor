"""
Layout detection для PDF через Dots.OCR.

Содержит классы для определения структуры страниц PDF
с использованием Dots.OCR через DotsOCRManager.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PIL import Image

from ....ocr.base import BaseLayoutDetector
from ....ocr.manager import DotsOCRManager, TaskStatus


class PdfLayoutDetector(BaseLayoutDetector):
    """
    Детектор layout для PDF через Dots.OCR.
    
    Использует DotsOCRManager для определения структуры страниц.
    """
    
    def __init__(self, ocr_manager: Optional[DotsOCRManager] = None) -> None:
        """
        Инициализация детектора.
        
        Args:
            ocr_manager: Экземпляр DotsOCRManager. Если None, автоматически создается из .env.
        """
        if ocr_manager is None:
            self.ocr_manager = DotsOCRManager(auto_load_models=True)
            self._own_manager = True
        else:
            self.ocr_manager = ocr_manager
            self._own_manager = False
    
    def detect_layout(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Определяет layout страницы через Dots.OCR.
        
        Args:
            image: Изображение страницы PDF
            
        Returns:
            List[Dict[str, Any]]: Список элементов layout с полями:
                - bbox: [x1, y1, x2, y2]
                - category: тип элемента
                - text: текст элемента (если доступен)
        """
        # Отправляем задачу на обработку
        task_id = self.ocr_manager.submit_task(
            image=image,
            task_format="Layout",
            prompt_mode="prompt_layout_only_en"
        )
        
        # Ожидаем результат
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
        if self._own_manager:
            self.ocr_manager.__exit__(exc_type, exc_val, exc_tb)
