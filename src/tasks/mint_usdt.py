from typing import Self
from web3.exceptions import ContractLogicError, TransactionNotFound

from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account, UsdtTokensContract
from src.utils import show_trx_log, random_sleep
from src.wallet import BlockchainError
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE

class MintUsdtModule(Wallet, AsyncLogger):
    def __init__(self, account: Account, rpc_url: str) -> None:
        Wallet.__init__(self, account.private_key, rpc_url, account.proxy)
        AsyncLogger.__init__(self)

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

    async def mint_usdt(self) -> tuple[bool, str]:
        try:
            await self.logger_msg("Checking sUSDT balance...", "info", self.wallet_address)

            contract = await self.get_contract(UsdtTokensContract())
            balance = await contract.functions.balanceOf(self.wallet_address).call()

            if balance > 0:
                return True, "already_minted"

            tx_params = await self.build_transaction_params(
                contract.functions.mint()
            )
            
            success, tx_hash = await self._process_transaction(tx_params)
            if not success:
                raise BlockchainError(f"Transaction failed: {tx_hash}")

            return True, tx_hash

        except ContractLogicError as e:
            error_msg = f"Contract error: {e}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "mint_usdt")
            return False, error_msg

        except TransactionNotFound as e:
            error_msg = f"Transaction not found: {e}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "mint_usdt")
            return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "mint_usdt")
            return False, error_msg

    async def run(self) -> tuple[bool, str]:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                status, result = await self.mint_usdt()

                await show_trx_log(
                    self.wallet_address, "Mint 1000 sUSDT", status, result
                )
                
                return status, "Success" if status else result

            except Exception as e:
                error_msg = f"Error: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run")
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
            
        return False, f"Failed to mint 1000 sUSDT after {MAX_RETRY_ATTEMPTS} attempts"