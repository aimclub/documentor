"""
Finding headers in PDF and building rules for finding missed headers.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from ...headers.constants import SPECIAL_HEADER_1, APPENDIX_HEADER_PATTERN

logger = logging.getLogger(__name__)


def _is_numbered_header(text: str) -> bool:
    """
    Check if header has explicit numbering.
    
    Similar to _is_numbered_header in DOCX parser.
    
    Args:
        text: Header text.
    
    Returns:
        True if header has explicit numbering.
    """
    text_stripped = text.strip()
    patterns = [
        r'^\d+\.\d+',  # "1.2" or "1.2Актуальность"
        r'^\d+\.',  # "1." or "1Анализ"
        r'^\d+[А-ЯЁA-Z]',  # "1Анализ" (without dot and space)
        r'^\d+\s+[А-ЯЁA-Z]',  # "1 Анализ" (with space)
        r'^[IVX]+\.',  # "I.", "II."
        r'^[A-Z]\.\d+',  # "A.1"
        r'^[A-Z]\.',  # "A."
        r'^[A-Z]\s+[A-Z]',  # "B Formulation", "A Methodologies"
    ]
    for pattern in patterns:
        if re.match(pattern, text_stripped, re.IGNORECASE):
            return True
    return False


def determine_level_by_numbering(text: str) -> Optional[int]:
    """
    Determines header level from numbering.
    
    Recognizes numbering types:
    - Numeric: "1", "1.1", "1.1.1", "1.2.3.4"
    - Alphabetic: "A", "A.1", "B.2.1"
    - Roman: "I", "II", "III"
    - Combined: "A.1", "B.2"
    
    Args:
        text: Header text.
    
    Returns:
        Header level (1-6) or None if numbering not recognized.
    """
    text_stripped = text.strip()
    
    # Patterns for level by numbering depth
    patterns = [
        # Level 4: "1.2.3.4" or "A.1.2.3"
        (r'^[A-Z\d]+\.\d+\.\d+\.\d+', 4),
        # Level 3: "1.2.3" or "A.1.2" or "1.1.1"
        (r'^[A-Z\d]+\.\d+\.\d+', 3),
        # Level 2: "1.2" or "A.1" or "1.1"
        (r'^[A-Z\d]+\.\d+', 2),
        # Level 1: "1." or "1 " or "I." or "A." or "A "
        (r'^\d+\.', 1),
        (r'^\d+\s+[А-ЯЁA-Z]', 1),  # "1 Header" (Cyrillic/Latin)
        (r'^[IVX]+\.', 1),  # "I.", "II.", "III."
        (r'^[A-Z]\.', 1),  # "A.", "B."
        (r'^[A-Z]\s+[А-ЯЁA-Z]', 1),  # "A Header" (Cyrillic/Latin)
    ]
    
    for pattern in patterns:
        if isinstance(pattern, tuple):
            regex, level = pattern
            if re.match(regex, text_stripped, re.IGNORECASE):
                return level
        else:
            # Legacy patterns without level - determine by dot count
            if re.match(pattern, text_stripped, re.IGNORECASE):
                # Count dots to determine level
                dot_count = text_stripped.split('.')[0].count('.') if '.' in text_stripped else 0
                if dot_count == 0:
                    return 1
                elif dot_count == 1:
                    return 2
                elif dot_count == 2:
                    return 3
                else:
                    return min(4, dot_count + 1)
    
    return None


def _is_structural_keyword(text: str) -> bool:
    """
    Checks if text is a structural keyword (HEADER_1 level).
    
    Similar to _is_structural_keyword in DOCX parser.
    
    Args:
        text: Text to check.
    
    Returns:
        True if text is a structural keyword.
    """
    # Remove trailing colon and whitespace before comparison
    text_normalized = text.strip().rstrip(':').strip().upper()
    return text_normalized in SPECIAL_HEADER_1


def extract_text_properties(
    page: fitz.Page, 
    rect: fitz.Rect,
    text: str
) -> Dict[str, Any]:
    """
    Extracts text properties from PDF text area (font size, bold, italic, alignment, caps lock).
    
    Similar to extract_paragraph_properties in DOCX parser.
    
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
                            properties['alignment'] = 'left'  # Default
                
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_size = span.get("size", 0)
                        if font_size > 0:
                            font_sizes.append(font_size)
                        
                        font_name = span.get("font", "")
                        if font_name:
                            font_names.append(font_name)
                            if not properties['font_name']: # Keep first encountered as initial
                                properties['font_name'] = font_name
                        
                        # Check formatting flags
                        flags = span.get("flags", 0)
                        span_text = span.get("text", "")
                        span_length = len(span_text)
                        
                        total_spans += 1
                        total_text_length += span_length
                        
                        # Check bold
                        # In PyMuPDF: flags & (1 << 18) = ForceBold (bit 19), or check font name
                        is_bold_span = False
                        if flags & (1 << 18):  # Bit 19 (0-indexed = 18) = ForceBold
                            is_bold_span = True
                        elif font_name:
                            font_lower = font_name.lower()
                            # Check for bold indicators in font name
                            if any(indicator in font_lower for indicator in ['bold', 'medi', 'black', 'heavy', 'demibold', 'semibold']):
                                is_bold_span = True
                        
                        if is_bold_span:
                            bold_spans += 1
                            bold_text_length += span_length
                        
                        # Check italic
                        # In PyMuPDF: flags & (1 << 6) = Italic (bit 7), or check font name
                        is_italic_span = False
                        if flags & (1 << 6):  # Bit 7 (0-indexed = 6) = Italic
                            is_italic_span = True
                        elif font_name:
                            font_lower = font_name.lower()
                            # Check for italic indicators in font name
                            if any(indicator in font_lower for indicator in ['italic', 'ital', 'oblique', 'slanted']):
                                is_italic_span = True
                        
                        if is_italic_span:
                            italic_spans += 1
                            italic_text_length += span_length
        
        # Calculate average font size
        if font_sizes:
            properties['font_size'] = sum(font_sizes) / len(font_sizes)
        
        # Get most common font name
        if font_names:
            properties['font_name'] = max(set(font_names), key=font_names.count)
        
        # Determine if text is mostly bold (≥95%)
        if total_text_length > 0:
            properties['is_bold'] = (bold_text_length / total_text_length) >= 0.95
        elif total_spans > 0:
            properties['is_bold'] = (bold_spans / total_spans) >= 0.95
        
        # Also check font name for bold if flags didn't catch it
        if not properties['is_bold'] and properties['font_name']:
            font_lower = properties['font_name'].lower()
            if any(indicator in font_lower for indicator in ['bold', 'medi', 'black', 'heavy', 'demibold', 'semibold', 'extrabold']):
                properties['is_bold'] = True
        
        # Determine if text is mostly italic (≥95%)
        if total_text_length > 0:
            properties['is_italic'] = (italic_text_length / total_text_length) >= 0.95
        elif total_spans > 0:
            properties['is_italic'] = (italic_spans / total_spans) >= 0.95
        
        # Also check font name for italic if flags didn't catch it
        if not properties['is_italic'] and properties['font_name']:
            font_lower = properties['font_name'].lower()
            if any(indicator in font_lower for indicator in ['italic', 'ital', 'oblique', 'slanted']):
                properties['is_italic'] = True
        
        # Check Caps Lock (70%+ uppercase letters)
        if text:
            letters = [c for c in text if c.isalpha()]
            if len(letters) >= 3:
                uppercase_count = sum(1 for c in letters if c.isupper())
                properties['is_caps_lock'] = (uppercase_count / len(letters)) >= 0.7
    
    except Exception as e:
        logger.debug(f"Error extracting text properties: {e}")
    
    return properties


def build_header_rules(
    pdf_path: str,
    header_positions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Builds rules for finding headers based on found headers.
    
    Similar to build_header_rules in DOCX parser.
    
    Args:
        pdf_path: Path to PDF file.
        header_positions: List of found header positions with metadata.
    
    Returns:
        Dictionary with header rules by level and common properties.
    """
    rules = {
        'by_level': {},
        'common_properties': {}
    }
    
    if not header_positions:
        return rules
    
    pdf_document = fitz.open(pdf_path)
    try:
        all_properties = []
        for header_info in header_positions:
            page_num = header_info.get('page_num', 0)
            bbox = header_info.get('bbox', [])
            text = header_info.get('text', '')
            
            if len(bbox) < 4 or page_num >= len(pdf_document):
                continue
            
            try:
                page = pdf_document.load_page(page_num)
                rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
                
                properties = extract_text_properties(page, rect, text)
                
                # Determine level
                level = header_info.get('level')
                if not level:
                    # Try to determine from numbering pattern
                    match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
                    if match:
                        if match.group(3):
                            level = 3
                        elif match.group(2):
                            level = 2
                        elif match.group(1):
                            level = 1
                
                if not level:
                    level = 'unknown'
                
                properties['page_num'] = page_num
                properties['text'] = text
                properties['detected_level'] = level
                all_properties.append(properties)
                
                level_key = str(level)
                if level_key not in rules['by_level']:
                    rules['by_level'][level_key] = []
                rules['by_level'][level_key].append(properties)
            
            except Exception as e:
                logger.debug(f"Error processing header at page {page_num}: {e}")
                continue
        
        # Build rules for each level
        for level, props_list in rules['by_level'].items():
            if not props_list:
                continue
            
            font_names = [p.get('font_name') for p in props_list if p.get('font_name')]
            font_sizes = [p.get('font_size') for p in props_list if p.get('font_size')]
            bold_count = sum(1 for p in props_list if p.get('is_bold'))
            italic_count = sum(1 for p in props_list if p.get('is_italic'))
            alignments = [p.get('alignment') for p in props_list if p.get('alignment')]
            caps_lock_count = sum(1 for p in props_list if p.get('is_caps_lock'))
            
            most_common_alignment = None
            if alignments:
                most_common_alignment = max(set(alignments), key=alignments.count)
            
            level_rules = {
                'font_name': max(set(font_names), key=font_names.count) if font_names else None,
                'font_size': sum(font_sizes) / len(font_sizes) if font_sizes else None,
                'font_size_range': (min(font_sizes), max(font_sizes)) if font_sizes else None,
                'is_bold': bold_count > len(props_list) / 2,
                'is_italic': italic_count > len(props_list) / 2,
                'alignment': most_common_alignment,
                'is_caps_lock': caps_lock_count > len(props_list) / 2,
                'count': len(props_list)
            }
            
            rules['by_level'][level] = level_rules
        
        # Add common_header if all headers are unknown level
        if 'unknown' in rules['by_level'] and len(rules['by_level']) == 1:
            common_props = rules['by_level']['unknown']
            if common_props:
                rules['common_header'] = {
                    'font_name': max(set([p.get('font_name') for p in common_props if p.get('font_name')]), 
                                   key=[p.get('font_name') for p in common_props if p.get('font_name')].count) if any(p.get('font_name') for p in common_props) else None,
                    'font_size': sum([p.get('font_size') for p in common_props if p.get('font_size')]) / len([p for p in common_props if p.get('font_size')]) if any(p.get('font_size') for p in common_props) else None,
                    'is_bold': sum(1 for p in common_props if p.get('is_bold')) > len(common_props) / 2,
                    'is_italic': sum(1 for p in common_props if p.get('is_italic')) > len(common_props) / 2,
                }
    
    finally:
        pdf_document.close()
    
    return rules


def determine_header_level_by_font_name(
    font_name: str,
    header_rules: Optional[Dict[str, Any]] = None
) -> Optional[int]:
    """
    Determines header level from font name.
    
    Logic (PRIORITY method):
    1. If font_name exactly matches level-1 header font_name - HEADER_1
    2. If font_name matches level-1 font but contains "Ital" - HEADER_2
    3. If font_name matches level-2 header font_name - HEADER_2
    
    Args:
        font_name: Element font name.
        header_rules: Header rules built from known headers.
    
    Returns:
        Header level (1-6) or None if not determined.
    """
    if not font_name or not header_rules:
        return None
    
    rules_by_level = header_rules.get('by_level', {})
    
    # Find font_name for level 1 (highest priority)
    level_1_font = None
    for level_key, level_rules in rules_by_level.items():
        if level_key == '1' or (isinstance(level_key, str) and level_key.isdigit() and int(level_key) == 1):
            level_1_font = level_rules.get('font_name')
            break
    
    # Find font_name for level 2
    level_2_font = None
    for level_key, level_rules in rules_by_level.items():
        if level_key == '2' or (isinstance(level_key, str) and level_key.isdigit() and int(level_key) == 2):
            level_2_font = level_rules.get('font_name')
            break
    
    # PRIORITY 1: Exact match with level 1
    if level_1_font and font_name == level_1_font:
        return 1
    
    # PRIORITY 2: If font_name contains level-1 base name + "Ital" - level 2
    if level_1_font:
        # Strip "Ital", "Italic", "Oblique" from font_name and compare to level_1_font
        # e.g. "NimbusRomNo9L-MediItal" -> "NimbusRomNo9L-Medi"
        font_base = font_name
        for suffix in ['Ital', 'Italic', 'Oblique', 'Obl']:
            if font_base.endswith(suffix):
                font_base = font_base[:-len(suffix)]
                break
        
        level_1_base = level_1_font
        for suffix in ['Ital', 'Italic', 'Oblique', 'Obl']:
            if level_1_base.endswith(suffix):
                level_1_base = level_1_base[:-len(suffix)]
                break
        
        # If base names match but font_name has "Ital" - level 2
        if font_base == level_1_base:
            font_lower = font_name.lower()
            if 'ital' in font_lower or 'oblique' in font_lower or 'obl' in font_lower:
                return 2
            # If base names match and no "Ital" - also level 1
            return 1
    
    # PRIORITY 3: Exact match with level 2
    if level_2_font and font_name == level_2_font:
        return 2
    
    return None


def _is_header_by_properties(
    text: str,
    properties: Dict[str, Any],
    header_rules: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Checks if text element is a header based on properties.
    
    Similar to _is_header_by_properties in DOCX parser.
    
    Checks:
    - Structural keywords (Abstract, Introduction, etc.)
    - Bold text (≥95% of text or font name indicates bold/medium)
    - Font size
    - Font name patterns (Medi, Bold, Ital, etc.)
    - Caps Lock (70%+ uppercase letters)
    - Numbered patterns with confirmation
    - Header rules from found headers (if provided)
    
    Args:
        text: Text content.
        properties: Text properties dictionary.
        header_rules: Optional header rules from build_header_rules.
    
    Returns:
        True if element is a header, False otherwise.
    """
    text = text.strip()
    if not text or text.endswith(':'):
        return False
    
    # Check structural keywords first (always HEADER_1) - highest priority
    if _is_structural_keyword(text):
        return True
    
    # Check font name for header indicators (Medi, Bold, etc.)
    # This is important because some PDFs encode bold/italic in font name, not flags
    font_name = properties.get('font_name', '')
    if font_name:
        font_lower = font_name.lower()
        # Font names with "Medi", "Bold", "Black", "Heavy" often indicate headers
        has_header_font = any(indicator in font_lower for indicator in [
            'medi', 'bold', 'black', 'heavy', 'demibold', 'semibold', 'extrabold'
        ])
        if has_header_font:
            # Additional check: short text or structural keyword
            if len(text) <= 100 or _is_structural_keyword(text):
                return True
    
    # If header_rules are provided, element must match the pattern of found headers
    if header_rules:
        rules_by_level = header_rules.get('by_level', {})
        common_header = header_rules.get('common_header', {})
        
        matches_any_rule = False
        
        # Check against level-specific rules
        for level, level_rules in rules_by_level.items():
            matches = 0
            total_checks = 0
            
            # Check font name
            if level_rules.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == level_rules['font_name']:
                    matches += 1
            
            # Check font size (allow ±1.0 tolerance)
            if level_rules.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = level_rules['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            # Check bold
            if level_rules.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == level_rules['is_bold']:
                    matches += 1
            
            # Check italic
            if level_rules.get('is_italic') is not None:
                total_checks += 1
                if properties.get('is_italic') == level_rules['is_italic']:
                    matches += 1
            
            # Check alignment
            if level_rules.get('alignment'):
                total_checks += 1
                if properties.get('alignment') == level_rules['alignment']:
                    matches += 1
            
            # Check Caps Lock
            if level_rules.get('is_caps_lock') is not None:
                total_checks += 1
                text_letters = [c for c in text if c.isalpha()]
                is_caps_lock = False
                if len(text_letters) >= 3:
                    uppercase_count = sum(1 for c in text_letters if c.isupper())
                    is_caps_lock = (uppercase_count / len(text_letters)) >= 0.7
                if is_caps_lock == level_rules['is_caps_lock']:
                    matches += 1
            
            if total_checks > 0:
                score = matches / total_checks
                if score >= 0.8:  # 80% match threshold
                    matches_any_rule = True
                    break
        
        # Check against common_header if no level match
        if not matches_any_rule and common_header:
            matches = 0
            total_checks = 0
            
            if common_header.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == common_header['font_name']:
                    matches += 1
            
            if common_header.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = common_header['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            if common_header.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == common_header['is_bold']:
                    matches += 1
            
            if common_header.get('is_italic') is not None:
                total_checks += 1
                if properties.get('is_italic') == common_header['is_italic']:
                    matches += 1
            
            if common_header.get('alignment'):
                total_checks += 1
                if properties.get('alignment') == common_header['alignment']:
                    matches += 1
            
            if common_header.get('is_caps_lock') is not None:
                total_checks += 1
                text_letters = [c for c in text if c.isalpha()]
                is_caps_lock = False
                if len(text_letters) >= 3:
                    uppercase_count = sum(1 for c in text_letters if c.isupper())
                    is_caps_lock = (uppercase_count / len(text_letters)) >= 0.7
                if is_caps_lock == common_header['is_caps_lock']:
                    matches += 1
            
            if total_checks > 0:
                score = matches / total_checks
                if score >= 0.8:  # 80% match threshold
                    matches_any_rule = True
        
        # If header_rules exist and element matches rules, it's a header
        if matches_any_rule:
            return True
        
        # If header_rules exist but element doesn't match any rule, check fallback criteria
        # Allow numbered headers with confirmation OR use fallback criteria
        if not matches_any_rule:
            # Check numbered header with confirmation (bold)
            is_numbered_header_with_capital = any(re.match(p, text) for p in [
                r'^\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1. Header" or "1 Header" (with separator)
                r'^\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1. Header" or "1.1 Header"
                r'^\d+\.\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1.1. Header" or "1.1.1 Header"
            ])
            if is_numbered_header_with_capital and properties.get('is_bold'):
                return True
            
            # Use fallback criteria if rules don't match
            # This ensures we don't filter out valid headers that just don't match the rules perfectly
            # Bold, short → potential header
            # Also check font name for bold/medium indicators
            is_bold = properties.get('is_bold', False)
            font_name = properties.get('font_name', '')
            if font_name:
                font_lower = font_name.lower()
                if any(indicator in font_lower for indicator in ['medi', 'bold', 'black', 'heavy']):
                    is_bold = True
            
            if is_bold and len(text) <= 100:
                return True
            
            # Check Caps Lock (70%+ uppercase letters)
            def _is_mostly_uppercase(text: str) -> bool:
                """Checks if majority of letters are uppercase (Caps Lock)."""
                if not text or not text.strip():
                    return False
                letters = [c for c in text if c.isalpha()]
                if len(letters) < 3:
                    return False
                uppercase_count = sum(1 for c in letters if c.isupper())
                return uppercase_count / len(letters) >= 0.7
            
            if (_is_mostly_uppercase(text) and
                len(text) >= 3 and len(text) <= 200):
                return True
            
            # If rules exist but element doesn't match rules and doesn't meet fallback criteria
            # Still allow it if it's a numbered header (even without bold confirmation)
            # This is more permissive than DOCX but needed for PDF where OCR might miss formatting
            if _is_numbered_header(text):
                return True
    
    # Fallback criteria: only use if NO header_rules are provided
    # Numbered pattern - require additional confirmation: bold
    is_numbered_header_with_capital = any(re.match(p, text) for p in [
        r'^\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1. Header" or "1 Header" (with separator)
        r'^\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1. Header" or "1.1 Header"
        r'^\d+\.\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1.1. Header" or "1.1.1 Header"
    ])
    # Also check font name for bold/medium indicators
    is_bold_fallback_no_rules = properties.get('is_bold', False)
    font_name_fallback_no_rules = properties.get('font_name', '')
    if font_name_fallback_no_rules:
        font_lower_fallback_no_rules = font_name_fallback_no_rules.lower()
        if any(indicator in font_lower_fallback_no_rules for indicator in ['medi', 'bold', 'black', 'heavy']):
            is_bold_fallback_no_rules = True

    if is_numbered_header_with_capital and is_bold_fallback_no_rules:
        return True
    
    # Bold, short → potential header
    if is_bold_fallback_no_rules and len(text) <= 100:
        return True
    
    # Check Caps Lock (70%+ uppercase letters)
    def _is_mostly_uppercase(text: str) -> bool:
        """Checks if majority of letters are uppercase (Caps Lock)."""
        if not text or not text.strip():
            return False
        letters = [c for c in text if c.isalpha()]
        if len(letters) < 3:
            return False
        uppercase_count = sum(1 for c in letters if c.isupper())
        return uppercase_count / len(letters) >= 0.7
    
    if (_is_mostly_uppercase(text) and
        len(text) >= 3 and len(text) <= 200):
        return True
    
    # Also allow numbered headers even without bold confirmation (for PDF OCR)
    if _is_numbered_header(text):
        return True
    
    # Final fallback: short text with font name indicating header
    if len(text) <= 80 and font_name:
        font_lower = font_name.lower()
        if any(indicator in font_lower for indicator in ['medi', 'bold', 'heading', 'title']):
            return True
    
    return False
