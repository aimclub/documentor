# Documentor Project Structure

## General Structure

```
documentor/
├── __init__.py              # Public API of the library
├── pipeline.py              # Main document processing pipeline
├── exceptions.py            # Custom exceptions
│
├── domain/                  # Domain models and data types
│   ├── __init__.py
│   └── models.py            # Element, ParsedDocument, ElementType, DocumentFormat, ElementIdGenerator
│
├── config/                  # Configuration
│   ├── __init__.py
│   ├── config.yaml          # General configuration (pdf_parser, docx_parser)
│   ├── llm_config.yaml      # LLM configuration (YAML)
│   └── ocr_config.yaml      # OCR configuration (YAML)
│
├── core/                    # Core library
│   └── __init__.py
│
├── utils/                   # Utilities
│   ├── __init__.py
│   ├── text_utils.py        # Text processing (chunks, cleaning)
│   ├── ocr_image_utils.py   # Image processing for OCR
│   ├── ocr_layout_utils.py  # Utilities for processing layout results
│   ├── ocr_output_cleaner.py # Cleaning JSON responses from LLM
│   └── ocr_consts.py        # OCR constants
│
├── llm/                     # LLM integration
│   ├── __init__.py
│   ├── header_detector.py  # Header detection via LLM
│   └── base.py              # Base class for LLM clients
│
├── ocr/                     # OCR integration
│   ├── __init__.py
│   ├── base.py              # Base classes for OCR
│   ├── dots_ocr.py         # Integration with Dots.OCR (layout detection)
│   └── manager.py          # Manager for OCR task management (DotsOCRManager)
│
└── processing/              # Document processing
    ├── loader/              # Document format detection
    │   ├── __init__.py
    │   └── loader.py        # detect_document_format, get_document_source
    │
    ├── parsers/             # Parsers for various formats
    │   ├── __init__.py
    │   ├── base.py          # Base class BaseParser
    │   │
    │   ├── md/              # Markdown parser
    │   │   ├── __init__.py
    │   │   ├── md_parser.py # Main Markdown parser
    │   │   ├── tokenizer.py # Markdown tokenization
    │   │   └── hierarchy.py # Hierarchy building for Markdown
    │   │
    │   ├── pdf/             # PDF parser
    │   │   ├── __init__.py
    │   │   ├── pdf_parser.py        # Main PDF parser
    │   │   ├── layout_processor.py   # Layout detection and filtering
    │   │   ├── text_extractor.py    # Text extraction processor
    │   │   ├── table_parser.py       # Table parsing processor
    │   │   ├── image_processor.py    # Image processing processor
    │   │   ├── hierarchy_builder.py  # Hierarchy building processor
    │   │   └── ocr/                 # OCR components for PDF
    │   │       ├── __init__.py
    │   │       ├── layout_detector.py  # Layout detection via Dots.OCR
    │   │       ├── page_renderer.py    # Page rendering to images
    │   │       ├── dots_ocr_client.py  # Direct Dots.OCR API client
    │   │       └── html_table_parser.py # HTML table parsing from Dots OCR
    │   │
    │   └── docx/            # DOCX parser
    │       ├── __init__.py
    │       ├── docx_parser.py         # Main DOCX parser
    │       ├── converter_wrapper.py   # DOCX to PDF conversion
    │       ├── xml_parser.py          # DOCX XML parsing
    │       ├── toc_parser.py          # Table of Contents parsing
    │       ├── header_finder.py       # Header finding and validation
    │       ├── header_processor.py    # Header processing and level determination
    │       ├── layout_detector.py     # Layout detection via Dots OCR
    │       ├── caption_finder.py      # Finding captions for tables and images
    │       ├── hierarchy_builder.py   # Hierarchy building
    │       └── ocr/                   # OCR components (for PDF conversion)
    │           ├── __init__.py
    │           └── layout_dots.py     # LayoutTypeDotsOCR enum (for PDF)
    │
    └── hierarchy/           # Element hierarchy building (NOT USED)
        └── __init__.py      # Hierarchy is built inside each parser
```

## Description of Main Modules

### domain/
Domain models and data types:
- `Element` - document element (id, type, content, parent_id, metadata)
- `ParsedDocument` - parsing result (source, format, elements, metadata)
- `ElementType` - element types (HEADER_1-6, TEXT, TABLE, IMAGE, etc.)
- `DocumentFormat` - document formats (MARKDOWN, PDF, DOCX)
- `ElementIdGenerator` - unique ID generator

### llm/
Large Language Models integration:
- Header detection in text (semantic analysis)
- Document element classification
- Document structure building
- Structure validation via LLM with XML markup (for DOCX)
- Support for various LLM providers (OpenAI, etc.)

### ocr/
Optical Character Recognition integration:
- Layout detection via Dots.OCR (used only for PDF) - block coordinate detection
- Text extraction via PyMuPDF by coordinates from Dots.OCR (used only for PDF)
- Reading order building for elements
- For DOCX, OCR approach is cancelled, used only for PDF

**Important**: Dots.OCR is used ONLY for layout detection (block coordinates). Text is extracted via PyMuPDF, not via OCR LLM.

### processing/parsers/
Parsers for various formats:
- **Markdown**: tokenization, hierarchy building (local parsing, no LLM)
- **PDF**: layout-based approach with specialized processors
  - Layout detection via Dots.OCR for all pages
    - Scanned PDFs: `prompt_layout_all_en` (layout + text + tables + formulas)
    - Text-extractable PDFs: `prompt_layout_only_en` (layout) + table reprocessing with `prompt_layout_all_en`
  - Hierarchy building around Section-header
  - Text extraction:
    - Text-extractable PDFs: via PyMuPDF by coordinates
    - Scanned PDFs: from Dots OCR (`prompt_layout_all_en`)
  - Table parsing from Dots OCR HTML
  - Specialized processors: layout, text, tables, images, hierarchy
- **DOCX**: combined approach
  - Content check (scanned or not)
  - Conversion to PDF for layout detection
  - Layout detection via Dots.OCR (Section-header, Caption)
  - Text extraction via PyMuPDF by coordinates
  - XML parsing for full content (text, tables, images)
  - Table of Contents (TOC) parsing for header validation
  - Header finding and matching (OCR + XML + rules-based search)
  - Caption finding for tables and images (from OCR)
  - Table structure matching (OCR vs XML)
  - Hierarchy building from all elements
  - Table conversion from XML to DataFrame

### processing/hierarchy/
Element hierarchy building (NOT USED):
- Hierarchy is built inside each parser
- Each parser independently assigns parent_id based on headers

## Parser Logic

### Markdown
1. Text tokenization (regex for block type detection)
2. Hierarchy building based on headers (header_stack)
3. parent_id assignment to elements
4. Table conversion to Pandas DataFrame
5. **No LLM required** - fully local parsing

### PDF
1. Check text extractability from PDF
2. **Layout Detection**: page rendering → Dots.OCR layout detection for all pages
   - Scanned PDFs: `prompt_layout_all_en` (layout + text + tables + formulas)
   - Text-extractable PDFs: `prompt_layout_only_en` (layout only)
3. **Table Reprocessing** (text-extractable PDFs only): re-process pages with tables using `prompt_layout_all_en` to get HTML
4. **Filtering**: remove Page-header, Page-footer, side text
5. **Header Level Analysis**: determine levels based on numbering, position, styles
6. **Hierarchy Building**: build hierarchy around Section-header elements
7. **Text Extraction**:
   - For text-extractable PDFs: PyMuPDF by coordinates from Dots.OCR
   - For scanned PDFs: text already in layout elements from Dots OCR (`prompt_layout_all_en`)
8. **Text Block Merging**: merge close blocks (up to 3000 characters)
9. **Table Parsing**: from Dots OCR HTML with DataFrame conversion
10. **Image Storage**: in metadata (base64)

### DOCX
1. **Content Check**: determine scanned document (images vs text)
2. **For scanned DOCX**: convert to PDF → process via PdfParser with OCR
3. **For normal DOCX**:
   - Convert DOCX to PDF for layout detection
   - Layout Detection via Dots.OCR (Section-header, Caption)
   - Extract text from PDF by bbox via PyMuPDF
   - XML parsing for full content (text, tables, images)
   - Table of Contents (TOC) parsing for header validation
   - Find headers in XML (OCR matching + rules-based search + TOC validation)
   - Find missing headers using rules (font properties, style, alignment, etc.)
   - Find table and image captions from OCR headers/captions
   - Match tables by structure comparison (OCR vs XML)
   - Build document hierarchy from all elements
   - Convert tables from XML to DataFrame
   - Enrich tables and images with caption information

## Organization Principles

1. **Separation of Concerns**: each module is responsible for its area
2. **Reusability**: common components (LLM, OCR) are extracted into separate modules
3. **Extensibility**: easy to add new parsers or LLM providers
4. **Testability**: each component can be tested separately
5. **Configuration**: settings in YAML files for easy modification
