import json
import secrets
from typing import Tuple
import asyncio
from pathlib import Path

from eth_keys import keys
from eth_utils import to_checksum_address
from better_proxy import Proxy

from core.api import SomniaClient
from logger import log
from models import Account
from utils import random_sleep
from config.settings import (
    recruiting_threads,
    sleep_onbord_and_registration,
    sleep_between_registrations,
    sleep_before_next_stream,
    sleep_between_referral_registrations_in_stream
)


class RecruitingReferralsModule(SomniaClient):
    """Handles referral registrations for Somnia Network."""

    def __init__(self, account: Account) -> None:
        """Initialize module with account credentials."""
        super().__init__(account)
        self.proxies = []

    @staticmethod
    def generate_eth_wallet() -> Tuple[str, str]:
        """Generate a new Ethereum wallet."""
        private_key_bytes = secrets.token_bytes(32)
        private_key = keys.PrivateKey(private_key_bytes)
        public_key = private_key.public_key
        address = to_checksum_address(public_key.to_address())
        return str(private_key), address

    async def onboarding(self, private_key: str, proxy: Proxy = None) -> str:
        """Onboard a new referral account and return auth token."""
        try:
            temp_wallet = self.wallet.from_key(private_key)
            wallet_address = temp_wallet.address
            signature = await self.get_signature(
                '{"onboardingUrl":"https://quest.somnia.network"}',
                private_key=private_key,
            )
            temp_client = self
            if proxy:
                temp_account = Account(
                    private_key=self.account.private_key,
                    proxy=proxy,
                    auth_tokens_twitter=self.account.auth_tokens_twitter,
                    referral_codes=self.account.referral_codes,
                    auth_tokens_discord=self.account.auth_tokens_discord
                )
                temp_client = SomniaClient(temp_account)
            response = await temp_client.send_request(
                request_type="POST",
                method="/auth/onboard",
                json_data={
                    "signature": f"0x{signature}",
                    "walletAddress": wallet_address,
                },
                headers=self._get_base_headers(
                    custom_referer="https://quest.somnia.network/connect?redirect=%2F"
                ),
            )
            if hasattr(response, "json"):
                response = response.json()
            return response.get("token", "")
        except Exception as e:
            log.error(f"Error during onboarding: {str(e)}")
            return ""

    async def register_referral(
        self,
        token: str,
        referral_code: str,
        private_key: str,
        proxy: Proxy = None
    ) -> bool:
        """Register a new referral with given credentials."""
        self.base_url = "https://quest.somnia.network/api"
        try:
            message = {
                "referralCode": referral_code,
                "product": "QUEST_PLATFORM"
            }
            message_to_sign = json.dumps(message, separators=(",", ":"))
            signature = await self.get_signature(message_to_sign, private_key=private_key)
            headers = self._get_base_headers(
                auth=True,
                custom_referer=f"https://quest.somnia.network/referrals/{referral_code}"
            )
            headers["priority"] = "u=1, i"
            headers["authorization"] = f"Bearer {token}"
            temp_client = self
            if proxy:
                temp_account = Account(
                    private_key=self.account.private_key,
                    proxy=proxy,
                    auth_tokens_twitter=self.account.auth_tokens_twitter,
                    referral_codes=self.account.referral_codes,
                    auth_tokens_discord=self.account.auth_tokens_discord
                )
                temp_client = SomniaClient(temp_account)
                temp_client.base_url = self.base_url
            response = await temp_client.send_request(
                request_type="POST",
                method="/users/referrals",
                json_data={**message, "signature": f"0x{signature}"},
                headers=headers,
            )
            if hasattr(response, "json"):
                try:
                    response_data = response.json()
                except ValueError:
                    log.error(f"Failed to parse JSON response for referral code {referral_code}")
                    return False
            else:
                if not response:
                    log.success(f"Successfully registered referral for code {referral_code}")
                    return True
                response_data = json.loads(response) if isinstance(response, str) else response
            if isinstance(response_data, dict) and response_data.get("message") == "Success":
                log.success(f"Successfully registered referral for code {referral_code}")
                return True
            if response_data is None or (isinstance(response_data, dict) and not response_data):
                log.success(f"Successfully registered referral for code {referral_code}")
                return True
            log.error(f"Failed to register referral for code {referral_code}. Response: {response_data}")
            return False
        except Exception as e:
            log.error(f"Error processing referral for code {referral_code}: {str(e)}")
            return False

    async def save_private_key(self, private_key: str, referral_code: str) -> None:
        """Save successful referral private key to file."""
        try:
            referrals_dir = Path("config/data/referrals")
            referrals_dir.mkdir(parents=True, exist_ok=True)
            file_path = referrals_dir / "referral_private_keys.txt"
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"{private_key}:{referral_code}\n")
        except Exception as e:
            log.error(f"Failed to save private key: {str(e)}")

    async def load_proxies(self, config) -> None:
        """Load all available proxies from configuration."""
        proxy_lines = []
        try:
            proxy_file = Path("config/data/client/proxies.txt")
            if proxy_file.exists():
                with open(proxy_file, "r", encoding="utf-8") as f:
                    proxy_lines = [line.strip() for line in f.readlines() if line.strip()]
            else:
                log.warning(f"Proxy file not found at {proxy_file}")
        except Exception as e:
            log.warning(f"Failed to load proxies: {str(e)}")
        for proxy_str in proxy_lines:
            try:
                self.proxies.append(Proxy.from_str(proxy_str))
            except Exception as e:
                log.warning(f"Invalid proxy format: {proxy_str}. Error: {e}")
        if not self.proxies:
            log.warning("No valid proxies found. Will use default account proxies.")

    def get_proxy_for_thread(self, thread_index: int) -> Proxy:
        """Get proxy for specific thread."""
        if not self.proxies:
            return self.account.proxy
        return self.proxies[thread_index % len(self.proxies)]

    async def recruiting_referrals(self) -> None:
        """Process multiple referral registrations with threading."""
        from loader import config as global_config
        if not self._validate_referral_data():
            return
        referrals_dir = Path("config/data/referrals")
        referrals_dir.mkdir(parents=True, exist_ok=True)
        await self.load_proxies(global_config)
        for referral_code, required_amount in self.account.referral_codes:
            log.info(f"Starting processing for referral code: {referral_code}")
            await self._process_single_referral_code_multithread(referral_code, required_amount)
            await random_sleep("Between-Referral-Codes", **sleep_between_registrations)
            log.info(f"Completed processing for referral code: {referral_code}")

    def _validate_referral_data(self) -> bool:
        """Validate availability of referral codes."""
        if not self.account.referral_codes:
            log.info("No referral codes available")
            return False
        return True

    async def _process_single_referral_code_multithread(
        self,
        referral_code: str,
        required_amount: int
    ) -> None:
        """Process registrations for one referral code using multiple threads."""
        actual_required = required_amount
        log.info(f"Will register exactly {actual_required} referrals for code {referral_code}")
        total_threads = recruiting_threads
        registrations_per_thread = [actual_required // total_threads] * total_threads
        remainder = actual_required % total_threads
        for i in range(remainder):
            registrations_per_thread[i] += 1
        started_tasks = []
        total_completed = 0
        for thread_index in range(total_threads):
            if registrations_per_thread[thread_index] <= 0:
                continue
            thread_amount = registrations_per_thread[thread_index]
            log.info(
                f"Starting Thread {thread_index+1} for referral code {referral_code} "
                f"with target {thread_amount} registrations"
            )
            task = asyncio.create_task(
                self._thread_worker(thread_index, referral_code, thread_amount)
            )
            started_tasks.append(task)
            await random_sleep(f"Thread-Staggered-Start-{thread_index+1}", **sleep_before_next_stream)
        results = await asyncio.gather(*started_tasks)
        total_completed = sum(results)
        if total_completed < actual_required:
            log.warning(
                f"Could not complete all registrations for code {referral_code}. "
                f"Completed {total_completed}/{actual_required}"
            )
        else:
            log.success(f"Successfully completed all {actual_required} registrations for code {referral_code}")

    async def _thread_worker(
        self,
        thread_index: int,
        referral_code: str,
        thread_amount: int
    ) -> int:
        """Execute registration tasks for a single thread."""
        log.info(
            f"Thread {thread_index+1} starting with target {thread_amount} "
            f"registrations for code {referral_code}"
        )
        thread_proxy = self.get_proxy_for_thread(thread_index)
        registrations_done = 0
        max_attempts_per_registration = 3
        while registrations_done < thread_amount:
            current_registration_attempts = 0
            while current_registration_attempts < max_attempts_per_registration:
                current_registration_attempts += 1
                log.info(
                    f"Thread {thread_index+1} | Registration {registrations_done+1}/{thread_amount} | "
                    f"Attempt {current_registration_attempts}/{max_attempts_per_registration}"
                )
                if await self._attempt_registration(
                    referral_code, registrations_done, thread_amount, thread_index, thread_proxy
                ):
                    registrations_done += 1
                    log.info(
                        f"Thread {thread_index+1} | Registration {registrations_done}/{thread_amount} "
                        f"successful after {current_registration_attempts} attempts"
                    )
                    break
                if current_registration_attempts < max_attempts_per_registration:
                    await random_sleep(f"Referral-Thread-{thread_index+1}", **sleep_between_referral_registrations_in_stream)
            if registrations_done < thread_amount:
                await random_sleep(f"Referral-Thread-{thread_index+1}", **sleep_between_referral_registrations_in_stream)
        log.info(
            f"Thread {thread_index+1} completed {registrations_done}/{thread_amount} "
            f"registrations for code {referral_code}"
        )
        return registrations_done

    async def _attempt_registration(
        self,
        referral_code: str,
        current_count: int,
        thread_amount: int,
        thread_index: int,
        proxy: Proxy = None
    ) -> bool:
        """Attempt a single referral registration."""
        try:
            private_key, _ = self.generate_eth_wallet()
            token = await self.onboarding(private_key, proxy)
            if not token:
                log.error(f"Thread {thread_index+1} | Failed to get token for referral code {referral_code}")
                return False
            await random_sleep(f"Referral-Thread-{thread_index+1}", **sleep_onbord_and_registration)
            if await self.register_referral(token, referral_code, private_key, proxy):
                await self.save_private_key(private_key, referral_code)
                return True
            return False
        except Exception as e:
            log.error(f"Thread {thread_index+1} | Error in attempt registration for code {referral_code}: {str(e)}")
            return False