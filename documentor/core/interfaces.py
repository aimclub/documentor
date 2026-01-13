"""Base interfaces for loaders and parsers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Set

from .document import Document


class BaseLoader(ABC):
    """
    Base class for all document loaders.
    
    Defines unified interface for loading files from various sources.
    """
    
    @abstractmethod
    def load_file(self, file_path: Path) -> Document:
        """
        Load single file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Document: Loaded document
            
        Raises:
            FileNotFoundError: If file not found
            ValueError: If file cannot be processed
        """
        pass
    
    @abstractmethod
    def load_directory(self, directory_path: Path, recursive: bool = True) -> Iterator[Document]:
        """
        Load all supported files from directory.
        
        Args:
            directory_path: Path to directory
            recursive: Recursive subdirectory traversal
            
        Yields:
            Document: Loaded documents
        """
        pass
    
    @abstractmethod
    def supported_extensions(self) -> Set[str]:
        """
        Get set of supported file extensions.
        
        Returns:
            Set[str]: Extensions in '.txt', '.pdf' format, etc.
        """
        pass


class BaseParser(ABC):
    """
    Base class for all document parsers.
    
    Defines unified interface for parsing different file types.
    """
    
    @abstractmethod
    def parse(self, file_path: Path) -> Document:
        """
        Parse file into document.
        
        Args:
            file_path: Path to file for parsing
            
        Returns:
            Document: Parsed document with fragments
            
        Raises:
            FileNotFoundError: If file not found
            ValueError: If file cannot be parsed
        """
        pass
    
    @abstractmethod
    def supported_extensions(self) -> Set[str]:
        """
        Get set of supported file extensions.
        
        Returns:
            Set[str]: Extensions in '.txt', '.pdf' format, etc.
        """
        pass
    
    def is_available(self) -> bool:
        """
        Check if parser is available for use.
        
        Returns:
            bool: True if parser is available, False otherwise
        """
        return True
    
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if parser can process given file.
        
        Args:
            file_path: Path to file
            
        Returns:
            bool: True if file can be processed
        """
        return file_path.suffix.lower() in self.supported_extensions()
