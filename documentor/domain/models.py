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

    def _validate_basic_fields(self) -> None:
        """
        Валидация базовых полей элемента (без проверки parent_id).
        
        Raises:
            ValueError: Если базовые поля невалидны
        """
        if not self.id or not isinstance(self.id, str) or not self.id.strip():
            raise ValueError(f"Element id must be a non-empty string, got: {self.id!r}")
        
        if not isinstance(self.type, ElementType):
            raise ValueError(f"Element type must be ElementType, got: {type(self.type).__name__}")
        
        if self.content is None:
            raise ValueError("Element content cannot be None")
        
        if not isinstance(self.content, str):
            raise ValueError(f"Element content must be a string, got: {type(self.content).__name__}")
        
        if not isinstance(self.metadata, dict):
            raise ValueError(f"Element metadata must be a dict, got: {type(self.metadata).__name__}")

    def validate(self) -> None:
        """
        Валидация элемента.
        
        Проверяет:
        - id не пустой
        - type валидный ElementType
        - content не None
        - parent_id валидный (если указан)
        
        Raises:
            ValueError: Если элемент невалиден
        """
        self._validate_basic_fields()
        
        if self.parent_id is not None:
            if not isinstance(self.parent_id, str) or not self.parent_id.strip():
                raise ValueError(f"Element parent_id must be a non-empty string or None, got: {self.parent_id!r}")

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        content_preview = (
            self.content[:50] + "..." if len(self.content) > 50 else self.content
        ).replace("\n", "\\n")
        metadata_str = f", metadata={self.metadata!r}" if self.metadata else ""
        parent_str = f", parent_id={self.parent_id!r}" if self.parent_id else ""
        return (
            f"Element(id={self.id!r}, type={self.type.value!r}, "
            f"content={content_preview!r}{parent_str}{metadata_str})"
        )

    def __str__(self) -> str:
        """Человекочитаемое строковое представление."""
        content_preview = (
            self.content[:30] + "..." if len(self.content) > 30 else self.content
        ).replace("\n", " ")
        parent_info = f" (parent: {self.parent_id})" if self.parent_id else ""
        return f"{self.type.value}[{self.id}]: {content_preview}{parent_info}"

    def to_dict(self) -> Dict[str, Any]:
        """
        Сериализация элемента в словарь.
        
        Returns:
            Dict[str, Any]: Словарь с данными элемента
        """
        result: Dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
        }
        if self.parent_id is not None:
            result["parent_id"] = self.parent_id
        if self.metadata:
            result["metadata"] = self.metadata
        return result

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
            KeyError: Если отсутствуют обязательные поля
        """
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict, got {type(data).__name__}")
        
        required_fields = ["id", "type", "content"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")
        
        try:
            element_type = ElementType(data["type"])
        except ValueError as e:
            raise ValueError(f"Invalid ElementType: {data['type']}") from e
        
        element = cls(
            id=str(data["id"]),
            type=element_type,
            content=str(data["content"]),
            parent_id=str(data["parent_id"]) if data.get("parent_id") is not None else None,
            metadata=dict(data.get("metadata", {})),
        )
        return element

    def to_json(self) -> str:
        """
        Сериализация элемента в JSON строку.
        
        Returns:
            str: JSON строка
        
        Raises:
            TypeError: Если данные не сериализуемы в JSON
        """
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        except TypeError as e:
            raise TypeError(f"Failed to serialize Element to JSON: {e}") from e

    @classmethod
    def from_json(cls, json_str: str) -> Element:
        """
        Десериализация элемента из JSON строки.
        
        Args:
            json_str: JSON строка
        
        Returns:
            Element: Экземпляр элемента
        
        Raises:
            ValueError: Если JSON невалиден или данные некорректны
            json.JSONDecodeError: Если JSON не может быть распарсен
        """
        if not isinstance(json_str, str):
            raise ValueError(f"Expected str, got {type(json_str).__name__}")
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
        
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
        if not self.source or not isinstance(self.source, str) or not self.source.strip():
            raise ValueError(f"Document source must be a non-empty string, got: {self.source!r}")
        
        if not isinstance(self.format, DocumentFormat):
            raise ValueError(f"Document format must be DocumentFormat, got: {type(self.format).__name__}")
        
        if not isinstance(self.elements, list):
            raise ValueError(f"Document elements must be a list, got: {type(self.elements).__name__}")
        
        if not self.elements:
            raise ValueError("Document must contain at least one element")
        
        # Валидация каждого элемента (базовые поля, parent_id проверяется в validate_hierarchy)
        for element in self.elements:
            if not isinstance(element, Element):
                raise ValueError(f"All elements must be Element instances, got: {type(element).__name__}")
            try:
                element._validate_basic_fields()
            except ValueError as e:
                raise ValueError(f"Invalid element {element.id}: {e}") from e
        
        # Проверка уникальности id
        element_ids = [elem.id for elem in self.elements]
        duplicate_ids = [eid for eid in element_ids if element_ids.count(eid) > 1]
        if duplicate_ids:
            raise ValueError(f"Duplicate element ids found: {set(duplicate_ids)}")
        
        # Валидация иерархии
        self.validate_hierarchy()
        
        # Валидация metadata
        if not isinstance(self.metadata, dict):
            raise ValueError(f"Document metadata must be a dict, got: {type(self.metadata).__name__}")

    def validate_hierarchy(self) -> None:
        """
        Валидация иерархии элементов.
        
        Проверяет:
        - все parent_id ссылаются на существующие элементы
        - отсутствие циклов в иерархии
        
        Примечание:
        - Разрешается любая структура заголовков (например, header_1 -> header_2 -> header_1 без родителя)
        - Заголовки могут "сбрасывать" иерархию, создавая новые разделы на том же или более высоком уровне
        
        Raises:
            ValueError: Если иерархия невалидна
        """
        # Создаем индекс элементов по id для быстрого поиска
        element_by_id: Dict[str, Element] = {elem.id: elem for elem in self.elements}
        
        # Проверка ссылок parent_id
        for element in self.elements:
            if element.parent_id is not None:
                if element.parent_id not in element_by_id:
                    raise ValueError(
                        f"Element {element.id} references non-existent parent_id: {element.parent_id}"
                    )
                
                # Проверка на самоссылку
                if element.parent_id == element.id:
                    raise ValueError(f"Element {element.id} cannot be its own parent")
        
        # Проверка на циклы в иерархии (DFS)
        visited: set[str] = set()
        rec_stack: set[str] = set()
        
        def has_cycle(element_id: str) -> bool:
            """Проверяет наличие цикла, начиная с элемента."""
            if element_id in rec_stack:
                return True
            if element_id in visited:
                return False
            
            visited.add(element_id)
            rec_stack.add(element_id)
            
            element = element_by_id[element_id]
            if element.parent_id is not None:
                if has_cycle(element.parent_id):
                    return True
            
            rec_stack.remove(element_id)
            return False
        
        for element in self.elements:
            if element.id not in visited:
                if has_cycle(element.id):
                    raise ValueError(f"Cycle detected in hierarchy starting from element {element.id}")

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        metadata_str = f", metadata={self.metadata!r}" if self.metadata else ""
        return (
            f"ParsedDocument(source={self.source!r}, format={self.format.value!r}, "
            f"elements={len(self.elements)}{metadata_str})"
        )

    def __str__(self) -> str:
        """Человекочитаемое строковое представление."""
        source_name = self.source.split("/")[-1] if "/" in self.source else self.source
        source_name = source_name.split("\\")[-1] if "\\" in source_name else source_name
        return f"ParsedDocument({self.format.value}): {source_name} ({len(self.elements)} elements)"

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
        result: Dict[str, Any] = {
            "source": self.source,
            "format": self.format.value,
            "elements": [element.to_dict() for element in self.elements],
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

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
            KeyError: Если отсутствуют обязательные поля
        """
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict, got {type(data).__name__}")
        
        required_fields = ["source", "format", "elements"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")
        
        if not isinstance(data["elements"], list):
            raise ValueError(f"Elements must be a list, got {type(data['elements']).__name__}")
        
        try:
            document_format = DocumentFormat(data["format"])
        except ValueError as e:
            raise ValueError(f"Invalid DocumentFormat: {data['format']}") from e
        
        try:
            elements = [Element.from_dict(elem) for elem in data["elements"]]
        except (ValueError, KeyError) as e:
            raise ValueError(f"Failed to deserialize elements: {e}") from e
        
        document = cls(
            source=str(data["source"]),
            format=document_format,
            elements=elements,
            metadata=dict(data.get("metadata", {})),
        )
        return document

    def to_json(self) -> str:
        """
        Сериализация документа в JSON строку.
        
        Returns:
            str: JSON строка
        
        Raises:
            TypeError: Если данные не сериализуемы в JSON
        """
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        except TypeError as e:
            raise TypeError(f"Failed to serialize ParsedDocument to JSON: {e}") from e

    @classmethod
    def from_json(cls, json_str: str) -> ParsedDocument:
        """
        Десериализация документа из JSON строки.
        
        Args:
            json_str: JSON строка
        
        Returns:
            ParsedDocument: Экземпляр документа
        
        Raises:
            ValueError: Если JSON невалиден или данные некорректны
            json.JSONDecodeError: Если JSON не может быть распарсен
        """
        if not isinstance(json_str, str):
            raise ValueError(f"Expected str, got {type(json_str).__name__}")
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
        
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
        next_id_preview = f"{self._counter:0{self._width}d}"
        return (
            f"ElementIdGenerator(counter={self._counter}, width={self._width}, "
            f"next_id={next_id_preview!r})"
        )

    def __str__(self) -> str:
        """Человекочитаемое строковое представление."""
        return f"ElementIdGenerator(width={self._width}, next_id={self._counter:0{self._width}d})"
