# Documentor Documentation

Complete documentation for the Documentor library.

## Overview

Documentor is an open-source library for preprocessing documents before RAG (Retrieval-Augmented Generation). It extracts structured content from PDF, DOCX, and Markdown files and converts them into a unified hierarchical structure.

## Quick Links

- [PDF Parser](PDF_PARSER.md) - Complete PDF parser documentation
- [DOCX Parser](DOCX_PARSER.md) - Complete DOCX parser documentation
- [Markdown Parser](MARKDOWN_PARSER.md) - Complete Markdown parser documentation
- [Project Structure](STRUCTURE.md) - Project structure and module descriptions
- [Architecture Diagram](architecture_diagram.md) - System architecture and data flow

## Parser Documentation

### PDF Parser

**Approach**: Layout-based parsing with specialized processors

**Key Features**:
- Layout detection via Dots.OCR for all pages
- Different prompts for different PDF types:
  - Scanned PDFs: `prompt_layout_all_en` (layout + text + tables + formulas)
  - Text-extractable PDFs: `prompt_layout_only_en` (layout) + table reprocessing with `prompt_layout_all_en`
- Text extraction via PyMuPDF (for text PDFs) or from Dots OCR (for scanned PDFs)
- Automatic scanned document detection
- Table parsing from Dots OCR HTML
- Image extraction and storage
- Specialized processors for modularity (layout, text, tables, images, hierarchy)

**Documentation**: [PDF_PARSER.md](PDF_PARSER.md)

### DOCX Parser

**Approach**: Combined approach (OCR layout + XML parsing + TOC validation)

**Key Features**:
- Layout detection via Dots.OCR for Section-header and Caption
- XML parsing for full content extraction
- Table of Contents parsing for header validation
- Rules-based missing header detection (adaptive thresholds, property matching)
- Caption finding for tables and images from OCR
- Table structure matching (OCR vs XML) for validation
- Automatic scanned document detection with fallback to PdfParser
- Table conversion from XML to DataFrame
- Support for numbered headers with/without spaces
- Automatic list item detection and splitting

**Documentation**: [DOCX_PARSER.md](DOCX_PARSER.md)

### Markdown Parser

**Approach**: Regex-based parsing (no LLM or OCR)

**Key Features**:
- Pure regex-based parsing
- Automatic table conversion to DataFrame
- Nested list support with proper hierarchy
- Header hierarchy building
- Support for code blocks, images, links, quotes

**Documentation**: [MARKDOWN_PARSER.md](MARKDOWN_PARSER.md)

## Architecture

All parsers follow a unified architecture:

1. **Input**: LangChain `Document` with file path or content
2. **Format Detection**: Automatic format detection
3. **Parser Selection**: Appropriate parser is selected
4. **Parsing**: Document is parsed into structured elements
5. **Hierarchy Building**: Elements are organized into hierarchy with `parent_id`
6. **Output**: `ParsedDocument` with unified structure

See [Architecture Diagram](architecture_diagram.md) for detailed system architecture.

## Unified Output Format

All parsers return the same `ParsedDocument` structure:

```python
ParsedDocument(
    source: str,
    format: DocumentFormat,
    elements: List[Element],
    metadata: Dict[str, Any]
)
```

Each `Element` contains:
- `id`: Unique identifier
- `type`: ElementType (HEADER_1-6, TEXT, TABLE, IMAGE, etc.)
- `content`: Element content
- `parent_id`: Parent element ID (for hierarchy)
- `metadata`: Additional metadata (bbox, page_num, dataframe, etc.)

## Configuration

Configuration is in `documentor/config/`:

- `config.yaml` - General settings (pdf_parser, docx_parser)
- `ocr_config.yaml` - OCR service (e.g. Dots.OCR)
- `llm_config.yaml` - LLM service for header detection

## Usage Example

```python
from langchain_core.documents import Document
from documentor import Pipeline

# Initialize pipeline
pipeline = Pipeline()

# Create document
doc = Document(
    page_content="",
    metadata={"source": "path/to/document.pdf"}
)

# Parse document
parsed_doc = pipeline.parse(doc)

# Access elements
for element in parsed_doc.elements:
    print(f"{element.type}: {element.content[:100]}")
```

For implementation details, see the parser-specific documentation files above.
