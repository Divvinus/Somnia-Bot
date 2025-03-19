from typing import Dict, Any

from core.api import BaseAPIClient
from core.wallet import Wallet
from logger import log
from models import Account
from utils import random_sleep
from config.settings import sleep_between_repeated_token_requests


class FaucetModule(Wallet, BaseAPIClient):
    def __init__(self, account: Account):
       Wallet.__init__(self, account.private_key, account.proxy)
       BaseAPIClient.__init__(self, base_url="https://testnet.somnia.network", proxy=account.proxy)  
       
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'api') and self.api:
            if hasattr(self, 'session') and self.session:
                await self._safely_close_session(self.session)
                self.session = None

    async def faucet(self) -> bool:
        log.info(f"Account {self.wallet_address} | Processing faucet...")

        headers = self._get_headers()
        json_data = {'address': self.wallet_address}

        while True:
            response = await self.send_request(
                request_type="POST", 
                method="/api/faucet", 
                json_data=json_data, 
                headers=headers,
                max_retries=1,
                verify=False
            )
            
            if response.get("data").get("error"):
                error_message = response.get("data").get("error")
                if error_message == "Bot detected":
                    log.warning(f"Account {self.wallet_address} | The address you provided is suspected to be a bot")
                    return False
            
            if await self._handle_response(response):
               return True

    def _get_headers(self) -> Dict[str, str]:
       return {
           'accept': '*/*',
           'cache-control': 'no-cache',
           'content-type': 'application/json',
           'origin': 'https://testnet.somnia.network',
           'pragma': 'no-cache',
           'priority': 'u=1, i',
           'referer': 'https://testnet.somnia.network/',
           'sec-fetch-dest': 'empty',
           'sec-fetch-mode': 'cors',
           'sec-fetch-site': 'same-origin',
       }

    async def _handle_response(self, response: Dict[str, Any]) -> bool:
        if response.get("status_code") == 403:
            log.warning(f"Account {self.wallet_address} | First register an account with the Somnia project, then come back and request tokens")
            return False
            
        if response.get("data").get("error"):
            error_message = response.get("data").get("error")
            if error_message == "Please wait 24 hours between requests" or error_message == "Rate limit exceeded. Maximum 10 requests per IP per 24 hours.":
                log.warning(f"Account {self.wallet_address} | Tokens have already been received for this wallet today, come back tomorrow")
                return True
            elif response.get("data").get("details") == "An error occurred while processing the faucet request. Please try again later." or response.get("details") == "Another request for this address is being processed":
                log.warning(f"Account {self.wallet_address} | Error occurred while processing the faucet request. Let's try again...")
                await random_sleep(self.wallet_address, **sleep_between_repeated_token_requests)
                return False
            else:
                log.error(f"Account {self.wallet_address} | {response}")
                return False
        else:
            log.success(f"Account {self.wallet_address} | Successfully requested test tokens")
            return True