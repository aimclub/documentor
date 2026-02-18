# OCR Services

OCR (Optical Character Recognition) service integrations with support for custom components.

## Architecture

The OCR module uses a modular architecture that allows you to replace individual components with your own implementations:

- **Base Classes** (`base.py`): Abstract interfaces for all OCR operations
- **Dots OCR Implementation** (`dots_ocr/`): Default implementation using Dots.OCR
- **Manager** (`manager.py`): DotsOCRManager for coordinating OCR operations

## Modules

### `base.py`
Base classes for OCR services. Defines common interfaces for OCR providers:
- `BaseLayoutDetector`: Interface for layout detection
- `BaseTextExtractor`: Interface for text extraction
- `BaseTableParser`: Interface for table parsing
- `BaseFormulaExtractor`: Interface for formula extraction
- `BaseOCR`: Interface for OCR operations
- `BaseReadingOrderBuilder`: Interface for reading order building

### `dots_ocr/`
Dots.OCR service integration (default implementation):
- `layout_detector.py`: DotsOCRLayoutDetector - layout detection
- `text_extractor.py`: DotsOCRTextExtractor - text extraction
- `table_parser.py`: DotsOCRTableParser - table parsing
- `formula_extractor.py`: DotsOCRFormulaExtractor - formula extraction
- `client.py`: Direct API client functions
- `prompts.py`: Prompt management
- `html_table_parser.py`: HTML table parsing utilities
- `utils.py`: Utility functions (e.g., markdown cleanup)
- `types.py`: Type definitions (LayoutTypeDotsOCR enum)

### `manager.py`
DotsOCRManager for coordinating OCR operations. Handles:
- Model loading and management
- Task queue management
- Direct API calls
- Configuration loading

## Custom Components

You can replace any OCR component with your own implementation. See [CUSTOM_COMPONENTS_GUIDE.md](../CUSTOM_COMPONENTS_GUIDE.md) for detailed instructions.

**Quick Example:**
```python
from documentor.ocr.base import BaseLayoutDetector
from documentor.processing.parsers.pdf import PdfParser
from PIL import Image

class MyLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image, origin_image=None):
        # Your custom implementation
        return [...]

# Use custom layout detector
parser = PdfParser(layout_detector=MyLayoutDetector())
```

## Default Behavior

If you don't provide custom components, the library uses Dots.OCR by default:
- **Layout Detection**: Dots OCR
- **Text Extraction**: Dots OCR (for scanned PDFs) or PyMuPDF (for text-extractable PDFs)
- **Table Parsing**: Dots OCR HTML tables
- **Formula Extraction**: LaTeX from Dots OCR layout detection

## Usage

### Default (Dots OCR)
```python
from documentor.ocr.manager import DotsOCRManager

manager = DotsOCRManager(auto_load_models=True)
result = manager.detect_layout(image)
```

### Custom Components
```python
from documentor.processing.parsers.pdf import PdfParser
from documentor.ocr.base import BaseLayoutDetector

class MyLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image, origin_image=None):
        # Your implementation
        return [...]

parser = PdfParser(layout_detector=MyLayoutDetector())
```

## Note

Dots.OCR is primarily used for layout detection (block coordinates). Text extraction for PDFs is done via PyMuPDF (for text-extractable PDFs) or from Dots OCR output (for scanned PDFs). For DOCX, text is extracted via PyMuPDF from converted PDF.

All Dots OCR specific code is isolated in the `dots_ocr/` directory, making it easy to replace with custom implementations.

## Docker Deployment

If you're using Dots OCR as the default OCR service, you can deploy it using Docker Compose. See the [main README](../../README.md#docker-deployment-dots-ocr) for a complete example configuration.

**Configuration:**
- Set `ocr_config.yaml` → `dots_ocr` → `endpoint` to your Docker service URL
- Use environment variables for API keys (never hardcode them)
- Adjust GPU settings and memory limits based on your hardware
