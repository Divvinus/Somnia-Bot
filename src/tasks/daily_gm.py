from typing import Self

from src.api import SomniaClient, BaseAPIClient
from src.logger import AsyncLogger
from src.models import Account


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
        await self.logger_msg(
            msg="I'm doing it Daily GM",
            address=self.wallet_address,
            type_msg="info"
        )
        
        status, result = await self.onboarding()
        if not status:
            raise RuntimeError(result)
        
        headers = {
            **self._base_headers(),
            "referer": "https://quest.somnia.network/account",
        }

        response = await self._api.send_request(
            request_type="POST",
            method="/users/gm",
            headers=headers,
            verify=False
        )
        status = response.get("status_code")
        
        if status == 200:
            await self.logger_msg(
                msg=f"Successfully executed Daily GM",
                type_msg="success",
                address=self.wallet_address,
            )
            return True, "Successfully executed Daily GM"
        
        await self.logger_msg(
            msg=f"Failed executed Daily GM",
            type_msg="error",
            address=self.wallet_address,
        )
        return False, "Failed executed Daily GM"
        
        