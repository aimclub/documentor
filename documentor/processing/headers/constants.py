"""
Constants for header level detection.

Contains dictionaries and lists of special headers that should be treated
as specific header levels across all parsers.
"""

# Special headers that should be treated as HEADER_1 (first level)
# These are common document section titles that are always top-level
SPECIAL_HEADER_1 = {
    # English headers
    "REFERENCES",
    "BIBLIOGRAPHY",
    "LITERATURE",
    "LITERATURE LIST",
    "A LIST OF LITERATURE",
    "ABSTRACT",
    "INTRODUCTION",
    "CONCLUSION",
    "CONCLUSIONS",
    "ACKNOWLEDGEMENT",
    "ACKNOWLEDGMENTS",
    "CONTENTS",
    "TABLE OF CONTENTS",
    # Russian headers
    "СПИСОК ЛИТЕРАТУРЫ",
    "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ",
    "ЛИТЕРАТУРА",
    "ВВЕДЕНИЕ",
    "СОДЕРЖАНИЕ",
    "СПИСОК ИСПОЛНИТЕЛЕЙ",
    "ОГЛАВЛЕНИЕ",
    "АННОТАЦИЯ",
    "РЕФЕРАТ",
    "ЗАКЛЮЧЕНИЕ",
    "ПРИЛОЖЕНИЯ",
    "ПРИЛОЖЕНИЕ",
    # English equivalents for appendices
    "APPENDICES",
    "APPENDIX",
}

# Headers for appendices (subsections under "ПРИЛОЖЕНИЯ" / "APPENDICES")
# These should be HEADER_2 when under appendix section
APPENDIX_HEADER_PATTERN = r'^(ПРИЛОЖЕНИЕ|APPENDIX)\s+[A-ZА-ЯЁ0-9]\.?'
