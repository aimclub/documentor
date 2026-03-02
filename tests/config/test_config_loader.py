"""
Tests for ConfigLoader utility.

Tests:
- ConfigLoader.load_config
- ConfigLoader.get_config_value
"""

import sys
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
import yaml

# Add project root to path
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.utils.config_loader import ConfigLoader


class TestConfigLoader:
    """Tests for ConfigLoader utility."""

    def test_load_config_existing_section(self, tmp_path):
        """Test loading existing configuration section."""
        config_content = {
            "pdf_parser": {
                "layout_detection": {
                    "render_scale": 2.0,
                },
            },
            "docx_parser": {
                "layout_detection": {
                    "render_scale": 1.5,
                },
            },
        }

        config_path = tmp_path / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_content, f)

        with patch("documentor.utils.config_loader.ConfigLoader.get_config_path", return_value=config_path):
            config = ConfigLoader.load_config("pdf_parser")
            assert config["layout_detection"]["render_scale"] == 2.0

    def test_load_config_missing_section(self, tmp_path):
        """Test loading missing configuration section."""
        config_content = {
            "pdf_parser": {
                "layout_detection": {
                    "render_scale": 2.0,
                },
            },
        }

        config_path = tmp_path / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_content, f)

        with patch("documentor.utils.config_loader.ConfigLoader.get_config_path", return_value=config_path):
            config = ConfigLoader.load_config("missing_section")
            assert config == {}

    def test_load_config_missing_file(self):
        """Test loading configuration when file doesn't exist."""
        with patch("documentor.utils.config_loader.ConfigLoader.get_config_path", return_value=Path("/nonexistent/config.yaml")):
            config = ConfigLoader.load_config("pdf_parser")
            assert config == {}

    def test_get_config_value_simple_key(self):
        """Test getting value with simple key."""
        config = {
            "render_scale": 2.0,
        }
        value = ConfigLoader.get_config_value(config, "render_scale", 1.0)
        assert value == 2.0

    def test_get_config_value_nested_key(self):
        """Test getting value with nested key."""
        config = {
            "layout_detection": {
                "render_scale": 2.0,
                "optimize_for_ocr": True,
            },
        }
        value = ConfigLoader.get_config_value(config, "layout_detection.render_scale", 1.0)
        assert value == 2.0

    def test_get_config_value_missing_key(self):
        """Test getting value with missing key."""
        config = {
            "layout_detection": {
                "render_scale": 2.0,
            },
        }
        value = ConfigLoader.get_config_value(config, "layout_detection.missing_key", "default")
        assert value == "default"

    def test_get_config_value_empty_config(self):
        """Test getting value with empty config."""
        config = {}
        value = ConfigLoader.get_config_value(config, "layout_detection.render_scale", 1.0)
        assert value == 1.0

    def test_get_config_value_none_config(self):
        """Test getting value with None config."""
        config = None
        value = ConfigLoader.get_config_value(config, "layout_detection.render_scale", 1.0)
        assert value == 1.0

    def test_get_config_value_deeply_nested(self):
        """Test getting value with deeply nested key."""
        config = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": 42,
                    },
                },
            },
        }
        value = ConfigLoader.get_config_value(config, "level1.level2.level3.value", 0)
        assert value == 42
