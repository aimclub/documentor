# Documentor Documentation

Complete documentation for the Documentor library.

## Overview

Documentor is an open-source library for preprocessing documents before RAG (Retrieval-Augmented Generation). It extracts structured content from PDF, DOCX, and Markdown files and converts them into a unified hierarchical structure.

## Quick Links

- [Main Pipeline Description](Полное%20описание%20нового%20пайплайна%20с%20langchain.md) - General overview of the pipeline
- [PDF Parser](PDF_PARSER.md) - Complete PDF parser documentation
- [DOCX Parser](DOCX_PARSER.md) - Complete DOCX parser documentation
- [Markdown Parser](MARKDOWN_PARSER.md) - Complete Markdown parser documentation
- [Project Structure](STRUCTURE.md) - Project structure and module descriptions
- [Architecture Diagram](architecture_diagram.md) - System architecture and data flow
- [Documentation Status](DOCUMENTATION_STATUS.md) - Status of all documentation files

## Parser Documentation

### PDF Parser

**Approach**: Layout-based parsing with OCR capabilities

**Key Features**:
- Layout detection via Dots.OCR for all pages
- Text extraction via PyMuPDF (for text PDFs) or Qwen2.5 OCR (for scanned PDFs)
- Automatic scanned document detection
- Table parsing via Qwen2.5 with DataFrame conversion
- Image extraction and storage

**Documentation**: [PDF_PARSER.md](PDF_PARSER.md)

### DOCX Parser

**Approach**: Combined approach (OCR layout + XML parsing + TOC validation)

**Key Features**:
- Layout detection via Dots.OCR for Section-header and Caption
- XML parsing for full content extraction
- Table of Contents parsing for header validation
- Automatic scanned document detection with fallback to PdfParser
- Table conversion from XML to DataFrame

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

All configuration is in `documentor/config/config.yaml`:

- `pdf_parser`: PDF parser settings
- `docx_parser`: DOCX parser settings
- `ocr_config.yaml`: OCR service configuration
- `llm_config.yaml`: LLM service configuration

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

## Historical Documents

The following documents are kept for historical reference but are outdated:
- `План_работы_16_01.md` - Historical planning document
- `План_работы.txt` - Historical planning document

For current implementation details, see the parser-specific documentation files.
