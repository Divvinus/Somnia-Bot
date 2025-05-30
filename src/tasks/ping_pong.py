import random

from web3.contract import AsyncContract
from typing import Self

from config.settings import sleep_between_minting, sleep_between_swap
from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import (
    Account,
    PingTokensContract,
    PongTokensContract,
    PingPongRouterContract,
)
from src.utils import show_trx_log, random_sleep
from config.settings import MAX_RETRY_ATTEMPTS, RETRY_SLEEP_RANGE


class MintPingPongModule(Wallet, AsyncLogger):
    def __init__(self, account: Account, rpc_url: str) -> None:
        Wallet.__init__(self, account.private_key, rpc_url, account.proxy)
        AsyncLogger.__init__(self)

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

    async def _mint_tokens(
        self,
        contract_model: PingTokensContract | PongTokensContract,
        token_name: str,
    ) -> tuple[bool, str | dict]:
        await self.logger_msg(
            f"Account {self.wallet_address} | Processing mint {token_name}...", "info", self.wallet_address
        )

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                contract: AsyncContract = await self.get_contract(contract_model)
                balance = await contract.functions.balanceOf(self.wallet_address).call()

                if balance > 0:
                    msg = f"Tokens {token_name} already minted"
                    await self.logger_msg(msg=msg, type_msg="success", address=self.wallet_address)
                    return True, "already_minted"

                tx_params = await self.build_transaction_params(contract.functions.mint())
                return await self._process_transaction(tx_params)

            except Exception as error:
                error_msg = f"Error: {str(error)}"
                await self.logger_msg(
                    error_msg, "error", self.wallet_address, "_mint_tokens"
                )
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                
        return False, f"Failed mint Ping/Pong after {MAX_RETRY_ATTEMPTS} attempts"

    async def run(self) -> bool:
        contracts = [
            (PingTokensContract(), "PING"),
            (PongTokensContract(), "PONG"),
        ]
        random.shuffle(contracts)
        success_count = 0

        for contract_model, token_name in contracts:
            status, result = await self._mint_tokens(contract_model, token_name)

            if "ACCOUNT_DOES_NOT_EXIST" in result:
                await self.logger_msg(
                    f"First register an account with the Somnia project, then come back and mint NFTs", 
                    "warning", self.wallet_address, "run"
                )
                return status, result

            if result != "already_minted":
                await show_trx_log(
                    self.wallet_address, f"Mint {token_name}", status, result
                )

            if status:
                if success_count == 0 and result != "already_minted":
                    await random_sleep(
                        self.wallet_address,
                        **sleep_between_minting
                    )
                success_count += 1
            else:
                await self.logger_msg(
                    f"Failed to mint {token_name}", "warning", self.wallet_address, "run"
                )

        if success_count == len(contracts):
            return True, "Successfully minted tokens"
        return False, "Unknown cause of error"


class SwapPingPongModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)

    async def _calculate_amount(
        self,
        contract_model: PingTokensContract | PongTokensContract,
        token_name: str,
    ) -> int | bool:
        balance = await self.token_balance(contract_model.address)

        if balance <= 0 or balance is None:
            await self.logger_msg(
                f'You do not have the tokens for the "{token_name}" swap', 
                "warning", self.wallet_address, "_calculate_amount"
            )
            return False

        random_percentage = random.uniform(10, 35)
        amount = balance * (random_percentage / 100)
        amount_human = int(round(self.from_wei(amount, "ether")))
        return int(self.to_wei(amount_human, "ether"))

    async def _approve_tokens(
        self,
        token_in_contract: PingTokensContract | PongTokensContract,
        token_in_name: str,
        amount_to_swap: int,
    ) -> tuple[bool, str]:
        await self.logger_msg(
            f"Approve {self.from_wei(amount_to_swap, 'ether')} tokens {token_in_name}", 
            "info", self.wallet_address
        )

        router_address = PingPongRouterContract().address
        approved, result = await self._check_and_approve_token(
            token_in_contract.address, router_address, amount_to_swap
        )
        return (approved, result) if approved else (False, result)

    async def _swap_tokens(
        self,
        token_in_contract: PingTokensContract | PongTokensContract,
        token_in_name: str,
        token_out_contract: PingTokensContract | PongTokensContract,
        token_out_name: str,
    ) -> tuple[bool, str]:
        await self.logger_msg(f"Processing swap...", "info", self.wallet_address)

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                amount_to_swap = await self._calculate_amount(token_in_contract, token_in_name)
                if not amount_to_swap:
                    return False, "insufficient_balance"

                approved, result = await self._approve_tokens(
                    token_in_contract, token_in_name, amount_to_swap
                )
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
                    0,
                )
                
                tx_params = await self.build_transaction_params(
                    router_contract.functions.exactInputSingle(params)
                )
                
                await self.logger_msg(
                    f"Swap {self.from_wei(amount_to_swap, 'ether')} "
                    f"{token_in_name} to {token_out_name}", 
                    "info", self.wallet_address
                )
                
                return await self._process_transaction(tx_params)

            except Exception as error:
                error_msg = f"Error: {error}"
                await self.logger_msg(
                    error_msg, "error", self.wallet_address, "_swap_tokens"
                )
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
        
        return False, f"Failed swap Ping/Pong after {MAX_RETRY_ATTEMPTS} attempts"

    async def run(self) -> bool:
        contracts = [
            (PingTokensContract(), "PING"),
            (PongTokensContract(), "PONG"),
        ]
        random.shuffle(contracts)
        success_count = 0

        for i, (token_in_contract, token_in_name) in enumerate(contracts):
            token_out_contract, token_out_name = contracts[(i + 1) % len(contracts)]
            
            status, result = await self._swap_tokens(
                token_in_contract,
                token_in_name,
                token_out_contract,
                token_out_name,
            )

            if "ACCOUNT_DOES_NOT_EXIST" in result:
                await self.logger_msg(
                    f"First register an account with the Somnia project", 
                    "warning", self.wallet_address, "run"
                )
                return status, result

            if status:
                await show_trx_log(
                    self.wallet_address,
                    f"Swap {token_in_name} to {token_out_name}",
                    status,
                    result
                )

            if status:
                if success_count == 0:
                    await random_sleep(
                        self.wallet_address,
                        **sleep_between_swap
                    )
                success_count += 1
            else:
                await self.logger_msg(
                    f"Failed swap {token_in_name}. Error: {result}", "warning", self.wallet_address, "run"
                )

        if success_count == len(contracts):
            return True, "Successfully swapped tokens"
        return False, "Unknown cause of error"