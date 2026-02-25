"""
Building document hierarchy from XML elements.
"""

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from PIL import Image

from ....domain import Element, ElementType
from .header_finder import extract_paragraph_properties


def _table_data_to_html(table_data: Dict[str, Any]) -> Optional[str]:
    """
    Converts table data from XML format to HTML.
    
    Args:
        table_data: Dictionary with table data from XML parser
        
    Returns:
        HTML string or None if HTML creation failed
    """
    try:
        data = table_data.get('data', [])
        if not data:
            return None
        
        # Determine maximum number of columns
        max_cols = max(len(row) for row in data) if data else 0
        if max_cols == 0:
            return None
        
        # Normalize all rows to same number of columns
        normalized_rows = []
        for row in data:
            # Pad with empty strings if columns are fewer
            normalized_row = list(row)
            while len(normalized_row) < max_cols:
                normalized_row.append("")
            # Truncate if columns are more
            normalized_rows.append(normalized_row[:max_cols])
        
        # Determine if first row is header
        # Heuristic: if first row contains short non-empty values
        # and there is at least one data row, use first row as headers
        first_row = normalized_rows[0] if normalized_rows else []
        use_first_row_as_header = False
        
        if len(normalized_rows) > 1 and first_row:
            # Check if first row looks like headers
            non_empty_cells = [cell.strip() for cell in first_row if cell.strip()]
            if non_empty_cells:
                # If majority of cells are non-empty and short, consider as headers
                avg_length = sum(len(cell) for cell in non_empty_cells) / len(non_empty_cells) if non_empty_cells else 0
                non_empty_ratio = len(non_empty_cells) / len(first_row) if first_row else 0
                
                # Headers are usually: short (avg length < 50), majority of cells filled (> 50%)
                use_first_row_as_header = (
                    avg_length < 50 and
                    non_empty_ratio > 0.5
                )
        
        # Build HTML table
        html_parts = ['<table>']
        
        if use_first_row_as_header and len(normalized_rows) > 1:
            # Add header row
            html_parts.append('<thead><tr>')
            for cell in first_row:
                cell_text = cell.strip() if cell else ""
                # Escape HTML special characters
                cell_text = cell_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                html_parts.append(f'<th>{cell_text}</th>')
            html_parts.append('</tr></thead>')
            data_rows = normalized_rows[1:]
        else:
            data_rows = normalized_rows
        
        # Add data rows
        html_parts.append('<tbody>')
        for row in data_rows:
            html_parts.append('<tr>')
            for cell in row:
                cell_text = cell.strip() if cell else ""
                # Escape HTML special characters
                cell_text = cell_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                html_parts.append(f'<td>{cell_text}</td>')
            html_parts.append('</tr>')
        html_parts.append('</tbody>')
        
        html_parts.append('</table>')
        
        return ''.join(html_parts)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error converting table to HTML: {e}")
        return None


def _is_table_caption(text: str) -> bool:
    """Checks if text is a table caption."""
    text_stripped = text.strip()
    if text_stripped.endswith(':'):
        return False
    
    text_lower = text_stripped.lower()
    patterns = [
        r'^таблица\s+\d+',
        r'^table\s+\d+',
        r'^табл\.\s*\d+',
        r'^tbl\.\s*\d+',
    ]
    return any(re.search(pattern, text_lower) for pattern in patterns)


def _is_image_caption(text: str) -> bool:
    """Checks if text is an image caption."""
    text_stripped = text.strip()
    if text_stripped.endswith(':'):
        return False
    
    text_lower = text_stripped.lower()
    patterns = [
        r'^рис\.\s*\d+',
        r'^рисунок\s+\d+',
        r'^figure\s+\d+',
        r'^fig\.\s*\d+',
        r'^изображение\s+\d+',
    ]
    return any(re.search(pattern, text_lower) for pattern in patterns)


def _is_structural_keyword(text: str) -> bool:
    """Checks if text is a structural keyword (HEADER_1 level)."""
    from ...headers.constants import SPECIAL_HEADER_1
    # Remove trailing colon before comparison
    text_normalized = text.strip().rstrip(':').strip().upper()
    return text_normalized in SPECIAL_HEADER_1


def _is_header_by_properties(
    text: str, 
    properties: Dict[str, Any], 
    header_rules: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Checks if paragraph is a header based on XML properties.
    
    Checks:
    - Heading style (Heading1, Heading2, "1", "2", "3")
    - Bold text (≥95% of text)
    - Font size
    - Caps Lock (70%+ uppercase letters)
    - Numbered patterns with confirmation
    - Header rules from OCR headers (if provided)
    """
    text = text.strip()
    if not text or text.endswith(':'):
        return False
    
    if _is_table_caption(text) or _is_image_caption(text):
        return False
    
    # Check definition pattern
    dash_patterns = [' – ', ' — ', ' - ']
    for dash in dash_patterns:
        idx = text.find(dash)
        if idx > 0:
            term = text[:idx].strip()
            definition = text[idx + len(dash):].strip()
            term_words = len(term.split())
            if 1 <= term_words <= 5 and len(definition) > 0:
                return False
    
    # IMPORTANT: Style check has HIGHEST priority - if element has heading style, it's ALWAYS a header
    # This must be checked BEFORE header rules to ensure style takes precedence
    style = properties.get('style')
    has_heading_style = (style and style.isdigit()) or properties.get('is_heading_style')
    
    # Style "1", "2", "3" - definitely header
    if style and style.isdigit():
        return True
    
    # is_heading_style (Heading1, Heading2, Title...) - definitely header
    if properties.get('is_heading_style'):
        return True
    
    # Structural keyword
    if _is_structural_keyword(text):
        return True
    
    # IMPORTANT: Numbered pattern check is moved AFTER header rules check
    # This ensures that if header_rules exist, they take precedence
    # Numbered pattern is only checked if no header_rules OR as exception when rules don't match
    
    # IMPORTANT: Check against header rules from OCR headers
    # If header_rules are provided, element must match the pattern of found headers
    # BUT: if element has explicit heading style, it's ALWAYS a header (already checked above)
    # This check is for elements WITHOUT explicit heading style - they must match rules
    if header_rules:
        rules_by_level = header_rules.get('by_level', {})
        common_header = header_rules.get('common_header', {})
        
        # Check if element matches any level rules
        matches_any_rule = False
        matched_level = None  # Сохраняем уровень, для которого элемент соответствует правилам
        
        for level, level_rules in rules_by_level.items():
            matches = 0
            total_checks = 0
            
            # Check font_name
            if level_rules.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == level_rules['font_name']:
                    matches += 1
            
            # Check font_size
            if level_rules.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = level_rules['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            # Check is_bold
            if level_rules.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == level_rules['is_bold']:
                    matches += 1
            
            # Check style_pattern (higher weight)
            if level_rules.get('style_pattern'):
                total_checks += 3
                if properties.get('style') == level_rules['style_pattern']:
                    matches += 3
            
            # Check is_heading_style
            if level_rules.get('is_heading_style') is not None:
                total_checks += 1
                if properties.get('is_heading_style') == level_rules['is_heading_style']:
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
            
            # Check is_italic (important for level 2 headers)
            if level_rules.get('is_italic') is not None:
                total_checks += 1
                if properties.get('is_italic') == level_rules['is_italic']:
                    matches += 1
            
            if total_checks > 0:
                # IMPORTANT: Style is CRITICAL - if rules specify a style pattern, element MUST have it
                # If style doesn't match, reject immediately, regardless of other properties
                style_pattern = level_rules.get('style_pattern')
                if style_pattern is not None:
                    element_style = properties.get('style')
                    if element_style != style_pattern:
                        # Style doesn't match - reject immediately
                        continue
                
                # IMPORTANT: Check critical properties (font_size, is_bold, is_italic)
                # These must match if specified in rules
                critical_properties_match = True
                if level_rules.get('font_size') is not None:
                    font_size = properties.get('font_size')
                    if font_size:
                        target_size = level_rules['font_size']
                        if abs(font_size - target_size) > 1.0:
                            critical_properties_match = False
                
                if level_rules.get('is_bold') is not None:
                    if properties.get('is_bold') != level_rules['is_bold']:
                        critical_properties_match = False
                
                if level_rules.get('is_italic') is not None:
                    if properties.get('is_italic') != level_rules['is_italic']:
                        critical_properties_match = False
                
                if not critical_properties_match:
                    # Critical properties don't match - reject
                    continue
                
                score = matches / total_checks
                # IMPORTANT: Require at least 80% match for other properties (increased from 70%)
                if score >= 0.8:  # At least 80% match
                    matches_any_rule = True
                    matched_level = level  # Сохраняем уровень, для которого элемент соответствует правилам
                    break
        
        # Check common_header if no level match
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
            
            if common_header.get('style_pattern'):
                total_checks += 1
                if properties.get('style') == common_header['style_pattern']:
                    matches += 1
            
            if common_header.get('is_heading_style') is not None:
                total_checks += 1
                if properties.get('is_heading_style') == common_header['is_heading_style']:
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
                # IMPORTANT: Style is CRITICAL - if rules specify a style pattern, element MUST have it
                style_pattern = common_header.get('style_pattern')
                if style_pattern is not None:
                    element_style = properties.get('style')
                    if element_style != style_pattern:
                        # Style doesn't match - reject immediately
                        matches_any_rule = False
                    else:
                        # Check critical properties (font_size, is_bold, is_italic)
                        critical_properties_match = True
                        if common_header.get('font_size') is not None:
                            font_size = properties.get('font_size')
                            if font_size:
                                target_size = common_header['font_size']
                                if abs(font_size - target_size) > 1.0:
                                    critical_properties_match = False
                        
                        if common_header.get('is_bold') is not None:
                            if properties.get('is_bold') != common_header['is_bold']:
                                critical_properties_match = False
                        
                        if common_header.get('is_italic') is not None:
                            if properties.get('is_italic') != common_header['is_italic']:
                                critical_properties_match = False
                        
                        if critical_properties_match:
                            score = matches / total_checks
                            # IMPORTANT: Require at least 80% match for other properties
                            if score >= 0.8:  # At least 80% match
                                matches_any_rule = True
                        else:
                            matches_any_rule = False
                else:
                    # Check critical properties even if no style pattern
                    critical_properties_match = True
                    if common_header.get('font_size') is not None:
                        font_size = properties.get('font_size')
                        if font_size:
                            target_size = common_header['font_size']
                            if abs(font_size - target_size) > 1.0:
                                critical_properties_match = False
                    
                    if common_header.get('is_bold') is not None:
                        if properties.get('is_bold') != common_header['is_bold']:
                            critical_properties_match = False
                    
                    if common_header.get('is_italic') is not None:
                        if properties.get('is_italic') != common_header['is_italic']:
                            critical_properties_match = False
                    
                    if critical_properties_match:
                        score = matches / total_checks
                        if score >= 0.8:  # At least 80% match
                            matches_any_rule = True
                    else:
                        matches_any_rule = False
        
        # IMPORTANT: If header_rules exist but element doesn't match any rule, it's NOT a header
        # (unless it has explicit heading style or numbered pattern with confirmation)
        if not matches_any_rule:
            # Allow ONLY if it's a numbered header with confirmation (bold OR heading style)
            # AND it matches the pattern properly (e.g., "1. Заголовок", not "1Adhera")
            # IMPORTANT: Must have separator (space or dot+space) between number and letter
            # AND must NOT be a list item
            if not properties.get('is_list_item'):
                is_numbered_header = any(re.match(p, text) for p in [
                    r'^\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1. Заголовок" or "1 Заголовок" (with separator)
                    r'^\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1. Заголовок" or "1.1 Заголовок"
                    r'^\d+\.\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1.1. Заголовок" or "1.1.1 Заголовок"
                ])
                # IMPORTANT: Must be numbered header pattern AND have confirmation (bold OR heading style)
                if is_numbered_header and (properties.get('is_bold') or has_heading_style):
                    # This is a valid numbered header with confirmation - allow it
                    return True
            # Element doesn't match rules and is not a valid numbered header - NOT a header
            return False
    
    # IMPORTANT: If header_rules are provided, ONLY check rules-based criteria
    # Don't use fallback criteria (bold, caps lock) if rules exist
    if header_rules:
        # If we got here and rules exist, element matched rules (matches_any_rule = True)
        # BUT: For HEADER_1 level, we require numbered pattern (unless it's a structural keyword or has explicit heading style)
        # This prevents marking regular text as HEADER_1 based on style matching alone
        if matches_any_rule:
            # Check if this element matches rules for level 1 (HEADER_1)
            # If matched_level is 1 or '1', or if we need to check level 1 rules
            rules_by_level = header_rules.get('by_level', {})
            level_1_rules = rules_by_level.get('1') or rules_by_level.get(1)
            
            # Check if element matches level 1 rules
            matches_level_1 = False
            if matched_level in (1, '1'):
                matches_level_1 = True
            elif level_1_rules:
                # Check if element matches level 1 rules by comparing critical properties
                critical_match = True
                if level_1_rules.get('font_size'):
                    font_size = properties.get('font_size')
                    if font_size:
                        target_size = level_1_rules['font_size']
                        if abs(font_size - target_size) > 1.0:
                            critical_match = False
                    else:
                        critical_match = False
                
                if level_1_rules.get('is_bold') is not None:
                    if properties.get('is_bold') != level_1_rules['is_bold']:
                        critical_match = False
                
                if level_1_rules.get('is_italic') is not None:
                    if properties.get('is_italic') != level_1_rules['is_italic']:
                        critical_match = False
                
                if level_1_rules.get('style_pattern'):
                    if properties.get('style') != level_1_rules['style_pattern']:
                        critical_match = False
                
                matches_level_1 = critical_match
            
            # If matches level 1 rules, require numbering (unless structural keyword or explicit heading style)
            if matches_level_1 and not _is_structural_keyword(text) and not has_heading_style:
                # Check if element is numbered
                is_numbered_header = any(re.match(p, text) for p in [
                    r'^\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1. Заголовок" or "1 Заголовок"
                    r'^\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1. Заголовок" or "1.1 Заголовок"
                    r'^\d+\.\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1.1. Заголовок" or "1.1.1 Заголовок"
                ])
                if not is_numbered_header:
                    # Element matches level 1 rules but is not numbered - NOT a header
                    return False
        
        # Element matched rules and passed all checks (or doesn't match level 1 rules)
        return True
    
    # Fallback criteria: only use if NO header_rules are provided
    # IMPORTANT: For HEADER_1, we require numbered pattern (e.g., "1. Заголовок")
    # when there's no explicit heading style or structural keyword
    # This prevents marking regular text as headers based on bold or caps lock alone
    
    # Numbered pattern - require additional confirmation: bold OR heading style OR caps
    # Support variants: "1. Заголовок", "1 Заголовок" (with separator), NOT "1Заголовок" (no separator)
    # IMPORTANT: Must have separator (space or dot+space) between number and letter to avoid matching "1Adhera"
    if not properties.get('is_list_item'):
        is_numbered_header = any(re.match(p, text) for p in [
            r'^\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1. Заголовок" or "1 Заголовок" (with separator)
            r'^\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1. Заголовок" or "1.1 Заголовок"
            r'^\d+\.\d+\.\d+(?:\.\s+|\s+)[А-ЯЁA-Z]',  # "1.1.1. Заголовок" or "1.1.1 Заголовок"
        ])
        if is_numbered_header:
            # Check for confirmation: bold OR heading style OR caps lock
            is_bold = properties.get('is_bold', False)
            is_caps = False
            text_letters = [c for c in text if c.isalpha()]
            if len(text_letters) >= 3:
                uppercase_count = sum(1 for c in text_letters if c.isupper())
                is_caps = (uppercase_count / len(text_letters)) >= 0.7
            
            if is_bold or has_heading_style or is_caps:
                return True
    
    # IMPORTANT: For HEADER_1, bold or caps lock alone is NOT enough
    # They must be combined with numbered pattern to avoid false positives
    # Exception: structural keywords and explicit heading styles are already handled above
    
    return False


def _determine_header_level(
    text: str,
    properties: Dict[str, Any],
    header_data: Optional[Dict[str, Any]] = None,
    header_stack: List[Tuple[int, str, bool]] = None
) -> int:
    """
    Determines header level with clear priorities.
    
    Priority order:
    1. Structural keywords (Введение, Заключение) = ALWAYS level 1
    2. Chapter patterns ("Глава X", "Часть X") = ALWAYS level 1
    3. Numbered headers level 1 ("1", "2", "3" without sublevels) = ALWAYS level 1
    4. Style = number ("1", "2", "3")
    5. Heading style
    6. Numbering ("12.1." = level 2, "12.1.1." = level 3)
    7. Context (nearest numbered parent in stack)
    """
    if header_stack is None:
        header_stack = []
    
    # Priority 1: Structural keywords = ALWAYS level 1
    if _is_structural_keyword(text):
        return 1
    
    # Priority 2: Chapter patterns = ALWAYS level 1
    text_lower = text.strip().lower()
    chapter_patterns = [
        r'^глава\s+\d+', r'^часть\s+\d+', r'^раздел\s+\d+',
        r'^chapter\s+\d+', r'^part\s+\d+', r'^section\s+\d+',
    ]
    for pattern in chapter_patterns:
        if re.match(pattern, text_lower):
            return 1
    
    # Priority 3: Numbered headers level 1 (just "1", "2", "3" without sublevels) = ALWAYS level 1
    # Support variants with and without space: "1Анализ", "1. Анализ", "1"
    # IMPORTANT: "1.1Актуальность" should be level 2, not 1
    full_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.?\s*)?', text.strip())
    if full_match:
        # If there are sublevels (1.1, 1.1.1) - process below
        if full_match.group(2) or full_match.group(3):
            # Has sublevels - don't return 1, process below
            pass
        else:
            # Just "1", "2", "3" without sublevel - ALWAYS level 1
            return 1
    
    # Priority 4: Style = number ("1", "2", "3")
    style = properties.get('style')
    if style and style.isdigit():
        return int(style)
    
    # Priority 5: Heading style
    if properties.get('is_heading_style') and properties.get('level'):
        return properties['level']
    
    # Priority 6: From numbering
    # Support variants with and without space: "1Анализ", "1.1Актуальность", "1. Анализ", "1.1. Актуальность"
    numbered_level = None
    # First try pattern with dot and optional space
    match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.?\s*)?', text.strip())
    if match:
        if match.group(3):
            numbered_level = 3
        elif match.group(2):
            numbered_level = 2
        elif match.group(1):
            numbered_level = 1
    
    # If numbering determined level 1 (just "1", without sublevel) - ALWAYS level 1
    if numbered_level == 1:
        return 1
    
    if numbered_level is not None:
        return numbered_level
    
    # Priority 7: From header_data (fallback) - but only if style is not available
    # IMPORTANT: If there is a style, it must have priority over header_data.level
    # header_data.level may be incorrectly determined from OCR or TOC context
    # Style from XML is the source of truth for header level
    if header_data and header_data.get('level') is not None:
        # Check if there is a style - if yes, don't use header_data.level
        # Style has priority because it's a property of the paragraph itself in XML
        has_style = (style and style.isdigit()) or properties.get('is_heading_style')
        if not has_style:
            lvl = header_data.get('level')
            if isinstance(lvl, str):
                try:
                    lvl = int(lvl)
                except Exception:
                    lvl = None
            if lvl and lvl != 'unknown':
                # IMPORTANT: If header_data.level = 1, but there are no other level indicators (style, numbering),
                # and there is context (header_stack), it's better to use context
                # This prevents incorrect determination of level 1 for headers that should be level 3
                is_current_numbered = bool(re.match(r'^\d+', text.strip()))
                if lvl == 1 and header_stack and not is_current_numbered:
                    # Skip header_data.level = 1, use context below
                    pass
                else:
                    return lvl
    
    # Priority 8: Context - find nearest numbered parent in stack
    # IMPORTANT: Context is used ONLY if there is no style
    # Style from XML is the source of truth, it should not be overridden by context
    has_style = (style and style.isdigit()) or properties.get('is_heading_style')
    if not has_style and header_stack:
        is_current_numbered = bool(re.match(r'^\d+', text.strip()))
        if not is_current_numbered:
            # For non-numbered: find nearest numbered/structural parent
            for stack_level, _, stack_is_numbered in reversed(header_stack):
                if stack_is_numbered:
                    return min(stack_level + 1, 6)
            # If no numbered parents - use level of last header
            return header_stack[-1][0] if header_stack else 1
        else:
            # For numbered: level below last
            last_level = header_stack[-1][0] if header_stack else 1
            return min(last_level + 1, 6)
    
    # Final check: structural keywords ALWAYS level 1
    if _is_structural_keyword(text):
        return 1
    
    return 1


def build_hierarchy(
    all_headers: List[Dict[str, Any]],
    all_xml_elements: List[Dict[str, Any]],
    docx_tables: List[Dict[str, Any]],
    docx_images: List[Dict[str, Any]],
    docx_path: Path,
    id_generator,
    max_text_block_size: int = 3000,
    max_paragraphs_per_block: int = 10,
    header_rules: Optional[Dict[str, Any]] = None
) -> List[Element]:
    """
    Builds complete document hierarchy from XML elements.
    
    Args:
        all_headers: List of found headers
        all_xml_elements: All XML elements
        docx_tables: List of tables
        docx_images: List of images
        docx_path: Path to DOCX file
        id_generator: ID generator for elements
        
    Returns:
        List of elements with hierarchy
    """
    elements: List[Element] = []
    header_stack: List[Tuple[int, str, bool]] = []
    
    header_by_pos = {}
    for h in all_headers:
        pos = h.get('xml_position')
        if pos is not None:
            header_by_pos[pos] = h
    
    tables_by_position = {t.get('xml_position'): t for t in docx_tables}
    images_by_position = {img.get('xml_position'): img for img in docx_images}
    
    properties_cache = {}
    
    def get_properties(pos):
        if pos not in properties_cache:
            properties_cache[pos] = extract_paragraph_properties(docx_path, pos)
        return properties_cache[pos]
    
    current_text_block = []
    current_text_positions = []
    current_text_size = 0
    
    def flush_text_block():
        """
        Saves accumulated text block as element.
        If block contains numbered list items (1., 2., 3., ...), splits them into list_item.
        """
        nonlocal current_text_block, current_text_positions, current_text_size
        if not current_text_block:
            return
        
        # Check if text block contains numbered list items
        # Preserve order: text BEFORE list → list items → text AFTER list
        processed_elements = []  # List of elements in correct order: (type, content, xml_pos)
        
        i = 0
        while i < len(current_text_block):
            para = current_text_block[i].strip()
            if not para:
                i += 1
                continue
            
            # Check if paragraph is a numbered list item
            match = re.match(r'^(\d+)\.\s+(.+)$', para)
            if match:
                item_num = int(match.group(1))
                item_text = match.group(2).strip()
                
                # Check if this is part of a sequence (1., 2., 3., ...)
                sequence = [(item_num, item_text, i)]
                j = i + 1
                expected_num = item_num + 1
                
                while j < len(current_text_block):
                    next_para = current_text_block[j].strip()
                    if not next_para:
                        j += 1
                        continue
                    next_match = re.match(r'^(\d+)\.\s+(.+)$', next_para)
                    if next_match and int(next_match.group(1)) == expected_num:
                        sequence.append((expected_num, next_match.group(2).strip(), j))
                        expected_num += 1
                        j += 1
                    else:
                        break
                
                # If found sequence of 2+ elements - this is a list
                if len(sequence) >= 2:
                    # Add all sequence elements as list_item in correct order
                    for seq_num, seq_text, seq_idx in sequence:
                        list_item_content = f"{seq_num}. {seq_text}"
                        xml_pos_for_item = current_text_positions[seq_idx] if seq_idx < len(current_text_positions) else (current_text_positions[-1] if current_text_positions else 0)
                        processed_elements.append(('list_item', list_item_content, xml_pos_for_item))
                    i = j
                    continue
            
            # If not numbered list item - add as text
            xml_pos_for_text = current_text_positions[i] if i < len(current_text_positions) else (current_text_positions[-1] if current_text_positions else 0)
            processed_elements.append(('text', current_text_block[i], xml_pos_for_text))
            i += 1
        
        # Now add elements in correct order
        text_parts = []
        text_positions = []
        
        for elem_type, elem_content, elem_xml_pos in processed_elements:
            if elem_type == 'list_item':
                # If text accumulated - save it first
                if text_parts:
                    text_content = '\n\n'.join(text_parts)
                    # Collect links from text positions
                    all_links = []
                    for pos in text_positions:
                        if pos < len(all_xml_elements):
                            elem = all_xml_elements[pos]
                            elem_links = elem.get('links', [])
                            if elem_links:
                                all_links.extend(elem_links)
                    all_links = list(set(all_links)) if all_links else []
                    
                    metadata = {
                        'source': 'xml',
                        'position': list(text_positions),
                        'size': len(text_content)
                    }
                    if all_links:
                        metadata['links'] = all_links
                    
                    text_element = Element(
                        id=id_generator.next_id(),
                        type=ElementType.TEXT,
                        content=text_content,
                        parent_id=header_stack[-1][1] if header_stack else None,
                        metadata=metadata
                    )
                    elements.append(text_element)
                    text_parts = []
                    text_positions = []
                
                # Add list_item
                list_item_element = Element(
                    id=id_generator.next_id(),
                    type=ElementType.LIST_ITEM,
                    content=elem_content,
                    parent_id=header_stack[-1][1] if header_stack else None,
                    metadata={
                        'xml_position': elem_xml_pos,
                        'source': 'xml',
                        'list_type': 'numbered'
                    }
                )
                elements.append(list_item_element)
            else:  # text
                # Accumulate text
                text_parts.append(elem_content)
                text_positions.append(elem_xml_pos)
        
        # If text remains - save it
        if text_parts:
            text_content = '\n\n'.join(text_parts)
            # Collect links from text positions
            all_links = []
            for pos in text_positions:
                if pos < len(all_xml_elements):
                    elem = all_xml_elements[pos]
                    elem_links = elem.get('links', [])
                    if elem_links:
                        all_links.extend(elem_links)
            all_links = list(set(all_links)) if all_links else []
            
            metadata = {
                'source': 'xml',
                'position': list(text_positions),
                'size': len(text_content)
            }
            if all_links:
                metadata['links'] = all_links
            
            text_element = Element(
                id=id_generator.next_id(),
                type=ElementType.TEXT,
                content=text_content,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata=metadata
            )
            elements.append(text_element)
        
        current_text_block = []
        current_text_positions = []
        current_text_size = 0
    
    def add_header_element(text: str, level: int, xml_pos: int, ocr_header: Optional[Dict] = None):
        nonlocal header_stack
        flush_text_block()
        
        header_type_map = {
            1: ElementType.HEADER_1, 2: ElementType.HEADER_2,
            3: ElementType.HEADER_3, 4: ElementType.HEADER_4,
            5: ElementType.HEADER_5, 6: ElementType.HEADER_6,
        }
        element_type = header_type_map.get(level, ElementType.HEADER_1)
        
        while header_stack and header_stack[-1][0] >= level:
            header_stack.pop()
        
        parent_id = header_stack[-1][1] if header_stack else None
        
        # Extract links from header element
        header_links = []
        if xml_pos < len(all_xml_elements):
            header_elem = all_xml_elements[xml_pos]
            header_links = header_elem.get('links', [])
        
        if ocr_header:
            source = 'ocr_then_xml'
            metadata = {
                'source': source,
                'position': xml_pos,
                'level': level,
                'bbox': ocr_header.get('bbox', []),
                'page_num': ocr_header.get('page_num', 0),
            }
        else:
            source = 'xml'
            metadata = {
                'source': source,
                'position': xml_pos,
                'level': level,
            }
        
        # Add links to metadata if found
        if header_links:
            metadata['links'] = list(set(header_links))  # Remove duplicates
        
        header_element = Element(
            id=id_generator.next_id(),
            type=element_type,
            content=text,
            parent_id=parent_id,
            metadata=metadata
        )
        elements.append(header_element)
        is_numbered = bool(re.match(r'^\d+', text.strip()))
        header_stack.append((level, header_element.id, is_numbered))
    
    for xml_elem in all_xml_elements:
        xml_pos = xml_elem.get('xml_position', 0)
        elem_type = xml_elem.get('type')
        
        if elem_type == 'table':
            flush_text_block()
            table_data = tables_by_position.get(xml_pos)
            if table_data:
                # Convert table to HTML
                table_html = _table_data_to_html(table_data)
                
                # Create metadata
                metadata = {
                    'source': 'xml',
                    'position': xml_pos,
                    'table_index': table_data.get('index', 0),
                    'rows_count': table_data.get('rows_count', 0),
                    'cols_count': table_data.get('cols_count', 0),
                }
                
                # Add OCR match information if available (structure-based matching)
                if 'ocr_match' in table_data:
                    ocr_match = table_data['ocr_match']
                    metadata['ocr_match'] = {
                        'ocr_table_bbox': ocr_match.get('ocr_table_bbox', []),
                        'ocr_table_page': ocr_match.get('ocr_table_page', 0),
                        'similarity': ocr_match.get('similarity', 0.0),
                        'matched_by': 'structure'
                    }
                    # Store headers for reference
                    if 'xml_headers' in ocr_match:
                        metadata['table_headers'] = ocr_match['xml_headers']
                
                # Add caption information if available (from OCR matching)
                if 'captions' in table_data and table_data['captions']:
                    # Use the first matched caption
                    caption_info = table_data['captions'][0]
                    metadata['caption'] = caption_info.get('text', '')
                    if 'table_number' in caption_info:
                        metadata['table_number'] = caption_info['table_number']
                    if 'bbox' in caption_info:
                        metadata['caption_bbox'] = caption_info['bbox']
                    if 'page' in caption_info:
                        metadata['caption_page'] = caption_info['page']
                
                # Store HTML in content (or empty string if conversion failed)
                table_content = table_html if table_html else ""
                
                elements.append(Element(
                    id=id_generator.next_id(),
                    type=ElementType.TABLE,
                    content=table_content,
                    parent_id=header_stack[-1][1] if header_stack else None,
                    metadata=metadata
                ))
            continue
        
        if elem_type != 'paragraph':
            continue
        
        text = xml_elem.get('text', '').strip()
        text_raw = xml_elem.get('text', '')
        text_size = len(text_raw)
        has_image = xml_elem.get('has_image', False)
        
        if xml_pos in images_by_position:
            flush_text_block()
            image_data = images_by_position[xml_pos]
            image_path = image_data.get('image_path', '')
            image_bytes = image_data.get('image_bytes')
            
            # Convert image to base64
            image_base64 = None
            if image_bytes:
                try:
                    # Determine image format from bytes or path
                    image_format = 'png'  # Default
                    
                    # Try to determine format from image bytes
                    try:
                        img = Image.open(BytesIO(image_bytes))
                        image_format = img.format.lower() if img.format else 'png'
                        # Normalize format names
                        if image_format in ['jpg', 'jpeg']:
                            image_format = 'jpeg'
                        elif image_format not in ['png', 'gif', 'webp', 'bmp']:
                            image_format = 'png'  # Fallback to PNG
                    except Exception:
                        # If PIL can't determine format, try from path
                        if image_path:
                            ext = Path(image_path).suffix.lower()
                            if ext in ['.jpg', '.jpeg']:
                                image_format = 'jpeg'
                            elif ext == '.gif':
                                image_format = 'gif'
                            elif ext == '.webp':
                                image_format = 'webp'
                            elif ext == '.bmp':
                                image_format = 'bmp'
                    
                    img_base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
                    image_base64 = f"data:image/{image_format};base64,{img_base64_encoded}"
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error converting image to base64: {e}")
            
            # Create image metadata
            image_metadata = {
                'source': 'xml',
                'position': xml_pos,
                'image_index': image_data.get('index', 0),
                'image_path': image_path,  # Keep for backward compatibility
                'image_data': image_base64,  # Base64 encoded image
                'width': image_data.get('width'),
                'height': image_data.get('height'),
            }
            
            # Add caption information if available (from OCR matching)
            if 'captions' in image_data and image_data['captions']:
                # Use the first matched caption
                caption_info = image_data['captions'][0]
                image_metadata['caption'] = caption_info.get('text', '')
                if 'image_number' in caption_info:
                    image_metadata['image_number'] = caption_info['image_number']
                if 'bbox' in caption_info:
                    image_metadata['caption_bbox'] = caption_info['bbox']
                if 'page' in caption_info:
                    image_metadata['caption_page'] = caption_info['page']
            
            elements.append(Element(
                id=id_generator.next_id(),
                type=ElementType.IMAGE,
                content=Path(image_path).name if image_path else '',
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata=image_metadata
            ))
            continue
        
        if not text and not has_image:
            continue
        
        props = get_properties(xml_pos)
        
        if xml_pos in header_by_pos:
            header_data = header_by_pos[xml_pos]
            # IMPORTANT: Use text from XML (DOCX) if available, otherwise use OCR text
            # OCR is needed for scanned documents (images only, no text in XML)
            # Similar to scanned PDF handling
            if text and text.strip():
                header_text = text.strip()
            else:
                # No text in XML - use OCR text (for scanned documents)
                header_text = header_data.get('text', '').strip()
            
            if not (header_text.endswith(':') or _is_table_caption(header_text) or _is_image_caption(header_text)):
                # IMPORTANT: Check style first - if element has heading style, it's ALWAYS a header
                # This has highest priority, even if it doesn't match header rules
                style = props.get('style')
                has_heading_style = (style and style.isdigit()) or props.get('is_heading_style')
                
                # IMPORTANT: If element found by OCR but has NO heading style and doesn't match header rules,
                # it should NOT be a header (e.g., author names, affiliations)
                if not has_heading_style and header_rules:
                    # Check if element matches header rules - must match CRITICAL properties
                    if not _is_header_by_properties(header_text, props, header_rules):
                        # This element doesn't match header rules and has no heading style - treat as text
                        if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
                            flush_text_block()
                        current_text_block.append(text_raw)
                        current_text_positions.append(xml_pos)
                        current_text_size += text_size
                        continue
                
                # IMPORTANT: Check if this is a list item
                # even if OCR identified it as a header
                if props.get('is_list_item'):
                    # Check if this is a numbered header
                    # Numbered header: "1. Заголовок" or "1 Заголовок" (with separator, capital letter after number)
                    # List item: "1. текст" or "1 текст" (lowercase letter after number)
                    # IMPORTANT: Must have separator to avoid matching "1Adhera"
                    is_numbered_header_with_capital = bool(re.match(r'^\d+(?:\.\s+|\s+)[А-ЯЁA-Z]', header_text))
                    
                    # If it's NOT a numbered header with capital letter and NOT a heading style - this is a list item
                    if not is_numbered_header_with_capital and not has_heading_style:
                        # This is a list item, add to text block
                        if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
                            flush_text_block()
                        current_text_block.append(text_raw)
                        current_text_positions.append(xml_pos)
                        current_text_size += text_size
                        continue
                
                # Check if this is part of a list sequence (1., 2., 3., ...)
                is_part_of_list_sequence = False
                text_match = re.match(r'^(\d+)\.\s+(.+)$', header_text)
                if text_match:
                    curr_num = int(text_match.group(1))
                    # Find current element in all_xml_elements
                    current_elem_idx = None
                    for idx, xml_elem_check in enumerate(all_xml_elements):
                        if xml_elem_check.get('xml_position') == xml_pos:
                            current_elem_idx = idx
                            break
                    
                    if current_elem_idx is not None:
                        # Check previous elements (within 5 positions)
                        for offset in range(1, min(6, current_elem_idx + 1)):
                            prev_elem = all_xml_elements[current_elem_idx - offset]
                            if prev_elem.get('type') == 'paragraph':
                                prev_text = prev_elem.get('text', '').strip()
                                prev_match = re.match(r'^(\d+)\.\s+(.+)$', prev_text)
                                if prev_match:
                                    prev_num = int(prev_match.group(1))
                                    # If previous element is the previous number (1. → 2., 2. → 3., ...)
                                    if prev_num == curr_num - 1:
                                        is_part_of_list_sequence = True
                                        break
                                elif prev_text:  # If there is text, but not numbered - stop search
                                    break
                        
                        # Check next elements (within 5 positions)
                        if not is_part_of_list_sequence:
                            for offset in range(1, min(6, len(all_xml_elements) - current_elem_idx)):
                                next_elem = all_xml_elements[current_elem_idx + offset]
                                if next_elem.get('type') == 'paragraph':
                                    next_text = next_elem.get('text', '').strip()
                                    next_match = re.match(r'^(\d+)\.\s+(.+)$', next_text)
                                    if next_match:
                                        next_num = int(next_match.group(1))
                                        # If next element is the next number (1. → 2., 2. → 3., ...)
                                        if next_num == curr_num + 1:
                                            is_part_of_list_sequence = True
                                            break
                                    elif next_text:  # If there is text, but not numbered - stop search
                                        break
                
                # If this is part of a list sequence - not a header, add to text block
                if is_part_of_list_sequence:
                    if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
                        flush_text_block()
                    current_text_block.append(text_raw)
                    current_text_positions.append(xml_pos)
                    current_text_size += text_size
                    continue
                
                level = _determine_header_level(header_text, props, header_data, header_stack)
                add_header_element(
                    header_text, level, xml_pos,
                    ocr_header=header_data.get('ocr_header')
                )
                continue
        
        # Check if XML element is a header even if not found via OCR
        # This handles cases where OCR missed headers but they exist in XML with heading styles or numbering patterns
        if text and text.strip():
            text_stripped = text.strip()
            
            # IMPORTANT: Skip list items - they should not be identified as headers
            # even if they look like headers (bold, large, etc.)
            if props.get('is_list_item'):
                # Check if this is a numbered header
                # Numbered header: "1. Заголовок" or "1Заголовок" (capital letter after number)
                # List item: "1. текст" or "1текст" (lowercase letter after number)
                is_numbered_header_with_capital = bool(re.match(r'^\d+(?:\.\s*)?[А-ЯЁA-Z]', text_stripped))
                
                # If it's NOT a numbered header with capital letter and NOT a heading style - skip
                if not is_numbered_header_with_capital and not props.get('is_heading_style'):
                    # This is a list item, add to text block
                    if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
                        flush_text_block()
                    current_text_block.append(text_raw)
                    current_text_positions.append(xml_pos)
                    current_text_size += text_size
                    continue
            
            # Check if part of list sequence (1., 2., 3., ...)
            is_part_of_list_sequence = False
            text_match = re.match(r'^(\d+)\.\s+(.+)$', text_stripped)
            if text_match:
                curr_num = int(text_match.group(1))
                # Find current element index
                current_elem_idx = None
                for idx, xml_elem_check in enumerate(all_xml_elements):
                    if xml_elem_check.get('xml_position') == xml_pos:
                        current_elem_idx = idx
                        break
                
                if current_elem_idx is not None:
                    # Check previous elements (within 5 positions)
                    for offset in range(1, min(6, current_elem_idx + 1)):
                        prev_elem = all_xml_elements[current_elem_idx - offset]
                        if prev_elem.get('type') == 'paragraph':
                            prev_text = prev_elem.get('text', '').strip()
                            prev_match = re.match(r'^(\d+)\.\s+(.+)$', prev_text)
                            if prev_match:
                                prev_num = int(prev_match.group(1))
                                if prev_num == curr_num - 1:
                                    is_part_of_list_sequence = True
                                    break
                            elif prev_text:
                                break
                    
                    # Check next elements (within 5 positions)
                    if not is_part_of_list_sequence:
                        for offset in range(1, min(6, len(all_xml_elements) - current_elem_idx)):
                            next_elem = all_xml_elements[current_elem_idx + offset]
                            if next_elem.get('type') == 'paragraph':
                                next_text = next_elem.get('text', '').strip()
                                next_match = re.match(r'^(\d+)\.\s+(.+)$', next_text)
                                if next_match:
                                    next_num = int(next_match.group(1))
                                    if next_num == curr_num + 1:
                                        is_part_of_list_sequence = True
                                        break
                                elif next_text:
                                    break
            
            # If part of list sequence - not a header, add to text block
            if is_part_of_list_sequence:
                if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
                    flush_text_block()
                current_text_block.append(text_raw)
                current_text_positions.append(xml_pos)
                current_text_size += text_size
                continue
            
            # Use is_header_by_properties to check if this is a header
            if _is_header_by_properties(text_stripped, props, header_rules):
                # Check numbering sequence violation relative to last header
                text_match_seq = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text_stripped)
                if text_match_seq and header_stack:
                    curr_num = int(text_match_seq.group(1))
                    curr_sub = text_match_seq.group(2)
                    
                    # Find last numbered header in stack
                    for stack_level, stack_header_id, stack_is_numbered in reversed(header_stack):
                        if stack_is_numbered:
                            # Find header element by ID
                            for elem in elements:
                                if elem.id == stack_header_id:
                                    prev_text = elem.content.strip()
                                    prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text)
                                    if prev_match:
                                        prev_num = int(prev_match.group(1))
                                        prev_sub = prev_match.group(2)
                                        
                                        # Check sequence violation
                                        is_sequence_violation = False
                                        if curr_num < prev_num:
                                            if prev_num - curr_num > 1:
                                                is_sequence_violation = True
                                            elif prev_num - curr_num == 1 and prev_sub:
                                                is_sequence_violation = True
                                        elif curr_num == prev_num and prev_sub and curr_sub:
                                            if int(curr_sub) < int(prev_sub):
                                                is_sequence_violation = True
                                        elif curr_num == 1 and prev_num > 1:
                                            is_sequence_violation = True
                                        
                                        if is_sequence_violation:
                                            # Add to text block instead of header
                                            if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
                                                flush_text_block()
                                            current_text_block.append(text_raw)
                                            current_text_positions.append(xml_pos)
                                            current_text_size += text_size
                                            continue
                                    break
                            break
                
                # Determine level
                level = _determine_header_level(text_stripped, props, None, header_stack)
                add_header_element(text_stripped, level, xml_pos, ocr_header=None)
                continue
        
        if _is_table_caption(text) or _is_image_caption(text):
            flush_text_block()
            caption_type = 'table' if _is_table_caption(text) else 'image'
            elements.append(Element(
                id=id_generator.next_id(),
                type=ElementType.CAPTION,
                content=text,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'source': 'xml',
                    'position': xml_pos,
                    'caption_type': caption_type,
                }
            ))
            continue
        
        if props.get('is_list_item'):
            flush_text_block()
            elements.append(Element(
                id=id_generator.next_id(),
                type=ElementType.LIST_ITEM,
                content=text,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'source': 'xml',
                    'position': xml_pos,
                    'list_type': props.get('list_type', 'unknown'),
                }
            ))
            continue
        
        if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
            flush_text_block()
        
        current_text_block.append(text_raw)
        current_text_positions.append(xml_pos)
        current_text_size += text_size
    
    flush_text_block()
    
    for i, elem in enumerate(elements):
        if elem.type == ElementType.IMAGE:
            if i + 1 < len(elements) and elements[i + 1].type == ElementType.CAPTION and _is_image_caption(elements[i + 1].content):
                elem.parent_id = elements[i + 1].id
                elements[i + 1].metadata['image'] = {
                    'image_path': elem.metadata.get('image_path', ''),  # Keep for backward compatibility
                    'image_data': elem.metadata.get('image_data'),  # Base64 encoded image
                    'image_index': elem.metadata.get('image_index', 0),
                    'content': elem.content
                }
        elif elem.type == ElementType.TABLE:
            if i > 0 and elements[i - 1].type == ElementType.CAPTION and _is_table_caption(elements[i - 1].content):
                elem.parent_id = elements[i - 1].id
                elements[i - 1].metadata['has_table'] = True
    
    return elements
