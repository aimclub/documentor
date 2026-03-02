# Domain Models

Core domain models and data structures for document representation.

## Models

### `Element`
Represents a single element in a document (header, text block, table, image, etc.).

**Fields:**
- `id`: Unique identifier
- `type`: Element type (ElementType enum)
- `content`: Element content (text, markdown, etc.)
- `parent_id`: Parent element ID for hierarchy
- `metadata`: Additional metadata (bbox, page_num, dataframe, etc.)

### `ParsedDocument`
Complete parsed document structure.

**Fields:**
- `source`: Document source path/URL
- `format`: Document format (DocumentFormat enum)
- `elements`: List of parsed elements
- `metadata`: Document-level metadata

### `DocumentFormat`
Enumeration of supported document formats:
- `MARKDOWN`
- `PDF`
- `DOCX`
- `UNKNOWN`

### `ElementType`
Enumeration of element types:
- `TITLE`, `HEADER_1` through `HEADER_6`
- `TEXT`, `IMAGE`, `TABLE`, `FORMULA`
- `LIST_ITEM`, `CAPTION`, `FOOTNOTE`
- `PAGE_HEADER`, `PAGE_FOOTER`, `LINK`, `CODE_BLOCK`

### `ElementIdGenerator`
Generates unique IDs for document elements.

## Usage

```python
from documentor.domain import DocumentFormat, Element, ElementIdGenerator, ElementType, ParsedDocument

element = Element(
    id="elem_1",
    type=ElementType.HEADER_1,
    content="Introduction",
    metadata={"level": 1, "page_num": 1}
)
```
