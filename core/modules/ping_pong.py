import asyncio
import random

from loader import config
from logger import log
from core.wallet import Wallet
from models import Account, PingNFTContract, PongNFTContract
from utils.logger_trx import show_trx_log


class MintNftModule(Wallet):
    def __init__(self, account: Account, rpc_url: str):
        super().__init__(account.private_key, rpc_url, account.proxy)

    async def _mint_nft(self, contract_model, nft_name: str) -> tuple[bool, str | dict]:
        log.info(f"Account {self.wallet_address} | Processing mint {nft_name}...")
        
        try:
            contract = await self.get_contract(contract_model)
            balance = await contract.functions.balanceOf(self.wallet_address).call()
            
            if balance > 0:
                log.success(f"Account {self.wallet_address} | NFT {nft_name} already minted")
                return True, "already_minted"
            
            tx_params = {
                "nonce": await self.transactions_count(),
                "gasPrice": await self.eth.gas_price,
                "from": self.wallet_address,
                "value": 0
            }

            mint_function = contract.functions.mint()
            
            try:
                gas_estimate = await mint_function.estimate_gas(tx_params)
                tx_params["gas"] = int(gas_estimate * 1.2)
            except Exception as estimate_error:
                log.debug(f"Gas estimate failed: {estimate_error}. Using fallback value")
                tx_params["gas"] = 3_000_000

            transaction = await mint_function.build_transaction(tx_params)
            await self.check_trx_availability(transaction)
            return await self._process_transaction(transaction)

        except Exception as error:
            log.error(f"Account {self.wallet_address} | Error: {str(error)}")
            return False, str(error)

    async def run(self):
        contracts = [
            (PingNFTContract(), "PING"),
            (PongNFTContract(), "PONG")
        ]
        random.shuffle(contracts)
        success_count = 0
        
        for contract_model, nft_name in contracts:
            status, result = await self._mint_nft(contract_model, nft_name)
            
            if "ACCOUNT_DOES_NOT_EXIST" in result:
                log.warning(f"Account {self.wallet_address} | First register an account with the Somnia project, then come back and mint nfts")
                return False
                
            if result != "already_minted":
                show_trx_log(self.wallet_address, f"Mint {nft_name}", status, result, config.somnia_explorer)
            
            if status:
                if success_count == 0:
                    delay = random.randint(5, 30)
                    log.info(f"Account {self.wallet_address} | Sleeping {delay} seconds")
                    await asyncio.sleep(delay)
                success_count += 1
            else:
                log.warning(f"Account {self.wallet_address} | Failed to mint {nft_name}")

        return success_count == len(contracts)