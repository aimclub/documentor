# Мониторинг потребления ресурсов (CPU/GPU)

Скрипт `monitor_resources.py` позволяет измерить потребление CPU и GPU при обработке документов через Marker и Dedoc.

## Требования

1. **psutil** - для мониторинга CPU и RAM:
   ```bash
   pip install psutil
   ```

2. **nvidia-ml-py3** (опционально) - для мониторинга GPU через Python:
   ```bash
   pip install nvidia-ml-py3
   ```
   **Важно:** Используйте `nvidia-ml-py3`, а не устаревший `pynvml`. Скрипт автоматически определит, какая библиотека доступна.
   
   Альтернатива: используйте `nvidia-smi` (должен быть установлен с драйверами NVIDIA) - скрипт автоматически переключится на него, если Python библиотека недоступна.

3. **Dedoc Docker контейнер** (для мониторинга Dedoc):
   ```bash
   docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc
   ```

4. **Marker** (для мониторинга Marker):
   - Должен быть установлен в `venv_marker` или `marker_local`
   - См. инструкции в `README_DEDOC.md` или документации Marker

## Использование

### Мониторинг Dedoc

```bash
cd experiments/metrics
python monitor_resources.py
```

Скрипт автоматически проверит доступность Dedoc и соберет метрики.

### Мониторинг Marker

Marker требует отдельного окружения. Используйте специальный скрипт:

```bash
# Активируйте окружение Marker
cd experiments/pdf_text_extraction
venv_marker\Scripts\activate  # Windows
# или
source venv_marker/bin/activate  # Linux/Mac

# Запустите мониторинг
cd ../../metrics
python monitor_marker_resources.py
```

**Примечание:** Скрипт `monitor_resources.py` также может мониторить Marker, если он доступен в текущем окружении, но рекомендуется использовать `monitor_marker_resources.py` из окружения Marker для более точных результатов.

### Объединение результатов

После запуска обоих скриптов результаты будут в:
- `resource_usage_report.json` - для Dedoc
- `marker_resource_usage_report.json` - для Marker

Вы можете объединить их вручную или использовать общий скрипт `monitor_resources.py`, если оба метода доступны в одном окружении.

## Выходные данные

Скрипт создает файл `resource_usage_report.json` со следующей структурой:

```json
{
  "dedoc": {
    "document_id": {
      "duration": 2.32,
      "cpu_avg_percent": 15.5,
      "cpu_max_percent": 45.2,
      "ram_avg_mb": 512.3,
      "ram_max_mb": 768.1,
      "gpu_vram_avg_mb": null,
      "gpu_vram_max_mb": null,
      "gpu_utilization_avg_percent": null,
      "gpu_utilization_max_percent": null
    }
  },
  "marker": {
    "document_id": {
      ...
    }
  },
  "_summary": {
    "dedoc": {
      "avg_cpu_percent": 15.5,
      "max_cpu_percent": 45.2,
      "avg_ram_mb": 512.3,
      "max_ram_mb": 768.1
    },
    "marker": {
      ...
    }
  }
}
```

## Метрики

- **CPU**: средний и максимальный процент использования CPU
- **RAM**: среднее и максимальное использование оперативной памяти (MB)
- **GPU VRAM**: среднее и максимальное использование видеопамяти (MB) - если доступен GPU
- **GPU Utilization**: средний и максимальный процент утилизации GPU - если доступен GPU

## Примечания

- Скрипт собирает метрики каждые 0.5 секунды во время обработки
- Если GPU недоступен или не используется, значения `gpu_vram_*` и `gpu_utilization_*` будут `null`
- Для более точного мониторинга конкретного процесса можно модифицировать скрипт для отслеживания PID процесса
