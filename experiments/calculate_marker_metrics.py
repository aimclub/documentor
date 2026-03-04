"""
Standalone script for calculating Marker metrics (PDF only).

Processes all PDFs from test_files/ (regular and scanned) through Marker,
compares with annotations. Output format aligned with DocuMentor: per-document
entries with document_type, _summary, _summary_pdf, _summary_pdf_scanned.
Uses existing MD files if present, else runs Marker on PDF.
See experiments/README.md for Marker installation.
"""

import json
import sys
import time
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

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

# Utilities (same functions as in calculate_dedoc_metrics.py)
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

def parse_markdown_to_elements(md_content: str, document_id: str) -> List[Element]:
    """Parses Markdown file into a list of elements."""
    elements = []
    element_counter = 0
    lines = md_content.split('\n')
    current_parent_id = None
    parent_stack = []
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        
        if not line.strip():
            i += 1
            continue
        
        elem_type = ElementType.TEXT
        content = line
        level = None
        
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            content = header_match.group(2).strip()
            
            if level == 1:
                elem_type = ElementType.HEADER_1
            elif level == 2:
                elem_type = ElementType.HEADER_2
            elif level == 3:
                elem_type = ElementType.HEADER_3
            elif level == 4:
                elem_type = ElementType.HEADER_4
            elif level == 5:
                elem_type = ElementType.HEADER_5
            elif level == 6:
                elem_type = ElementType.HEADER_6
            
            while parent_stack and parent_stack[-1][1] >= level:
                parent_stack.pop()
            
            if parent_stack:
                current_parent_id = parent_stack[-1][0]
            else:
                current_parent_id = None
            
            elem_id = f"md_elem_{element_counter:04d}"
            element_counter += 1
            parent_stack.append((elem_id, level))
        elif line.strip().startswith('|') and '|' in line:
            table_lines = [line]
            i += 1
            if i < len(lines) and '|' in lines[i] and re.match(r'^\|[\s\-:]+\|', lines[i]):
                i += 1
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].rstrip())
                i += 1
            i -= 1
            content = '\n'.join(table_lines)
            elem_type = ElementType.TABLE
            elem_id = f"md_elem_{element_counter:04d}"
            element_counter += 1
        elif re.match(r'^[\-\*\+]\s+', line):
            elem_type = ElementType.LIST_ITEM
            content = re.sub(r'^[\-\*\+]\s+', '', line)
            elem_id = f"md_elem_{element_counter:04d}"
            element_counter += 1
        else:
            text_lines = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i].rstrip()
                if (not next_line.strip() or
                    re.match(r'^(#{1,6})\s+', next_line) or
                    next_line.strip().startswith('|') or
                    re.match(r'^\$\$', next_line) or
                    re.match(r'^!\[.*?\]\(.*?\)', next_line) or
                    re.match(r'^[\-\*\+]\s+', next_line)):
                    i -= 1
                    break
                text_lines.append(next_line)
                i += 1
            content = '\n'.join(text_lines)
            elem_type = ElementType.TEXT
            elem_id = f"md_elem_{element_counter:04d}"
            element_counter += 1
        
        if content.strip():
            element = Element(
                id=elem_id,
                type=elem_type,
                content=content,
                parent_id=current_parent_id,
                metadata={'source': 'marker_md', 'document_id': document_id}
            )
            elements.append(element)
        
        i += 1
    
    return elements

def process_pdf_with_marker(pdf_path: Path) -> str:
    """Processes PDF through Marker and returns MD content."""
    # Try to import Marker
    try:
        import sys
        project_root = Path(__file__).parent.parent
        marker_path = project_root / "experiments" / "marker"
        venv_marker = project_root / "experiments" / "venv_marker"
        
        if marker_path.exists() and str(marker_path) not in sys.path:
            sys.path.insert(0, str(marker_path))
        if venv_marker.exists():
            venv_site_packages = venv_marker / "Lib" / "site-packages"
            if venv_site_packages.exists() and str(venv_site_packages) not in sys.path:
                sys.path.insert(0, str(venv_site_packages))
        
        from marker.models import create_model_dict
        from marker.converters.pdf import PdfConverter
        from marker.output import text_from_rendered
        
        model_dict = create_model_dict()
        converter = PdfConverter(artifact_dict=model_dict)
        
        rendered = converter(str(pdf_path.absolute()))
        text, _, _ = text_from_rendered(rendered)
        return text
    except ImportError as e:
        raise ImportError(f"Marker is not installed or unavailable: {e}")
    except Exception as e:
        raise Exception(f"Error processing PDF through Marker: {e}")

def process_markdown_file(
    md_content: str,
    annotation_path: Path,
    document_id: str
) -> DocumentMetrics:
    """Processes MD content and calculates metrics."""
    start_time = time.time()
    
    predicted = parse_markdown_to_elements(md_content, document_id)
    
    with open(annotation_path, 'r', encoding='utf-8') as f:
        gt_data = json.load(f)
    gt_elements = gt_data.get('elements', [])
    
    matches = match_elements_simple(predicted, gt_elements)
    
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
    
    # Structure metrics: TEDS are distance (lower is better)
    ordering_accuracy = calculate_ordering_accuracy_simple(predicted, gt_elements, matches)
    hierarchy_accuracy = calculate_hierarchy_accuracy_simple(predicted, gt_elements, matches)
    hierarchy_teds = 1.0 - hierarchy_accuracy  # distance, lower is better
    document_teds = (hierarchy_teds + (1.0 - ordering_accuracy)) / 2.0  # distance, lower is better
    
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
    """Main function. Processes all PDFs (regular + scanned), same task layout as DocuMentor."""
    project_root = Path(__file__).parent.parent
    test_files_dir = project_root / "test_files"
    output_file = project_root / "experiments" / "marker_metrics.json"

    if not test_files_dir.exists():
        print(f"[ERROR] Folder {test_files_dir} not found")
        sys.exit(1)

    document_dirs = [d for d in test_files_dir.iterdir() if d.is_dir()]
    if not document_dirs:
        print(f"[ERROR] No document folders found in {test_files_dir}")
        sys.exit(1)

    tasks = []
    for doc_dir in sorted(document_dirs):
        annotations_dir = doc_dir / "annotations"
        if not annotations_dir.exists():
            continue
        for pdf_path in sorted(doc_dir.glob("*.pdf")):
            stem = pdf_path.stem
            if "_scanned" in pdf_path.name:
                ann = annotations_dir / f"{stem}_annotation.json"
                key = stem
                doc_type = "pdf_scanned"
            else:
                ann = annotations_dir / f"{stem}.pdf_annotation.json"
                if not ann.exists():
                    ann = annotations_dir / f"{stem}_pdf_annotation.json"
                key = f"{stem}_pdf"
                doc_type = "pdf"
            if ann.exists():
                tasks.append((pdf_path, ann, key, doc_type))

    if not tasks:
        print("[ERROR] No PDF+annotation pairs found in test_files/")
        sys.exit(1)

    print(f"Found {len(tasks)} PDF(s) to process")
    print("=" * 80)
    results = {}
    all_metrics = []
    metrics_by_type = []

    for i, (pdf_path, annotation_path, result_key, doc_type) in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {result_key}")
        print(f"  PDF: {pdf_path.name}")
        print(f"  Annotation: {annotation_path.name}")
        md_file = pdf_path.parent / f"{pdf_path.stem}.md"
        try:
            if md_file.exists():
                print(f"  Using existing MD: {md_file.name}")
                with open(md_file, "r", encoding="utf-8") as f:
                    md_content = f.read()
            else:
                print(f"  Running Marker on PDF...")
                md_content = process_pdf_with_marker(pdf_path)
            metrics = process_markdown_file(md_content, annotation_path, result_key)
            all_metrics.append(metrics)
            metrics_by_type.append((doc_type, metrics))
            results[result_key] = {
                "document_id": metrics.document_id,
                "document_type": doc_type,
                "cer": metrics.cer,
                "wer": metrics.wer,
                "ordering_accuracy": metrics.ordering_accuracy,
                "hierarchy_accuracy": metrics.hierarchy_accuracy,
                "document_teds": metrics.document_teds,
                "hierarchy_teds": metrics.hierarchy_teds,
                "total_elements_gt": metrics.total_elements_gt,
                "total_elements_pred": metrics.total_elements_pred,
                "matched_elements": metrics.matched_elements,
                "processing_time": metrics.processing_time,
            }
            print(f"  [OK] CER: {metrics.cer:.4f}")
            print(f"  [OK] WER: {metrics.wer:.4f}")
            print(f"  [OK] Ordering accuracy: {metrics.ordering_accuracy:.4f}")
            print(f"  [OK] Hierarchy accuracy: {metrics.hierarchy_accuracy:.4f}")
            print(f"  [OK] Document TEDS: {metrics.document_teds:.4f}")
            print(f"  [OK] Hierarchy TEDS: {metrics.hierarchy_teds:.4f}")
            print(f"  [OK] Time: {metrics.processing_time:.2f} sec")
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()

    if all_metrics:
        summary = {
            "total_files": len(all_metrics),
            "avg_cer": sum(m.cer for m in all_metrics) / len(all_metrics),
            "avg_wer": sum(m.wer for m in all_metrics) / len(all_metrics),
            "avg_ordering_accuracy": sum(m.ordering_accuracy for m in all_metrics) / len(all_metrics),
            "avg_hierarchy_accuracy": sum(m.hierarchy_accuracy for m in all_metrics) / len(all_metrics),
            "avg_document_teds": sum(m.document_teds for m in all_metrics) / len(all_metrics),
            "avg_hierarchy_teds": sum(m.hierarchy_teds for m in all_metrics) / len(all_metrics),
        }
        results["_summary"] = summary
        by_type = {}
        for dt, m in metrics_by_type:
            by_type.setdefault(dt, []).append(m)
        for dt, group in sorted(by_type.items()):
            n = len(group)
            results[f"_summary_{dt}"] = {
                "total_files": n,
                "avg_cer": sum(m.cer for m in group) / n,
                "avg_wer": sum(m.wer for m in group) / n,
                "avg_ordering_accuracy": sum(m.ordering_accuracy for m in group) / n,
                "avg_hierarchy_accuracy": sum(m.hierarchy_accuracy for m in group) / n,
                "avg_document_teds": sum(m.document_teds for m in group) / n,
                "avg_hierarchy_teds": sum(m.hierarchy_teds for m in group) / n,
            }
        print("\n" + "=" * 80)
        print("SUMMARY (all)")
        print("=" * 80)
        print(f"Average CER: {summary['avg_cer']:.4f}")
        print(f"Average WER: {summary['avg_wer']:.4f}")
        print(f"Average Ordering accuracy: {summary['avg_ordering_accuracy']:.4f}")
        print(f"Average Hierarchy accuracy: {summary['avg_hierarchy_accuracy']:.4f}")
        print(f"Average Document TEDS: {summary['avg_document_teds']:.4f}")
        print(f"Average Hierarchy TEDS: {summary['avg_hierarchy_teds']:.4f}")
        for dt in sorted(by_type.keys()):
            s = results[f"_summary_{dt}"]
            print("\n" + "-" * 40)
            print(f"SUMMARY ({dt}, n={s['total_files']})")
            print("-" * 40)
            print(f"  CER: {s['avg_cer']:.4f}")
            print(f"  WER: {s['avg_wer']:.4f}")
            print(f"  Ordering accuracy: {s['avg_ordering_accuracy']:.4f}")
            print(f"  Hierarchy accuracy: {s['avg_hierarchy_accuracy']:.4f}")
            print(f"  Document TEDS: {s['avg_document_teds']:.4f}")
            print(f"  Hierarchy TEDS: {s['avg_hierarchy_teds']:.4f}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
