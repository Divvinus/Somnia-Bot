from typing import Self

from web3 import AsyncWeb3
from faker import Faker
import re

from src.api import BaseAPIClient
from src.wallet import Wallet
from src.logger import AsyncLogger
from src.models import Account, ZNSContract
from src.utils import show_trx_log, random_sleep
from bot_loader import config
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE


class MintDomenModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        self.api_client = BaseAPIClient(
            "https://contracts-api.mintair.xyz/api", account.proxy
        )        
        self.faker = Faker()
        
    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        self.api_client = await self.api_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'api_client') and self.api_client:
            try:
                await self.api_client.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                await self.logger_msg(
                    f"Error closing API client: {str(e)}", "error", self.wallet_address
                )
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

    async def generate_domain_name(self):
        while True:
            domain_name = self.faker.domain_name()
            name = re.split(r'\.', domain_name)[0]
            if len(name) > 5:
                return name
            
    async def register_domain(self, name: str) -> tuple[bool, str]:
        try:
            await self.logger_msg("Minting domain...", "info", self.wallet_address)

            contract = await self.get_contract(ZNSContract())
            
            length_of_domain = len(name)
            price = await contract.functions.priceToRegister(length_of_domain).call()
            
            balance = await self.eth.get_balance(self.wallet_address)
            if balance < price:
                balance_eth = self.from_wei(balance, 'ether')
                price_eth = self.from_wei(price, 'ether')
                error_msg = f"Insufficient balance for mint domen. Balance: {balance_eth:.6f} ETH, Price: {price_eth:.6f} ETH"
                await self.logger_msg(error_msg, "error", self.wallet_address)
                return False, "Insufficient balance"

            tx_params = await self.build_transaction_params(
                contract.functions.registerDomains(
                    [self.wallet_address],
                    [name],
                    [1],
                    AsyncWeb3.to_checksum_address('0x0000000000000000000000000000000000000000'),
                    0   
                ),
                value=price
            )
            
            result, tx_hash = await self._process_transaction(tx_params)
            if not result:
                error_msg = f"Transaction failed: {tx_hash}"
                return False, tx_hash

            return True, tx_hash

        except Exception as e:
            error_str = str(e)
            if '0x3a81d6fc' in error_str:
                error_msg = f"Domain '{name}' already registered"
                await self.logger_msg(error_msg, "warning", self.wallet_address, "register_domain")
                return False, "domain_already_registered"
            else:
                error_msg = f"Unexpected error: {error_str}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "register_domain")
                return False, error_msg

    async def run(self) -> tuple[bool, str]:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                name = await self.generate_domain_name()
                
                await self.logger_msg(
                    f"Attempt {attempt}/{MAX_RETRY_ATTEMPTS}: registering domain '{name}'", "info", self.wallet_address
                )
                
                status, result = await self.register_domain(name)
                
                if status or result != "domain_already_registered":
                    await show_trx_log(
                        self.wallet_address, f"Register domain: {name}", status, result
                    )
                    return status, "Success" if status else result
                
                if attempt < MAX_RETRY_ATTEMPTS:
                    await self.logger_msg(f"Trying another domain name...", "info", self.wallet_address)
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "run")
                return False, str(e)
            
        return False, f"Failed to register domain after {MAX_RETRY_ATTEMPTS} attempts"