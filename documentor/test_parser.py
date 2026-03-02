"""
Universal test script for running documentor parsers.

Supports:
- DOCX files (DocxParser)
- Regular PDF files (PdfParser)
- Scanned PDF files (PdfParser with OCR)

Processes documents and saves results, including bbox visualization.
"""

import json
import sys
import time
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

from langchain_core.documents import Document
from tqdm import tqdm
from PIL import Image, ImageDraw, ImageFont
import base64
from io import BytesIO
import fitz
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# Add project root to sys.path if needed
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import directly from modules
from documentor.domain.models import ParsedDocument, ElementType
from documentor.processing.parsers.docx.docx_parser import DocxParser
from documentor.processing.parsers.pdf.pdf_parser import PdfParser
from documentor.processing.parsers.docx.converter import convert_docx_to_pdf


class DocumentType(Enum):
    """Document type for processing."""
    DOCX = "docx"
    PDF_REGULAR = "pdf_regular"
    PDF_SCANNED = "pdf_scanned"


def _base64_to_image(base64_str: str) -> Optional[Image.Image]:
    """Converts base64 string to PIL Image."""
    try:
        if base64_str.startswith("data:image"):
            base64_str = base64_str.split(",")[1]
        img_data = base64.b64decode(base64_str)
        return Image.open(BytesIO(img_data))
    except Exception as e:
        logger.error(f"Error decoding base64 image: {e}")
        return None


def _get_element_color(element_type: str) -> str:
    """Returns color for element type."""
    color_map = {
        "TEXT": "green",
        "IMAGE": "magenta",
        "CAPTION": "orange",
        "HEADER_1": "cyan",
        "HEADER_2": "cyan",
        "HEADER_3": "cyan",
        "HEADER_4": "cyan",
        "HEADER_5": "cyan",
        "HEADER_6": "cyan",
        "TITLE": "red",
        "TABLE": "pink",
        "FORMULA": "gray",
        "LIST_ITEM": "blue",
        "PAGE_HEADER": "green",
        "PAGE_FOOTER": "purple",
    }
    return color_map.get(element_type, "red")


def _draw_bbox_on_image(image: Image.Image, bbox: List[float], label: str = "", color: str = "red") -> Image.Image:
    """
    Draws bbox on image.

    Note: image is already cropped to bbox, so we draw the frame along the edges.
    """
    img_copy = image.copy()
    draw = ImageDraw.Draw(img_copy)
    
    width, height = img_copy.size
    
    # Draw frame along image edges (image is already cropped)
    draw.rectangle([0, 0, width - 1, height - 1], outline=color, width=3)
    
    # Add label if present
    if label:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 16)
            except:
                font = ImageFont.load_default()
        
        # Background for text
        text_bbox = draw.textbbox((5, 5), label, font=font)
        # Expand bbox for background
        text_bbox = (text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 2, text_bbox[3] + 2)
        draw.rectangle(text_bbox, fill=color)
        draw.text((5, 5), label, fill="white", font=font)
    
    return img_copy


def _draw_bbox_on_full_page(image: Image.Image, bbox: List[float], label: str = "", color: str = "red") -> Image.Image:
    """Draws bbox on full page."""
    img_copy = image.copy()
    draw = ImageDraw.Draw(img_copy)
    
    if len(bbox) >= 4:
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        
        # Draw rectangle
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        
        # Add label if present
        if label:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", 12)
                except:
                    font = ImageFont.load_default()
            
            # Background for text
            text_bbox = draw.textbbox((x1, y1 - 15), label, font=font)
            text_bbox = (text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 2, text_bbox[3] + 2)
            draw.rectangle(text_bbox, fill=color)
            draw.text((x1, y1 - 15), label, fill="white", font=font)
    
    return img_copy


def _save_full_pages_with_layout(
    source_path: Path,
    parsed_doc: ParsedDocument,
    output_dir: Path,
    render_scale: float = 2.0,
    is_docx: bool = False,
) -> int:
    """
    Saves full pages with drawn bbox for all layout elements.

    Args:
        source_path: Path to source file (DOCX or PDF)
        parsed_doc: Parsed document
        output_dir: Directory for output
        render_scale: Render scale
        is_docx: If True, converts DOCX to PDF for visualization

    Returns:
        Number of saved pages
    """
    pages_dir = output_dir / "pages_with_layout"
    pages_dir.mkdir(exist_ok=True)
    
    # Group elements by page
    elements_by_page: Dict[int, List[Any]] = defaultdict(list)
    for element in parsed_doc.elements:
        page_num = element.metadata.get("page_num", 0)
        if "bbox" in element.metadata and len(element.metadata["bbox"]) >= 4:
            elements_by_page[page_num].append(element)
    
    if not elements_by_page:
        return 0
    
    # For DOCX convert to PDF
    pdf_path = source_path
    temp_pdf_path = None
    
    if is_docx:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            temp_pdf_path = Path(tmp_pdf.name)
        
        try:
            convert_docx_to_pdf(source_path, temp_pdf_path)
            if not temp_pdf_path.exists():
                return 0
            pdf_path = temp_pdf_path
        except Exception as e:
            logger.error(f"Error converting DOCX to PDF: {e}")
            return 0
    
    # Render each page and draw bbox
    pdf_document = fitz.open(str(pdf_path))
    saved_count = 0
    
    try:
        for page_num in tqdm(sorted(elements_by_page.keys()), desc="Saving pages with layout", unit="page", leave=False):
            if page_num >= len(pdf_document):
                continue
            
            try:
                # Render page
                page = pdf_document.load_page(page_num)
                mat = fitz.Matrix(render_scale, render_scale)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("ppm")
                page_image = Image.open(BytesIO(img_data)).convert("RGB")
                
                # Draw bbox for all elements on page
                for element in elements_by_page[page_num]:
                    element_type_name = element.type.name if hasattr(element.type, "name") else str(element.type)
                    bbox = element.metadata.get("bbox", [])
                    color = _get_element_color(element_type_name)
                    label = f"{element_type_name} {element.id}"
                    
                    page_image = _draw_bbox_on_full_page(page_image, bbox, label, color)
                
                # Save page
                page_file = pages_dir / f"page_{page_num + 1}_with_layout.png"
                page_image.save(page_file, "PNG")
                saved_count += 1
                
            except Exception as e:
                logger.error(f"Error saving page {page_num + 1}: {e}")
                continue
    
    finally:
        pdf_document.close()
        # Remove temporary PDF file for DOCX
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
            except:
                pass
    
    return saved_count


def process_document(
    file_path: Path,
    parser: Any,
    output_dir: Path,
    doc_type: DocumentType,
) -> Dict[str, Any]:
    """
    Processes one document (DOCX or PDF).

    Args:
        file_path: Path to file
        parser: Parser instance (DocxParser or PdfParser)
        output_dir: Directory for results
        doc_type: Document type

    Returns:
        Dict with processing results
    """
    doc_type_name = {
        DocumentType.DOCX: "DOCX",
        DocumentType.PDF_REGULAR: "PDF (regular)",
        DocumentType.PDF_SCANNED: "PDF (scanned)",
    }.get(doc_type, "Unknown")
    
    print(f"\n{'='*80}")
    print(f"Processing {doc_type_name}: {file_path.name}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        # Create LangChain Document
        document = Document(
            page_content="",
            metadata={"source": str(file_path.absolute())}
        )
        
        # Parse document
        parsed_doc: ParsedDocument = parser.parse(document)
        
        processing_time = time.time() - start_time
        
        # Create output directory
        doc_output_dir = output_dir / file_path.stem
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save metadata
        metadata_file = doc_output_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(parsed_doc.metadata, f, indent=2, ensure_ascii=False, default=str)
        
        # Save document structure
        structure_file = doc_output_dir / "structure.json"
        structure = {
            "source": parsed_doc.source,
            "format": parsed_doc.format.value if hasattr(parsed_doc.format, "value") else str(parsed_doc.format),
            "total_elements": len(parsed_doc.elements),
            "elements": []
        }
        
        for element in tqdm(parsed_doc.elements, desc="Processing elements", unit="element", leave=False):
            element_type_name = element.type.name if hasattr(element.type, "name") else str(element.type)
            
            # Clean text for preview
            cleaned_content = element.content.replace("\n", " ").replace("\r", " ").strip()
            while "  " in cleaned_content:
                cleaned_content = cleaned_content.replace("  ", " ")
            
            elem_data = {
                "id": element.id,
                "type": element_type_name,
                "content_preview": cleaned_content[:200] + "..." if len(cleaned_content) > 200 else cleaned_content,
                "content_length": len(element.content),
                "parent_id": element.parent_id,
                "metadata_keys": list(element.metadata.keys()),
            }
            
            # Add important metadata
            if "bbox" in element.metadata:
                elem_data["bbox"] = element.metadata["bbox"]
            if "page_num" in element.metadata:
                elem_data["page_num"] = element.metadata["page_num"]
            if "category" in element.metadata:
                elem_data["category"] = element.metadata["category"]
            if "xml_position" in element.metadata:
                elem_data["xml_position"] = element.metadata["xml_position"]
            
            # For headers
            if element_type_name.startswith("HEADER") or element_type_name == "TITLE":
                if "level" in element.metadata:
                    elem_data["level"] = element.metadata["level"]
                if "from_toc" in element.metadata:
                    elem_data["from_toc"] = element.metadata["from_toc"]
                if "from_ocr" in element.metadata:
                    elem_data["from_ocr"] = element.metadata["from_ocr"]
            
            # For tables
            if element_type_name == "TABLE":
                has_html = bool(element.content and element.content.strip())
                has_image = "image_data" in element.metadata
                elem_data["has_html"] = has_html
                elem_data["has_image"] = has_image
                if has_html:
                    elem_data["html_length"] = len(element.content)
                if "parsing_method" in element.metadata:
                    elem_data["parsing_method"] = element.metadata["parsing_method"]
                if "merged_tables" in element.metadata:
                    elem_data["merged_tables"] = element.metadata["merged_tables"]
                if "table_count" in element.metadata:
                    elem_data["table_count"] = element.metadata["table_count"]
            
            # For images
            if element_type_name == "IMAGE":
                has_image = "image_data" in element.metadata
                
                # Check related CAPTION
                if not has_image and element.parent_id:
                    caption_element = next(
                        (e for e in parsed_doc.elements if e.id == element.parent_id and e.type.name == "CAPTION"),
                        None
                    )
                    if caption_element and "image_data" in caption_element.metadata:
                        has_image = True
                        elem_data["image_data"] = caption_element.metadata["image_data"]
                
                elem_data["has_image"] = has_image
                if has_image and "image_data" not in elem_data:
                    elem_data["image_data"] = element.metadata["image_data"]
                if "caption" in element.metadata:
                    elem_data["caption"] = element.metadata["caption"]
            
            # For CAPTION
            if element_type_name == "CAPTION":
                has_image = "image_data" in element.metadata
                elem_data["has_image"] = has_image
                if has_image:
                    image_data_value = element.metadata["image_data"]
                    if image_data_value:
                        elem_data["image_data"] = image_data_value
                        elem_data["image_data_size"] = len(image_data_value) if isinstance(image_data_value, str) else 0
            
            structure["elements"].append(elem_data)
        
        with open(structure_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False, default=str)
        
        # Save full document text
        full_text_file = doc_output_dir / "full_text.txt"
        with open(full_text_file, "w", encoding="utf-8") as f:
            for element in parsed_doc.elements:
                if element.content:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"ID: {element.id}\n")
                    f.write(f"Type: {element.type.name if hasattr(element.type, 'name') else element.type}\n")
                    f.write(f"Parent: {element.parent_id}\n")
                    f.write(f"{'='*80}\n")
                    f.write(element.content)
                    f.write("\n")
        
        # Save tables
        tables = parsed_doc.get_tables()
        if tables:
            tables_dir = doc_output_dir / "tables"
            tables_dir.mkdir(exist_ok=True)
            
            for i, table in enumerate(tqdm(tables, desc="Saving tables", unit="table", leave=False), start=1):
                # For DOCX use markdown, for PDF use JSON
                if doc_type == DocumentType.DOCX:
                    table_file = tables_dir / f"table_{i}.md"
                    with open(table_file, "w", encoding="utf-8") as f:
                        f.write(f"# Table {i}\n\n")
                        f.write(f"ID: {table.id}\n")
                        f.write(f"Page: {table.metadata.get('page_num', 'N/A')}\n")
                        f.write(f"BBox: {table.metadata.get('bbox', [])}\n\n")
                        f.write("## HTML Table\n\n")
                        f.write(table.content if table.content else "(empty)")
                        f.write("\n\n")
                else:
                    table_file = tables_dir / f"table_{i}.json"
                    with open(table_file, "w", encoding="utf-8") as f:
                        table_data = {
                            "id": table.id,
                            "page": table.metadata.get("page_num", "N/A"),
                            "bbox": table.metadata.get("bbox", []),
                            "html": table.content if table.content else "",
                            "html_length": len(table.content) if table.content else 0,
                        }
                        
                        json.dump(table_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Save images
        # Images are stored only in base64 format in metadata, no local file saving
        
        # Save full pages with layout
        render_scale = 2.0
        saved_pages = _save_full_pages_with_layout(
            file_path,
            parsed_doc,
            doc_output_dir,
            render_scale=render_scale,
            is_docx=(doc_type == DocumentType.DOCX),
        )
        
        # Statistics
        processing_method = {
            DocumentType.DOCX: "DOCX (Dots OCR + XML + TOC parsing)",
            DocumentType.PDF_REGULAR: "PDF (OCR layout + PyMuPDF text)",
            DocumentType.PDF_SCANNED: "PDF (OCR full extraction)",
        }.get(doc_type, "Unknown")
        
        stats = {
            "processing_time_seconds": processing_time,
            "total_elements": len(parsed_doc.elements),
            "headers": len([e for e in parsed_doc.elements if e.type.name.startswith("HEADER")]),
            "text_blocks": len([e for e in parsed_doc.elements if e.type.name == "TEXT"]),
            "tables": len(tables),
            "images": len([e for e in parsed_doc.elements if e.type.name == "IMAGE"]),
            "captions": len([e for e in parsed_doc.elements if e.type.name == "CAPTION"]),
            "saved_pages_with_layout": saved_pages,
            "processing_method": processing_method,
        }
        
        stats_file = doc_output_dir / "stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        print(f"Successfully processed in {processing_time:.2f} sec")
        print(f"  Processing method: {stats['processing_method']}")
        print(f"  Elements: {stats['total_elements']}")
        print(f"  Headers: {stats['headers']}")
        print(f"  Text blocks: {stats['text_blocks']}")
        print(f"  Tables: {stats['tables']}")
        print(f"  Images: {stats['images']}")
        print(f"  Results saved to: {doc_output_dir}")
        
        return {
            "success": True,
            "processing_time": processing_time,
            "stats": stats,
            "output_dir": str(doc_output_dir),
        }
    
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Error processing {file_path.name}: {e}"
        print(f"Error: {error_msg}")
        import traceback
        traceback.print_exc()
        
        return {
            "success": False,
            "processing_time": processing_time,
            "error": str(e),
        }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test documentor parsers")
    parser.add_argument(
        "--type",
        type=str,
        choices=["docx", "pdf", "pdf_scanned"],
        default="docx",
        help="Document type to process (docx, pdf, pdf_scanned)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Path to file to process"
    )
    parser.add_argument(
        "--folder",
        type=str,
        help="Path to folder with files to process"
    )
    
    args = parser.parse_args()
    
    # Determine document type
    project_root = Path(__file__).resolve().parents[1]
    
    if args.type == "docx":
        doc_type = DocumentType.DOCX
        parser_class = DocxParser
        default_folder = Path("E:/easy/documentor/documentor_langchain/experiments/pdf_text_extraction/test_folder")
        default_file = None
        file_ext = ".docx"
    elif args.type == "pdf_scanned":
        doc_type = DocumentType.PDF_SCANNED
        parser_class = PdfParser
        default_folder = project_root / "experiments" / "metrics" / "test_files_for_metrics"
        default_file = None
        file_ext = ".pdf"
    else:  # pdf
        doc_type = DocumentType.PDF_REGULAR
        parser_class = PdfParser
        default_folder = project_root / "experiments" / "metrics" / "test_files_for_metrics"
        default_file = None
        file_ext = ".pdf"
    
    # Determine files to process
    files_to_process = []
    
    if args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            # If relative path, try relative to project_root
            file_path = project_root / file_path
        if file_path.exists():
            files_to_process = [file_path]
        else:
            print(f"File not found: {file_path}")
            return
    elif args.folder:
        folder_path = Path(args.folder)
        if not folder_path.is_absolute():
            # If relative path, try relative to project_root
            folder_path = project_root / folder_path
        if folder_path.exists():
            files_to_process = list(folder_path.glob(f"*{file_ext}"))
        else:
            print(f"Folder not found: {folder_path}")
            return
    else:
        # Use defaults
        if default_file and default_file.exists():
            files_to_process = [default_file]
        elif default_folder and default_folder.exists():
            # For metrics use specific files if specified
            if "test_files_for_metrics" in str(default_folder):
                specific_files = [
                    "2508.19267v1.pdf",
                    "2412.19495v2.pdf",
                    "journal-10-67-5-676-697.pdf",
                    "journal-10-67-5-721-729.pdf"
                ]
                files_to_process = []
                for filename in specific_files:
                    file_path = default_folder / filename
                    if file_path.exists():
                        files_to_process.append(file_path)
                    else:
                        print(f"Warning: file not found: {file_path}")
                
                if not files_to_process:
                    # If specific files not found, use all PDFs in folder
                    files_to_process = list(default_folder.glob(f"*{file_ext}"))
            else:
                files_to_process = list(default_folder.glob(f"*{file_ext}"))
        else:
            print(f"No files to process. Use --file or --folder")
            return
    
    if not files_to_process:
        print(f"No files found")
        return
    
    print(f"Found {len(files_to_process)} file(s)")
    for file in files_to_process:
        print(f"  - {file.name}")
    
    # Paths relative to project root
    output_dir = project_root / "experiments" / "pdf_text_extraction" / "results" / args.type
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nOutput directory: {output_dir}")
    
    # Create parser
    print(f"\nInitializing {parser_class.__name__}...")
    doc_parser = parser_class()
    print(f"{parser_class.__name__} initialized")
    
    # Process files
    results = []
    for i, file_path in enumerate(files_to_process, 1):
        print(f"\n{'='*80}")
        print(f"Processing file {i}/{len(files_to_process)}: {file_path.name}")
        print(f"{'='*80}")
        
        result = process_document(file_path, doc_parser, output_dir, doc_type)
        result["file_name"] = file_path.name
        results.append(result)
    
    # Print summary
    print(f"\n{'='*80}")
    print("PROCESSING SUMMARY")
    print(f"{'='*80}")
    
    successful = [r for r in results if r.get("success", False)]
    failed = [r for r in results if not r.get("success", False)]
    
    print(f"\nSuccessfully processed: {len(successful)}/{len(results)}")
    if successful:
        print("\nSuccessful files:")
        for result in successful:
            print(f"  - {result['file_name']}")
            print(f"    Processing time: {result.get('processing_time', 0):.2f} sec")
            if "stats" in result:
                stats = result["stats"]
                print(f"    Elements: {stats.get('total_elements', 0)}")
                print(f"    Headers: {stats.get('headers', 0)}")
                print(f"    Text blocks: {stats.get('text_blocks', 0)}")
                print(f"    Tables: {stats.get('tables', 0)}")
                print(f"    Images: {stats.get('images', 0)}")
            print(f"    Results: {result.get('output_dir', 'N/A')}")
            print()
    
    if failed:
        print(f"\nFailed: {len(failed)}/{len(results)}")
        print("\nFiles with errors:")
        for result in failed:
            print(f"  - {result['file_name']}")
            print(f"    Error: {result.get('error', 'Unknown error')}")
            print()
    
    # Overall statistics
    if successful:
        total_time = sum(r.get("processing_time", 0) for r in results)
        total_elements = sum(r.get("stats", {}).get("total_elements", 0) for r in successful)
        total_headers = sum(r.get("stats", {}).get("headers", 0) for r in successful)
        total_tables = sum(r.get("stats", {}).get("tables", 0) for r in successful)
        total_images = sum(r.get("stats", {}).get("images", 0) for r in successful)
        
        print(f"\nOverall statistics:")
        print(f"  Total files: {len(results)}")
        print(f"  Successful: {len(successful)}")
        print(f"  Failed: {len(failed)}")
        print(f"  Total processing time: {total_time:.2f} sec")
        print(f"  Total elements: {total_elements}")
        print(f"  Total headers: {total_headers}")
        print(f"  Total tables: {total_tables}")
        print(f"  Total images: {total_images}")


if __name__ == "__main__":
    main()
