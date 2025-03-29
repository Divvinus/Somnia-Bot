import asyncio
import json
from functools import cached_property
from typing import Dict, Optional

from core.api import *
from logger import log
from models import Account
from utils import generate_username, random_sleep
from config.settings import (
    sleep_after_referral_bind,
    sleep_after_username_creation,
    sleep_after_discord_connection,
    sleep_after_twitter_connection,
    sleep_after_telegram_connection
)


class ProfileModule(SomniaClient):
    def __init__(self, account: Account, referral_code: str | None = None):
        super().__init__(account)
        self.twitter_worker = TwitterClient(account)
        self.telegram_worker = TelegramClient(account)
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
            "accept": "application/json",
            "authorization": f"Bearer {self._authorization_token}",
            "content-type": "application/json",
            "origin": "https://quest.somnia.network",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    async def create_username(self) -> tuple[bool, str]:
        log.info(f"Account {self.wallet_address} | Trying to set the username...")
        headers = {
            **self._base_headers,
            "referer": "https://quest.somnia.network/account",
        }

        for _ in range(3):
            try:
                username = generate_username()
                response = await self.send_request(
                    request_type="PATCH",
                    method="/users/username",
                    json_data={"username": username},
                    headers=headers,
                    verify=False,
                )

                if response.get('status_code') in [200, 201, 204]:
                    log.info(f"Account {self.wallet_address} | Created username {username}")
                    self._me_info_cache = None
                    return True, "Successfully created username"

                log.warning(
                    f"Account {self.wallet_address} | Failed to create username {username}. Status: {response.get('status_code')}. Let's try again..."
                )
                await random_sleep(self.wallet_address, **sleep_after_username_creation)

            except Exception as error:
                log.error(f"Account {self.wallet_address} | Error: {str(error)}")
                return False, str(error)
            
        return False, "Failed to create username even with three attempts"

    async def connect_telegram_account(self) -> tuple[bool, str]:
        log.info(f"Account {self.wallet_address} | Trying to link a Telegram account to a website...")
        try:
            code = await self.telegram_worker.run()
            if not code:
                log.error(f"Account {self.wallet_address} | No code received from Telegram worker")
                return False, "No code received from Telegram worker"
            
            json_data = {
                'encodedDetails': code,
                'provider': 'telegram',
            }

            headers = {
                **self._base_headers,
                "accept": "*/*",
                "referer": f"https://quest.somnia.network/telegram",
            }
            
            response = await self.send_request(
                request_type="POST",
                method="/auth/socials",
                json_data=json_data,
                headers=headers,
                verify=False
            )
            
            success = (
                response.get('status_code') == 200 
                and response.get('data', {}).get("success", False)
            )
            if success:
                log.success(f"Account {self.wallet_address} | Telegram account connected successfully")
                self._me_info_cache = None
                return True, "Successfully connected Telegram account"
            else:
                log.error(f"Account {self.wallet_address} | Failed to connect Telegram account")
                log.error(f"Account {self.wallet_address} | Error: {response}")
                return False, "Failed to connect Telegram account"
                    
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error: {str(e)}")
            return False, str(e)

    async def connect_discord_account(self) -> tuple[bool, str]:
        log.info(f"Account {self.wallet_address} | Trying to link a Discord account to a website...")
        try:
            code = await self.discord_worker._request_authorization()
            if not code:
                return False, "No code received from Discord worker"

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

            success = (
                response.get('status_code') == 200 
                and response.get('data', {}).get("success", False)
            )
            if success:
                log.success(f"Account {self.wallet_address} | Discord account connected successfully")
                self._me_info_cache = None
            else:
                log.error(f"Account {self.wallet_address} | Failed to connect Discord account")
                log.error(f"Account {self.wallet_address} | Error: {response}")

            return success, "Successfully connected Discord account"

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error: {str(e)}")
            return False, str(e)

    async def connect_twitter_account(self) -> tuple[bool, str]:
        log.info(f"Account {self.wallet_address} | Trying to connect Twitter account...")
        try:
            code = await self.twitter_worker.connect_twitter()
            if not code:
                return False, "No code received from Twitter worker"

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
                verify=False
            )

            success = (
                response.get('status_code') == 200 
                and response.get('data', {}).get("success", False)
            )
            if success:
                log.success(f"Account {self.wallet_address} | Twitter account connected successfully")
                self._me_info_cache = None
            else:
                log.error(f"Account {self.wallet_address} | Failed to connect Twitter account")
                log.error(f"Account {self.wallet_address} | Error: {response}")

            return success, "Successfully connected Twitter account"

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error: {str(e)}")
            return False, str(e)
        
    async def referral_bind(self) -> tuple[bool, str]:
        if not self.referral_code:
            log.warning(f"Account {self.wallet_address} | Referral code not found")
            return False, "Referral code not found"

        try:
            payload = {"referralCode": self.referral_code, "product": "QUEST_PLATFORM"}
            message_to_sign = json.dumps(payload, separators=(",", ":"))
            signature = await self.get_signature(message_to_sign)

            headers = {
                **self._base_headers,
                "priority": "u=1, i",
                "referer": f"https://quest.somnia.network/referrals/{self.referral_code}",
            }
            
            json_data = {**payload, "signature": f'0x{signature}'}

            response = await self.send_request(
                request_type="POST",
                method="/users/referrals",
                json_data=json_data,
                headers=headers,
                verify=False
            )
            
            if response.get('status_code') == 200:
                log.success(f"Account {self.wallet_address} | Referral code bound to the account")
                return True, "Successfully bound referral code"
            else:
                log.error(f"Account {self.wallet_address} | Failed to bind referral code")
                log.error(f"Account {self.wallet_address} | Error: {response}")
                return False, "Failed to bind referral code"

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error binding referral: {str(e)}")
            return False, str(e)

    async def get_account_statistics(self) -> tuple[bool, str]:
        log.info(f"Account {self.wallet_address} | Getting account statistics...")
        try:
            status, result = await self.onboarding()
            if not status:
                log.error(f"Account {self.wallet_address} | Failed to authorize on Somnia")
                return status, result
            await self.get_stats()
            return True, "Successfully got account statistics"
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error getting statistics: {str(e)}")
            return False, str(e)

    async def run(self) -> tuple[bool, str]:
        log.info(f"Account {self.wallet_address} | Starting the profile module...")
        error_messages = []
        try:
            log.info(f"Account {self.wallet_address} | Starting the onboarding process...")
            status, result = await self.onboarding()
            if not status:
                log.error(f"Account {self.wallet_address} | Failed to authorize on Somnia")
                return False, result

            log.info(f"Account {self.wallet_address} | Binding the referral code...")
            if self.referral_code:
                await self.referral_bind()
                await random_sleep(self.wallet_address, **sleep_after_referral_bind)

            log.info(f"Account {self.wallet_address} | Getting the current user info...")
            null_fields = await self.get_me_info()
            if null_fields is None:
                log.success(f"Account {self.wallet_address} | Profile setup completed successfully")
                return True, "Successfully got the current user info"

            if "username" in null_fields:
                status, result = await self.create_username()
                if not status:
                    error_messages.append(result)
                else:
                    await random_sleep(self.wallet_address, **sleep_after_username_creation)

            if not self.account.telegram_session:
                error_messages.append("Telegram session not found")
            if "telegramName" in null_fields and self.account.telegram_session:
                status, result = await self.connect_telegram_account()
                if not status:
                    error_messages.append(result)
                else:
                    await random_sleep(self.wallet_address, **sleep_after_telegram_connection)

            if not self.account.auth_tokens_discord:
                error_messages.append("Discord auth tokens not found")
            if "discordName" in null_fields and self.account.auth_tokens_discord:
                status, result = await self.connect_discord_account()
                if not status:
                    error_messages.append(result)
                else:
                    await random_sleep(self.wallet_address, **sleep_after_discord_connection)

            if not self.account.auth_tokens_twitter:
                error_messages.append("Twitter auth tokens not found")
            if "twitterName" in null_fields and self.account.auth_tokens_twitter:
                status, result = await self.connect_twitter_account()
                if not status:
                    error_messages.append(result)
                else:
                    await random_sleep(self.wallet_address, **sleep_after_twitter_connection)

            referral_code = await self.get_me_info(get_referral_code=True)
            if referral_code is None:
                status, result = await self.activate_referral()
                if not status:
                    error_messages.append(result)

            if error_messages:
                combined_error = "; ".join(error_messages)
                log.error(f"Account {self.wallet_address} | Profile setup completed with errors: {combined_error}")
                return True, combined_error
            else:
                log.success(f"Account {self.wallet_address} | Profile setup completed successfully")
                return True, "Successfully setup profile"

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error in run method: {str(e)}")
            return False, str(e)