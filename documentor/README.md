# Documentor Package

Main package for document parsing and processing.

## Structure

- **config/**: Configuration files (YAML format)
- **core/**: Core utilities and environment management
- **domain/**: Domain models and data structures
- **llm/**: LLM integration modules
- **ocr/**: OCR service integrations
- **processing/**: Document processing pipeline
- **utils/**: Utility functions and helpers

## Key Modules

### Pipeline (`pipeline.py`)
Main entry point for document processing. Handles format detection, parser selection, and error handling.

### Domain Models (`domain/models.py`)
Core data structures:
- `Element`: Represents a document element (header, text, table, etc.)
- `ParsedDocument`: Complete parsed document with elements and metadata
- `DocumentFormat`: Supported document formats enum
- `ElementType`: Types of document elements

### Exceptions (`exceptions.py`)
Custom exceptions for error handling:
- `ParsingError`: Errors during document parsing
- `ValidationError`: Input validation errors
- `UnsupportedFormatError`: Unsupported document format

## Usage

```python
from documentor import Pipeline
from langchain_core.documents import Document

pipeline = Pipeline()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = pipeline.parse(doc)
```
