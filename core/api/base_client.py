import asyncio
import json
import random
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Dict, List, Literal, Optional, Tuple, Union

import aiohttp
import pycountry
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
    DEFAULT_TIMEOUT: Tuple[float, float] = (10.0, 15.0)
    DEFAULT_RETRY_DELAY: float = 3.0
    DEFAULT_MAX_RETRIES: int = 3
    COOKIE_CLEANUP_PROBABILITY: float = 0.1
    COOKIE_MAX_AGE: int = 3600
    DELAY_MEAN: float = 1.5
    DELAY_STD: float = 0.5
    SESSION_LIFETIME_VARIANCE: Tuple[float, float] = (0.8, 1.2)


class ProxyLocale:
    """Utility for managing proxy locales with multilingual support."""
    DEFAULT_LOCALE = "en-US,en;q=0.9"
    FALLBACK_LANGUAGE = "en;q=0.8"
    MULTILINGUAL_COUNTRIES = {
        "CA": [("en", 0.9), ("fr", 0.8)],
        "CH": [("de", 0.9), ("fr", 0.8), ("it", 0.7), ("rm", 0.6)],
        "BE": [("nl", 0.9), ("fr", 0.8), ("de", 0.7)],
        "LU": [("lb", 0.9), ("fr", 0.8), ("de", 0.7)],
    }

    @classmethod
    @lru_cache(maxsize=128)
    def _generate_locale(cls, country: str) -> str:
        """Generate a locale string based on a country code."""
        if not isinstance(country, str) or len(country) != 2 or not country.isalpha():
            return cls.DEFAULT_LOCALE

        country_upper = country.upper()
        if not pycountry.countries.get(alpha_2=country_upper):
            return cls.DEFAULT_LOCALE

        if country_upper in cls.MULTILINGUAL_COUNTRIES:
            languages = cls.MULTILINGUAL_COUNTRIES[country_upper]
            return ",".join(f"{lang}-{country_upper};q={q:.1f}" for lang, q in languages) + f",{cls.FALLBACK_LANGUAGE}"

        country_lower = country_upper.lower()
        return f"{country_lower}-{country_upper},{cls.FALLBACK_LANGUAGE}"

    @classmethod
    async def get_country_from_ip(cls, ip: str) -> str:
        """Get the country code from an IP address."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://ipinfo.io/{ip}/json") as response:
                data = await response.json()
                return data.get("country", "US")

    @classmethod
    async def get_locale_for_proxy(cls, proxy: Optional[Proxy]) -> str:
        """Retrieve locale for a proxy based on its IP address."""
        if not proxy:
            return cls.DEFAULT_LOCALE
        proxy_ip = proxy.host
        country_code = await cls.get_country_from_ip(proxy_ip)
        return cls._generate_locale(country_code)


class BrowserProfile:
    """Browser profile management for HTTP requests."""
    CHROME_VERSIONS = [
        ChromeVersion("chrome119", 5, "119.0.0.0"),
        ChromeVersion("chrome120", 10, "120.0.0.0"),
        ChromeVersion("chrome123", 15, "123.0.0.0"),
        ChromeVersion("chrome124", 20, "124.0.0.0"),
    ]

    @classmethod
    @lru_cache(maxsize=1)
    def get_random_chrome_version(cls) -> ChromeVersion:
        """Select a random Chrome version based on weighted probabilities."""
        return random.choices(cls.CHROME_VERSIONS, weights=[v.weight for v in cls.CHROME_VERSIONS])[0]


class BaseAPIClient:
    """Base class for interacting with APIs using asynchronous HTTP requests."""

    def __init__(
        self,
        base_url: str,
        proxy: Optional[Proxy] = None,
        session_lifetime: int = 5,
        enable_random_delays: bool = True
    ):
        """Initialize the API client."""
        self.base_url = base_url.rstrip('/')
        self.proxy = proxy
        self.session_lifetime = session_lifetime
        self.enable_random_delays = enable_random_delays
        self.config = APIConfig()
        self.requests_count = 0
        self.last_url: Optional[str] = None
        self.session_start_time: Optional[float] = None
        self.session: Optional[AsyncSession] = None
        self._session_lock = asyncio.Lock()
        self._closed = False

    async def initialize(self) -> None:
        """Initialize a new HTTP session."""
        if self._closed:
            self._closed = False
        self.session = await self._create_session()

    async def close(self) -> None:
        """Close the current HTTP session."""
        async with self._session_lock:
            if self.session and not self._closed:
                try:
                    await self.session.close()
                    log.debug("Session closed successfully")
                except Exception as e:
                    log.warning(f"Error closing session: {e}")
                finally:
                    self._closed = True
                    self.session = None
                    self.requests_count = 0
                    self.session_start_time = None

    async def __aenter__(self) -> 'BaseAPIClient':
        """Async context manager entry point."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit point."""
        await self.close()

    async def _ensure_session(self) -> None:
        """Ensure a valid session exists."""
        if self.session is None or self._closed:
            log.debug("Session is None or closed, initializing new session")
            await self.initialize()
        else:
            log.debug("Session is valid, reusing")

    async def _handle_curl_error(self, error: Exception) -> bool:
        """Handle curl-related or network errors."""
        error_str = str(error).lower()
        session_reset_errors = [
            "curlm already closed", "curl error", "connection", "timeout",
            "reset by peer", "eof", "broken pipe", "shutdown", "certificate", "handshake"
        ]
        if any(err in error_str for err in session_reset_errors):
            log.warning(f"Detected connection error: {error_str}. Restarting session.")
            await self.close()
            await asyncio.sleep(1.5)
            await self.initialize()
            return True
        return False

    async def _get_session_headers(self, chrome_version: ChromeVersion) -> Dict[str, str]:
        """Generate HTTP headers for the session."""
        locale = await ProxyLocale.get_locale_for_proxy(self.proxy)
        version = chrome_version.ua_version
        chrome_major = version.split(".", 1)[0]
        return {
            "accept-language": locale,
            "user-agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36",
            "sec-ch-ua": f'"Chromium";v="{chrome_major}", "Google Chrome";v="{chrome_major}", "Not=A?Brand";v="99"',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-mobile": "?0"
        }

    async def _create_session(self) -> AsyncSession:
        """Create a new HTTP session with configured headers and proxy."""
        chrome_version = BrowserProfile.get_random_chrome_version()
        session = AsyncSession(
            impersonate=chrome_version.version,
            verify=False,
            timeout=random.uniform(*self.config.DEFAULT_TIMEOUT)
        )
        session.headers.update(await self._get_session_headers(chrome_version))
        if self.proxy:
            proxy_url = self.proxy.as_url
            session.proxies.update({"http": proxy_url, "https": proxy_url})
        self.session_start_time = time.time()
        return session

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

    async def _add_random_delay(self) -> None:
        """Add a random delay if enabled."""
        if self.enable_random_delays:
            delay = abs(random.gauss(self.config.DELAY_MEAN, self.config.DELAY_STD))
            log.debug(f"Adding random delay of {delay:.2f}s")
            await asyncio.sleep(min(delay, 1.0))

    async def _maybe_rotate_session(self) -> None:
        """Rotate the session if request count exceeds a randomized threshold."""
        log.debug(f"Current request count: {self.requests_count}")
        self.requests_count += 1
        threshold = self.session_lifetime * random.uniform(*self.config.SESSION_LIFETIME_VARIANCE)
        log.debug(f"Checking if rotation needed: {self.requests_count} >= {threshold:.2f}")
        
        if self.requests_count >= threshold:
            log.debug("Rotating session: closing current session")
            try:
                await asyncio.wait_for(self.close(), timeout=5.0)
            except asyncio.TimeoutError:
                log.error("Session close timed out after 5s, forcing cleanup")
                self.session = None
                self._closed = True
            except Exception as e:
                log.error(f"Error closing session during rotation: {e}")
                self.session = None
                self._closed = True
            
            log.debug("Rotating session: initializing new session")
            try:
                await asyncio.wait_for(self.initialize(), timeout=10.0)
                self.requests_count = 0
                log.debug("Session rotated successfully")
            except asyncio.TimeoutError:
                log.error("Session initialization timed out after 10s")
                raise ServerError("Failed to initialize new session during rotation due to timeout")
            except Exception as e:
                log.error(f"Error initializing new session during rotation: {e}")
                raise ServerError(f"Failed to initialize new session: {str(e)}")
        else:
            log.debug("No session rotation needed")

    async def _make_request(self, request_type: RequestType, url: str, headers: Dict[str, str], **kwargs) -> Response:
        """Execute an HTTP request of the specified type."""
        log.debug(f"Making {request_type.value} request to {url}")
        timeout = random.uniform(*self.config.DEFAULT_TIMEOUT)
        request_method = {
            RequestType.POST: self.session.post,
            RequestType.GET: self.session.get,
            RequestType.PATCH: self.session.patch,
            RequestType.OPTIONS: self.session.options
        }[request_type]
        try:
            response = await asyncio.wait_for(request_method(url, headers=headers, **kwargs), timeout=timeout)
            log.debug(f"Request to {url} succeeded with status {response.status_code}")
            return response
        except asyncio.TimeoutError:
            log.error(f"Request to {url} timed out after {timeout:.2f} seconds")
            raise

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
        custom_timeout: Optional[float] = None
    ) -> Response:
        """Send an HTTP request with retry logic and error handling."""
        log.debug("Entering send_request")
        async with self._session_lock:
            log.debug("Acquired session lock")
            await self._ensure_session()
            log.debug("Session ensured")

            request_url = url or f"{self.base_url}/{method.lstrip('/')}" if method else self.base_url
            request_type = RequestType(request_type)
            
            log.debug("Rotating session if needed")
            await self._maybe_rotate_session()
            log.debug("Adding random delay")
            await self._add_random_delay()
            log.debug("Delay completed")

            base_timeout = custom_timeout or (
                self.config.DEFAULT_TIMEOUT[1] + 5
                if (method and any(kw in method for kw in ["auth", "users", "socials", "stats"]))
                else self.config.DEFAULT_TIMEOUT[1]
            )

            request_headers = dict(self.session.headers)
            if headers:
                request_headers.update(headers)
                if "referer" not in headers and self.last_url and not request_url.startswith(self.last_url):
                    request_headers["referer"] = self.last_url

            kwargs = {"params": params, "cookies": cookies, "allow_redirects": allow_redirects}
            if json_data and request_type != RequestType.GET:
                kwargs["json"] = json_data
            if data and request_type != RequestType.GET:
                kwargs["data"] = data

            for attempt in range(max_retries):
                adaptive_timeout = min(base_timeout * (1 + attempt * 0.2), 15.0)
                log.debug(f"Request to {request_url} (attempt {attempt+1}/{max_retries}) with timeout {adaptive_timeout:.2f}s")
                
                try:
                    log.debug(f"Starting request execution for {request_url}")
                    response = await asyncio.wait_for(
                        self._make_request(request_type, request_url, request_headers, **kwargs),
                        timeout=adaptive_timeout
                    )
                    log.debug(f"Request completed successfully for {request_url} with status {response.status_code}")
                    
                    
                    if response.status_code == 429:
                        retry_after = float(response.headers.get('Retry-After', retry_delay * 2))
                        log.warning(f"Rate limited (429) on attempt {attempt+1}/{max_retries}: {request_url}, waiting {retry_after:.2f}s")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    await self._manage_cookies(response)
                    self.last_url = request_url
                    
                    if 'application/json' in response.headers.get('Content-Type', '',):
                        response_data = response.json()
                        await self._verify_response(response_data)
                    
                    log.debug(f"Request to {request_url} succeeded on attempt {attempt+1}/{max_retries}")
                    return response
                    
                except asyncio.TimeoutError as e:
                    log.error(f"Timeout on attempt {attempt+1}/{max_retries}: {request_url} - Timeout: {adaptive_timeout:.2f}s")
                    await self.close()
                    await asyncio.sleep(1.0)
                    await self.initialize()
                    if attempt == max_retries - 1:
                        raise ServerError(f"Request to {request_url} timed out after {max_retries} attempts") from e
                except Exception as e:
                    if await self._handle_curl_error(e):
                        continue
                    if attempt == max_retries - 1:
                        error_msg = f"Failed after {max_retries} attempts"
                        if e:
                            error_msg += f". Last error: {str(e)}"
                        log.error(error_msg)
                        raise ServerError(error_msg) from e

                backoff = retry_delay * (2 ** attempt) * (0.8 + random.random() * 0.4)
                log.debug(f"Waiting {backoff:.2f}s before retry...")
                await asyncio.sleep(backoff)

    @staticmethod
    def _verify_response_status(response: Response) -> None:
        """Verify the HTTP response status code."""
        status = response.status_code
        if status == 403:
            raise SessionRateLimited(f"Session is rate-limited (HTTP 403). URL: {response.url}")
        if status in (500, 502, 503, 504):
            raise ServerError(f"Server error - {status}")

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