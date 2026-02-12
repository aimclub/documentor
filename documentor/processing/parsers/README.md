# Document Parsers

Format-specific parsers for PDF, DOCX, and Markdown documents.

## Base Parser

### `base.py`
Abstract base class for all parsers. Defines the common interface:
- `parse()`: Parse a document (abstract method)
- `can_parse()`: Check if parser can handle the document
- `get_source()`: Extract document source
- Validation and error handling utilities

## Parser Implementations

### PDF Parser (`pdf/`)
Layout-based PDF parser with OCR support.

**Key Features:**
- Layout detection via Dots.OCR
- Text extraction (PyMuPDF or OCR)
- Table parsing with Qwen2.5
- Automatic scanned document detection
- Header hierarchy building

**Modules:**
- `pdf_parser.py`: Main PDF parser
- `text_extractor.py`: Text extraction utilities
- `ocr/`: OCR-related modules
  - `layout_detector.py`: Layout detection
  - `page_renderer.py`: PDF page rendering
  - `dots_ocr_client.py`: Dots.OCR client
  - `qwen_ocr.py`: Qwen OCR client
  - `qwen_table_parser.py`: Table parsing with Qwen

### DOCX Parser (`docx/`)
Combined approach parser for DOCX documents.

**Key Features:**
- Layout detection (DOCX → PDF → OCR)
- XML parsing for full content extraction
- Table of Contents (TOC) parsing
- Header detection (OCR + XML + TOC validation)
- Automatic scanned document detection

**Modules:**
- `docx_parser.py`: Main DOCX parser
- `xml_parser.py`: XML structure parsing
- `toc_parser.py`: Table of Contents parsing
- `header_finder.py`: Header detection and validation
- `hierarchy_builder.py`: Document hierarchy building
- `converter.py`: DOCX to PDF conversion
- `ocr/`: OCR-related modules for DOCX

### Markdown Parser (`md/`)
Regex-based Markdown parser.

**Key Features:**
- Header parsing (levels 1-6)
- Table extraction to Pandas DataFrame
- List, link, image, and code block support
- Hierarchy building

**Modules:**
- `md_parser.py`: Main Markdown parser
- `tokenizer.py`: Markdown tokenization
- `hierarchy.py`: Hierarchy building for Markdown

## Usage

```python
from documentor.processing.parsers.pdf.pdf_parser import PdfParser
from documentor.processing.parsers.docx.docx_parser import DocxParser
from documentor.processing.parsers.md.md_parser import MarkdownParser

# Initialize parser
parser = PdfParser()  # or DocxParser(), MarkdownParser()

# Parse document
from langchain_core.documents import Document
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```
