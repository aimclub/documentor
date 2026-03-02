"""
Скрипт для конвертации всех PDF файлов из test_files_for_metrics в Markdown с помощью marker.
Засекает время для каждого файла.
"""

import sys
import time
from pathlib import Path
from typing import List, Tuple

# Добавляем путь к marker
base_dir = Path(__file__).parent.parent / "pdf_text_extraction"
venv_marker_path = base_dir / "venv_marker"
if venv_marker_path.exists():
    venv_site_packages = venv_marker_path / "Lib" / "site-packages"
    if venv_site_packages.exists():
        sys.path.insert(0, str(venv_site_packages))

marker_local_path = base_dir / "marker_local"
if marker_local_path.exists():
    sys.path.insert(0, str(marker_local_path))

try:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    MARKER_AVAILABLE = True
except ImportError as e:
    MARKER_AVAILABLE = False
    MARKER_ERROR = str(e)
    print(f"[ERROR] Не удалось импортировать marker: {e}")
    print("Убедитесь, что marker-pdf установлен в venv_marker")
    sys.exit(1)


def convert_pdf_to_markdown(pdf_path: Path, output_dir: Path) -> Tuple[Path, float]:
    """
    Конвертирует PDF в Markdown с помощью marker.
    
    Args:
        pdf_path: Путь к PDF файлу
        output_dir: Директория для сохранения результата
    
    Returns:
        Tuple[Path, float]: Путь к созданному MD файлу и время конвертации в секундах
    """
    start_time = time.time()
    
    # Создаем директорию для результатов
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Путь для выходного файла
    output_md_path = output_dir / f"{pdf_path.stem}.md"
    
    try:
        # Создаем converter
        converter = PdfConverter(
            artifact_dict=create_model_dict(),
        )
        
        # Конвертируем PDF
        rendered = converter(str(pdf_path.absolute()))
        
        # Извлекаем текст из результата
        full_text, _, images = text_from_rendered(rendered)
        
        # Сохраняем результат
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write(full_text)
        
        elapsed_time = time.time() - start_time
        return output_md_path, elapsed_time
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        raise RuntimeError(f"Ошибка при конвертации {pdf_path.name}: {e}") from e


def main():
    """Основная функция для конвертации всех PDF файлов."""
    if not MARKER_AVAILABLE:
        print(f"[ERROR] Marker недоступен: {MARKER_ERROR}")
        sys.exit(1)
    
    # Определяем пути
    script_dir = Path(__file__).parent
    test_files_dir = script_dir / "test_files_for_metrics"
    output_dir = script_dir / "marker_md_output"
    
    if not test_files_dir.exists():
        print(f"[ERROR] Папка {test_files_dir} не найдена")
        sys.exit(1)
    
    # Находим все PDF файлы
    pdf_files = sorted(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"[ERROR] PDF файлы не найдены в {test_files_dir}")
        sys.exit(1)
    
    print(f"Найдено {len(pdf_files)} PDF файлов для конвертации")
    print(f"Выходная директория: {output_dir}")
    print("-" * 80)
    
    # Результаты
    results: List[Tuple[str, float, bool, str]] = []
    total_start_time = time.time()
    
    # Конвертируем каждый файл
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Обработка: {pdf_file.name}")
        try:
            output_path, elapsed_time = convert_pdf_to_markdown(pdf_file, output_dir)
            print(f"  ✓ Успешно: {output_path.name}")
            print(f"  Время: {elapsed_time:.2f} секунд ({elapsed_time/60:.2f} минут)")
            results.append((pdf_file.name, elapsed_time, True, ""))
        except Exception as e:
            print(f"  ✗ Ошибка: {e}")
            results.append((pdf_file.name, 0.0, False, str(e)))
    
    total_elapsed_time = time.time() - total_start_time
    
    # Выводим итоговую статистику
    print("\n" + "=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    
    successful = [r for r in results if r[2]]
    failed = [r for r in results if not r[2]]
    
    print(f"\nУспешно обработано: {len(successful)}/{len(results)}")
    print(f"Ошибок: {len(failed)}")
    print(f"\nОбщее время: {total_elapsed_time:.2f} секунд ({total_elapsed_time/60:.2f} минут)")
    
    if successful:
        times = [r[1] for r in successful]
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        print(f"\nВремя конвертации (успешные):")
        print(f"  Среднее: {avg_time:.2f} секунд ({avg_time/60:.2f} минут)")
        print(f"  Минимальное: {min_time:.2f} секунд ({min_time/60:.2f} минут)")
        print(f"  Максимальное: {max_time:.2f} секунд ({max_time/60:.2f} минут)")
    
    print("\nДетали по файлам:")
    print("-" * 80)
    for filename, elapsed, success, error in results:
        status = "✓" if success else "✗"
        if success:
            print(f"  {status} {filename:50s} {elapsed:8.2f} сек ({elapsed/60:6.2f} мин)")
        else:
            print(f"  {status} {filename:50s} ОШИБКА: {error}")
    
    print(f"\nРезультаты сохранены в: {output_dir}")


if __name__ == "__main__":
    main()
