import asyncio
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Literal, Optional, Union

from better_proxy import Proxy
from curl_cffi.requests import AsyncSession, Response

from core.exceptions.base import APIError, ServerError, SessionRateLimited
from logger import log


class RequestType(Enum):
    """Enum representing supported HTTP request types."""
    POST = "POST"
    GET = "GET"
    OPTIONS = "OPTIONS"
    PATCH = "PATCH"


@dataclass
class ChromeVersion:
    """Chrome version details with randomization weights."""
    version: str
    weight: int
    ua_version: str


@dataclass
class APIConfig:
    """Configuration settings for the API client."""
    DEFAULT_TIMEOUT: float = 30.0
    DEFAULT_RETRY_DELAY: float = 1.0
    DEFAULT_MAX_RETRIES: int = 3
    COOKIE_CLEANUP_PROBABILITY: float = 0.1
    COOKIE_MAX_AGE: int = 3600


class BrowserProfile:
    """Browser profile management for HTTP requests."""
    CHROME_VERSIONS = [
        ChromeVersion("chrome124", 20, "124.0.0.0"),
    ]

    @classmethod
    def get_random_chrome_version(cls) -> ChromeVersion:
        """Select the latest Chrome version for consistency."""
        return cls.CHROME_VERSIONS[0]


class BaseAPIClient:
    """Optimized and reliable API client for asynchronous HTTP requests."""

    def __init__(
        self,
        base_url: str,
        proxy: Optional[Proxy] = None,
        session_lifetime: int = 10
    ):
        """Initialize the API client."""
        self.base_url = base_url.rstrip('/')
        self.proxy = proxy
        self.session_lifetime = session_lifetime
        self.config = APIConfig()
        self.requests_count = 0
        self.last_url: Optional[str] = None
        self.session_start_time: Optional[float] = None
        self.session: Optional[AsyncSession] = None
        self._closed = False

    async def initialize(self) -> None:
        """Initialize a new HTTP session quickly."""
        try:
            self.session = await asyncio.wait_for(self._create_session(), timeout=5.0)
            self.session_start_time = time.time()
            self.requests_count = 0
            self._closed = False
            log.debug("Session initialized")
        except Exception as e:
            log.error(f"Failed to initialize session: {e}")
            raise ServerError(f"Session initialization failed: {e}")

    async def close(self) -> None:
        """Close the current HTTP session efficiently."""
        if self.session and not self._closed:
            try:
                await asyncio.wait_for(self.session.close(), timeout=3.0)
            except Exception as e:
                log.warning(f"Error closing session: {e}")
            finally:
                self.session = None
                self._closed = True
                self.requests_count = 0
                self.session_start_time = None

    async def _create_session(self) -> AsyncSession:
        """Create a new HTTP session with minimal overhead."""
        chrome_version = BrowserProfile.get_random_chrome_version()
        session = AsyncSession(
            impersonate=chrome_version.version,
            verify=False,
            timeout=self.config.DEFAULT_TIMEOUT
        )
        session.headers.update({
            "accept-language": "en-US,en;q=0.9",
            "user-agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version.ua_version} Safari/537.36",
            "sec-ch-ua": f'"Chromium";v="{chrome_version.ua_version.split(".")[0]}", "Google Chrome";v="{chrome_version.ua_version.split(".")[0]}", "Not=A?Brand";v="99"',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-mobile": "?0"
        })
        if self.proxy:
            proxy_url = self.proxy.as_url
            session.proxies = {"http": proxy_url, "https": proxy_url}
        return session

    async def _rotate_session(self) -> None:
        """Rotate session if needed with minimal delay."""
        self.requests_count += 1
        if self.requests_count >= self.session_lifetime:
            await self.close()
            await self.initialize()

    async def _manage_cookies(self, response: Response) -> None:
        """Manage session cookies, cleaning up expired ones probabilistically."""
        if not response.cookies or random.random() >= self.config.COOKIE_CLEANUP_PROBABILITY:
            return
        current_time = time.time()
        expired_keys = [
            key for key, _ in self.session.cookies.items()
            if current_time - self.session_start_time > self.config.COOKIE_MAX_AGE
        ]
        for key in expired_keys:
            del self.session.cookies[key]
        self.session.cookies.update(response.cookies)

    async def send_request(
        self,
        request_type: Literal["POST", "GET", "OPTIONS", "PATCH"] = "POST",
        method: Optional[str] = None,
        json_data: Optional[Dict] = None,
        data: Optional[str] = None,
        params: Optional[Dict] = None,
        url: Optional[str] = None,
        headers: Optional[Dict] = None,
        cookies: Optional[Dict] = None,
        verify: bool = True,
        max_retries: int = APIConfig.DEFAULT_MAX_RETRIES,
        retry_delay: float = APIConfig.DEFAULT_RETRY_DELAY,
        allow_redirects: bool = False,
        custom_timeout: Optional[float] = None,
        raw_request: bool = False,
        ignore_errors: bool = False,
        user_agent: Optional[str] = None
    ) -> Response:
        """Send an HTTP request with full parameter support and optimized retry logic."""
        if not self.session or self._closed:
            await self.initialize()

        request_url = url or f"{self.base_url}/{method.lstrip('/')}" if method else self.base_url
        request_type = RequestType(request_type)
        request_headers = dict(self.session.headers)
        if user_agent:
            request_headers["user-agent"] = user_agent
        if headers:
            request_headers.update(headers)
            if "referer" not in headers and self.last_url and not request_url.startswith(self.last_url):
                request_headers["referer"] = self.last_url

        kwargs = {"params": params, "cookies": cookies, "allow_redirects": allow_redirects}
        if json_data and request_type != RequestType.GET:
            kwargs["json"] = json_data
        if data and request_type != RequestType.GET:
            kwargs["data"] = data

        request_method = {
            RequestType.POST: self.session.post,
            RequestType.GET: self.session.get,
            RequestType.PATCH: self.session.patch,
            RequestType.OPTIONS: self.session.options
        }[request_type]

        for attempt in range(max_retries):
            timeout = custom_timeout or self.config.DEFAULT_TIMEOUT
            try:
                response = await asyncio.wait_for(
                    request_method(request_url, headers=request_headers, **kwargs),
                    timeout=timeout
                )
                if response.status_code == 429:
                    retry_after = float(response.headers.get('Retry-After', retry_delay))
                    log.warning(f"Rate limited (429), retrying after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                
                if raw_request:
                    return response
                
                await self._manage_cookies(response)
                self.last_url = request_url
                
                if verify and not ignore_errors:
                    self._verify_response_status(response)
                    if 'application/json' in response.headers.get('Content-Type', ''):
                        response_data = response.json()
                        await self._verify_response(response_data)
                
                return response

            except asyncio.TimeoutError as e:
                log.error(f"Timeout on attempt {attempt + 1}/{max_retries} after {timeout}s")
                await self.close()
                await self._rotate_session()
                if attempt == max_retries - 1:
                    raise ServerError(f"Request timed out after {max_retries} attempts") from e
                await asyncio.sleep(retry_delay)

            except Exception as e:
                log.error(f"Error on attempt {attempt + 1}/{max_retries}: {e}")
                await self.close()
                await self._rotate_session()
                if attempt == max_retries - 1:
                    raise ServerError(f"Request failed after {max_retries} attempts: {e}")
                await asyncio.sleep(retry_delay)

    @staticmethod
    def _verify_response_status(response: Response) -> None:
        """Verify the HTTP response status code."""
        status = response.status_code
        if status == 403:
            raise SessionRateLimited(f"Session is rate-limited (HTTP 403). URL: {response.url}")
        if status in (500, 502, 503, 504):
            raise ServerError(f"Server error - {status}")
        if status >= 400:
            raise ServerError(f"HTTP error: {status}")

    @staticmethod
    async def _verify_response(response_data: Union[Dict, List]) -> None:
        """Check the API response data for errors."""
        if not isinstance(response_data, dict):
            return
            
        error_checks = [
            ("status", lambda x: x is False or str(x).lower() == "failed"),
            ("success", lambda x: x is False),
            ("error", lambda x: x is not None and x),
            ("errors", lambda x: x and len(x) > 0),
            ("statusCode", lambda x: isinstance(x, int) and x not in (200, 201, 202, 204)),
            ("code", lambda x: isinstance(x, int) and x >= 400)
        ]
        
        for key, check in error_checks:
            if key in response_data and check(response_data[key]):
                error_details = response_data.get("message", "")
                if not error_details and isinstance(response_data.get("errors"), list):
                    error_details = ", ".join(str(e) for e in response_data["errors"])
                raise APIError(f"API error: {error_details or response_data}", response_data)

    async def __aenter__(self) -> 'BaseAPIClient':
        """Async context manager entry point."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit point."""
        await self.close()