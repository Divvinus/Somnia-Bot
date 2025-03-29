import random
import secrets

from eth_keys import keys
from eth_utils import to_checksum_address

from core.wallet import Wallet
from loader import config
from logger import log
from models import Account
from utils.logger_trx import show_trx_log


class TransferSTTModule(Wallet):
    MINIMUM_BALANCE: float = 0.001
    GAS_LIMIT: int = 21000

    def __init__(self, account: Account, rpc_url: str, me: bool = False) -> None:
        super().__init__(account.private_key, rpc_url, account.proxy)
        self.me: bool = me

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
        log.info(f"Account {self.wallet_address} | Processing transfer_stt...")

        try:
            balance = await self.human_balance()
            status, amount = self._calculate_transfer_amount(balance)
            if not status:
                error_msg = f"Account {self.wallet_address} | {amount}"
                return status, amount

            to_address = (
                self.wallet_address if self.me 
                else self.generate_eth_address()
            )

            transaction = {
                "from": self.wallet_address,
                "to": to_address,
                "value": self.to_wei(amount, "ether"),
                "nonce": await self.transactions_count(),
                "gasPrice": await self.eth.gas_price,
                "gas": self.GAS_LIMIT,
            }

            await self.check_trx_availability(transaction)
            status, tx_hash = await self._process_transaction(transaction)

            show_trx_log(
                self.wallet_address,
                f"Transfer {amount} STT to {to_address}",
                status,
                tx_hash,
                config.somnia_explorer,
            )

            return (True, tx_hash) if status else (False, f"Transaction failed: {tx_hash}")

        except Exception as error:
            error_msg = f"Error in transfer_stt: {str(error)}"
            log.error(f"Account {self.wallet_address} | {error_msg}")
            return False, error_msg