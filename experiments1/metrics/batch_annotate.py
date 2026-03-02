"""
Пакетная разметка всех PDF файлов из test_files_for_metrics.
"""

import subprocess
import sys
from pathlib import Path

def batch_annotate():
    """Размечает все PDF файлы из test_files_for_metrics."""
    base_dir = Path(__file__).parent
    test_files_dir = base_dir / "test_files_for_metrics"
    annotations_dir = base_dir / "annotations"
    
    # Находим все PDF файлы
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"Не найдено PDF файлов в {test_files_dir}")
        return
    
    print(f"Найдено {len(pdf_files)} PDF файлов для разметки\n")
    
    for i, pdf_file in enumerate(sorted(pdf_files), 1):
        doc_id = pdf_file.stem
        annotation_file = annotations_dir / f"{doc_id}_annotation.json"
        
        print(f"[{i}/{len(pdf_files)}] Разметка: {pdf_file.name}")
        
        try:
            cmd = [
                sys.executable,
                str(base_dir / "annotate_document.py"),
                "--input", str(pdf_file),
                "--output", str(annotation_file),
                "--annotator", "auto"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(base_dir))
            
            if result.returncode == 0:
                print(f"  ✓ Успешно: {annotation_file.name}\n")
            else:
                print(f"  ✗ Ошибка: {result.stderr}\n")
                
        except Exception as e:
            print(f"  ✗ Исключение: {e}\n")
    
    print("Пакетная разметка завершена!")
    print(f"\nРазметки сохранены в: {annotations_dir}")
    print("ВАЖНО: Проверьте и отредактируйте разметки вручную!")

if __name__ == "__main__":
    batch_annotate()
