import asyncio
import random
import orjson
import certifi
import ssl as ssl_module
from types import TracebackType
from typing import Literal, Any, Self, Type

import aiohttp
import ua_generator
from yarl import URL
from better_proxy import Proxy

from src.exceptions.api_exceptions import (
    APIClientError, APIConnectionError, APITimeoutError, 
    APIRateLimitError, APIResponseError, APIClientSideError, 
    APIServerSideError, APISessionError, APISSLError
)


class BaseAPIClient:
    RETRYABLE_ERRORS = (
        APIServerSideError,
        APIRateLimitError,
        APITimeoutError,
        aiohttp.ClientError, 
        asyncio.TimeoutError,
        aiohttp.ClientSSLError,
        APIResponseError
    )
    
    def __init__(
        self, 
        base_url: str, 
        proxy: Proxy | None = None
    ) -> None:
        self.base_url: str = base_url
        self.proxy: Proxy | None = proxy
        self.session: aiohttp.ClientSession | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._session_active: bool = False
        self._headers: dict[str, str | bool | list[str]] = self._generate_headers()
        self._ssl_context = ssl_module.create_default_context(cafile=certifi.where())
        self._connector: aiohttp.TCPConnector = self._create_connector()
        
    @staticmethod
    def _generate_headers() -> dict[str, str | bool | list[str]]:
        user_agent = ua_generator.generate(
            device='desktop', 
            platform='windows', 
            browser='chrome'
        )
        
        return {
            'accept-language': 'en-US;q=0.9,en;q=0.8',
            'sec-ch-ua': user_agent.ch.brands,
            'sec-ch-ua-mobile': user_agent.ch.mobile,
            'sec-ch-ua-platform': user_agent.ch.platform,
            'user-agent': user_agent.text
        }
    
    def _create_connector(self) -> aiohttp.TCPConnector:
        return aiohttp.TCPConnector(
            enable_cleanup_closed=True,
            force_close=False,
            ssl=self._ssl_context,
            limit=10
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            if self._connector is None or self._connector.closed:
                self._connector = self._create_connector()
            self.session = aiohttp.ClientSession(
                connector=self._connector,
                headers=self._headers
            )
        return self.session

    async def _check_session_valid(self) -> bool:
        if self.session is None or self.session.closed:
            return False
        return True

    async def _safely_close_resource(self, resource: Any, resource_name: str) -> None:
        if resource and hasattr(resource, 'closed') and not resource.closed:
            try:
                await resource.close()
                await asyncio.sleep(0.1)
            except Exception:
                pass

    async def __aenter__(self) -> Self:
        if not self._session_active:
            self.session = await self._get_session()
            self._session_active = True
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None
    ) -> None:
        await self.close()

    async def send_request(
        self,
        request_type: Literal["POST", "GET", "PUT", "OPTIONS"] = "POST",
        method: str | None = None,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        verify: bool = True,
        allow_redirects: bool = True,
        ssl: bool | ssl_module.SSLContext = True,
        max_retries: int = 3,
        retry_delay: tuple[float, float] = (1.5, 5.0),
        user_agent: str | None = None,
        timeout: float = 30.0
    ) -> dict[str, Any] | str:
        
        if not url and not method:
            raise APIClientError("Either url or method must be provided")
        
        if url:
            try:
                parsed_url = URL(url)
                if parsed_url.scheme == 'https' and parsed_url.port == 80:
                    parsed_url = parsed_url.with_port(443)
                elif parsed_url.scheme == 'http' and parsed_url.port == 443:
                    parsed_url = parsed_url.with_port(80)
                target_url = str(parsed_url)
            except:
                target_url = url
        else:
            base = URL(self.base_url)
            method_path = method.lstrip('/') if method else ''
            target_url = str(base / method_path)
            
        custom_headers = dict(headers) if headers else {}
        if user_agent:
            custom_headers['user-agent'] = user_agent
            
        ssl_param = self._ssl_context if verify else False
        if isinstance(ssl, ssl_module.SSLContext):
            ssl_param = ssl

        for attempt in range(1, max_retries + 1):
            try:
                session = await self._get_session()
                
                if not await self._check_session_valid():
                    session = await self._get_session()
                
                merged_headers = dict(session.headers)
                if custom_headers:
                    merged_headers.update(custom_headers)
        
                try:
                    async with session.request(
                        method=request_type,
                        url=target_url,
                        json=json_data,
                        data=data,
                        params=params,
                        headers=merged_headers,
                        cookies=cookies,
                        proxy=self.proxy.as_url if self.proxy else None,
                        ssl=ssl_param,
                        allow_redirects=allow_redirects,
                        raise_for_status=False,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        content_type = response.headers.get('Content-Type', '').lower()
                        status_code = response.status
                        
                        text = await response.text()
                        result = {
                            "status_code": status_code,
                            "url": str(response.url),
                            "text": text,
                            "data": None
                        }
                        
                        try:
                            if text and ('application/json' in content_type or 'json' in content_type or text.strip().startswith('{')):
                                result["data"] = orjson.loads(text)
                        except orjson.JSONDecodeError:
                            pass
                            
                        if verify:
                            if status_code == 429:
                                raise APIRateLimitError(f"Too many requests: {status_code}")
                            elif 400 <= status_code < 500:
                                raise APIClientSideError(f"Client error: {status_code}", status_code, result)
                            elif status_code >= 500:
                                raise APIServerSideError(f"Server error: {status_code}", status_code, result)
                        
                        return result
                    
                except asyncio.TimeoutError as e:
                    if attempt < max_retries:
                        delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                        await asyncio.sleep(delay)
                        continue
                    raise APITimeoutError(f"Request timed out after {timeout} seconds")
                
                except aiohttp.ServerTimeoutError as e:
                    if attempt < max_retries:
                        delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                        await asyncio.sleep(delay)
                        continue
                    raise APITimeoutError(f"Server timeout error: {e}")
                        
                except aiohttp.ClientSSLError as ssl_error:
                    await self.reset_session()
                    if attempt < max_retries:
                        delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                        await asyncio.sleep(delay)
                        continue
                    raise APISSLError(f"SSL Error: {ssl_error}")
                        
                except RuntimeError as re:
                    if "Session is closed" in str(re):
                        if self.session and not self.session.closed:
                            await self._safely_close_resource(self.session, "Session")
                        self.session = None
                        
                        if attempt < max_retries:
                            delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                            await asyncio.sleep(delay)
                            continue
                    raise APISessionError(f"Session error: {re}")
                    
                except aiohttp.ClientConnectorError as e:
                    raise APIConnectionError(f"Connection error: {e}")

            except (aiohttp.ClientOSError, aiohttp.ServerDisconnectedError, RuntimeError) as e:
                error_msg = str(e)
                is_session_closed = isinstance(e, RuntimeError) and "Session is closed" in error_msg
                
                if self.session and not self.session.closed:
                    await self._safely_close_resource(self.session, "Session")
                self.session = None
                
                if attempt < max_retries:
                    delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    await asyncio.sleep(delay)
                    continue
                
                if is_session_closed:
                    raise APISessionError(f"Session closed: {e}")
                else:
                    raise APIConnectionError(f"Connection disrupted: {e}")

            except self.RETRYABLE_ERRORS as error:
                if isinstance(error, APIClientSideError):
                    raise
                
                if attempt < max_retries:
                    delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    await asyncio.sleep(delay)
                    continue
                
                if isinstance(error, APIRateLimitError):
                    raise
                
                raise APIServerSideError(
                    f"The request failed after {max_retries} attempts to {target_url}",
                    None,
                    {"error": str(error)}
                )
                    
            except Exception as error:
                if attempt < max_retries:
                    delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    
                    if self.session and not self.session.closed:
                        await self._safely_close_resource(self.session, "Session")
                        self.session = None
                        
                    await asyncio.sleep(delay)
                    continue
                
                raise APIClientError(f"Unexpected error when querying to {target_url}: {type(error).__name__}: {error}")

            except asyncio.TimeoutError:
                if attempt < max_retries:
                    delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    await asyncio.sleep(delay)
                    continue
                raise APITimeoutError(f"Operation timed out after {timeout} seconds")

        raise APIServerSideError(f"Unreachable code: all {max_retries} attempts have been exhausted")

    async def close(self) -> None:
        try:
            if hasattr(self, 'session') and self.session:
                await self._safely_close_resource(self.session, "Session")
                self.session = None
            
            if hasattr(self, '_connector') and self._connector:
                await self._safely_close_resource(self._connector, "Connector")
                self._connector = None
            
            self._session_active = False
        except Exception as e:
            self.session = None
            self._connector = None
            self._session_active = False
            raise APIClientError(f"Error during API client cleanup: {str(e)}")

    async def reset_session(self) -> None:
        if hasattr(self, 'session') and self.session:
            await self._safely_close_resource(self.session, "Session")
            self.session = None
            self._session_active = False