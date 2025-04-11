import re
import random
from faker import Faker

from typing import Self

from src.logger import AsyncLogger
from src.models import Account, ERC20Contract
from src.wallet import Wallet



class ContractGeneratorData:
    def __init__(self):
        self.fake = Faker()

    def generate_contract_name(self) -> str:
        word = self.fake.word()
        contract_name = ''.join(x.capitalize() for x in word.split())
        contract_name = re.sub(r'[^a-zA-Z]', '', contract_name)
        return contract_name

    def generate_token_details(self) -> dict:
        return {
            'token_name': f"{self.fake.company()}",
            'token_symbol': self.generate_token_symbol(),
            'total_supply': self.generate_total_supply()
        }

    def generate_token_symbol(self, max_length: int = 5) -> str:
        symbol = ''.join(self.fake.random_uppercase_letter() for _ in range(min(max_length, 5)))
        return symbol

    def generate_total_supply(self) -> int:
        round_multipliers = [1000, 10_000, 100_000, 1_000_000]
        base_numbers = [1, 5, 10, 25, 50, 100]
        base = random.choice(base_numbers)
        multiplier = random.choice(round_multipliers)
        total_supply = base * multiplier
        return max(10_000, min(total_supply, 1_000_000))
    
    
class DeployContractWorker(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        from bot_loader import config
        Wallet.__init__(self, account.private_key, rpc_url=config.somnia_rpc, proxy=account.proxy)
        AsyncLogger.__init__(self)
        
        self.erc20_contract = ERC20Contract()
        
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
        
    async def deploy_erc_20_contract(self) -> tuple[bool, str]:        
        generator = ContractGeneratorData()
        token_details = generator.generate_token_details()
        name = token_details['token_name']
        symbol = token_details['token_symbol']
        total_supply = token_details['total_supply']
        decimals = 18
        initial_supply_wei = total_supply * 10**decimals

        await self.logger_msg(
            msg=f"Preparing to deploy a contract {name} ({symbol})", 
            type_msg="info", address=self.wallet_address
        )
        
        abi = await self.erc20_contract.get_abi()
        bytecode = await self.erc20_contract.get_bytecode()
        contract = self.eth.contract(abi=abi, bytecode=bytecode)

        deploy_tx = await contract.constructor(name, symbol, initial_supply_wei).build_transaction({
            'from': self.wallet_address,
            'nonce': await self.get_nonce(),
            'gasPrice': await self.eth.gas_price,
        })

        gas_estimate = await self.eth.estimate_gas(deploy_tx)
        deploy_tx['gas'] = int(gas_estimate * 1.2)
        
        status, tx_hash = await self.send_and_verify_transaction(deploy_tx)
        
        if status:
            receipt = await self.eth.wait_for_transaction_receipt(tx_hash)
            deployed_address = receipt['contractAddress']
            await self.logger_msg(
                msg=f"Contract deployed successfully at address: {deployed_address}", 
                type_msg="success", address=self.wallet_address
            )
            return status, tx_hash
        else:
            await self.logger_msg(
                msg=f"Error deploying contract", type_msg="error",
                address=self.wallet_address, method_name="deploy_contract"
            )
            return status, tx_hash