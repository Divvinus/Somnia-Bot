from typing import Self
from web3 import AsyncWeb3

from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import (
    Account, 
    YappersNFTContract, 
    ShannonNFTContract, 
    NerzoNFTContract, 
    SomniNFTContract,
    CommunityNFTContract,
    BeaconNFTContract
)
from src.utils import show_trx_log, random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE

class BaseNFTMintModule(Wallet, AsyncLogger):
    module_name = "NFT Mint"

    def __init__(self, account: Account, contract_config) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        self.contract_config = contract_config

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

    def get_claim_params(self):
        return {
            "recipient": self.wallet_address,
            "amount": 1,
            "token": AsyncWeb3.to_checksum_address("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
            "deadline": 1000000000000000 if self.module_name == "Shannon NFT" else 0,
            "permit": (
                [],
                2**256 - 1,
                0,
                AsyncWeb3.to_checksum_address("0x0000000000000000000000000000000000000000")
            ),
            "signature": b''
        }

    async def run(self) -> tuple[bool, str]:
        await self.logger_msg(
            f"Starting {self.module_name}", "info", self.wallet_address
        )

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                contract = await self.get_contract(self.contract_config)
                params = self.get_claim_params()

                tx_params = await self.build_transaction_params(
                    to=contract.address,
                    contract_function=contract.functions.claim(
                        params["recipient"],
                        params["amount"],
                        params["token"],
                        params["deadline"],
                        params["permit"],
                        params["signature"]
                    ),
                    value=self.to_wei(0.001, 'ether') if self.module_name == "Shannon NFT" else 0
                )

                status, tx_hash = await self._process_transaction(tx_params)

                await show_trx_log(
                    self.wallet_address, self.module_name,
                    status, tx_hash
                )

                return status, tx_hash
            
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                await self.logger_msg(
                    error_msg, "error", self.wallet_address, "run"
                )
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
            
        return False, f"Failed to mint {self.module_name} after {MAX_RETRY_ATTEMPTS} attempts"

class YappersNFTModule(BaseNFTMintModule):
    module_name = "Yappers NFT"

    def __init__(self, account: Account) -> None:
        super().__init__(account, YappersNFTContract())


class ShannonNFTModule(BaseNFTMintModule):
    module_name = "Shannon NFT"

    def __init__(self, account: Account) -> None:
        super().__init__(account, ShannonNFTContract())
        

class NerzoNFTModule(BaseNFTMintModule):
    module_name = "Nerzo NFT"

    def __init__(self, account: Account) -> None:
        super().__init__(account, NerzoNFTContract())
        

class SomniNFTModule(BaseNFTMintModule):
    module_name = "Somni NFT"

    def __init__(self, account: Account) -> None:
        super().__init__(account, SomniNFTContract())
        
class BeaconNFTModule(BaseNFTMintModule):
    module_name = "Beacon NFT"

    def __init__(self, account: Account) -> None:
        super().__init__(account, BeaconNFTContract())
        
class CommunityNFTModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

    async def run(self) -> tuple[bool, str]:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.logger_msg(
                    "Starting mint Community Member of Somnia NFT", "info", self.wallet_address
                )

                contract = await self.get_contract(CommunityNFTContract())

                tx_params = await self.build_transaction_params(
                    contract.functions.mint(),
                    value=self.to_wei(0.05, "ether")
                )
                
                status, tx_hash = await self._process_transaction(tx_params)
                
                await show_trx_log(
                    self.wallet_address, "Mint Community Member of Somnia NFT", status, tx_hash
                )
                
                return status, tx_hash

            except Exception as e:
                error_msg = f"Error: {str(e)}"
                await self.logger_msg(
                    error_msg, "error", self.wallet_address, "run"
                )
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
            
        return False, f"Failed to mint Community Member of Somnia NFT after {MAX_RETRY_ATTEMPTS} attempts"