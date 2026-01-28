"""
Менеджер для управления Dots OCR через vLLM API.

Управляет:
- Очередями задач на распознавание для каждой модели
- Состоянием моделей (свободна/занята)
- Отправкой изображений на обработку через API
- Получением ответов
- Пуллом воркеров для параллельной обработки
- Загрузкой конфигурации из .env файла
"""

from __future__ import annotations

import os
import time
import json
import uuid
import threading
import base64
import io
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from queue import Queue, Empty
from PIL import Image
import openai

from .dots_ocr import get_system_prompt, load_prompts_from_config
from ..core.load_env import load_env_file


class TaskStatus(str, Enum):
    """Статус задачи на распознавание."""
    PENDING = "pending"  # В очереди
    PROCESSING = "processing"  # Обрабатывается
    COMPLETED = "completed"  # Завершена успешно
    FAILED = "failed"  # Завершена с ошибкой
    CANCELLED = "cancelled"  # Отменена


@dataclass
class OCRTask:
    """Задача на распознавание изображения."""
    task_id: str
    image: Image.Image
    model_id: str  # ID модели для обработки
    prompt_mode: str = "prompt_layout_only_en"
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    callback: Optional[Callable[[OCRTask], None]] = None
    
    def __post_init__(self) -> None:
        """Инициализация задачи."""
        if not self.task_id:
            self.task_id = str(uuid.uuid4())


@dataclass
class ModelConfig:
    """Конфигурация модели."""
    model_id: str
    base_url: str
    api_key: str
    model_name: str
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 60
    task_format: str = "Layout"  # OCR, Layout, Text


@dataclass
class ModelState:
    """Состояние модели."""
    config: ModelConfig
    is_available: bool = True
    is_busy: bool = False
    current_task_id: Optional[str] = None
    client: Optional[openai.OpenAI] = None
    total_tasks_processed: int = 0
    total_errors: int = 0
    last_used_at: Optional[float] = None


class DotsOCRManager:
    """
    Менеджер для управления Dots OCR через vLLM API.
    
    Управляет очередями задач для каждой модели, состоянием моделей и обработкой изображений.
    Поддерживает несколько моделей из .env файла.
    """
    
    def __init__(
        self,
        max_queue_size: int = 100,
        num_workers_per_model: int = 1,
        auto_load_models: bool = True,
        env_file: Optional[Path] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        """
        Инициализация менеджера.
        
        Args:
            max_queue_size: Максимальный размер очереди задач для каждой модели
            num_workers_per_model: Количество воркеров на каждую модель
            auto_load_models: Автоматически загружать модели при инициализации
            env_file: Путь к .env файлу (если None - ищет автоматически)
            config_path: Путь к конфигурационному файлу с промптами
        """
        self.max_queue_size = max_queue_size
        self.num_workers_per_model = num_workers_per_model
        self.auto_load_models = auto_load_models
        self.env_file = env_file
        self.config_path = config_path
        
        # Конфигурации моделей (model_id -> ModelConfig)
        self.model_configs: Dict[str, ModelConfig] = {}
        
        # Состояния моделей (model_id -> ModelState)
        self.model_states: Dict[str, ModelState] = {}
        
        # Очереди задач для каждой модели (model_id -> Queue)
        self.task_queues: Dict[str, Queue[OCRTask]] = {}
        
        # Все задачи (task_id -> OCRTask)
        self.tasks: Dict[str, OCRTask] = {}
        
        # Потоки воркеров (model_id -> List[Thread])
        self.worker_threads: Dict[str, List[threading.Thread]] = {}
        self._stop_workers = False
        self._workers_lock = threading.Lock()
        
        # Блокировки для доступа к состоянию моделей
        self._model_locks: Dict[str, threading.Lock] = {}
        
        # Загружаем промпты
        self.prompts = load_prompts_from_config(config_path)
        
        # Загружаем конфигурацию моделей из .env
        if auto_load_models:
            self.load_models_from_env()
    
    def load_models_from_env(self) -> None:
        """
        Загружает конфигурацию моделей из .env файла.
        
        Raises:
            RuntimeError: Если не удалось загрузить модели
        """
        # Загружаем .env файл
        load_env_file(self.env_file)
        
        # Получаем URL моделей (может быть несколько через запятую или перенос строки)
        dots_base_url_raw = os.getenv("DOTS_OCR_BASE_URL", "")
        
        if not dots_base_url_raw:
            raise RuntimeError("DOTS_OCR_BASE_URL не найден в переменных окружения")
        
        # Обрабатываем несколько URL
        urls = []
        for line in dots_base_url_raw.split('\n'):
            for url in line.split(','):
                url = self._clean_url(url.strip())
                if url and url not in urls:
                    urls.append(url)
        
        if not urls:
            raise RuntimeError("Не найдено ни одного валидного DOTS_OCR_BASE_URL")
        
        # Получаем общие параметры
        api_key = os.getenv("DOTS_OCR_API_KEY", "")
        model_name = os.getenv("DOTS_OCR_MODEL_NAME", "/model")
        temperature = float(os.getenv("DOTS_OCR_TEMPERATURE", "0.1"))
        max_tokens = int(os.getenv("DOTS_OCR_MAX_TOKENS", "4096"))
        timeout = int(os.getenv("DOTS_OCR_TIMEOUT", "60"))
        
        # Получаем task_format для каждой модели (может быть несколько через запятую)
        task_formats_raw = os.getenv("DOTS_OCR_TASK_FORMAT", "")
        task_formats = []
        if task_formats_raw:
            for line in task_formats_raw.split('\n'):
                for fmt in line.split(','):
                    fmt = fmt.strip()
                    if fmt and fmt.upper() in ["OCR", "LAYOUT", "TEXT"]:
                        task_formats.append(fmt.upper())
        
        # Если не указаны форматы, используем дефолтный "Layout" для всех моделей
        if not task_formats:
            task_formats = ["Layout"] * len(urls)
        elif len(task_formats) < len(urls):
            # Если указано меньше форматов, чем URL, повторяем последний
            task_formats.extend([task_formats[-1]] * (len(urls) - len(task_formats)))
        elif len(task_formats) > len(urls):
            # Если указано больше форматов, обрезаем
            task_formats = task_formats[:len(urls)]
        
        if not api_key:
            raise RuntimeError("DOTS_OCR_API_KEY не найден в переменных окружения")
        
        # Создаем конфигурацию для каждой модели
        for i, base_url in enumerate(urls):
            model_id = f"dots_ocr_{i}"
            task_format = task_formats[i] if i < len(task_formats) else "Layout"
            
            config = ModelConfig(
                model_id=model_id,
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                task_format=task_format
            )
            
            self.model_configs[model_id] = config
            
            # Создаем состояние модели
            client = openai.OpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=config.timeout
            )
            
            state = ModelState(
                config=config,
                client=client
            )
            
            self.model_states[model_id] = state
            self.task_queues[model_id] = Queue(maxsize=self.max_queue_size)
            self._model_locks[model_id] = threading.Lock()
            
            print(f"Модель {model_id} загружена: {base_url} (формат: {task_format})")
        
        print(f"Загружено {len(self.model_configs)} моделей")
        
        # Запускаем воркеры для каждой модели
        self._start_workers()
    
    def _clean_url(self, url: str) -> str:
        """Очищает URL от комментариев и пробелов."""
        if '#' in url:
            url = url.split('#')[0]
        return url.strip()
    
    def _start_workers(self) -> None:
        """Запускает воркеры для всех моделей."""
        with self._workers_lock:
            if self._stop_workers:
                return
            
            for model_id in self.model_configs.keys():
                if model_id in self.worker_threads:
                    continue  # Воркеры уже запущены
                
                threads = []
                for i in range(self.num_workers_per_model):
                    worker = threading.Thread(
                        target=self._worker_loop,
                        args=(model_id,),
                        name=f"DotsOCRWorker-{model_id}-{i}",
                        daemon=True
                    )
                    worker.start()
                    threads.append(worker)
                
                self.worker_threads[model_id] = threads
                print(f"Запущено {self.num_workers_per_model} воркеров для модели {model_id}")
    
    def _stop_workers(self) -> None:
        """Останавливает все воркеры."""
        with self._workers_lock:
            self._stop_workers = True
            
            for model_id, threads in self.worker_threads.items():
                for worker in threads:
                    worker.join(timeout=5.0)
            
            self.worker_threads.clear()
            print("Все воркеры остановлены")
    
    def _worker_loop(self, model_id: str) -> None:
        """Основной цикл воркера для обработки задач конкретной модели."""
        task_queue = self.task_queues.get(model_id)
        if task_queue is None:
            return
        
        while not self._stop_workers:
            try:
                # Получаем задачу из очереди (с таймаутом)
                try:
                    task = task_queue.get(timeout=1.0)
                except Empty:
                    continue
                
                # Проверяем, что задача предназначена для этой модели
                if task.model_id != model_id:
                    # Возвращаем задачу в правильную очередь
                    correct_queue = self.task_queues.get(task.model_id)
                    if correct_queue:
                        correct_queue.put(task)
                    continue
                
                # Обрабатываем задачу
                self._process_task(task, model_id)
                
                # Помечаем задачу как выполненную
                task_queue.task_done()
                
            except Exception as e:
                print(f"Ошибка в воркере {model_id}: {e}")
                import traceback
                traceback.print_exc()
    
    def _process_task(self, task: OCRTask, model_id: str) -> None:
        """
        Обрабатывает задачу на распознавание.
        
        Args:
            task: Задача на распознавание
            model_id: ID модели для обработки
        """
        model_state = self.model_states.get(model_id)
        if model_state is None:
            task.status = TaskStatus.FAILED
            task.error = f"Модель {model_id} не найдена"
            task.completed_at = time.time()
            return
        
        with self._model_locks[model_id]:
            if not model_state.is_available:
                task.status = TaskStatus.FAILED
                task.error = f"Модель {model_id} недоступна"
                task.completed_at = time.time()
                return
            
            if model_state.is_busy:
                # Если модель занята, возвращаем задачу в очередь
                self.task_queues[model_id].put(task)
                return
            
            # Помечаем модель как занятую
            model_state.is_busy = True
            model_state.current_task_id = task.task_id
        
        try:
            task.status = TaskStatus.PROCESSING
            task.started_at = time.time()
            
            # Получаем промпт
            prompt = self.prompts.get(task.prompt_mode, self.prompts.get("prompt_layout_only_en", ""))
            
            # Обрабатываем изображение через API
            result = self._detect_layout_api(
                task.image,
                prompt,
                model_state,
                task.metadata
            )
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            
            model_state.total_tasks_processed += 1
            model_state.last_used_at = time.time()
            
            # Вызываем callback, если есть
            if task.callback:
                try:
                    task.callback(task)
                except Exception as e:
                    print(f"Ошибка в callback для задачи {task.task_id}: {e}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            model_state.total_errors += 1
            print(f"Ошибка обработки задачи {task.task_id}: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            with self._model_locks[model_id]:
                model_state.is_busy = False
                model_state.current_task_id = None
    
    def _image_to_base64(self, image: Image.Image) -> str:
        """Конвертирует PIL изображение в base64 строку."""
        if hasattr(image, 'format') and image.format:
            format_type = image.format.upper()
        else:
            format_type = 'PNG'
        
        # Нормализуем формат для правильного MIME типа
        if format_type in ['JPG', 'JPEG']:
            format_type = 'JPEG'
            mime_type = 'jpeg'
        elif format_type == 'PNG':
            mime_type = 'png'
        elif format_type in ['GIF', 'WEBP']:
            mime_type = format_type.lower()
        else:
            format_type = 'PNG'
            mime_type = 'png'
        
        buffer = io.BytesIO()
        image.save(buffer, format=format_type)
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/{mime_type};base64,{img_str}"
    
    def _resize_image_if_needed(self, image: Image.Image, max_size: int = 2048) -> Image.Image:
        """Уменьшает изображение, если оно слишком большое."""
        width, height = image.size
        if max(width, height) > max_size:
            ratio = max_size / max(width, height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        return image
    
    def _detect_layout_api(
        self,
        image: Image.Image,
        prompt: str,
        model_state: ModelState,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Определяет layout страницы используя API.
        
        Args:
            image: PIL изображение страницы
            prompt: Текстовый промпт
            model_state: Состояние модели
            metadata: Дополнительные метаданные
            
        Returns:
            Dict с результатами layout detection
        """
        if model_state.client is None:
            raise RuntimeError("API клиент не инициализирован")
        
        # Уменьшаем изображение, если нужно
        processed_image = self._resize_image_if_needed(image, max_size=2048)
        width, height = processed_image.size
        
        # Получаем system prompt
        system_prompt = get_system_prompt(width, height)
        
        # Конвертируем изображение в base64
        image_base64 = self._image_to_base64(processed_image)
        
        # Создаем сообщения в формате OpenAI API
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_base64
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        
        # Отправляем запрос к API
        response = model_state.client.chat.completions.create(
            model=model_state.config.model_name,
            messages=messages,
            max_tokens=model_state.config.max_tokens,
            temperature=model_state.config.temperature
        )
        
        content = response.choices[0].message.content
        
        # Парсим ответ
        result = self._parse_layout_response(content)
        
        return result
    
    def _parse_layout_response(self, content: str) -> Dict[str, Any]:
        """
        Парсит JSON из текстового ответа модели.
        
        Args:
            content: Текстовый ответ модели
            
        Returns:
            Dict с распарсенным JSON
        """
        # Пытаемся найти JSON объект или массив в тексте
        text = content.strip()
        
        # Ищем первый { или [
        start_idx = -1
        for i, char in enumerate(text):
            if char in ['{', '[']:
                start_idx = i
                break
        
        if start_idx == -1:
            raise ValueError(f"Не найдено JSON в ответе: {text[:200]}")
        
        # Ищем последний } или ]
        end_idx = -1
        bracket_stack = []
        for i in range(start_idx, len(text)):
            char = text[i]
            if char == '{' or char == '[':
                bracket_stack.append(char)
            elif char == '}' or char == ']':
                if bracket_stack:
                    bracket_stack.pop()
                    if not bracket_stack:
                        end_idx = i + 1
                        break
        
        if end_idx == -1:
            raise ValueError(f"Не найден конец JSON в ответе: {text[:200]}")
        
        json_str = text[start_idx:end_idx]
        
        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка парсинга JSON: {e}. Текст: {json_str[:200]}")
    
    def get_available_models(self, task_format: Optional[str] = None) -> List[str]:
        """
        Получает список доступных моделей.
        
        Args:
            task_format: Формат задачи (OCR, Layout, Text). Если None - возвращает все доступные модели.
        
        Returns:
            List[str]: Список ID моделей
        """
        models = [
            model_id for model_id, state in self.model_states.items()
            if state.is_available
        ]
        
        # Фильтруем по формату задачи, если указан
        if task_format:
            task_format_upper = task_format.upper()
            models = [
                model_id for model_id in models
                if self.model_configs[model_id].task_format.upper() == task_format_upper
            ]
        
        return models
    
    def get_best_model(self, task_format: Optional[str] = None) -> Optional[str]:
        """
        Получает лучшую доступную модель (наименее загруженную).
        
        Args:
            task_format: Формат задачи (OCR, Layout, Text). Если None - выбирается любая модель.
        
        Returns:
            str: ID модели или None, если нет доступных моделей
        """
        available_models = self.get_available_models()
        if not available_models:
            return None
        
        # Фильтруем модели по формату задачи, если указан
        if task_format:
            task_format_upper = task_format.upper()
            available_models = [
                model_id for model_id in available_models
                if self.model_configs[model_id].task_format.upper() == task_format_upper
            ]
            if not available_models:
                return None
        
        # Выбираем модель с наименьшей очередью и не занятую
        best_model = None
        best_score = float('inf')
        
        for model_id in available_models:
            state = self.model_states[model_id]
            queue_size = self.task_queues[model_id].qsize()
            
            # Приоритет: не занятая модель с меньшей очередью
            score = queue_size
            if state.is_busy:
                score += 1000  # Штраф за занятую модель
            
            if score < best_score:
                best_score = score
                best_model = model_id
        
        return best_model
    
    def submit_task(
        self,
        image: Image.Image,
        model_id: Optional[str] = None,
        task_format: Optional[str] = None,
        prompt_mode: str = "prompt_layout_only_en",
        metadata: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[OCRTask], None]] = None,
        task_id: Optional[str] = None
    ) -> str:
        """
        Добавляет задачу в очередь на обработку.
        
        Args:
            image: Изображение для обработки
            model_id: ID модели для обработки (если None - выбирается автоматически)
            task_format: Формат задачи (OCR, Layout, Text). Используется для фильтрации моделей при автовыборе.
            prompt_mode: Режим промпта
            metadata: Дополнительные метаданные
            callback: Функция обратного вызова, вызываемая после завершения задачи
            task_id: ID задачи (если None - генерируется автоматически)
            
        Returns:
            str: ID задачи
            
        Raises:
            RuntimeError: Если очередь переполнена или модель не найдена
        """
        if not self.model_configs:
            raise RuntimeError("Модели не загружены. Вызовите load_models_from_env() или установите auto_load_models=True")
        
        # Выбираем модель, если не указана
        if model_id is None:
            model_id = self.get_best_model(task_format=task_format)
            if model_id is None:
                format_msg = f" с форматом {task_format}" if task_format else ""
                raise RuntimeError(f"Нет доступных моделей{format_msg}")
        
        # Проверяем соответствие формата задачи модели, если указан
        if task_format and model_id in self.model_configs:
            model_format = self.model_configs[model_id].task_format.upper()
            task_format_upper = task_format.upper()
            if model_format != task_format_upper:
                print(f"Предупреждение: Модель {model_id} имеет формат {model_format}, а задача требует {task_format_upper}")
        
        if model_id not in self.model_configs:
            raise ValueError(f"Модель {model_id} не найдена")
        
        task_queue = self.task_queues[model_id]
        if task_queue.full():
            raise RuntimeError(f"Очередь модели {model_id} переполнена (максимум {self.max_queue_size} задач)")
        
        task = OCRTask(
            task_id=task_id or str(uuid.uuid4()),
            image=image,
            model_id=model_id,
            prompt_mode=prompt_mode,
            metadata=metadata or {},
            callback=callback
        )
        
        self.tasks[task.task_id] = task
        task_queue.put(task)
        
        return task.task_id
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        Получает статус задачи.
        
        Args:
            task_id: ID задачи
            
        Returns:
            TaskStatus или None, если задача не найдена
        """
        task = self.tasks.get(task_id)
        if task is None:
            return None
        return task.status
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает результат задачи.
        
        Args:
            task_id: ID задачи
            
        Returns:
            Dict с результатом или None, если задача не найдена или еще не завершена
        """
        task = self.tasks.get(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.COMPLETED:
            return None
        return task.result
    
    def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> OCRTask:
        """
        Ожидает завершения задачи.
        
        Args:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах (None - без таймаута)
            
        Returns:
            OCRTask: Завершенная задача
            
        Raises:
            TimeoutError: Если задача не завершилась за указанное время
            ValueError: Если задача не найдена
        """
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError(f"Задача {task_id} не найдена")
        
        start_time = time.time()
        while task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            if timeout is not None and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Задача {task_id} не завершилась за {timeout} секунд")
            time.sleep(0.1)
        
        return task
    
    def get_model_state(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Получает состояние модели(ей).
        
        Args:
            model_id: ID модели (если None - возвращает состояние всех моделей)
            
        Returns:
            Dict с информацией о состоянии модели(ей)
        """
        if model_id is not None:
            state = self.model_states.get(model_id)
            if state is None:
                return {}
            
            with self._model_locks[model_id]:
                return {
                    "model_id": model_id,
                    "is_available": state.is_available,
                    "is_busy": state.is_busy,
                    "current_task_id": state.current_task_id,
                    "base_url": state.config.base_url,
                    "model_name": state.config.model_name,
                    "task_format": state.config.task_format,
                    "total_tasks_processed": state.total_tasks_processed,
                    "total_errors": state.total_errors,
                    "queue_size": self.task_queues[model_id].qsize(),
                    "last_used_at": state.last_used_at,
                }
        else:
            # Возвращаем состояние всех моделей
            result = {}
            for mid in self.model_configs.keys():
                result[mid] = self.get_model_state(mid)
            return result
    
    def clear_completed_tasks(self) -> int:
        """
        Очищает завершенные задачи из памяти.
        
        Returns:
            int: Количество удаленных задач
        """
        completed_task_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        ]
        
        for task_id in completed_task_ids:
            del self.tasks[task_id]
        
        return len(completed_task_ids)
    
    def __enter__(self) -> DotsOCRManager:
        """Поддержка контекстного менеджера."""
        if not self.model_configs and self.auto_load_models:
            self.load_models_from_env()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Очистка при выходе из контекстного менеджера."""
        self._stop_workers()
