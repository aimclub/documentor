"""
Standalone script for calculating DocuMentor metrics.

Processes documents from test_files/ through DocuMentor Pipeline and compares
results with annotations from test_files/{document}/annotations/.
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

# DocuMentor imports
try:
    from documentor import Pipeline
    from documentor.domain.models import ParsedDocument, Element, ElementType
    DOCUMENTOR_AVAILABLE = True
except ImportError:
    DOCUMENTOR_AVAILABLE = False
    print("[ERROR] DocuMentor is not installed. Install project dependencies.")
    sys.exit(1)

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

# Utilities (same functions as in other scripts)
def normalize_content(content: str) -> str:
    """Normalizes text for comparison."""
    if not content:
        return ""
    return " ".join(content.split())

def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calculates Character Error Rate."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_norm = normalize_content(reference).lower()
    hyp_norm = normalize_content(hypothesis).lower()
    
    if not ref_norm:
        return 1.0 if hyp_norm else 0.0
    
    ref_chars = list(ref_norm)
    hyp_chars = list(hyp_norm)
    
    m, n = len(ref_chars), len(hyp_chars)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_chars[i-1] == hyp_chars[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    return min(1.0, edit_distance / len(ref_chars)) if ref_chars else 0.0

def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculates Word Error Rate."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_norm = normalize_content(reference).lower()
    hyp_norm = normalize_content(hypothesis).lower()
    
    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    return min(1.0, edit_distance / len(ref_words)) if ref_words else 0.0

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

def process_document_with_documentor(
    doc_path: Path,
    annotation_path: Path,
    document_id: str
) -> DocumentMetrics:
    """Processes document through DocuMentor Pipeline and calculates metrics."""
    start_time = time.time()
    
    # Create Pipeline
    pipeline = Pipeline()
    
    # Process document
    try:
        parsed_doc = pipeline.process(str(doc_path.absolute()))
        predicted = parsed_doc.elements
    except Exception as e:
        raise Exception(f"Error processing document through DocuMentor: {e}")
    
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
    output_file = project_root / "evaluation_scripts" / "documentor_metrics.json"
    
    if not test_files_dir.exists():
        print(f"[ERROR] Folder {test_files_dir} not found")
        sys.exit(1)
    
    if not DOCUMENTOR_AVAILABLE:
        print("[ERROR] DocuMentor is not available")
        sys.exit(1)
    
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
        
        # Find documents (DOCX or PDF)
        docx_file = next(doc_dir.glob("*.docx"), None)
        pdf_file = next((f for f in doc_dir.glob("*.pdf") if "_scanned" not in f.name), None)
        
        if not docx_file and not pdf_file:
            print(f"  [SKIP] DOCX or PDF file not found")
            continue
        
        doc_file = docx_file if docx_file else pdf_file
        annotations_dir = doc_dir / "annotations"
        
        if not annotations_dir.exists():
            print(f"  [SKIP] annotations folder not found")
            continue
        
        # Find corresponding annotation
        if docx_file:
            annotation_path = annotations_dir / f"{doc_name}.docx_annotation.json"
            if not annotation_path.exists():
                annotation_path = annotations_dir / f"{doc_name}_docx_annotation.json"
        else:
            annotation_path = annotations_dir / f"{doc_name}.pdf_annotation.json"
            if not annotation_path.exists():
                annotation_path = annotations_dir / f"{doc_name}_pdf_annotation.json"
        
        if not annotation_path.exists():
            print(f"  [SKIP] Annotation not found")
            continue
        
        print(f"  Document: {doc_file.name}")
        print(f"  Annotation: {annotation_path.name}")
        
        try:
            metrics = process_document_with_documentor(doc_file, annotation_path, doc_name)
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
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
