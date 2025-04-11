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
            ssl=True
        )

    def _determine_ssl_settings(
        self,
        url: str,
        ssl_param: bool | ssl_module.SSLContext
    ) -> ssl_module.SSLContext | bool:
        parsed_url: URL = URL(url)
        is_https: bool = parsed_url.scheme.lower() == 'https'
        
        if not is_https:
            return False
        
        if isinstance(ssl_param, ssl_module.SSLContext):
            return ssl_param
            
        return self._ssl_context if ssl_param else False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=120),
                headers=self._headers
            )
        return self.session

    async def _reset_session_if_needed(self, skip_header_regeneration: bool = False) -> None:
        async with self._lock:
            await self.logger_msg(
                msg="Starting session reset",
                type_msg="debug",
                method_name="_reset_session_if_needed"
            )

            if self.session is not None:
                if not self.session.closed:
                    await self.logger_msg(
                        msg="Closing existing session",
                        type_msg="debug",
                        method_name="_reset_session_if_needed"
                    )
                    try:
                        await self._safely_close_session(self.session)
                    except Exception as e:
                        await self.logger_msg(
                            msg=f"Failed to close session: {type(e).__name__}: {e}",
                            type_msg="warning",
                            method_name="_reset_session_if_needed"
                        )
                else:
                    await self.logger_msg(
                        msg="Session is already closed",
                        type_msg="debug",
                        method_name="_reset_session_if_needed"
                    )
                self.session = None

            if not skip_header_regeneration:
                try:
                    self._headers = self._generate_headers()
                    await self.logger_msg(
                        msg="Headers regenerated successfully",
                        type_msg="debug",
                        method_name="_reset_session_if_needed"
                    )
                except Exception as e:
                    await self.logger_msg(
                        msg=f"Failed to regenerate headers: {type(e).__name__}: {e}",
                        type_msg="error",
                        method_name="_reset_session_if_needed"
                    )
                    raise RuntimeError("Failed to regenerate headers") from e

            try:
                self.session = aiohttp.ClientSession(
                    connector=self._connector,
                    timeout=aiohttp.ClientTimeout(total=120),
                    headers=self._headers
                )
                await self.logger_msg(
                    msg="New session created successfully",
                    type_msg="debug",
                    method_name="_reset_session_if_needed"
                )
            except Exception as e:
                await self.logger_msg(
                    msg=f"Failed to create new session: {type(e).__name__}: {e}",
                    type_msg="error",
                    method_name="_reset_session_if_needed"
                )
                self.session = None
                raise RuntimeError("Failed to create new session") from e

    async def _safely_close_session(self, session: aiohttp.ClientSession) -> None:
        if session and not session.closed:
            try:
                await session.close()
                await asyncio.sleep(0.25)
            except Exception as e:
                await self.logger_msg(
                    msg=f"Error closing session: {type(e).__name__}: {e}", type_msg="warning", 
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
            raise ValueError("Either url or method must be provided")
        
        if url:
            target_url: str = url
        else:
            base: URL = URL(self.base_url)
            method_path: str = method.lstrip('/') if method else ''
            target_url: str = str(base / method_path)
        
        if ssl:
            ssl_param: ssl_module.SSLContext | bool = self._determine_ssl_settings(target_url, ssl)
        else:
            ssl_param = ssl
            
        skip_header_regeneration: bool = user_agent is not None
        
        retryable_errors: tuple = self.RETRYABLE_ERRORS

        for attempt in range(1, max_retries + 1):
            try:
                if not self.session or self.session.closed:
                    await self._reset_session_if_needed(skip_header_regeneration)
    
                if self.session and self.session.closed:
                    await self._reset_session_if_needed(skip_header_regeneration)
                
                session: aiohttp.ClientSession = await self._get_session()
                
                merged_headers: dict[str, str | bool | list[str]] = dict(session.headers)
                if headers:
                    merged_headers.update(headers)
                
                if user_agent:
                    merged_headers['user-agent'] = user_agent
        
                async with session.request(
                    proxy=self.proxy.as_url if self.proxy else None,
                    method=request_type,
                    url=target_url,
                    json=json_data,
                    data=data,
                    params=params,
                    headers=merged_headers,
                    cookies=cookies,
                    ssl=ssl_param,
                    allow_redirects=allow_redirects,
                    raise_for_status=False
                ) as response:
                    response_data: dict[str, Any] | list[Any] | str = await self._parse_response(response)
                    
                    if verify:
                        await self._verify_response(response, response_data)
                        
                    return response_data

            except retryable_errors as error:
                if isinstance(error, HttpStatusError) and getattr(error, 'status_code', 0) != 429:
                    raise error
                
                if attempt < max_retries:
                    delay: float = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    
                    if isinstance(error, (SessionRateLimited)):
                        await self.logger_msg(
                            msg=f"Server or rate limit error. Retry {attempt}/{max_retries} in {delay:.2f} seconds", 
                            type_msg="debug", method_name="send_request"
                        )
                    elif isinstance(error, (aiohttp.ClientError, asyncio.TimeoutError)):
                        await self.logger_msg(
                            msg=f"Network error {type(error).__name__}: {error}. Retry {attempt}/{max_retries} after {delay:.2f} seconds", 
                            type_msg="debug", method_name="send_request"
                        )
                        await self._reset_session_if_needed(skip_header_regeneration)
                    
                    await asyncio.sleep(delay)
                    continue
                
                if isinstance(error, (ServerError, SessionRateLimited)):
                    raise error
                else:
                    raise ServerError(
                        f"The request failed after {max_retries} attempts to {target_url}. Error {error}"
                    ) from error
                    
            except Exception as error:
                await self.logger_msg(
                    msg=f"Unexpected error when querying to {target_url}: {type(error).__name__}: {error}", 
                    type_msg="error", method_name="send_request"
                )
                if attempt < max_retries:
                    delay: float = random.uniform(*retry_delay) * min(2 ** (attempt - 1), 30)
                    await self._reset_session_if_needed(skip_header_regeneration)
                    await asyncio.sleep(delay)
                    continue
                raise ServerError(
                    f"The request failed after {max_retries} attempts to {target_url}"
                ) from error

        raise ServerError(f"Unreachable code: all {max_retries} attempts have been exhausted")

    async def _parse_response(self, response: aiohttp.ClientResponse) -> dict[str, Any] | list[Any] | str:
        content_type: str = response.headers.get('Content-Type', '').lower()
        
        result = {
            "status_code": response.status,
            "url": str(response.url),
            "data": None,
            "text": ""
        }
        
        try:
            text: str = await response.text()
            result["text"] = text
            
            try:
                json_data = orjson.loads(text)
                result["data"] = json_data
            except orjson.JSONDecodeError:
                pass
            
            if 'application/json' in content_type or 'json' in content_type:
                if result["data"] is None:
                    raise orjson.JSONDecodeError("JSON expected but not parsed", "", 0)
                    
        except orjson.JSONDecodeError as e:
            await self.logger_msg(
                msg=f"JSON decode failed: {e}", type_msg="warning", method_name="_parse_response"
            )
        except Exception as e:
            await self.logger_msg(
                msg=f"Error parsing response: {str(e)}", type_msg="error", method_name="_parse_response"
            )
            result["text"] = "Failed to parse response"
        
        return result
    
    async def _verify_response(
        self,
        response: aiohttp.ClientResponse,
        response_data: dict[str, Any] | list[Any] | str
    ) -> None:
        status_code: int = response.status
        
        information_responses: range = range(100, 200)
        successful_responses: range = range(200, 300)
        redirection_responses: range = range(300, 400)
        client_errors: range = range(400, 500)
        server_errors: range = range(500, 600)
        
        if status_code not in successful_responses:
            if status_code in client_errors:
                if status_code == 400:
                    error_msg: str = "Invalid request"
                elif status_code == 401:
                    error_msg: str = "Not authorized"
                elif status_code == 403:
                    error_msg: str = "Access denied"
                elif status_code == 404:
                    error_msg: str = "Resource not found"
                elif status_code == 429:
                    error_msg: str = "Too many requests"
                    raise SessionRateLimited(f"{error_msg}: {status_code}", response_data)
                else:
                    error_msg: str = f"Client error"
                    
                if status_code != 429:
                    raise HttpStatusError(f"{error_msg}: {status_code}", status_code, response_data)
            
            elif status_code in server_errors:
                raise ServerError(f"Server error: {status_code}", response_data)
            
            elif status_code in redirection_responses:
                await self.logger_msg(
                    msg=f"Redirection received: {status_code}", type_msg="warning", method_name="_verify_response"
                )
            
            elif status_code in information_responses:
                await self.logger_msg(
                    msg=f"Information response received: {status_code}", type_msg="debug", method_name="_verify_response"
                )
            
            else:
                raise HttpStatusError(f"Unexpected HTTP code: {status_code}", status_code, response_data)
        
        if isinstance(response_data, dict):
            status: bool | str | None = response_data.get("status")
            
            if isinstance(status, bool) and not status:
                raise APIError(f"API returned an invalid status: {response_data}", response_data)
                
            if isinstance(status, str) and status.lower() == "failed":
                raise APIError(f"API reported a failed status: {response_data}", response_data)
            
            if response_data.get("success") is False:
                raise APIError(f"API returned an unsuccessful response: {response_data}", response_data)
            
            status_code_in_body: int | None = response_data.get("statusCode")
            if status_code_in_body and status_code_in_body not in {200, 201, 202, 204}:
                raise APIError(f"Invalid status code in response body: {status_code_in_body}", response_data)
        
        elif isinstance(response_data, list):
            if not response_data:
                await self.logger_msg(
                    msg="An empty response array is received", type_msg="debug", method_name="_verify_response"
                )