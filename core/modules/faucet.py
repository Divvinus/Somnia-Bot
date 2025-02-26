from typing import Dict, Any

from core.api import BaseAPIClient
from core.wallet import Wallet
from logger import log
from models import Account
from utils import random_sleep
from config.settings import sleep_between_repeated_token_requests


class FaucetModule(Wallet, BaseAPIClient):
   """
   Module for interacting with Somnia testnet faucet.
   Handles wallet initialization and faucet requests with rate limiting.
   """

   def __init__(self, account: Account):
       """
       Initialize faucet module with account details.

       Args:
           account: Account object containing private key/mnemonic and proxy
       """
       Wallet.__init__(self, account.private_key, account.proxy)
       BaseAPIClient.__init__(self, base_url="https://testnet.somnia.network", proxy=account.proxy)  
   
   async def faucet(self) -> bool:
       """
       Request test tokens from Somnia faucet.
       Handles rate limiting and retries automatically.

       Returns:
           bool: True if request succeeded or already claimed, False on error
       """
       log.info(f"Account {self.wallet_address} | Processing faucet...")

       headers = self._get_headers()
       json_data = {'address': self.wallet_address}

       while True:
           response = await self.send_request(
               request_type="POST", 
               method="/api/faucet", 
               json_data=json_data, 
               headers=headers
           )
           response_data = response.json()
           
           if await self._handle_response(response_data):
               return True

   def _get_headers(self) -> Dict[str, str]:
       """
       Generate headers required for faucet API request.

       Returns:
           dict: HTTP headers for faucet request
       """
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
       """
       Process faucet API response and handle various error cases.

       Args:
           response: JSON response from faucet API

       Returns:
           bool: True if request succeeded or already claimed, False on error
       """
       if response.get("error"):
           error_message = response.get("error")
           if error_message == "Please wait 24 hours between requests" or error_message == "Rate limit exceeded. Maximum 10 requests per IP per 24 hours.":
               log.warning(f"Account {self.wallet_address} | Tokens have already been received for this wallet today, come back tomorrow")
               return True
           elif response.get("details") == "An error occurred while processing the faucet request. Please try again later." or response.get("details") == "Another request for this address is being processed":
               log.warning(f"Account {self.wallet_address} | Error occurred while processing the faucet request. Let's try again...")
               await random_sleep(self.wallet_address, **sleep_between_repeated_token_requests)
               return False
           else:
               log.error(f"Account {self.wallet_address} | {response}")
               return False
       else:
           log.success(f"Account {self.wallet_address} | Successfully requested test tokens")
           return True