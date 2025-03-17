from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

# from Jam_Twitter_API.account_sync import TwitterAccountSync
# from Jam_Twitter_API.errors import *

from logger import log
from core.exceptions.base import TwitterError
from core.wallet import Wallet
from models import Account

@dataclass
class TwitterAuthConfig:
    pass
#     """Configuration for Twitter authentication"""
#     CLIENT_ID: str = "WS1FeDNoZnlqTEw1WFpvX1laWkc6MTpjaQ"
#     REDIRECT_URI: str = "https://quest.somnia.network/twitter"
#     BEARER_TOKEN: str = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
#     API_DOMAIN: str = "twitter.com"
#     OAUTH2_PATH: str = "/i/api/2/oauth2/authorize"
#     REQUIRED_SCOPES: str = "users.read follows.write tweet.write like.write tweet.read"


class TwitterClient(Wallet):
    pass
#     def __init__(self, account: Account):
#         """
#         Initializing Twitter client
        
#         Args:
#             account: Account object containing authentication details
#         """
#         super().__init__(account.private_key, account.proxy)
#         self.account = account
#         self.twitter_client = None
#         self.config = TwitterAuthConfig()

#     def _build_headers(self, ct0_token: str) -> Dict[str, str]:
#         """
#         Creating headers for requests
        
#         Args:
#             ct0_token: CSRF token
            
#         Returns:
#             Dict with headers
#         """
#         return {
#             'authority': self.config.API_DOMAIN,
#             'accept': '*/*',
#             'accept-language': 'ru,en-US;q=0.9,en;q=0.8',
#             'authorization': f'Bearer {self.config.BEARER_TOKEN}',
#             'cookie': f'auth_token={self.account.auth_tokens_twitter}; ct0={ct0_token}',
#             'x-csrf-token': ct0_token,
#         }

#     def _build_auth_params(self) -> Dict[str, str]:
#         """
#         Creating authentication parameters
        
#         Returns:
#             Dict with authentication parameters
#         """
#         return {
#             "code_challenge": "challenge123",
#             "code_challenge_method": "plain",
#             "client_id": self.config.CLIENT_ID,
#             "redirect_uri": self.config.REDIRECT_URI,
#             "response_type": "code",
#             "scope": self.config.REQUIRED_SCOPES,
#             "state": "eyJ0eXBlIjoiQ09OTkVDVF9UV0lUVEVSIn0="
#         }

#     @staticmethod
#     def _extract_code_from_redirect(redirect_uri: str) -> str:
#         """
#         Extracting code from redirect URI
        
#         Args:
#             redirect_uri: URI with authorization code
            
#         Returns:
#             Authorization code
#         """
#         parsed = urlparse(redirect_uri)
#         query_params = parse_qs(parsed.query)
#         return query_params.get('code', [''])[0]

#     async def get_account(self) -> Optional[Any]:
#         """
#         Getting Twitter account
        
#         Returns:
#             TwitterAccountSync instance or None if failed
#         """
#         try:
#             self.twitter_client = TwitterAccountSync.run(
#                 auth_token=self.account.auth_tokens_twitter,
#                 proxy=str(self.account.proxy),
#                 setup_session=True
#             )
#             return self.twitter_client

#         except TwitterAccountSuspended as error:
#             log.error(f"Account: {self.wallet_address} | Account suspended: {error}")
#         except TwitterError as error:
#             log.error(
#                 f"Account: {self.wallet_address} | Twitter error: {error.error_message} | {error.error_code}"
#             )
#         except IncorrectData as error:
#             log.error(f"Account: {self.wallet_address} | Invalid data: {error}")
#         except RateLimitError as error:
#             log.error(f"Account: {self.wallet_address} | Rate limit hit: {error}")
#         except Exception as error:
#             log.error(f"Account: {self.wallet_address} | Unexpected error: {error}")
            
#         return None

#     async def connect_twitter(self) -> Optional[str]:
#         """
#         Connecting to Twitter
        
#         Returns:
#             Authorization code or None if failed
#         """
#         try:
#             twitter_client = await self.get_account()
#             if not twitter_client:
#                 log.error(
#                     f"Account: {self.wallet_address} | Failed to get Twitter account | "
#                     f"auth_token: {self.account.auth_tokens_twitter}"
#                 )
#                 return None

#             session = twitter_client.session
#             headers = self._build_headers(twitter_client.ct0)
            
#             auth_response = session.get(
#                 f"https://{self.config.API_DOMAIN}{self.config.OAUTH2_PATH}",
#                 params=self._build_auth_params(),
#                 headers=headers
#             )
#             auth_response.raise_for_status()
#             auth_code = auth_response.json()['auth_code']

#             approve_response = session.post(
#                 f"https://{self.config.API_DOMAIN}{self.config.OAUTH2_PATH}",
#                 params={"approval": "true", "code": auth_code},
#                 headers=headers
#             )
#             approve_response.raise_for_status()
            
#             redirect_uri = approve_response.json()['redirect_uri']
#             return self._extract_code_from_redirect(redirect_uri)

#         except Exception as error:
#             log.error(f"Account: {self.wallet_address} | Twitter connection error: {error}")
#             return None