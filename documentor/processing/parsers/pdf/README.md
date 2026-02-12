# PDF Parser

Layout-based PDF parser with OCR capabilities.

## Architecture

The PDF parser uses a multi-stage approach:

1. **Text Detection**: Check if PDF has extractable text
2. **Layout Detection**: Use Dots.OCR to detect document structure
3. **Header Analysis**: Determine header levels from layout
4. **Hierarchy Building**: Build document hierarchy around headers
5. **Text Extraction**: Extract text using PyMuPDF or OCR (Qwen2.5)
6. **Table Parsing**: Parse tables using Qwen2.5 with Markdown output
7. **Image Handling**: Extract and link images with captions

## Modules

### `pdf_parser.py`
Main PDF parser class. Implements the complete parsing pipeline.

### `text_extractor.py`
Text extraction utilities for PDF documents.

### OCR Modules (`ocr/`)

- **`layout_detector.py`**: Layout detection using Dots.OCR
- **`page_renderer.py`**: PDF page rendering with scaling
- **`dots_ocr_client.py`**: Dots.OCR API client
- **`qwen_ocr.py`**: Qwen OCR client for text extraction
- **`qwen_table_parser.py`**: Table parsing using Qwen2.5

## Features

- **Automatic Scanned Document Detection**: Detects scanned PDFs and switches to OCR mode
- **Layout-based Parsing**: Uses OCR layout detection for structure
- **Header Hierarchy**: Builds complete header hierarchy (levels 1-6)
- **Table Extraction**: Converts tables to Pandas DataFrames
- **Image Extraction**: Extracts images and links them with captions
- **Progress Tracking**: tqdm progress bars for long operations

## Configuration

See `documentor/config/pdf_config.yaml` for configuration options.

## Usage

```python
from documentor.processing.parsers.pdf.pdf_parser import PdfParser
from langchain_core.documents import Document

parser = PdfParser()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```
