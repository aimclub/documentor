# Custom Components Quick Start

This guide shows you how to replace OCR components in Documentor with your own implementations.

## Quick Example: Replace Layout Detector

```python
from documentor.ocr.base import BaseLayoutDetector
from documentor.processing.parsers.pdf import PdfParser
from PIL import Image
from typing import List, Dict, Any, Optional

class MyLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image: Image.Image, origin_image=None) -> List[Dict[str, Any]]:
        # Your OCR model call here
        return [
            {
                "bbox": [100, 100, 500, 150],
                "category": "Title",
                "text": "Document Title"
            }
        ]

# Use it
parser = PdfParser(layout_detector=MyLayoutDetector())
```

## Quick Example: Replace Text Extractor for Scanned PDFs

```python
from documentor.ocr.base import BaseTextExtractor
from documentor.processing.parsers.pdf import PdfParser
from PIL import Image
from typing import List

class MyTextExtractor(BaseTextExtractor):
    def extract_text(self, image: Image.Image, bbox: List[float], category: str) -> str:
        # Your OCR model call here
        return "extracted text"

# Use it - layout detection will still use Dots OCR
parser = PdfParser(text_extractor=MyTextExtractor())
```

## Available Components

You can replace any of these components:

- **`layout_detector`** - Detects page structure (headers, text blocks, tables, images)
- **`text_extractor`** - Extracts text from image regions
- **`table_parser`** - Parses tables from images
- **`formula_extractor`** - Extracts formulas in LaTeX format

## Default Behavior

If you don't provide custom components, the library uses **Dots OCR by default**:

- **Layout Detection**: Dots OCR
- **Text Extraction**: Dots OCR (for scanned PDFs) or PyMuPDF (for text-extractable PDFs)
- **Table Parsing**: Dots OCR HTML tables
- **Formula Extraction**: LaTeX from Dots OCR layout detection

**For formulas specifically**: If you don't provide `formula_extractor`, formulas will use the text from your layout detector:
- Default layout detector (Dots OCR) → formulas from Dots OCR
- Custom layout detector → formulas from your custom detector

**What if your layout detector doesn't extract formulas or tables?**

**For formulas:**
- If your layout detector doesn't return Formula elements → Formulas are simply skipped (not an error)
- If your layout detector returns Formula elements with empty text → A warning is logged and the empty formula is skipped
- Parsing continues normally - no errors occur

**For tables:**
- If your layout detector doesn't return Table elements → Tables are simply skipped (not an error)
- If your layout detector returns Table elements with empty HTML:
  - **No custom `table_parser`**: A warning is logged and the table element is skipped
  - **Custom `table_parser` provided**: The table element is created and your custom parser will try to parse it from the image
- Parsing continues normally - no errors occur

## Common Use Cases

### Use Case 1: Keep Layout, Replace Text Extraction

```python
# Use Dots OCR for layout (good at structure detection)
# Use your model for text (better accuracy)
parser = PdfParser(text_extractor=MyTextExtractor())
```

### Use Case 2: Replace All OCR Components

```python
parser = PdfParser(
    layout_detector=MyLayoutDetector(),
    text_extractor=MyTextExtractor(),
    table_parser=MyTableParser(),
    formula_extractor=MyFormulaExtractor()
)
```

### Use Case 3: Replace Only Table Parsing

```python
# Keep default layout and text extraction
# Use custom table parser
parser = PdfParser(table_parser=MyTableParser())
```

## Full Documentation

See [CUSTOM_COMPONENTS_GUIDE.md](CUSTOM_COMPONENTS_GUIDE.md) for:
- Detailed implementation examples
- Complete API reference
- Format specifications
- Migration guide

## Examples

See [examples/custom_ocr_example.py](../examples/custom_ocr_example.py) for working code examples.
