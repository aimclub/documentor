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
Layout-based PDF parser with specialized processors.

**Key Features:**
- Layout detection via Dots.OCR with different prompts:
  - Scanned PDFs: `prompt_layout_all_en` (layout + text + tables + formulas)
  - Text-extractable PDFs: `prompt_layout_only_en` (layout) + table reprocessing
- Text extraction:
  - Text-extractable PDFs: PyMuPDF by bbox coordinates
  - Scanned PDFs: Text from Dots OCR (`prompt_layout_all_en`)
- Table parsing from Dots OCR HTML
- Automatic scanned document detection
- Header hierarchy building
- Specialized processors for modularity

**Modules:**
- `pdf_parser.py`: Main PDF parser (orchestrates processors)
- `layout_processor.py`: Layout detection and filtering processor
- `text_extractor.py`: Text extraction processor
- `table_parser.py`: Table parsing processor (from HTML)
- `image_processor.py`: Image processing processor
- `hierarchy_builder.py`: Hierarchy building processor
- `ocr/`: OCR-related modules
  - `layout_detector.py`: Layout detection
  - `page_renderer.py`: PDF page rendering
  - `dots_ocr_client.py`: Dots.OCR API client
  - `html_table_parser.py`: HTML table parsing from Dots OCR

### DOCX Parser (`docx/`)
Combined approach parser for DOCX documents.

**Key Features:**
- Layout detection (DOCX → PDF → OCR) for Section-header and Caption
- XML parsing for full content extraction
- Table of Contents (TOC) parsing for header validation
- Header detection:
  - OCR headers matched with XML
  - TOC validation
  - Rules-based missing header detection (adaptive thresholds, property matching)
- Caption finding for tables and images from OCR
- Table structure matching (OCR vs XML) for validation
- Automatic scanned document detection with fallback to PdfParser
- Support for numbered headers with/without spaces
- Automatic list item detection and splitting

**Modules:**
- `docx_parser.py`: Main DOCX parser (orchestrates pipeline)
- `layout_detector.py`: Layout detection via Dots OCR
- `header_processor.py`: Header processing and level determination
- `header_finder.py`: Header finding and rules building
- `caption_finder.py`: Finding captions for tables and images
- `hierarchy_builder.py`: Document hierarchy building
- `xml_parser.py`: XML structure parsing
- `toc_parser.py`: Table of Contents parsing
- `converter_wrapper.py`: DOCX to PDF conversion
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
