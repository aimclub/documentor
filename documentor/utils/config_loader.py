"""
Configuration loader utility.

Provides centralized configuration loading from YAML files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Utility class for loading configuration from YAML files.
    
    Provides centralized configuration loading to avoid code duplication.
    """

    @staticmethod
    def get_config_path() -> Path:
        """
        Gets the path to the main configuration file.
        
        Returns:
            Path to config.yaml file.
        """
        # Assuming this is called from documentor/processing/parsers/...
        # Go up to documentor root, then to config/
        return Path(__file__).parent.parent / "config" / "config.yaml"

    @staticmethod
    def load_config(config_name: str) -> Dict[str, Any]:
        """
        Loads configuration section from config.yaml.
        
        Args:
            config_name: Name of the configuration section (e.g., "pdf_parser", "docx_parser").
        
        Returns:
            Dictionary with configuration values. Empty dict if file not found or section missing.
        """
        config_path = ConfigLoader.get_config_path()
        
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}, using default values")
            return {}
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                if config is None:
                    return {}
                return config.get(config_name, {})
        except Exception as e:
            logger.error(f"Error loading configuration from {config_path}: {e}")
            return {}

    @staticmethod
    def get_config_value(config: Dict[str, Any], key: str, default: Any = None) -> Any:
        """
        Gets value from configuration dictionary using dot-separated key path.
        
        Args:
            config: Configuration dictionary.
            key: Dot-separated key path (e.g., "layout_detection.render_scale").
            default: Default value if key not found.
        
        Returns:
            Configuration value or default.
        """
        if not config:
            return default
        
        keys = key.split(".")
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value if value is not None else default
