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
Layout-based PDF parser with specialized processors and support for custom OCR components.

**Key Features:**
- Layout detection via OCR (default: Dots.OCR) with different prompts:
  - Scanned PDFs: Full extraction (layout + text + tables + formulas)
  - Text-extractable PDFs: Layout only + table reprocessing
- Text extraction:
  - Text-extractable PDFs: PyMuPDF by bbox coordinates
  - Scanned PDFs: Text from OCR (default: Dots OCR)
- Table parsing from OCR HTML (default: Dots OCR)
- Formula extraction in LaTeX format (default: Dots OCR)
- Automatic scanned document detection
- Header hierarchy building
- Specialized processors for modularity
- **Custom Components Support**: Replace any OCR component with your own implementation

**Custom Components:**
The PDF parser supports replacing OCR components via constructor parameters:
- `layout_detector`: Custom layout detector implementing `BaseLayoutDetector`
- `text_extractor`: Custom text extractor implementing `BaseTextExtractor`
- `table_parser`: Custom table parser implementing `BaseTableParser`
- `formula_extractor`: Custom formula extractor implementing `BaseFormulaExtractor`

See [CUSTOM_COMPONENTS_GUIDE.md](../../CUSTOM_COMPONENTS_GUIDE.md) for detailed instructions.

**Modules:**
- `pdf_parser.py`: Main PDF parser (orchestrates processors, supports custom OCR components)
- `layout_processor.py`: Layout detection and filtering processor
- `text_extractor.py`: Text extraction processor
- `table_parser.py`: Table parsing processor (from HTML)
- `image_processor.py`: Image processing processor
- `hierarchy_builder.py`: Hierarchy building processor
- `ocr/`: OCR-related modules (wrappers for backward compatibility)
  - `layout_detector.py`: Layout detection wrapper
  - `page_renderer.py`: PDF page rendering

**Note**: Dots OCR specific code has been moved to `documentor/ocr/dots_ocr/`. The `ocr/` directory in PDF parser contains wrappers for backward compatibility.

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
- `layout_detector.py`: Layout detection via OCR (default: Dots OCR, supports custom detectors)
- `header_processor.py`: Header processing and level determination
- `header_finder.py`: Header finding and rules building
- `caption_finder.py`: Finding captions for tables and images
- `hierarchy_builder.py`: Document hierarchy building
- `xml_parser.py`: XML structure parsing
- `toc_parser.py`: Table of Contents parsing
- `converter_wrapper.py`: DOCX to PDF conversion
- `ocr/`: OCR-related modules for DOCX (wrappers for backward compatibility)

**Note**: Dots OCR specific code has been moved to `documentor/ocr/dots_ocr/`. The `ocr/` directory in DOCX parser contains wrappers for backward compatibility.

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
