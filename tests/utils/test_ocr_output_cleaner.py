"""
Tests for OCR output cleaner.

Tested classes:
- OutputCleaner
- CleanedData
"""

import json
import sys
from pathlib import Path

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from documentor.utils.ocr_output_cleaner import CleanedData, OutputCleaner


class TestCleanedData:
    """Tests for CleanedData dataclass."""

    def test_cleaned_data_creation(self):
        """Test CleanedData creation."""
        data = CleanedData(
            case_id=1,
            original_type='list',
            original_length=5,
            cleaned_data=[],
            cleaning_operations={},
            success=True
        )
        
        assert data.case_id == 1
        assert data.original_type == 'list'
        assert data.original_length == 5
        assert data.cleaned_data == []
        assert data.cleaning_operations == {}
        assert data.success is True


class TestOutputCleaner:
    """Tests for OutputCleaner class."""

    def test_output_cleaner_initialization(self):
        """Test OutputCleaner initialization."""
        cleaner = OutputCleaner()
        assert cleaner is not None
        assert isinstance(cleaner.cleaned_results, list)
        assert len(cleaner.cleaned_results) == 0

    def test_clean_list_data_basic(self):
        """Test cleaning list data with valid input."""
        cleaner = OutputCleaner()
        
        cells = [
            {
                'bbox': [100, 100, 200, 200],
                'text': 'Cell 1'
            },
            {
                'bbox': [300, 300, 400, 400],
                'text': 'Cell 2'
            }
        ]
        
        result = cleaner.clean_list_data(cells, case_id=1)
        
        assert isinstance(result, CleanedData)
        assert result.case_id == 1
        assert result.original_type == 'list'
        assert result.original_length == 2
        assert result.success is True

    def test_clean_list_data_with_invalid_items(self):
        """Test cleaning list data with invalid items."""
        cleaner = OutputCleaner()
        
        cells = [
            {'bbox': [100, 100, 200, 200], 'text': 'Valid'},
            'invalid_string',  # Invalid item
            {'bbox': [300, 300, 400, 400], 'text': 'Also valid'}
        ]
        
        result = cleaner.clean_list_data(cells, case_id=1)
        
        assert result.success is True
        assert result.original_length == 3
        # Invalid items should be removed
        assert len(result.cleaned_data) <= 2

    def test_clean_string_data_basic(self):
        """Test cleaning string data with valid JSON."""
        cleaner = OutputCleaner()
        
        # Create valid JSON string
        data = [
            {'bbox': [100, 100, 200, 200], 'text': 'Cell 1'},
            {'bbox': [300, 300, 400, 400], 'text': 'Cell 2'}
        ]
        json_string = json.dumps(data)
        
        result = cleaner.clean_string_data(json_string, case_id=2)
        
        assert isinstance(result, CleanedData)
        assert result.case_id == 2
        assert result.original_type == 'str'
        assert result.success is True

    def test_clean_string_data_invalid_json(self):
        """Test cleaning string data with invalid JSON."""
        cleaner = OutputCleaner()
        
        invalid_json = "This is not valid JSON {"
        
        result = cleaner.clean_string_data(invalid_json, case_id=3)
        
        # Should handle gracefully
        assert isinstance(result, CleanedData)
        assert result.case_id == 3

    def test_clean_string_data_malformed_bbox(self):
        """Test cleaning string data with malformed bbox."""
        cleaner = OutputCleaner()
        
        # String with malformed bbox
        malformed = '[{"bbox": [100, 200], "text": "test"}]'  # bbox should have 4 elements
        
        result = cleaner.clean_string_data(malformed, case_id=4)
        
        assert isinstance(result, CleanedData)

    def test_clean_string_data_fixes_missing_delimiters(self):
        """Test that cleaner fixes missing delimiters."""
        cleaner = OutputCleaner()
        
        # String with missing delimiter between objects
        data = '[{"bbox": [100, 100, 200, 200], "text": "test"} {"bbox": [300, 300, 400, 400], "text": "test2"}]'
        
        result = cleaner.clean_string_data(data, case_id=5)
        
        assert isinstance(result, CleanedData)
        # Should attempt to fix the delimiter issue

    def test_output_cleaner_tracks_results(self):
        """Test that OutputCleaner tracks cleaning results."""
        cleaner = OutputCleaner()
        
        cells = [{'bbox': [100, 100, 200, 200], 'text': 'Test'}]
        cleaner.clean_list_data(cells, case_id=1)
        
        assert len(cleaner.cleaned_results) == 1
        assert cleaner.cleaned_results[0].case_id == 1

    def test_output_cleaner_multiple_cleanings(self):
        """Test multiple cleaning operations."""
        cleaner = OutputCleaner()
        
        # Clean list data
        cells = [{'bbox': [100, 100, 200, 200], 'text': 'Test'}]
        cleaner.clean_list_data(cells, case_id=1)
        
        # Clean string data
        json_str = json.dumps(cells)
        cleaner.clean_string_data(json_str, case_id=2)
        
        assert len(cleaner.cleaned_results) == 2
        assert cleaner.cleaned_results[0].case_id == 1
        assert cleaner.cleaned_results[1].case_id == 2
