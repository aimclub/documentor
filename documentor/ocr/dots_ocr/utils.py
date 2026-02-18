"""
Utility functions for Dots OCR.

Contains helper functions specific to Dots OCR output processing,
such as markdown formatting removal.
"""

from __future__ import annotations

import re


def remove_markdown_formatting(text: str) -> str:
    """
    Remove markdown formatting from Dots OCR text output.
    
    Dots OCR returns text with markdown formatting (**bold**, *italic*, __bold__).
    This function removes that formatting while preserving list markers.
    
    Preserves single asterisks (*) used as list markers at the start of lines.
    
    Args:
        text: Text with potential markdown formatting from Dots OCR
        
    Returns:
        Text with markdown formatting removed
        
    Examples:
        >>> remove_markdown_formatting("**bold** text")
        'bold text'
        >>> remove_markdown_formatting("* List item")
        '* List item'
        >>> remove_markdown_formatting("Normal *italic* text")
        'Normal italic text'
    """
    if not text:
        return text
    
    # First, remove **text** (bold) -> text
    cleaned_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove __text__ (bold) -> text
    cleaned_text = re.sub(r'__([^_]+)__', r'\1', cleaned_text)
    
    # Remove *text* (italic) but preserve list markers (* at start of line or after newline)
    # Split by lines to handle list markers correctly
    lines = cleaned_text.split('\n')
    cleaned_lines = []
    for line in lines:
        # If line starts with "* " (list marker), preserve it and remove *text* from the rest
        if line.strip().startswith('* '):
            # Keep the "* " prefix, remove *text* from the rest
            prefix = line[:line.find('* ') + 2]  # "* " + everything before it
            rest = line[line.find('* ') + 2:]
            # Remove *text* from the rest
            rest_cleaned = re.sub(r'\*([^*]+)\*', r'\1', rest)
            cleaned_lines.append(prefix + rest_cleaned)
        else:
            # Remove all *text* (italic) from the line
            cleaned_line = re.sub(r'\*([^*]+)\*', r'\1', line)
            cleaned_lines.append(cleaned_line)
    
    cleaned_text = '\n'.join(cleaned_lines)
    
    return cleaned_text.strip()
