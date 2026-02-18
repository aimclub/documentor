# LLM Integration

Language Model integration modules for advanced document processing.

## Modules

### `base.py`
Base class for LLM clients. Provides common interface for LLM providers.

### `header_detector.py`
Header detection using LLM for semantic analysis. Currently used for header detection in text documents.

## Usage

```python
from documentor.llm.header_detector import HeaderDetector

detector = HeaderDetector()
headers = detector.detect_headers(document)
```

## Note

Most document structure detection is now handled by Dots.OCR for layout detection. LLM integration is primarily used for semantic header detection when needed.
