import asyncio
import random
import json
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
    """Chrome version details with randomization weights.

    Attributes:
        version (str): Chrome version identifier for impersonation.
        weight (int): Weight for random selection probability.
        ua_version (str): Version string used in User-Agent header.
    """
    version: str
    weight: int
    ua_version: str


@dataclass
class APIConfig:
    """Configuration settings for the API client.

    Attributes:
        DEFAULT_TIMEOUT (Tuple[float, float]): Min and max timeout range in seconds (default: 25.0, 35.0).
        DEFAULT_RETRY_DELAY (float): Base delay between retries in seconds (default: 3.0).
        DEFAULT_MAX_RETRIES (int): Maximum retry attempts (default: 3).
        COOKIE_CLEANUP_PROBABILITY (float): Chance to clean expired cookies (default: 0.1).
        COOKIE_MAX_AGE (int): Maximum cookie age in seconds (default: 3600).
        DELAY_MEAN (float): Mean delay for random delays in seconds (default: 1.5).
        DELAY_STD (float): Standard deviation for random delays (default: 0.5).
        SESSION_LIFETIME_VARIANCE (Tuple[float, float]): Variance range for session lifetime (default: 0.8, 1.2).
    """
    DEFAULT_TIMEOUT: Tuple[float, float] = (25.0, 35.0)
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

    MULTILINGUAL_COUNTRIES: Dict[str, List[Tuple[str, float]]] = {
        'CA': [('en', 0.9), ('fr', 0.8)],
        'CH': [('de', 0.9), ('fr', 0.8), ('it', 0.7), ('rm', 0.6)],
        'BE': [('nl', 0.9), ('fr', 0.8), ('de', 0.7)],
        'LU': [('lb', 0.9), ('fr', 0.8), ('de', 0.7)],
    }

    @classmethod
    @lru_cache(maxsize=128)
    def _generate_locale(cls, country: str) -> str:
        """Generate a locale string based on a country code.

        Args:
            country (str): Two-letter ISO 3166-1 alpha-2 country code.

        Returns:
            str: A locale string (e.g., "en-US,en;q=0.8") or default if invalid.
        """
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
        """Get the country from an IP address."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://ipinfo.io/{ip}/json") as response:
                data: Dict = await response.json()
                return data.get("country", "US")
            
    @classmethod
    async def get_locale_for_proxy(cls, proxy: Optional[Proxy]) -> str:
        """Retrieve the locale for a given proxy based on its IP address.

        Args:
            proxy (Optional[Proxy]): Proxy object with IP address.

        Returns:
            str: Locale string tailored to the proxy's country or default locale.
        """
        if not proxy:
            return cls.DEFAULT_LOCALE
        
        proxy_ip = proxy.host
        country_code = await cls.get_country_from_ip(proxy_ip)
        return cls._generate_locale(country_code)

class BrowserProfile:
    """Browser profile management for HTTP requests."""
    
    CHROME_VERSIONS: List[ChromeVersion] = [
        ChromeVersion("chrome119", 5, "119.0.0.0"),
        ChromeVersion("chrome120", 10, "120.0.0.0"),
        ChromeVersion("chrome123", 15, "123.0.0.0"),
        ChromeVersion("chrome124", 20, "124.0.0.0"),
    ]

    @classmethod
    @lru_cache(maxsize=1)
    def get_random_chrome_version(cls) -> ChromeVersion:
        """Select a random Chrome version based on weighted probabilities.

        Returns:
            ChromeVersion: A randomly chosen Chrome version object.
        """
        return random.choices(cls.CHROME_VERSIONS, weights=[v.weight for v in cls.CHROME_VERSIONS], k=1)[0]


class BaseAPIClient:
    """Base class for interacting with APIs using asynchronous HTTP requests.

    Args:
        base_url (str): Base URL for API requests.
        proxy (Optional[Proxy]): Proxy configuration for requests (default: None).
        session_lifetime (int): Number of requests before session rotation (default: 5).
        enable_random_delays (bool): Whether to add random delays between requests (default: True).
    """
    
    def __init__(
        self,
        base_url: str,
        proxy: Optional[Proxy] = None,
        session_lifetime: int = 5,
        enable_random_delays: bool = True
    ):
        self.base_url = base_url.rstrip('/')
        self.proxy = proxy
        self.session_lifetime = session_lifetime
        self.enable_random_delays = enable_random_delays
        self.config = APIConfig()
        self.requests_count = 0
        self.last_url: Optional[str] = None
        self.session_start_time: Optional[float] = None
        self.session = None
        self._session_lock = asyncio.Lock()
        self._closed = False
        
    async def initialize(self):
        """Initialize the session."""
        if self._closed:
            self._closed = False
        self.session = await self._create_session()

    async def close(self):
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

    async def __aenter__(self):
        """Async context manager enter."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self):
        if self.session is None or self._closed:
            log.debug("Session is None or closed, initializing new session")
            await self.initialize()
        else:
            log.debug("Session is valid, reusing")

    async def _handle_curl_error(self, error: Exception) -> bool:
        """Обработка ошибок, связанных с cURL и сетевыми сбоями.
        
        Returns:
            bool: True, если ошибка была обработана и запрос следует повторить
        """
        error_str = str(error).lower()
        
        session_reset_errors = [
            "curlm already closed", 
            "curl error", 
            "connection",
            "timeout", 
            "reset by peer",
            "eof",
            "broken pipe",
            "shutdown",
            "certificate",
            "handshake"
        ]
        
        if any(err in error_str for err in session_reset_errors):
            log.warning(f"Detected connection error: {error_str}. Restarting session.")
            await self.close()
            await asyncio.sleep(1.5)
            await self.initialize()
            return True
            
        return False

    async def _get_session_headers(self, chrome_version: ChromeVersion) -> Dict[str, str]:
        """Generate session headers based on Chrome version and proxy locale.

        Args:
            chrome_version (ChromeVersion): Chrome version details.

        Returns:
            Dict[str, str]: HTTP headers for the session.
        """
        locale = await ProxyLocale.get_locale_for_proxy(self.proxy)
        version = chrome_version.ua_version
        chrome_major = version.split(".", 1)[0]
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"

        return {
            "accept-language": locale,
            "user-agent": ua,
            "sec-ch-ua": f'"Chromium";v="{chrome_major}", "Google Chrome";v="{chrome_major}", "Not=A?Brand";v="99"',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-mobile": "?0"
        }

    async def _create_session(self) -> AsyncSession:
        """Create a new HTTP session with configured headers and proxy.

        Returns:
            AsyncSession: A new asynchronous session object.
        """
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
        """Manage session cookies, cleaning up expired ones probabilistically.

        Args:
            response (Response): HTTP response containing cookies.
        """
        if not response.cookies or random.random() >= self.config.COOKIE_CLEANUP_PROBABILITY:
            return

        current_time = time.time()
        for key in [k for k, v in self.session.cookies.items() if current_time - self.session_start_time > self.config.COOKIE_MAX_AGE]:
            del self.session.cookies[key]
        self.session.cookies.update(response.cookies)

    async def _add_random_delay(self) -> None:
        if self.enable_random_delays:
            delay = abs(random.gauss(self.config.DELAY_MEAN, self.config.DELAY_STD))
            log.debug(f"Adding random delay of {delay:.2f}s")
            await asyncio.sleep(min(delay, 1.0))

    async def _maybe_rotate_session(self) -> None:
        """Rotate the session if the request count exceeds a randomized lifetime."""
        self.requests_count += 1
        if self.requests_count >= self.session_lifetime * random.uniform(*self.config.SESSION_LIFETIME_VARIANCE):
            await self.close()
            await self.initialize()
            self.requests_count = 0

    async def _make_request(self, request_type: RequestType, url: str, headers: Dict[str, str], **kwargs) -> Response:
        """Execute an HTTP request of the specified type.

        Args:
            request_type (RequestType): Type of HTTP request (e.g., POST, GET).
            url (str): Target URL for the request.
            headers (Dict[str, str]): Request headers.
            **kwargs: Additional arguments for the request method.

        Returns:
            Response: HTTP response object.
        """
        log.debug(f"Making {request_type.value} request to {url}")
        timeout = random.uniform(*self.config.DEFAULT_TIMEOUT)
        request_method = {
            RequestType.POST: self.session.post,
            RequestType.GET: self.session.get,
            RequestType.PATCH: self.session.patch,
            RequestType.OPTIONS: self.session.options
        }[request_type]
        try:
            response = await asyncio.wait_for(
                request_method(url, headers=headers, **kwargs),
                timeout=timeout
            )
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
        """
        Send a request with extended error handling and adaptive timeouts.
        
        Args:
            custom_timeout: User-defined timeout for heavy requests
        """
        async with self._session_lock:
            await self._ensure_session()
            
            request_url = url or f"{self.base_url}/{method.lstrip('/')}" if method else self.base_url
            request_type = RequestType(request_type)
            await self._maybe_rotate_session()
            await self._add_random_delay()

            is_stats_request = method and "stats" in method
            is_heavy_request = method and any(keyword in method for keyword in ["auth", "users", "socials"])
            
            base_timeout = custom_timeout or (
                self.config.DEFAULT_TIMEOUT[1] + 15 if is_stats_request else
                self.config.DEFAULT_TIMEOUT[1] + 10 if is_heavy_request else
                self.config.DEFAULT_TIMEOUT[1] + 5
            )

            request_headers = dict(self.session.headers)
            if headers:
                request_headers.update(headers)
                if "referer" not in headers and self.last_url and not request_url.startswith(self.last_url):
                    request_headers["referer"] = self.last_url

            kwargs = {"params": params, "cookies": cookies, "allow_redirects": allow_redirects}
            if json_data and request_type != RequestType.GET:
                kwargs["json"] = json_data

            last_error = None
            for attempt in range(max_retries):
                adaptive_timeout = base_timeout * (1 + attempt * 0.2)
                
                log.debug(f"Request to {request_url} (attempt {attempt+1}/{max_retries}) with timeout {adaptive_timeout:.2f}s")
                
                try:
                    response = await asyncio.wait_for(
                        self._make_request(request_type, request_url, request_headers, **kwargs),
                        timeout=adaptive_timeout
                    )
                    
                    if response.status_code == 429:
                        retry_after = response.headers.get('Retry-After', retry_delay * 2)
                        retry_after = float(retry_after) if isinstance(retry_after, str) and retry_after.isdigit() else retry_delay * 2
                        log.warning(f"Rate limited (attempt {attempt+1}/{max_retries}): {request_url}, waiting {retry_after:.2f}s")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    await self._manage_cookies(response)
                    self.last_url = request_url
                    
                    if verify:
                        try:
                            self._verify_response_status(response)
                        except (SessionRateLimited, ServerError) as e:
                            last_error = e
                            log.warning(f"Response status error (attempt {attempt+1}/{max_retries}): {str(e)}")
                            
                            if isinstance(e, SessionRateLimited):
                                await self.close()
                                await asyncio.sleep(retry_delay * 2)
                                await self.initialize()
                            elif isinstance(e, ServerError) and attempt < max_retries - 1:
                                backoff = retry_delay * (2 ** attempt) * (0.8 + random.random() * 0.4)
                                log.info(f"Server error, waiting {backoff:.2f}s before retry...")
                                await asyncio.sleep(backoff)
                            continue
                    
                    if 'application/json' in response.headers.get('Content-Type', ''):
                        try:
                            response_data = response.json()
                            await self._verify_response(response_data)
                        except json.JSONDecodeError:
                            log.warning(f"Invalid JSON in response (attempt {attempt+1}/{max_retries})")
                            if attempt == max_retries - 1:
                                log.error(f"Failed to parse JSON response after {max_retries} attempts")
                                raise
                            continue
                        except APIError as e:
                            last_error = e
                            log.warning(f"API error in response (attempt {attempt+1}/{max_retries}): {str(e)}")
                            if attempt == max_retries - 1:
                                raise
                            await asyncio.sleep(retry_delay)
                            continue
                            
                    return response
                    
                except asyncio.TimeoutError as e:
                    last_error = e
                    log.warning(f"Request timed out (attempt {attempt+1}/{max_retries}): {request_url} - Timeout: {adaptive_timeout:.2f}s")
                    
                    await self.close()
                    await asyncio.sleep(1.5)    
                    await self.initialize()
                    
                except aiohttp.ClientError as e:
                    last_error = e
                    log.warning(f"HTTP client error (attempt {attempt+1}/{max_retries}): {str(e)}")
                    await self._handle_curl_error(e)
                    
                except Exception as error:
                    last_error = error
                    log.warning(f"Request error (attempt {attempt+1}/{max_retries}): {str(error)}")
                    
                    if await self._handle_curl_error(error):
                        continue
                        
                    if "certificate" in str(error).lower():
                        log.warning("SSL certificate error detected, continuing anyway")
                        continue
                        
                    if attempt == max_retries - 1:
                        raise

                backoff = retry_delay * (2 ** attempt) * (0.8 + random.random() * 0.4)
                log.info(f"Waiting {backoff:.2f}s before retry...")
                await asyncio.sleep(backoff)

            error_msg = f"Failed after {max_retries} attempts"
            if last_error:
                error_msg += f". Last error: {str(last_error)}"
            raise ServerError(error_msg)
    
    @staticmethod
    def _verify_response_status(response: Response) -> None:
        """Verify the HTTP response status code.

        Args:
            response (Response): HTTP response to check.

        Raises:
            SessionRateLimited: If status is 403.
            ServerError: If status is 500, 502, 503, or 504.
        """
        status = response.status_code
        if status == 403:
            raise SessionRateLimited("Session is rate-limited")
        if status in (500, 502, 503, 504):
            raise ServerError(f"Server error - {status}")

    @staticmethod
    async def _verify_response(response_data: Union[Dict, List]) -> None:
        """Check the API response data for errors.

        Args:
            response_data (Union[Dict, List]): Parsed response data.

        Raises:
            APIError: If the response contains an error indicator.
        """
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