from typing import Self

from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account
from src.utils.excel_processor import update_native_balance_in_excel

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
        try:
            balance = await self.human_balance()
            await self.logger_msg(
                msg=f"Native balance: {balance}",
                type_msg="success",
                address=self.wallet_address
            )
            
            await update_native_balance_in_excel(
                wallet_address=self.wallet_address, 
                balance=balance, 
                private_key=self.account.private_key
            )
            
            return True, f"Native balance: {balance}"
        
        except Exception as e:
            await self.logger_msg(
                msg=f"Error checking native balance: {e}",
                type_msg="error",
                address=self.wallet_address
            )
            return False, f"Error checking native balance: {e}"