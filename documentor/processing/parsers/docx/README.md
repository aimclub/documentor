# DOCX Parser

Combined approach parser for DOCX documents using OCR, XML parsing, and TOC validation.

## Architecture

The DOCX parser uses a multi-stage approach:

1. **Content Check**: Determine if document is scanned (image-based)
   - If scanned: Convert to PDF and process via PdfParser with OCR
2. **PDF Conversion**: Convert DOCX to PDF for layout detection
3. **Layout Detection**: Use OCR (default: Dots.OCR) to detect Section-header and Caption elements
4. **Text Extraction**: Extract text from PDF using PyMuPDF by bbox coordinates
5. **XML Parsing**: Parse DOCX XML for full content extraction (text, tables, images)
6. **TOC Parsing**: Parse table of contents for header validation
7. **Header Detection**: 
   - Match OCR headers with XML
   - Validate headers via TOC
   - Find missing headers using rules (adaptive thresholds, property matching)
8. **Caption Finding**: Find captions for tables and images from OCR headers/captions
9. **Table Structure Matching**: Match tables by comparing OCR and XML structures
10. **Hierarchy Building**: Build complete document hierarchy
    - Group text blocks
    - Split numbered lists into LIST_ITEM elements
    - Enrich tables and images with caption information
11. **Table Conversion**: Convert XML tables to Pandas DataFrames

## Modules

### `docx_parser.py`
Main DOCX parser class. Orchestrates the complete parsing pipeline.

### `layout_detector.py`
Layout detection processor:
- PDF page rendering
- Layout detection via OCR (default: Dots OCR, supports custom detectors)
- Text extraction from PDF by bbox

### `header_processor.py`
Header processing and level determination:
- Processes headers from OCR
- Determines header levels
- Filters false positives (list items, definitions, etc.)

### `header_finder.py`
Header finding and rules building:
- Finds headers in XML
- Builds header rules from found headers
- Finds missing headers using rules
- Extracts paragraph properties

### `caption_finder.py`
Caption finding for tables and images:
- Finds table captions in OCR headers/captions
- Finds image captions in OCR headers/captions
- Matches tables by structure (OCR vs XML)

### `hierarchy_builder.py`
Document hierarchy building from all elements:
- Groups text blocks
- Splits numbered lists into LIST_ITEM elements
- Links elements to headers
- Handles tables and images with captions
- Determines header levels with priority rules

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

### `converter_wrapper.py`
DOCX to PDF conversion using:
- win32com (Windows)
- docx2pdf
- LibreOffice

### OCR Modules (`ocr/`)
- **`layout_dots.py`**: Dots.OCR integration enum (deprecated, use `documentor.ocr.dots_ocr.types`)

**Note**: Dots OCR specific code has been moved to `documentor/ocr/dots_ocr/`. The `ocr/` directory in DOCX parser contains wrappers for backward compatibility.

## Features

- **Automatic Scanned Document Detection**: Detects image-based DOCX and processes via PdfParser
- **Combined Approach**: OCR + XML + TOC for maximum accuracy
- **Rules-based Missing Header Detection**: Finds headers missed by OCR using adaptive thresholds and property matching
- **Caption Finding**: Automatically finds captions for tables and images from OCR
- **Table Structure Matching**: Validates tables by comparing OCR and XML structures
- **TOC Validation**: Uses table of contents to validate and improve header detection
- **Numbered Header Support**: Supports headers with/without spaces after numbers (e.g., "1Анализ", "1. Анализ")
- **List Item Detection**: Automatically identifies and splits numbered list items
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
