import base64
import orjson

from typing import Self
from curl_cffi.requests import AsyncSession, Response

from src.models import Account
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.utils import random_sleep, save_bad_discord_token


class DiscordTasksModule(Wallet, AsyncLogger):
    __slots__ = ['account', 'user_agent', 'session']

    DEFAULT_HEADERS = {
        'authority': 'discord.com',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'sec-ch-ua': '"Chromium";v="131", "Not A(Brand";v="24", "Google Chrome";v="131"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
    }

    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, account.proxy)
        AsyncLogger.__init__(self)
        
        self.account: Account = account
        self.user_agent: str = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/134.0.0.0 Safari/537.36'
        )
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self.session = AsyncSession(impersonate="chrome110")
        if self.account.proxy:
            proxy_str = str(self.account.proxy)
            self.session.proxies = {"http": proxy_str, "https": proxy_str}
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    def _create_x_super_properties(self) -> str:
        properties = {
            "os": "Windows",
            "browser": "Chrome",
            "device": "",
            "system_locale": "en",
            "browser_user_agent": self.user_agent,
            "browser_version": "134.0.0.0",
            "os_version": "10",
            "referrer": "https://discord.com/",
            "referring_domain": "discord.com",
            "referrer_current": "",
            "referring_domain_current": "",
            "release_channel": "stable",
            "client_build_number": 814692,
            "client_event_source": None,
            "has_client_mods": False
        }
        return base64.b64encode(orjson.dumps(properties)).decode('utf-8')

    @staticmethod
    def create_x_context_properties(guild_id: str, channel_id: str) -> str:
        context = {
            "location": "Accept Invite Page",
            "location_guild_id": guild_id,
            "location_channel_id": channel_id,
            "location_channel_type": 0
        }
        return base64.b64encode(orjson.dumps(context)).decode('utf-8')

    async def init_cf(self) -> bool:
        if not self.session:
            return False
            
        try:
            resp = await self.session.get(
                "https://discord.com/login",
                headers=self.DEFAULT_HEADERS,
                verify=False
            )
            return resp.status_code == 200
        except Exception as error:
            await self.logger_msg(
                msg=f"Failed to initialize cookies: {error}", 
                type_msg="error", 
                address=self.wallet_address, 
                method_name="init_cf"
            )
            return False

    def _prepare_join_headers(self, invite_code: str, guild_id: str, channel_id: str) -> dict:
        return {
            "accept": "*/*",
            "accept-language": "en-GB,en;q=0.9,en-US;q=0.8,en;q=0.7",
            "authorization": self.account.auth_tokens_discord,
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://discord.com",
            "priority": "u=1, i",
            "referer": f"https://discord.com/invite/{invite_code}",
            "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self.user_agent,
            "x-context-properties": self.create_x_context_properties(guild_id, channel_id),
            "x-debug-options": "bugReporterEnabled",
            "x-discord-locale": "en-US",
            "x-discord-timezone": "Europe/London",
            "x-super-properties": self._create_x_super_properties(),
        }

    async def _send_join_request(self, invite_code: str, headers: dict) -> Response:
        json_data = {"session_id": None}
        return await self.session.post(
            f"https://discord.com/api/v9/invites/{invite_code}",
            headers=headers,
            json=json_data,
            verify=False
        )

    async def _handle_join_response(self, response: Response) -> tuple[bool, str]:
        if response.status_code == 401:
            await save_bad_discord_token(self.account.auth_tokens_discord)
            await self.logger_msg(
                msg="Incorrect Discord token or account blocked", 
                type_msg="error", address=self.wallet_address, 
                method_name="_handle_join_response"
            )
            return False, "Incorrect Discord token or account blocked"

        response_data: dict = response.json()

        if any(
            "You need to update your app to join this server." in str(value)
            or "captcha_rqdata" in str(value)
            for value in response_data.values()
        ):
            await self.logger_msg(
                msg="Captcha detected. Cannot solve it.", 
                type_msg="error", address=self.wallet_address, 
                method_name="_handle_join_response"
            )
            return False, "Captcha detected. Cannot solve it."

        if response.status_code == 200 and response_data.get("type") == 0:
            await self.logger_msg(
                msg="Account joined the server!", 
                type_msg="success", address=self.wallet_address
            )
            return True, "Account joined the server"

        if "Unauthorized" in str(response_data):
            await self.logger_msg(
                msg="Incorrect Discord token or account blocked", 
                type_msg="error", address=self.wallet_address, 
                method_name="_handle_join_response"
            )
            return False, "Incorrect Discord token or account blocked"

        if "You need to verify your account in order to" in str(response_data):
            await self.logger_msg(
                msg="Account requires verification (email code)", 
                type_msg="error", address=self.wallet_address, 
                method_name="_handle_join_response"
            )
            return False, "Account requires verification (email code)"

        await self.logger_msg(
            msg=f"Unknown error: {response_data}", 
            type_msg="error", address=self.wallet_address, 
            method_name="_handle_join_response"
        )
        return False, "Unknown error during invite"

    async def join_server(self, invite_code: str, guild_id: str, channel_id: str) -> tuple[bool, str]:
        if not await self.init_cf():
            return False, "Failed to initialize cookies"

        for attempt in range(3):
            try:
                headers = self._prepare_join_headers(invite_code, guild_id, channel_id)
                response = await self._send_join_request(invite_code, headers)
                return await self._handle_join_response(response)
            except Exception as error:
                await self.logger_msg(
                    msg=f"Error sending invite: {error}", 
                    type_msg="error", address=self.wallet_address, 
                    method_name="join_server"
                )
                await random_sleep(self.wallet_address, 10, 20)

        return False, "Failed to join the server after three attempts"