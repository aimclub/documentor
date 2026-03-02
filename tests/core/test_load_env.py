"""
Tests for core/load_env.py.

Tested functions:
- load_env_file()
"""

import os
import sys
import tempfile
from pathlib import Path

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from documentor.core.load_env import load_env_file


class TestLoadEnvFile:
    """Tests for load_env_file function."""

    def test_load_env_file_with_valid_file(self, tmp_path: Path):
        """Test loading environment variables from a valid .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TEST_VAR=test_value\n"
            "ANOTHER_VAR=another_value\n"
            "QUOTED_VAR=\"quoted_value\"\n"
            "SINGLE_QUOTED_VAR='single_quoted_value'\n"
        )
        
        # Clear any existing values
        if "TEST_VAR" in os.environ:
            del os.environ["TEST_VAR"]
        if "ANOTHER_VAR" in os.environ:
            del os.environ["ANOTHER_VAR"]
        if "QUOTED_VAR" in os.environ:
            del os.environ["QUOTED_VAR"]
        if "SINGLE_QUOTED_VAR" in os.environ:
            del os.environ["SINGLE_QUOTED_VAR"]
        
        load_env_file(env_file)
        
        assert os.environ.get("TEST_VAR") == "test_value"
        assert os.environ.get("ANOTHER_VAR") == "another_value"
        assert os.environ.get("QUOTED_VAR") == "quoted_value"
        assert os.environ.get("SINGLE_QUOTED_VAR") == "single_quoted_value"
        
        # Cleanup
        for key in ["TEST_VAR", "ANOTHER_VAR", "QUOTED_VAR", "SINGLE_QUOTED_VAR"]:
            if key in os.environ:
                del os.environ[key]

    def test_load_env_file_skips_comments(self, tmp_path: Path):
        """Test that comments are skipped in .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\n"
            "TEST_VAR=test_value\n"
            "# Another comment\n"
            "ANOTHER_VAR=another_value\n"
        )
        
        if "TEST_VAR" in os.environ:
            del os.environ["TEST_VAR"]
        if "ANOTHER_VAR" in os.environ:
            del os.environ["ANOTHER_VAR"]
        
        load_env_file(env_file)
        
        assert os.environ.get("TEST_VAR") == "test_value"
        assert os.environ.get("ANOTHER_VAR") == "another_value"
        
        # Cleanup
        for key in ["TEST_VAR", "ANOTHER_VAR"]:
            if key in os.environ:
                del os.environ[key]

    def test_load_env_file_skips_empty_lines(self, tmp_path: Path):
        """Test that empty lines are skipped."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n"
            "TEST_VAR=test_value\n"
            "\n"
            "ANOTHER_VAR=another_value\n"
            "\n"
        )
        
        if "TEST_VAR" in os.environ:
            del os.environ["TEST_VAR"]
        if "ANOTHER_VAR" in os.environ:
            del os.environ["ANOTHER_VAR"]
        
        load_env_file(env_file)
        
        assert os.environ.get("TEST_VAR") == "test_value"
        assert os.environ.get("ANOTHER_VAR") == "another_value"
        
        # Cleanup
        for key in ["TEST_VAR", "ANOTHER_VAR"]:
            if key in os.environ:
                del os.environ[key]

    def test_load_env_file_handles_inline_comments(self, tmp_path: Path):
        """Test that inline comments are removed."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TEST_VAR=test_value # inline comment\n"
            "ANOTHER_VAR=another_value#no space comment\n"
        )
        
        if "TEST_VAR" in os.environ:
            del os.environ["TEST_VAR"]
        if "ANOTHER_VAR" in os.environ:
            del os.environ["ANOTHER_VAR"]
        
        load_env_file(env_file)
        
        assert os.environ.get("TEST_VAR") == "test_value"
        assert os.environ.get("ANOTHER_VAR") == "another_value"
        
        # Cleanup
        for key in ["TEST_VAR", "ANOTHER_VAR"]:
            if key in os.environ:
                del os.environ[key]

    def test_load_env_file_does_not_override_existing(self, tmp_path: Path):
        """Test that existing environment variables are not overridden."""
        os.environ["EXISTING_VAR"] = "existing_value"
        
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_VAR=new_value\n")
        
        load_env_file(env_file)
        
        assert os.environ.get("EXISTING_VAR") == "existing_value"
        
        # Cleanup
        if "EXISTING_VAR" in os.environ:
            del os.environ["EXISTING_VAR"]

    def test_load_env_file_with_nonexistent_file(self):
        """Test loading with nonexistent file."""
        nonexistent_file = Path("/nonexistent/path/.env")
        # Should not raise an error
        load_env_file(nonexistent_file)

    def test_load_env_file_auto_search(self, tmp_path: Path):
        """Test automatic search for .env file in current directory and parents."""
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_VAR=auto_value\n")
        
        # Change to temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            if "AUTO_VAR" in os.environ:
                del os.environ["AUTO_VAR"]
            
            load_env_file()  # Should find .env in current directory
            
            assert os.environ.get("AUTO_VAR") == "auto_value"
            
            # Cleanup
            if "AUTO_VAR" in os.environ:
                del os.environ["AUTO_VAR"]
        finally:
            os.chdir(original_cwd)

    def test_load_env_file_handles_invalid_lines(self, tmp_path: Path, capsys):
        """Test that invalid lines are handled gracefully."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "VALID_VAR=valid_value\n"
            "INVALID_LINE_NO_EQUALS\n"
            "ANOTHER_VALID_VAR=another_value\n"
        )
        
        if "VALID_VAR" in os.environ:
            del os.environ["VALID_VAR"]
        if "ANOTHER_VALID_VAR" in os.environ:
            del os.environ["ANOTHER_VALID_VAR"]
        
        load_env_file(env_file)
        
        # Valid variables should still be loaded
        assert os.environ.get("VALID_VAR") == "valid_value"
        assert os.environ.get("ANOTHER_VALID_VAR") == "another_value"
        
        # Cleanup
        for key in ["VALID_VAR", "ANOTHER_VALID_VAR"]:
            if key in os.environ:
                del os.environ[key]
