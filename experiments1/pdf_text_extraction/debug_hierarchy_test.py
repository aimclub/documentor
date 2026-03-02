"""Quick debug script to test build_hierarchy_from_headers without OCR."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from experiments.pdf_text_extraction.docx_xml_parser import (
    extract_all_elements_from_docx_xml_ordered,
    extract_images_from_docx_xml,
    extract_tables_from_docx_xml
)
from experiments.pdf_text_extraction.docx_complete_pipeline import (
    extract_paragraph_properties_from_xml,
    is_table_caption,
    is_image_caption,
    is_structural_keyword,
    build_hierarchy_from_headers,
)

docx_path = Path("experiments/pdf_text_extraction/test_folder/Diplom2024.docx")

# Load XML elements
all_xml_elements = extract_all_elements_from_docx_xml_ordered(docx_path)
print(f"Total XML elements: {len(all_xml_elements)}")

# Print first 35 elements
for elem in all_xml_elements[:35]:
    pos = elem.get('xml_position', '?')
    tp = elem.get('type', '?')
    txt = elem.get('text', '')[:60].replace('\n', ' ')
    img = elem.get('has_image', False)
    print(f"  pos={pos} type={tp} has_img={img} text='{txt}'")

# Load tables and images
docx_tables = extract_tables_from_docx_xml(docx_path)
docx_images = extract_images_from_docx_xml(docx_path, all_xml_elements)

# Skip first table
docx_tables = docx_tables[1:]

print(f"\nTables: {len(docx_tables)}")
print(f"Images: {len(docx_images)}")

# Use minimal header_positions (just "Введение" at pos 0)
header_positions = [
    {'xml_position': 0, 'text': 'Введение', 'level': 1, 'found_by_rules': False},
]

# Run build_hierarchy
print("\n=== Building hierarchy ===")
elements = build_hierarchy_from_headers(
    header_positions,
    all_xml_elements,
    docx_tables,
    docx_images,
    docx_path=docx_path,
    header_rules=None,
    caption_rules=None,
    saved_images_map=None,
)

print(f"\nTotal elements: {len(elements)}")
for e in elements[:30]:
    print(f"  [{e.id}] {e.type.value}: '{e.content[:80]}...' (parent={e.parent_id})")
