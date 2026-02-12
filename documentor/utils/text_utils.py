"""
Text utilities.

Contains functions for:
- Splitting text into chunks with overlap
- Text cleaning
- Text normalization
- Pattern searching in text
"""

from __future__ import annotations

from typing import List


def split_with_overlap(
    text: str,
    chunk_size: int = 3000,
    overlap_size: int = 500,
    separator: str = "\n\n",
) -> List[str]:
    """
    Splits text into chunks with overlap.
    
    Args:
        text: Text to split.
        chunk_size: Chunk size in characters (~3000).
        overlap_size: Overlap size in characters (~1 paragraph).
        separator: Separator for splitting (default is double newline).
        
    Returns:
        List of chunks with overlap.
    """
    # TODO: Implement chunk splitting with overlap
    # - Split text by separator (paragraphs)
    # - Collect chunks of size ~chunk_size
    # - Add overlap (overlap_size characters from previous chunk)
    # - Ensure overlap doesn't duplicate whole paragraphs
    raise NotImplementedError("split_with_overlap() function requires implementation")


def clean_text(text: str) -> str:
    """
    Cleans text from extra characters and formatting.
    
    Args:
        text: Text to clean.
        
    Returns:
        Cleaned text.
    """
    # TODO: Implement text cleaning
    # - Remove extra spaces
    # - Normalize line breaks
    # - Remove special characters (if needed)
    raise NotImplementedError("clean_text() function requires implementation")


def normalize_text(text: str) -> str:
    """
    Normalizes text (converts to unified format).
    
    Args:
        text: Text to normalize.
        
    Returns:
        Normalized text.
    """
    # TODO: Implement text normalization
    # - Convert to unified case (if needed)
    # - Normalize spaces
    # - Remove extra characters
    raise NotImplementedError("normalize_text() function requires implementation")


def find_patterns(text: str, pattern: str) -> List[str]:
    """
    Finds patterns in text using regular expressions.
    
    Args:
        text: Text to search.
        pattern: Regular expression.
        
    Returns:
        List of found matches.
    """
    # TODO: Implement pattern search
    # - Use re for search
    # - Return list of matches
    raise NotImplementedError("find_patterns() function requires implementation")
