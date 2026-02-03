"""
Тесты для детектирования layout PDF страниц.

Тестируемый класс:
- PdfLayoutDetector
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Добавляем корневую директорию проекта в PYTHONPATH
_project_root = Path(__file__).parent.parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.processing.parsers.pdf.ocr.layout_detector import PdfLayoutDetector


# ============================================================================
# Фикстуры
# ============================================================================

@pytest.fixture
def mock_image():
    """Создает тестовое изображение."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def mock_layout_result():
    """Возвращает моковый результат layout detection."""
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
# Тесты инициализации
# ============================================================================

class TestPdfLayoutDetectorInitialization:
    """Тесты инициализации PdfLayoutDetector."""

    def test_initialization_with_direct_api(self):
        """Тест инициализации с прямым API."""
        detector = PdfLayoutDetector(use_direct_api=True)
        assert detector.use_direct_api is True
        assert detector.ocr_manager is None

    def test_initialization_with_manager(self):
        """Тест инициализации с OCR менеджером."""
        mock_manager = MagicMock()
        detector = PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False)
        assert detector.use_direct_api is False
        assert detector.ocr_manager is mock_manager
        assert detector._own_manager is False

    @patch("documentor.ocr.manager.DotsOCRManager")
    def test_initialization_auto_create_manager(self, mock_manager_class):
        """Тест автоматического создания менеджера."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        
        detector = PdfLayoutDetector(use_direct_api=False)
        assert detector.use_direct_api is False
        assert detector.ocr_manager is not None
        assert detector._own_manager is True


# ============================================================================
# Тесты detect_layout с прямым API
# ============================================================================

class TestDetectLayoutDirectAPI:
    """Тесты detect_layout с прямым API."""

    @patch("documentor.processing.parsers.pdf.ocr.layout_detector.process_layout_detection")
    def test_detect_layout_success(self, mock_process, mock_image, mock_layout_result):
        """Тест успешного layout detection через прямое API."""
        mock_process.return_value = (mock_layout_result, "raw_response", True)
        
        detector = PdfLayoutDetector(use_direct_api=True)
        result = detector.detect_layout(mock_image)
        
        assert len(result) == len(mock_layout_result)
        assert result[0]["category"] == "Section-header"
        mock_process.assert_called_once()

    @patch("documentor.processing.parsers.pdf.ocr.layout_detector.process_layout_detection")
    def test_detect_layout_failure(self, mock_process, mock_image):
        """Тест обработки ошибки layout detection."""
        mock_process.return_value = (None, "error_response", False)
        
        detector = PdfLayoutDetector(use_direct_api=True)
        with pytest.raises(RuntimeError, match="Ошибка layout detection"):
            detector.detect_layout(mock_image)

    @patch("documentor.processing.parsers.pdf.ocr.layout_detector.process_layout_detection")
    def test_detect_layout_with_origin_image(self, mock_process, mock_image, mock_layout_result):
        """Тест layout detection с оригинальным изображением."""
        mock_process.return_value = (mock_layout_result, "raw_response", True)
        
        detector = PdfLayoutDetector(use_direct_api=True)
        origin_image = Image.new("RGB", (400, 300), color="white")
        result = detector.detect_layout(mock_image, origin_image=origin_image)
        
        assert len(result) > 0
        # Проверяем, что process_layout_detection вызван с origin_image
        call_args = mock_process.call_args
        assert call_args[1]["origin_image"] is origin_image


# ============================================================================
# Тесты detect_layout с DotsOCRManager
# ============================================================================

class TestDetectLayoutWithManager:
    """Тесты detect_layout с DotsOCRManager."""

    @patch("documentor.ocr.manager.TaskStatus")
    def test_detect_layout_with_manager_success(self, mock_task_status, mock_image, mock_layout_result):
        """Тест успешного layout detection через менеджер."""
        from enum import Enum
        
        # Создаем моковый TaskStatus
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
        """Тест обработки ошибки layout detection через менеджер."""
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
        
        with pytest.raises(RuntimeError, match="Ошибка layout detection"):
            detector.detect_layout(mock_image)

    @patch("documentor.ocr.manager.TaskStatus")
    def test_detect_layout_with_manager_dict_result(self, mock_task_status, mock_image):
        """Тест обработки результата в формате словаря."""
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
        """Тест обработки результата с одним элементом."""
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
        """Тест обработки невалидного результата."""
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
        
        with pytest.raises(ValueError, match="Неожиданный формат результата"):
            detector.detect_layout(mock_image)


# ============================================================================
# Тесты контекстного менеджера
# ============================================================================

class TestContextManager:
    """Тесты контекстного менеджера."""

    @patch("documentor.ocr.manager.DotsOCRManager")
    def test_context_manager_with_own_manager(self, mock_manager_class):
        """Тест контекстного менеджера с собственным менеджером."""
        mock_manager = MagicMock()
        mock_manager.__exit__ = MagicMock(return_value=None)
        mock_manager_class.return_value = mock_manager
        
        with PdfLayoutDetector(use_direct_api=False) as detector:
            assert detector.use_direct_api is False
        
        # Проверяем, что __exit__ был вызван
        mock_manager.__exit__.assert_called_once()

    def test_context_manager_with_provided_manager(self):
        """Тест контекстного менеджера с предоставленным менеджером."""
        mock_manager = MagicMock()
        
        with PdfLayoutDetector(ocr_manager=mock_manager, use_direct_api=False) as detector:
            assert detector.ocr_manager is mock_manager
        
        # Проверяем, что __exit__ НЕ был вызван (менеджер не наш)
        assert not hasattr(mock_manager, "__exit__") or not mock_manager.__exit__.called
