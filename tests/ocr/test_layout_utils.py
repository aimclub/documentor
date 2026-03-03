"""
Unit tests for OCR layout utilities.

Tested functions:
- post_process_cells
"""

import pytest
from PIL import Image

from documentor.ocr.layout.layout_utils import post_process_cells


class TestPostProcessCells:
    """Tests for post_process_cells."""

    def test_post_process_cells_basic(self):
        """post_process_cells returns list of cells with bbox."""
        origin_image = Image.new("RGB", (1000, 1000), color="white")
        cells = [
            {"bbox": [100, 100, 200, 200], "text": "Cell 1"},
            {"bbox": [300, 300, 400, 400], "text": "Cell 2"},
        ]
        result = post_process_cells(origin_image, cells, 1000, 1000)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all("bbox" in c for c in result)

    def test_post_process_cells_empty_list_raises(self):
        """post_process_cells with empty cells list raises AssertionError."""
        origin_image = Image.new("RGB", (1000, 1000), color="white")
        with pytest.raises(AssertionError):
            post_process_cells(origin_image, [], 1000, 1000)

    def test_post_process_cells_scale_conversion(self):
        """post_process_cells converts bbox coordinates to origin scale."""
        origin_image = Image.new("RGB", (500, 500), color="white")
        cells = [{"bbox": [100, 100, 200, 200], "text": "Test"}]
        result = post_process_cells(origin_image, cells, 1000, 1000)
        assert len(result) == 1
        bbox = result[0]["bbox"]
        assert isinstance(bbox, list)
        assert len(bbox) == 4

    def test_post_process_cells_preserves_other_fields(self):
        """post_process_cells preserves text, type, confidence and other keys."""
        origin_image = Image.new("RGB", (1000, 1000), color="white")
        cells = [
            {
                "bbox": [100, 100, 200, 200],
                "text": "Cell 1",
                "type": "text",
                "confidence": 0.95,
            }
        ]
        result = post_process_cells(origin_image, cells, 1000, 1000)
        assert len(result) == 1
        assert result[0]["text"] == "Cell 1"
        assert result[0]["type"] == "text"
        assert result[0]["confidence"] == 0.95

    def test_post_process_cells_custom_params(self):
        """post_process_cells accepts custom factor, min_pixels, max_pixels."""
        origin_image = Image.new("RGB", (1000, 1000), color="white")
        cells = [{"bbox": [100, 100, 200, 200], "text": "Test"}]
        result = post_process_cells(
            origin_image, cells, 1000, 1000, factor=32, min_pixels=5000, max_pixels=10000000
        )
        assert len(result) == 1
        assert "bbox" in result[0]
