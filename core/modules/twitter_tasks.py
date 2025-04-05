import twitter
import random
import asyncio

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from models import Account
from core.wallet import Wallet
from logger import log


class TwitterTasksModule(Wallet):
    def __init__(self, account: Account) -> None:
        super().__init__(account.private_key, account.proxy)
        self.account: Account = account
        self.twitter_account: twitter.Account | None = None
        
    @asynccontextmanager
    async def _get_twitter_client(self) -> AsyncGenerator[twitter.Client | None, None]:
        self.twitter_account = twitter.Account(auth_token=self.account.auth_tokens_twitter)
        client: twitter.Client | None = None

        try:
            log.info(f"Account: {self.wallet_address} | Initializing Twitter client")

            async with twitter.Client(
                self.twitter_account,
                proxy=str(self.account.proxy) if self.account.proxy else None
            ) as client:
                await client.update_account_info()

                log.success(
                    f"Account: {self.wallet_address} | Twitter client initialized successfully. "
                    f"Logged in as @{self.twitter_account.username}"
                )

                yield client

        except Exception as error:
            log.error(f"Account: {self.wallet_address} | Twitter client error: {error}")
            yield None

        finally:
            if client:
                log.info(f"Account: {self.wallet_address} | Twitter client connection closed")
                
    
    async def retweet_tweeet_darktable(self) -> bool:
        log.info(f"Account: {self.wallet_address} | Trying to retweet the post from Darktable")
        tweet_id: int = 1906754535110090831

        async with self._get_twitter_client() as client:
            if not client:
                log.error(f"Account: {self.wallet_address} | Failed to initialize Twitter client for retweet")
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
                            log.success(f"Account: {self.wallet_address} | Successfully retweeted. Retweet ID: {retweet_id}")
                            return True
                            
                    except Exception as api_error:
                        error_str = str(api_error)
                        if "327" in error_str or "You have already retweeted this Tweet" in error_str:
                            log.success(f"Account: {self.wallet_address} | You previously retweeted this tweet, so the task has already been completed")
                            return True

                except Exception as outer_error:
                    log.error(f"Account: {self.wallet_address} | Unexpected error: {outer_error}")
                    if attempt == 2:
                        return False

            log.error(f"Account: {self.wallet_address} | Failed to retweet a tweet from Darktable even after three attempts")
            return False