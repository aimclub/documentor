"""
Converting DOCX to PDF for subsequent OCR processing.
"""

import subprocess
from pathlib import Path
from typing import Optional

try:
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False

try:
    from docx2pdf import convert as docx2pdf_convert
    HAS_DOCX2PDF = True
except ImportError:
    HAS_DOCX2PDF = False

HAS_LIBREOFFICE = False
LIBREOFFICE_CMD: Optional[str] = None

try:
    for cmd in ['soffice', 'libreoffice', '/Applications/LibreOffice.app/Contents/MacOS/soffice']:
        try:
            result = subprocess.run([cmd, '--version'], capture_output=True, timeout=5)
            if result.returncode == 0:
                HAS_LIBREOFFICE = True
                LIBREOFFICE_CMD = cmd
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
except Exception:
    pass


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    """
    Converts DOCX to PDF.
    
    Method priority:
    1. Word COM (Windows) - best image support
    2. LibreOffice - cross-platform
    3. docx2pdf - fallback
    
    Args:
        docx_path: Path to DOCX file
        pdf_path: Path to save PDF
        
    Raises:
        RuntimeError: If conversion failed
    """
    if HAS_WIN32COM:
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False
            
            try:
                doc = word.Documents.Open(str(docx_path.absolute()))
                try:
                    doc.ExportAsFixedFormat(
                        OutputFileName=str(pdf_path),
                        ExportFormat=17,
                        OpenAfterExport=False,
                        OptimizeFor=0,
                        BitmapMissingFonts=True,
                        UseISO19005_1=False,
                        IncludeDocProps=False,
                        KeepIRM=False,
                        CreateBookmarks=0,
                        DocStructureTags=False,
                    )
                    if pdf_path.exists():
                        return
                finally:
                    doc.Close(SaveChanges=False)
            finally:
                word.Quit()
        except Exception:
            pass
    
    if HAS_LIBREOFFICE:
        try:
            cmd = LIBREOFFICE_CMD or 'soffice'
            result = subprocess.run(
                [
                    cmd,
                    '--headless',
                    '--nodefault',
                    '--nolockcheck',
                    '--invisible',
                    '--convert-to', 'pdf',
                    '--outdir', str(pdf_path.parent),
                    str(docx_path.absolute())
                ],
                check=True,
                timeout=120,
                capture_output=True,
                text=True
            )
            
            expected_pdf = pdf_path.parent / f"{docx_path.stem}.pdf"
            if expected_pdf.exists() and expected_pdf != pdf_path:
                expected_pdf.rename(pdf_path)
            
            if pdf_path.exists():
                return
        except Exception:
            pass
    
    if HAS_DOCX2PDF:
        try:
            docx2pdf_convert(str(docx_path), str(pdf_path))
            if pdf_path.exists():
                return
        except Exception:
            pass
    
    raise RuntimeError(
        "Failed to convert DOCX to PDF. Install one of:\n"
        "- Microsoft Word (Windows) + pywin32\n"
        "- LibreOffice (cross-platform)\n"
        "- docx2pdf (pip install docx2pdf)"
    )
