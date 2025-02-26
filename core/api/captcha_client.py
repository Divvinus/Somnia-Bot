import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import List, Optional, Tuple

from better_proxy import Proxy

from logger import log
from loader import config
from .base_client import BaseAPIClient


class CaptchaService(Enum):
    """Enum for captcha services"""
    CAPMONSTER = ("https://api.capmonster.cloud", "AntiTurnstileTaskProxyLess")
    TWOCAPTCHA = ("https://api.2captcha.com", "TurnstileTaskProxyless")
    CAPSOLVER = ("https://api.capsolver.com", "AntiTurnstileTaskProxyLess")

    def __init__(self, url: str, task_type: str):
        self.url = url
        self.task_type = task_type


@dataclass
class CaptchaConfig:
    """Configuration for working with captcha"""
    DEFAULT_SLEEP_TIME: int = 2
    ERROR_SLEEP_TIME: int = 5
    MAX_RETRIES: int = 3
    BALANCE_THRESHOLD: float = 0.0

class CapcthaSolutionWorker(BaseAPIClient):
    """Worker for solving captcha"""

    def __init__(self, proxy: Optional[Proxy] = None):
        super().__init__(base_url="", proxy=proxy)
        self.api_key: Optional[str] = None
        self.config = CaptchaConfig()
        self._current_service: Optional[CaptchaService] = None

    def _get_service_by_key(self, api_key: str) -> Optional[CaptchaService]:
        """Determining the service by the API key"""
        if api_key == config.cap_monster:
            return CaptchaService.CAPMONSTER
        elif api_key == config.two_captcha:
            return CaptchaService.TWOCAPTCHA
        elif api_key == config.capsolver:
            return CaptchaService.CAPSOLVER
        return None

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_available_keys() -> List[str]:
        """Getting available API keys with caching"""
        return [key for key in [config.cap_monster, config.two_captcha, config.capsolver] if key]

    async def _check_balance(self, api_key: str) -> bool:
        """Checking the balance of the API key"""
        try:
            service = self._get_service_by_key(api_key)
            if not service:
                return False

            self.base_url = service.url
            response = await self.send_request(
                request_type="POST",
                method="/getBalance",
                json_data={"clientKey": api_key},
                verify=False
            )
            
            if not isinstance(response, (str, bytes)):
                return False

            data = json.loads(response if isinstance(response, str) else response.decode())
            balance = data.get("balance")
            
            return balance is not None and balance > self.config.BALANCE_THRESHOLD

        except Exception as e:
            log.warning(f"Balance check failed for service {service}: {e}")
            return False

    async def _get_working_api_key(self) -> Tuple[bool, str]:
        """Getting a working API key"""
        available_keys = self._get_available_keys()
        if not available_keys:
            return False, "No API keys configured for captcha solving"

        for api_key in available_keys:
            if await self._check_balance(api_key):
                service = self._get_service_by_key(api_key)
                if service:
                    self._current_service = service
                    self.base_url = service.url
                    return True, api_key

        return False, "No API keys with sufficient balance found"

    async def _create_task(self, website_url: str, website_key: str) -> Optional[str]:
        """Creating a task for solving captcha"""
        try:
            if not self._current_service:
                return None

            json_data = {
                "clientKey": self.api_key,
                "task": {
                    "type": self._current_service.task_type,
                    "websiteURL": website_url,
                    "websiteKey": website_key
                }
            }

            response = await self.send_request(
                method="/createTask",
                json_data=json_data,
                verify=False
            )
            
            if not isinstance(response, (str, bytes)):
                return None

            data = json.loads(response if isinstance(response, str) else response.decode())
            return data.get("taskId")

        except Exception as e:
            log.error(f"Task creation failed: {e}")
            return None

    async def _get_solution(self, task_id: str) -> Optional[str]:
        """Getting the solution result"""
        try:
            json_data = {
                "clientKey": self.api_key,
                "taskId": task_id
            }

            response = await self.send_request(
                method="/getTaskResult",
                json_data=json_data
            )

            if not isinstance(response, dict):
                return None

            if response.get("errorId") == 12:
                return None

            if response.get("status") == "ready" and "solution" in response:
                return response["solution"]["token"]

            return None

        except Exception as e:
            log.error(f"Getting solution failed: {e}")
            return None

    async def get_task_result(
        self,
        website_url: str,
        website_key: str,
        start_attempt: int = 0,
        finish_attempt: int = 60
    ) -> Tuple[bool, str]:
        """
        Getting the solution result with retries
        
        Args:
            website_url: URL of the website
            website_key: Captcha key
            start_attempt: Initial attempt
            finish_attempt: Maximum number of attempts
            
        Returns:
            Tuple[bool, str]: (success, result/error message)
        """
        success, result = await self._get_working_api_key()
        if not success:
            return False, result

        self.api_key = result

        for _ in range(self.config.MAX_RETRIES):
            try:
                task_id = await self._create_task(website_url, website_key)
                if not task_id:
                    continue

                for attempt in range(start_attempt, finish_attempt + 1):
                    solution = await self._get_solution(task_id)
                    
                    if solution:
                        return True, solution
                        
                    if attempt < finish_attempt:
                        await asyncio.sleep(self.config.DEFAULT_SLEEP_TIME)

            except Exception as error:
                log.error(f"Captcha solving error: {error}")
                await asyncio.sleep(self.config.ERROR_SLEEP_TIME)

        return False, "Failed to solve captcha after maximum attempts"