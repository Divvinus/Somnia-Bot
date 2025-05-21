import time

from faker import Faker
from typing import Self
from src.logger import AsyncLogger
from src.api import BaseAPIClient
from src.wallet import Wallet
from src.models import Account
from src.utils import random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE


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
                await self.logger_msg(f"Error closing API client: {str(e)}", "error", self.wallet_address)
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
    
    async def _process_api_response(self, response: dict, operation_name: str) -> tuple[bool, str]:
        if not response:
            error_msg = f"Empty response during {operation_name}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "_process_api_response")
            return False, error_msg
            
        if response.get("data", {}).get("success"):
            success_msg = f"Successfully {operation_name}"
            await self.logger_msg(success_msg, "success", self.wallet_address)
            return True, success_msg
        
        else:
            error_msg = f"Unknown error during {operation_name}. Response: {response}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "_process_api_response")
            return False, error_msg
    
    async def auth(self) -> tuple[bool, str]:
        await self.logger_msg("Starting authorization on the quills.fun...", "info", self.wallet_address)
        error_messages = []
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.logger_msg(f"Authorization attempt {attempt+1}/{MAX_RETRY_ATTEMPTS}", "info", self.wallet_address)
                
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
                
                if response is None:
                    error_msg = f"Empty auth response (attempt {attempt+1})"
                    await self.logger_msg(error_msg, "error", self.wallet_address, "auth")
                    error_messages.append(error_msg)
                    if attempt < MAX_RETRY_ATTEMPTS-1:
                        await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                    continue
                    
                status, result = await self._process_api_response(response, "logged into the site quills.fun")
                if status:
                    return status, result
                    
                error_messages.append(result)
                if attempt < MAX_RETRY_ATTEMPTS-1:
                    await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                    
            except Exception as e:
                error_msg = f"Auth attempt {attempt+1} failed: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "auth")
                error_messages.append(error_msg)
                if attempt < MAX_RETRY_ATTEMPTS-1:
                    await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
        
        return False, f"Authorization failed after {MAX_RETRY_ATTEMPTS} attempts. Errors:\n" + "\n".join(error_messages)

    async def mint_message_nft(self) -> tuple[bool, str]:
        await self.logger_msg(f"Starting sending a message...", "info", self.wallet_address)
        error_messages = []
        message = self.fake.word()
        
        json_data = {
            'walletAddress': self.wallet_address,
            'message': message,
        }
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.logger_msg(f"Attempt to mint a message {attempt+1}/{MAX_RETRY_ATTEMPTS}", "info", self.wallet_address)
                
                response = await self._api.send_request(
                    request_type="POST",
                    method="/mint-nft",
                    json_data=json_data,
                    headers=_get_headers(),
                    verify=False
                )
                
                if response is None:
                    error_msg = f"Received empty API response (attempt {attempt+1})"
                    await self.logger_msg(error_msg, "error", self.wallet_address, "mint_message_nft")
                    error_messages.append(error_msg)
                    if attempt < MAX_RETRY_ATTEMPTS-1:
                        await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                    continue
                    
                status, result = await self._process_api_response(response, f"minted an nft message: {message}")
                if status:
                    return status, result
                
                error_messages.append(result)
                if attempt < MAX_RETRY_ATTEMPTS-1:
                    await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                    
            except Exception as e:
                error_msg = f"Attempt {attempt+1} failed: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "mint_message_nft")
                error_messages.append(error_msg)
                if attempt < MAX_RETRY_ATTEMPTS-1:
                    await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
            
        return False, f"Failed minting message after {MAX_RETRY_ATTEMPTS} attempts. Error details:\n" + "\n".join(error_messages)
    
    async def run(self) -> tuple[bool, str]:
        try:
            await self.logger_msg(f"Performing the task of sending and minting nft messages on quills.fun...", "info", self.wallet_address
            )
            
            status, msg = await self.auth()
            if not status: return status, msg
            
            return await self.mint_message_nft()
        
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "run")
            return False, error_msg