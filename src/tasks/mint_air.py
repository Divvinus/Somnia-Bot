from typing import Self

from datetime import datetime, timezone

from src.api import BaseAPIClient
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account
from src.utils import show_trx_log, DeployContractWorker
from bot_loader import config
from src.utils import random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE


class MintairDeployContractModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        
        self.api_client = BaseAPIClient(
            "https://contracts-api.mintair.xyz/api", account.proxy
        )
        self.deploy_contract_worker = DeployContractWorker(account)
        
    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        self.api_client = await self.api_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'api_client') and self.api_client:
            try:
                await self.api_client.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                await self.logger_msg(
                    msg=f"Error closing API client: {str(e)}", 
                    type_msg="error", 
                    address=self.wallet_address
                )
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
    
    def _get_headers(self) -> dict[str, str]:
        return {
            'accept': '*/*',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://contracts.mintair.xyz',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://contracts.mintair.xyz/',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'wallet-address': self.wallet_address,
        }
    
    async def check_daily_streak(self) -> tuple[bool, str] | bool:
        await self.logger_msg(
            "Checking to see if we can do 'Daily Streak'", "info", self.wallet_address
        )
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                response = await self.api_client.send_request(
                    request_type="GET",
                    method="/v1/user/streak",
                    headers=self._get_headers(),
                    verify=False
                )
                
                response_data = response.get("data", {})
                
                streak_data = response_data.get('data', {}).get('streak')
                
                if not streak_data:
                    return True
                
                updated_at_str = streak_data.get('updatedAt')
                
                if not updated_at_str:
                    return True
                
                updated_at = datetime.strptime(updated_at_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                
                current_time = datetime.now(timezone.utc)
                
                time_difference = current_time - updated_at
                
                return time_difference.total_seconds() >= 24 * 3600
            
            except Exception as e:
                error_msg = f"Error checking daily streak: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address)
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
        
        return False, f"Failed checking daily streak after {MAX_RETRY_ATTEMPTS} attempts"

    async def daily_streak(self, contract_address: str) -> tuple[bool, str]:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.logger_msg(
                    "Send a request to the 'Daily Streak'", "info", self.wallet_address
                )
                
                json_data = {
                    'transactionHash': contract_address,
                    'metaData': {
                        'name': 'Somnia Testnet',
                        'type': 'Timer',
                    },
                }
                    
                response = await self.api_client.send_request(
                    request_type="POST",
                    method="/v1/user/transaction",
                    json_data=json_data,
                    headers=self._get_headers(),
                    verify=False
                )
                
                if response.get("status_code") == 404 and response.get("data").get("message") == "Account not found":
                    return True, "Account not found"                
                
                if response.get("data", {}).get("success"):
                    await self.logger_msg(
                        "Successfully completed the 'Daily Streak' task", "success", self.wallet_address
                    )
                    return True, "Successfully completed the 'Daily Streak' task"
                
                else:
                    await self.logger_msg(
                        f"Unknown error during 'Daily Streak' task. Response: {response}", "error", self.wallet_address
                    )
                    return False, "Unknown error"
                
            except Exception as e:
                error_msg = f"Error during 'Daily Streak' task: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "daily_streak")
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
        
        return False, f"Failed during 'Daily Streak' task after {MAX_RETRY_ATTEMPTS} attempts"
    
    async def run(self) -> tuple[bool, str]:
        await self.logger_msg(
            "Beginning the contract deployment process...", "info", self.wallet_address
        )
        
        if not await self.check_daily_streak():
            await self.logger_msg("Waiting 24 hours", "info", self.wallet_address)
            return True, "Waiting 24 hours"
        
        try:
            await self.logger_msg("Selected ERC20 contract deployment", "info", self.wallet_address)
            status, result = await self.deploy_contract_worker.deploy_erc_20_contract()
            
            await show_trx_log(self.wallet_address, "ERC20 contract deployment", status, result)
            
            status, result = await self.daily_streak(result)
            
            return status, result
        
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "run")
            return False, error_msg