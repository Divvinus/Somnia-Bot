import asyncio
from typing import Any, TypedDict, Self

from config.settings import sleep_between_repeated_token_requests
from src.api import BaseAPIClient
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account
from src.utils import random_sleep, save_bad_private_key


file_lock = asyncio.Lock()

class FaucetResponse(TypedDict):
    status_code: int
    data: dict[str, Any]


class FaucetModule(Wallet):
    logger = AsyncLogger()
    ATTEMPTS = 3
    
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, account.proxy)
        self.account = account
        self.api_client: BaseAPIClient | None = None

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        self.api_client = BaseAPIClient(
            base_url="https://testnet.somnia.network",
            proxy=self.account.proxy
        )
        await self.api_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'api_client') and self.api_client:
            await self.api_client.__aexit__(exc_type, exc_val, exc_tb)
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

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
            await self.logger.logger_msg(
                msg="First register account with Somnia project", type_msg="warning", 
                address=self.wallet_address, 
                class_name=self.__class__.__name__, method_name="_handle_response"
            )
            await random_sleep(
                self.wallet_address,
                **sleep_between_repeated_token_requests
            )
            return False, "First register account with Somnia project"

        data = response.get("data", {})
        error_message = data.get("error")
        details = data.get("details")

        if error_message in {
            "Please wait 24 hours between requests",
            "Rate limit exceeded. Maximum 10 requests per IP per 24 hours."
        }:
            await self.logger.logger_msg(
                msg="Tokens already received today", 
                type_msg="warning", address=self.wallet_address, 
                class_name=self.__class__.__name__, method_name="_handle_response"
            )
            return True, "Tokens already received today"

        if details in {
            "An error occurred while processing the faucet request. Please try again later.",
            "Another request for this address is being processed"
        }:
            await self.logger.logger_msg(
                msg="Faucet request error. Retrying...", 
                type_msg="warning", address=self.wallet_address, 
                class_name=self.__class__.__name__, method_name="_handle_response"
            )
            await random_sleep(
                self.wallet_address,
                **sleep_between_repeated_token_requests
            )
            return False, "Faucet request error. Retrying..."

        if error_message:
            await self.logger.logger_msg(
                msg=f"Unexpected error: {error_message}", 
                type_msg="error", address=self.wallet_address, 
                class_name=self.__class__.__name__, method_name="_handle_response"
            )
            await random_sleep(
                self.wallet_address,
                **sleep_between_repeated_token_requests
            )
            return False, "Unexpected error"

        await self.logger.logger_msg(
            msg="Successfully requested test tokens", 
            type_msg="success", address=self.wallet_address
        )
        return True, "Successfully requested test tokens"
    
    async def run(self) -> tuple[bool, str]:
        await self.logger.logger_msg(
            msg=f"Processing faucet...", 
            type_msg="info", address=self.wallet_address
        )

        headers = self._get_headers()
        json_data = {"address": self.wallet_address}
        
        try:
            for _ in range(self.ATTEMPTS):
                response = await self.api_client.send_request(
                    request_type="POST",
                    method="/api/faucet",
                    json_data=json_data,
                    headers=headers,
                    max_retries=1,
                    verify=False,
                    ssl=False
                )

                if response.get("data", {}).get("error") == "Bot detected":
                    await self.logger.logger_msg(
                        msg="Address suspected to be a bot", 
                        type_msg="warning", address=self.wallet_address, 
                        class_name=self.__class__.__name__, method_name="run"
                    )
                    asyncio.create_task(save_bad_private_key(self.account.private_key, self.wallet_address))
                    return False, "Address suspected to be a bot"

                return await self._handle_response(response)
                
        except Exception as e:
            await self.logger.logger_msg(
                msg=f"Critical error: {str(e)}", 
                type_msg="error", address=self.wallet_address, 
                class_name=self.__class__.__name__, method_name="run"
            )
            return False, str(e)
        
        return False, "Unknown cause of error" 