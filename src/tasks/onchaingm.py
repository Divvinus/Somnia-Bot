from typing import Self

from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import Account, OnchainGMContract
from src.utils.logger_trx import show_trx_log


class OnchainGMModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
    
    async def run(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg="Starting Onchain GM",
            type_msg="info",
            address=self.wallet_address
        )

        try:
            contract = await self.get_contract(OnchainGMContract())
            
            data = bytes.fromhex("5011b71c")

            tx_params = await self.build_transaction_params(
                to=contract.address,
                data=data,
                value=self.to_wei(0.000029, 'ether')
            )
            
            status, tx_hash = await self._process_transaction(tx_params)
            
            
            await show_trx_log(
                self.wallet_address, "OnchainGM",
                status, tx_hash
            )
            
            return status, tx_hash
        
        except Exception as error:
            await self.logger_msg(
                msg=f"Error: {str(error)}", type_msg="error", 
                address=self.wallet_address, method_name="run"
            )
            return False, str(error)