from dataclasses import dataclass
from functools import cached_property
from typing import Self
from urllib.parse import parse_qs, urlparse
import asyncio

from curl_cffi.requests import AsyncSession

from src.exceptions.custom_exceptions import DiscordAuthError, DiscordError
from src.models import Account
from src.utils import save_bad_discord_token

file_lock = asyncio.Lock()

@dataclass
class DiscordConfig:
    API_VERSION: str = "v9"
    CLIENT_ID: str = "1318915934878040064"
    GUILD_ID: str = "1284288403638325318"
    REDIRECT_URI: str = "https://quest.somnia.network/discord"
    BASE_URL: str = "https://discord.com"
    API_URL: str = f"{BASE_URL}/api/{API_VERSION}"
    OAUTH_URL: str = f"{BASE_URL}/oauth2/authorize"
    STATE: str = "eyJ0eXBlIjoiQ09OTkVDVF9ESVNDT1JEIn0="
    SUPER_PROPERTIES: str = "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6InJ1IiwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTI5LjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiJodHRwczovL2Rpc2NvcmQuY29tL2FwcC9pbnZpdGUtd2l0aC1ndWlsZC1vbmJvYXJkaW5nL2lua29uY2hhaW4iLCJyZWZlcnJpbmdfZG9tYWluIjoiZGlzY29yZC5jb20iLCJyZWZlcnJlcl9jdXJyZW50IjoiaHR0cHM6Ly9xdWVzdC5zb21uaWEubmV0d29yay8iLCJyZWZlcnJpbmdfZG9tYWluX2N1cnJlbnQiOiJxdWVzdC5zb21uaWEubmV0d29yayIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjM3MDUzMywiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbCwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZX0="


class DiscordClient:
    def __init__(self, account: Account):
        self.token = account.auth_tokens_discord
        self.proxy = account.proxy
        self.discord_config = DiscordConfig()
        self.session: AsyncSession | None = None

        if not self.token:
            raise DiscordError("Discord token not provided")

    async def __aenter__(self) -> Self:
        self.session = AsyncSession(
            verify=False,
            timeout=30
        )
        if self.proxy:
            proxy_url = self.proxy.as_url
            self.session.proxies.update({"http": proxy_url, "https": proxy_url})
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    @cached_property
    async def auth_headers(self) -> dict[str, str]:
        return {
            'authority': 'discord.com',
            'accept': 'application/json',
            'authorization': self.token,
            'content-type': 'application/json',
            'dnt': '1',
            'origin': self.discord_config.BASE_URL,
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-super-properties': self.discord_config.SUPER_PROPERTIES,
            'x-requested-with': 'XMLHttpRequest'
        }

    def _get_oauth_params(self) -> dict[str, str]:
        return {
            'client_id': self.discord_config.CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': self.discord_config.REDIRECT_URI,
            'scope': 'identify',
            'state': self.discord_config.STATE
        }

    def _get_oauth_referer(self, params: dict[str, str]) -> str:
        return f"https://discord.com/oauth2/authorize?response_type=code&client_id=1318915934878040064&redirect_uri=https%3A%2F%2Fquest.somnia.network%2Fdiscord&scope=identify&state=eyJ0eXBlIjoiQ09OTkVDVF9ESVNDT1JEIn0="

    @staticmethod
    def _extract_auth_code(response_data: dict) -> str | None:
        if 'location' not in response_data:
            return None
        parsed_url = urlparse(response_data['location'])
        query_params = parse_qs(parsed_url.query)
        return query_params.get('code', [None])[0]

    async def _request_authorization(self) -> str:
        try:
            oauth_params = self._get_oauth_params()
            oauth_referer = self._get_oauth_referer(oauth_params)

            headers = await self.auth_headers
            headers['referer'] = oauth_referer

            auth_data = {
                "permissions": "0",
                "authorize": True,
                "integration_type": 0,
                "location_context": {
                    "guild_id": "10000",
                    "channel_id": "10000",
                    "channel_type": 10000
                }
            }

            response = await self.session.post(
                url=f"{self.discord_config.API_URL}/oauth2/authorize",
                params=oauth_params,
                headers=headers,
                json=auth_data,
                allow_redirects=False
            )
            
            if response.status_code == 401 or response.status_code == 403:
                await save_bad_discord_token(self.token)
                raise DiscordAuthError(f"Invalid Discord token: {response.text}")
            elif response.status_code != 200:
                raise DiscordAuthError(f"Authorization request failed: {response.text}")

            auth_code = self._extract_auth_code(response.json())
            if not auth_code:
                raise DiscordAuthError(f"Failed to extract authorization code. Response: {response.text}")

            return auth_code

        except Exception as e:
            raise DiscordAuthError(f"Authorization process failed: {str(e)}")