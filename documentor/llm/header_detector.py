"""
Header detection using LLM.

Contains logic for:
- Detecting headers in text
- Determining header levels
- Building header hierarchy
- Validating hierarchy logic (HEADER_1 cannot be inside HEADER_2)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..domain import ElementType


class HeaderInfo:
    """Header information."""
    
    def __init__(
        self,
        text: str,
        level: int,
        position: int,
        element_type: ElementType,
    ) -> None:
        """
        Initialize header information.
        
        Args:
            text: Header text.
            level: Header level (1-6).
            position: Position in text (character or index).
            element_type: Element type (HEADER_1, HEADER_2, etc.).
        """
        self.text = text
        self.level = level
        self.position = position
        self.element_type = element_type


class HeaderDetector:
    """
    Detects headers in text using LLM.
    
    Supports:
    - Header detection in text chunks
    - Hierarchy logic validation
    - Header tree building
    - Merging headers from different chunks
    """

    def __init__(
        self,
        llm_client: Optional[any] = None,
        chunk_size: int = 3000,
        overlap_size: int = 500,
    ) -> None:
        """
        Initialize header detector.
        
        Args:
            llm_client: LLM client for requests (if None - will be created later).
            chunk_size: Chunk size for processing (~3000 characters).
            overlap_size: Overlap size between chunks (~1 paragraph).
        """
        self.llm_client = llm_client
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        # TODO: Initialize LLM client if needed

    def detect_headers(
        self,
        chunk: str,
        previous_headers: Optional[List[HeaderInfo]] = None,
    ) -> List[HeaderInfo]:
        """
        Detects headers in text chunk.
        
        Args:
            chunk: Text chunk for analysis.
            previous_headers: List of headers from previous chunks (for context).
            
        Returns:
            List of found headers.
        """
        # TODO: Implement header detection via LLM
        # - Prepare prompt with chunk text
        # - Pass previous headers for context
        # - Call LLM to determine headers and levels
        # - Parse JSON response from LLM
        # - Validate hierarchy logic
        raise NotImplementedError("detect_headers() method requires implementation")

    def validate_hierarchy(self, headers: List[HeaderInfo]) -> bool:
        """
        Validates header hierarchy logic.
        
        Rules:
        - HEADER_1 cannot be inside HEADER_2
        - Levels must be sequential (no HEADER_1 → HEADER_3)
        
        Args:
            headers: List of headers to validate.
            
        Returns:
            True if hierarchy is correct, False otherwise.
        """
        # TODO: Implement hierarchy validation
        # - Check level sequence
        # - Check that there are no level skips without reason
        # - Check nesting logic
        raise NotImplementedError("Method validate_hierarchy() requires implementation")

    def build_header_tree(self, headers: List[HeaderInfo]) -> Dict[str, any]:
        """
        Builds a header tree with hierarchy.
        
        Args:
            headers: List of headers.
            
        Returns:
            Header tree as a dictionary with fields:
            - header: header information
            - children: list of child headers
        """
        # TODO: Implement header tree building
        # - Determine parent_id for each header
        # - Build hierarchical structure
        raise NotImplementedError("Method build_header_tree() requires implementation")

    def merge_headers(
        self,
        headers_list: List[List[HeaderInfo]],
    ) -> List[HeaderInfo]:
        """
        Merges headers from different chunks.
        
        Args:
            headers_list: List of header lists from different chunks.
            
        Returns:
            Merged and sorted list of headers.
        """
        # TODO: Implement header merging
        # - Remove duplicates (same headers in overlap)
        # - Sort by position in document
        # - Validate final hierarchy
        raise NotImplementedError("Method merge_headers() requires implementation")
