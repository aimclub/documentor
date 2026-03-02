import json
from pathlib import Path
from collections import defaultdict

def analyze_dedoc_structure(json_file: Path):
    """Анализирует структуру JSON файла dedoc и собирает все типы paragraph_type."""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    types_found = set()
    sample_texts = defaultdict(list)
    
    def traverse(node, depth=0):
        if not isinstance(node, dict):
            return
        
        metadata = node.get('metadata', {})
        paragraph_type = metadata.get('paragraph_type', 'unknown')
        text = node.get('text', '').strip()
        
        types_found.add(paragraph_type)
        if text and len(sample_texts[paragraph_type]) < 3:
            sample_texts[paragraph_type].append(text[:100])
        
        subparagraphs = node.get('subparagraphs', [])
        for subpara in subparagraphs:
            traverse(subpara, depth + 1)
    
    structure = data.get('content', {}).get('structure')
    if structure:
        traverse(structure)
    
    print(f"\n=== Analysis of {json_file.name} ===")
    print(f"\nAll paragraph types found: {sorted(types_found)}")
    print(f"\nSample texts for each type:")
    for ptype in sorted(types_found):
        print(f"\n  {ptype}:")
        for sample in sample_texts[ptype]:
            print(f"    - {sample}")

if __name__ == "__main__":
    # Анализируем несколько файлов
    dedoc_output_dir = Path(__file__).parent / "dedoc_output"
    
    files_to_analyze = [
        "journal-10-67-5-676-697_dedoc.json",
        "2508.19267v1_dedoc.json",
    ]
    
    for filename in files_to_analyze:
        json_file = dedoc_output_dir / filename
        if json_file.exists():
            analyze_dedoc_structure(json_file)
        else:
            print(f"File not found: {json_file}")
