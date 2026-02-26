# Document Processing

Document processing pipeline and parsers.

## Structure

- **hierarchy/**: Document hierarchy building and validation
- **loader/**: Document loading and format detection
- **parsers/**: Format-specific parsers (PDF, DOCX, Markdown)

## Modules

### Hierarchy (`hierarchy/`)
- `builder.py`: Builds document hierarchy from elements
- `validator.py`: Validates document structure

### Loader (`loader/`)
- `loader.py`: Document loading utilities and format detection

### Parsers (`parsers/`)
- `base.py`: Base parser class
- `docx/`: DOCX parser implementation
- `md/`: Markdown parser implementation
- `pdf/`: PDF parser implementation

## Usage

```python
from documentor.processing.parsers.pdf.pdf_parser import PdfParser
from langchain_core.documents import Document

parser = PdfParser()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```
