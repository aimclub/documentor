"""
Standalone script for calculating Dedoc metrics.

Processes PDF files from test_files/ through Dedoc API and compares
results with annotations from test_files/{document}/annotations/.
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Try to import requests for Docker API
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[ERROR] requests is not installed. Install: pip install requests")
    sys.exit(1)

# Element classes
class ElementType(str, Enum):
    TITLE = "title"
    HEADER_1 = "header_1"
    HEADER_2 = "header_2"
    HEADER_3 = "header_3"
    HEADER_4 = "header_4"
    HEADER_5 = "header_5"
    HEADER_6 = "header_6"
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    FORMULA = "formula"
    LIST_ITEM = "list_item"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    LINK = "link"
    CODE_BLOCK = "code_block"

@dataclass
class Element:
    id: str
    type: ElementType
    content: str
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DocumentMetrics:
    document_id: str
    cer: float
    wer: float
    ordering_accuracy: float
    hierarchy_accuracy: float
    document_teds: float
    hierarchy_teds: float
    total_elements_gt: int
    total_elements_pred: int
    matched_elements: int
    processing_time: float

# Utilities
def normalize_content(content: str) -> str:
    """Normalizes text for comparison."""
    if not content:
        return ""
    return " ".join(content.split())

def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calculates Character Error Rate."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_norm = normalize_content(reference)
    hyp_norm = normalize_content(hypothesis)
    
    def levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    distance = levenshtein_distance(ref_norm, hyp_norm)
    return distance / len(ref_norm) if ref_norm else 1.0

def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculates Word Error Rate."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_words = normalize_content(reference).split()
    hyp_words = normalize_content(hypothesis).split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    
    def word_levenshtein_distance(words1: List[str], words2: List[str]) -> int:
        if len(words1) < len(words2):
            return word_levenshtein_distance(words2, words1)
        if len(words2) == 0:
            return len(words1)
        
        previous_row = range(len(words2) + 1)
        for i, w1 in enumerate(words1):
            current_row = [i + 1]
            for j, w2 in enumerate(words2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (w1 != w2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    distance = word_levenshtein_distance(ref_words, hyp_words)
    return distance / len(ref_words) if ref_words else 1.0

def match_elements_simple(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    threshold: float = 0.5
) -> Dict[str, str]:
    """Simple element matching by text."""
    matches = {}
    used_gt = set()
    
    for pred_elem in predicted:
        best_match = None
        best_score = 0.0
        
        for gt_elem in ground_truth:
            gt_id = gt_elem['id']
            if gt_id in used_gt:
                continue
            
            type_match = (pred_elem.type.value.lower() == gt_elem['type'].lower())
            if not type_match:
                continue
            
            pred_content = normalize_content(pred_elem.content)
            gt_content = normalize_content(gt_elem['content'])
            
            if not pred_content and not gt_content:
                score = 1.0
            elif not pred_content or not gt_content:
                score = 0.0
            else:
                common_words = set(pred_content.lower().split()) & set(gt_content.lower().split())
                total_words = set(pred_content.lower().split()) | set(gt_content.lower().split())
                score = len(common_words) / len(total_words) if total_words else 0.0
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = gt_id
        
        if best_match:
            matches[pred_elem.id] = best_match
            used_gt.add(best_match)
    
    return matches

def calculate_ordering_accuracy_simple(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> float:
    """Calculates element ordering accuracy."""
    if not matches:
        return 0.0
    
    pred_indices = []
    gt_indices = []
    
    for i, pred_elem in enumerate(predicted):
        if pred_elem.id in matches:
            pred_indices.append(i)
            gt_id = matches[pred_elem.id]
            gt_idx = next((j for j, gt_elem in enumerate(ground_truth) if gt_elem['id'] == gt_id), None)
            if gt_idx is not None:
                gt_indices.append(gt_idx)
    
    if len(pred_indices) != len(gt_indices) or len(pred_indices) < 2:
        return 1.0 if len(pred_indices) <= 1 else 0.0
    
    correct_order = 0
    total_pairs = 0
    
    for i in range(len(pred_indices) - 1):
        for j in range(i + 1, len(pred_indices)):
            total_pairs += 1
            if (pred_indices[i] < pred_indices[j]) == (gt_indices[i] < gt_indices[j]):
                correct_order += 1
    
    return correct_order / total_pairs if total_pairs > 0 else 1.0

def calculate_hierarchy_accuracy_simple(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> float:
    """Calculates element hierarchy accuracy."""
    if not matches:
        return 0.0
    
    correct_hierarchy = 0
    total_matched = 0
    
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    for pred_id, gt_id in matches.items():
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        total_matched += 1
        
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        if pred_parent is None and gt_parent is None:
            correct_hierarchy += 1
        elif pred_parent and gt_parent:
            pred_parent_gt = matches.get(pred_parent)
            if pred_parent_gt == gt_parent:
                correct_hierarchy += 1
    
    return correct_hierarchy / total_matched if total_matched > 0 else 0.0

def get_element_type_from_paragraph_type(paragraph_type: str, text: str) -> ElementType:
    """Determines element type based on paragraph_type and text."""
    if not paragraph_type or paragraph_type == "root":
        text_lower = text.lower().strip()
        if any(keyword in text_lower for keyword in ['abstract', 'introduction', 'conclusion']):
            return ElementType.HEADER_1
        return ElementType.TEXT
    
    paragraph_type_lower = paragraph_type.lower()
    
    if 'header' in paragraph_type_lower or 'title' in paragraph_type_lower:
        if '1' in paragraph_type_lower or 'title' in paragraph_type_lower:
            return ElementType.HEADER_1
        elif '2' in paragraph_type_lower:
            return ElementType.HEADER_2
        elif '3' in paragraph_type_lower:
            return ElementType.HEADER_3
        elif '4' in paragraph_type_lower:
            return ElementType.HEADER_4
        elif '5' in paragraph_type_lower:
            return ElementType.HEADER_5
        elif '6' in paragraph_type_lower:
            return ElementType.HEADER_6
        return ElementType.HEADER_1
    
    if 'list' in paragraph_type_lower:
        return ElementType.LIST_ITEM
    
    if 'table' in paragraph_type_lower:
        return ElementType.TABLE
    
    return ElementType.TEXT

def parse_dedoc_structure(dedoc_result: Dict[str, Any], document_id: str) -> List[Element]:
    """Parses dedoc result into a list of elements."""
    elements = []
    element_counter = 0
    id_mapping = {}
    
    if not isinstance(dedoc_result, dict):
        return elements
    
    content = dedoc_result.get('content', {})
    if not isinstance(content, dict):
        return elements
    
    structure = content.get('structure')
    if not structure or not isinstance(structure, dict):
        return elements
    
    def process_node(node: Dict[str, Any], parent_id: Optional[str] = None) -> None:
        nonlocal element_counter
        
        if not isinstance(node, dict):
            return
        
        node_id = node.get('node_id')
        text = node.get('text', '')
        metadata = node.get('metadata', {})
        paragraph_type = metadata.get('paragraph_type', 'raw_text')
        page_id = metadata.get('page_id', 0)
        
        if paragraph_type == 'root' and not text.strip():
            subparagraphs = node.get('subparagraphs', [])
            for subpara in subparagraphs:
                process_node(subpara, parent_id)
            return
        
        elem_type = get_element_type_from_paragraph_type(paragraph_type, text)
        
        if text.strip():
            elem_id = f"dedoc_elem_{element_counter:04d}"
            element_counter += 1
            
            if node_id:
                id_mapping[node_id] = elem_id
            
            our_parent_id = None
            if parent_id and parent_id in id_mapping:
                our_parent_id = id_mapping[parent_id]
            
            element = Element(
                id=elem_id,
                type=elem_type,
                content=text.strip(),
                parent_id=our_parent_id,
                metadata={
                    'source': 'dedoc',
                    'document_id': document_id,
                    'dedoc_node_id': node_id,
                    'dedoc_paragraph_type': paragraph_type,
                    'page_id': page_id,
                }
            )
            
            elements.append(element)
        
        subparagraphs = node.get('subparagraphs', [])
        current_parent_id = node_id if node_id else parent_id
        for subpara in subparagraphs:
            process_node(subpara, current_parent_id)
    
    process_node(structure)
    return elements

def process_pdf_with_dedoc(
    pdf_path: Path,
    annotation_path: Path,
    dedoc_api_url: str = "http://localhost:1231/upload"
) -> DocumentMetrics:
    """Processes PDF through Dedoc API and calculates metrics."""
    start_time = time.time()
    document_id = pdf_path.stem
    
    # Send PDF to Dedoc API
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.name, f, 'application/pdf')}
            response = requests.post(dedoc_api_url, files=files, timeout=300)
            response.raise_for_status()
            dedoc_result = response.json()
    except Exception as e:
        print(f"  [ERROR] Error processing through Dedoc API: {e}")
        raise
    
    # Parse Dedoc result
    predicted = parse_dedoc_structure(dedoc_result, document_id)
    
    # Load ground truth
    with open(annotation_path, 'r', encoding='utf-8') as f:
        gt_data = json.load(f)
    gt_elements = gt_data.get('elements', [])
    
    # Match elements
    matches = match_elements_simple(predicted, gt_elements)
    
    # Calculate CER and WER
    total_cer = 0.0
    total_wer = 0.0
    matched_pairs = 0
    
    for pred_id, gt_id in matches.items():
        pred_elem = next((e for e in predicted if e.id == pred_id), None)
        gt_elem = next((e for e in gt_elements if e['id'] == gt_id), None)
        
        if pred_elem and gt_elem:
            cer = calculate_cer(gt_elem['content'], pred_elem.content)
            wer = calculate_wer(gt_elem['content'], pred_elem.content)
            total_cer += cer
            total_wer += wer
            matched_pairs += 1
    
    avg_cer = total_cer / matched_pairs if matched_pairs > 0 else 1.0
    avg_wer = total_wer / matched_pairs if matched_pairs > 0 else 1.0
    
    # Calculate metrics
    ordering_accuracy = calculate_ordering_accuracy_simple(predicted, gt_elements, matches)
    hierarchy_accuracy = calculate_hierarchy_accuracy_simple(predicted, gt_elements, matches)
    hierarchy_teds = 1.0 - hierarchy_accuracy
    document_teds = (hierarchy_teds + (1.0 - ordering_accuracy)) / 2.0
    
    processing_time = time.time() - start_time
    
    return DocumentMetrics(
        document_id=document_id,
        cer=avg_cer,
        wer=avg_wer,
        ordering_accuracy=ordering_accuracy,
        hierarchy_accuracy=hierarchy_accuracy,
        document_teds=document_teds,
        hierarchy_teds=hierarchy_teds,
        total_elements_gt=len(gt_elements),
        total_elements_pred=len(predicted),
        matched_elements=len(matches),
        processing_time=processing_time
    )

def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    test_files_dir = project_root / "test_files"
    output_file = project_root / "evaluation_scripts" / "dedoc_metrics.json"
    
    if not test_files_dir.exists():
        print(f"[ERROR] Folder {test_files_dir} not found")
        sys.exit(1)
    
    # Check Dedoc API availability
    try:
        response = requests.get('http://localhost:1231/', timeout=2)
        print("[INFO] Dedoc Docker API is available")
    except:
        print("[ERROR] Dedoc Docker API is not available at http://localhost:1231/")
        print("Start Docker container:")
        print("  docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc")
        sys.exit(1)
    
    # Find all document folders
    document_dirs = [d for d in test_files_dir.iterdir() if d.is_dir()]
    
    if not document_dirs:
        print(f"[ERROR] No document folders found in {test_files_dir}")
        sys.exit(1)
    
    print(f"Found {len(document_dirs)} documents")
    print("=" * 80)
    
    results = {}
    all_metrics = []
    
    for i, doc_dir in enumerate(sorted(document_dirs), 1):
        doc_name = doc_dir.name
        print(f"\n[{i}/{len(document_dirs)}] Processing: {doc_name}")
        
        # Find PDF files (regular, not scanned)
        pdf_files = [f for f in doc_dir.glob("*.pdf") if "_scanned" not in f.name]
        
        if not pdf_files:
            print(f"  [SKIP] PDF file not found")
            continue
        
        pdf_file = pdf_files[0]
        annotations_dir = doc_dir / "annotations"
        
        if not annotations_dir.exists():
            print(f"  [SKIP] annotations folder not found")
            continue
        
        # Find annotation for PDF
        annotation_path = annotations_dir / f"{doc_name}.pdf_annotation.json"
        if not annotation_path.exists():
            annotation_path = annotations_dir / f"{doc_name}_pdf_annotation.json"
        
        if not annotation_path.exists():
            print(f"  [SKIP] Annotation not found")
            continue
        
        print(f"  PDF: {pdf_file.name}")
        print(f"  Annotation: {annotation_path.name}")
        
        try:
            metrics = process_pdf_with_dedoc(pdf_file, annotation_path)
            all_metrics.append(metrics)
            
            results[doc_name] = {
                'document_id': metrics.document_id,
                'cer': metrics.cer,
                'wer': metrics.wer,
                'ordering_accuracy': metrics.ordering_accuracy,
                'hierarchy_accuracy': metrics.hierarchy_accuracy,
                'document_teds': metrics.document_teds,
                'hierarchy_teds': metrics.hierarchy_teds,
                'total_elements_gt': metrics.total_elements_gt,
                'total_elements_pred': metrics.total_elements_pred,
                'matched_elements': metrics.matched_elements,
                'processing_time': metrics.processing_time
            }
            
            print(f"  [OK] CER: {metrics.cer:.4f}")
            print(f"  [OK] WER: {metrics.wer:.4f}")
            print(f"  [OK] Ordering accuracy: {metrics.ordering_accuracy:.4f}")
            print(f"  [OK] Hierarchy accuracy: {metrics.hierarchy_accuracy:.4f}")
            print(f"  [OK] Document TEDS: {metrics.document_teds:.4f}")
            print(f"  [OK] Time: {metrics.processing_time:.2f} sec")
            
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
    
    # Calculate average metrics
    if all_metrics:
        summary = {
            'total_files': len(all_metrics),
            'avg_cer': sum(m.cer for m in all_metrics) / len(all_metrics),
            'avg_wer': sum(m.wer for m in all_metrics) / len(all_metrics),
            'avg_ordering_accuracy': sum(m.ordering_accuracy for m in all_metrics) / len(all_metrics),
            'avg_hierarchy_accuracy': sum(m.hierarchy_accuracy for m in all_metrics) / len(all_metrics),
            'avg_document_teds': sum(m.document_teds for m in all_metrics) / len(all_metrics),
            'avg_hierarchy_teds': sum(m.hierarchy_teds for m in all_metrics) / len(all_metrics),
        }
        
        results['_summary'] = summary
        
        print("\n" + "=" * 80)
        print("SUMMARY METRICS")
        print("=" * 80)
        print(f"Average CER: {summary['avg_cer']:.4f}")
        print(f"Average WER: {summary['avg_wer']:.4f}")
        print(f"Average Ordering accuracy: {summary['avg_ordering_accuracy']:.4f}")
        print(f"Average Hierarchy accuracy: {summary['avg_hierarchy_accuracy']:.4f}")
        print(f"Average Document TEDS: {summary['avg_document_teds']:.4f}")
        print(f"Average Hierarchy TEDS: {summary['avg_hierarchy_teds']:.4f}")
    
    # Save results
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
