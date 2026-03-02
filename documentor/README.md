# Documentor Package

Main package for document parsing and processing.

## Structure

- **config/**: Configuration files (YAML) and ConfigLoader
- **core/**: Core utilities and environment loading (load_env_file)
- **domain/**: Domain models and data structures
- **ocr/**: OCR integrations (base classes, Dots.OCR, cleaning, image, layout)
- **processing/**: Document processing (loader, parsers, hierarchy, headers, image, pdf)

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
- `DocumentorError`: Base exception for all library errors
- `ParsingError`: Errors during document parsing
- `ValidationError`: Input validation errors
- `UnsupportedFormatError`: Unsupported document format
- `OCRError`: OCR service errors
- `LLMError`: LLM service errors

## Usage

### Basic Usage
```python
from documentor import Pipeline
from langchain_core.documents import Document

pipeline = Pipeline()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = pipeline.parse(doc)
```

### Custom OCR Components
The library supports replacing OCR components with your own implementations. See [CUSTOM_COMPONENTS_GUIDE.md](CUSTOM_COMPONENTS_GUIDE.md) for detailed instructions.

**Quick Example:**
```python
from documentor.processing.parsers.pdf import PdfParser
from documentor.ocr.base import BaseLayoutDetector

class MyLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image, origin_image=None):
        # Your custom implementation
        return [...]

parser = PdfParser(layout_detector=MyLayoutDetector())
```
