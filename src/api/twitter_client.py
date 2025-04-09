from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import aiohttp
from Jam_Twitter_API.account_sync import TwitterAccountSync
from Jam_Twitter_API.errors import *

from src.logger import AsyncLogger
from src.exceptions.custom_exceptions import TwitterError
from src.wallet import Wallet
from src.models import Account
from src.utils import check_twitter_error_for_invalid_token

@dataclass
class TwitterAuthConfig:
    CLIENT_ID: str = "WS1FeDNoZnlqTEw1WFpvX1laWkc6MTpjaQ"
    REDIRECT_URI: str = "https://quest.somnia.network/twitter"
    BEARER_TOKEN: str = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    API_DOMAIN: str = "twitter.com"
    OAUTH2_PATH: str = "/i/api/2/oauth2/authorize"
    REQUIRED_SCOPES: str = "users.read follows.write tweet.write like.write tweet.read"


class TwitterClient(Wallet, AsyncLogger):
    def __init__(self, account: Account):
        Wallet.__init__(self, account.private_key, account.proxy)
        AsyncLogger.__init__(self)
        
        self.account = account
        self.twitter_client = None
        self.config = TwitterAuthConfig()

    def _build_headers(self, ct0_token: str) -> dict[str, str]:
        return {
            'authority': self.config.API_DOMAIN,
            'accept': '*/*',
            'accept-language': 'ru,en-US;q=0.9,en;q=0.8',
            'authorization': f'Bearer {self.config.BEARER_TOKEN}',
            'cookie': f'auth_token={self.account.auth_tokens_twitter}; ct0={ct0_token}',
            'x-csrf-token': ct0_token,
        }

    def _build_auth_params(self) -> dict[str, str]:
        return {
            "code_challenge": "challenge123",
            "code_challenge_method": "plain",
            "client_id": self.config.CLIENT_ID,
            "redirect_uri": self.config.REDIRECT_URI,
            "response_type": "code",
            "scope": self.config.REQUIRED_SCOPES,
            "state": "eyJ0eXBlIjoiQ09OTkVDVF9UV0lUVEVSIn0="
        }

    @staticmethod
    def _extract_code_from_redirect(redirect_uri: str) -> str:
        parsed = urlparse(redirect_uri)
        query_params = parse_qs(parsed.query)
        return query_params.get('code', [''])[0]

    async def get_account(self) -> TwitterAccountSync | None:
        try:
            self.twitter_client = TwitterAccountSync.run(
                auth_token=self.account.auth_tokens_twitter,
                proxy=str(self.account.proxy),
                setup_session=True
            )
            return self.twitter_client
        except TwitterAccountSuspended as error:
            await self.logger_msg(
                msg=f"Account suspended: {error}", type_msg="error", 
                address=self.wallet_address, method_name="get_account"
            )
            await check_twitter_error_for_invalid_token(error, self.account.auth_tokens_twitter, self.wallet_address)
        except TwitterError as error:
            await self.logger_msg(
                msg=f"Twitter error: {error.error_message} | {error.error_code}", 
                type_msg="error", address=self.wallet_address, method_name="get_account"
            )
            if hasattr(error, 'error_code') and error.error_code in (32, 89, 215, 326):
                await check_twitter_error_for_invalid_token(error, self.account.auth_tokens_twitter, self.wallet_address)
        except IncorrectData as error:
            await self.logger_msg(
                msg=f"Invalid data: {error}", type_msg="error", 
                address=self.wallet_address, method_name="get_account"
            )
            await check_twitter_error_for_invalid_token(error, self.account.auth_tokens_twitter, self.wallet_address)
        except Exception as error:
            await self.logger_msg(
                msg=f"Unexpected error: {str(error)}", type_msg="error", 
                address=self.wallet_address, method_name="get_account"
            )
            await check_twitter_error_for_invalid_token(error, self.account.auth_tokens_twitter, self.wallet_address)
            
        return None

    async def connect_twitter(self) -> str | None:
        try:
            twitter_client = await self.get_account()
            if not twitter_client:
                await self.logger_msg(
                    msg=f"Failed to get Twitter account | auth_token: {self.account.auth_tokens_twitter[:5]}***", 
                    type_msg="error", address=self.wallet_address, method_name="connect_twitter"
                )
                return None

            headers = self._build_headers(twitter_client.ct0)
            
            async with aiohttp.ClientSession(headers=headers) as session:
                auth_url = f"https://{self.config.API_DOMAIN}{self.config.OAUTH2_PATH}"
                async with session.get(auth_url, params=self._build_auth_params()) as auth_response:
                    if auth_response.status != 200:
                        await self.logger_msg(
                            msg=f"Auth response error: {auth_response.status}", 
                            type_msg="error", address=self.wallet_address, method_name="connect_twitter"
                        )
                        return None
                    auth_data = await auth_response.json()
                    auth_code = auth_data['auth_code']
                
                async with session.post(
                    auth_url,
                    params={"approval": "true", "code": auth_code}
                ) as approve_response:
                    if approve_response.status != 200:
                        await self.logger_msg(
                            msg=f"Approval response error: {approve_response.status}", 
                            type_msg="error", address=self.wallet_address, method_name="connect_twitter"
                        )
                        return None
                    approve_data = await approve_response.json()
                    redirect_uri = approve_data['redirect_uri']
                    return self._extract_code_from_redirect(redirect_uri)

        except aiohttp.ClientError as error:
            await self.logger_msg(
                msg=f"Twitter HTTP error: {error}", type_msg="error", 
                address=self.wallet_address, method_name="connect_twitter"
            )
        except Exception as error:
            await self.logger_msg(
                msg=f"Twitter connection error: {str(error)}", type_msg="error", 
                address=self.wallet_address, method_name="connect_twitter"
            )
            
        return None
    
    async def close(self):
        if hasattr(self, 'twitter_client') and self.twitter_client:
            await self.twitter_client.session.close()