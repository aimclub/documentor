"""
Скрипт для конвертации PDF в Markdown с помощью библиотеки marker-pdf.
"""

import sys
import os
import subprocess
from pathlib import Path

# Убираем текущую директорию из sys.path, чтобы избежать конфликта с локальной папкой marker
current_dir = Path(__file__).parent
if str(current_dir) in sys.path:
    sys.path.remove(str(current_dir))

# Пытаемся импортировать marker из venv_marker
try:
    # Добавляем venv_marker в sys.path, если он существует
    base_dir = Path(__file__).parent
    venv_marker_path = base_dir / "venv_marker"
    if venv_marker_path.exists():
        venv_site_packages = venv_marker_path / "Lib" / "site-packages"
        if venv_site_packages.exists():
            sys.path.insert(0, str(venv_site_packages))
    
    import marker
except ImportError as e:
    print(f"[ERROR] Не удалось импортировать marker: {e}")
    print("Убедитесь, что marker-pdf установлен в venv_marker:")
    print("venv_marker\\Scripts\\activate")
    print("pip install marker-pdf")
    sys.exit(1)


def convert_pdf_to_markdown(
    pdf_path: Path,
    output_dir: Path
):
    """
    Конвертирует PDF в Markdown с помощью marker CLI.
    
    Args:
        pdf_path: Путь к PDF файлу
        output_dir: Директория для сохранения результата
    """
    print(f"Конвертация PDF в Markdown: {pdf_path.name}")
    
    # Создаем директорию для результатов
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Путь для выходного файла
    output_md_path = output_dir / f"{pdf_path.stem}.md"
    
    try:
        # Пробуем использовать Python API marker напрямую
        print("  Конвертация PDF в Markdown через marker Python API...", end=" ", flush=True)
        
        # Инициализируем переменные
        result = None
        command_start_time = None
        
        try:
            # Пытаемся импортировать правильный Python API marker
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
            from marker.output import text_from_rendered
            
            # Создаем converter
            print("\n  [INFO] Создание PdfConverter...", end=" ", flush=True)
            converter = PdfConverter(
                artifact_dict=create_model_dict(),
            )
            print("[OK]")
            
            # Конвертируем PDF
            print("  [INFO] Конвертация PDF...", end=" ", flush=True)
            rendered = converter(str(pdf_path.absolute()))
            print("[OK]")
            
            # Извлекаем текст из результата
            print("  [INFO] Извлечение текста...", end=" ", flush=True)
            full_text, _, images = text_from_rendered(rendered)
            print("[OK]")
            
            # Сохраняем результат
            print("  [INFO] Сохранение результата...", end=" ", flush=True)
            with open(output_md_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            print("[OK]")
            
            print("[OK]")
            # Если использовали Python API, файл уже создан, возвращаем путь
            if output_md_path.exists():
                return output_md_path
            
        except ImportError as e:
            print(f"[ERROR] Не удалось импортировать marker API: {e}")
            print("  Пробуем использовать CLI команду...")
            
            # Fallback на CLI команду
            project_root = Path(__file__).parent.parent.parent
            
            # Пытаемся найти venv_marker и использовать его Python
            python_executable = sys.executable
            possible_venv_paths = [
                project_root / "venv_marker",
                Path(__file__).parent / "venv_marker",
                Path.cwd() / "venv_marker",
            ]
            
            for venv_marker_path in possible_venv_paths:
                if venv_marker_path.exists():
                    venv_python = venv_marker_path / "Scripts" / "python.exe"
                    if not venv_python.exists():
                        venv_python = venv_marker_path / "bin" / "python"
                    if venv_python.exists():
                        python_executable = str(venv_python)
                        print(f"\n  [INFO] Используется Python из venv_marker: {python_executable}")
                        break
            
            # Используем правильную команду marker_single
            # Проверяем, есть ли локальная копия marker
            marker_local_path = Path(__file__).parent / "marker_local"
            if marker_local_path.exists():
                # Используем локальную копию
                marker_script = marker_local_path / "convert_single.py"
                if marker_script.exists():
                    cmd = [
                        python_executable, str(marker_script),
                        str(pdf_path.absolute())
                    ]
                else:
                    # Используем установленную версию через marker_single
                    cmd = [
                        python_executable, "-m", "marker.scripts.convert_single",
                        str(pdf_path.absolute())
                    ]
            else:
                # Используем установленную версию через marker_single
                cmd = [
                    python_executable, "-m", "marker.scripts.convert_single",
                    str(pdf_path.absolute())
                ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                cwd=str(project_root)
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"marker CLI вернул код ошибки: {result.returncode}")
            
            # Запоминаем время перед запуском команды для проверки времени создания файла
            import time
            command_start_time = time.time() - 5  # Небольшой запас на случай задержек
            
            # Проверяем, может быть marker выводит результат в stdout
            if result.stdout and result.stdout.strip():
                print(f"\n  [INFO] Marker вывел результат в stdout ({len(result.stdout)} символов)")
                # Сохраняем stdout как результат
                with open(output_md_path, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
                print(f"  [OK] Результат сохранен из stdout: {output_md_path}")
                print("[OK]")
                return output_md_path
            
            print("[OK]")
            
            # Проверяем возможные места, где marker мог сохранить файл
            # Marker обычно создает файл рядом с исходным PDF или в текущей директории
            # Приоритет: файлы, которые соответствуют имени PDF
            pdf_stem = pdf_path.stem
            possible_paths = [
                pdf_path.parent / f"{pdf_stem}.md",  # Рядом с PDF (высший приоритет)
                pdf_path.parent / f"{pdf_stem}_marker.md",  # С суффиксом
                Path.cwd() / f"{pdf_stem}.md",  # В текущей директории
                project_root / f"{pdf_stem}.md",  # В корне проекта
                output_md_path,  # Указанный путь
                output_dir / f"{pdf_stem}.md",
            ]
            
            # Парсим stdout на предмет пути к файлу
            md_paths_in_output = []
            if result.stdout:
                import re
                # Ищем пути к .md файлам в выводе
                md_paths_in_output = re.findall(r'[\w\\/]+\.md', result.stdout)
            
            if md_paths_in_output:
                print(f"  [DEBUG] Найдены пути к .md файлам в stdout: {md_paths_in_output}")
                for path_str in md_paths_in_output:
                    path = Path(path_str)
                    if not path.is_absolute():
                        # Пробуем относительно разных директорий
                        for base in [pdf_path.parent, project_root, Path.cwd()]:
                            abs_path = base / path
                            if abs_path.exists():
                                possible_paths.append(abs_path)
                    elif path.exists():
                        possible_paths.append(path)
        
        # Если использовали CLI, ищем созданный файл
        if result is not None and command_start_time is not None:
            # Ищем файлы, которые соответствуют имени PDF (приоритет)
            print(f"  [DEBUG] Поиск созданных файлов...")
            print(f"  [DEBUG] Ищем файлы с именем, соответствующим PDF: {pdf_stem}")
        
        # Проверяем файлы в директории PDF, которые соответствуют имени
        md_files_in_pdf_dir = [
            f for f in pdf_path.parent.glob("*.md")
            if pdf_stem in f.stem or f.stem in pdf_stem
        ]
        if md_files_in_pdf_dir:
            print(f"  [DEBUG] Найдены соответствующие .md файлы в директории PDF: {[f.name for f in md_files_in_pdf_dir]}")
            # Добавляем в начало списка (высший приоритет)
            possible_paths = md_files_in_pdf_dir + possible_paths
        
        found_path = None
        # Сначала проверяем файлы, которые точно соответствуют имени PDF
        for path in possible_paths:
            if path.exists():
                # Проверяем, что файл соответствует имени PDF
                if pdf_stem in path.stem or path.stem in pdf_stem:
                    # Проверяем время создания (должен быть создан недавно)
                    file_mtime = path.stat().st_mtime
                    if file_mtime >= command_start_time:
                        found_path = path
                        print(f"  [DEBUG] Файл найден (соответствует имени и времени): {path}")
                        break
                    else:
                        print(f"  [DEBUG] Файл найден, но создан до запуска команды: {path} (пропускаем)")
        
        # Если не нашли по имени, ищем по времени создания (только в директории PDF)
        if not found_path:
            print(f"  [DEBUG] Поиск по времени создания в директории PDF...")
            for md_file in pdf_path.parent.glob("*.md"):
                file_mtime = md_file.stat().st_mtime
                if file_mtime >= command_start_time:
                    found_path = md_file
                    print(f"  [DEBUG] Файл найден по времени создания: {found_path}")
                    break
        
        # Если файл не найден, выводим дополнительную информацию
        if not found_path:
            print(f"  [WARNING] Файл не найден автоматически")
            print(f"  [DEBUG] Проверяем все возможные места вручную...")
            # Проверяем все возможные пути еще раз
            for path in possible_paths:
                if path.exists():
                    file_mtime = path.stat().st_mtime
                    print(f"    - {path} (существует, время создания: {time.ctime(file_mtime)})")
                else:
                    print(f"    - {path} (не существует)")
        
        # Если файл найден, но не в ожидаемом месте, копируем его
        if found_path and found_path != output_md_path:
            print(f"  [INFO] Файл найден в другом месте: {found_path}")
            import shutil
            # Копируем вместо перемещения, чтобы не удалить исходный файл
            shutil.copy2(str(found_path), str(output_md_path))
            print(f"  [INFO] Файл скопирован в: {output_md_path}")
        
        # Проверяем, что файл создан
        if output_md_path.exists():
            file_size = output_md_path.stat().st_size
            print(f"  [OK] Markdown сохранен: {output_md_path.name} ({file_size} байт)")
            
            # Показываем первые несколько строк для проверки
            try:
                with open(output_md_path, 'r', encoding='utf-8') as f:
                    first_lines = f.readlines()[:5]
                    if first_lines:
                        print(f"  Первые строки результата:")
                        for i, line in enumerate(first_lines, 1):
                            print(f"    {i}: {line.strip()[:80]}")
            except Exception as e:
                print(f"  [WARNING] Не удалось прочитать файл: {e}")
        else:
            print(f"  [WARNING] Файл не найден: {output_md_path}")
        
        print(f"\n[OK] Конвертация завершена!")
        print(f"Результаты сохранены в: {output_dir}")
        return output_md_path
        
    except FileNotFoundError:
        print(f"[ERROR] Команда marker не найдена")
        print("Убедитесь, что marker-pdf установлен: pip install marker-pdf")
        raise
    except Exception as e:
        print(f"[ERROR] Ошибка при конвертации: {e}")
        import traceback
        traceback.print_exc()
        raise


def main():
    """Основная функция."""
    # Находим тестовый PDF файл
    base_dir = Path(__file__).parent
    test_files_dir = base_dir / "test_files"
    
    pdf_files = list(test_files_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[ERROR] PDF файлы не найдены в {test_files_dir}")
        return
    
    # Берем первый файл для теста
    test_pdf = pdf_files[0]
    print(f"Выбран файл для тестирования: {test_pdf.name}\n")
    
    # Создаем директорию для результатов
    output_dir = base_dir / "results" / "marker_markdown"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Результаты будут сохранены в: {output_dir}\n")
    
    # Конвертируем
    try:
        result_path = convert_pdf_to_markdown(test_pdf, output_dir)
        if result_path and result_path.exists():
            print(f"\n[SUCCESS] Файл успешно создан: {result_path}")
    except Exception as e:
        print(f"\n[ERROR] Не удалось конвертировать PDF: {e}")


if __name__ == "__main__":
    main()
