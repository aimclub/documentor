"""
Tests for PDF page layout detection.

Class under test:
- PdfLayoutDetector
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.processing.parsers.pdf.ocr.layout_detector import PdfLayoutDetector


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_image():
    """Create test image."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def mock_layout_result():
    """Return mock layout detection result."""
    return [
        {
            "bbox": [100, 50, 500, 100],
            "category": "Section-header",
        },
        {
            "bbox": [100, 120, 500, 200],
            "category": "Text",
        },
    ]


# ============================================================================
# Initialization tests
# ============================================================================

class TestPdfLayoutDetectorInitialization:
    """PdfLayoutDetector initialization tests."""

    def test_initialization_with_direct_api(self):
        """Test initialization with direct API."""
        detector = PdfLayoutDetector(use_direct_api=True)
        assert detector.use_direct_api is True
        assert detector.ocr_manager is None

    def test_initialization_with_manager(self):
        """Test initialization with OCR manager."""
        mock_manager = MagicMock()
        detector = PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False)
        assert detector.use_direct_api is False
        assert detector.ocr_manager is mock_manager
        assert detector._own_manager is False

    @patch("documentor.ocr.manager.DotsOCRManager")
    def test_initialization_auto_create_manager(self, mock_manager_class):
        """Test automatic manager creation."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        
        detector = PdfLayoutDetector(use_direct_api=False)
        assert detector.use_direct_api is False
        assert detector.ocr_manager is not None
        assert detector._own_manager is True


# ============================================================================
# detect_layout with direct API tests
# ============================================================================

class TestDetectLayoutDirectAPI:
    """Tests for detect_layout with direct API."""

    @patch("documentor.processing.parsers.pdf.ocr.layout_detector.process_layout_detection")
    def test_detect_layout_success(self, mock_process, mock_image, mock_layout_result):
        """Test successful layout detection via direct API."""
        mock_process.return_value = (mock_layout_result, "raw_response", True)
        
        detector = PdfLayoutDetector(use_direct_api=True)
        result = detector.detect_layout(mock_image)
        
        assert len(result) == len(mock_layout_result)
        assert result[0]["category"] == "Section-header"
        mock_process.assert_called_once()

    @patch("documentor.processing.parsers.pdf.ocr.layout_detector.process_layout_detection")
    def test_detect_layout_failure(self, mock_process, mock_image):
        """Test layout detection error handling."""
        mock_process.return_value = (None, "error_response", False)
        
        detector = PdfLayoutDetector(use_direct_api=True)
        with pytest.raises(RuntimeError, match="Layout detection error"):
            detector.detect_layout(mock_image)

    @patch("documentor.processing.parsers.pdf.ocr.layout_detector.process_layout_detection")
    def test_detect_layout_with_origin_image(self, mock_process, mock_image, mock_layout_result):
        """Test layout detection with original image."""
        mock_process.return_value = (mock_layout_result, "raw_response", True)
        
        detector = PdfLayoutDetector(use_direct_api=True)
        origin_image = Image.new("RGB", (400, 300), color="white")
        result = detector.detect_layout(mock_image, origin_image=origin_image)
        
        assert len(result) > 0
        # Check that process_layout_detection was called with origin_image
        call_args = mock_process.call_args
        assert call_args[1]["origin_image"] is origin_image


# ============================================================================
# detect_layout with DotsOCRManager tests
# ============================================================================

class TestDetectLayoutWithManager:
    """Tests for detect_layout with DotsOCRManager."""

    @patch("documentor.ocr.manager.TaskStatus")
    def test_detect_layout_with_manager_success(self, mock_task_status, mock_image, mock_layout_result):
        """Test successful layout detection via manager."""
        from enum import Enum
        
        # Create mock TaskStatus
        class MockTaskStatus(Enum):
            COMPLETED = "completed"
            FAILED = "failed"
        
        mock_task_status.COMPLETED = MockTaskStatus.COMPLETED
        
        mock_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.status = MockTaskStatus.COMPLETED
        mock_task.result = mock_layout_result
        mock_task.error = None
        
        mock_manager.submit_task.return_value = "task_id_123"
        mock_manager.wait_for_task.return_value = mock_task
        
        detector = PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False)
        result = detector.detect_layout(mock_image)
        
        assert len(result) == len(mock_layout_result)
        mock_manager.submit_task.assert_called_once()
        mock_manager.wait_for_task.assert_called_once()

    @patch("documentor.ocr.manager.TaskStatus")
    def test_detect_layout_with_manager_failure(self, mock_task_status, mock_image):
        """Test layout detection error handling via manager."""
        from enum import Enum
        
        class MockTaskStatus(Enum):
            COMPLETED = "completed"
            FAILED = "failed"
        
        mock_task_status.COMPLETED = MockTaskStatus.COMPLETED
        
        mock_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.status = MockTaskStatus.FAILED
        mock_task.error = "Task failed"
        
        mock_manager.submit_task.return_value = "task_id_123"
        mock_manager.wait_for_task.return_value = mock_task
        
        detector = PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False)
        
        with pytest.raises(RuntimeError, match="Layout detection error"):
            detector.detect_layout(mock_image)

    @patch("documentor.ocr.manager.TaskStatus")
    def test_detect_layout_with_manager_dict_result(self, mock_task_status, mock_image):
        """Test handling result in dict format."""
        from enum import Enum
        
        class MockTaskStatus(Enum):
            COMPLETED = "completed"
            FAILED = "failed"
        
        mock_task_status.COMPLETED = MockTaskStatus.COMPLETED
        
        mock_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.status = MockTaskStatus.COMPLETED
        mock_task.result = {"elements": [{"bbox": [0, 0, 100, 50], "category": "Text"}]}
        
        mock_manager.submit_task.return_value = "task_id_123"
        mock_manager.wait_for_task.return_value = mock_task
        
        detector = PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False)
        result = detector.detect_layout(mock_image)
        
        assert len(result) == 1
        assert result[0]["category"] == "Text"

    @patch("documentor.ocr.manager.TaskStatus")
    def test_detect_layout_with_manager_single_element_result(self, mock_task_status, mock_image):
        """Test handling result with single element."""
        from enum import Enum
        
        class MockTaskStatus(Enum):
            COMPLETED = "completed"
            FAILED = "failed"
        
        mock_task_status.COMPLETED = MockTaskStatus.COMPLETED
        
        mock_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.status = MockTaskStatus.COMPLETED
        mock_task.result = {"bbox": [0, 0, 100, 50], "category": "Text"}
        
        mock_manager.submit_task.return_value = "task_id_123"
        mock_manager.wait_for_task.return_value = mock_task
        
        detector = PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False)
        result = detector.detect_layout(mock_image)
        
        assert len(result) == 1
        assert result[0]["category"] == "Text"

    @patch("documentor.ocr.manager.TaskStatus")
    def test_detect_layout_with_manager_invalid_result(self, mock_task_status, mock_image):
        """Test handling invalid result."""
        from enum import Enum
        
        class MockTaskStatus(Enum):
            COMPLETED = "completed"
            FAILED = "failed"
        
        mock_task_status.COMPLETED = MockTaskStatus.COMPLETED
        
        mock_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.status = MockTaskStatus.COMPLETED
        mock_task.result = "invalid_result"
        
        mock_manager.submit_task.return_value = "task_id_123"
        mock_manager.wait_for_task.return_value = mock_task
        
        detector = PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False)
        
        with pytest.raises(ValueError, match="Unexpected result format"):
            detector.detect_layout(mock_image)


# ============================================================================
# Context manager tests
# ============================================================================

class TestContextManager:
    """Context manager tests."""

    @patch("documentor.ocr.manager.DotsOCRManager")
    def test_context_manager_with_own_manager(self, mock_manager_class):
        """Test context manager with own manager."""
        mock_manager = MagicMock()
        mock_manager.__exit__ = MagicMock(return_value=None)
        mock_manager_class.return_value = mock_manager
        
        with PdfLayoutDetector(use_direct_api=False) as detector:
            assert detector.use_direct_api is False
        
        # Check that __exit__ was called
        mock_manager.__exit__.assert_called_once()

    def test_context_manager_with_provided_manager(self):
        """Test context manager with provided manager."""
        mock_manager = MagicMock()
        
        with PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False) as detector:
            assert detector.ocr_manager is mock_manager
        
        # Check that __exit__ was NOT called (manager not ours)
        assert not hasattr(mock_manager, "__exit__") or not mock_manager.__exit__.called
