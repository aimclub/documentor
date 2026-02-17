from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

try:
    import pandas as pd
except ImportError:
    pd = None  # pandas is optional

if TYPE_CHECKING:
    import pandas as pd


class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"
    UNKNOWN = "unknown"


class ElementType(str, Enum):
    TITLE = "title"  # Document title
    HEADER_1 = "header_1"  # Level 1 header
    HEADER_2 = "header_2"  # Level 2 header
    HEADER_3 = "header_3"  # Level 3 header
    HEADER_4 = "header_4"  # Level 4 header
    HEADER_5 = "header_5"  # Level 5 header
    HEADER_6 = "header_6"  # Level 6 header
    TEXT = "text"  # Text content
    IMAGE = "image"  # Image
    TABLE = "table"  # Table
    FORMULA = "formula"  # Formula
    LIST_ITEM = "list_item"  # List item
    CAPTION = "caption"  # Caption
    FOOTNOTE = "footnote"  # Footnote
    PAGE_HEADER = "page_header"  # Page header
    PAGE_FOOTER = "page_footer"  # Page footer
    LINK = "link"  # Link
    CODE_BLOCK = "code_block"  # Code block

@dataclass(slots=True)
class Element:
    id: str
    type: ElementType
    content: str
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate element after initialization."""
        self.validate()

    def _validate_basic_fields(self) -> None:
        """
        Validate basic element fields (without parent_id check).
        
        Raises:
            ValueError: If basic fields are invalid
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
        Validate element.
        
        Checks:
        - id is not empty
        - type is valid ElementType
        - content is not None
        - parent_id is valid (if specified)
        
        Raises:
            ValueError: If element is invalid
        """
        self._validate_basic_fields()
        
        if self.parent_id is not None:
            if not isinstance(self.parent_id, str) or not self.parent_id.strip():
                raise ValueError(f"Element parent_id must be a non-empty string or None, got: {self.parent_id!r}")

    def __repr__(self) -> str:
        """String representation for debugging."""
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
        """Human-readable string representation."""
        content_preview = (
            self.content[:30] + "..." if len(self.content) > 30 else self.content
        ).replace("\n", " ")
        parent_info = f" (parent: {self.parent_id})" if self.parent_id else ""
        return f"{self.type.value}[{self.id}]: {content_preview}{parent_info}"

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize element to dictionary.
        
        Returns:
            Dict[str, Any]: Dictionary with element data
        """
        result: Dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
        }
        if self.parent_id is not None:
            result["parent_id"] = self.parent_id
        if self.metadata:
            # Convert DataFrame to dict for JSON serialization
            metadata_serialized = {}
            for key, value in self.metadata.items():
                if pd is not None and isinstance(value, pd.DataFrame):
                    # Convert DataFrame to dict format
                    metadata_serialized[key] = {
                        "_type": "DataFrame",
                        "data": value.to_dict(orient="records"),
                        "columns": value.columns.tolist(),
                        "index": value.index.tolist(),
                    }
                else:
                    metadata_serialized[key] = value
            result["metadata"] = metadata_serialized
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Element:
        """
        Deserialize element from dictionary.
        
        Args:
            data: Dictionary with element data
        
        Returns:
            Element: Element instance
        
        Raises:
            ValueError: If data is invalid
            KeyError: If required fields are missing
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
        
        # Deserialize metadata, converting DataFrame dicts back to DataFrames
        metadata = {}
        if "metadata" in data:
            for key, value in data["metadata"].items():
                if isinstance(value, dict) and value.get("_type") == "DataFrame" and pd is not None:
                    # Convert dict back to DataFrame
                    try:
                        df = pd.DataFrame(value["data"])
                        if "columns" in value:
                            df.columns = value["columns"]
                        if "index" in value:
                            df.index = value["index"]
                        metadata[key] = df
                    except Exception:
                        # If conversion fails, keep as dict
                        metadata[key] = value
                else:
                    metadata[key] = value
        
        element = cls(
            id=str(data["id"]),
            type=element_type,
            content=str(data["content"]),
            parent_id=str(data["parent_id"]) if data.get("parent_id") is not None else None,
            metadata=metadata,
        )
        return element

    def to_json(self) -> str:
        """
        Serialize element to JSON string.
        
        Returns:
            str: JSON string
        
        Raises:
            TypeError: If data cannot be serialized to JSON
        """
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        except TypeError as e:
            raise TypeError(f"Failed to serialize Element to JSON: {e}") from e

    @classmethod
    def from_json(cls, json_str: str) -> Element:
        """
        Deserialize element from JSON string.
        
        Args:
            json_str: JSON string
        
        Returns:
            Element: Element instance
        
        Raises:
            ValueError: If JSON is invalid or data is incorrect
            json.JSONDecodeError: If JSON cannot be parsed
        """
        if not isinstance(json_str, str):
            raise ValueError(f"Expected str, got {type(json_str).__name__}")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        return cls.from_dict(data)

    @property
    def dataframe(self) -> Optional["pd.DataFrame"]:
        """
        Returns pandas DataFrame for TABLE type elements.

        Returns:
            pandas.DataFrame or None if element is not a table
            or DataFrame was not created during parsing
        """
        if self.type != ElementType.TABLE:
            return None
        return self.metadata.get("dataframe")


@dataclass(slots=True)
class ParsedDocument:
    source: str
    format: DocumentFormat
    elements: List[Element]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate document after initialization."""
        self.validate()

    def validate(self) -> None:
        """
        Validate document.
        
        Checks:
        - source is not empty
        - format is valid DocumentFormat
        - elements is a list
        - hierarchy integrity (parent_id references existing elements)
        - no cycles in hierarchy
        - unique element ids
        
        Raises:
            ValueError: If document is invalid
        """
        if not self.source or not isinstance(self.source, str) or not self.source.strip():
            raise ValueError(f"Document source must be a non-empty string, got: {self.source!r}")
        
        if not isinstance(self.format, DocumentFormat):
            raise ValueError(f"Document format must be DocumentFormat, got: {type(self.format).__name__}")
        
        if not isinstance(self.elements, list):
            raise ValueError(f"Document elements must be a list, got: {type(self.elements).__name__}")
        
        # Allow empty documents (may be valid for some cases)
        # if not self.elements:
        #     raise ValueError("Document must contain at least one element")
        
        # Validate each element (basic fields, parent_id is checked in validate_hierarchy)
        for element in self.elements:
            if not isinstance(element, Element):
                raise ValueError(f"All elements must be Element instances, got: {type(element).__name__}")
            try:
                element._validate_basic_fields()
            except ValueError as e:
                raise ValueError(f"Invalid element {element.id}: {e}") from e
        
        # Check id uniqueness
        element_ids = [elem.id for elem in self.elements]
        duplicate_ids = [eid for eid in element_ids if element_ids.count(eid) > 1]
        if duplicate_ids:
            raise ValueError(f"Duplicate element ids found: {set(duplicate_ids)}")
        
        # Validate hierarchy
        self.validate_hierarchy()
        
        # Validate metadata
        if not isinstance(self.metadata, dict):
            raise ValueError(f"Document metadata must be a dict, got: {type(self.metadata).__name__}")

    def validate_hierarchy(self) -> None:
        """
        Validate element hierarchy.
        
        Checks:
        - all parent_id references point to existing elements
        - no cycles in hierarchy
        
        Note:
        - Any header structure is allowed (e.g., header_1 -> header_2 -> header_1 without parent)
        - Headers can "reset" hierarchy, creating new sections at the same or higher level
        
        Raises:
            ValueError: If hierarchy is invalid
        """
        # Create element index by id for fast lookup
        element_by_id: Dict[str, Element] = {elem.id: elem for elem in self.elements}
        
        # Check parent_id references
        for element in self.elements:
            if element.parent_id is not None:
                if element.parent_id not in element_by_id:
                    raise ValueError(
                        f"Element {element.id} references non-existent parent_id: {element.parent_id}"
                    )
                
                # Check for self-reference
                if element.parent_id == element.id:
                    raise ValueError(f"Element {element.id} cannot be its own parent")
        
        # Check for cycles in hierarchy (DFS)
        visited: set[str] = set()
        rec_stack: set[str] = set()
        
        def has_cycle(element_id: str) -> bool:
            """Check for cycle starting from element."""
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
        """String representation for debugging."""
        metadata_str = f", metadata={self.metadata!r}" if self.metadata else ""
        return (
            f"ParsedDocument(source={self.source!r}, format={self.format.value!r}, "
            f"elements={len(self.elements)}{metadata_str})"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        source_name = self.source.split("/")[-1] if "/" in self.source else self.source
        source_name = source_name.split("\\")[-1] if "\\" in source_name else source_name
        return f"ParsedDocument({self.format.value}): {source_name} ({len(self.elements)} elements)"

    def to_dicts(self) -> List[Dict[str, Any]]:
        """
        Serialize document elements to list of dictionaries.
        
        Returns:
            List[Dict[str, Any]]: List of dictionaries with element data
        """
        return [element.to_dict() for element in self.elements]

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize document to dictionary.
        
        Returns:
            Dict[str, Any]: Dictionary with document data
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
        Deserialize document from dictionary.
        
        Args:
            data: Dictionary with document data
        
        Returns:
            ParsedDocument: Document instance
        
        Raises:
            ValueError: If data is invalid
            KeyError: If required fields are missing
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
        Serialize document to JSON string.
        
        Returns:
            str: JSON string
        
        Raises:
            TypeError: If data cannot be serialized to JSON
        """
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        except TypeError as e:
            raise TypeError(f"Failed to serialize ParsedDocument to JSON: {e}") from e

    @classmethod
    def from_json(cls, json_str: str) -> ParsedDocument:
        """
        Deserialize document from JSON string.
        
        Args:
            json_str: JSON string
        
        Returns:
            ParsedDocument: Document instance
        
        Raises:
            ValueError: If JSON is invalid or data is incorrect
            json.JSONDecodeError: If JSON cannot be parsed
        """
        if not isinstance(json_str, str):
            raise ValueError(f"Expected str, got {type(json_str).__name__}")
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
        
        return cls.from_dict(data)

    def get_elements_by_type(self, element_type: ElementType) -> List[Element]:
        """
        Returns all elements of the specified type.

        Args:
            element_type: Element type to search for

        Returns:
            List of elements of the specified type
        """
        return [elem for elem in self.elements if elem.type == element_type]

    def get_tables(self) -> List[Element]:
        """
        Returns all table elements.

        Returns:
            List of TABLE type elements
        """
        return self.get_elements_by_type(ElementType.TABLE)

    def get_headers(self, level: Optional[int] = None) -> List[Element]:
        """
        Returns all headers, optionally filtered by level.

        Args:
            level: Header level (1-6). If None, returns all headers.

        Returns:
            List of header elements
        """
        if level is None:
            header_types = [
                ElementType.HEADER_1,
                ElementType.HEADER_2,
                ElementType.HEADER_3,
                ElementType.HEADER_4,
                ElementType.HEADER_5,
                ElementType.HEADER_6,
            ]
            return [elem for elem in self.elements if elem.type in header_types]
        else:
            if not 1 <= level <= 6:
                raise ValueError(f"Header level must be between 1 and 6, got: {level}")
            header_type = ElementType[f"HEADER_{level}"]
            return self.get_elements_by_type(header_type)


class ElementIdGenerator:
    def __init__(self, start: int = 1, width: int = 8) -> None:
        self._counter = start
        self._width = width  # Index width in characters

    def next_id(self) -> str:
        value = f"{self._counter:0{self._width}d}"
        self._counter += 1
        return value

    def reset(self, start: int = 1) -> None:
        self._counter = start

    def __repr__(self) -> str:
        """String representation for debugging."""
        next_id_preview = f"{self._counter:0{self._width}d}"
        return (
            f"ElementIdGenerator(counter={self._counter}, width={self._width}, "
            f"next_id={next_id_preview!r})"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"ElementIdGenerator(width={self._width}, next_id={self._counter:0{self._width}d})"
