"""
Unit tests for OCR output cleaner.

Tested classes: OutputCleaner, CleanedData.
"""

import json

import pytest

from documentor.ocr.cleaning.output_cleaner import CleanedData, OutputCleaner


class TestCleanedData:
    """Tests for CleanedData dataclass."""

    def test_cleaned_data_creation(self):
        """CleanedData stores all fields correctly."""
        data = CleanedData(
            case_id=1,
            original_type="list",
            original_length=5,
            cleaned_data=[],
            cleaning_operations={},
            success=True,
        )
        assert data.case_id == 1
        assert data.original_type == "list"
        assert data.original_length == 5
        assert data.cleaned_data == []
        assert data.success is True


class TestOutputCleaner:
    """Tests for OutputCleaner."""

    def test_initialization(self):
        """OutputCleaner initializes with empty cleaned_results."""
        cleaner = OutputCleaner()
        assert cleaner is not None
        assert len(cleaner.cleaned_results) == 0

    def test_clean_list_data_valid_bbox(self):
        """clean_list_data keeps items with valid 4-element bbox."""
        cleaner = OutputCleaner()
        cells = [
            {"bbox": [100, 100, 200, 200], "text": "Cell 1"},
            {"bbox": [300, 300, 400, 400], "text": "Cell 2"},
        ]
        result = cleaner.clean_list_data(cells, case_id=1)
        assert isinstance(result, CleanedData)
        assert result.case_id == 1
        assert result.original_type == "list"
        assert result.original_length == 2
        assert result.success is True
        assert len(result.cleaned_data) == 2

    def test_clean_list_data_removes_non_dict(self):
        """clean_list_data drops non-dict items."""
        cleaner = OutputCleaner()
        cells = [
            {"bbox": [100, 100, 200, 200], "text": "Valid"},
            "invalid_string",
            {"bbox": [300, 300, 400, 400], "text": "Valid2"},
        ]
        result = cleaner.clean_list_data(cells, case_id=1)
        assert result.success is True
        assert result.original_length == 3
        assert len(result.cleaned_data) == 2

    def test_clean_string_data_valid_json(self):
        """clean_string_data parses valid JSON and returns CleanedData."""
        cleaner = OutputCleaner()
        data = [
            {"bbox": [100, 100, 200, 200], "text": "Cell 1"},
            {"bbox": [300, 300, 400, 400], "text": "Cell 2"},
        ]
        json_string = json.dumps(data)
        result = cleaner.clean_string_data(json_string, case_id=2)
        assert isinstance(result, CleanedData)
        assert result.case_id == 2
        assert result.original_type == "str"
        assert result.success is True

    def test_clean_model_output_list(self):
        """clean_model_output with list returns list."""
        cleaner = OutputCleaner()
        cells = [{"bbox": [100, 100, 200, 200], "text": "A"}]
        result = cleaner.clean_model_output(cells)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["text"] == "A"

    def test_clean_model_output_string(self):
        """clean_model_output with string parses and returns list."""
        cleaner = OutputCleaner()
        data = [{"bbox": [100, 100, 200, 200], "text": "B"}]
        result = cleaner.clean_model_output(json.dumps(data))
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_cleaner_tracks_results(self):
        """cleaned_results accumulates after each clean_list_data."""
        cleaner = OutputCleaner()
        cleaner.clean_list_data([{"bbox": [0, 0, 1, 1], "text": "x"}], case_id=1)
        assert len(cleaner.cleaned_results) == 1
        assert cleaner.cleaned_results[0].case_id == 1
