from dataclasses import dataclass
from functools import cached_property
from typing import Any
from urllib.parse import parse_qs, urlparse

from curl_cffi.requests import AsyncSession

from src.exceptions.discord_exceptions import (
    DiscordAuthError,
    DiscordClientError,
    DiscordInvalidTokenError,
    DiscordNetworkError,
    DiscordRateLimitError,
    DiscordServerError,
)
from src.models import Account
from src.utils import save_bad_discord_token, get_address


Headers = dict[str, str]


@dataclass(frozen=True)
class DiscordConfig:
    """
    Configuration constants for Discord API interaction.
    """
    API_VERSION: str = "v9"
    CLIENT_ID: str = "1318915934878040064"
    GUILD_ID: str = "1284288403638325318"
    REDIRECT_URI: str = "https://quest.somnia.network/discord"
    BASE_URL: str = "https://discord.com"
    API_URL: str = f"{BASE_URL}/api/{API_VERSION}"
    OAUTH_PATH: str = "/oauth2/authorize"
    STATE: str = (
        "eyJ0eXBlIjoiQ09OTkVDVF9ESVNDT1JEIn0="
    )
    SUPER_PROPERTIES: str = (
        "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwi"
        "c3lzdGVtX2xvY2FsZSI6InJ1IiwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS"
    )


class DiscordClient:
    """
    Asynchronous Discord OAuth2 client for account linking.
    """

    def __init__(self, account: Account) -> None:
        self._token: str | None = account.auth_tokens_discord
        self._proxy = account.proxy
        self._config = DiscordConfig()
        self._session: AsyncSession | None = None
        self.wallet_address = get_address(account.private_key)

        if not self._token:
            raise DiscordClientError("Discord token not provided")

    async def __aenter__(self) -> "DiscordClient":
        self._session = AsyncSession(verify=False, timeout=30)
        if self._proxy:
            proxy_url = self._proxy.as_url
            self._session.proxies.update({"http": proxy_url, "https": proxy_url})
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @cached_property
    def _base_headers(self) -> Headers:
        """
        Base headers for Discord API calls, including authorization.
        """
        return {
            "authority": "discord.com",
            "accept": "application/json",
            "authorization": self._token,
            "content-type": "application/json",
            "dnt": "1",
            "origin": self._config.BASE_URL,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-super-properties": self._config.SUPER_PROPERTIES,
            "x-requested-with": "XMLHttpRequest",
        }

    def _oauth_params(self) -> dict[str, str]:
        """
        Parameters for the OAuth2 authorization request.
        """
        return {
            "client_id": self._config.CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self._config.REDIRECT_URI,
            "scope": "identify",
            "state": self._config.STATE,
        }

    def _oauth_referer(self, params: dict[str, str]) -> str:
        """
        Constructs the Referer URL for the OAuth2 request.
        """
        query = (
            f"response_type={params['response_type']}"
            f"&client_id={params['client_id']}"
            f"&redirect_uri={params['redirect_uri']}"
            f"&scope={params['scope']}"
            f"&state={params['state']}"
        )
        return f"{self._config.BASE_URL}{self._config.OAUTH_PATH}?{query}"

    @staticmethod
    def _extract_auth_code(response_data: dict[str, Any]) -> str:
        """
        Parses redirect location header to extract the authorization code.
        """
        location = response_data.get("location")
        if not location:
            raise DiscordAuthError("Location header missing in response")

        parsed = urlparse(location)
        code = parse_qs(parsed.query).get("code", [None])[0]
        if not code:
            raise DiscordAuthError("Authorization code not found in response")
        return code

    async def _validate_status(
        self, status: int, text: str
    ) -> None:
        """
        Validates HTTP status and raises appropriate errors.
        """
        if status in (401, 403):
            await save_bad_discord_token(self._token, self.wallet_address)
            raise DiscordInvalidTokenError(f"Invalid token: {text}")
        if status >= 500:
            raise DiscordServerError(f"Server error {status}: {text}")
        if status != 200:
            raise DiscordAuthError(f"Auth failed {status}: {text}")

    async def request_authorization(self) -> str:
        """
        Sends OAuth2 authorization request and returns the auth code.
        """
        if not self._session:
            raise DiscordNetworkError("Session not initialized")

        params = self._oauth_params()
        referer = self._oauth_referer(params)
        headers = {**self._base_headers, "referer": referer}
        payload = {
            "permissions": "0",
            "authorize": True,
            "integration_type": 0,
            "location_context": {
                "guild_id": self._config.GUILD_ID,
                "channel_id": "10000",
                "channel_type": 10000,
            },
        }

        try:
            response = await self._session.post(
                url=f"{self._config.API_URL}{self._config.OAUTH_PATH}",
                params=params,
                headers=headers,
                json=payload,
                allow_redirects=False,
            )

            await self._validate_status(response.status_code, response.text)
            data = response.json()
            return self._extract_auth_code(data)

        except (DiscordAuthError, DiscordInvalidTokenError, DiscordServerError):
            raise
        except Exception as err:
            msg = str(err)
            if "429" in msg:
                raise DiscordRateLimitError(f"Rate limit: {msg}")
            if any(tok in msg.lower() for tok in ["unauthorized", "forbidden"]):
                await save_bad_discord_token(self._token, self.wallet_address)
                raise DiscordInvalidTokenError(f"Detected invalid token: {msg}")
            raise DiscordNetworkError(f"Network error: {msg}")