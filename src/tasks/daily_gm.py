from typing import Self

from src.api import SomniaClient, BaseAPIClient
from src.logger import AsyncLogger
from src.models import Account
from src.utils import random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE


class GmModule(SomniaClient, AsyncLogger):
    def __init__(
        self,
        account: Account
    ) -> None:
        SomniaClient.__init__(self, account)
        AsyncLogger.__init__(self)
        
        self._api = BaseAPIClient(
            base_url="https://quest.somnia.network", proxy=account.proxy
        )
        
    @property
    def api(self) -> BaseAPIClient:
        return self._api
    
    @api.setter
    def api(self, value: BaseAPIClient) -> None:
        self._api = value
        
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
        
    async def __aenter__(self) -> Self:
        await SomniaClient.__aenter__(self)
        self._api = await self._api.__aenter__()
        return self

    async def __aexit__(self, *args):
        await SomniaClient.__aexit__(self, *args)
        await self._api.__aexit__(*args)
        
    async def run(self) -> tuple[bool, str]:
        await self.logger_msg("I'm doing it Daily GM", "info", self.wallet_address)
        
        status, result = await self.onboarding()
        if not status:
            raise RuntimeError(result)
        
        headers = {
            **self._base_headers(),
            "referer": "https://quest.somnia.network/account",
        }

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                response = await self._api.send_request(
                    request_type="POST",
                    method="/users/gm",
                    headers=headers,
                    verify=False
                )
                status = response.get("status_code")
                
                if status == 200:
                    await self.logger_msg(f"Successfully executed Daily GM", "success", self.wallet_address)
                    return True, "Successfully executed Daily GM"
                
                await self.logger_msg(f"Failed executed Daily GM", "error", self.wallet_address)
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, "Failed executed Daily GM"
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
            
            except Exception as e:
                error_msg = f"Error executing Daily GM: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address)
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
        
        return False, f"Failed executed Daily GM after {MAX_RETRY_ATTEMPTS} attempts"