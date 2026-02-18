# Documentor

A powerful document parsing library that extracts structured content from PDF, DOCX, and Markdown files. Documentor uses a layout-based approach with OCR capabilities to parse documents into a unified hierarchical structure.

## Features

- **Multi-format Support**: Parse PDF, DOCX, and Markdown documents
- **Layout-based Parsing**: Uses Dots.OCR for intelligent layout detection
- **Smart OCR Integration**: 
  - Different prompts for different PDF types (scanned vs text-extractable)
  - Text extraction from Dots OCR for scanned PDFs
  - PyMuPDF extraction for text-extractable PDFs
- **Structured Output**: Unified hierarchical structure across all formats
- **Table Extraction**: 
  - PDF: Parsing from Dots OCR HTML
  - DOCX: Conversion from XML to Pandas DataFrames
  - Markdown: Automatic conversion to DataFrames
- **Image Handling**: Extracts and links images with captions
- **Advanced Header Detection**:
  - DOCX: OCR + XML + TOC validation + rules-based missing header detection
  - PDF: Layout-based with level analysis
  - Markdown: Regex-based parsing
- **Caption Finding**: Automatic caption detection for tables and images (DOCX)
- **Table Structure Matching**: Validates tables by comparing OCR and XML structures (DOCX)
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
- **OCR**: OCR services integration (Dots.OCR)
- **Domain Models**: Unified data structures (Element, ParsedDocument)

### Parser Types

1. **PDF Parser**: 
   - Layout-based parsing with specialized processors
   - Different prompts for scanned vs text-extractable PDFs
   - Table parsing from Dots OCR HTML
   - Specialized processors: layout, text, tables, images, hierarchy

2. **DOCX Parser**: 
   - Combined approach (OCR + XML + TOC parsing)
   - Rules-based missing header detection
   - Caption finding for tables and images
   - Table structure matching (OCR vs XML)

3. **Markdown Parser**: 
   - Regex-based parsing (no LLM or OCR)
   - Table extraction to DataFrames
   - Nested list support with proper hierarchy

## Project Structure

```
documentor/
├── config/          # Configuration files (YAML)
├── core/            # Core utilities (environment loading)
├── domain/          # Domain models (Element, ParsedDocument)
├── exceptions.py    # Custom exceptions
├── llm/             # LLM integration (header detection, structure validation)
├── ocr/             # OCR services (Dots.OCR manager)
├── pipeline.py      # Main pipeline class
├── processing/      # Document processing modules
│   ├── loader/      # Document loading utilities
│   └── parsers/    # Format-specific parsers
│       ├── docx/   # DOCX parser modules
│       │   ├── docx_parser.py
│       │   ├── layout_detector.py
│       │   ├── header_processor.py
│       │   ├── header_finder.py
│       │   ├── caption_finder.py
│       │   ├── hierarchy_builder.py
│       │   ├── xml_parser.py
│       │   ├── toc_parser.py
│       │   └── converter_wrapper.py
│       ├── md/     # Markdown parser modules
│       │   ├── md_parser.py
│       │   ├── tokenizer.py
│       │   └── hierarchy.py
│       └── pdf/    # PDF parser modules
│           ├── pdf_parser.py
│           ├── layout_processor.py
│           ├── text_extractor.py
│           ├── table_parser.py
│           ├── image_processor.py
│           ├── hierarchy_builder.py
│           └── ocr/  # OCR components
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
