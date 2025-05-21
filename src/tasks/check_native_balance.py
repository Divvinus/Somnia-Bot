from typing import Self

from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account
from src.utils import update_native_balance_in_excel, random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE

class CheckNativeBalanceModule(Wallet, AsyncLogger):
    def __init__(self, account: Account, rpc_url: str) -> None:
        Wallet.__init__(self, account.private_key, rpc_url, account.proxy)
        AsyncLogger.__init__(self)
        self.account = account

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
        
    async def check_native_balance(self) -> tuple[bool, str]:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                balance = await self.human_balance()
                await self.logger_msg(f"Native balance: {balance}", "success", self.wallet_address)
                
                await update_native_balance_in_excel(self.wallet_address, balance, self.account.private_key)
                
                return True, f"Native balance: {balance}"
            
            except Exception as e:
                error_msg = f"Error checking native balance: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address)
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg                    
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                
        return False, f"Failed checking native balance after {MAX_RETRY_ATTEMPTS} attempts"