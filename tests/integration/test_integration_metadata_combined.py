"""
Integration tests: combined parser metadata (tables, images, links) via Pipeline.
"""

import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.domain import ElementType
from documentor.pipeline import Pipeline


# ============================================================================
# Combined tests for all metadata features
# ============================================================================

class TestAllFeaturesTogether:
    """Combined tests for tables, images, and links metadata."""

    def test_markdown_all_features(self):
        """Test all three features for Markdown."""
        doc = Document(
            page_content="""# Document Title

## Section with https://example.com

| Column1 | Column2 |
|---------|---------|
| Data1   | Data2   |

![Image](https://example.com/image.png)

Text with [link](https://google.com) and www.test.org
""",
            metadata={"source": "test.md"}
        )

        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Check tables (stored as HTML in content)
        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) > 0
        for table in tables:
            assert isinstance(table.content, str)
            assert "<table>" in table.content

        # Check images
        images = [e for e in result.elements if e.type == ElementType.IMAGE]
        for img in images:
            assert "src" in img.metadata or "href" in img.metadata

        # Check links
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        found_links = False
        for elem in text_elements:
            if "links" in elem.metadata:
                found_links = True
                assert len(elem.metadata["links"]) > 0

    def test_all_features_metadata_structure(self):
        """Test metadata structure for all features."""
        doc = Document(
            page_content="""# Test

| A | B |
|---|---|
| 1 | 2 |

Text with https://example.com
""",
            metadata={"source": "test.md"}
        )

        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Check metadata structure
        for elem in result.elements:
            assert elem.metadata is not None
            assert isinstance(elem.metadata, dict)

            # If table, content is HTML
            if elem.type == ElementType.TABLE:
                assert isinstance(elem.content, str)
                assert "<table>" in elem.content

            # If image, may have image_data (PDF/DOCX) or src (Markdown)
            if elem.type == ElementType.IMAGE:
                has_image_data = "image_data" in elem.metadata
                has_src = "src" in elem.metadata or "href" in elem.metadata
                assert has_image_data or has_src

            # If text has links, they should be in the list
            if "links" in elem.metadata:
                assert isinstance(elem.metadata["links"], list)
                for link in elem.metadata["links"]:
                    assert isinstance(link, str)
