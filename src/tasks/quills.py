import time

from faker import Faker
from typing import Self
from src.logger import AsyncLogger
from src.api import BaseAPIClient
from src.wallet import Wallet
from src.models import Account
from src.utils import random_sleep


def _get_headers() -> dict[str, str]:
    return {
        'authority': 'quills.fun',
        'accept': '*/*',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'dnt': '1',
        'origin': 'https://quills.fun',
        'pragma': 'no-cache',
        'referer': 'https://quills.fun/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin'
    }
    

class QuillsMessageModule(Wallet, AsyncLogger):
    def __init__(self, account: Account):
        Wallet.__init__(self, account.private_key, account.proxy)
        AsyncLogger.__init__(self)
        
        self._api = BaseAPIClient(base_url="https://quills.fun/api", proxy=account.proxy)
        self.fake = Faker()
    
    @property
    def api(self) -> BaseAPIClient:
        return self._api

    @api.setter
    def api(self, value: BaseAPIClient) -> None:
        self._api = value
        
    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        self._api = await self._api.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, '_api') and self._api:
            try:
                await self._api.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                await self.logger_msg(
                    msg=f"Error closing API client: {str(e)}", 
                    type_msg="error", 
                    address=self.wallet_address
                )
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
    
    async def _process_api_response(self, response: dict, operation_name: str) -> tuple[bool, str]:
        if not response:
            await self.logger_msg(
                msg=f"Empty response during {operation_name}", 
                type_msg="error", address=self.wallet_address, method_name="_process_api_response"
            )
            return False, "Empty response"
            
        if response.get("data", {}).get("success"):
            await self.logger_msg(
                msg=f"Successfully {operation_name}", 
                type_msg="success", address=self.wallet_address
            )
            return True, "Successfully completed operation"
        
        else:
            await self.logger_msg(
                msg=f"Unknown error during {operation_name}. Response: {response}", 
                type_msg="error", address=self.wallet_address, method_name="_process_api_response"
            )
            return False, "Unknown error"
    
    async def auth(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Beginning the authorization process on the site quills.fun...", 
            type_msg="info", address=self.wallet_address
        )
        
        message = f"I accept the Quills Adventure Terms of Service at https://quills.fun/terms\n\nNonce: {int(time.time() * 1000)}"
        signature = await self.get_signature(message)
        
        json_data = {
            'address': self.wallet_address,
            'signature': f"0x{signature}",
            'message': message,
        }
        
        response = await self._api.send_request(
            request_type="POST",
            method="/auth/wallet",
            json_data=json_data,
            headers=_get_headers(),
            verify=False
        )
        
        return await self._process_api_response(response, "logged into the site quills.fun")

    async def mint_message_nft(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Beginning the process of sending a message...", 
            type_msg="info", address=self.wallet_address
        )
        
        message = self.fake.word()
        
        json_data = {
            'walletAddress': self.wallet_address,
            'message': message,
        }
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                await self.logger_msg(
                    msg=f"Attempt to mint a message {attempt}/{max_attempts}", 
                    type_msg="info", address=self.wallet_address
                )
                
                response = await self._api.send_request(
                    request_type="POST",
                    method="/mint-nft",
                    json_data=json_data,
                    headers=_get_headers(),
                    verify=False
                )
                
                if response is None:
                    await self.logger_msg(
                        msg=f"Received an empty response from the API (attempt {attempt})", 
                        type_msg="error", address=self.wallet_address, method_name="mint_message_nft"
                    )
                    if attempt < max_attempts:
                        await random_sleep(self.wallet_address)
                    continue
                    
                status, result = await self._process_api_response(response, f"minted an nft message: {message}")
                if status:
                    return status, result
                    
                if attempt < max_attempts:
                    await random_sleep(self.wallet_address)
            except Exception as e:
                await self.logger_msg(
                    msg=f"Error during minting a message (attempt {attempt}): {str(e)}", 
                    type_msg="error", address=self.wallet_address, method_name="mint_message_nft"
                )
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
        
        await self.logger_msg(
            msg=f"All attempts to mint a message have been exhausted", 
            type_msg="error", address=self.wallet_address, method_name="mint_message_nft"
        )
        return False, "Failed to mint an nft message"
    
    async def run(self) -> tuple[bool, str]:
        try:
            await self.logger_msg(
                msg=f"I perform tasks on sending and minting nft message on the site quills.fun...", 
                type_msg="info", address=self.wallet_address
            )
            
            if not await self.auth():
                return False, "Failed to authorize on the site quills.fun"
            
            return await self.mint_message_nft()
        
        except Exception as e:
            await self.logger_msg(
                msg=f"Error: {str(e)}", type_msg="error", 
                address=self.wallet_address, method_name="run"
            )
            return False, str(e)