"""
Parsing built-in DOCX styles for header detection.

Contains classes for:
- Extracting styles from DOCX paragraphs
- Mapping DOCX styles to ElementType
- Determining header levels from styles
- Building structure based on styles
"""

# TODO: Implement StyleParser class:
# - parse_styles() - parsing styles from paragraphs
# - map_style_to_element_type() - mapping style to ElementType
#   - "Heading 1" → HEADER_1
#   - "Heading 2" → HEADER_2
#   - "Title" → TITLE (TitleFragment)
#   - Regular text → TEXT
# - get_header_level() - getting header level from style
# - has_heading_styles() - checking for heading styles in document
