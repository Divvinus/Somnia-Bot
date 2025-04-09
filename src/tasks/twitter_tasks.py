import twitter
import random
import asyncio

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Self

from src.models import Account
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.utils import check_twitter_error_for_invalid_token


class TwitterTasksModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, account.proxy)
        AsyncLogger.__init__(self)
        
        self.account: Account = account
        self.twitter_account: twitter.Account | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await super().__aexit__(exc_type, exc_val, exc_tb)

    @asynccontextmanager
    async def _get_twitter_client(self) -> AsyncGenerator[twitter.Client | None, None]:
        self.twitter_account = twitter.Account(auth_token=self.account.auth_tokens_twitter)
        client: twitter.Client | None = None

        try:
            await self.logger_msg(
                msg=f"Initializing Twitter client", type_msg="info", address=self.wallet_address
            )

            async with twitter.Client(
                self.twitter_account,
                proxy=str(self.account.proxy) if self.account.proxy else None
            ) as client:
                await client.update_account_info()

                await self.logger_msg(
                    msg=f"Account: {self.wallet_address} | Twitter client initialized successfully. "
                    f"Logged in as @{self.twitter_account.username}", type_msg="success"
                )

                yield client

        except Exception as error:
            await self.logger_msg(
                msg=f"Twitter client error: {error}", type_msg="error", 
                address=self.wallet_address, method_name="_get_twitter_client"
            )
            await check_twitter_error_for_invalid_token(error, self.account.auth_tokens_twitter, self.wallet_address)
            yield None

        finally:
            if client:
                await self.logger_msg(
                    msg=f"Twitter client connection closed", type_msg="info", 
                    address=self.wallet_address
                )
                
    async def retweet_tweeet_darktable(self) -> bool:
        await self.logger_msg(
            msg=f"Trying to retweet the post from Darktable", type_msg="info", 
            address=self.wallet_address
        )
        tweet_id: int = 1906754535110090831

        async with self._get_twitter_client() as client:
            if not client:
                await self.logger_msg(
                    msg=f"Failed to initialize Twitter client for retweet", type_msg="error", 
                    address=self.wallet_address, method_name="retweet_tweeet_darktable"
                )
                return False

            for attempt in range(3):
                try:
                    await asyncio.sleep(random.uniform(2, 5))

                    query_id = client._ACTION_TO_QUERY_ID['CreateRetweet']
                    url = f"{client._GRAPHQL_URL}/{query_id}/CreateRetweet"
                    
                    json_payload = {
                        "variables": {"tweet_id": tweet_id, "dark_request": False},
                        "queryId": query_id,
                    }
                    
                    try:
                        response, data = await client.request("POST", url, json=json_payload)
                        
                        if "data" in data and "create_retweet" in data["data"] and "retweet_results" in data["data"]["create_retweet"]:
                            retweet_id = data["data"]["create_retweet"]["retweet_results"]["result"]["rest_id"]
                            await self.logger_msg(
                                msg=f"Successfully retweeted. Retweet ID: {retweet_id}", type_msg="success", 
                                address=self.wallet_address
                            )
                            return True
                            
                    except Exception as api_error:
                        error_str = str(api_error)
                        if "327" in error_str or "You have already retweeted this Tweet" in error_str:
                            await self.logger_msg(
                                msg=f"You previously retweeted this tweet, so the task has already been completed", 
                                type_msg="success", address=self.wallet_address
                            )
                            return True
                        
                        is_invalid_token = await check_twitter_error_for_invalid_token(api_error, self.account.auth_tokens_twitter, self.wallet_address)
                        if is_invalid_token:
                            return False

                except Exception as outer_error:
                    await self.logger_msg(
                        msg=f"Unexpected error: {outer_error}", type_msg="error", 
                        address=self.wallet_address, method_name="retweet_tweeet_darktable"
                    )
                    if attempt == 2:
                        return False

            await self.logger_msg(
                msg=f"Failed to retweet a tweet from Darktable even after three attempts", type_msg="error", 
                address=self.wallet_address, method_name="retweet_tweeet_darktable"
            )
            return False