import secrets
from typing import Tuple, Union
import random

from eth_keys import keys
from eth_utils import to_checksum_address

from core.wallet import Wallet
from logger import log
from models import Account
from utils.logger_trx import show_trx_log
from loader import config


class TransferSTTModule(Wallet):
    MINIMUM_BALANCE = 0.001
    GAS_LIMIT = 21000
    
    def __init__(self, account: Account, rpc_url: str):
        """
        Initialize transfer module.

        Args:
            account: Account object containing private key/mnemonic and proxy
            rpc_url: Somnia testnet network RPC endpoint URL
        """
        super().__init__(account.private_key, rpc_url, account.proxy)
    
    @staticmethod
    def generate_eth_address() -> str:
        """
        Generate new EVM address from random private key.
        
        Returns:
            str: Checksum formatted EVM address
        """
        private_key = keys.PrivateKey(secrets.token_bytes(32))
        return to_checksum_address(private_key.public_key.to_address())
    
    def _calculate_transfer_amount(self, balance: float) -> Union[float, None]:
        """
        Determine transfer amount based on current balance.
        Randomly selects amount from available options based on balance threshold.

        Args:
            balance: Current wallet balance in STT
        Returns:
            float or None: Transfer amount or None if balance insufficient
        """
        if balance > 0.01:
            return random.choice([0.01, 0.005, 0.001])
        elif balance > 0.005:
            return random.choice([0.005, 0.001])
        elif balance > 0.001:
            return 0.001
        return None
    
    async def transfer_stt(self) -> Tuple[bool, str]:
        """
        Execute STT transfer to randomly generated address.
        
        Transfer amount is determined based on current wallet balance.
        Checks transaction availability and executes with set gas limit.

        Returns:
            Tuple[bool, str]: (operation status, tx_hash or error message)
        """
        log.info(f"Account {self.wallet_address} | Processing transfer_stt...")
        
        try:
            balance = await self.human_balance()
            amount = self._calculate_transfer_amount(balance)
            to_address = self.generate_eth_address()
            
            if not amount:
                error_msg = f"Account {self.wallet_address} | Not enough balance"
                log.error(error_msg)
                return False, error_msg
            
            transaction = {
                "from": self.wallet_address,
                "to": to_address,
                "value": self.to_wei(amount, "ether"),
                "nonce": await self.transactions_count(),
                "gasPrice": await self.eth.gas_price,
                "gas": self.GAS_LIMIT
            }
            
            await self.check_trx_availability(transaction)
            status, tx_hash = await self._process_transaction(transaction)
            
            show_trx_log(self.wallet_address, f"Transfer {amount} STT to {to_address}", status, tx_hash, 
                        config.somnia_explorer)
            
            return (True, tx_hash) if status else (False, f"Transaction failed: {tx_hash}")
            
        except Exception as e:
            error_msg = f"Error in transfer_stt: {str(e)}"
            log.error(f"Account {self.wallet_address} | {error_msg}")
            return False, error_msg