# Complete Pipeline Description with LangChain

## Introduction

Documentor is an open-source library for preprocessing documents before RAG (Retrieval-Augmented Generation). It extracts structured content from PDF, DOCX, and Markdown files and converts them into a unified hierarchical structure.

## Usage Concept

Input: LangChain `Document` object. Output: Structured `ParsedDocument` with hierarchical elements.

```python
from langchain_core.documents import Document
from documentor import Pipeline

# Initialize pipeline
pipeline = Pipeline()

# Create document
document = Document(
    page_content="",
    metadata={"source": "path/to/document.pdf"}
)

# Parse document
result = pipeline.parse(document)

# Access parsed elements
for element in result.elements:
    print(f"{element.type}: {element.content[:100]}")
```

## Output Structure Example

```python
ParsedDocument(
    source: "path/to/document.pdf",
    format: DocumentFormat.PDF,
    elements: [
        Element(
            id="00000001",
            type=ElementType.HEADER_1,
            content="Introduction",
            parent_id=None,
            metadata={
                "level": 1,
                "page_num": 1,
                "bbox": [72, 100, 500, 130],
                "source": "pymupdf"
            }
        ),
        Element(
            id="00000002",
            type=ElementType.TEXT,
            content="This is a paragraph of text...",
            parent_id="00000001",
            metadata={
                "page_num": 1,
                "bbox": [72, 140, 500, 200],
                "source": "pymupdf"
            }
        ),
        Element(
            id="00000003",
            type=ElementType.TABLE,
            content="| Header 1 | Header 2 |\n|----------|----------|\n| Data 1   | Data 2   |",
            parent_id="00000001",
            metadata={
                "page_num": 2,
                "bbox": [72, 250, 500, 350],
                "dataframe": <pandas.DataFrame>,
                "rows_count": 1,
                "cols_count": 2,
                "source": "ocr"
            }
        ),
        Element(
            id="00000004",
            type=ElementType.IMAGE,
            content="Figure 1: Architecture diagram",
            parent_id="00000001",
            metadata={
                "page_num": 2,
                "bbox": [72, 400, 500, 600],
                "image_path": "path/to/image.png",
                "caption": "Figure 1: Architecture diagram",
                "source": "xml"
            }
        )
    ],
    metadata={
        "parser": "pdf",
        "status": "completed",
        "processing_method": "layout_based",
        "total_pages": 45,
        "elements_count": 189,
        "headers_count": 12,
        "tables_count": 5,
        "images_count": 8
    }
)
```

**Notes**:
- `id`: Unique identifier; each next element increments by 1 (format: "00000001", "00000002", etc.)
- `parent_id`: Reference to parent element in hierarchy (e.g., paragraph belongs to nearest header)
- `metadata`: Additional fields (element type, image, coordinates, page number, DataFrame, etc.)
- All parsers return the same unified structure

## Supported Formats

### Currently Supported
- **DOCX** - Microsoft Word documents
- **PDF** - Portable Document Format (text and scanned)
- **Markdown** - Markdown text files

### Planned for Future
- DOC (via conversion to DOCX)
- TXT (plain text)
- Excel (spreadsheets)

## General Pipeline Description

The pipeline follows these steps:

1. **Input**: User provides document(s) in selected formats as LangChain `Document` objects
2. **Format Detection**: Automatically detect source format (PDF/Markdown/DOCX)
3. **Parser Selection**: Select appropriate parser based on format
4. **Parsing**: Extract structure and content using format-specific parser
5. **Normalization**: Convert results from different parsers to unified element format (with `id`, `parent_id`, `metadata`, etc.)
6. **Output**: Return `ParsedDocument` with structured hierarchical elements

## Parser Descriptions

> 📖 **Detailed Documentation**: See separate documents for each parser:
> - [PDF Parser](PDF_PARSER.md) - Layout-based approach with OCR
> - [DOCX Parser](DOCX_PARSER.md) - Combined approach (OCR + XML + TOC)
> - [Markdown Parser](MARKDOWN_PARSER.md) - Regex-based parsing

### Markdown Parser

Markdown is parsed without LLM, using regular expressions.

**Process**:
1. Extract `page_content` from LangChain `Document` (or load from file if empty)
2. Parse using regular expressions:
   - Headers by `#` count (HEADER_1-6)
   - Tables by `| ... |` with automatic conversion to DataFrame
   - Lists with nesting support
   - Quotes, code blocks, images, links
3. Build hierarchy (headers → nested blocks, lists → nested elements)

**Features**:
- Fully local parsing (no LLM or OCR required)
- Automatic table conversion to pandas DataFrame
- Nested list support with proper hierarchy
- Header hierarchy building

📖 **Detailed Documentation**: [MARKDOWN_PARSER.md](MARKDOWN_PARSER.md)

### PDF Parser

> 📖 **Detailed Documentation**: [PDF_PARSER.md](PDF_PARSER.md)

PDF parser uses **layout-based approach** for all documents.

#### Layout-based Approach (Always Used)

The PDF parser uses layout-based approach for all documents:

1. **Text Extractability Check**: Determine if text can be extracted from PDF
2. **Layout Detection**: Detect page structure using Dots.OCR layout detection for all pages (get block coordinates: Section-header, Text, Table, Picture, Caption, etc.)
3. **Element Filtering**: Remove unnecessary elements (Page-header, Page-footer, side text)
4. **Header Level Analysis**: Determine header levels based on numbering, position, and styles
5. **Hierarchy Building**: Build hierarchy around Section-header elements
6. **Text Extraction**: 
   - For text-extractable PDFs: Extract text via PyMuPDF by coordinates from Dots.OCR
   - For scanned PDFs: Text already extracted by Dots OCR (`prompt_layout_all_en`)
7. **Text Block Merging**: Merge close text blocks (up to 3000 characters)
8. **Table Parsing**: Parse tables from Dots OCR HTML with conversion to Pandas DataFrame
9. **Image Storage**: Store images in metadata (base64)

**Important**: 
- Dots.OCR is used for layout detection and block coordinates
- Different prompts for different PDF types:
  - Scanned PDFs: `prompt_layout_all_en` (layout + text + tables + formulas)
  - Text-extractable PDFs: `prompt_layout_only_en` (layout) + table reprocessing with `prompt_layout_all_en`
- For text-extractable PDFs, text is extracted via PyMuPDF by coordinates from Dots.OCR
- For scanned PDFs, text is already extracted by Dots OCR (`prompt_layout_all_en`)
- Tables are parsed from HTML provided by Dots OCR, not via separate OCR service
- Layout-based approach is always used, regardless of whether text can be extracted from PDF

### DOCX Parser

> 📖 **Detailed Documentation**: [DOCX_PARSER.md](DOCX_PARSER.md)

DOCX parser uses **combined approach** (OCR layout + XML parsing + TOC validation).

**Main Steps**:
1. **Content Check**: Determine if document is scanned (mostly images, little text)
2. **PDF Conversion**: If document is not scanned, convert DOCX to PDF for layout detection
3. **Layout Detection**: Use Dots.OCR to detect structural elements (Section-header, Caption)
4. **Text Extraction**: Extract text from PDF by coordinates via PyMuPDF (for Section-header and Caption)
5. **XML Parsing**: Parse DOCX XML to extract full content (text, tables, images)
6. **Table of Contents (TOC) Parsing**: Parse TOC for validation and improving header detection
7. **Hierarchy Building**: Combine OCR, XML, and TOC results to build complete document hierarchy
8. **Table Conversion**: Convert tables from XML to Pandas DataFrame

**Important**: 
- Dots.OCR is used for layout detection and block coordinates (Section-header, Caption)
- Text is extracted via PyMuPDF by coordinates from Dots.OCR
- For scanned DOCX, document is automatically converted to PDF and processed via PdfParser with OCR

**Automatic Scanned DOCX Detection**:
- Analyzes ratio of text to images
- If text is absent or images are many, document is considered scanned
- Scanned DOCX are processed via PdfParser with full OCR pipeline

#### Structural Elements (Images/Tables/Formulas)

Correct linking of "caption → object" within text and preserving order is important.

- **Images**: Possible issue with order. For example, document has Fig. 1, Fig. 2, Fig. 3, but order in DOCX may not match visual order. This can result in incorrect correspondence:
  - Fig. 3 → Fig. 1
  - Fig. 1 → Fig. 2
  - Fig. 2 → Fig. 3

  **Result**: Lost sequence of images and caption linking.

  **Requirement**: Solve the problem in the most efficient way; if not possible, match objects by page (visually) and/or by context around caption.

- **Formulas**: Need to think about formula extraction (OMML/MathML, or recognition by image).
- **Tables**: Need to choose extraction strategy (structure, merged cells, captions, export to HTML/Markdown).

### DOC (Future)

In theory, on Windows you can automatically convert `doc → docx`. If this works stably, we'll add this option.

## Implemented Features

1. ✅ **Combined approach for DOCX**: OCR (layout detection) + XML parsing + TOC validation
2. ✅ **Layout-based approach for PDF**: Dots.OCR for layout detection + PyMuPDF for text extraction
3. ✅ **Automatic scanned document detection**: for DOCX and PDF
4. ✅ **Table parsing**: all tables converted to Pandas DataFrame
5. ✅ **Metadata unification**: uniform structure for all parsers
6. ✅ **Table of Contents parsing**: for DOCX documents
7. ✅ **Progress tracking**: tqdm progress bars for long operations
8. ✅ **Configuration management**: all parameters configurable via YAML files
9. ✅ **Skip title page**: option to skip first page for documents with title pages

## Planned Improvements

1. **Link resolution**: Linking references to structural elements within text (see Fig. 1, see Table 2)
2. **Header level detection**: Improve header level determination
3. **Performance optimization**: For large documents
4. **Extended Markdown support**: GFM (GitHub Flavored Markdown)
5. **Deterministic identifiers**: Generate `id` by order + hash(source, page, bbox) for stability
6. **Quality assessment**: Metrics and test corpora for pipeline comparison (precision/recall for headers)

## Research Topics and Additional Studies

1. **Link resolution**: Linking references to structural elements within text (see Fig. 1 → output image id or caption)
2. **Formula parsing by image**: Formats and tools (OMML/MathML)
3. **Header level detection improvement**: By metadata (size, font type, bold, etc.)
4. **OCR performance optimization**: For large documents (batching, caching)
5. **Complex table processing**: With merged cells

## Implemented Improvements

1. ✅ **Unified output contract**: All parsers return the same `Element` structure with fields `id`, `parent_id`, `content`, `type`, `metadata`
2. ✅ **Element metadata**: Standardized for all parsers (see `documentor/ELEMENT_METADATA_STANDARD.md`)
3. ✅ **Reading order**: For layout-based approach, store `page_num` and block coordinates (bbox)
4. ✅ **Tables in DataFrame**: All tables converted to Pandas DataFrame and stored in metadata
5. ✅ **Configuration**: All parameters configurable via YAML configuration files
6. ✅ **Progress visualization**: tqdm progress bars for user feedback
7. ✅ **Error handling**: Comprehensive error handling with custom exceptions

## Configuration

All configuration is in `documentor/config/config.yaml`:

- `pdf_parser`: PDF parser settings (layout detection, filtering, table parsing, header analysis)
- `docx_parser`: DOCX parser settings (layout detection, scanned detection, hierarchy building)
- `ocr_config.yaml`: OCR service configuration (Dots.OCR)
- `llm_config.yaml`: LLM service configuration

See [Configuration README](../documentor/config/README.md) for detailed configuration options.

## Architecture

See [Architecture Diagram](architecture_diagram.md) for detailed system architecture, data structures, and processing flows.

## Testing

Test files are located in:
- `tests/` - Unit and integration tests
- `tests/files_for_tests/` - Test document files
- `experiments/pdf_text_extraction/test_files/` - Experimental test files

Run tests:
```bash
pytest tests/
```

## Examples

See [README](README.md) for usage examples and quick start guide.
