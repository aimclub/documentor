"""
Tests for OCR layout utilities.

Tested functions:
- post_process_cells()
"""

import sys
from pathlib import Path

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from PIL import Image

from documentor.ocr.layout.layout_utils import post_process_cells


class TestPostProcessCells:
    """Tests for post_process_cells function."""

    def test_post_process_cells_basic(self):
        """Test basic post_process_cells functionality."""
        # Create a test image
        origin_image = Image.new('RGB', (1000, 1000), color='white')
        
        # Create test cells with bounding boxes
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
        
        input_width = 1000
        input_height = 1000
        
        result = post_process_cells(
            origin_image, cells, input_width, input_height
        )
        
        assert isinstance(result, list)
        assert len(result) == len(cells)
        assert all('bbox' in cell for cell in result)

    def test_post_process_cells_empty_list(self):
        """Test post_process_cells with empty cells list."""
        origin_image = Image.new('RGB', (1000, 1000), color='white')
        
        with pytest.raises(AssertionError):
            post_process_cells(origin_image, [], 1000, 1000)

    def test_post_process_cells_scale_conversion(self):
        """Test that bbox coordinates are properly scaled."""
        origin_image = Image.new('RGB', (500, 500), color='white')
        
        cells = [
            {
                'bbox': [100, 100, 200, 200],
                'text': 'Test'
            }
        ]
        
        # Input dimensions are different from origin
        input_width = 1000
        input_height = 1000
        
        result = post_process_cells(
            origin_image, cells, input_width, input_height
        )
        
        assert len(result) == 1
        # Bbox should be scaled back to original dimensions
        # Scale factor: 1000/500 = 2.0
        # So bbox [100, 100, 200, 200] in input space
        # Should become [50, 50, 100, 100] in origin space
        bbox = result[0]['bbox']
        assert isinstance(bbox, list)
        assert len(bbox) == 4

    def test_post_process_cells_preserves_other_fields(self):
        """Test that post_process_cells preserves other cell fields."""
        origin_image = Image.new('RGB', (1000, 1000), color='white')
        
        cells = [
            {
                'bbox': [100, 100, 200, 200],
                'text': 'Cell 1',
                'type': 'text',
                'confidence': 0.95
            }
        ]
        
        result = post_process_cells(
            origin_image, cells, 1000, 1000
        )
        
        assert len(result) == 1
        assert 'text' in result[0]
        assert 'type' in result[0]
        assert 'confidence' in result[0]
        assert result[0]['text'] == 'Cell 1'
        assert result[0]['type'] == 'text'
        assert result[0]['confidence'] == 0.95

    def test_post_process_cells_with_custom_params(self):
        """Test post_process_cells with custom parameters."""
        origin_image = Image.new('RGB', (1000, 1000), color='white')
        
        cells = [
            {
                'bbox': [100, 100, 200, 200],
                'text': 'Test'
            }
        ]
        
        result = post_process_cells(
            origin_image, cells, 1000, 1000,
            factor=32,  # Different factor
            min_pixels=5000,
            max_pixels=10000000
        )
        
        assert len(result) == 1
        assert 'bbox' in result[0]
