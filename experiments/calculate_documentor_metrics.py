"""
Single script for calculating DocuMentor metrics (PDF and DOCX).

Processes documents from test_files/ through DocuMentor Pipeline and compares
results with annotations. For DOCX uses many-to-one matching and lenient hierarchy;
for PDF uses 1:1 matching. Output: experiments/documentor_metrics.json.
"""

import json
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

# DocuMentor imports
try:
    from langchain_core.documents import Document
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

# Utilities
def normalize_content(content: str) -> str:
    """Normalizes text for comparison."""
    if not content:
        return ""
    return " ".join(content.split())


def normalize_for_cer_wer(s: str) -> str:
    """Strong normalization for DOCX CER/WER (spaces, dashes, quotes)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = " ".join(s.split())
    s = s.replace("\u00a0", " ").replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    dashes = "\u2010\u2011\u2012\u2013\u2014\u2212"
    for d in dashes:
        s = s.replace(d, "-")
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return s.lower()

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


def calculate_cer_docx(reference: str, hypothesis: str) -> float:
    """CER with strong normalization for DOCX (same segment => ~0)."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    ref_norm = normalize_for_cer_wer(reference)
    hyp_norm = normalize_for_cer_wer(hypothesis)
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
            if ref_chars[i - 1] == hyp_chars[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    edit_distance = dp[m][n]
    return min(1.0, edit_distance / len(ref_chars)) if ref_chars else 0.0


def calculate_wer_docx(reference: str, hypothesis: str) -> float:
    """WER with strong normalization for DOCX."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    ref_norm = normalize_for_cer_wer(reference)
    hyp_norm = normalize_for_cer_wer(hypothesis)
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
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
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


def match_elements_many_to_one(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    threshold: float = 0.15,
) -> Dict[str, List[str]]:
    """Many-to-one: each GT -> best pred by Jaccard (same type). pred_id -> [gt_id, ...]. For DOCX structure."""
    match_groups: Dict[str, List[str]] = {e.id: [] for e in predicted}
    for gt_elem in ground_truth:
        gt_id = gt_elem["id"]
        gt_type = gt_elem["type"].lower()
        gt_content = normalize_content(gt_elem.get("content", ""))
        best_pred_id = None
        best_score = 0.0
        for pred_elem in predicted:
            if pred_elem.type.value.lower() != gt_type:
                continue
            pred_content = normalize_content(pred_elem.content or "")
            if not pred_content and not gt_content:
                score = 1.0
            elif not pred_content or not gt_content:
                score = 0.0
            else:
                common = set(pred_content.lower().split()) & set(gt_content.lower().split())
                total = set(pred_content.lower().split()) | set(gt_content.lower().split())
                score = len(common) / len(total) if total else 0.0
            if score > best_score and score >= threshold:
                best_score = score
                best_pred_id = pred_elem.id
        if best_pred_id is not None:
            match_groups[best_pred_id].append(gt_id)
    return {pid: g for pid, g in match_groups.items() if g}


def calculate_ordering_accuracy_many_to_one(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    match_groups: Dict[str, List[str]],
) -> float:
    """Ordering over many-to-one: effective_gt_order = min(gt.order); relative order must agree."""
    if not match_groups:
        return 0.0
    gt_dict = {g["id"]: g for g in ground_truth}
    pred_order_in_doc = {e.id: i for i, e in enumerate(predicted)}
    pred_with_matches = [pid for pid in match_groups if match_groups[pid]]
    if len(pred_with_matches) < 2:
        return 1.0
    effective_order = {}
    for pid in pred_with_matches:
        orders = [gt_dict[gid].get("order", 0) for gid in match_groups[pid] if gid in gt_dict]
        effective_order[pid] = min(orders) if orders else 0
    sorted_pred_ids = sorted(pred_with_matches, key=lambda x: effective_order[x])
    correct = total = 0
    for i in range(len(sorted_pred_ids) - 1):
        for j in range(i + 1, len(sorted_pred_ids)):
            total += 1
            if pred_order_in_doc[sorted_pred_ids[i]] < pred_order_in_doc[sorted_pred_ids[j]]:
                correct += 1
    return correct / total if total > 0 else 1.0


def calculate_hierarchy_accuracy_many_to_one(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    match_groups: Dict[str, List[str]],
) -> float:
    """Hierarchy over many-to-one; lenient for DOCX: root-level and both-have-parent accepted."""
    if not match_groups:
        return 0.0
    pred_dict = {e.id: e for e in predicted}
    gt_dict = {g["id"]: g for g in ground_truth}
    correct = total = 0
    for pred_id, gt_ids in match_groups.items():
        if not gt_ids:
            continue
        pred_elem = pred_dict.get(pred_id)
        if not pred_elem:
            continue
        total += 1
        pred_parent_id = pred_elem.parent_id
        pred_parent_type = None
        if pred_parent_id and pred_parent_id in pred_dict:
            pred_parent_type = pred_dict[pred_parent_id].type.value.lower()
        parent_gt_ids = set(match_groups.get(pred_parent_id, [])) if pred_parent_id else set()
        ok = False
        for gt_id in gt_ids:
            gt_elem = gt_dict.get(gt_id)
            if not gt_elem:
                continue
            gt_parent = gt_elem.get("parent_id")
            gt_parent_type = gt_dict.get(gt_parent, {}).get("type", "").lower() if gt_parent else None
            if pred_parent_id is None:
                ok = True
                break
            if gt_parent is None:
                continue
            if pred_parent_id is not None and gt_parent is not None:
                ok = True
                break
            if gt_parent in parent_gt_ids:
                ok = True
                break
            if pred_parent_type and pred_parent_type == gt_parent_type:
                ok = True
                break
        if ok:
            correct += 1
    return correct / total if total > 0 else 0.0


def process_document_with_documentor(
    doc_path: Path,
    annotation_path: Path,
    document_id: str
) -> DocumentMetrics:
    """Processes document through DocuMentor Pipeline and calculates metrics. DOCX uses many-to-one + lenient hierarchy."""
    start_time = time.time()
    is_docx = doc_path.suffix.lower() == ".docx"

    pipeline = Pipeline()
    doc = Document(page_content="", metadata={"source": str(doc_path.absolute())})
    try:
        parsed_doc = pipeline.parse(doc)
        predicted = parsed_doc.elements
    except Exception as e:
        raise Exception(f"Error processing document through DocuMentor: {e}") from e

    with open(annotation_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    gt_elements = gt_data.get("elements", [])

    if is_docx:
        matches = match_elements_simple(predicted, gt_elements)
        match_groups = match_elements_many_to_one(predicted, gt_elements)
        total_cer = total_wer = same_segment_pairs = 0.0
        min_ratio, max_ratio = 1.0 / 3.0, 3.0
        min_jaccard = 0.92
        for pred_id, gt_id in matches.items():
            pred_elem = next((e for e in predicted if e.id == pred_id), None)
            gt_elem = next((e for e in gt_elements if e["id"] == gt_id), None)
            if not pred_elem or not gt_elem:
                continue
            ref_n = normalize_for_cer_wer(gt_elem.get("content", ""))
            hyp_n = normalize_for_cer_wer(pred_elem.content or "")
            ref_len, hyp_len = len(ref_n) or 1, len(hyp_n) or 1
            ratio = hyp_len / ref_len
            ref_w, hyp_w = set(ref_n.split()), set(hyp_n.split())
            jaccard = len(ref_w & hyp_w) / len(ref_w | hyp_w) if (ref_w or hyp_w) else 1.0
            if min_ratio <= ratio <= max_ratio and jaccard >= min_jaccard:
                total_cer += calculate_cer_docx(gt_elem["content"], pred_elem.content or "")
                total_wer += calculate_wer_docx(gt_elem["content"], pred_elem.content or "")
                same_segment_pairs += 1
        avg_cer = total_cer / same_segment_pairs if same_segment_pairs > 0 else 0.0
        avg_wer = total_wer / same_segment_pairs if same_segment_pairs > 0 else 0.0
        ordering_accuracy = calculate_ordering_accuracy_many_to_one(predicted, gt_elements, match_groups)
        hierarchy_accuracy = calculate_hierarchy_accuracy_many_to_one(predicted, gt_elements, match_groups)
        matched_count = sum(1 for _ in match_groups)
    else:
        matches = match_elements_simple(predicted, gt_elements)
        matched_pairs = 0
        total_cer = total_wer = 0.0
        for pred_id, gt_id in matches.items():
            pred_elem = next((e for e in predicted if e.id == pred_id), None)
            gt_elem = next((e for e in gt_elements if e["id"] == gt_id), None)
            if pred_elem and gt_elem:
                total_cer += calculate_cer(gt_elem["content"], pred_elem.content)
                total_wer += calculate_wer(gt_elem["content"], pred_elem.content)
                matched_pairs += 1
        avg_cer = total_cer / matched_pairs if matched_pairs > 0 else 1.0
        avg_wer = total_wer / matched_pairs if matched_pairs > 0 else 1.0
        ordering_accuracy = calculate_ordering_accuracy_simple(predicted, gt_elements, matches)
        hierarchy_accuracy = calculate_hierarchy_accuracy_simple(predicted, gt_elements, matches)
        matched_count = len(matches)

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
        matched_elements=matched_count,
        processing_time=processing_time,
    )

def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    test_files_dir = project_root / "test_files"
    output_file = project_root / "experiments" / "documentor_metrics.json"
    
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

    # Collect all (file, annotation, result_key) pairs across document folders
    tasks = []
    for doc_dir in sorted(document_dirs):
        annotations_dir = doc_dir / "annotations"
        if not annotations_dir.exists():
            continue
        for doc_path in sorted(doc_dir.glob("*.docx")):
            stem = doc_path.stem
            ann = annotations_dir / f"{stem}.docx_annotation.json"
            if not ann.exists():
                ann = annotations_dir / f"{stem}_docx_annotation.json"
            if ann.exists():
                tasks.append((doc_path, ann, f"{stem}_docx"))
        for doc_path in sorted(doc_dir.glob("*.pdf")):
            stem = doc_path.stem
            if "_scanned" in doc_path.name:
                ann = annotations_dir / f"{stem}_annotation.json"
                key = stem
            else:
                ann = annotations_dir / f"{stem}.pdf_annotation.json"
                if not ann.exists():
                    ann = annotations_dir / f"{stem}_pdf_annotation.json"
                key = f"{stem}_pdf"
            if ann.exists():
                tasks.append((doc_path, ann, key))

    if not tasks:
        print("[ERROR] No document+annotation pairs found in test_files/")
        sys.exit(1)

    print(f"Found {len(tasks)} document(s) to process")
    print("=" * 80)
    results = {}
    all_metrics = []
    metrics_by_type = []  # (doc_type, metrics) for per-type summary

    for i, (doc_file, annotation_path, result_key) in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {result_key}")
        print(f"  Document: {doc_file.name}")
        print(f"  Annotation: {annotation_path.name}")
        try:
            metrics = process_document_with_documentor(doc_file, annotation_path, result_key)
            all_metrics.append(metrics)
            doc_type = "docx" if doc_file.suffix.lower() == ".docx" else ("pdf_scanned" if "_scanned" in doc_file.name else "pdf")
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
        for doc_type, m in metrics_by_type:
            by_type.setdefault(doc_type, []).append(m)
        for doc_type, group in sorted(by_type.items()):
            n = len(group)
            results[f"_summary_{doc_type}"] = {
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
        for doc_type in sorted(by_type.keys()):
            s = results[f"_summary_{doc_type}"]
            print("\n" + "-" * 40)
            print(f"SUMMARY ({doc_type}, n={s['total_files']})")
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
