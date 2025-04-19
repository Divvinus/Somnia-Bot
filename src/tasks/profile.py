import asyncio
import orjson
from functools import cached_property
from typing import Self

from src.api import (
    SomniaClient,
    TwitterClient,
    TelegramClient,
    DiscordClient
)
from src.logger import AsyncLogger
from src.models import Account
from src.utils import generate_username, random_sleep
from config.settings import (
    sleep_after_referral_bind,
    sleep_after_username_creation,
    sleep_after_discord_connection,
    sleep_after_twitter_connection,
    sleep_after_telegram_connection
)


class ProfileModule(SomniaClient, AsyncLogger):
    def __init__(self, account: Account, referral_code: str | None = None):
        SomniaClient.__init__(self, account)
        AsyncLogger.__init__(self)
        
        self.account: Account = account
        self.referral_code: str | None = referral_code            
        self._me_info_cache: dict | None = None
        
        self.twitter_worker: TwitterClient | None = None
        self.telegram_worker: TelegramClient | None = None
        self._discord_worker: DiscordClient | None = None

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        if self.account.telegram_session:
            self.telegram_worker = TelegramClient(self.account)
            await self.telegram_worker.__aenter__()
        
        if self.account.auth_tokens_twitter:
            self.twitter_worker = TwitterClient(self.account)
            await self.twitter_worker.__aenter__()
        
        if self.account.auth_tokens_discord:
            self._discord_worker = DiscordClient(self.account)
            await self._discord_worker.__aenter__()
            
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        cleanup_tasks = []
        
        if self.twitter_worker:
            cleanup_tasks.append(self.twitter_worker.__aexit__(exc_type, exc_val, exc_tb))
        if self.telegram_worker:
            cleanup_tasks.append(self.telegram_worker.__aexit__(exc_type, exc_val, exc_tb))
        if self._discord_worker:
            cleanup_tasks.append(self._discord_worker.__aexit__(exc_type, exc_val, exc_tb))
        
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        await super().__aexit__(exc_type, exc_val, exc_tb)

    @property
    def discord_worker(self) -> DiscordClient | None:
        if self._discord_worker is None and self.account.auth_tokens_discord:
            self._discord_worker = DiscordClient(self.account)
        return self._discord_worker

    @discord_worker.setter
    def discord_worker(self, value: DiscordClient | None):
        self._discord_worker = value

    @cached_property
    def _base_headers(self) -> dict[str, str]:
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
        await self.logger_msg(
            msg=f"Trying to set the username...", 
            type_msg="info", address=self.wallet_address
        )
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
                    await self.logger_msg(
                        msg=f"Created username {username}", 
                        type_msg="success", address=self.wallet_address
                    )
                    self._me_info_cache = None
                    return True, "Successfully created username"

                await self.logger_msg(
                    msg=f"Failed to create username {username}. Status: {response.get('status_code')}. Let's try again...", 
                    type_msg="warning", address=self.wallet_address, method_name="create_username"
                )
                await random_sleep(self.wallet_address, **sleep_after_username_creation)

            except Exception as error:
                await self.logger_msg(
                    msg=f"Error: {str(error)}", type_msg="error", 
                    address=self.wallet_address, method_name="create_username"
                )
                return False, str(error)
            
        return False, "Failed to create username even with three attempts"

    async def connect_telegram_account(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Trying to link a Telegram account to a website...", 
            type_msg="info", address=self.wallet_address
        )
        try:
            code = await self.telegram_worker.run()
            if not code:
                await self.logger_msg(
                    msg=f"No code received from Telegram worker", 
                    type_msg="error", address=self.wallet_address, method_name="connect_telegram_account"
                )
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
                await self.logger_msg(
                    msg=f"Telegram account connected successfully", 
                    type_msg="success", address=self.wallet_address
                )
                self._me_info_cache = None
                return True, "Successfully connected Telegram account"
            else:
                status_code = response.get('status_code')
                error_text = response.get('text', '')
                await self.logger_msg(
                    msg=f"Error connecting Telegram: Status {status_code}, Response: {error_text}", 
                    type_msg="error", address=self.wallet_address, method_name="connect_telegram_account"
                )
                return False, "Failed to connect Telegram account"
                    
        except Exception as e:
            await self.logger_msg(
                msg=f"Error: {str(e)}", type_msg="error", 
                address=self.wallet_address, method_name="connect_telegram_account"
            )
            return False, str(e)

    async def connect_discord_account(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Trying to link a Discord account to a website...", 
            type_msg="info", address=self.wallet_address
        )
        try:
            code = await self._discord_worker._request_authorization()
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
                await self.logger_msg(
                    msg=f"Discord account connected successfully", 
                    type_msg="success", address=self.wallet_address
                )
                self._me_info_cache = None
            else:
                status_code = response.get('status_code')
                error_text = response.get('text', '')
                await self.logger_msg(
                    msg=f"Error connecting Discord: Status {status_code}, Response: {error_text}", 
                    type_msg="error", address=self.wallet_address, method_name="connect_discord_account"
                )

            return success, "Successfully connected Discord account" if success else f"Failed to connect Discord account (Status: {response.get('status_code')})"

        except Exception as e:
            await self.logger_msg(
                msg=f"Error: {str(e)}", type_msg="error", 
                address=self.wallet_address, method_name="connect_discord_account"
            )
            return False, str(e)

    async def connect_twitter_account(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Trying to connect Twitter account...", 
            type_msg="info", address=self.wallet_address
        )
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

            result = (
                response.get('status_code') == 200 
                and response.get('data', {}).get("success", False)
            )
            if result:
                msg = f"Twitter account connected successfully"
                await self.logger_msg(
                    msg=msg, 
                    type_msg="success", address=self.wallet_address
                )
                self._me_info_cache = None
            else:
                status_code = response.get('status_code')
                error_text = response.get('text', '')
                await self.logger_msg(
                    msg=f"Error connecting Twitter: Status {status_code}, Response: {error_text}", 
                    type_msg="error", address=self.wallet_address, method_name="connect_twitter_account"
                )

            return result, msg if result else f"Failed to connect Twitter account (Status: {response.get('status_code')})"

        except Exception as e:
            await self.logger_msg(
                msg=f"Error: {str(e)}", 
                type_msg="error", address=self.wallet_address, method_name="connect_twitter_account"
            )
            return False, str(e)
        
    async def referral_bind(self) -> tuple[bool, str]:
        if not self.referral_code:
            await self.logger_msg(
                msg=f"Referral code not found", 
                type_msg="warning", address=self.wallet_address, method_name="referral_bind"
            )
            return False, "Referral code not found"

        try:
            payload = {"referralCode": self.referral_code, "product": "QUEST_PLATFORM"}
            signature = await self.get_signature(orjson.dumps(payload).decode('utf-8'))

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
            
            if response.get('status_code') == 500:
                await self.logger_msg(
                    msg=f"The referral code has already been previously linked", 
                    type_msg="success", address=self.wallet_address
                )
                return True, "Successfully bound referral code"
            
            if response.get('status_code') == 200:
                await self.logger_msg(
                    msg=f"Referral code bound to the account", 
                    type_msg="success", address=self.wallet_address
                )
                return True, "Successfully bound referral code"
            else:
                await self.logger_msg(
                    msg=f"Error: {response}", 
                    type_msg="error", address=self.wallet_address, method_name="referral_bind"
                )
                return False, "Failed to bind referral code"

        except Exception as e:
            await self.logger_msg(
                msg=f"Error binding referral: {str(e)}", 
                type_msg="error", address=self.wallet_address, method_name="referral_bind"
            )
            return False, str(e)

    async def get_account_statistics(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Getting account statistics...", 
            type_msg="info", address=self.wallet_address
        )
        try:
            status, result = await self.onboarding()
            if not status:
                await self.logger_msg(
                    msg=f"Failed to authorize on Somnia", 
                    type_msg="error", address=self.wallet_address, method_name="get_account_statistics"
                )
                return status, result
            await self.get_stats()
            return True, "Successfully got account statistics"
        except Exception as e:
            await self.logger_msg(
                msg=f"Error getting statistics: {str(e)}", 
                type_msg="error", address=self.wallet_address, method_name="get_account_statistics"
            )
            return False, str(e)

    async def run(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Starting the profile module...", 
            type_msg="info", address=self.wallet_address
        )
        error_messages = []
        try:
            await self.logger_msg(
                msg=f"Starting the onboarding process...", 
                type_msg="info", address=self.wallet_address
            )
            status, result = await self.onboarding()
            if not status:
                await self.logger_msg(
                    msg=f"Failed to authorize on Somnia", 
                    type_msg="error", address=self.wallet_address, method_name="run"
                )
                return False, result

            await self.logger_msg(
                msg=f"Binding the referral code...", 
                type_msg="info", address=self.wallet_address
            )
            if self.referral_code:
                await self.referral_bind()
                await random_sleep(self.wallet_address, **sleep_after_referral_bind)

            await self.logger_msg(
                msg=f"Getting the current user info...", 
                type_msg="info", address=self.wallet_address
            )
            null_fields = await self.get_me_info()
            if null_fields is None:
                await self.logger_msg(
                    msg=f"Profile setup completed successfully", 
                    type_msg="success", address=self.wallet_address
                )
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
                return True, combined_error
            else:
                await self.logger_msg(
                    msg=f"Profile setup completed successfully", 
                    type_msg="success", address=self.wallet_address
                )
                return True, "Successfully setup profile"

        except Exception as e:
            await self.logger_msg(
                msg=f"Error in run method: {str(e)}", 
                type_msg="error", address=self.wallet_address, method_name="run"
            )
            return False, str(e)