# DOCX Parser

Combined approach parser for DOCX documents using OCR, XML parsing, and TOC validation.

## Architecture

The DOCX parser uses a multi-stage approach:

1. **Content Check**: Determine if document is scanned (image-based)
2. **PDF Conversion**: Convert DOCX to PDF for layout detection
3. **Layout Detection**: Use Dots.OCR to detect structural elements
4. **Text Extraction**: Extract text from PDF using PyMuPDF
5. **XML Parsing**: Parse DOCX XML for full content extraction
6. **TOC Parsing**: Parse table of contents for header validation
7. **Header Detection**: Combine OCR + XML + TOC for accurate header detection
8. **Hierarchy Building**: Build complete document hierarchy
9. **Table Conversion**: Convert XML tables to Pandas DataFrames

## Modules

### `docx_parser.py`
Main DOCX parser class. Orchestrates the complete parsing pipeline.

### `xml_parser.py`
XML structure parsing for DOCX documents. Extracts:
- Text content
- Tables
- Images
- Element positions

### `toc_parser.py`
Table of Contents parsing. Supports:
- Static text TOC
- TOC styles (TOC1, TOC2, TOC3)
- Hyperlink-based TOC

### `header_finder.py`
Header detection and validation:
- Finds headers in XML
- Validates headers using TOC
- Determines header levels

### `hierarchy_builder.py`
Document hierarchy building from all elements:
- Groups text blocks
- Links elements to headers
- Handles tables and images

### `converter.py`
DOCX to PDF conversion using:
- win32com (Windows)
- docx2pdf
- LibreOffice

### OCR Modules (`ocr/`)
- **`layout_detector.py`**: Layout detection for DOCX
- **`layout_dots.py`**: Dots.OCR integration

## Features

- **Automatic Scanned Document Detection**: Detects image-based DOCX and processes via PdfParser
- **Combined Approach**: OCR + XML + TOC for maximum accuracy
- **TOC Validation**: Uses table of contents to validate and improve header detection
- **Table Extraction**: Converts XML tables to Pandas DataFrames
- **Image Handling**: Extracts images and links them with captions
- **Progress Tracking**: tqdm progress bars for all operations

## Configuration

See `documentor/config/config.yaml` (section `docx_parser`) for configuration options.

## Usage

```python
from documentor.processing.parsers.docx.docx_parser import DocxParser
from langchain_core.documents import Document

parser = DocxParser()
doc = Document(page_content="", metadata={"source": "document.docx"})
parsed = parser.parse(doc)
```
