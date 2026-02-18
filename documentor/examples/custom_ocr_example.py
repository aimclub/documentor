"""
Example: Using Custom OCR Components with PdfParser

This example demonstrates how to replace Dots OCR components with your own implementations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from langchain_core.documents import Document

# Import base classes
from documentor.ocr.base import (
    BaseLayoutDetector,
    BaseTextExtractor,
    BaseTableParser,
    BaseFormulaExtractor
)

# Import parser
from documentor.processing.parsers.pdf import PdfParser

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    pd = None


# ============================================================================
# Example 1: Custom Layout Detector
# ============================================================================

class MyCustomLayoutDetector(BaseLayoutDetector):
    """
    Example custom layout detector.
    
    Replace this with your own OCR model implementation.
    """
    
    def __init__(self, api_endpoint: str = None):
        """
        Initialize your custom detector.
        
        Args:
            api_endpoint: Endpoint for your OCR API
        """
        self.api_endpoint = api_endpoint
        # Initialize your OCR client here
        print(f"Initialized MyCustomLayoutDetector with endpoint: {api_endpoint}")
    
    def detect_layout(
        self, 
        image: Image.Image, 
        origin_image: Optional[Image.Image] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect page layout using your custom OCR model.
        
        Args:
            image: Page image (optimized/preprocessed)
            origin_image: Original image (optional)
            
        Returns:
            List[Dict[str, Any]]: List of layout elements
        """
        # TODO: Replace with your actual OCR model call
        # Example structure:
        elements = [
            {
                "bbox": [100, 100, 500, 150],
                "category": "Title",
                "text": "Document Title",
                "page_num": 0
            },
            {
                "bbox": [100, 200, 500, 400],
                "category": "Text",
                "text": "Document content...",
                "page_num": 0
            }
        ]
        
        return elements


# ============================================================================
# Example 2: Custom Text Extractor
# ============================================================================

class MyCustomTextExtractor(BaseTextExtractor):
    """
    Example custom text extractor.
    
    Replace this with your own text extraction model.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize your custom text extractor.
        
        Args:
            model_path: Path to your OCR model
        """
        self.model_path = model_path
        # Load your model here
        print(f"Initialized MyCustomTextExtractor with model: {model_path}")
    
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
            bbox: Bounding box [x1, y1, x2, y2]
            category: Element category
            
        Returns:
            str: Extracted text
        """
        # TODO: Replace with your actual OCR model call
        # Use your model to extract text from the image
        return "Extracted text from custom model"


# ============================================================================
# Example 3: Custom Table Parser
# ============================================================================

class MyCustomTableParser(BaseTableParser):
    """
    Example custom table parser.
    
    Replace this with your own table recognition model.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize your custom table parser.
        
        Args:
            model_path: Path to your table recognition model
        """
        self.model_path = model_path
        # Load your model here
        print(f"Initialized MyCustomTableParser with model: {model_path}")
    
    def parse_table(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> Tuple[Optional[Any], Optional[str], bool]:
        """
        Parse table from image.
        
        Args:
            image: Image containing the table (already cropped to bbox)
            bbox: Bounding box [x1, y1, x2, y2]
            
        Returns:
            Tuple[DataFrame or None, HTML/markdown or None, success: bool]
        """
        # TODO: Replace with your actual table recognition model
        try:
            # Use your model to parse the table
            if HAS_PANDAS:
                # Create example DataFrame
                dataframe = pd.DataFrame({
                    "Column1": ["Value1", "Value2"],
                    "Column2": ["Value3", "Value4"]
                })
            else:
                dataframe = None
            
            html_markdown = "<table>...</table>"  # Optional
            success = True
            
            return dataframe, html_markdown, success
        except Exception as e:
            print(f"Error parsing table: {e}")
            return None, None, False


# ============================================================================
# Example 4: Custom Formula Extractor
# ============================================================================

class MyCustomFormulaExtractor(BaseFormulaExtractor):
    """
    Example custom formula extractor.
    
    Replace this with your own formula recognition model.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize your custom formula extractor.
        
        Args:
            model_path: Path to your formula recognition model
        """
        self.model_path = model_path
        # Load your model here
        print(f"Initialized MyCustomFormulaExtractor with model: {model_path}")
    
    def extract_formula(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> str:
        """
        Extract formula in LaTeX format from image.
        
        Args:
            image: Image containing the formula (already cropped to bbox)
            bbox: Bounding box [x1, y1, x2, y2]
            
        Returns:
            str: Formula in LaTeX format
        """
        # TODO: Replace with your actual formula recognition model
        return "\\frac{a}{b} = c"


# ============================================================================
# Usage Examples
# ============================================================================

def example_1_custom_layout_only():
    """
    Example: Use custom layout detector, keep default text/table extraction.
    """
    print("\n=== Example 1: Custom Layout Detector Only ===")
    
    # Create custom layout detector
    custom_detector = MyCustomLayoutDetector(api_endpoint="https://api.example.com/ocr")
    
    # Create parser with custom layout detector
    parser = PdfParser(layout_detector=custom_detector)
    
    # Parse document
    document = Document(
        page_content="",
        metadata={"source": "path/to/scanned.pdf"}
    )
    
    # parsed_doc = parser.parse(document)
    print("Parser created with custom layout detector")


def example_2_custom_text_extraction():
    """
    Example: Use custom text extractor for scanned PDFs, keep default layout detection.
    """
    print("\n=== Example 2: Custom Text Extractor Only ===")
    
    # Create custom text extractor
    custom_text_extractor = MyCustomTextExtractor(model_path="path/to/model.pth")
    
    # Create parser with custom text extractor
    parser = PdfParser(text_extractor=custom_text_extractor)
    
    # Parse document
    document = Document(
        page_content="",
        metadata={"source": "path/to/scanned.pdf"}
    )
    
    # parsed_doc = parser.parse(document)
    print("Parser created with custom text extractor")


def example_3_custom_table_parser():
    """
    Example: Use custom table parser, keep default other components.
    """
    print("\n=== Example 3: Custom Table Parser Only ===")
    
    # Create custom table parser
    custom_table_parser = MyCustomTableParser(model_path="path/to/table_model.pth")
    
    # Create parser with custom table parser
    parser = PdfParser(table_parser=custom_table_parser)
    
    # Parse document
    document = Document(
        page_content="",
        metadata={"source": "path/to/document.pdf"}
    )
    
    # parsed_doc = parser.parse(document)
    print("Parser created with custom table parser")


def example_4_all_custom_components():
    """
    Example: Replace all OCR components with custom implementations.
    """
    print("\n=== Example 4: All Custom Components ===")
    
    # Create all custom components
    custom_detector = MyCustomLayoutDetector(api_endpoint="https://api.example.com/ocr")
    custom_text_extractor = MyCustomTextExtractor(model_path="path/to/text_model.pth")
    custom_table_parser = MyCustomTableParser(model_path="path/to/table_model.pth")
    custom_formula_extractor = MyCustomFormulaExtractor(model_path="path/to/formula_model.pth")
    
    # Create parser with all custom components
    parser = PdfParser(
        layout_detector=custom_detector,
        text_extractor=custom_text_extractor,
        table_parser=custom_table_parser,
        formula_extractor=custom_formula_extractor
    )
    
    # Parse document
    document = Document(
        page_content="",
        metadata={"source": "path/to/scanned.pdf"}
    )
    
    # parsed_doc = parser.parse(document)
    print("Parser created with all custom components")


def example_5_keep_layout_replace_text():
    """
    Example: Keep Dots OCR for layout detection, use custom model for text extraction.
    
    This is a common use case - you want to use Dots OCR's layout detection
    (which is good) but your own model for text extraction (which might be better).
    """
    print("\n=== Example 5: Keep Layout, Replace Text Extraction ===")
    
    # Only provide custom text extractor
    # Layout detection will use default Dots OCR
    custom_text_extractor = MyCustomTextExtractor(model_path="path/to/better_text_model.pth")
    
    parser = PdfParser(text_extractor=custom_text_extractor)
    
    # Parse scanned PDF
    document = Document(
        page_content="",
        metadata={"source": "path/to/scanned.pdf"}
    )
    
    # parsed_doc = parser.parse(document)
    print("Parser created: Dots OCR for layout, custom model for text")


def example_6_default_behavior():
    """
    Example: Use all default Dots OCR components.
    
    If you don't provide any custom components, the library uses Dots OCR by default:
    - Layout detection: Dots OCR
    - Text extraction: Dots OCR (for scanned PDFs) or PyMuPDF (for text-extractable PDFs)
    - Table parsing: Dots OCR HTML tables
    - Formula extraction: LaTeX from Dots OCR layout detection
    """
    print("\n=== Example 6: Default Behavior (All Dots OCR) ===")
    
    # Don't provide any custom components - uses Dots OCR by default
    parser = PdfParser()
    
    # Parse scanned PDF
    document = Document(
        page_content="",
        metadata={"source": "path/to/scanned.pdf"}
    )
    
    # parsed_doc = parser.parse(document)
    print("Parser created: All components use Dots OCR by default")
    print("  - Layout: Dots OCR")
    print("  - Text: Dots OCR (scanned) or PyMuPDF (text-extractable)")
    print("  - Tables: Dots OCR HTML")
    print("  - Formulas: LaTeX from Dots OCR layout detection")


def example_7_simple_layout_with_custom_table_parser():
    """
    Example: Simple layout detector that doesn't extract table HTML, but custom table parser.
    
    This demonstrates that if your layout detector returns Table elements with empty HTML,
    but you provide a custom table_parser, the parser will still try to parse tables from images.
    """
    print("\n=== Example 7: Simple Layout + Custom Table Parser ===")
    
    class SimpleLayoutDetector(BaseLayoutDetector):
        def detect_layout(self, image, origin_image=None):
            # Detects tables but doesn't extract HTML
            return [
                {"bbox": [100, 100, 500, 150], "category": "Title", "text": "Title"},
                {"bbox": [100, 200, 500, 600], "category": "Table", "text": ""}  # Table with empty HTML
            ]
    
    # Custom table parser will parse tables from images even if HTML is empty
    parser = PdfParser(
        layout_detector=SimpleLayoutDetector(),
        table_parser=MyCustomTableParser(model_path="path/to/table_model.pth")
    )
    
    # Parse document
    document = Document(
        page_content="",
        metadata={"source": "path/to/document.pdf"}
    )
    
    # parsed_doc = parser.parse(document)
    print("Parser created: Simple layout detector + custom table parser")
    print("  - Tables will be parsed from images even if layout detector doesn't provide HTML")


if __name__ == "__main__":
    print("Custom OCR Components Examples")
    print("=" * 60)
    
    # Run examples
    example_1_custom_layout_only()
    example_2_custom_text_extraction()
    example_3_custom_table_parser()
    example_4_all_custom_components()
    example_5_keep_layout_replace_text()
    example_6_default_behavior()
    example_7_simple_layout_with_custom_table_parser()
    
    print("\n" + "=" * 60)
    print("See CUSTOM_COMPONENTS_GUIDE.md for detailed documentation")
