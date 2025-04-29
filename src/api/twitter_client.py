import aiohttp
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse
from typing import Self
from Jam_Twitter_API.account_sync import TwitterAccountSync
from Jam_Twitter_API.errors import TwitterError, TwitterAccountSuspended, IncorrectData

from src.exceptions.twitter_exceptions import (
    TwitterAuthError,
    TwitterNetworkError,
    TwitterInvalidTokenError,
    TwitterAccountSuspendedError,
)
from src.models import Account
from src.utils import save_bad_twitter_token, get_address


Headers = dict[str, str]


@dataclass(frozen=True)
class TwitterConfig:
    """
    Configuration for Twitter OAuth2 via Quest platform.
    """
    CLIENT_ID: str = "WS1FeDNoZnlqTEw1WFpvX1laWkc6MTpjaQ"
    REDIRECT_URI: str = "https://quest.somnia.network/twitter"
    BEARER_TOKEN: str = (
        "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    )
    API_DOMAIN: str = "twitter.com"
    OAUTH_PATH: str = "/i/api/2/oauth2/authorize"
    SCOPES: str = (
        "users.read follows.write tweet.write like.write tweet.read"
    )
    STATE: str = "eyJ0eXBlIjoiQ09OTkVDVF9UV0lUVEVSIn0="
    CODE_CHALLENGE: str = "challenge123"


class TwitterClient:
    """
    Asynchronous client to perform Twitter OAuth2 authorization.
    """

    def __init__(self, account: Account) -> None:
        self._account: Account = account
        self._config: TwitterConfig = TwitterConfig()
        self._sync_client: TwitterAccountSync | None = None
        self.wallet_address = get_address(account.private_key)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def _build_headers(self, ct0_token: str) -> Headers:
        """
        Builds HTTP headers for Twitter OAuth requests.
        """
        return {
            'authority': self._config.API_DOMAIN,
            'accept': '*/*',
            'accept-language': 'ru,en-US;q=0.9,en;q=0.8',
            'authorization': f'Bearer {self._config.BEARER_TOKEN}',
            'cookie': (
                f'auth_token={self._account.auth_tokens_twitter};'
                f' ct0={ct0_token}'
            ),
            'x-csrf-token': ct0_token,
        }

    def _auth_params(self) -> dict[str, str]:
        """
        Returns query parameters for the OAuth2 authorization URL.
        """
        return {
            'response_type': 'code',
            'client_id': self._config.CLIENT_ID,
            'redirect_uri': self._config.REDIRECT_URI,
            'scope': self._config.SCOPES,
            'state': self._config.STATE,
            'code_challenge': self._config.CODE_CHALLENGE,
            'code_challenge_method': 'plain',
        }

    @staticmethod
    def _extract_code(redirect_uri: str) -> str:
        """
        Parses authorization code from redirect URI.
        """
        parsed = urlparse(redirect_uri)
        return parse_qs(parsed.query).get('code', [''])[0]

    async def _handle_sync_errors(self, error: TwitterError) -> None:
        """
        Checks for token-related errors and raises appropriate exceptions.
        """
        if isinstance(error, TwitterAccountSuspended):
            await save_bad_twitter_token(self._account.auth_tokens_twitter, self.wallet_address)
            raise TwitterAccountSuspendedError(f"Account suspended: {error}")

        code = getattr(error, 'error_code', None)
        if code in (32, 89, 215, 326) or isinstance(error, IncorrectData):
            await save_bad_twitter_token(self._account.auth_tokens_twitter, self.wallet_address)
            raise TwitterInvalidTokenError(
                f"Invalid token or data: {error}"
            )

    async def _init_sync_client(self) -> TwitterAccountSync:
        """
        Initializes synchronous TwitterAccountSync and returns it.
        Handles suspension and invalid token errors.
        """
        try:
            return TwitterAccountSync.run(
                auth_token=self._account.auth_tokens_twitter,
                proxy=str(self._account.proxy),
                setup_session=True
            )
        except TwitterError as err:
            await self._handle_sync_errors(err)
            raise TwitterAuthError(f"Twitter sync error: {err}")

    async def connect_twitter(self) -> str:
        """
        Performs full OAuth2 flow: obtains ct0 token, requests auth URL,
        approves, and extracts authorization code.
        """
        # Initialize sync client
        sync_client = await self._init_sync_client()
        ct0_token = sync_client.ct0
        headers = self._build_headers(ct0_token)
        auth_url = f"https://{self._config.API_DOMAIN}{self._config.OAUTH_PATH}"

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                # Authorization request
                async with session.get(
                    auth_url,
                    params=self._auth_params()
                ) as resp:
                    if resp.status != 200:
                        if resp.status in (401, 403):
                            await save_bad_twitter_token(self._account.auth_tokens_twitter, self.wallet_address)
                            raise TwitterInvalidTokenError(
                                f"Unauthorized status: {resp.status}"
                            )
                        raise TwitterAuthError(
                            f"Auth request failed: {resp.status}"
                        )
                    data = await resp.json()
                    code = data.get('auth_code')
                    if not code:
                        raise TwitterAuthError("Auth code missing in response")

                # Approval step
                async with session.post(
                    auth_url,
                    params={'approval': 'true', 'code': code}
                ) as approve_resp:
                    if approve_resp.status != 200:
                        if approve_resp.status in (401, 403):
                            await save_bad_twitter_token(self._account.auth_tokens_twitter, self.wallet_address)
                            raise TwitterInvalidTokenError(
                                f"Unauthorized approval: {approve_resp.status}"
                            )
                        raise TwitterAuthError(
                            f"Approval failed: {approve_resp.status}"
                        )
                    approve_data = await approve_resp.json()
                    redirect = approve_data.get('redirect_uri', '')
                    return self._extract_code(redirect)

        except aiohttp.ClientError as err:
            msg = str(err)
            if any(term in msg.lower() for term in ("401", "403", "invalid")):
                await save_bad_twitter_token(self._account.auth_tokens_twitter, self.wallet_address)
                raise TwitterInvalidTokenError(f"Network unauthorized: {msg}")
            raise TwitterNetworkError(f"HTTP error: {msg}")

        except Exception as err:
            raise TwitterAuthError(f"Unexpected error: {err}")