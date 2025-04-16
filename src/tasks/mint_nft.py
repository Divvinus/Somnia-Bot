from typing import Self
from web3 import AsyncWeb3

from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import Account, YappersNFTContract, ShannonNFTContract
from src.utils.logger_trx import show_trx_log


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
            msg=f"Starting {self.module_name}",
            type_msg="info",
            address=self.wallet_address
        )

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
            await self.logger_msg(
                msg=f"Error: {str(e)}", type_msg="error", 
                address=self.wallet_address, method_name="run"
            )
            return False, str(e)

class YappersNFTModule(BaseNFTMintModule):
    module_name = "Yappers NFT"

    def __init__(self, account: Account) -> None:
        super().__init__(account, YappersNFTContract())


class ShannonNFTModule(BaseNFTMintModule):
    module_name = "Shannon NFT"

    def __init__(self, account: Account) -> None:
        super().__init__(account, ShannonNFTContract())