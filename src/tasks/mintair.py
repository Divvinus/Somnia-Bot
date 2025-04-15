from typing import Self

from datetime import datetime, timezone

from src.api import BaseAPIClient
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account
from src.utils import show_trx_log, DeployContractWorker
from bot_loader import config


class MintairDeployContractModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        
        self.api_client = BaseAPIClient(
            base_url="https://contracts-api.mintair.xyz/api",
            proxy=account.proxy
        )
        self.deploy_contract_worker = DeployContractWorker(account)
        
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
    
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
    
    async def check_daily_streak(self) -> bool:
        await self.logger_msg(
            msg=f"Checking to see if we can do 'Daily Streak'", 
            type_msg="info", 
            address=self.wallet_address
        )
        
        response = await self.api_client.send_request(
            request_type="GET",
            method="/v1/user/streak",
            headers=self._get_headers()
        )
        
        response_data = response.get("data", {})
        
        streak_data = response_data.get('data', {}).get('streak')
        updated_at_str = streak_data.get('updatedAt')
        
        if not updated_at_str:
            return True
        
        updated_at = datetime.strptime(updated_at_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        
        current_time = datetime.now(timezone.utc)
        
        time_difference = current_time - updated_at
        
        return time_difference.total_seconds() >= 24 * 3600
        
    async def daily_streak(self, transaction_hash: str) -> dict[str, str]:
        await self.logger_msg(
            msg=f"Send a request to the 'Daily Streak'", 
            type_msg="info", 
            address=self.wallet_address
        )
        
        json_data = {
            'transactionHash': transaction_hash,
            'metaData': {
                'name': 'Somnia Testnet',
                'type': 'Timer',
            },
        }
                
        response = await self.api_client.send_request(
            request_type="POST",
            method="/v1/user/transaction",
            json_data=json_data,
            headers=self._get_headers()
        )
        
        if response.get("data", {}).get("success"):
            await self.logger_msg(
                msg=f"Successfully completed the 'Daily Streak' task", 
                type_msg="success", 
                address=self.wallet_address
            )
            return True, "Successfully completed the 'Daily Streak' task"
        
        else:
            await self.logger_msg(
                msg=f"Unknown error during 'Daily Streak' task. Response: {response}", 
                type_msg="error", 
                address=self.wallet_address
            )
            return False, "Unknown error"
    
    async def run(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Beginning the contract deployment process...", 
            type_msg="info", 
            address=self.wallet_address
        )
        
        if not await self.check_daily_streak():
            await self.logger_msg(
                msg="Waiting 24 hours",
                type_msg="info",
                address=self.wallet_address
            )
            return True, "Waiting 24 hours"
        
        try:
            await self.logger_msg(
                msg="Selected ERC20 contract deployment",
                type_msg="info",
                address=self.wallet_address
            )
            status, result = await self.deploy_contract_worker.deploy_erc_20_contract()
            
            await show_trx_log(
                address=self.wallet_address,
                trx_type="ERC20 contract deployment",
                status=status,
                result=result
            )
            
            status, result = await self.daily_streak(result)
            
            return status, result
            
        except (ValueError, ConnectionError) as e:
            await self.logger_msg(
                msg=f"Error during contract deployment: {str(e)}", 
                type_msg="error", 
                address=self.wallet_address, 
                method_name="run"
            )
            return False, str(e)
        except Exception as e:
            await self.logger_msg(
                msg=f"Unexpected error: {str(e)}", 
                type_msg="error", 
                address=self.wallet_address, 
                method_name="run"
            )
            return False, str(e)