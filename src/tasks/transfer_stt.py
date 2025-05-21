import random
import secrets

from eth_keys import keys
from eth_utils import to_checksum_address
from typing import Self

from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account
from src.utils import show_trx_log, random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE


class TransferSTTModule(Wallet, AsyncLogger):
    MINIMUM_BALANCE: float = 0.001

    def __init__(self, account: Account, rpc_url: str, me: bool = False) -> None:
        Wallet.__init__(self, account.private_key, rpc_url, account.proxy)
        AsyncLogger.__init__(self)
        
        self.me: bool = me

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

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
        await self.logger_msg(f"Processing transfer_stt...", "info", self.wallet_address)
        error_messages = []
        
        try:
            balance = await self.human_balance()
            status, amount = self._calculate_transfer_amount(balance)
            if not status:
                await self.logger_msg(amount, "error", self.wallet_address, "transfer_stt")
                return status, amount

            to_address = (
                self.wallet_address if self.me 
                else self.generate_eth_address()
            )
        except Exception as error:
            error_msg = f"Error:{str(error)}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "transfer_stt")
            return False, error_msg

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.logger_msg(f"Transfer attempt {attempt+1}/{MAX_RETRY_ATTEMPTS}", "info", self.wallet_address)
                
                tx_params = await self.build_transaction_params(
                    to=to_address,
                    value=self.to_wei(amount, "ether")
                )

                status, tx_hash = await self._process_transaction(tx_params)

                if status:
                    await show_trx_log(self.wallet_address, f"Transfer {amount} STT to {to_address}", status, tx_hash)
                    return status, tx_hash
                    
                error_msg = f"Transaction failed: {tx_hash}"
                error_messages.append(error_msg)
                await self.logger_msg(error_msg, "error", self.wallet_address, "transfer_stt")

            except Exception as error:
                error_msg = f"Attempt {attempt+1} error: {str(error)}"
                error_messages.append(error_msg)
                await self.logger_msg(error_msg, "error", self.wallet_address, "transfer_stt")

            if attempt < MAX_RETRY_ATTEMPTS - 1:
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                
        return False, f"Transfer failed after {MAX_RETRY_ATTEMPTS} attempts. Errors:\n" + "\n".join(error_messages)