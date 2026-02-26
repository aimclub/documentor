"""
Configuration loader utility.

Provides centralized configuration loading from YAML files or dictionaries.
Supports both internal default configs and external configs passed by users.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Utility class for loading configuration from YAML files or dictionaries.
    
    Provides centralized configuration loading to avoid code duplication.
    Supports:
    - Loading from default internal config files
    - Loading from external config files (by path)
    - Using configuration dictionaries directly
    """

    @staticmethod
    def get_default_config_path() -> Path:
        """
        Gets the path to the default internal configuration file.
        
        Returns:
            Path to config.yaml file in the package.
        """
        # This file is in documentor/config/, so config.yaml is in the same directory
        return Path(__file__).parent / "config.yaml"

    @staticmethod
    def load_config(
        config_name: str,
        config_path: Optional[Union[str, Path]] = None,
        config_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Loads configuration section from YAML file or dictionary.
        
        Priority:
        1. config_dict (if provided) - highest priority
        2. config_path (if provided) - load from external file
        3. Default internal config file - fallback
        
        Args:
            config_name: Name of the configuration section (e.g., "pdf_parser", "docx_parser").
            config_path: Optional path to external config file. If None, uses default internal config.
            config_dict: Optional dictionary with full config. If provided, extracts section by config_name.
        
        Returns:
            Dictionary with configuration values. Empty dict if file not found or section missing.
        """
        # Priority 1: Use provided dictionary
        if config_dict is not None:
            if not isinstance(config_dict, dict):
                logger.warning(f"config_dict must be a dictionary, got {type(config_dict)}, using default values")
                return ConfigLoader._load_from_default_file(config_name)
            
            section = config_dict.get(config_name, {})
            if section:
                logger.debug(f"Loaded config section '{config_name}' from provided dictionary")
            return section if isinstance(section, dict) else {}
        
        # Priority 2: Load from external file
        if config_path is not None:
            return ConfigLoader._load_from_file(config_path, config_name)
        
        # Priority 3: Load from default internal file
        return ConfigLoader._load_from_default_file(config_name)
    
    @staticmethod
    def _load_from_file(config_path: Union[str, Path], config_name: str) -> Dict[str, Any]:
        """
        Loads configuration section from a specific YAML file.
        
        Args:
            config_path: Path to config file.
            config_name: Name of the configuration section.
        
        Returns:
            Dictionary with configuration values.
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}, using default values")
            return ConfigLoader._load_from_default_file(config_name)
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                if config is None:
                    logger.warning(f"Configuration file {config_path} is empty, using default values")
                    return ConfigLoader._load_from_default_file(config_name)
                
                section = config.get(config_name, {})
                if section:
                    logger.debug(f"Loaded config section '{config_name}' from {config_path}")
                return section if isinstance(section, dict) else {}
        except Exception as e:
            logger.error(f"Error loading configuration from {config_path}: {e}, using default values")
            return ConfigLoader._load_from_default_file(config_name)
    
    @staticmethod
    def _load_from_default_file(config_name: str) -> Dict[str, Any]:
        """
        Loads configuration section from default internal config file.
        
        Args:
            config_name: Name of the configuration section.
        
        Returns:
            Dictionary with configuration values. Empty dict if file not found or section missing.
        """
        config_path = ConfigLoader.get_default_config_path()
        
        if not config_path.exists():
            logger.warning(f"Default configuration file not found: {config_path}, using empty config")
            return {}
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                if config is None:
                    return {}
                return config.get(config_name, {})
        except Exception as e:
            logger.error(f"Error loading default configuration from {config_path}: {e}")
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
