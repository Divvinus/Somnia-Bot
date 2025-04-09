from typing import Self
from web3.exceptions import ContractLogicError, TransactionNotFound

from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import Account, UsdtTokensContract
from src.utils.logger_trx import show_trx_log
from src.wallet import BlockchainError

class MintUsdtModule(Wallet, AsyncLogger):
    def __init__(self, account: Account, rpc_url: str) -> None:
        Wallet.__init__(self, account.private_key, rpc_url, account.proxy)
        AsyncLogger.__init__(self)
        self._mint_limit = 1000
        self._contract_address = UsdtTokensContract().address

    async def __aenter__(self) -> Self:
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def mint_usdt(self) -> tuple[bool, str]:
        try:
            await self.logger_msg(
                msg="Checking sUSDT balance...",
                type_msg="info",
                address=self.wallet_address
            )

            contract = await self.get_contract(UsdtTokensContract())
            balance = await contract.functions.balanceOf(self.wallet_address).call()

            if balance >= self._mint_limit:
                await self.logger_msg(
                    msg=f"Wallet already has {balance} sUSDT",
                    type_msg="warning",
                    address=self.wallet_address
                )
                return True, "already_minted"

            tx_params = await self.build_transaction_params(
                contract.functions.mint(),
                gas_limit=200000
            )
            
            success, tx_hash = await self._process_transaction(tx_params)
            if not success:
                raise BlockchainError(f"Transaction failed: {tx_hash}")

            return True, tx_hash

        except ContractLogicError as e:
            error_msg = f"Contract error: {e}"
            await self.logger_msg(
                msg=error_msg,
                type_msg="error",
                address=self.wallet_address,
                method_name="mint_usdt"
            )
            return False, error_msg

        except TransactionNotFound as e:
            error_msg = f"Transaction not found: {e}"
            await self.logger_msg(
                msg=error_msg,
                type_msg="error",
                address=self.wallet_address,
                method_name="mint_usdt"
            )
            return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            await self.logger_msg(
                msg=error_msg,
                type_msg="critical",
                address=self.wallet_address,
                method_name="mint_usdt"
            )
            return False, error_msg

    async def run(self) -> tuple[bool, str]:
        try:
            status, result = await self.mint_usdt()

            await show_trx_log(
                self.wallet_address,
                "Mint 1000 sUSDT",
                status,
                result,
                config.somnia_explorer
            )
            
            return status, "Success" if status else result

        except Exception as e:
            await self.logger_msg(
                msg=f"Critical error: {str(e)}",
                type_msg="critical",
                address=self.wallet_address,
                method_name="run"
            )
            return False, str(e)