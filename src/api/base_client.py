import asyncio
import random
import orjson
import ssl as ssl_module
from types import TracebackType
from typing import Literal, Any, Self, Type

import aiohttp
import ua_generator
from yarl import URL
from better_proxy import Proxy

from src.exceptions.custom_exceptions import APIError, ServerError, SessionRateLimited
from src.logger import AsyncLogger


class HttpStatusError(APIError):
    def __init__(self, message: str, status_code: int, response_data: Any = None) -> None:
        super().__init__(message, response_data)
        self.status_code: int = status_code
        

class BaseAPIClient(AsyncLogger):
    RETRYABLE_ERRORS = (
        ServerError, 
        SessionRateLimited,
        aiohttp.ClientError, 
        asyncio.TimeoutError,
        HttpStatusError
    )
    
    def __init__(
        self, 
        base_url: str, 
        proxy: Proxy | None = None
    ) -> None:
        super().__init__()
        self.base_url: str = base_url
        self.proxy: Proxy | None = proxy
        self.session: aiohttp.ClientSession | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._session_active: bool = False
        self._headers: dict[str, str | bool | list[str]] = self._generate_headers()
        self._ssl_context: ssl_module.SSLContext = ssl_module.create_default_context()
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
        async with self._lock:
            if self.session is None or self.session.closed:
                await self.logger_msg(
                    msg="Creating new session", 
                    type_msg="debug", 
                    method_name="_get_session"
                )
                self.session = aiohttp.ClientSession(
                    connector=self._connector,
                    timeout=aiohttp.ClientTimeout(total=120),
                    headers=self._headers
                )
            return self.session

    async def _check_session_valid(self) -> bool:
        if self.session is None or self.session.closed:
            return False
        return True

    async def _safely_close_session(self, session: aiohttp.ClientSession) -> None:
        if session and not session.closed:
            try:
                await session.close()
                await asyncio.sleep(0.25)
            except Exception as e:
                await self.logger_msg(
                    msg=f"Error closing session: {type(e).__name__}: {e}", 
                    type_msg="warning", 
                    method_name="_safely_close_session"
                )

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
        if self.session and not self.session.closed:
            await self._safely_close_session(self.session)
            self.session = None
            self._session_active = False
        
        if self._connector and not self._connector.closed:
            await self._connector.close()
            
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
        user_agent: str | None = None
    ) -> dict[str, Any] | str:
        
        if not url and not method:
            error_msg = "Either url or method must be provided"
            await self.logger_msg(
                msg=error_msg, 
                type_msg="error", 
                method_name="send_request"
            )
            return {"status_code": 400, "error": error_msg, "data": None, "text": ""}
        
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
            
        ssl_param = True
        if isinstance(ssl, bool):
            ssl_param = self._ssl_context if ssl else False
        elif isinstance(ssl, ssl_module.SSLContext):
            ssl_param = ssl

        for attempt in range(1, max_retries + 1):
            try:
                session = await self._get_session()
                
                if not await self._check_session_valid():
                    await self.logger_msg(
                        msg="Session was closed, recreating...", 
                        type_msg="debug", 
                        method_name="send_request"
                    )
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
                        raise_for_status=False
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
                                raise SessionRateLimited(f"Too many requests: {status_code}", result)
                            elif 400 <= status_code < 500:
                                raise HttpStatusError(f"Client error: {status_code}", status_code, result)
                            elif status_code >= 500:
                                raise ServerError(f"Server error: {status_code}", result)
                        
                        return result
                        
                except RuntimeError as re:
                    if "Session is closed" in str(re):
                        await self.logger_msg(
                            msg="Session is closed, recreating for next attempt", 
                            type_msg="warning", 
                            method_name="send_request"
                        )
                        
                        if self.session and not self.session.closed:
                            await self._safely_close_session(self.session)
                        self.session = None
                        
                        if attempt < max_retries:
                            delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                            await asyncio.sleep(delay)
                            continue
                    raise
                    
                except aiohttp.ClientConnectorError as e:
                    await self.logger_msg(
                        msg=f"Connection error: {e}", 
                        type_msg="error", 
                        method_name="send_request"
                    )
                    raise

            except (aiohttp.ClientOSError, aiohttp.ServerDisconnectedError, RuntimeError) as e:
                error_msg = str(e)
                is_session_closed = isinstance(e, RuntimeError) and "Session is closed" in error_msg
                
                if is_session_closed:
                    await self.logger_msg(
                        msg=f"Session closed error: {e}. Recreating session", 
                        type_msg="warning", 
                        method_name="send_request"
                    )
                else:
                    await self.logger_msg(
                        msg=f"Connection disrupted: {e}. Resetting session", 
                        type_msg="warning", 
                        method_name="send_request"
                    )
                
                if self.session and not self.session.closed:
                    await self._safely_close_session(self.session)
                self.session = None
                
                if attempt < max_retries:
                    delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    await asyncio.sleep(delay)
                    continue
                raise

            except self.RETRYABLE_ERRORS as error:
                if isinstance(error, HttpStatusError) and getattr(error, 'status_code', 0) != 429:
                    raise error
                
                if attempt < max_retries:
                    delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    
                    if isinstance(error, SessionRateLimited):
                        await self.logger_msg(
                            msg=f"Rate limit error. Retry {attempt}/{max_retries} in {delay:.2f} seconds", 
                            type_msg="debug", 
                            method_name="send_request"
                        )
                    else:
                        await self.logger_msg(
                            msg=f"Error {type(error).__name__}: {error}. Retry {attempt}/{max_retries} after {delay:.2f} seconds", 
                            type_msg="debug", 
                            method_name="send_request"
                        )
                    
                    await asyncio.sleep(delay)
                    continue
                
                raise ServerError(
                    f"The request failed after {max_retries} attempts to {target_url}. Error {error}"
                ) from error
                    
            except Exception as error:
                error_msg = f"Unexpected error when querying to {target_url}: {type(error).__name__}: {error}"
                await self.logger_msg(
                    msg=error_msg, 
                    type_msg="error", 
                    method_name="send_request"
                )
                
                if attempt < max_retries:
                    delay = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    
                    if self.session and not self.session.closed:
                        await self._safely_close_session(self.session)
                        self.session = None
                        
                    await asyncio.sleep(delay)
                    continue
                
                return {
                    "status_code": 500, 
                    "error": str(error), 
                    "error_type": type(error).__name__,
                    "data": None, 
                    "text": error_msg
                }

        raise ServerError(f"Unreachable code: all {max_retries} attempts have been exhausted")