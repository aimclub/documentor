#!/usr/bin/env python3
"""
Documentor Daemon

Continuously monitors folder, processes new documents and saves results.

Usage:
    python -m documentor.cli.daemon                   # Daemon mode (monitor folder)
    python -m documentor.cli.daemon --single-run      # Process all files from config
    python -m documentor.cli.daemon --file path.pdf   # Process single file
    python -m documentor.cli.daemon --dir folder      # Process directory
    python -m documentor.cli.daemon --status          # Show status
    python -m documentor.cli.daemon --config custom.json
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, Optional, List

# Windows encoding setup
if sys.platform == 'win32':
    os.system('chcp 65001 >nul')

os.environ['PYTHONUNBUFFERED'] = '1'

import warnings
warnings.filterwarnings("ignore")

# Documentor imports
from documentor.processing.processors.document_processor import DocumentProcessor
from documentor.processing.processors.config import ProcessingConfig
from documentor.storage import StructuredDocumentStorage
from documentor.processing.parsers.ocr_health_check import check_ocr_services_from_env


DEFAULT_CONFIG_PATH = str(Path(__file__).resolve().parents[1] / 'config' / 'daemon_config.json')


class DocumentDaemon:
    """Automatic document processor."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config = self._load_config(config_path)
        self.running = False
        self.processed_files: Set[str] = set()

        # Initialize components
        self.storage = StructuredDocumentStorage(Path(self.config["output_directory"]))
        self.processor = DocumentProcessor(ProcessingConfig.create_default())

        # Show parser status
        self._show_parser_status()

        # Show OCR services status
        self._show_ocr_status()

        # Load already processed files
        self._load_processed_files()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"ERROR: Configuration file not found: {config_path}", flush=True)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid configuration file: {e}", flush=True)
            sys.exit(1)

    def _load_processed_files(self) -> None:
        """Load list of already processed files."""
        try:
            for doc_id, doc_info in self.storage.index.get("documents", {}).items():
                if "original_file" in doc_info:
                    filename = doc_info["original_file"]
                    self.processed_files.add(filename)

            print(f"INFO: Loaded {len(self.processed_files)} previously processed files", flush=True)
        except Exception as e:
            print(f"WARNING: Error loading processed files list: {e}", flush=True)

    def _show_parser_status(self) -> None:
        """Show status of available parsers."""
        print("=" * 60, flush=True)
        print("DOCUMENTOR PARSER STATUS", flush=True)
        print("=" * 60, flush=True)
        
        # Get parser information
        parser_info = self.processor.get_processing_stats()
        supported_extensions = parser_info.get("supported_extensions", [])
        parsers = parser_info.get("parsers", {})
        
        print(f"Supported file extensions: {', '.join(sorted(supported_extensions))}", flush=True)
        print("", flush=True)
        
        # Show individual parser status
        parser_status = {
            '.txt': 'TXT Parser',
            '.pdf': 'PDF Parser (OCR)',
            '.jpg': 'Image Parser (OCR)',
            '.png': 'Image Parser (OCR)',
            '.jpeg': 'Image Parser (OCR)',
            '.docx': 'DOCX Parser',
            '.doc': 'DOC Parser (Word COM)'
        }
        
        for ext, name in parser_status.items():
            if ext in supported_extensions:
                parser_name = parsers.get(ext, 'Unknown')
                print(f"[OK] {name}: {parser_name}", flush=True)
            else:
                if ext == '.doc':
                    print(f"[FAIL] {name}: Word COM not available - convert DOC files manually", flush=True)
                elif ext in ['.pdf', '.jpg', '.png', '.jpeg']:
                    print(f"[FAIL] {name}: OCR services not available", flush=True)
                else:
                    print(f"[FAIL] {name}: Not available", flush=True)
        
        print("", flush=True)
        
        # Special message for DOC files
        if '.doc' not in supported_extensions:
            print("NOTE: DOC files require Microsoft Word and Windows for automatic conversion.", flush=True)
            print("      Please convert DOC files to DOCX manually before processing.", flush=True)
        
        print("=" * 60, flush=True)

    def _show_ocr_status(self) -> None:
        """Show status of OCR services."""
        print("=" * 60, flush=True)
        print("OCR SERVICES STATUS", flush=True)
        print("=" * 60, flush=True)
        
        try:
            # Check OCR services
            ocr_results = check_ocr_services_from_env()
            
            # Dots.OCR status
            dots_ocr = ocr_results.get('dots_ocr', {})
            dots_available = dots_ocr.get('available', False)
            dots_message = dots_ocr.get('message', 'Unknown')
            dots_url = dots_ocr.get('url', 'not specified')
            
            if dots_available:
                print(f"[OK] Dots.OCR: {dots_message}", flush=True)
            else:
                print(f"[FAIL] Dots.OCR: {dots_message}", flush=True)
            
            print(f"  URL: {dots_url}", flush=True)
            
            # Qwen2.5-VL status
            qwen = ocr_results.get('qwen', {})
            qwen_available = qwen.get('available', False)
            qwen_message = qwen.get('message', 'Unknown')
            qwen_url = qwen.get('url', 'not specified')
            
            if qwen_available:
                print(f"[OK] Qwen2.5-VL: {qwen_message}", flush=True)
            else:
                print(f"[FAIL] Qwen2.5-VL: {qwen_message}", flush=True)
            
            print(f"  URL: {qwen_url}", flush=True)
            
            # Overall status
            overall_available = ocr_results.get('overall_available', False)
            print("", flush=True)
            
            if overall_available:
                print("[OK] OCR services ready for work", flush=True)
            else:
                print("[WARNING] OCR services unavailable - PDF and images will not be processed", flush=True)
                print("  Check settings in .env file:", flush=True)
                print("  - DOTS_OCR_BASE_URL, DOTS_OCR_API_KEY", flush=True)
                print("  - QWEN_BASE_URL, QWEN_API_KEY", flush=True)
                print("  - Ensure services are running and accessible", flush=True)
            
        except Exception as e:
            print(f"[ERROR] OCR services check error: {e}", flush=True)
            print("  OCR functionality may be unavailable", flush=True)
        
        print("=" * 60, flush=True)

    def _is_file_supported(self, file_path: Path) -> bool:
        """Check file support."""
        extension = file_path.suffix.lower().lstrip('.')
        return (
            extension in self.config["supported_extensions"] and
            file_path.stat().st_size <= self.config["max_file_size_mb"] * 1024 * 1024
        )

    def _should_process_file(self, file_path: Path) -> bool:
        """Determine if file needs processing."""
        if not self._is_file_supported(file_path):
            return False

        if file_path.name in self.processed_files:
            print(f"SKIP: File already processed: {file_path.name}", flush=True)
            return False

        if self.config.get("enable_deduplication", True):
            duplicate_id = self.storage.check_duplicate(file_path)
            if duplicate_id:
                self.processed_files.add(file_path.name)
                print(f"SKIP: Duplicate file detected: {file_path.name} (ID: {duplicate_id})", flush=True)
                return False

        return True

    def _find_new_files(self) -> List[Path]:
        """Find new files for processing."""
        input_dir = Path(self.config["input_directory"])
        if not input_dir.exists():
            return []

        new_files = []
        pattern = "**/*" if self.config.get("watch_subdirectories", True) else "*"

        for file_path in input_dir.glob(pattern):
            if file_path.is_file():
                if self._should_process_file(file_path):
                    new_files.append(file_path)

        return new_files

    def _process_file(self, file_path: Path) -> bool:
        """Process single file."""
        try:
            print(f"FOUND: File detected: {file_path.name}", flush=True)

            start_time = datetime.now()
            print(f"PROCESSING: Processing file...", flush=True)

            document = self.processor.process_file(file_path)

            if not document:
                print(f"ERROR: Failed to process file: {file_path.name}", flush=True)
                return False

            end_time = datetime.now()

            extension = file_path.suffix.lower().lstrip('.')
            if extension == "txt":
                processing_method = "txt"
            elif extension == "pdf":
                processing_method = "pdf_ocr"
            else:
                processing_method = "image_ocr"

            document_id = self.storage.save_document(
                document=document,
                original_file_path=file_path,
                processing_method=processing_method,
                processing_start=start_time,
                processing_end=end_time,
                save_fragment_images=self.config.get("save_fragment_images", True)
            )

            fragments_count = len(document.fragments())
            print(f"SUCCESS: File processed and saved ({fragments_count} fragments)", flush=True)

            self.processed_files.add(file_path.name)
            return True

        except Exception as e:
            print(f"ERROR: File processing error: {file_path.name} - {str(e)}", flush=True)
            return False

    def run_single_pass(self, target_path: Optional[Path] = None) -> int:
        if target_path:
            return self._process_target(target_path)
        else:
            return self._process_all_files()

    def _process_target(self, target_path: Path) -> int:
        if not target_path.exists():
            print(f"ERROR: Path not found: {target_path}", flush=True)
            return 0

        if target_path.is_file():
            print(f"PROCESSING: Single file: {target_path}", flush=True)
            if self._process_file(target_path):
                print(f"SUCCESS: File processed successfully", flush=True)
                return 1
            else:
                print(f"ERROR: Failed to process file", flush=True)
                return 0

        elif target_path.is_dir():
            print(f"PROCESSING: Directory: {target_path}", flush=True)

            files_to_process = []
            pattern = "**/*" if self.config.get("watch_subdirectories", True) else "*"

            for file_path in target_path.glob(pattern):
                if file_path.is_file() and self._is_file_supported(file_path):
                    files_to_process.append(file_path)

            if not files_to_process:
                print("INFO: No supported files found for processing", flush=True)
                return 0

            print(f"INFO: Found {len(files_to_process)} files for processing", flush=True)

            processed_count = 0
            for file_path in files_to_process:
                if self._process_file(file_path):
                    processed_count += 1

            print(f"COMPLETE: Processing finished: {processed_count}/{len(files_to_process)} files", flush=True)
            return processed_count

        else:
            print(f"ERROR: Unsupported path type: {target_path}", flush=True)
            return 0

    def _process_all_files(self) -> int:
        new_files = self._find_new_files()
        processed_count = 0

        if not new_files:
            print("INFO: No new files found for processing", flush=True)
            return 0

        print(f"INFO: Found {len(new_files)} files for processing", flush=True)

        for file_path in new_files:
            if self._process_file(file_path):
                processed_count += 1

        print(f"COMPLETE: Processing finished: {processed_count}/{len(new_files)} files", flush=True)

        stats = self.storage.get_statistics()
        print(f"STATS: Total documents: {stats['total_documents']}", flush=True)

        return processed_count

    def run_daemon(self) -> None:
        print("START: Document Daemon started", flush=True)
        print("       Press Ctrl+C to stop", flush=True)

        self.running = True

        def signal_handler(signum, frame):
            print("\nSTOP: Stopping daemon...", flush=True)
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        check_interval = self.config.get("file_check_interval_seconds", 2)

        try:
            while self.running:
                new_files = self._find_new_files()

                for file_path in new_files:
                    if not self.running:
                        break
                    self._process_file(file_path)

                time.sleep(check_interval)

        except KeyboardInterrupt:
            pass
        finally:
            print("STOP: Document Daemon stopped", flush=True)

    def get_status(self) -> Dict[str, Any]:
        """Get daemon status and statistics."""
        stats = self.storage.get_statistics()
        return {
            "running": self.running,
            "processed_files_count": len(self.processed_files),
            "total_documents": stats.get("total_documents", 0),
            "total_processed": stats.get("total_processed", 0),
            "success_rate": stats.get("success_rate", 0.0),
            "config": self.config
        }


def main():
    parser = argparse.ArgumentParser(
        description="Document Processing Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  python -m documentor.cli.daemon                   # Daemon mode (monitor folder)
  python -m documentor.cli.daemon --single-run      # Process all files from config
  python -m documentor.cli.daemon --file path.pdf   # Process single file
  python -m documentor.cli.daemon --dir folder      # Process directory
  python -m documentor.cli.daemon --status          # Show status
  python -m documentor.cli.daemon --config custom.json
        """
    )

    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH,
                        help=f"Path to configuration file (default: {DEFAULT_CONFIG_PATH})")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--single-run", action="store_true",
                            help="Single-pass processing of all files from configuration")
    mode_group.add_argument("--file", type=str, metavar="PATH",
                            help="Process a single specific file")
    mode_group.add_argument("--dir", type=str, metavar="PATH",
                            help="Process all files in specified directory")
    mode_group.add_argument("--status", action="store_true",
                            help="Show current status and statistics")

    args = parser.parse_args()

    try:
        daemon = DocumentDaemon(args.config)

        if args.status:
            status = daemon.get_status()
            print(f"STATUS: {json.dumps(status, indent=2, ensure_ascii=False)}")

        elif args.file:
            target_path = Path(args.file)
            daemon.run_single_pass(target_path)

        elif args.dir:
            target_path = Path(args.dir)
            daemon.run_single_pass(target_path)

        elif args.single_run:
            daemon.run_single_pass()

        else:
            daemon.run_daemon()

    except KeyboardInterrupt:
        print("\nEXIT: User requested exit")
    except Exception as e:
        print(f"ERROR: Critical error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


