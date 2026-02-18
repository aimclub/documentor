# OCR Services

OCR (Optical Character Recognition) service integrations.

## Modules

### `base.py`
Base class for OCR services. Defines common interface for OCR providers.

### `dots_ocr.py`
Dots.OCR service integration for layout detection. Provides functions for loading prompts from configuration and processing layout detection.

### `manager.py`
DotsOCRManager for coordinating OCR operations. Handles:
- Model loading and management
- Task queue management
- Direct API calls
- Configuration loading

## Usage

```python
from documentor.ocr.manager import DotsOCRManager

manager = DotsOCRManager(auto_load_models=True)
result = manager.detect_layout(image)
```

## Note

Dots.OCR is primarily used for layout detection (block coordinates). Text extraction for PDFs is done via PyMuPDF (for text-extractable PDFs) or from Dots OCR output (for scanned PDFs). For DOCX, text is extracted via PyMuPDF from converted PDF.
