# Custom Components Guide

This guide explains how to replace default OCR components with your own implementations in the Documentor library.

## Overview

The Documentor library uses a modular architecture that allows you to replace individual components while keeping the rest of the parsing pipeline intact. This is particularly useful when you want to:

- Use your own OCR model instead of Dots OCR
- Keep layout detection but use custom text extraction
- Replace table parsing with your own implementation
- Use custom formula extraction

## Base Classes

All custom components must implement the corresponding base classes from `documentor.ocr.base`:

- `BaseLayoutDetector` - for layout detection
- `BaseTextExtractor` - for text extraction
- `BaseTableParser` - for table parsing
- `BaseFormulaExtractor` - for formula extraction

## Example: Custom Layout Detector

### Step 1: Implement BaseLayoutDetector

```python
from documentor.ocr.base import BaseLayoutDetector
from PIL import Image
from typing import Any, Dict, List, Optional

class MyCustomLayoutDetector(BaseLayoutDetector):
    """
    Custom layout detector using your own OCR model.
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize your custom detector.
        
        Args:
            api_key: API key for your OCR service (if needed)
        """
        self.api_key = api_key
        # Initialize your OCR client here
    
    def detect_layout(
        self, 
        image: Image.Image, 
        origin_image: Optional[Image.Image] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect page layout using your custom OCR model.
        
        Args:
            image: Page image (optimized/preprocessed)
            origin_image: Original image (optional, for post-processing)
            
        Returns:
            List[Dict[str, Any]]: List of layout elements with fields:
                - bbox: [x1, y1, x2, y2] - bounding box coordinates
                - category: element type (e.g., "Text", "Title", "Section-header", "Table", "Picture", "Formula")
                - text: element text (if available)
        """
        # Your custom implementation here
        # Call your OCR API/model
        # Process the response
        # Return list of elements
        
        elements = []
        # Example structure:
        # elements.append({
        #     "bbox": [100, 200, 500, 250],
        #     "category": "Section-header",
        #     "text": "Introduction"
        # })
        
        return elements
    
    def detect_layout_with_text(
        self, 
        image: Image.Image, 
        origin_image: Optional[Image.Image] = None
    ) -> List[Dict[str, Any]]:
        """
        Optional: Detect layout with text content simultaneously.
        
        If your model can return layout + text in one call, implement this method.
        Otherwise, the default implementation will call detect_layout().
        """
        # Your implementation that returns layout + text
        return self.detect_layout(image, origin_image)
```

### Step 2: Use Custom Layout Detector in PdfParser

```python
from documentor.processing.parsers.pdf import PdfParser
from langchain_core.documents import Document

# Create your custom detector
my_detector = MyCustomLayoutDetector(api_key="your-api-key")

# Create parser with custom layout detector
parser = PdfParser(layout_detector=my_detector)

# Parse document as usual
document = Document(
    page_content="",
    metadata={"source": "path/to/scanned.pdf"}
)
parsed_doc = parser.parse(document)
```

## Example: Custom Text Extractor

### Step 1: Implement BaseTextExtractor

```python
from documentor.ocr.base import BaseTextExtractor
from PIL import Image
from typing import List

class MyCustomTextExtractor(BaseTextExtractor):
    """
    Custom text extractor using your own OCR model.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize your custom text extractor.
        
        Args:
            model_path: Path to your OCR model
        """
        self.model_path = model_path
        # Load your model here
    
    def extract_text(
        self, 
        image: Image.Image, 
        bbox: List[float], 
        category: str
    ) -> str:
        """
        Extract text from image region.
        
        Args:
            image: Image containing the text (already cropped to bbox)
            bbox: Bounding box [x1, y1, x2, y2] of the text region
            category: Category of the text element (Text, Title, Section-header, etc.)
            
        Returns:
            str: Extracted text
        """
        # Your custom implementation
        # Use your OCR model to extract text from the image
        text = "extracted text from your model"
        return text
```

### Step 2: Use Custom Text Extractor

```python
from documentor.processing.parsers.pdf import PdfParser

# Create your custom text extractor
my_text_extractor = MyCustomTextExtractor(model_path="path/to/model")

# Create parser with custom text extractor
parser = PdfParser(text_extractor=my_text_extractor)

# Parse document
document = Document(
    page_content="",
    metadata={"source": "path/to/scanned.pdf"}
)
parsed_doc = parser.parse(document)
```

## Example: Custom Table Parser

### Step 1: Implement BaseTableParser

```python
from documentor.ocr.base import BaseTableParser
from PIL import Image
from typing import Any, List, Optional, Tuple
import pandas as pd

class MyCustomTableParser(BaseTableParser):
    """
    Custom table parser using your own table recognition model.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize your custom table parser.
        
        Args:
            model_path: Path to your table recognition model
        """
        self.model_path = model_path
        # Load your model here
    
    def parse_table(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> Tuple[Optional[str], bool]:
        """
        Parse table from image.
        
        Args:
            image: Image containing the table (already cropped to bbox)
            bbox: Bounding box [x1, y1, x2, y2] of the table region
            
        Returns:
            Tuple containing:
                - HTML string or None
                - success: bool indicating if parsing was successful
        """
        try:
            # Your custom implementation
            # Use your model to parse the table
            table_html = "<table>...</table>"  # Your parsed table as HTML
            success = True
            
            return table_html, success
        except Exception as e:
            return None, None, False
```

### Step 2: Use Custom Table Parser

```python
from documentor.processing.parsers.pdf import PdfParser

# Create your custom table parser
my_table_parser = MyCustomTableParser(model_path="path/to/model")

# Create parser with custom table parser
parser = PdfParser(table_parser=my_table_parser)

# Parse document
document = Document(
    page_content="",
    metadata={"source": "path/to/document.pdf"}
)
parsed_doc = parser.parse(document)
```

## Example: Custom Formula Extractor

### Step 1: Implement BaseFormulaExtractor

```python
from documentor.ocr.base import BaseFormulaExtractor
from PIL import Image
from typing import List

class MyCustomFormulaExtractor(BaseFormulaExtractor):
    """
    Custom formula extractor using your own formula recognition model.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize your custom formula extractor.
        
        Args:
            model_path: Path to your formula recognition model
        """
        self.model_path = model_path
        # Load your model here
    
    def extract_formula(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> str:
        """
        Extract formula in LaTeX format from image.
        
        Args:
            image: Image containing the formula (already cropped to bbox)
            bbox: Bounding box [x1, y1, x2, y2] of the formula region
            
        Returns:
            str: Formula in LaTeX format
        """
        # Your custom implementation
        # Use your model to extract formula as LaTeX
        latex_formula = "\\frac{a}{b} = c"  # Example
        return latex_formula
```

### Step 2: Use Custom Formula Extractor

```python
from documentor.processing.parsers.pdf import PdfParser

# Create your custom formula extractor
my_formula_extractor = MyCustomFormulaExtractor(model_path="path/to/model")

# Create parser with custom formula extractor
parser = PdfParser(formula_extractor=my_formula_extractor)

# Parse document
document = Document(
    page_content="",
    metadata={"source": "path/to/document.pdf"}
)
parsed_doc = parser.parse(document)
```

## Complete Example: Replace All OCR Components

```python
from documentor.processing.parsers.pdf import PdfParser
from documentor.ocr.base import (
    BaseLayoutDetector,
    BaseTextExtractor,
    BaseTableParser,
    BaseFormulaExtractor
)
from langchain_core.documents import Document

# Implement all your custom components
class MyLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image, origin_image=None):
        # Your implementation
        return []

class MyTextExtractor(BaseTextExtractor):
    def extract_text(self, image, bbox, category):
        # Your implementation
        return ""

class MyTableParser(BaseTableParser):
    def parse_table(self, image, bbox):
        # Your implementation
        return None, None, False

class MyFormulaExtractor(BaseFormulaExtractor):
    def extract_formula(self, image, bbox):
        # Your implementation
        return ""

# Create parser with all custom components
parser = PdfParser(
    layout_detector=MyLayoutDetector(),
    text_extractor=MyTextExtractor(),
    table_parser=MyTableParser(),
    formula_extractor=MyFormulaExtractor()
)

# Parse document
document = Document(
    page_content="",
    metadata={"source": "path/to/scanned.pdf"}
)
parsed_doc = parser.parse(document)
```

## Example: Keep Layout Detection, Replace Only Text Extraction

This is a common use case - you want to use Dots OCR for layout detection but your own model for text extraction:

```python
from documentor.processing.parsers.pdf import PdfParser
from documentor.ocr.base import BaseTextExtractor
from PIL import Image
from typing import List

class MyTextExtractor(BaseTextExtractor):
    def extract_text(self, image, bbox, category):
        # Your custom text extraction
        return "extracted text"

# Create parser with custom text extractor only
# Layout detection will still use Dots OCR
parser = PdfParser(text_extractor=MyTextExtractor())

# Parse scanned PDF
document = Document(
    page_content="",
    metadata={"source": "path/to/scanned.pdf"}
)
parsed_doc = parser.parse(document)
```

## Layout Element Format

When implementing `BaseLayoutDetector.detect_layout()`, your returned elements must follow this format:

```python
[
    {
        "bbox": [x1, y1, x2, y2],  # Bounding box coordinates
        "category": "Text",  # Element type
        "text": "Optional text content",  # Text if available
        "page_num": 0  # Page number (0-indexed)
    },
    # ... more elements
]
```

### Supported Categories

- `"Text"` - Regular text blocks
- `"Title"` - Document title
- `"Section-header"` - Section headers (H1-H6)
- `"Table"` - Tables
- `"Picture"` - Images
- `"Caption"` - Image/table captions
- `"Formula"` - Mathematical formulas
- `"List-item"` - List items
- `"Page-header"` - Page headers (usually filtered out)
- `"Page-footer"` - Page footers (usually filtered out)

## Default Behavior

If you don't provide a custom component, the library uses Dots OCR by default:

- **Layout Detection**: Uses Dots OCR layout detector (via `PdfLayoutDetector`)
- **Text Extraction**: 
  - For scanned PDFs: Uses text from Dots OCR layout detection
  - For text-extractable PDFs: Uses PyMuPDF to extract text by coordinates
- **Table Parsing**: Uses HTML tables from Dots OCR
- **Formula Extraction**: Uses LaTeX text from Dots OCR layout detection

**Important**: For formulas, if you don't provide a custom `formula_extractor`, the library will use the formula text that comes from the layout detector. This means:
- If you use default Dots OCR layout detector → formulas come from Dots OCR
- If you use custom layout detector → formulas come from your custom layout detector

**What happens if your custom layout detector doesn't extract formulas or tables?**

If your custom layout detector:
1. **Doesn't return Formula/Table elements** (category != "Formula"/"Table") → Formulas/tables simply won't appear in the result. This is **not an error** - they're just skipped.
2. **Returns Formula elements with empty text** → The library will:
   - Log a warning message
   - Skip the empty formula element (won't create an element with empty content)
   - Continue processing other elements normally
3. **Returns Table elements with empty HTML** → The library will:
   - If no custom `table_parser` is provided: Log a warning and skip the table element
   - If custom `table_parser` is provided: Create the table element and let the custom parser try to parse it from the image

**Example scenario:**
```python
# Custom layout detector that doesn't extract formulas or tables
class MySimpleLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image, origin_image=None):
        # Only detects text and headers, no formulas or tables
        return [
            {"bbox": [100, 100, 500, 150], "category": "Title", "text": "Title"},
            {"bbox": [100, 200, 500, 400], "category": "Text", "text": "Content"}
            # No Formula/Table elements - they will be skipped (no error)
        ]

parser = PdfParser(layout_detector=MySimpleLayoutDetector())
# Formulas and tables in the document won't be extracted, but parsing will succeed
```

**If you need formula/table extraction with a simple layout detector:**

**For formulas:**
If you want to use a simple layout detector (that doesn't extract formulas) but still extract formulas, provide a custom `formula_extractor`:

```python
parser = PdfParser(
    layout_detector=MySimpleLayoutDetector(),  # Only detects layout structure
    formula_extractor=MyFormulaExtractor()      # Extracts formulas separately
)
```

However, note that the `formula_extractor` will only be called if the layout detector returns Formula elements with valid bounding boxes. If your layout detector doesn't detect formulas at all, you'll need to either:
1. Enhance your layout detector to detect Formula regions (even without text)
2. Use a different approach to identify formula regions

**For tables:**
If you want to use a simple layout detector (that doesn't extract table HTML) but still parse tables, provide a custom `table_parser`:

```python
parser = PdfParser(
    layout_detector=MySimpleLayoutDetector(),  # Only detects layout structure (may return Table with empty HTML)
    table_parser=MyTableParser()                # Parses tables from images
)
```

The `table_parser` will be called if the layout detector returns Table elements with valid bounding boxes, even if the HTML is empty. The custom parser will receive the table image region and can parse it directly.

## Notes

1. **Bounding Box Coordinates**: All bbox coordinates should be in the same coordinate system as the input image (after any preprocessing/optimization).

2. **Image Preprocessing**: The library may preprocess images (resize, optimize) before passing them to your components. The `origin_image` parameter contains the original image if you need it.

3. **Error Handling**: Your implementations should handle errors gracefully. Return empty results rather than raising exceptions when possible.

4. **Performance**: For scanned PDFs, your components will be called for each page and each element. Consider caching or batching if your model supports it.

5. **Compatibility**: You can mix and match - use custom components for some operations and default Dots OCR for others.

## Testing Your Custom Components

You can test your custom components independently before integrating them:

```python
from PIL import Image

# Load a test image
image = Image.open("test_page.png")

# Test your layout detector
my_detector = MyCustomLayoutDetector()
layout = my_detector.detect_layout(image)
print(f"Detected {len(layout)} elements")

# Test your text extractor
my_text_extractor = MyCustomTextExtractor()
text = my_text_extractor.extract_text(image, [100, 200, 500, 250], "Text")
print(f"Extracted text: {text}")
```

## Migration from Dots OCR

If you're currently using Dots OCR and want to migrate to your own model:

1. **Start with Layout Detection**: Implement `BaseLayoutDetector` first, as it's the foundation
2. **Add Text Extraction**: Implement `BaseTextExtractor` for scanned PDFs
3. **Add Table Parsing**: Implement `BaseTableParser` if you need table extraction
4. **Add Formula Extraction**: Implement `BaseFormulaExtractor` if you need formula extraction

You can migrate incrementally - start with one component and gradually replace others.
