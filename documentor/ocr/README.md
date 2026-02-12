# OCR Services

OCR (Optical Character Recognition) service integrations.

## Modules

### `base.py`
Base class for OCR services.

### `dots_ocr.py`
Dots.OCR service integration for layout detection.

### `qwen_ocr.py`
Qwen OCR service for text extraction from images.

### `manager.py`
OCR service manager for coordinating multiple OCR providers.

### `reading_order.py`
Reading order detection and text flow analysis.

## Usage

```python
from documentor.ocr.manager import DotsOCRManager

manager = DotsOCRManager()
result = manager.detect_layout(image)
```
