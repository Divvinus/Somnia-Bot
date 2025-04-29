import asyncio
from functools import cached_property
from typing import Any, Self

import orjson

from src.api import DiscordClient, SomniaClient, TelegramClient, TwitterClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import (
    generate_username,
    random_sleep,
    clear_token_after_successful_connection,
    COL_RECONNECT_DISCORD,
    COL_RECONNECT_TWITTER
)
from config.settings import (
    sleep_after_referral_bind,
    sleep_after_username_creation,
    sleep_after_discord_connection,
    sleep_after_twitter_connection,
    sleep_after_telegram_connection,
)


class ProfileModule(SomniaClient, AsyncLogger):
    def __init__(
        self,
        account: Account,
        referral_code: str | None = None,
    ) -> None:
        SomniaClient.__init__(self, account)
        AsyncLogger.__init__(self)

        self.account: Account = account
        self.referral_code: str | None = referral_code
        self._me_info_cache: dict[str, Any] | None = None

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

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        tasks = [
            worker.__aexit__(exc_type, exc_val, exc_tb)
            for worker in (
                self.twitter_worker,
                self.telegram_worker,
                self._discord_worker,
            )
            if worker
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await super().__aexit__(exc_type, exc_val, exc_tb)

    @property
    def discord_worker(self) -> DiscordClient | None:
        if self._discord_worker is None and self.account.auth_tokens_discord:
            self._discord_worker = DiscordClient(self.account)
        return self._discord_worker

    @discord_worker.setter
    def discord_worker(self, client: DiscordClient | None) -> None:
        self._discord_worker = client

    @cached_property
    def _base_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "authorization": f"Bearer {self._token}",
            "content-type": "application/json",
            "origin": "https://quest.somnia.network",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    async def create_username(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg="Trying to set the username...",
            type_msg="info",
            address=self.wallet_address,
        )

        headers = {
            **self._base_headers,
            "referer": "https://quest.somnia.network/account",
        }

        for attempt in range(1, 4):
            try:
                username = generate_username()
                response = await self.send_request(
                    request_type="PATCH",
                    method="/users/username",
                    json_data={"username": username},
                    headers=headers,
                    verify=False,
                )

                status = response.get("status_code")
                if status in (200, 201, 204):
                    await self.logger_msg(
                        msg=f"Created username {username}",
                        type_msg="success",
                        address=self.wallet_address,
                    )
                    self._me_info_cache = None
                    return True, "Successfully created username"

                await self.logger_msg(
                    msg=(
                        f"Attempt {attempt}: Failed to create username {username}. "
                        f"Status: {status}. Retrying..."
                    ),
                    type_msg="warning",
                    address=self.wallet_address,
                    method_name="create_username",
                )
                await random_sleep(self.wallet_address, **sleep_after_username_creation)

            except Exception as error:
                err_msg = str(error)
                await self.logger_msg(
                    msg=f"Error creating username: {err_msg}",
                    type_msg="error",
                    address=self.wallet_address,
                    method_name="create_username",
                )
                return False, err_msg

        return False, "Failed to create username after 3 attempts"

    async def connect_telegram_account(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg="Linking Telegram account...",
            type_msg="info",
            address=self.wallet_address,
        )

        if not self.telegram_worker:
            return False, "Telegram worker not initialized"

        try:
            code = await self.telegram_worker.run()
            if not code:
                raise RuntimeError("No code from Telegram worker")

            payload = {"encodedDetails": code, "provider": "telegram"}
            headers = {
                **self._base_headers,
                "accept": "*/*",
                "referer": "https://quest.somnia.network/telegram",
            }

            response = await self.send_request(
                request_type="POST",
                method="/auth/socials",
                json_data=payload,
                headers=headers,
                verify=False,
            )

            status = response.get("status_code")
            success = status == 200 and response.get("data", {}).get("success", False)
            if success:
                await self.logger_msg(
                    msg="Telegram account connected successfully",
                    type_msg="success",
                    address=self.wallet_address,
                )
                self._me_info_cache = None
                return True, "Telegram connected"

            if status == 500 and response.get("text", "").find("Internal server error") != -1:
                await self.logger_msg(
                    msg="Telegram account already bound to another wallet in Somnia",
                    type_msg="warning",
                    address=self.wallet_address,
                    method_name="connect_telegram_account",
                )
                return False, "Telegram account already bound to another wallet"

            err_text = response.get("text", "")
            await self.logger_msg(
                msg=(f"Telegram connection failed: {status}, {err_text}"),
                type_msg="error",
                address=self.wallet_address,
                method_name="connect_telegram_account",
            )
            return False, "Failed to connect Telegram"

        except Exception as e:
            err_msg = str(e)
            await self.logger_msg(
                msg=f"Error connecting Telegram: {err_msg}",
                type_msg="error",
                address=self.wallet_address,
                method_name="connect_telegram_account",
            )
            return False, err_msg

    async def connect_discord_account(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg="Linking Discord account...",
            type_msg="info",
            address=self.wallet_address,
        )

        if not self._discord_worker:
            return False, "Discord worker not initialized"

        try:
            code = await self._discord_worker.request_authorization()
            if not code:
                raise RuntimeError("No code from Discord worker")

            headers = {
                **self._base_headers,
                "accept": "*/*",
                "referer": (
                    f"https://quest.somnia.network/discord?code={code}"
                    "&state=eyJ0eXBlIjoiQ09OTkVDVF9ESVNDT1JEIn0%3D"
                ),
            }
            payload = {"code": code, "provider": "discord"}

            response = await self.send_request(
                request_type="POST",
                method="/auth/socials",
                json_data=payload,
                headers=headers,
                verify=False,
            )

            status = response.get("status_code")
            success = status == 200 and response.get("data", {}).get("success", False)
            if success:
                await self.logger_msg(
                    msg="Discord account connected successfully",
                    type_msg="success",
                    address=self.wallet_address,
                )
                self._me_info_cache = None
                
                if self.account.auth_tokens_discord:
                    await clear_token_after_successful_connection(
                        token=self.account.auth_tokens_discord,
                        token_column_name=COL_RECONNECT_DISCORD,
                        wallet_address=self.wallet_address
                    )
                    
                return True, "Discord connected"

            if status == 500 and response.get("text", "").find("Internal server error") != -1:
                await self.logger_msg(
                    msg="Discord account already bound to another wallet in Somnia",
                    type_msg="warning",
                    address=self.wallet_address,
                    method_name="connect_discord_account",
                )
                return False, "Discord account already bound to another wallet"

            err_text = response.get("text", "")
            await self.logger_msg(
                msg=(f"Discord connection failed: {status}, {err_text}"),
                type_msg="error",
                address=self.wallet_address,
                method_name="connect_discord_account",
            )
            return False, "Failed to connect Discord"

        except Exception as e:
            err_msg = str(e)
            await self.logger_msg(
                msg=f"Error connecting Discord: {err_msg}",
                type_msg="error",
                address=self.wallet_address,
                method_name="connect_discord_account",
            )
            return False, err_msg

    async def connect_twitter_account(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg="Linking Twitter account...",
            type_msg="info",
            address=self.wallet_address,
        )

        if not self.twitter_worker:
            return False, "Twitter worker not initialized"

        try:
            code = await self.twitter_worker.connect_twitter()
            if not code:
                raise RuntimeError("No code from Twitter worker")

            headers = {
                **self._base_headers,
                "dnt": "1",
                "referer": (
                    f"https://quest.somnia.network/twitter?state="
                    "eyJ0eXBlIjoiQ09OTkVDVF9UV0lUVEVSIn0%3D&code={code}"
                ),
            }
            payload = {"code": code, "provider": "twitter", "codeChallenge": "challenge123"}

            response = await self.send_request(
                request_type="POST",
                method="/auth/socials",
                json_data=payload,
                headers=headers,
                verify=False,
            )

            status = response.get("status_code")
            success = status == 200 and response.get("data", {}).get("success", False)
            if success:
                await self.logger_msg(
                    msg="Twitter account connected successfully",
                    type_msg="success",
                    address=self.wallet_address,
                )
                self._me_info_cache = None
                
                if self.account.auth_tokens_twitter:
                    await clear_token_after_successful_connection(
                        token=self.account.auth_tokens_twitter,
                        token_column_name=COL_RECONNECT_TWITTER,
                        wallet_address=self.wallet_address
                    )
                    
                return True, "Twitter connected"

            if status == 500 and response.get("text", "").find("Internal server error") != -1:
                await self.logger_msg(
                    msg="Twitter account already bound to another wallet in Somnia",
                    type_msg="warning",
                    address=self.wallet_address,
                    method_name="connect_twitter_account",
                )
                return False, "Twitter account already bound to another wallet"

            err_text = response.get("text", "")
            await self.logger_msg(
                msg=(f"Twitter connection failed: {status}, {err_text}"),
                type_msg="error",
                address=self.wallet_address,
                method_name="connect_twitter_account",
            )
            return False, "Failed to connect Twitter"

        except Exception as e:
            err_msg = str(e)
            await self.logger_msg(
                msg=f"Error connecting Twitter: {err_msg}",
                type_msg="error",
                address=self.wallet_address,
                method_name="connect_twitter_account",
            )
            return False, err_msg

    async def referral_bind(self) -> tuple[bool, str]:
        if not self.referral_code:
            await self.logger_msg(
                msg="Referral code not provided",
                type_msg="warning",
                address=self.wallet_address,
                method_name="referral_bind",
            )
            return False, "Referral code not found"

        try:
            payload = {"referralCode": self.referral_code, "product": "QUEST_PLATFORM"}
            signature = await self.get_signature(orjson.dumps(payload).decode())

            headers = {
                **self._base_headers,
                "priority": "u=1, i",
                "referer": f"https://quest.somnia.network/referrals/{self.referral_code}",
            }
            json_data = {**payload, "signature": f"0x{signature}"}

            response = await self.send_request(
                request_type="POST",
                method="/users/referrals",
                json_data=json_data,
                headers=headers,
                verify=False,
            )

            status = response.get("status_code")
            if status == 500:
                await self.logger_msg(
                    msg="Referral code already bound",
                    type_msg="success",
                    address=self.wallet_address,
                )
                return True, "Referral was already bound"

            if status == 200:
                await self.logger_msg(
                    msg="Referral code bound successfully",
                    type_msg="success",
                    address=self.wallet_address,
                )
                return True, "Referral bound successfully"

            await self.logger_msg(
                msg=f"Referral bind failed: {response}",
                type_msg="error",
                address=self.wallet_address,
                method_name="referral_bind",
            )
            return False, "Failed to bind referral"

        except Exception as e:
            err_msg = str(e)
            await self.logger_msg(
                msg=f"Error binding referral: {err_msg}",
                type_msg="error",
                address=self.wallet_address,
                method_name="referral_bind",
            )
            return False, err_msg

    async def get_account_statistics(self) -> tuple[bool, str]:
        try:
            status, result = await self.onboarding()
            if not status:
                raise RuntimeError(result)

            stats = await self.get_stats()
            if stats:
                return True, stats
            else:
                return False, f"Failed to get statistics: {stats}"

        except Exception as e:
            err_msg = str(e)
            await self.logger_msg(
                msg=f"Error getting statistics: {err_msg}",
                type_msg="error",
                address=self.wallet_address,
                method_name="get_account_statistics",
            )
            return False, err_msg

    async def run(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg="Starting profile setup...",
            type_msg="info",
            address=self.wallet_address,
        )
        errors: list[str] = []

        try:
            # Authorize
            status, result = await self.onboarding()
            if not status:
                raise RuntimeError(result)

            # Bind referral
            if self.referral_code:
                await self.referral_bind()
                await random_sleep(self.wallet_address, **sleep_after_referral_bind)

            # Ensure user info
            null_fields = await self.get_me_info()
            if null_fields is None:
                return True, "User profile is complete"

            # Username
            if "username" in null_fields:
                ok, msg = await self.create_username()
                if not ok:
                    errors.append(msg)
                else:
                    await random_sleep(
                        self.wallet_address,
                        **sleep_after_username_creation,
                    )

            # Telegram
            if "telegramName" in null_fields and self.account.telegram_session:
                ok, msg = await self.connect_telegram_account()
                if not ok:
                    errors.append(msg)
                else:
                    await random_sleep(
                        self.wallet_address,
                        **sleep_after_telegram_connection,
                    )

            # Discord
            if (self.account.auth_tokens_discord
                    and ("discordName" in null_fields or self.account.reconnect_discord)):
                ok, msg = await self.connect_discord_account()
                if not ok:
                    errors.append(msg)
                else:
                    await random_sleep(
                        self.wallet_address,
                        **sleep_after_discord_connection,
                    )

            # Twitter
            if (self.account.auth_tokens_twitter
                    and ("twitterName" in null_fields or self.account.reconnect_twitter)):
                ok, msg = await self.connect_twitter_account()
                if not ok:
                    errors.append(msg)
                else:
                    await random_sleep(
                        self.wallet_address,
                        **sleep_after_twitter_connection,
                    )

            # Activate referral if needed
            referral_code = await self.get_me_info(get_referral_code=True)
            if referral_code is None:
                ok, msg = await self.activate_referral()
                if not ok:
                    errors.append(msg)

            if errors:
                return True, "; ".join(errors)

            await self.logger_msg(
                msg="Profile setup completed successfully",
                type_msg="success",
                address=self.wallet_address,
            )
            return True, "Profile setup successful"

        except Exception as e:
            err_msg = str(e)
            await self.logger_msg(
                msg=f"Error in run: {err_msg}",
                type_msg="error",
                address=self.wallet_address,
                method_name="run",
            )
            return False, err_msg