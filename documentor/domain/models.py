from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"
    UNKNOWN = "unknown"


class ElementType(str, Enum):
    TITLE = "title"  # Заголовок документа
    HEADER_1 = "header_1"  # Заголовок уровня 1
    HEADER_2 = "header_2"  # Заголовок уровня 2
    HEADER_3 = "header_3"  # Заголовок уровня 3
    HEADER_4 = "header_4"  # Заголовок уровня 4
    HEADER_5 = "header_5"  # Заголовок уровня 5
    HEADER_6 = "header_6"  # Заголовок уровня 6
    TEXT = "text"  # Текст
    IMAGE = "image"  # Изображение
    TABLE = "table"  # Таблица
    FORMULA = "formula"  # Формула
    LIST_ITEM = "list_item"  # Элемент списка
    CAPTION = "caption"  # Подпись
    FOOTNOTE = "footnote"  # Сноска
    PAGE_HEADER = "page_header"  # Колонтитул верхний
    PAGE_FOOTER = "page_footer"  # Колонтитул нижний


@dataclass(slots=True)
class Element:
    id: str
    type: ElementType
    content: str
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Валидация элемента после инициализации."""
        self.validate()

    def validate(self) -> None:
        """
        Валидация элемента.
        
        Проверяет:
        - id не пустой
        - type валидный ElementType
        - content не None
        - parent_id ссылается на существующий элемент (если указан)
        
        Raises:
            ValueError: Если элемент невалиден
        """
        # TODO: Реализовать валидацию
        pass

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        # TODO: Реализовать __repr__
        return f"Element(id={self.id!r}, type={self.type.value!r}, ...)"

    def __str__(self) -> str:
        """Человекочитаемое строковое представление."""
        # TODO: Реализовать __str__
        return f"Element({self.type.value}, id={self.id})"

    def to_dict(self) -> Dict[str, Any]:
        """
        Сериализация элемента в словарь.
        
        Returns:
            Dict[str, Any]: Словарь с данными элемента
        """
        # TODO: Реализовать сериализацию
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "parent_id": self.parent_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Element:
        """
        Десериализация элемента из словаря.
        
        Args:
            data: Словарь с данными элемента
        
        Returns:
            Element: Экземпляр элемента
        
        Raises:
            ValueError: Если данные невалидны
        """
        # TODO: Реализовать десериализацию
        return cls(
            id=data["id"],
            type=ElementType(data["type"]),
            content=data["content"],
            parent_id=data.get("parent_id"),
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """
        Сериализация элемента в JSON строку.
        
        Returns:
            str: JSON строка
        """
        # TODO: Реализовать JSON сериализацию
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> Element:
        """
        Десериализация элемента из JSON строки.
        
        Args:
            json_str: JSON строка
        
        Returns:
            Element: Экземпляр элемента
        
        Raises:
            ValueError: Если JSON невалиден
        """
        # TODO: Реализовать JSON десериализацию
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass(slots=True)
class ParsedDocument:
    source: str
    format: DocumentFormat
    elements: List[Element]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Валидация документа после инициализации."""
        self.validate()

    def validate(self) -> None:
        """
        Валидация документа.
        
        Проверяет:
        - source не пустой
        - format валидный DocumentFormat
        - elements не пустой список
        - целостность иерархии (parent_id ссылаются на существующие элементы)
        - отсутствие циклов в иерархии
        - уникальность id элементов
        
        Raises:
            ValueError: Если документ невалиден
        """
        # TODO: Реализовать валидацию
        pass

    def validate_hierarchy(self) -> None:
        """
        Валидация иерархии элементов.
        
        Проверяет:
        - все parent_id ссылаются на существующие элементы
        - отсутствие циклов в иерархии
        - корректность уровней заголовков
        
        Raises:
            ValueError: Если иерархия невалидна
        """
        # TODO: Реализовать валидацию иерархии
        pass

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        # TODO: Реализовать __repr__
        return f"ParsedDocument(source={self.source!r}, format={self.format.value!r}, elements={len(self.elements)})"

    def __str__(self) -> str:
        """Человекочитаемое строковое представление."""
        # TODO: Реализовать __str__
        return f"ParsedDocument({self.format.value}, {len(self.elements)} elements)"

    def to_dicts(self) -> List[Dict[str, Any]]:
        """
        Сериализация элементов документа в список словарей.
        
        Returns:
            List[Dict[str, Any]]: Список словарей с данными элементов
        """
        return [element.to_dict() for element in self.elements]

    def to_dict(self) -> Dict[str, Any]:
        """
        Сериализация документа в словарь.
        
        Returns:
            Dict[str, Any]: Словарь с данными документа
        """
        # TODO: Реализовать сериализацию
        return {
            "source": self.source,
            "format": self.format.value,
            "elements": [element.to_dict() for element in self.elements],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ParsedDocument:
        """
        Десериализация документа из словаря.
        
        Args:
            data: Словарь с данными документа
        
        Returns:
            ParsedDocument: Экземпляр документа
        
        Raises:
            ValueError: Если данные невалидны
        """
        # TODO: Реализовать десериализацию
        return cls(
            source=data["source"],
            format=DocumentFormat(data["format"]),
            elements=[Element.from_dict(elem) for elem in data["elements"]],
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """
        Сериализация документа в JSON строку.
        
        Returns:
            str: JSON строка
        """
        # TODO: Реализовать JSON сериализацию
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> ParsedDocument:
        """
        Десериализация документа из JSON строки.
        
        Args:
            json_str: JSON строка
        
        Returns:
            ParsedDocument: Экземпляр документа
        
        Raises:
            ValueError: Если JSON невалиден
        """
        # TODO: Реализовать JSON десериализацию
        data = json.loads(json_str)
        return cls.from_dict(data)


class ElementIdGenerator:
    def __init__(self, start: int = 1, width: int = 8) -> None:
        self._counter = start
        self._width = width  # размерность индекса в знаках

    def next_id(self) -> str:
        value = f"{self._counter:0{self._width}d}"
        self._counter += 1
        return value

    def reset(self, start: int = 1) -> None:
        self._counter = start

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        # TODO: Реализовать __repr__
        return f"ElementIdGenerator(start={self._counter}, width={self._width})"

    def __str__(self) -> str:
        """Человекочитаемое строковое представление."""
        # TODO: Реализовать __str__
        return f"ElementIdGenerator(width={self._width}, current={self._counter})"
