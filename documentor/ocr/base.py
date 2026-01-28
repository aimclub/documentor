"""
Базовые классы для работы с OCR.

Определяет интерфейсы для:
- Layout detection
- Text recognition
- Reading order построения
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from PIL import Image


class BaseLayoutDetector(ABC):
    """
    Базовый класс для layout detection.
    
    Определяет интерфейс для определения структуры страницы документа.
    """
    
    @abstractmethod
    def detect_layout(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Определяет layout страницы.
        
        Args:
            image: Изображение страницы
            
        Returns:
            List[Dict[str, Any]]: Список элементов layout с полями:
                - bbox: [x1, y1, x2, y2]
                - category: тип элемента
                - text: текст элемента (если доступен)
        """
        raise NotImplementedError


class BaseOCR(ABC):
    """
    Базовый класс для распознавания текста.
    
    Определяет интерфейс для OCR обработки изображений.
    """
    
    @abstractmethod
    def recognize_text(self, image: Image.Image) -> str:
        """
        Распознает текст из изображения.
        
        Args:
            image: Изображение для распознавания
            
        Returns:
            str: Распознанный текст
        """
        raise NotImplementedError


class BaseReadingOrderBuilder(ABC):
    """
    Базовый класс для построения порядка чтения.
    
    Определяет интерфейс для определения порядка чтения элементов на странице.
    """
    
    @abstractmethod
    def build_reading_order(self, layout_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Строит порядок чтения элементов.
        
        Args:
            layout_elements: Список элементов layout
            
        Returns:
            List[Dict[str, Any]]: Элементы в порядке чтения
        """
        raise NotImplementedError
