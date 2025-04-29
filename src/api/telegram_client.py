import asyncio
import re
from typing import Any, Self

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton

from bot_loader import config
from src.models import Account
from src.exceptions.telegram_exceptions import (
    TelegramAuthError,
    TelegramNetworkError,
    TelegramTimeoutError
)
from src.exceptions.config_exceptions import MissingConfigError, TelegramConfigError
from src.utils import get_address

class TelegramClient:
    
    BOT_ID = '7919397002'
    ORIGIN = 'https://quest.somnia.network/telegram'
    OAUTH_BASE_URL = 'https://oauth.telegram.org'
    
    AUTH_KEYWORDS = [
        "получили запрос на авторизацию", 
        "authorization request", 
        "запрос", "request", 
        "авторизац", "auth"
    ]    

    def __init__(self, account: Account):        
        self.account: Account = account
        self.telegram_api_id: str = config.telegram_api_id
        self.telegram_api_hash: str = config.telegram_api_hash
        self.phone: str | None = None
        self.client: Client | None = None
        self.auth_confirmed: asyncio.Event = asyncio.Event()
        self.proxy: str | None = account.proxy
        self.form_session: aiohttp.ClientSession | None = None
        self.cookies: dict[str, str] = {}
        self.wallet_address: str = get_address(account.private_key)

    async def __aenter__(self) -> Self:
        self.form_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        cleanup_tasks = []
        
        if self.form_session and not self.form_session.closed:
            cleanup_tasks.append(self.form_session.close())
        
        if self.client and self.client.is_connected:
            cleanup_tasks.append(self.client.stop())
        
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    async def get_client(self) -> Any:
        self.client = Client(
            session_string=None,
            api_id=int(self.telegram_api_id),
            api_hash=self.telegram_api_hash,
            workdir=str(self.account.telegram_session.parent),
            name=self.account.telegram_session.stem
        )
        
        await self.client.start()
        
        me = await self.client.get_me()
        self.phone = me.phone_number
        
        return me

    async def confirm_auth(self, client: Client, message: Message) -> None:
        if not self._is_auth_message(message.text):
            return
            
        await self._process_auth_buttons(client, message)

    def _is_auth_message(self, text: str | None) -> bool:
        if not text:
            return False
        return any(keyword in text.lower() for keyword in self.AUTH_KEYWORDS)

    async def _process_auth_buttons(self, client: Client, message: Message) -> None:
        if not hasattr(message, 'reply_markup') or not message.reply_markup:
            raise TelegramAuthError("Buttons not found in message")
            
        buttons = message.reply_markup.inline_keyboard
        
        if len(buttons) > 0 and len(buttons[0]) > 0:
            accept_btn_idx = len(buttons[0]) - 1
            await self._click_button(client, message, buttons[0][accept_btn_idx])

    async def _click_button(
        self, client: Client, message: Message, button: InlineKeyboardButton
    ) -> None:
        try:
            await client.request_callback_answer(
                chat_id=message.chat.id,
                message_id=message.id,
                callback_data=button.callback_data
            )
            self.auth_confirmed.set()
        except Exception as e:
            raise TelegramAuthError(f"Error while clicking button: {e}")

    async def get_user_agent(self) -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    async def run(self) -> str:
        me = await self.get_client()
        phone = self.phone
        
        if not phone:
            raise TelegramAuthError("Phone number is missing")
        
        @self.client.on_message(filters.private)
        async def handle_message(client: Client, message: Message) -> None:
            await self.confirm_auth(client, message)
        
        await self._send_auth_request(phone)
        await self._wait_for_confirmation()
        await self._confirm_login()
        
        tg_auth_result = await self._generate_user_data(me)
        if not tg_auth_result:
            raise TelegramAuthError("Failed to generate tgAuthResult")
        
        return tg_auth_result

    async def _send_auth_request(self, phone: str) -> None:
        auth_request_url = f'{self.OAUTH_BASE_URL}/auth/request'
        params = {
            'bot_id': self.BOT_ID,
            'origin': self.ORIGIN
        }

        headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': self.OAUTH_BASE_URL,
            'referer': (
                f'{self.OAUTH_BASE_URL}/auth?bot_id={self.BOT_ID}&origin={self.ORIGIN}'
                f'&redirect_uri={self.ORIGIN}&scope=users'
            ),
            'user-agent': await self.get_user_agent(),
            'x-requested-with': 'XMLHttpRequest'
        }

        data = {'phone': phone.lstrip('+')}
        proxy_url = str(self.proxy) if self.proxy else None
        
        try:
            async with self.form_session.post(
                auth_request_url, 
                params=params, 
                headers=headers, 
                data=data, 
                proxy=proxy_url
            ) as response:     
                cookies = {k: v.value for k, v in response.cookies.items()}
                stel_tsession_key = next(
                    (k for k in cookies.keys() if k.startswith('stel_tsession_')), 
                    None
                )

                if stel_tsession_key:
                    self.cookies.update({
                        'stel_ssid': cookies.get('stel_ssid'),
                        stel_tsession_key: cookies.get(stel_tsession_key)
                    })
                
                response_text = await response.text()
                
                if response.status != 200 or response_text != 'true':
                    raise TelegramAuthError(
                        f"Authorization request failed: {response.status} - {response_text}"
                    )
        
        except aiohttp.ClientError as e:
            raise TelegramNetworkError(
                f"Network error while sending authorization request: {e}"
            )

    async def _wait_for_confirmation(self) -> None:
        try:
            await asyncio.wait_for(self.auth_confirmed.wait(), timeout=120)
        except asyncio.TimeoutError:
            raise TelegramTimeoutError("Timeout while waiting for confirmation")

    async def _confirm_login(self) -> None:
        login_url = f'{self.OAUTH_BASE_URL}/auth/login'
        login_headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': self.OAUTH_BASE_URL,
            'referer': (
                f'{self.OAUTH_BASE_URL}/auth?bot_id={self.BOT_ID}&origin={self.ORIGIN}'
                f'&redirect_uri={self.ORIGIN}&scope=users'
            ),
            'user-agent': await self.get_user_agent(),
            'x-requested-with': 'XMLHttpRequest'
        }
        params = {
            'bot_id': self.BOT_ID,
            'origin': self.ORIGIN,
        }
        proxy_url = str(self.proxy) if self.proxy else None
        
        max_attempts = 10
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                async with self.form_session.post(
                    login_url, 
                    headers=login_headers, 
                    params=params, 
                    proxy=proxy_url,
                    cookies=self.cookies
                ) as response:
                    response_text = await response.text()
                    
                    cookies = {k: v.value for k, v in response.cookies.items()}
                    if 'stel_token' in cookies:
                        self.cookies.update({'stel_token': cookies.get('stel_token')})
                    
                    if response.status == 200 and response_text == 'true':
                        return
                    
                    last_error = f"Статус: {response.status}, ответ: {response_text}"
                    
                    if attempt == max_attempts - 1:
                        break
                    
                    await asyncio.sleep(5)
            except aiohttp.ClientError as e:
                last_error = str(e)
                if attempt == max_attempts - 1:
                    break
                await asyncio.sleep(5)
        
        raise TelegramAuthError(
            f"Failed to login after {max_attempts} attempts: {last_error}"
        )

    async def _generate_user_data(self, me: Any) -> str | None:
        headers = {
            'authority': self.OAUTH_BASE_URL,
            'accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
                'image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
            ),
            'dnt': '1',
            'referer': 'https://quest.somnia.network/',
            'upgrade-insecure-requests': '1',
            'user-agent': await self.get_user_agent()
        }
        
        params = {
            'bot_id': self.BOT_ID,
            'origin': self.ORIGIN,
            'redirect_uri': self.ORIGIN,
            'scope': 'users',
        }
        
        proxy_url = str(self.proxy) if self.proxy else None
        
        try:
            async with self.form_session.get(
                f'{self.OAUTH_BASE_URL}/auth', 
                headers=headers, 
                params=params,
                cookies=self.cookies, 
                proxy=proxy_url
            ) as response:
                response_text = await response.text()
                
                if 'login_form' in response_text:
                    await self._send_auth_request(self.phone)
                    await self._wait_for_confirmation()
                    await self._confirm_login()
                    
                    async with self.form_session.get(
                        f'{self.OAUTH_BASE_URL}/auth',
                        headers=headers,
                        params=params,
                        cookies=self.cookies,
                        proxy=proxy_url
                    ) as confirm_response:
                        response_text = await confirm_response.text()
                
                if 'login_content_request' in response_text:
                    return await self._process_confirmation_page(
                        response_text, headers, proxy_url
                    )
                
                tg_auth_match = re.search(r'tgAuthResult=([^"]+)', response_text)
                if tg_auth_match:
                    return tg_auth_match.group(1)
                else:
                    return None
        except aiohttp.ClientError as e:
            raise TelegramNetworkError(
                f"Network error while generating user data: {e}"
            )

    async def _process_confirmation_page(
        self, response_text: str, headers: dict, proxy_url: str | None
    ) -> str | None:
        confirm_url_match = re.search(r"confirm_url = '(/auth/auth\?[^']+)'", response_text)
        if not confirm_url_match:
            confirm_url_match = re.search(r"var confirm_url = '(/auth/auth\?[^']+)'", response_text)
            if not confirm_url_match:
                return None
        
        confirm_url = f"{self.OAUTH_BASE_URL}{confirm_url_match.group(1)}"
        
        try:
            async with self.form_session.get(
                confirm_url,
                headers=headers,
                cookies=self.cookies,
                proxy=proxy_url
            ) as final_response:
                final_text = await final_response.text()
                tg_auth_match = re.search(r'tgAuthResult=([^"]+)', final_text)
                if tg_auth_match:
                    return tg_auth_match.group(1)
                else:
                    return None
        except aiohttp.ClientError as e:
            raise TelegramNetworkError(
                f"Network error while processing the confirmation page: {e}"
            )

    async def get_pyrogram_client(self) -> Any:
        if not hasattr(config, 'telegram_api_id') or not config.telegram_api_id:
            raise MissingConfigError("telegram_api_id is missing in configuration")
        if not hasattr(config, 'telegram_api_hash') or not config.telegram_api_hash:
            raise MissingConfigError("telegram_api_hash is missing in configuration")
        
        try:
            int(config.telegram_api_id)
        except ValueError:
            raise TelegramConfigError(
                f"telegram_api_id must be a number, got: {config.telegram_api_id}"
            )
            
        self.client = Client(
            session_string=None,
            api_id=int(config.telegram_api_id),
            api_hash=config.telegram_api_hash,
            workdir=str(self.account.telegram_session.parent),
            name=self.account.telegram_session.stem,
        )
        await self.client.start()
        me = await self.client.get_me()
        self.phone = me.phone_number
        return me