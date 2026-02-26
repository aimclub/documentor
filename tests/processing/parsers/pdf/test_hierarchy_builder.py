"""
Tests for PdfHierarchyBuilder.

Tests:
- PdfHierarchyBuilder.build_hierarchy_from_section_headers
- PdfHierarchyBuilder.analyze_header_levels_from_elements
- PdfHierarchyBuilder.create_elements_from_hierarchy
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

from documentor.domain import ElementType
from documentor.processing.parsers.pdf.hierarchy_builder import PdfHierarchyBuilder


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a temporary PDF file for tests."""
    if not FITZ_AVAILABLE:
        pytest.skip("PyMuPDF (fitz) not installed")
    
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "1 Introduction")
    page.insert_text((50, 100), "This is introduction text.")
    page.insert_text((50, 150), "1.1 Subsection")
    page.insert_text((50, 200), "This is subsection text.")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


@pytest.fixture
def mock_id_generator():
    """Create a mock ID generator."""
    generator = MagicMock()
    counter = 0
    def next_id():
        nonlocal counter
        counter += 1
        return f"0000000{counter}"
    generator.next_id = next_id
    return generator


@pytest.fixture
def hierarchy_builder(mock_id_generator):
    """Create PdfHierarchyBuilder instance."""
    config = {
        "layout_detection": {
            "render_scale": 2.0,
        },
        "header_analysis": {
            "use_font_size": True,
            "use_position": True,
        },
    }
    return PdfHierarchyBuilder(config=config, id_generator=mock_id_generator)


class TestPdfHierarchyBuilder:
    """Tests for PdfHierarchyBuilder."""

    def test_build_hierarchy_from_section_headers_with_headers(self, hierarchy_builder):
        """Test building hierarchy with section headers."""
        layout_elements = [
            {"category": "Section-header", "bbox": [50, 50, 200, 70], "page_num": 0, "text": "1 Introduction"},
            {"category": "Text", "bbox": [50, 100, 400, 120], "page_num": 0},
            {"category": "Section-header", "bbox": [50, 150, 200, 170], "page_num": 0, "text": "1.1 Subsection"},
            {"category": "Text", "bbox": [50, 200, 400, 220], "page_num": 0},
        ]
        
        hierarchy = hierarchy_builder.build_hierarchy_from_section_headers(layout_elements)
        
        assert len(hierarchy) == 2
        assert hierarchy[0]["header"]["text"] == "1 Introduction"
        assert len(hierarchy[0]["children"]) == 1
        assert hierarchy[1]["header"]["text"] == "1.1 Subsection"
        assert len(hierarchy[1]["children"]) == 1

    def test_build_hierarchy_from_section_headers_no_headers(self, hierarchy_builder):
        """Test building hierarchy without headers."""
        layout_elements = [
            {"category": "Text", "bbox": [50, 50, 400, 70], "page_num": 0},
            {"category": "Picture", "bbox": [50, 100, 200, 200], "page_num": 0},
        ]
        
        hierarchy = hierarchy_builder.build_hierarchy_from_section_headers(layout_elements)
        
        assert len(hierarchy) == 1
        assert hierarchy[0]["header"] is None
        assert len(hierarchy[0]["children"]) == 2

    def test_analyze_header_levels_numbered_headers(self, hierarchy_builder, sample_pdf_path):
        """Test analyzing header levels for numbered headers."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        layout_elements = [
            {"category": "Section-header", "bbox": [50, 50, 200, 70], "page_num": 0},
            {"category": "Section-header", "bbox": [50, 150, 200, 170], "page_num": 0},
        ]
        
        analyzed = hierarchy_builder.analyze_header_levels_from_elements(
            layout_elements, sample_pdf_path, is_text_extractable=True
        )
        
        assert len(analyzed) == 2
        # Both should have level assigned
        assert "level" in analyzed[0]
        assert "level" in analyzed[1]

    def test_analyze_header_levels_special_headers(self, hierarchy_builder, sample_pdf_path):
        """Test analyzing header levels for special headers (REFERENCES, etc.)."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        layout_elements = [
            {"category": "Section-header", "bbox": [50, 50, 200, 70], "page_num": 0},
        ]
        
        # Mock text extraction to return "REFERENCES"
        with patch.object(hierarchy_builder, '_get_font_size', return_value=12.0):
            with patch('fitz.open') as mock_open:
                mock_doc = MagicMock()
                mock_page = MagicMock()
                mock_page.get_textbox.return_value = "REFERENCES"
                mock_page.get_text.return_value = "REFERENCES"
                mock_doc.__len__.return_value = 1
                mock_doc.load_page.return_value = mock_page
                mock_open.return_value.__enter__.return_value = mock_doc
                mock_open.return_value.__exit__.return_value = None
                
                analyzed = hierarchy_builder.analyze_header_levels_from_elements(
                    layout_elements, sample_pdf_path, is_text_extractable=True
                )
                
                assert len(analyzed) == 1
                assert analyzed[0]["level"] == 1  # Special header should be level 1

    def test_create_elements_from_hierarchy(self, hierarchy_builder, sample_pdf_path):
        """Test creating elements from hierarchy."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        hierarchy = [
            {
                "header": {
                    "category": "Section-header",
                    "text": "1 Introduction",
                    "level": 1,
                    "element_type": ElementType.HEADER_1,
                    "bbox": [50, 50, 200, 70],
                    "page_num": 0,
                },
                "children": [
                    {"category": "Text", "bbox": [50, 100, 400, 120], "page_num": 0, "text": "Text content"},
                ],
            },
        ]
        
        merged_text_elements = [
            {"category": "Text", "bbox": [50, 100, 400, 120], "page_num": 0, "text": "Text content"},
        ]
        
        layout_elements = [
            {"category": "Section-header", "bbox": [50, 50, 200, 70], "page_num": 0, "text": "1 Introduction"},
            {"category": "Text", "bbox": [50, 100, 400, 120], "page_num": 0, "text": "Text content"},
        ]
        
        elements = hierarchy_builder.create_elements_from_hierarchy(
            hierarchy, merged_text_elements, layout_elements, sample_pdf_path
        )
        
        assert len(elements) == 2  # Header + Text
        assert elements[0].type == ElementType.HEADER_1
        assert elements[1].type == ElementType.TEXT
