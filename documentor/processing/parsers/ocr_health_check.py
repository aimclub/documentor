"""OCR services health check utility."""

import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from ...core.logging import get_logger

logger = get_logger(__name__)


class OCRHealthChecker:
    """
    Health checker for OCR services (Dots.OCR and Qwen2.5-VL).
    
    Checks if OCR services are available and responding correctly.
    """
    
    def __init__(self, dots_ocr_url: str, dots_ocr_api_key: str, 
                 qwen_url: str, qwen_api_key: str, timeout: int = 5):
        """
        Initialize OCR health checker.
        
        Args:
            dots_ocr_url: Dots.OCR API URL
            dots_ocr_api_key: Dots.OCR API key
            qwen_url: Qwen API URL
            qwen_api_key: Qwen API key
            timeout: Request timeout in seconds
        """
        self.dots_ocr_url = dots_ocr_url.rstrip('/')
        self.dots_ocr_api_key = dots_ocr_api_key
        self.qwen_url = qwen_url.rstrip('/')
        self.qwen_api_key = qwen_api_key
        self.timeout = timeout
        
        # Results cache
        self._last_check_time = 0
        self._cache_duration = 60  # Cache results for 60 seconds
        self._cached_results = None
    
    async def check_dots_ocr(self) -> Tuple[bool, str]:
        """
        Check Dots.OCR service availability.
        
        Returns:
            Tuple[bool, str]: (is_available, status_message)
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                # Try to get models list
                headers = {
                    'Authorization': f'Bearer {self.dots_ocr_api_key}',
                    'Content-Type': 'application/json'
                }
                
                async with session.get(f"{self.dots_ocr_url}/models", headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get('data', [])
                        if models:
                            return True, f"Dots.OCR available (models: {len(models)})"
                        else:
                            return True, "Dots.OCR available (no models found)"
                    else:
                        return False, f"Dots.OCR unavailable (HTTP {response.status})"
                        
        except asyncio.TimeoutError:
            return False, "Dots.OCR unavailable (timeout)"
        except aiohttp.ClientError as e:
            return False, f"Dots.OCR unavailable (connection error: {e})"
        except Exception as e:
            return False, f"Dots.OCR unavailable (error: {e})"
    
    async def check_qwen(self) -> Tuple[bool, str]:
        """
        Check Qwen2.5-VL service availability.
        
        Returns:
            Tuple[bool, str]: (is_available, status_message)
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                # Try to get models list
                headers = {
                    'Authorization': f'Bearer {self.qwen_api_key}',
                    'Content-Type': 'application/json'
                }
                
                async with session.get(f"{self.qwen_url}/models", headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get('data', [])
                        if models:
                            return True, f"Qwen2.5-VL available (models: {len(models)})"
                        else:
                            return True, "Qwen2.5-VL available (no models found)"
                    else:
                        return False, f"Qwen2.5-VL unavailable (HTTP {response.status})"
                        
        except asyncio.TimeoutError:
            return False, "Qwen2.5-VL unavailable (timeout)"
        except aiohttp.ClientError as e:
            return False, f"Qwen2.5-VL unavailable (connection error: {e})"
        except Exception as e:
            return False, f"Qwen2.5-VL unavailable (error: {e})"
    
    async def check_all_services(self) -> Dict[str, Any]:
        """
        Check all OCR services availability.
        
        Returns:
            Dict[str, Any]: Health check results
        """
        # Check cache first
        current_time = time.time()
        if (self._cached_results and 
            current_time - self._last_check_time < self._cache_duration):
            return self._cached_results
        
        logger.info("Checking OCR services availability...")
        
        # Check both services concurrently
        dots_ocr_task = asyncio.create_task(self.check_dots_ocr())
        qwen_task = asyncio.create_task(self.check_qwen())
        
        dots_ocr_available, dots_ocr_message = await dots_ocr_task
        qwen_available, qwen_message = await qwen_task
        
        results = {
            'dots_ocr': {
                'available': dots_ocr_available,
                'message': dots_ocr_message,
                'url': self.dots_ocr_url
            },
            'qwen': {
                'available': qwen_available,
                'message': qwen_message,
                'url': self.qwen_url
            },
            'overall_available': dots_ocr_available and qwen_available,
            'check_time': current_time
        }
        
        # Cache results
        self._cached_results = results
        self._last_check_time = current_time
        
        return results
    
    def check_all_services_sync(self) -> Dict[str, Any]:
        """
        Synchronous wrapper for checking all OCR services.
        
        Returns:
            Dict[str, Any]: Health check results
        """
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.check_all_services())
                    return future.result()
            else:
                return loop.run_until_complete(self.check_all_services())
        except RuntimeError:
            # No event loop, create new one
            return asyncio.run(self.check_all_services())


def check_ocr_services_from_env() -> Dict[str, Any]:
    """
    Check OCR services using environment variables.
    
    Returns:
        Dict[str, Any]: Health check results
    """
    import os
    
    # Get configuration from environment
    dots_ocr_url = os.getenv('DOTS_OCR_BASE_URL', '')
    dots_ocr_api_key = os.getenv('DOTS_OCR_API_KEY', '')
    qwen_url = os.getenv('QWEN_BASE_URL', '')
    qwen_api_key = os.getenv('QWEN_API_KEY', '')
    
    # Check if configuration is provided
    if not all([dots_ocr_url, dots_ocr_api_key, qwen_url, qwen_api_key]):
        return {
            'dots_ocr': {
                'available': False,
                'message': 'Dots.OCR not configured (missing environment variables)',
                'url': dots_ocr_url or 'not specified'
            },
            'qwen': {
                'available': False,
                'message': 'Qwen2.5-VL not configured (missing environment variables)',
                'url': qwen_url or 'not specified'
            },
            'overall_available': False,
            'check_time': time.time()
        }
    
    # Create checker and run health check
    checker = OCRHealthChecker(
        dots_ocr_url=dots_ocr_url,
        dots_ocr_api_key=dots_ocr_api_key,
        qwen_url=qwen_url,
        qwen_api_key=qwen_api_key,
        timeout=5
    )
    
    return checker.check_all_services_sync()


# Global checker instance
_health_checker: Optional[OCRHealthChecker] = None


def get_ocr_health_checker() -> Optional[OCRHealthChecker]:
    """Get global OCR health checker instance."""
    return _health_checker


def initialize_ocr_health_checker(dots_ocr_url: str, dots_ocr_api_key: str,
                                 qwen_url: str, qwen_api_key: str) -> OCRHealthChecker:
    """
    Initialize global OCR health checker.
    
    Args:
        dots_ocr_url: Dots.OCR API URL
        dots_ocr_api_key: Dots.OCR API key
        qwen_url: Qwen API URL
        qwen_api_key: Qwen API key
        
    Returns:
        OCRHealthChecker: Initialized checker
    """
    global _health_checker
    _health_checker = OCRHealthChecker(
        dots_ocr_url=dots_ocr_url,
        dots_ocr_api_key=dots_ocr_api_key,
        qwen_url=qwen_url,
        qwen_api_key=qwen_api_key
    )
    return _health_checker
