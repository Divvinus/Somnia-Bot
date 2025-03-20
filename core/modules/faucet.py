from typing import Any, TypedDict

from config.settings import sleep_between_repeated_token_requests
from core.api import BaseAPIClient
from core.wallet import Wallet
from logger import log
from models import Account
from utils import random_sleep


class FaucetResponse(TypedDict):
    status_code: int
    data: dict[str, Any]


class FaucetModule(Wallet, BaseAPIClient):    
    ATTEMPTS = 3
    
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, account.proxy)
        BaseAPIClient.__init__(
            self,
            base_url="https://testnet.somnia.network",
            proxy=account.proxy
        )

    async def __aenter__(self) -> "FaucetModule":
        return self
    
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any
    ) -> None:
        if self.session:
            await self._safely_close_session(self.session)
            self.session = None

    def _get_headers(self) -> dict[str, str]:
        return {
            "accept": "*/*",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://testnet.somnia.network",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://testnet.somnia.network/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    async def _handle_response(self, response: FaucetResponse) -> bool:
        if response.get("status_code") == 403:
            log.warning(
                f"Account {self.wallet_address} | "
                "First register account with Somnia project"
            )
            await random_sleep(
                self.wallet_address,
                **sleep_between_repeated_token_requests
            )
            return False

        data = response.get("data", {})
        error_message = data.get("error")
        details = data.get("details")

        if error_message in {
            "Please wait 24 hours between requests",
            "Rate limit exceeded. Maximum 10 requests per IP per 24 hours."
        }:
            log.warning(
                f"Account {self.wallet_address} | "
                "Tokens already received today"
            )
            return True

        if details in {
            "An error occurred while processing the faucet request. Please try again later.",
            "Another request for this address is being processed"
        }:
            log.warning(
                f"Account {self.wallet_address} | "
                "Faucet request error. Retrying..."
            )
            await random_sleep(
                self.wallet_address,
                **sleep_between_repeated_token_requests
            )
            return False

        if error_message:
            log.error(
                f"Account {self.wallet_address} | "
                f"Unexpected error: {error_message}"
            )
            await random_sleep(
                self.wallet_address,
                **sleep_between_repeated_token_requests
            )
            return False

        log.success(
            f"Account {self.wallet_address} | "
            "Successfully requested test tokens"
        )
        return True
    
    async def run(self) -> bool:
        log.info(f"Account {self.wallet_address} | Processing faucet...")

        headers = self._get_headers()
        json_data = {"address": self.wallet_address}

        for _ in range(self.ATTEMPTS):
            response = await self.send_request(
                request_type="POST",
                method="/api/faucet",
                json_data=json_data,
                headers=headers,
                max_retries=1,
                verify=False
            )

            if response.get("data", {}).get("error") == "Bot detected":
                log.warning(
                    f"Account {self.wallet_address} | "
                    "Address suspected to be a bot"
                )
                return False

            if await self._handle_response(response):
                return True