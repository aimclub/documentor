# Document Processing

Document processing pipeline and parsers.

## Structure

- **loader/**: Document format detection and source resolution
- **parsers/**: Format-specific parsers (PDF, DOCX, Markdown)
- **hierarchy/**: Shared hierarchy utilities (hierarchy is built inside each parser)
- **headers/**: Header-related constants and helpers
- **image/**: Image processing utilities
- **pdf/**: PDF text extraction utilities

## Modules

### Loader (`loader/`)
- `loader.py`: `detect_document_format()`, `get_document_source()` for LangChain Document

### Parsers (`parsers/`)
- `base.py`: Base parser class
- `pdf/`: PDF parser (layout-based, custom OCR components supported)
- `docx/`: DOCX parser (OCR + XML + TOC)
- `md/`: Markdown parser (regex-based)

### Hierarchy (`hierarchy/`)
Shared utilities; actual hierarchy building is done inside each parser (see parsers' hierarchy_builder or hierarchy modules).

## Usage

```python
from documentor.processing.parsers.pdf import PdfParser
from langchain_core.documents import Document

parser = PdfParser()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```
