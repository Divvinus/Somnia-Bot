import asyncio
import json
from functools import cached_property
from typing import Dict, Optional, Union

from core.api import *
from logger import log
from models import Account
from utils import generate_username, random_sleep
from config.settings import (
    sleep_after_referral_bind,
    sleep_after_username_creation,
    sleep_after_discord_connection,
    sleep_after_twitter_connection
)


class ProfileModule(SomniaClient):
    def __init__(self, account: Account, referral_code: str = ""):
        super().__init__(account)
        self.twitter_worker = TwitterClient(account)
        self.account = account
        self.referral_code = referral_code
        self._me_info_cache: Optional[Dict] = None
        self._discord_worker = None

    @property
    def discord_worker(self) -> Optional[DiscordClient]:
        if self._discord_worker is None and self.account.auth_tokens_discord:
            self._discord_worker = DiscordClient(self.account)
        return self._discord_worker

    @cached_property
    def _base_headers(self) -> Dict[str, str]:
        return {
            "authority": "quest.somnia.network",
            "accept": "application/json",
            "dnt": "1",
            "authorization": f"Bearer {self._authorization_token}",
            "content-type": "application/json",
            "origin": "https://quest.somnia.network",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    async def create_username(self) -> bool:
        log.info(f"Account {self.wallet_address} | Trying to set the username...")
        headers = {
            **self._base_headers,
            "referer": "https://quest.somnia.network/account",
        }

        while True:
            try:
                username = generate_username()
                response = await self.send_request(
                    request_type="PATCH",
                    method="/users/username",
                    json_data={"username": username},
                    headers=headers,
                    verify=False,
                )

                if response.status_code in [200, 201, 204]:
                    log.info(f"Account {self.wallet_address} | Created username {username}")
                    self._me_info_cache = None
                    return True

                log.error(
                    f"Account {self.wallet_address} | Failed to create username {username}. Status: {response.status_code}. Let's try again..."
                )
                await asyncio.sleep(2)

            except Exception as error:
                log.error(f"Account {self.wallet_address} | Error: {error}")
                await asyncio.sleep(2)

    async def connect_discord_account(self) -> bool:
        log.info(f"Account {self.wallet_address} | Trying to link a Discord account to a website...")
        try:
            code = await self.discord_worker._request_authorization()
            if not code:
                return False

            headers = {
                **self._base_headers,
                "accept": "*/*",
                "referer": f"https://quest.somnia.network/discord?code={code}&state=eyJ0eXBlIjoiQ09OTkVDVF9ESVNDT1JEIn0%3D",
            }

            response = await self.send_request(
                request_type="POST",
                method="/auth/socials",
                headers=headers,
                json_data={"code": code, "provider": "discord"}
            )

            success = response.status_code == 200 and response.json().get("success", False)
            if success:
                log.success(f"Account {self.wallet_address} | Discord account connected successfully")
                self._me_info_cache = None
            else:
                log.error(f"Account {self.wallet_address} | Failed to connect Discord account")
                log.error(f"Account {self.wallet_address} | Error: {response}")

            return success

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error: {e}")
            return False

    async def connect_twitter_account(self) -> bool:
        log.info(f"Account {self.wallet_address} | Trying to connect Twitter account...")
        try:
            code = await self.twitter_worker.connect_twitter()
            if not code:
                return False

            headers = {
                **self._base_headers,
                "dnt": "1",
                "referer": f"https://quest.somnia.network/twitter?state=eyJ0eXBlIjoiQ09OTkVDVF9UV0lUVEVSIn0%3D&code={code}",
            }

            json_data = {
                "code": code,
                "codeChallenge": "challenge123",
                "provider": "twitter",
            }

            response = await self.send_request(
                request_type="POST",
                method="/auth/socials",
                json_data=json_data,
                headers=headers,
            )

            success = response.status_code == 200 and response.json().get("success", False)
            if success:
                log.success(f"Account {self.wallet_address} | Twitter account connected successfully")
                self._me_info_cache = None
            else:
                log.error(f"Account {self.wallet_address} | Failed to connect Twitter account")
                log.error(f"Account {self.wallet_address} | Error: {response}")

            return success

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error: {e}")
            return False

    async def referral_bind(self) -> None:
        if not self.referral_code:
            log.error(f"Account {self.wallet_address} | Referral code not found")
            return

        try:
            payload = {"referralCode": self.referral_code, "product": "QUEST_PLATFORM"}
            message_to_sign = json.dumps(payload, separators=(",", ":"))
            signature = await self.get_signature(message_to_sign)

            headers = {
                **self._base_headers,
                "priority": "u=1, i",
                "referer": f"https://quest.somnia.network/referrals/{self.referral_code}",
            }

            json_data = {**payload, "signature": signature}

            await self.send_request(
                request_type="POST",
                method="/users/referrals",
                json_data=json_data,
                headers=headers,
                verify=False,
            )

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error binding referral: {e}")

    async def get_account_statistics(self) -> bool:
        log.info(f"Account {self.wallet_address} | Getting account statistics...")
        try:
            if not await self.onboarding():
                log.error(f"Account {self.wallet_address} | Failed to authorize on Somnia")
                return False
            await self.get_stats()
            return True
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error getting statistics: {e}")
            return False

    async def run(self) -> bool:
        log.info(f"Account {self.wallet_address} | Starting the profile module...")
        try:
            # First step - authorization
            if not await self.onboarding():
                log.error(f"Account {self.wallet_address} | Failed to authorize on Somnia")
                return False
            
            # Handle referral
            await self.referral_bind()
            log.info(f"Account {self.wallet_address} | Referral code bound to the account")
            await random_sleep(self.wallet_address, **sleep_after_referral_bind)
            
            # Get current user info
            null_fields = await self.get_me_info()
            if null_fields is None:
                return False
                         
            if "username" in null_fields:
                if not await self.create_username():
                    return False
                await random_sleep(self.wallet_address, **sleep_after_username_creation)

            # Подключить Discord, если токен доступен
            if "discordName" in null_fields and self.account.auth_tokens_discord:
                if not await self.connect_discord_account():
                    return False
                await random_sleep(self.wallet_address, **sleep_after_discord_connection)

            # Подключить Twitter, если токен доступен
            if "twitterName" in null_fields and self.account.auth_tokens_twitter:
                if not await self.connect_twitter_account():
                    return False
                await random_sleep(self.wallet_address, **sleep_after_twitter_connection)

            # Check if we need to activate referral
            referral_code = await self.get_me_info(get_referral_code=True)          
            if referral_code is None:
                await self.activate_referral()

            # Get final stats
            await self.get_stats()
            log.success(f"Account {self.wallet_address} | Profile setup completed successfully")
            return True

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error in run method: {e}")
            return False