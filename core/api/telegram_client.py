import asyncio
import hashlib
import jwt
import time

import aiohttp
from pyrogram import Client, filters

from core.api import BaseAPIClient
from core.wallet import Wallet
from loader import config
from logger import log
from models import Account


class TelegramClient(Wallet):
    """Telegram client for OAuth authorization and handling auth requests."""
    
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
        """Initialize Telegram client with account data."""
        super().__init__(account.private_key, account.proxy)
        self.account = account
        self.telegram_api_id = config.telegram_api_id
        self.telegram_api_hash = config.telegram_api_hash
        self.phone = None
        self.client = None
        self.auth_confirmed = asyncio.Event()
        self.proxy = account.proxy
        
        self.api_client = BaseAPIClient(
            base_url=self.OAUTH_BASE_URL,
            proxy=account.proxy,
            session_lifetime=5,
            enable_random_delays=True
        )
        self.form_session = None

    async def get_client(self):
        """Initialize Telegram client and return user data."""
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
        log.info(
            f"Account {self.wallet_address} | Telegram client initialized | "
            f"User: {me.first_name} {me.last_name} | Username: @{me.username}"
        )
        
        return me

    async def confirm_auth(self, client, message):
        """Process Telegram authorization message."""
        if not self._is_auth_message(message.text):
            return
            
        try:
            await self._process_auth_buttons(client, message)
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error processing buttons: {e}")

    def _is_auth_message(self, text):
        """Check if message is an authorization request."""
        return any(keyword in text.lower() for keyword in self.AUTH_KEYWORDS)

    async def _process_auth_buttons(self, client, message):
        """Process authorization buttons in message."""
        if not hasattr(message, 'reply_markup') or not message.reply_markup:
            log.error(f"Account {self.wallet_address} | Buttons not found in message")
            return
            
        buttons = message.reply_markup.inline_keyboard
        
        if len(buttons) > 0 and len(buttons[0]) > 0:
            accept_btn_idx = len(buttons[0]) - 1
            await self._click_button(client, message, buttons[0][accept_btn_idx])

    async def _click_button(self, client, message, button):
        """Click button in message."""
        try:
            await client.request_callback_answer(
                chat_id=message.chat.id,
                message_id=message.id,
                callback_data=button.callback_data
            )
            log.success(f"Account {self.wallet_address} | Authorization request confirmed")
            self.auth_confirmed.set()
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error clicking button: {e}")

    def get_user_agent(self):
        """Get User-Agent from BaseAPIClient."""
        return self.api_client.session.headers.get('user-agent')

    async def run(self):
        """Execute Telegram authorization process."""
        try:
            await self.api_client.initialize()
            self.form_session = aiohttp.ClientSession()
            
            me = await self.get_client()
            phone = self.phone
            
            @self.client.on_message(filters.private)
            async def handle_message(client, message):
                await self.confirm_auth(client, message)
            
            if not await self._send_auth_request(phone):
                return False
                
            if not await self._wait_for_confirmation():
                return False
                
            if not await self._confirm_login():
                return False
            
            encoded_user_data = self._generate_user_data(me)
            
            await self._cleanup()
            
            return encoded_user_data
            
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Unexpected error in Telegram auth: {e}")
            await self._cleanup()
            return False

    async def _send_auth_request(self, phone):
        """Send authorization request."""
        auth_request_url = f'{self.OAUTH_BASE_URL}/auth/request'
        params = {
            'bot_id': self.BOT_ID,
            'origin': self.ORIGIN
        }

        headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': self.OAUTH_BASE_URL,
            'referer': f'{self.OAUTH_BASE_URL}/auth?bot_id={self.BOT_ID}&origin={self.ORIGIN}&redirect_uri={self.ORIGIN}&scope=users',
            'user-agent': self.get_user_agent(),
            'x-requested-with': 'XMLHttpRequest'
        }

        data = {'phone': phone.lstrip('+')}
        proxy_url = str(self.proxy) if self.proxy else None
        
        async with self.form_session.post(
            auth_request_url, 
            params=params, 
            headers=headers, 
            data=data, 
            proxy=proxy_url
        ) as response:
            response_text = await response.text()
            
            if response.status != 200 or response_text != 'true':
                log.error(f"Account {self.wallet_address} | Auth request failed")
                return False
        
        log.success(f"Account {self.wallet_address} | Auth request successful, waiting for confirmation")
        return True

    async def _wait_for_confirmation(self):
        """Wait for authorization confirmation."""
        try:
            await asyncio.wait_for(self.auth_confirmed.wait(), timeout=120)
            log.success(f"Account {self.wallet_address} | Auth confirmed, requesting login")
            return True
        except asyncio.TimeoutError:
            log.error(f"Account {self.wallet_address} | Timeout waiting for auth confirmation")
            return False

    async def _confirm_login(self):
        """Confirm login after user approval."""
        login_url = f'{self.OAUTH_BASE_URL}/auth/login'
        login_headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': self.OAUTH_BASE_URL,
            'referer': f'{self.OAUTH_BASE_URL}/auth?bot_id={self.BOT_ID}&origin={self.ORIGIN}&redirect_uri={self.ORIGIN}&scope=users',
            'user-agent': self.get_user_agent(),
            'x-requested-with': 'XMLHttpRequest'
        }
        params = {
            'bot_id': self.BOT_ID,
            'origin': self.ORIGIN,
        }
        proxy_url = str(self.proxy) if self.proxy else None
        
        max_attempts = 10
        for attempt in range(max_attempts):
            async with self.form_session.post(
                login_url, 
                headers=login_headers, 
                params=params, 
                proxy=proxy_url
            ) as response:
                response_text = await response.text()
                
                if response.status == 200 and response_text == 'true':
                    log.success(f"Account {self.wallet_address} | Login successful")
                    return True
                
                if attempt == max_attempts - 1:
                    log.error(f"Account {self.wallet_address} | Failed to login after {max_attempts} attempts")
                    return False
                
                await asyncio.sleep(5)

    def _generate_user_data(self, me):
        current_time = int(time.time())
        
        payload = {
            "sub": int(me.id),
            "first_name": str(me.first_name or ""),
            "username": str(me.username or ""),
            "iat": current_time,
            "exp": current_time + 86400,
            "auth_date": current_time
        }
        
        SECRET_KEY = hashlib.sha256(str(self.wallet_address).encode()).hexdigest()
        
        token = jwt.encode(
            payload, 
            SECRET_KEY, 
            algorithm='HS256'
        )
        
        return token

    async def _cleanup(self):
        """Close all open sessions and connections."""
        if self.client and self.client.is_connected:
            await self.client.stop()
            
        if self.form_session and not self.form_session.closed:
            await self.form_session.close()
            
        if self.api_client:
            await self.api_client.close()