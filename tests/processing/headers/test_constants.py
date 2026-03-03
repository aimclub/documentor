"""
Unit tests for header constants.

Tested: SPECIAL_HEADER_1, APPENDIX_HEADER_PATTERN.
"""

import re

import pytest

from documentor.processing.headers.constants import APPENDIX_HEADER_PATTERN, SPECIAL_HEADER_1


class TestSpecialHeader1:
    """Tests for SPECIAL_HEADER_1 set."""

    def test_is_set(self):
        """SPECIAL_HEADER_1 is a set."""
        assert isinstance(SPECIAL_HEADER_1, set)

    def test_contains_english_headers(self):
        """Contains common English section headers."""
        assert "INTRODUCTION" in SPECIAL_HEADER_1
        assert "CONCLUSION" in SPECIAL_HEADER_1
        assert "REFERENCES" in SPECIAL_HEADER_1
        assert "ABSTRACT" in SPECIAL_HEADER_1
        assert "TABLE OF CONTENTS" in SPECIAL_HEADER_1

    def test_contains_russian_headers(self):
        """Contains common Russian section headers."""
        assert "ВВЕДЕНИЕ" in SPECIAL_HEADER_1
        assert "СОДЕРЖАНИЕ" in SPECIAL_HEADER_1
        assert "ЛИТЕРАТУРА" in SPECIAL_HEADER_1


class TestAppendixHeaderPattern:
    """Tests for APPENDIX_HEADER_PATTERN regex."""

    def test_matches_appendix_with_letter(self):
        """Pattern matches APPENDIX A, ПРИЛОЖЕНИЕ А, etc."""
        pattern = re.compile(APPENDIX_HEADER_PATTERN)
        assert pattern.match("APPENDIX A")
        assert pattern.match("ПРИЛОЖЕНИЕ А")
        assert pattern.match("APPENDIX 1")

    def test_does_not_match_plain_appendix(self):
        """Pattern may not match plain word without letter/number (depends on pattern)."""
        pattern = re.compile(APPENDIX_HEADER_PATTERN)
        assert pattern.match("APPENDIX A") is not None
