# Documentor

A powerful document parsing library that extracts structured content from PDF, DOCX, and Markdown files. Documentor uses a layout-based approach with OCR capabilities to parse documents into a unified hierarchical structure.

## Features

- **Multi-format Support**: Parse PDF, DOCX, and Markdown documents
- **Layout-based Parsing**: Uses Dots.OCR for intelligent layout detection
- **OCR Integration**: Automatic OCR for scanned documents using Qwen2.5
- **Structured Output**: Unified hierarchical structure across all formats
- **Table Extraction**: Automatic conversion to Pandas DataFrames
- **Image Handling**: Extracts and links images with captions
- **TOC Parsing**: Table of Contents parsing for DOCX documents
- **LangChain Integration**: Compatible with LangChain Document format

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from langchain_core.documents import Document
from documentor import Pipeline

# Initialize pipeline
pipeline = Pipeline()

# Create a document
doc = Document(
    page_content="",
    metadata={"source": "path/to/document.pdf"}
)

# Parse the document
parsed_doc = pipeline.parse(doc)

# Access elements
for element in parsed_doc.elements:
    print(f"{element.type}: {element.content[:100]}")
```

## Architecture

### Core Components

- **Pipeline**: Main entry point for document processing
- **Parsers**: Format-specific parsers (PDF, DOCX, Markdown)
- **OCR**: OCR services integration (Dots.OCR, Qwen2.5)
- **Domain Models**: Unified data structures (Element, ParsedDocument)

### Parser Types

1. **PDF Parser**: Layout-based parsing with OCR support
2. **DOCX Parser**: Combined approach (OCR + XML + TOC parsing)
3. **Markdown Parser**: Regex-based parsing with table extraction

## Project Structure

```
documentor/
├── config/          # Configuration files (YAML)
├── core/            # Core utilities (environment loading)
├── domain/          # Domain models (Element, ParsedDocument)
├── exceptions.py    # Custom exceptions
├── llm/             # LLM integration (Qwen, structure validation)
├── ocr/             # OCR services (Dots.OCR, Qwen OCR)
├── pipeline.py      # Main pipeline class
├── processing/      # Document processing modules
│   ├── hierarchy/  # Hierarchy building and validation
│   ├── loader/      # Document loading utilities
│   └── parsers/    # Format-specific parsers
│       ├── docx/   # DOCX parser modules
│       ├── md/     # Markdown parser modules
│       └── pdf/    # PDF parser modules
└── utils/          # Utility functions
```

## Configuration

Configuration files are located in `documentor/config/`:

- `config.yaml`: Main configuration file (contains `pdf_parser` and `docx_parser` sections)
- `llm_config.yaml`: LLM service configuration
- `ocr_config.yaml`: OCR service configuration

## Output Format

All parsers return a unified `ParsedDocument` structure:

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
- `type`: Element type (HEADER_1-6, TEXT, TABLE, IMAGE, etc.)
- `content`: Element content
- `parent_id`: Parent element ID (for hierarchy)
- `metadata`: Additional metadata (bbox, page_num, dataframe, etc.)

## Documentation

See the [documentation](docs/) folder for detailed information about each module.

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]
