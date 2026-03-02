# PDF Parser

Layout-based PDF parser with OCR capabilities and support for custom OCR components.

## Architecture

The PDF parser uses specialized processors in a multi-stage approach:

1. **Text Detection**: Check if PDF has extractable text
2. **Layout Detection**: Use OCR (default: Dots.OCR) with appropriate prompt:
   - Scanned PDFs: Full extraction (layout + text + tables + formulas)
   - Text-extractable PDFs: Layout only
3. **Table Reprocessing** (text-extractable PDFs only): Re-process pages with tables using full extraction to get HTML
4. **Element Filtering**: Remove page headers/footers, side text
5. **Header Analysis**: Determine header levels from layout
6. **Hierarchy Building**: Build document hierarchy around headers
7. **Text Extraction**:
   - Text-extractable PDFs: Extract text using PyMuPDF by bbox coordinates
   - Scanned PDFs: Text from OCR (default: Dots OCR)
8. **Text Block Merging**: Merge close text blocks (up to 3000 chars)
9. **Table Parsing**: Parse tables from OCR HTML (default: Dots OCR)
10. **Formula Extraction**: Extract formulas in LaTeX format (default: Dots OCR)
11. **Image Handling**: Extract and store images in metadata (base64)

## Modules

### `pdf_parser.py`
Main PDF parser class. Orchestrates the complete parsing pipeline using specialized processors.

### `layout_processor.py`
Layout detection and filtering processor:
- Page rendering
- Layout detection via OCR (default: Dots OCR, supports custom detectors)
- Filtering unnecessary elements
- Table reprocessing with full prompt

### `text_extractor.py`
Text extraction processor:
- Text extraction via PyMuPDF (for text-extractable PDFs)
- Text extraction from OCR (default: Dots OCR, supports custom extractors)
- Text block merging

### `table_parser.py`
Table parsing processor:
- Parses tables from OCR HTML (default: Dots OCR, supports custom parsers)
- Stores tables as HTML in element.content
- Stores table images

### `image_processor.py`
Image processing processor:
- Extracts images from PDF
- Stores images in metadata (base64)

### `hierarchy_builder.py`
Hierarchy building processor:
- Analyzes header levels
- Builds document hierarchy
- Creates Element objects

### OCR Modules (`ocr/`)

- **`layout_detector.py`**: Layout detection wrapper (uses Dots.OCR by default, supports custom detectors)
- **`page_renderer.py`**: PDF page rendering with scaling

**Note**: Dots OCR specific code has been moved to `documentor/ocr/dots_ocr/`. The `ocr/` directory in PDF parser contains wrappers for backward compatibility.

## Features

- **Automatic Scanned Document Detection**: Detects scanned PDFs and switches to appropriate prompt
- **Smart Prompt Selection**: Uses different prompts based on PDF type:
  - Scanned PDFs: Full extraction for complete extraction
  - Text-extractable PDFs: Layout only, then reprocesses tables
- **Layout-based Parsing**: Uses OCR layout detection for structure (default: Dots OCR)
- **Header Hierarchy**: Builds complete header hierarchy (levels 1-6)
- **Table Extraction**: Parses tables from OCR HTML and stores as HTML strings in element.content (default: Dots OCR)
- **Formula Extraction**: Extracts formulas in LaTeX format (default: Dots OCR)
- **Image Extraction**: Extracts images and stores in metadata (base64)
- **Specialized Processors**: Modular architecture with separate processors for each task
- **Progress Tracking**: tqdm progress bars for long operations
- **Custom Components Support**: Replace any OCR component with your own implementation

## Configuration

See `documentor/config/config.yaml` (section `pdf_parser`) for configuration options.

## Usage

### Default (Dots OCR)
```python
from documentor.processing.parsers.pdf import PdfParser
from langchain_core.documents import Document

parser = PdfParser()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```

### Custom Components
```python
from documentor.processing.parsers.pdf import PdfParser
from documentor.ocr.base import BaseLayoutDetector, BaseTextExtractor
from langchain_core.documents import Document

# Define custom components
class MyLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image, origin_image=None):
        # Your implementation
        return [...]

class MyTextExtractor(BaseTextExtractor):
    def extract_text(self, image, bbox, category):
        # Your implementation
        return "extracted text"

# Use custom components
parser = PdfParser(
    layout_detector=MyLayoutDetector(),
    text_extractor=MyTextExtractor()
)
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```

For more examples, see [CUSTOM_COMPONENTS_GUIDE.md](../../CUSTOM_COMPONENTS_GUIDE.md).
