from faker import Faker
import re
from typing import Self

from src.models import Account, SomniaDomainsContract
from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.utils import show_trx_log, random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE


class SomniaDomainsModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        self.faker = Faker()

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

    def generate_domain_name(self) -> str:
        domain_name = self.faker.domain_name()
        return re.split(r'\.', domain_name)[0]

    async def run(self) -> tuple[bool, str]:
        await self.logger_msg("Starting mint Somnia Domain...", "info", self.wallet_address)
        error_messages = []
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.logger_msg(f"Mint attempt {attempt+1}/{MAX_RETRY_ATTEMPTS}", "info", self.wallet_address)
                
                balance = await self.human_balance()
                if balance < 1:
                    error_msg = f"Not enough balance for mint. Current: {balance} STT, Required: 1 STT"
                    await self.logger_msg(error_msg, "error", self.wallet_address, "run")
                    return False, error_msg
                    
                contract = await self.get_contract(SomniaDomainsContract())
                domain = self.generate_domain_name()

                tx_params = await self.build_transaction_params(
                    contract.functions.claimName(str(domain)),
                    value=self.to_wei(1, "ether")
                )

                status, tx_hash = await self._process_transaction(tx_params)
                
                await show_trx_log(self.wallet_address, f"Somnia Domain {domain}", status, tx_hash)
                
                if status:
                    return status, tx_hash
            except Exception as e:
                error_str = str(e)
                if "0x08c379a000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000016416c726561647920636c61696d65642061206e616d6500000000000000000000" in error_str:
                    success_msg = "Domain already minted for this account"
                    await self.logger_msg(success_msg, "success", self.wallet_address)
                    return True, success_msg
                    
                error_msg = f"Attempt {attempt+1} error: {error_str}"
                error_messages.append(error_msg)
                await self.logger_msg(error_msg, "error", self.wallet_address, "run")

            if attempt < MAX_RETRY_ATTEMPTS - 1:
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Failed after {MAX_RETRY_ATTEMPTS} attempts. Errors:\n" + "\n".join(error_messages)