"""
Скрипт для мониторинга потребления CPU и GPU при обработке документов через Marker и Dedoc.

Собирает метрики:
- CPU usage (%)
- RAM usage (MB)
- GPU VRAM usage (MB) - если доступен GPU
- GPU utilization (%) - если доступен GPU
"""

import json
import time
import subprocess
import threading
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import sys

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[WARNING] psutil не установлен. Установите: pip install psutil")

try:
    import pynvml
    # Проверяем, что это nvidia-ml-py, а не устаревший pynvml
    try:
        import nvidia_ml_py3
        PYNVML_AVAILABLE = True
        USE_NVIDIA_ML_PY = True
    except ImportError:
        # Используем pynvml как fallback, но предупреждаем
        PYNVML_AVAILABLE = True
        USE_NVIDIA_ML_PY = False
        print("[WARNING] Используется устаревший pynvml. Рекомендуется: pip install nvidia-ml-py3")
except ImportError:
    PYNVML_AVAILABLE = False
    USE_NVIDIA_ML_PY = False
    print("[WARNING] nvidia-ml-py не установлен. Установите: pip install nvidia-ml-py3")
    print("[INFO] Будет использоваться nvidia-smi для мониторинга GPU")


@dataclass
class ResourceMetrics:
    """Метрики потребления ресурсов в определенный момент времени."""
    timestamp: float
    cpu_percent: float
    ram_mb: float
    gpu_vram_mb: Optional[float] = None
    gpu_utilization_percent: Optional[float] = None


@dataclass
class ResourceSummary:
    """Сводка потребления ресурсов за период."""
    method: str
    document_id: str
    duration: float
    cpu_avg: float
    cpu_max: float
    ram_avg_mb: float
    ram_max_mb: float
    gpu_vram_avg_mb: Optional[float] = None
    gpu_vram_max_mb: Optional[float] = None
    gpu_utilization_avg: Optional[float] = None
    gpu_utilization_max: Optional[float] = None
    metrics: List[ResourceMetrics] = field(default_factory=list)


class ResourceMonitor:
    """Класс для мониторинга потребления ресурсов."""
    
    def __init__(self, interval: float = 0.5):
        """
        Инициализирует монитор ресурсов.
        
        Args:
            interval: Интервал сбора метрик в секундах
        """
        self.interval = interval
        self.monitoring = False
        self.metrics: List[ResourceMetrics] = []
        self.monitor_thread: Optional[threading.Thread] = None
        self.process = None
        
        # Инициализация GPU мониторинга
        self.gpu_available = False
        self.nvml_module = None
        if PYNVML_AVAILABLE:
            try:
                # Используем nvidia-ml-py3 если доступен, иначе pynvml
                if USE_NVIDIA_ML_PY:
                    import nvidia_ml_py3 as nvml
                    nvml.nvmlInit()
                    self.gpu_handle = nvml.nvmlDeviceGetHandleByIndex(0)
                    self.nvml_module = nvml
                else:
                    pynvml.nvmlInit()
                    self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self.nvml_module = pynvml
                self.gpu_available = True
            except Exception as e:
                print(f"[WARNING] Не удалось инициализировать GPU мониторинг: {e}")
                self.gpu_available = False
    
    def get_gpu_metrics_nvidia_smi(self) -> Tuple[Optional[float], Optional[float]]:
        """Получает метрики GPU через nvidia-smi."""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', 
                 '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(', ')
                if len(parts) >= 2:
                    vram_mb = float(parts[0])
                    utilization = float(parts[1])
                    return vram_mb, utilization
        except Exception as e:
            pass
        return None, None
    
    def get_gpu_metrics_pynvml(self) -> Tuple[Optional[float], Optional[float]]:
        """Получает метрики GPU через pynvml/nvidia-ml-py."""
        if not self.gpu_available:
            return None, None
        
        try:
            nvml = self.nvml_module
            # Получаем использование VRAM
            mem_info = nvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
            vram_mb = mem_info.used / (1024 * 1024)  # Конвертируем в MB
            
            # Получаем утилизацию GPU
            util = nvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
            utilization = util.gpu
            
            return vram_mb, utilization
        except Exception as e:
            return None, None
    
    def get_gpu_metrics(self) -> Tuple[Optional[float], Optional[float]]:
        """Получает метрики GPU (пробует pynvml, затем nvidia-smi)."""
        if PYNVML_AVAILABLE and self.gpu_available:
            vram, util = self.get_gpu_metrics_pynvml()
            if vram is not None:
                return vram, util
        
        # Fallback на nvidia-smi
        return self.get_gpu_metrics_nvidia_smi()
    
    def collect_metrics(self):
        """Собирает метрики в отдельном потоке."""
        while self.monitoring:
            try:
                timestamp = time.time()
                
                # CPU и RAM
                if PSUTIL_AVAILABLE:
                    cpu_percent = psutil.cpu_percent(interval=0.1)
                    ram_mb = psutil.virtual_memory().used / (1024 * 1024)
                else:
                    cpu_percent = 0.0
                    ram_mb = 0.0
                
                # GPU
                gpu_vram_mb, gpu_utilization = self.get_gpu_metrics()
                
                metric = ResourceMetrics(
                    timestamp=timestamp,
                    cpu_percent=cpu_percent,
                    ram_mb=ram_mb,
                    gpu_vram_mb=gpu_vram_mb,
                    gpu_utilization_percent=gpu_utilization
                )
                
                self.metrics.append(metric)
                
                time.sleep(self.interval)
            except Exception as e:
                print(f"[WARNING] Ошибка при сборе метрик: {e}")
                time.sleep(self.interval)
    
    def start_monitoring(self, process=None):
        """
        Начинает мониторинг ресурсов.
        
        Args:
            process: Процесс для мониторинга (опционально, для более точного мониторинга)
        """
        self.process = process
        self.monitoring = True
        self.metrics = []
        self.monitor_thread = threading.Thread(target=self.collect_metrics, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self) -> ResourceSummary:
        """
        Останавливает мониторинг и возвращает сводку.
        
        Args:
            method: Название метода (marker/dedoc)
            document_id: ID документа
            
        Returns:
            ResourceSummary с метриками
        """
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        
        if not self.metrics:
            return None
        
        # Вычисляем сводку
        cpu_values = [m.cpu_percent for m in self.metrics]
        ram_values = [m.ram_mb for m in self.metrics]
        
        gpu_vram_values = [m.gpu_vram_mb for m in self.metrics if m.gpu_vram_mb is not None]
        gpu_util_values = [m.gpu_utilization_percent for m in self.metrics if m.gpu_utilization_percent is not None]
        
        duration = self.metrics[-1].timestamp - self.metrics[0].timestamp if len(self.metrics) > 1 else 0
        
        summary = ResourceSummary(
            method="",  # Будет установлено позже
            document_id="",  # Будет установлено позже
            duration=duration,
            cpu_avg=sum(cpu_values) / len(cpu_values) if cpu_values else 0.0,
            cpu_max=max(cpu_values) if cpu_values else 0.0,
            ram_avg_mb=sum(ram_values) / len(ram_values) if ram_values else 0.0,
            ram_max_mb=max(ram_values) if ram_values else 0.0,
            gpu_vram_avg_mb=sum(gpu_vram_values) / len(gpu_vram_values) if gpu_vram_values else None,
            gpu_vram_max_mb=max(gpu_vram_values) if gpu_vram_values else None,
            gpu_utilization_avg=sum(gpu_util_values) / len(gpu_util_values) if gpu_util_values else None,
            gpu_utilization_max=max(gpu_util_values) if gpu_util_values else None,
            metrics=self.metrics.copy()
        )
        
        return summary


def process_with_dedoc(pdf_path: Path, dedoc_output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Обрабатывает документ через Dedoc."""
    try:
        import requests
    except ImportError:
        raise ImportError("requests не установлен. Установите: pip install requests")
    
    api_url = 'http://localhost:1231/upload'
    
    with open(pdf_path, 'rb') as f:
        files = {'file': (pdf_path.name, f, 'application/pdf')}
        response = requests.post(api_url, files=files, timeout=300)
        response.raise_for_status()
        return response.json()


def process_with_marker(pdf_path: Path) -> Dict[str, Any]:
    """Обрабатывает документ через Marker."""
    # Добавляем путь к marker
    base_dir = Path(__file__).parent.parent / "pdf_text_extraction"
    venv_marker_path = base_dir / "venv_marker"
    marker_local_path = base_dir / "marker_local"
    
    if venv_marker_path.exists():
        venv_site_packages = venv_marker_path / "Lib" / "site-packages"
        if venv_site_packages.exists():
            sys.path.insert(0, str(venv_site_packages))
    
    if marker_local_path.exists():
        sys.path.insert(0, str(marker_local_path))
    
    try:
        from marker.models import create_model_dict
        from marker.converters.pdf import PdfConverter
        from marker.renderers.json import JSONRenderer
    except ImportError as e:
        raise ImportError(f"Marker не установлен: {e}")
    
    # Создаем конвертер
    models = create_model_dict()
    
    converter = PdfConverter(
        artifact_dict=models,
        renderer="marker.renderers.json.JSONRenderer",
    )
    
    # Конвертируем PDF
    result = converter(str(pdf_path.absolute()))
    return result


def monitor_processing(
    method: str,
    pdf_path: Path,
    processing_func,
    document_id: str
) -> ResourceSummary:
    """
    Мониторит обработку документа и собирает метрики ресурсов.
    
    Args:
        method: Название метода ('marker' или 'dedoc')
        pdf_path: Путь к PDF файлу
        processing_func: Функция для обработки документа
        document_id: ID документа
        
    Returns:
        ResourceSummary с метриками
    """
    monitor = ResourceMonitor(interval=0.5)
    
    print(f"  [INFO] Начинается мониторинг ресурсов для {method}...")
    monitor.start_monitoring()
    
    try:
        start_time = time.time()
        result = processing_func(pdf_path)
        processing_time = time.time() - start_time
        print(f"  [OK] Обработка завершена за {processing_time:.2f} сек")
    except Exception as e:
        print(f"  [ERROR] Ошибка при обработке: {e}")
        monitor.stop_monitoring()
        raise
    
    summary = monitor.stop_monitoring()
    summary.method = method
    summary.document_id = document_id
    
    return summary


def main():
    """Основная функция для мониторинга ресурсов."""
    parser = argparse.ArgumentParser(description='Мониторинг потребления CPU/GPU для Marker и Dedoc')
    parser.add_argument('--limit', type=int, default=None, 
                       help='Ограничить количество обрабатываемых файлов (для тестирования)')
    parser.add_argument('--output', type=str, default=None,
                       help='Путь к выходному JSON файлу (по умолчанию: resource_usage_report.json)')
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    
    # Пути к файлам
    test_files_dir = script_dir / "test_files_for_metrics"
    output_file = script_dir / (args.output or "resource_usage_report.json")
    
    if not PSUTIL_AVAILABLE:
        print("[ERROR] psutil не установлен. Установите: pip install psutil")
        return
    
    # Проверяем доступность методов
    dedoc_available = False
    marker_available = False
    
    # Проверяем Dedoc
    try:
        import requests
        response = requests.get('http://localhost:1231/', timeout=2)
        dedoc_available = True
        print("[INFO] Dedoc Docker API доступен")
    except:
        print("[WARNING] Dedoc Docker API недоступен")
    
    # Проверяем Marker
    try:
        base_dir = script_dir.parent / "pdf_text_extraction"
        venv_marker_path = base_dir / "venv_marker"
        marker_local_path = base_dir / "marker_local"
        
        if venv_marker_path.exists():
            venv_site_packages = venv_marker_path / "Lib" / "site-packages"
            if venv_site_packages.exists():
                sys.path.insert(0, str(venv_site_packages))
        
        if marker_local_path.exists():
            sys.path.insert(0, str(marker_local_path))
        
        from marker.models import create_model_dict
        marker_available = True
        print("[INFO] Marker доступен")
    except:
        print("[WARNING] Marker недоступен")
    
    if not dedoc_available and not marker_available:
        print("[ERROR] Ни один метод не доступен. Убедитесь, что:")
        print("  - Dedoc Docker контейнер запущен (docker run -d -p 1231:1231 dedocproject/dedoc)")
        print("  - Marker установлен в venv_marker или marker_local")
        return
    
    # Находим PDF файлы
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"[ERROR] PDF файлы не найдены в {test_files_dir}")
        return
    
    # Обрабатываем файлы (можно ограничить через --limit)
    if args.limit:
        test_files = pdf_files[:args.limit]
        print(f"[INFO] Ограничено до {args.limit} файлов для тестирования")
    else:
        test_files = pdf_files  # Обрабатываем все файлы
    
    print(f"\nНайдено {len(pdf_files)} PDF файлов")
    print(f"Будет обработано {len(test_files)} файлов для мониторинга\n")
    
    results = {}
    
    # Мониторим Dedoc
    if dedoc_available:
        print("=" * 60)
        print("МОНИТОРИНГ DEDOC")
        print("=" * 60)
        
        dedoc_results = {}
        for i, pdf_file in enumerate(test_files, 1):
            print(f"\n[{i}/{len(test_files)}] Dedoc: {pdf_file.name}")
            document_id = pdf_file.stem
            
            try:
                summary = monitor_processing(
                    method="dedoc",
                    pdf_path=pdf_file,
                    processing_func=lambda p: process_with_dedoc(p),
                    document_id=document_id
                )
                
                dedoc_results[document_id] = {
                    'duration': summary.duration,
                    'cpu_avg_percent': summary.cpu_avg,
                    'cpu_max_percent': summary.cpu_max,
                    'ram_avg_mb': summary.ram_avg_mb,
                    'ram_max_mb': summary.ram_max_mb,
                    'gpu_vram_avg_mb': summary.gpu_vram_avg_mb,
                    'gpu_vram_max_mb': summary.gpu_vram_max_mb,
                    'gpu_utilization_avg_percent': summary.gpu_utilization_avg,
                    'gpu_utilization_max_percent': summary.gpu_utilization_max,
                }
                
                print(f"  CPU: avg={summary.cpu_avg:.1f}%, max={summary.cpu_max:.1f}%")
                print(f"  RAM: avg={summary.ram_avg_mb:.1f} MB, max={summary.ram_max_mb:.1f} MB")
                if summary.gpu_vram_avg_mb is not None:
                    print(f"  GPU VRAM: avg={summary.gpu_vram_avg_mb:.1f} MB, max={summary.gpu_vram_max_mb:.1f} MB")
                if summary.gpu_utilization_avg is not None:
                    print(f"  GPU Utilization: avg={summary.gpu_utilization_avg:.1f}%, max={summary.gpu_utilization_max:.1f}%")
                
            except Exception as e:
                print(f"  [ERROR] Ошибка: {e}")
                import traceback
                traceback.print_exc()
        
        results['dedoc'] = dedoc_results
    
    # Мониторим Marker
    if marker_available:
        print("\n" + "=" * 60)
        print("МОНИТОРИНГ MARKER")
        print("=" * 60)
        
        marker_results = {}
        for i, pdf_file in enumerate(test_files, 1):
            print(f"\n[{i}/{len(test_files)}] Marker: {pdf_file.name}")
            document_id = pdf_file.stem
            
            try:
                summary = monitor_processing(
                    method="marker",
                    pdf_path=pdf_file,
                    processing_func=lambda p: process_with_marker(p),
                    document_id=document_id
                )
                
                marker_results[document_id] = {
                    'duration': summary.duration,
                    'cpu_avg_percent': summary.cpu_avg,
                    'cpu_max_percent': summary.cpu_max,
                    'ram_avg_mb': summary.ram_avg_mb,
                    'ram_max_mb': summary.ram_max_mb,
                    'gpu_vram_avg_mb': summary.gpu_vram_avg_mb,
                    'gpu_vram_max_mb': summary.gpu_vram_max_mb,
                    'gpu_utilization_avg_percent': summary.gpu_utilization_avg,
                    'gpu_utilization_max_percent': summary.gpu_utilization_max,
                }
                
                print(f"  CPU: avg={summary.cpu_avg:.1f}%, max={summary.cpu_max:.1f}%")
                print(f"  RAM: avg={summary.ram_avg_mb:.1f} MB, max={summary.ram_max_mb:.1f} MB")
                if summary.gpu_vram_avg_mb is not None:
                    print(f"  GPU VRAM: avg={summary.gpu_vram_avg_mb:.1f} MB, max={summary.gpu_vram_max_mb:.1f} MB")
                if summary.gpu_utilization_avg is not None:
                    print(f"  GPU Utilization: avg={summary.gpu_utilization_avg:.1f}%, max={summary.gpu_utilization_max:.1f}%")
                
            except Exception as e:
                print(f"  [ERROR] Ошибка: {e}")
                import traceback
                traceback.print_exc()
        
        results['marker'] = marker_results
    
    # Вычисляем средние значения
    if results:
        summary = {}
        for method, method_results in results.items():
            if method_results:
                summary[method] = {
                    'avg_cpu_percent': sum(r['cpu_avg_percent'] for r in method_results.values()) / len(method_results),
                    'max_cpu_percent': max(r['cpu_max_percent'] for r in method_results.values()),
                    'avg_ram_mb': sum(r['ram_avg_mb'] for r in method_results.values()) / len(method_results),
                    'max_ram_mb': max(r['ram_max_mb'] for r in method_results.values()),
                }
                
                # GPU метрики (если доступны)
                gpu_vram_values = [r['gpu_vram_avg_mb'] for r in method_results.values() if r['gpu_vram_avg_mb'] is not None]
                if gpu_vram_values:
                    summary[method]['avg_gpu_vram_mb'] = sum(gpu_vram_values) / len(gpu_vram_values)
                    summary[method]['max_gpu_vram_mb'] = max(r['gpu_vram_max_mb'] for r in method_results.values() if r['gpu_vram_max_mb'] is not None)
                
                gpu_util_values = [r['gpu_utilization_avg_percent'] for r in method_results.values() if r['gpu_utilization_avg_percent'] is not None]
                if gpu_util_values:
                    summary[method]['avg_gpu_utilization_percent'] = sum(gpu_util_values) / len(gpu_util_values)
                    summary[method]['max_gpu_utilization_percent'] = max(r['gpu_utilization_max_percent'] for r in method_results.values() if r['gpu_utilization_max_percent'] is not None)
        
        results['_summary'] = summary
        
        print("\n" + "=" * 60)
        print("ИТОГОВАЯ СВОДКА")
        print("=" * 60)
        for method, method_summary in summary.items():
            print(f"\n{method.upper()}:")
            print(f"  CPU: avg={method_summary['avg_cpu_percent']:.1f}%, max={method_summary['max_cpu_percent']:.1f}%")
            print(f"  RAM: avg={method_summary['avg_ram_mb']:.1f} MB, max={method_summary['max_ram_mb']:.1f} MB")
            if 'avg_gpu_vram_mb' in method_summary:
                print(f"  GPU VRAM: avg={method_summary['avg_gpu_vram_mb']:.1f} MB, max={method_summary['max_gpu_vram_mb']:.1f} MB")
            if 'avg_gpu_utilization_percent' in method_summary:
                print(f"  GPU Utilization: avg={method_summary['avg_gpu_utilization_percent']:.1f}%, max={method_summary['max_gpu_utilization_percent']:.1f}%")
    
    # Сохраняем результаты
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены в: {output_file}")


if __name__ == "__main__":
    main()
