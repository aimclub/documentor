"""
Скрипт для мониторинга потребления CPU и GPU при обработке документов через Marker.

Запускайте этот скрипт из окружения Marker (venv_marker):
  cd experiments/pdf_text_extraction
  venv_marker\\Scripts\\activate  # Windows
  # или
  source venv_marker/bin/activate  # Linux/Mac
  cd ../../metrics
  python monitor_marker_resources.py
"""

import json
import time
import subprocess
import threading
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import sys

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[ERROR] psutil не установлен. Установите: pip install psutil")
    sys.exit(1)

try:
    import pynvml
    try:
        import nvidia_ml_py3
        USE_NVIDIA_ML_PY = True
    except ImportError:
        USE_NVIDIA_ML_PY = False
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False
    USE_NVIDIA_ML_PY = False
    print("[WARNING] nvidia-ml-py не установлен. Установите: pip install nvidia-ml-py3")
    print("[INFO] Будет использоваться nvidia-smi для мониторинга GPU")

# Импортируем Marker
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
    MARKER_AVAILABLE = True
except ImportError as e:
    MARKER_AVAILABLE = False
    print(f"[ERROR] Marker не доступен: {e}")
    print("\nУбедитесь, что:")
    print("1. Активировано окружение venv_marker:")
    print("   cd experiments/pdf_text_extraction")
    print("   venv_marker\\Scripts\\activate  # Windows")
    print("   source venv_marker/bin/activate  # Linux/Mac")
    print("2. Marker установлен: pip install marker-pdf")
    sys.exit(1)


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
        except Exception:
            pass
        return None, None
    
    def get_gpu_metrics_pynvml(self) -> Tuple[Optional[float], Optional[float]]:
        """Получает метрики GPU через pynvml/nvidia-ml-py."""
        if not self.gpu_available:
            return None, None
        
        try:
            nvml = self.nvml_module
            mem_info = nvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
            vram_mb = mem_info.used / (1024 * 1024)
            util = nvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
            utilization = util.gpu
            return vram_mb, utilization
        except Exception:
            return None, None
    
    def get_gpu_metrics(self) -> Tuple[Optional[float], Optional[float]]:
        """Получает метрики GPU."""
        if PYNVML_AVAILABLE and self.gpu_available:
            vram, util = self.get_gpu_metrics_pynvml()
            if vram is not None:
                return vram, util
        return self.get_gpu_metrics_nvidia_smi()
    
    def collect_metrics(self):
        """Собирает метрики в отдельном потоке."""
        while self.monitoring:
            try:
                timestamp = time.time()
                cpu_percent = psutil.cpu_percent(interval=0.1)
                ram_mb = psutil.virtual_memory().used / (1024 * 1024)
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
        self.process = process
        self.monitoring = True
        self.metrics = []
        self.monitor_thread = threading.Thread(target=self.collect_metrics, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self) -> ResourceSummary:
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        
        if not self.metrics:
            return None
        
        cpu_values = [m.cpu_percent for m in self.metrics]
        ram_values = [m.ram_mb for m in self.metrics]
        gpu_vram_values = [m.gpu_vram_mb for m in self.metrics if m.gpu_vram_mb is not None]
        gpu_util_values = [m.gpu_utilization_percent for m in self.metrics if m.gpu_utilization_percent is not None]
        
        duration = self.metrics[-1].timestamp - self.metrics[0].timestamp if len(self.metrics) > 1 else 0
        
        summary = ResourceSummary(
            method="marker",
            document_id="",
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


def process_with_marker(pdf_path: Path) -> Dict[str, Any]:
    """Обрабатывает документ через Marker."""
    models = create_model_dict()
    
    converter = PdfConverter(
        artifact_dict=models,
        renderer="marker.renderers.json.JSONRenderer",
    )
    
    result = converter(str(pdf_path.absolute()))
    return result


def monitor_processing(
    pdf_path: Path,
    document_id: str
) -> ResourceSummary:
    """Мониторит обработку документа и собирает метрики ресурсов."""
    monitor = ResourceMonitor(interval=0.5)
    
    print(f"  [INFO] Начинается мониторинг ресурсов для marker...")
    monitor.start_monitoring()
    
    try:
        start_time = time.time()
        result = process_with_marker(pdf_path)
        processing_time = time.time() - start_time
        print(f"  [OK] Обработка завершена за {processing_time:.2f} сек")
    except Exception as e:
        print(f"  [ERROR] Ошибка при обработке: {e}")
        monitor.stop_monitoring()
        raise
    
    summary = monitor.stop_monitoring()
    summary.document_id = document_id
    
    return summary


def main():
    """Основная функция для мониторинга ресурсов."""
    parser = argparse.ArgumentParser(description='Мониторинг потребления CPU/GPU для Marker')
    parser.add_argument('--limit', type=int, default=None, 
                       help='Ограничить количество обрабатываемых файлов')
    parser.add_argument('--output', type=str, default=None,
                       help='Путь к выходному JSON файлу')
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    test_files_dir = script_dir / "test_files_for_metrics"
    output_file = script_dir / (args.output or "marker_resource_usage_report.json")
    
    if not MARKER_AVAILABLE:
        print("[ERROR] Marker недоступен")
        return
    
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"[ERROR] PDF файлы не найдены в {test_files_dir}")
        return
    
    if args.limit:
        test_files = pdf_files[:args.limit]
        print(f"[INFO] Ограничено до {args.limit} файлов для тестирования")
    else:
        test_files = pdf_files
    
    print(f"\nНайдено {len(pdf_files)} PDF файлов")
    print(f"Будет обработано {len(test_files)} файлов для мониторинга\n")
    
    print("=" * 60)
    print("МОНИТОРИНГ MARKER")
    print("=" * 60)
    
    results = {}
    
    for i, pdf_file in enumerate(test_files, 1):
        print(f"\n[{i}/{len(test_files)}] Marker: {pdf_file.name}")
        document_id = pdf_file.stem
        
        try:
            summary = monitor_processing(pdf_file, document_id)
            
            results[document_id] = {
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
    
    # Вычисляем средние значения
    if results:
        summary_data = {
            'avg_cpu_percent': sum(r['cpu_avg_percent'] for r in results.values()) / len(results),
            'max_cpu_percent': max(r['cpu_max_percent'] for r in results.values()),
            'avg_ram_mb': sum(r['ram_avg_mb'] for r in results.values()) / len(results),
            'max_ram_mb': max(r['ram_max_mb'] for r in results.values()),
        }
        
        gpu_vram_values = [r['gpu_vram_avg_mb'] for r in results.values() if r['gpu_vram_avg_mb'] is not None]
        if gpu_vram_values:
            summary_data['avg_gpu_vram_mb'] = sum(gpu_vram_values) / len(gpu_vram_values)
            summary_data['max_gpu_vram_mb'] = max(r['gpu_vram_max_mb'] for r in results.values() if r['gpu_vram_max_mb'] is not None)
        
        gpu_util_values = [r['gpu_utilization_avg_percent'] for r in results.values() if r['gpu_utilization_avg_percent'] is not None]
        if gpu_util_values:
            summary_data['avg_gpu_utilization_percent'] = sum(gpu_util_values) / len(gpu_util_values)
            summary_data['max_gpu_utilization_percent'] = max(r['gpu_utilization_max_percent'] for r in results.values() if r['gpu_utilization_max_percent'] is not None)
        
        results['_summary'] = summary_data
        
        print("\n" + "=" * 60)
        print("ИТОГОВАЯ СВОДКА")
        print("=" * 60)
        print(f"\nMARKER:")
        print(f"  CPU: avg={summary_data['avg_cpu_percent']:.1f}%, max={summary_data['max_cpu_percent']:.1f}%")
        print(f"  RAM: avg={summary_data['avg_ram_mb']:.1f} MB, max={summary_data['max_ram_mb']:.1f} MB")
        if 'avg_gpu_vram_mb' in summary_data:
            print(f"  GPU VRAM: avg={summary_data['avg_gpu_vram_mb']:.1f} MB, max={summary_data['max_gpu_vram_mb']:.1f} MB")
        if 'avg_gpu_utilization_percent' in summary_data:
            print(f"  GPU Utilization: avg={summary_data['avg_gpu_utilization_percent']:.1f}%, max={summary_data['max_gpu_utilization_percent']:.1f}%")
    
    # Сохраняем результаты
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({'marker': results}, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены в: {output_file}")


if __name__ == "__main__":
    main()
