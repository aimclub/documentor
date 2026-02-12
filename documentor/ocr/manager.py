"""
Manager for managing Dots OCR via vLLM API.

Manages:
- Recognition task queues for each model
- Model state (available/busy)
- Sending images for processing via API
- Receiving responses
- Worker pool for parallel processing
- Loading configuration from .env file
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
import yaml

from .dots_ocr import get_system_prompt, load_prompts_from_config
from ..core.load_env import load_env_file

# Cache for OCR config
_ocr_config_cache: Optional[dict] = None


def _load_ocr_config() -> dict:
    """Loads OCR configuration from ocr_config.yaml."""
    global _ocr_config_cache
    if _ocr_config_cache is not None:
        return _ocr_config_cache
    
    config_path = Path(__file__).parent.parent / "config" / "ocr_config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                _ocr_config_cache = config or {}
                return _ocr_config_cache
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to load OCR config from {config_path}: {e}")
            _ocr_config_cache = {}
            return _ocr_config_cache
    else:
        _ocr_config_cache = {}
        return _ocr_config_cache


def _get_config_value(key_path: str, env_var: Optional[str] = None, default: Optional[Any] = None) -> Any:
    """
    Gets configuration value with priority: config file → env var → default.
    
    Args:
        key_path: Dot-separated path in config (e.g., "dots_ocr.recognition.timeout")
        env_var: Environment variable name (optional)
        default: Default value if not found
    
    Returns:
        Configuration value
    """
    config = _load_ocr_config()
    
    # Try config file first
    keys = key_path.split(".")
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
            break
        if value is None:
            break
    
    if value is not None:
        return value
    
    # Fallback to environment variable
    if env_var:
        env_value = os.getenv(env_var)
        if env_value is not None:
            try:
                # Try to convert to appropriate type
                if isinstance(default, int):
                    return int(env_value)
                elif isinstance(default, float):
                    return float(env_value)
                elif isinstance(default, bool):
                    return env_value.lower() in ("true", "1", "yes", "on")
                return env_value
            except (ValueError, TypeError):
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to convert env var {env_var}={env_value} to {type(default).__name__}")
    
    # Return default
    return default


class TaskStatus(str, Enum):
    """Recognition task status."""
    PENDING = "pending"  # In queue
    PROCESSING = "processing"  # Processing
    COMPLETED = "completed"  # Completed successfully
    FAILED = "failed"  # Completed with error
    CANCELLED = "cancelled"  # Cancelled


@dataclass
class OCRTask:
    """Image recognition task."""
    task_id: str
    image: Image.Image
    model_id: str  # Model ID for processing
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
        """Initialize task."""
        if not self.task_id:
            self.task_id = str(uuid.uuid4())


@dataclass
class ModelConfig:
    """Model configuration."""
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
    """Model state."""
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
    Manager for managing Dots OCR via vLLM API.
    
    Manages task queues for each model, model state and image processing.
    Supports multiple models from .env file.
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
        Initialize manager.
        
        Args:
            max_queue_size: Maximum task queue size for each model
            num_workers_per_model: Number of workers per model
            auto_load_models: Automatically load models on initialization
            env_file: Path to .env file (if None - searches automatically)
            config_path: Path to configuration file with prompts
        """
        self.max_queue_size = max_queue_size
        self.num_workers_per_model = num_workers_per_model
        self.auto_load_models = auto_load_models
        self.env_file = env_file
        self.config_path = config_path
        
        # Model configurations (model_id -> ModelConfig)
        self.model_configs: Dict[str, ModelConfig] = {}
        
        # Model states (model_id -> ModelState)
        self.model_states: Dict[str, ModelState] = {}
        
        # Task queues for each model (model_id -> Queue)
        self.task_queues: Dict[str, Queue[OCRTask]] = {}
        
        # All tasks (task_id -> OCRTask)
        self.tasks: Dict[str, OCRTask] = {}
        
        # Worker threads (model_id -> List[Thread])
        self.worker_threads: Dict[str, List[threading.Thread]] = {}
        self._stop_workers = False
        self._workers_lock = threading.Lock()
        
        # Locks for model state access
        self._model_locks: Dict[str, threading.Lock] = {}
        
        # Load prompts
        self.prompts = load_prompts_from_config(config_path)
        
        # Load model configurations from .env
        if auto_load_models:
            self.load_models_from_env()
    
    def load_models_from_env(self) -> None:
        """
        Loads model configurations from .env file.
        
        Raises:
            RuntimeError: If models could not be loaded
        """
        # Load .env file
        load_env_file(self.env_file)
        
        # Get model URLs (can be multiple via comma or newline)
        dots_base_url_raw = os.getenv("DOTS_OCR_BASE_URL", "")
        
        if not dots_base_url_raw:
            raise RuntimeError("DOTS_OCR_BASE_URL not found in environment variables")
        
        # Process multiple URLs
        urls = []
        for line in dots_base_url_raw.split('\n'):
            for url in line.split(','):
                url = self._clean_url(url.strip())
                if url and url not in urls:
                    urls.append(url)
        
        if not urls:
            raise RuntimeError("No valid DOTS_OCR_BASE_URL found")
        
        # Get common parameters
        # Secret parameters: only from env
        api_key = os.getenv("DOTS_OCR_API_KEY", "")
        
        # Non-secret parameters: from config → env → default
        model_name = _get_config_value(
            "dots_ocr.model",
            "DOTS_OCR_MODEL_NAME",
            "/model"
        )
        temperature = _get_config_value(
            "dots_ocr.recognition.temperature",
            "DOTS_OCR_TEMPERATURE",
            0.1
        )
        max_tokens = _get_config_value(
            "dots_ocr.recognition.max_tokens",
            "DOTS_OCR_MAX_TOKENS",
            4096
        )
        timeout = _get_config_value(
            "dots_ocr.recognition.timeout",
            "DOTS_OCR_TIMEOUT",
            60
        )
        
        # Get task_format for each model (can be multiple via comma)
        task_formats_raw = os.getenv("DOTS_OCR_TASK_FORMAT", "")
        task_formats = []
        if task_formats_raw:
            for line in task_formats_raw.split('\n'):
                for fmt in line.split(','):
                    fmt = fmt.strip()
                    if fmt and fmt.upper() in ["OCR", "LAYOUT", "TEXT"]:
                        task_formats.append(fmt.upper())
        
        # If formats not specified, use default "Layout" for all models
        if not task_formats:
            task_formats = ["Layout"] * len(urls)
        elif len(task_formats) < len(urls):
            # If fewer formats than URLs, repeat last one
            task_formats.extend([task_formats[-1]] * (len(urls) - len(task_formats)))
        elif len(task_formats) > len(urls):
            # If more formats than URLs, truncate
            task_formats = task_formats[:len(urls)]
        
        if not api_key:
            raise RuntimeError("DOTS_OCR_API_KEY not found in environment variables")
        
        # Create configuration for each model
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
            
            # Create model state
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
            
            print(f"Model {model_id} loaded: {base_url} (format: {task_format})")
        
        print(f"Loaded {len(self.model_configs)} models")
        
        # Start workers for each model
        self._start_workers()
    
    def _clean_url(self, url: str) -> str:
        """Cleans URL from comments and spaces."""
        if '#' in url:
            url = url.split('#')[0]
        return url.strip()
    
    def _start_workers(self) -> None:
        """Starts workers for all models."""
        with self._workers_lock:
            if self._stop_workers:
                return
            
            for model_id in self.model_configs.keys():
                if model_id in self.worker_threads:
                    continue  # Workers already started
                
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
                print(f"Started {self.num_workers_per_model} workers for model {model_id}")
    
    def _stop_workers(self) -> None:
        """Stops all workers."""
        with self._workers_lock:
            self._stop_workers = True
            
            for model_id, threads in self.worker_threads.items():
                for worker in threads:
                    worker.join(timeout=5.0)
            
            self.worker_threads.clear()
            print("All workers stopped")
    
    def _worker_loop(self, model_id: str) -> None:
        """Main worker loop for processing tasks for specific model."""
        task_queue = self.task_queues.get(model_id)
        if task_queue is None:
            return
        
        while not self._stop_workers:
            try:
                # Get task from queue (with timeout)
                try:
                    task = task_queue.get(timeout=1.0)
                except Empty:
                    continue
                
                # Check that task is intended for this model
                if task.model_id != model_id:
                    # Return task to correct queue
                    correct_queue = self.task_queues.get(task.model_id)
                    if correct_queue:
                        correct_queue.put(task)
                    continue
                
                # Process task
                self._process_task(task, model_id)
                
                # Mark task as done
                task_queue.task_done()
                
            except Exception as e:
                print(f"Error in worker {model_id}: {e}")
                import traceback
                traceback.print_exc()
    
    def _process_task(self, task: OCRTask, model_id: str) -> None:
        """
        Processes recognition task.
        
        Args:
            task: Recognition task
            model_id: Model ID for processing
        """
        model_state = self.model_states.get(model_id)
        if model_state is None:
            task.status = TaskStatus.FAILED
            task.error = f"Model {model_id} not found"
            task.completed_at = time.time()
            return
        
        with self._model_locks[model_id]:
            if not model_state.is_available:
                task.status = TaskStatus.FAILED
                task.error = f"Model {model_id} unavailable"
                task.completed_at = time.time()
                return
            
            if model_state.is_busy:
                # If model is busy, return task to queue
                self.task_queues[model_id].put(task)
                return
            
            # Mark model as busy
            model_state.is_busy = True
            model_state.current_task_id = task.task_id
        
        try:
            task.status = TaskStatus.PROCESSING
            task.started_at = time.time()
            
            # Get prompt
            prompt = self.prompts.get(task.prompt_mode, self.prompts.get("prompt_layout_only_en", ""))
            
            # Process image via API
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
            
            # Call callback if exists
            if task.callback:
                try:
                    task.callback(task)
                except Exception as e:
                    print(f"Error in callback for task {task.task_id}: {e}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            model_state.total_errors += 1
            print(f"Error processing task {task.task_id}: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            with self._model_locks[model_id]:
                model_state.is_busy = False
                model_state.current_task_id = None
    
    def _image_to_base64(self, image: Image.Image) -> str:
        """Converts PIL image to base64 string."""
        if hasattr(image, 'format') and image.format:
            format_type = image.format.upper()
        else:
            format_type = 'PNG'
        
        # Normalize format for correct MIME type
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
        """Reduces image size if it's too large."""
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
        Detects page layout using API.
        
        Args:
            image: PIL page image
            prompt: Text prompt
            model_state: Model state
            metadata: Additional metadata
            
        Returns:
            Dict with layout detection results
        """
        if model_state.client is None:
            raise RuntimeError("API client not initialized")
        
        # Resize image if needed
        processed_image = self._resize_image_if_needed(image, max_size=2048)
        width, height = processed_image.size
        
        # Get system prompt
        system_prompt = get_system_prompt(width, height)
        
        # Convert image to base64
        image_base64 = self._image_to_base64(processed_image)
        
        # Create messages in OpenAI API format
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
        
        # Send request to API
        response = model_state.client.chat.completions.create(
            model=model_state.config.model_name,
            messages=messages,
            max_tokens=model_state.config.max_tokens,
            temperature=model_state.config.temperature
        )
        
        content = response.choices[0].message.content
        
        # Parse response
        result = self._parse_layout_response(content)
        
        return result
    
    def _parse_layout_response(self, content: str) -> Dict[str, Any]:
        """
        Parses JSON from model text response.
        
        Args:
            content: Model text response
            
        Returns:
            Dict with parsed JSON
        """
        # Try to find JSON object or array in text
        text = content.strip()
        
        # Find first { or [
        start_idx = -1
        for i, char in enumerate(text):
            if char in ['{', '[']:
                start_idx = i
                break
        
        if start_idx == -1:
            raise ValueError(f"JSON not found in response: {text[:200]}")
        
        # Find last } or ]
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
            raise ValueError(f"JSON end not found in response: {text[:200]}")
        
        json_str = text[start_idx:end_idx]
        
        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parsing error: {e}. Text: {json_str[:200]}")
    
    def get_available_models(self, task_format: Optional[str] = None) -> List[str]:
        """
        Gets list of available models.
        
        Args:
            task_format: Task format (OCR, Layout, Text). If None - returns all available models.
        
        Returns:
            List[str]: List of model IDs
        """
        models = [
            model_id for model_id, state in self.model_states.items()
            if state.is_available
        ]
        
        # Filter by task format if specified
        if task_format:
            task_format_upper = task_format.upper()
            models = [
                model_id for model_id in models
                if self.model_configs[model_id].task_format.upper() == task_format_upper
            ]
        
        return models
    
    def get_best_model(self, task_format: Optional[str] = None) -> Optional[str]:
        """
        Gets best available model (least loaded).
        
        Args:
            task_format: Task format (OCR, Layout, Text). If None - any model is selected.
        
        Returns:
            str: Model ID or None if no available models
        """
        available_models = self.get_available_models()
        if not available_models:
            return None
        
        # Filter models by task format if specified
        if task_format:
            task_format_upper = task_format.upper()
            available_models = [
                model_id for model_id in available_models
                if self.model_configs[model_id].task_format.upper() == task_format_upper
            ]
            if not available_models:
                return None
        
        # Select model with smallest queue and not busy
        best_model = None
        best_score = float('inf')
        
        for model_id in available_models:
            state = self.model_states[model_id]
            queue_size = self.task_queues[model_id].qsize()
            
            # Priority: not busy model with smaller queue
            score = queue_size
            if state.is_busy:
                score += 1000  # Penalty for busy model
            
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
        Adds task to processing queue.
        
        Args:
            image: Image for processing
            model_id: Model ID for processing (if None - selected automatically)
            task_format: Task format (OCR, Layout, Text). Used for filtering models during auto-selection.
            prompt_mode: Prompt mode
            metadata: Additional metadata
            callback: Callback function called after task completion
            task_id: Task ID (if None - generated automatically)
            
        Returns:
            str: Task ID
            
        Raises:
            RuntimeError: If queue is full or model not found
        """
        if not self.model_configs:
            raise RuntimeError("Models not loaded. Call load_models_from_env() or set auto_load_models=True")
        
        # Select model if not specified
        if model_id is None:
            model_id = self.get_best_model(task_format=task_format)
            if model_id is None:
                format_msg = f" with format {task_format}" if task_format else ""
                raise RuntimeError(f"No available models{format_msg}")
        
        # Check task format match with model if specified
        if task_format and model_id in self.model_configs:
            model_format = self.model_configs[model_id].task_format.upper()
            task_format_upper = task_format.upper()
            if model_format != task_format_upper:
                print(f"Warning: Model {model_id} has format {model_format}, but task requires {task_format_upper}")
        
        if model_id not in self.model_configs:
            raise ValueError(f"Model {model_id} not found")
        
        task_queue = self.task_queues[model_id]
        if task_queue.full():
            raise RuntimeError(f"Model {model_id} queue is full (maximum {self.max_queue_size} tasks)")
        
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
        Gets task status.
        
        Args:
            task_id: Task ID
            
        Returns:
            TaskStatus or None if task not found
        """
        task = self.tasks.get(task_id)
        if task is None:
            return None
        return task.status
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Gets task result.
        
        Args:
            task_id: Task ID
            
        Returns:
            Dict with result or None if task not found or not completed yet
        """
        task = self.tasks.get(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.COMPLETED:
            return None
        return task.result
    
    def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> OCRTask:
        """
        Waits for task completion.
        
        Args:
            task_id: Task ID
            timeout: Wait timeout in seconds (None - no timeout)
            
        Returns:
            OCRTask: Completed task
            
        Raises:
            TimeoutError: If task did not complete within specified time
            ValueError: If task not found
        """
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        
        start_time = time.time()
        while task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            if timeout is not None and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")
            time.sleep(0.1)
        
        return task
    
    def get_model_state(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Gets model state(s).
        
        Args:
            model_id: Model ID (if None - returns state of all models)
            
        Returns:
            Dict with model state information
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
            # Return state of all models
            result = {}
            for mid in self.model_configs.keys():
                result[mid] = self.get_model_state(mid)
            return result
    
    def clear_completed_tasks(self) -> int:
        """
        Clears completed tasks from memory.
        
        Returns:
            int: Number of removed tasks
        """
        completed_task_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        ]
        
        for task_id in completed_task_ids:
            del self.tasks[task_id]
        
        return len(completed_task_ids)
    
    def __enter__(self) -> DotsOCRManager:
        """Context manager support."""
        if not self.model_configs and self.auto_load_models:
            self.load_models_from_env()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup on context manager exit."""
        self._stop_workers()
