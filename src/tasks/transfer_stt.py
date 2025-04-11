import random
import secrets

from eth_keys import keys
from eth_utils import to_checksum_address
from typing import Self

from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import Account
from src.utils.logger_trx import show_trx_log


class TransferSTTModule(Wallet, AsyncLogger):
    MINIMUM_BALANCE: float = 0.001

    def __init__(self, account: Account, rpc_url: str, me: bool = False) -> None:
        Wallet.__init__(self, account.private_key, rpc_url, account.proxy)
        AsyncLogger.__init__(self)
        
        self.me: bool = me

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    @staticmethod
    def generate_eth_address() -> str:
        private_key = keys.PrivateKey(secrets.token_bytes(32))
        return to_checksum_address(private_key.public_key.to_address())

    def _calculate_transfer_amount(self, balance: float) -> tuple[bool, float | str]:
        if balance > 0.01:
            return True, random.choice([0.01, 0.005, 0.001])
        if balance > 0.005:
            return True, random.choice([0.005, 0.001])
        if balance > 0.001:
            return True, 0.001
        return False, "Not enough balance"

    async def transfer_stt(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Processing transfer_stt...", type_msg="info", 
            address=self.wallet_address
        )

        try:
            balance = await self.human_balance()
            status, amount = self._calculate_transfer_amount(balance)
            if not status:
                await self.logger_msg(
                    msg=f"Account {self.wallet_address} | {amount}", 
                    type_msg="error", method_name="transfer_stt"
                )
                return status, amount

            to_address = (
                self.wallet_address if self.me 
                else self.generate_eth_address()
            )
            
            tx_params = await self.build_transaction_params(
                to=to_address,
                value=self.to_wei(amount, "ether")
            )

            status, tx_hash = await self._process_transaction(tx_params)

            await show_trx_log(
                self.wallet_address,
                f"Transfer {amount} STT to {to_address}",
                status,
                tx_hash
            )

            return (True, tx_hash) if status else (False, f"Transaction failed: {tx_hash}")

        except Exception as error:
            error_msg = f"Error in transfer_stt: {str(error)}"
            await self.logger_msg(
                msg=f"Account {self.wallet_address} | {error_msg}", 
                type_msg="error", method_name="transfer_stt"
            )
            return False, error_msg