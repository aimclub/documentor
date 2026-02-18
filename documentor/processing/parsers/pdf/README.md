# PDF Parser

Layout-based PDF parser with OCR capabilities.

## Architecture

The PDF parser uses specialized processors in a multi-stage approach:

1. **Text Detection**: Check if PDF has extractable text
2. **Layout Detection**: Use Dots.OCR with appropriate prompt:
   - Scanned PDFs: `prompt_layout_all_en` (layout + text + tables + formulas)
   - Text-extractable PDFs: `prompt_layout_only_en` (layout only)
3. **Table Reprocessing** (text-extractable PDFs only): Re-process pages with tables using `prompt_layout_all_en` to get HTML
4. **Element Filtering**: Remove page headers/footers, side text
5. **Header Analysis**: Determine header levels from layout
6. **Hierarchy Building**: Build document hierarchy around headers
7. **Text Extraction**:
   - Text-extractable PDFs: Extract text using PyMuPDF by bbox coordinates
   - Scanned PDFs: Text already extracted by Dots OCR (`prompt_layout_all_en`)
8. **Text Block Merging**: Merge close text blocks (up to 3000 chars)
9. **Table Parsing**: Parse tables from Dots OCR HTML
10. **Image Handling**: Extract and store images in metadata (base64)

## Modules

### `pdf_parser.py`
Main PDF parser class. Orchestrates the complete parsing pipeline using specialized processors.

### `layout_processor.py`
Layout detection and filtering processor:
- Page rendering
- Layout detection via Dots OCR
- Filtering unnecessary elements
- Table reprocessing with full prompt

### `text_extractor.py`
Text extraction processor:
- Text extraction via PyMuPDF (for text-extractable PDFs)
- Text extraction from Dots OCR (for scanned PDFs)
- Text block merging

### `table_parser.py`
Table parsing processor:
- Parses tables from Dots OCR HTML
- Converts to pandas DataFrame
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

- **`layout_detector.py`**: Layout detection using Dots.OCR
- **`page_renderer.py`**: PDF page rendering with scaling
- **`dots_ocr_client.py`**: Dots.OCR API client
- **`html_table_parser.py`**: HTML table parsing from Dots OCR

## Features

- **Automatic Scanned Document Detection**: Detects scanned PDFs and switches to appropriate prompt
- **Smart Prompt Selection**: Uses different prompts based on PDF type:
  - Scanned PDFs: `prompt_layout_all_en` for complete extraction
  - Text-extractable PDFs: `prompt_layout_only_en` for layout, then reprocesses tables
- **Layout-based Parsing**: Uses OCR layout detection for structure
- **Header Hierarchy**: Builds complete header hierarchy (levels 1-6)
- **Table Extraction**: Parses tables from Dots OCR HTML and converts to Pandas DataFrames
- **Image Extraction**: Extracts images and stores in metadata (base64)
- **Specialized Processors**: Modular architecture with separate processors for each task
- **Progress Tracking**: tqdm progress bars for long operations

## Configuration

See `documentor/config/config.yaml` (section `pdf_parser`) for configuration options.

## Usage

```python
from documentor.processing.parsers.pdf.pdf_parser import PdfParser
from langchain_core.documents import Document

parser = PdfParser()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```
