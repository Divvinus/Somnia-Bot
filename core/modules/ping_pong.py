import asyncio
import random

from web3.contract import AsyncContract

from loader import config
from logger import log
from core.wallet import Wallet
from models import Account, PingTokensContract, PongTokensContract, PingPongRouterContract
from utils import show_trx_log, random_sleep


class MintPingPongModule(Wallet):
    def __init__(self, account: Account, rpc_url: str):
        super().__init__(account.private_key, rpc_url, account.proxy)

    async def _mint_tokens(self, contract_model, token_name: str) -> tuple[bool, str | dict]:
        log.info(f"Account {self.wallet_address} | Processing mint {token_name}...")
        
        try:
            contract: AsyncContract = await self.get_contract(contract_model)
            balance = await contract.functions.balanceOf(self.wallet_address).call()
            
            if balance > 0:
                log.success(f"Account {self.wallet_address} | Tokens {token_name} already minted")
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
            (PingTokensContract(), "PING"),
            (PongTokensContract(), "PONG")
        ]
        random.shuffle(contracts)
        success_count = 0
        
        for contract_model, token_name in contracts:
            status, result = await self._mint_tokens(contract_model, token_name)
            
            if "ACCOUNT_DOES_NOT_EXIST" in result:
                log.warning(f"Account {self.wallet_address} | First register an account with the Somnia project, then come back and mint nfts")
                return False
                
            if result != "already_minted":
                show_trx_log(self.wallet_address, f"Mint {token_name}", status, result, config.somnia_explorer)
            
            if status:
                if success_count == 0:
                    await random_sleep(self.wallet_address, 5, 30)
                success_count += 1
            else:
                log.warning(f"Account {self.wallet_address} | Failed to mint {token_name}")

        return success_count == len(contracts)
    

class SmapPingPongModule(Wallet):
    def __init__(self, account: Account, rpc_url: str):
        super().__init__(account.private_key, rpc_url, account.proxy)
        
    async def _calculate_amount(
        self, 
        contract_model: PingTokensContract | PongTokensContract, 
        token_name: str
    ) -> int | bool:
        
        balance = await self.token_balance(contract_model.address)
        
        if balance <= 0 or balance is None:
            log.success(
                f'Account {self.wallet_address} | You do not have the tokens for the "{token_name}" swap'
            )
            return False
        
        random_percentage = random.uniform(10, 35)
        amount = balance * (random_percentage / 100)
        amount_human = int(round(self.from_wei(amount, 'ether')))
        amount_to_swap = self.to_wei(amount_human, 'ether')
        
        return int(amount_to_swap)
    
    async def _approve_tokens(
        self, 
        token_in_contract: PingTokensContract | PongTokensContract, 
        token_in_name: str,
        amount_to_swap: int
    ) -> tuple[bool, str]:
        
        log.info(f"Account {self.wallet_address} | Appove {self.from_wei(amount_to_swap, 'ether')} tokens {token_in_name}")
        
        router_address = PingPongRouterContract().address
        
        approved, result = await self._check_and_approve_token(
            token_in_contract.address, router_address, amount_to_swap
        )
        await asyncio.sleep(5)
        
        if not approved:
            return False, result
        
        return True, result
        
    async def _swap_tokens(
        self, 
        token_in_contract: PingTokensContract | PongTokensContract, 
        token_in_name: str,
        token_out_contract: PingTokensContract | PongTokensContract,
        token_out_name: str
    ) -> tuple[bool, str]:
        
        log.info(
            f"Account {self.wallet_address} | Processing swap..."
        )
        
        try:            
            amount_to_swap = await self._calculate_amount(token_in_contract, token_in_name)
            
            if not amount_to_swap:
                return False, "False"
            
            approved, result = await self._approve_tokens(token_in_contract, token_in_name, amount_to_swap)
            if not approved:
                return approved, result
                
            router_contract = await self.get_contract(PingPongRouterContract())     
            
            params = (
                token_in_contract.address,
                token_out_contract.address,
                500,
                self.wallet_address,
                amount_to_swap,
                0,
                0
            )
            
            swap_function = router_contract.functions.exactInputSingle(params)             
            
            tx_params = {
                "nonce": await self.transactions_count(),
                "gasPrice": await self.eth.gas_price,
                "from": self.wallet_address,
                "value": 0
            }

            try:
                gas_estimate = await swap_function.estimate_gas(tx_params)
                tx_params["gas"] = int(gas_estimate * 1.2)
            except Exception as estimate_error:
                log.debug(f"Gas estimate failed: {estimate_error}. Using fallback value")
                tx_params["gas"] = 3_000_000
                
            log.info(
                f"Account {self.wallet_address} | Swap {self.from_wei(amount_to_swap, 'ether')} {token_in_name} to {token_out_name}"
            )

            transaction = await swap_function.build_transaction(tx_params)
            await self.check_trx_availability(transaction)
            return await self._process_transaction(transaction)

        except Exception as error:
            log.error(f"Account {self.wallet_address} | Error: {str(error)}")
            return False, str(error)
    
    async def run(self):
        contracts = [
            (PingTokensContract(), "PING"),
            (PongTokensContract(), "PONG")
        ]
        random.shuffle(contracts)
        success_count = 0

        for i, (token_in_contract, token_in_name) in enumerate(contracts):
            token_out_contract, token_out_name = contracts[(i + 1) % len(contracts)]
            
            status, result = await self._swap_tokens(
                token_in_contract, token_in_name,
                token_out_contract, token_out_name
            )
            
            if "ACCOUNT_DOES_NOT_EXIST" in result:
                log.warning(f"Account {self.wallet_address} | First register an account with the Somnia project")
                return False
                
            if status:
                show_trx_log(self.wallet_address, f"Swap {token_in_name} to {token_out_name}", status, result, config.somnia_explorer)
            
            if status:
                if success_count == 0:
                    await random_sleep(self.wallet_address, 30, 120)
                success_count += 1
            else:
                log.warning(f"Account {self.wallet_address} | Failed swap {token_in_name}. Error: {result}")

        return success_count == len(contracts)