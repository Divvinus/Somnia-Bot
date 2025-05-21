from typing import Self

from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import Account, OnchainGMContract
from src.utils import show_trx_log, random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE

class OnchainGMModule(Wallet, AsyncLogger):
    WAIT_24H_ERROR_HEX = "0x08c379a00000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000d5761697420323420686f75727300000000000000000000000000000000000000"
    
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        
    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
    
    async def run(self) -> tuple[bool, str]:
        await self.logger_msg("Starting Onchain GM", "info", self.wallet_address)

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                contract = await self.get_contract(OnchainGMContract())
                
                data = bytes.fromhex("5011b71c")

                try:
                    tx_params = await self.build_transaction_params(
                        to=contract.address,
                        data=data,
                        value=self.to_wei(0.000029, 'ether')
                    )
                    
                    status, tx_hash = await self._process_transaction(tx_params)                

                    if isinstance(tx_hash, tuple) and tx_hash[0] == "execution reverted" and tx_hash[1] == self.WAIT_24H_ERROR_HEX:
                        await self.logger_msg("Wait 24 hours", "info", self.wallet_address, "run")
                        return True, "Wait 24 hours"
                    
                    await show_trx_log(
                        self.wallet_address, "OnchainGM",
                        status, tx_hash
                    )
                    
                    return status, tx_hash
                except Exception as error:
                    error_str = str(error)
                    if self.WAIT_24H_ERROR_HEX in error_str:
                        await self.logger_msg("Wait 24 hours", "info", self.wallet_address, "run")
                        return True, "Wait 24 hours"
                    raise
            
            except Exception as error:
                error_msg = f"Error: {str(error)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run")
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
            
        return False, f"Failed to perform Onchain GM after {MAX_RETRY_ATTEMPTS} attempts"