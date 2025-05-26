import twitter

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Self

from src.models import Account
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.utils import check_twitter_error_for_invalid_token


class TwitterWorker(Wallet, AsyncLogger):
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
                    msg=f"Twitter client connection closed", type_msg="debug", 
                    address=self.wallet_address
                )
                
    async def retweet_tweet(self, tweet_id: int) -> bool:
        await self.logger_msg(
            msg=f"Trying to retweet the post with ID: {tweet_id}", type_msg="info", 
            address=self.wallet_address
        )

        async with self._get_twitter_client() as client:
            if not client:
                return False

            for attempt in range(3):
                try:
                    await self.logger_msg(
                        msg=f"Retweet attempt {attempt+1}/3 for tweet ID: {tweet_id}", 
                        type_msg="info", address=self.wallet_address
                    )
                    
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
                        address=self.wallet_address, method_name="retweet_tweet"
                    )
                    if attempt == 2:
                        return False

            await self.logger_msg(
                msg=f"Failed to retweet a tweet even after three attempts", type_msg="error", 
                address=self.wallet_address, method_name="retweet_tweet"
            )
            return False
        
    async def like_tweet(self, tweet_id: int) -> bool:
        await self.logger_msg(
            msg=f"Trying to like the post with ID: {tweet_id}", 
            type_msg="info", 
            address=self.wallet_address
        )
        
        async with self._get_twitter_client() as client:
            if not client:
                await self.logger_msg(
                    msg=f"Failed to initialize Twitter client for like", 
                    type_msg="error", 
                    address=self.wallet_address, 
                    method_name="like_tweet"
                )
                return False

            for attempt in range(3):
                try:
                    await self.logger_msg(
                        msg=f"Like attempt {attempt+1}/3 for tweet ID: {tweet_id}", 
                        type_msg="info", address=self.wallet_address
                    )
                    
                    query_id = client._ACTION_TO_QUERY_ID.get('FavoriteTweet')
                    url = f"{client._GRAPHQL_URL}/{query_id}/FavoriteTweet"
                    
                    json_payload = {
                        "variables": {"tweet_id": str(tweet_id)},
                        "queryId": query_id,
                    }
                    
                    try:
                        response, data = await client.request("POST", url, json=json_payload)
                        
                        if data.get("data", {}).get("favorite_tweet") == "Done":
                            await self.logger_msg(
                                msg=f"Successfully liked tweet {tweet_id}", 
                                type_msg="success", 
                                address=self.wallet_address
                            )
                            return True
                            
                    except Exception as api_error:
                        error_str = str(api_error)
                        if "139" in error_str or "Already favorited" in error_str:
                            await self.logger_msg(
                                msg=f"Tweet already liked", 
                                type_msg="success", 
                                address=self.wallet_address
                            )
                            return True
                        
                        is_invalid_token = await check_twitter_error_for_invalid_token(
                            api_error, 
                            self.account.auth_tokens_twitter, 
                            self.wallet_address
                        )
                        if is_invalid_token:
                            return False

                        await self.logger_msg(
                            msg=f"Attempt {attempt+1}/3 failed. API error: {error_str}", 
                            type_msg="error", 
                            address=self.wallet_address, 
                            method_name="like_tweet"
                        )

                except Exception as outer_error:
                    await self.logger_msg(
                        msg=f"Unexpected error: {outer_error}", 
                        type_msg="error", 
                        address=self.wallet_address, 
                        method_name="like_tweet"
                    )
                    if attempt == 2:
                        return False

            await self.logger_msg(
                msg=f"Failed to like tweet after 3 attempts", 
                type_msg="error", 
                address=self.wallet_address, 
                method_name="like_tweet"
            )
            return False
        
    async def follow_user(self, user_id: int) -> bool:
        await self.logger_msg(
            msg=f"Trying to follow user with ID: {user_id}", 
            type_msg="info", 
            address=self.wallet_address
        )
        
        async with self._get_twitter_client() as client:
            if not client:
                await self.logger_msg(
                    msg=f"Failed to initialize Twitter client for follow", 
                    type_msg="error", 
                    address=self.wallet_address, 
                    method_name="follow_user"
                )
                return False

            for attempt in range(3):
                try:
                    await self.logger_msg(
                        msg=f"Follow attempt {attempt+1}/3 for user ID: {user_id}", 
                        type_msg="info", address=self.wallet_address
                    )
                    
                    url = "https://x.com/i/api/1.1/friendships/create.json"
                    data = {
                        "include_profile_interstitial_type": "1",
                        "include_blocking": "1",
                        "include_blocked_by": "1",
                        "include_followed_by": "1",
                        "include_want_retweets": "1",
                        "include_mute_edge": "1",
                        "include_can_dm": "1",
                        "include_can_media_tag": "1",
                        "include_ext_is_blue_verified": "1",
                        "include_ext_verified_type": "1",
                        "include_ext_profile_image_shape": "1",
                        "skip_status": "1",
                        "user_id": str(user_id)
                    }
                    
                    try:
                        response, data = await client.request("POST", url, data=data)
                        
                        if "id" in data and data["id"] == user_id:
                            await self.logger_msg(
                                msg=f"Successfully followed user {user_id}", 
                                type_msg="success", 
                                address=self.wallet_address
                            )
                            return True
                            
                    except Exception as api_error:
                        error_str = str(api_error)
                        if "108" in error_str or "You are unable to follow more people at this time" in error_str:
                            await self.logger_msg(
                                msg=f"Unable to follow user {user_id}: {error_str}", 
                                type_msg="error", 
                                address=self.wallet_address, 
                                method_name="follow_user"
                            )
                            return False
                        elif "160" in error_str or "You have already requested to follow" in error_str:
                            await self.logger_msg(
                                msg=f"Already requested to follow user {user_id}", 
                                type_msg="success", 
                                address=self.wallet_address
                            )
                            return True
                        elif "162" in error_str or "You have been blocked from following this account" in error_str:
                            await self.logger_msg(
                                msg=f"Blocked from following user {user_id}", 
                                type_msg="error", 
                                address=self.wallet_address, 
                                method_name="follow_user"
                            )
                            return False
                        else:
                            is_invalid_token = await check_twitter_error_for_invalid_token(
                                api_error, 
                                self.account.auth_tokens_twitter, 
                                self.wallet_address
                            )
                            if is_invalid_token:
                                return False

                except Exception as outer_error:
                    await self.logger_msg(
                        msg=f"Unexpected error: {outer_error}", 
                        type_msg="error", 
                        address=self.wallet_address, 
                        method_name="follow_user"
                    )
                    if attempt == 2:
                        return False

            await self.logger_msg(
                msg=f"Failed to follow user after 3 attempts", 
                type_msg="error", 
                address=self.wallet_address, 
                method_name="follow_user"
            )
            return False