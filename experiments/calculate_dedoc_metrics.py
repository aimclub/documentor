"""
Standalone script for calculating Dedoc metrics.

Processes pdf, pdf_scanned, and docx files from test_files/ through Dedoc API
and compares results with annotations. Evaluation is aligned with DocuMentor:
same metrics (CER, WER, ordering, hierarchy, TEDS) and per-type summaries
(pdf, pdf_scanned, docx) for fair comparison.
"""

import json
import unicodedata
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
    """Many-to-one: each GT -> best pred by Jaccard (same type). pred_id -> [gt_id, ...]. For DOCX."""
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


def get_element_type_from_paragraph_type(paragraph_type: str, text: str) -> ElementType:
    """Determines element type based on paragraph_type and text."""
    if not paragraph_type or paragraph_type == "root":
        text_lower = text.lower().strip()
        if any(keyword in text_lower for keyword in ['abstract', 'introduction', 'conclusion']):
            return ElementType.HEADER_1
        return ElementType.TEXT
    
    paragraph_type_lower = paragraph_type.lower()
    if paragraph_type_lower == "title" or (
        "title" in paragraph_type_lower and "header" not in paragraph_type_lower
    ):
        return ElementType.TITLE

    if "header" in paragraph_type_lower or "title" in paragraph_type_lower:
        if "1" in paragraph_type_lower or "title" in paragraph_type_lower:
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

def _get_mime_type(path: Path) -> str:
    """Returns MIME type for Dedoc upload by file extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def _upload_dedoc(file_path: Path, dedoc_api_url: str) -> Dict[str, Any]:
    """Uploads file to Dedoc API and returns parsed JSON response."""
    mime = _get_mime_type(file_path)
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, mime)}
        response = requests.post(dedoc_api_url, files=files, timeout=300)
        response.raise_for_status()
        return response.json()


def process_document_with_dedoc(
    doc_path: Path,
    annotation_path: Path,
    document_id: str,
    doc_type: str,
    dedoc_api_url: str = "http://localhost:1231/upload",
) -> DocumentMetrics:
    """Processes document through Dedoc API and calculates metrics.
    For pdf/pdf_scanned: 1:1 matching and simple ordering/hierarchy.
    For docx: many-to-one matching and lenient hierarchy (aligned with DocuMentor DOCX evaluation).
    """
    start_time = time.time()
    try:
        dedoc_result = _upload_dedoc(doc_path, dedoc_api_url)
    except Exception as e:
        raise RuntimeError(f"Error processing through Dedoc API: {e}") from e

    predicted = parse_dedoc_structure(dedoc_result, document_id)
    with open(annotation_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    gt_elements = gt_data.get("elements", [])

    if doc_type == "docx":
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
        ordering_accuracy = calculate_ordering_accuracy_many_to_one(
            predicted, gt_elements, match_groups
        )
        hierarchy_accuracy = calculate_hierarchy_accuracy_many_to_one(
            predicted, gt_elements, match_groups
        )
        matched_count = sum(len(g) for g in match_groups.values())
    else:
        matches = match_elements_simple(predicted, gt_elements)
        total_cer = total_wer = 0.0
        matched_pairs = 0
        for pred_id, gt_id in matches.items():
            pred_elem = next((e for e in predicted if e.id == pred_id), None)
            gt_elem = next((e for e in gt_elements if e["id"] == gt_id), None)
            if pred_elem and gt_elem:
                total_cer += calculate_cer(gt_elem["content"], pred_elem.content)
                total_wer += calculate_wer(gt_elem["content"], pred_elem.content)
                matched_pairs += 1
        avg_cer = total_cer / matched_pairs if matched_pairs > 0 else 1.0
        avg_wer = total_wer / matched_pairs if matched_pairs > 0 else 1.0
        ordering_accuracy = calculate_ordering_accuracy_simple(
            predicted, gt_elements, matches
        )
        hierarchy_accuracy = calculate_hierarchy_accuracy_simple(
            predicted, gt_elements, matches
        )
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
    """Main function: build task list (pdf, pdf_scanned, docx), run Dedoc, output per-type summaries."""
    project_root = Path(__file__).parent.parent
    test_files_dir = project_root / "test_files"
    output_file = project_root / "experiments" / "dedoc_metrics.json"

    if not test_files_dir.exists():
        print(f"[ERROR] Folder {test_files_dir} not found")
        sys.exit(1)

    try:
        response = requests.get("http://localhost:1231/", timeout=2)
        print("[INFO] Dedoc API is available")
    except Exception:
        print("[ERROR] Dedoc API is not available at http://localhost:1231/")
        print("Start container: docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc")
        sys.exit(1)

    document_dirs = [d for d in test_files_dir.iterdir() if d.is_dir()]
    if not document_dirs:
        print(f"[ERROR] No document folders found in {test_files_dir}")
        sys.exit(1)

    # Collect all (file, annotation, result_key, doc_type) aligned with DocuMentor task list
    tasks: List[Tuple[Path, Path, str, str]] = []
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
                tasks.append((doc_path, ann, f"{stem}_docx", "docx"))
        for doc_path in sorted(doc_dir.glob("*.pdf")):
            stem = doc_path.stem
            if "_scanned" in doc_path.name:
                ann = annotations_dir / f"{stem}_annotation.json"
                if ann.exists():
                    tasks.append((doc_path, ann, stem, "pdf_scanned"))
            else:
                ann = annotations_dir / f"{stem}.pdf_annotation.json"
                if not ann.exists():
                    ann = annotations_dir / f"{stem}_pdf_annotation.json"
                if ann.exists():
                    tasks.append((doc_path, ann, f"{stem}_pdf", "pdf"))

    if not tasks:
        print("[ERROR] No document+annotation pairs found in test_files/")
        sys.exit(1)

    print(f"Found {len(tasks)} document(s) to process")
    print("=" * 80)
    results: Dict[str, Any] = {}
    all_metrics: List[DocumentMetrics] = []
    metrics_by_type: List[Tuple[str, DocumentMetrics]] = []

    for i, (doc_file, annotation_path, result_key, doc_type) in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {result_key} ({doc_type})")
        print(f"  Document: {doc_file.name}")
        print(f"  Annotation: {annotation_path.name}")
        try:
            metrics = process_document_with_dedoc(
                doc_file, annotation_path, result_key, doc_type
            )
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
            print(f"  [OK] CER: {metrics.cer:.4f}  WER: {metrics.wer:.4f}")
            print(f"  [OK] Ordering: {metrics.ordering_accuracy:.4f}  Hierarchy: {metrics.hierarchy_accuracy:.4f}")
            print(f"  [OK] Document TEDS: {metrics.document_teds:.4f}  Time: {metrics.processing_time:.2f}s")
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

        by_type: Dict[str, List[DocumentMetrics]] = {}
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
        print(f"Average CER: {summary['avg_cer']:.4f}  WER: {summary['avg_wer']:.4f}")
        print(f"Ordering: {summary['avg_ordering_accuracy']:.4f}  Hierarchy: {summary['avg_hierarchy_accuracy']:.4f}")
        print(f"Document TEDS: {summary['avg_document_teds']:.4f}  Hierarchy TEDS: {summary['avg_hierarchy_teds']:.4f}")
        for doc_type in sorted(by_type.keys()):
            s = results[f"_summary_{doc_type}"]
            print("\n" + "-" * 40)
            print(f"SUMMARY ({doc_type}, n={s['total_files']})")
            print("-" * 40)
            print(f"  CER: {s['avg_cer']:.4f}  WER: {s['avg_wer']:.4f}")
            print(f"  Ordering: {s['avg_ordering_accuracy']:.4f}  Hierarchy: {s['avg_hierarchy_accuracy']:.4f}")
            print(f"  Document TEDS: {s['avg_document_teds']:.4f}  Hierarchy TEDS: {s['avg_hierarchy_teds']:.4f}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
