"""
Script to extract header metadata from PDF annotation and PDF file.
Extracts font properties (size, bold, italic, alignment, caps lock) for all headers.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    print("ERROR: PyMuPDF (fitz) is not installed. Please install it: pip install PyMuPDF")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_text_properties(
    page: fitz.Page, 
    rect: fitz.Rect,
    text: str
) -> Dict[str, Any]:
    """
    Extracts text properties from PDF text area (font size, bold, italic, alignment, caps lock).
    
    Args:
        page: PDF page.
        rect: Text area rectangle.
        text: Text content.
    
    Returns:
        Dictionary with keys:
        - font_name: main font name (str or None)
        - font_size: average font size (float or None)
        - is_bold: True if ≥95% of text is bold (bool)
        - is_italic: True if ≥95% of text is italic (bool)
        - alignment: text alignment (str or None)
        - is_caps_lock: True if ≥70% of letters are uppercase (bool)
    """
    properties = {
        'font_name': None,
        'font_size': None,
        'is_bold': False,
        'is_italic': False,
        'alignment': None,
        'is_caps_lock': False,
    }
    
    try:
        text_dict = page.get_text("dict", clip=rect)
        blocks = text_dict.get("blocks", [])
        
        font_sizes = []
        font_names = []
        bold_spans = 0
        italic_spans = 0
        total_spans = 0
        total_text_length = 0
        bold_text_length = 0
        italic_text_length = 0
        
        for block in blocks:
            if block.get("type") == 0:  # Text block
                # Check alignment
                if properties['alignment'] is None:
                    bbox = block.get("bbox", [])
                    if len(bbox) >= 4:
                        page_rect = page.rect
                        block_center_x = (bbox[0] + bbox[2]) / 2
                        page_center_x = (page_rect.x0 + page_rect.x1) / 2
                        if abs(block_center_x - page_center_x) < 50:
                            properties['alignment'] = 'center'
                        elif bbox[0] < page_rect.x0 + 50:
                            properties['alignment'] = 'left'
                        elif bbox[2] > page_rect.x1 - 50:
                            properties['alignment'] = 'right'
                        else:
                            properties['alignment'] = 'left'
                
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        if not span_text:
                            continue
                        
                        font_size = span.get("size", 0)
                        font_name = span.get("font", "")
                        flags = span.get("flags", 0)
                        
                        if font_size > 0:
                            font_sizes.append(font_size)
                        if font_name:
                            font_names.append(font_name)
                        
                        # Check bold: bit 18 (ForceBold) OR font name
                        is_bold_span = False
                        if flags & (1 << 18):  # Bit 19 (0-indexed = 18) = ForceBold
                            is_bold_span = True
                        elif font_name:
                            font_lower = font_name.lower()
                            # Check for bold indicators in font name
                            if any(indicator in font_lower for indicator in ['bold', 'medi', 'black', 'heavy', 'demibold', 'semibold', 'extrabold']):
                                is_bold_span = True
                        
                        # Check italic: bit 6 OR font name
                        is_italic_span = False
                        if flags & (1 << 6):  # Bit 7 (0-indexed = 6) = Italic
                            is_italic_span = True
                        elif font_name:
                            font_lower = font_name.lower()
                            # Check for italic indicators in font name
                            if any(indicator in font_lower for indicator in ['italic', 'ital', 'oblique', 'slanted']):
                                is_italic_span = True
                        
                        total_spans += 1
                        total_text_length += len(span_text)
                        
                        if is_bold_span:
                            bold_spans += 1
                            bold_text_length += len(span_text)
                        if is_italic_span:
                            italic_spans += 1
                            italic_text_length += len(span_text)
        
        # Calculate averages
        if font_sizes:
            properties['font_size'] = sum(font_sizes) / len(font_sizes)
        if font_names:
            # Get most common font name
            properties['font_name'] = max(set(font_names), key=font_names.count)
        
        # Determine if mostly bold/italic (≥95% of text)
        if total_text_length > 0:
            properties['is_bold'] = (bold_text_length / total_text_length) >= 0.95
            properties['is_italic'] = (italic_text_length / total_text_length) >= 0.95
        elif total_spans > 0:
            properties['is_bold'] = (bold_spans / total_spans) >= 0.95
            properties['is_italic'] = (italic_spans / total_spans) >= 0.95
        
        # Also check font name for bold/italic if flags didn't catch it
        # This is CRITICAL because many PDFs encode formatting in font name, not flags
        if not properties['is_bold'] and properties['font_name']:
            font_lower = properties['font_name'].lower()
            if any(indicator in font_lower for indicator in ['bold', 'medi', 'black', 'heavy', 'demibold', 'semibold', 'extrabold']):
                properties['is_bold'] = True
        
        if not properties['is_italic'] and properties['font_name']:
            font_lower = properties['font_name'].lower()
            if any(indicator in font_lower for indicator in ['italic', 'ital', 'oblique', 'slanted']):
                properties['is_italic'] = True
        
        # Check caps lock (≥70% uppercase letters)
        if text:
            letters = [c for c in text if c.isalpha()]
            if len(letters) >= 3:
                uppercase_count = sum(1 for c in letters if c.isupper())
                properties['is_caps_lock'] = (uppercase_count / len(letters)) >= 0.7
    
    except Exception as e:
        logger.warning(f"Error extracting text properties: {e}")
    
    return properties


def extract_header_metadata(
    annotation_path: str,
    pdf_path: str,
    output_path: str
) -> None:
    """
    Extracts metadata for all headers from PDF annotation and PDF file.
    
    Args:
        annotation_path: Path to JSON annotation file.
        pdf_path: Path to PDF file.
        output_path: Path to output JSON file with header metadata.
    """
    # Load annotation
    with open(annotation_path, 'r', encoding='utf-8') as f:
        annotation = json.load(f)
    
    elements = annotation.get('elements', [])
    
    # Filter headers
    headers = [
        elem for elem in elements
        if elem.get('type', '').startswith('header_')
    ]
    
    logger.info(f"Found {len(headers)} headers in annotation")
    
    # Open PDF
    pdf_document = fitz.open(pdf_path)
    render_scale = 2.0  # Default render scale
    
    header_metadata = []
    
    try:
        for header in headers:
            header_type = header.get('type', '')
            header_text = header.get('content', '').strip()
            bbox = header.get('bbox', [])
            page_num = header.get('page_number', 0) - 1  # Convert to 0-based
            
            if len(bbox) < 4 or page_num < 0 or page_num >= len(pdf_document):
                logger.warning(f"Invalid bbox or page number for header: {header_text[:50]}...")
                continue
            
            try:
                page = pdf_document.load_page(page_num)
                
                # Convert coordinates from render_scale to original PDF scale
                x1, y1, x2, y2 = (
                    bbox[0] / render_scale,
                    bbox[1] / render_scale,
                    bbox[2] / render_scale,
                    bbox[3] / render_scale,
                )
                rect = fitz.Rect(x1, y1, x2, y2)
                
                # Extract properties
                properties = extract_text_properties(page, rect, header_text)
                
                # Add header info
                header_info = {
                    'id': header.get('id', ''),
                    'type': header_type,
                    'text': header_text,
                    'page_number': page_num + 1,  # Convert back to 1-based
                    'bbox': bbox,
                    'properties': properties,
                }
                
                header_metadata.append(header_info)
                logger.debug(f"Extracted metadata for header: {header_text[:50]}...")
            
            except Exception as e:
                logger.warning(f"Error extracting metadata for header '{header_text[:50]}...': {e}")
                continue
    
    finally:
        pdf_document.close()
    
    # Save results
    output_data = {
        'source_annotation': str(annotation_path),
        'source_pdf': str(pdf_path),
        'total_headers': len(header_metadata),
        'headers': header_metadata
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved header metadata to {output_path}")
    logger.info(f"Total headers processed: {len(header_metadata)}")
    
    # Print summary
    print("\n=== Header Metadata Summary ===")
    print(f"Total headers: {len(header_metadata)}")
    
    # Group by type
    by_type = {}
    for header in header_metadata:
        header_type = header['type']
        if header_type not in by_type:
            by_type[header_type] = []
        by_type[header_type].append(header)
    
    print("\nBy type:")
    for header_type, headers_list in sorted(by_type.items()):
        print(f"  {header_type}: {len(headers_list)}")
        
        # Show properties statistics
        if headers_list:
            font_sizes = [h['properties'].get('font_size') for h in headers_list if h['properties'].get('font_size')]
            bold_count = sum(1 for h in headers_list if h['properties'].get('is_bold'))
            italic_count = sum(1 for h in headers_list if h['properties'].get('is_italic'))
            caps_lock_count = sum(1 for h in headers_list if h['properties'].get('is_caps_lock'))
            
            if font_sizes:
                avg_size = sum(font_sizes) / len(font_sizes)
                min_size = min(font_sizes)
                max_size = max(font_sizes)
                print(f"    Font size: avg={avg_size:.1f}, min={min_size:.1f}, max={max_size:.1f}")
            print(f"    Bold: {bold_count}/{len(headers_list)} ({100*bold_count/len(headers_list):.1f}%)")
            print(f"    Italic: {italic_count}/{len(headers_list)} ({100*italic_count/len(headers_list):.1f}%)")
            print(f"    Caps Lock: {caps_lock_count}/{len(headers_list)} ({100*caps_lock_count/len(headers_list):.1f}%)")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python extract_header_metadata.py <annotation.json> <pdf_file> [output.json]")
        sys.exit(1)
    
    annotation_path = sys.argv[1]
    pdf_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else 'header_metadata.json'
    
    extract_header_metadata(annotation_path, pdf_path, output_path)
