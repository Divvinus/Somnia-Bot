from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple, Union

from better_proxy import Proxy
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress, HexStr
from pydantic import HttpUrl
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.contract import AsyncContract
from web3.eth import AsyncEth
from web3.types import Nonce, TxParams

from core.exceptions.base import InsufficientFundsError, WalletError
from models.onchain import *
import asyncio
from logger import log


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ETH_ADDRESS = "0x4200000000000000000000000000000000000006"

Account.enable_unaudited_hdwallet_features()


class Wallet(AsyncWeb3, Account):
    def __init__(self, private_key: str, rpc_url: Union[HttpUrl, str], proxy: Optional[Proxy] = None):
        provider = AsyncHTTPProvider(
            str(rpc_url),
            request_kwargs={
                "proxy": proxy.as_url if proxy else None,
                "ssl": False
            }
        )
        super().__init__(provider, modules={"eth": (AsyncEth,)})
        
        self.keypair = self._initialize_keypair(private_key)
        self._contracts_cache: Dict[str, AsyncContract] = {}
        
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.provider, '_session') and self.provider._session:
            await self.provider._session.close()

    def __del__(self):
        if hasattr(self.provider, '_session') and self.provider._session:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.provider._session.close())
        
    @staticmethod
    def _initialize_keypair(private_key: str) -> Account:
        if not private_key:
            raise WalletError("Empty private_key provided")
        return (Account.from_mnemonic(private_key) 
                if len(private_key.split()) in (12, 24) 
                else Account.from_key(private_key))

    @property
    def wallet_address(self) -> ChecksumAddress:
        return self.keypair.address

    @staticmethod
    @lru_cache(maxsize=1000)
    def _get_checksum_address(address: str) -> ChecksumAddress:
        return AsyncWeb3.to_checksum_address(address)

    async def get_contract(self, contract: Union[BaseContract, str, object]) -> AsyncContract:
        if isinstance(contract, str):
            address = self._get_checksum_address(contract)
            if address not in self._contracts_cache:
                temp_contract = ERC20Contract(address="")
                abi = await temp_contract.get_abi()
                self._contracts_cache[address] = self.eth.contract(
                    address=address,
                    abi=abi
                )
            return self._contracts_cache[address]
        
        if isinstance(contract, BaseContract):
            address = self._get_checksum_address(contract.address)
            if address not in self._contracts_cache:
                abi = await contract.get_abi()
                self._contracts_cache[address] = self.eth.contract(
                    address=address,
                    abi=abi
                )
            return self._contracts_cache[address]

        if hasattr(contract, "address") and hasattr(contract, "abi"):
            address = self._get_checksum_address(contract.address)
            if address not in self._contracts_cache:
                self._contracts_cache[address] = self.eth.contract(
                    address=address,
                    abi=contract.abi
                )
            return self._contracts_cache[address]

        raise TypeError("Invalid contract type: expected BaseContract, str, or contract-like object")

    async def token_balance(self, token_address: str) -> int:
        contract = await self.get_contract(token_address)
        return await contract.functions.balanceOf(
            self._get_checksum_address(self.keypair.address)
        ).call()

    @staticmethod
    def _is_native_token(token_address: str) -> bool:
        return token_address in (ZERO_ADDRESS, ETH_ADDRESS)

    async def convert_amount_to_decimals(self, amount: float, token_address: str) -> int:
        token_address = self._get_checksum_address(token_address)
        
        if self._is_native_token(token_address):
            return self.to_wei(Decimal(str(amount)), 'ether')

        contract = await self.get_contract(token_address)
        decimals = await contract.functions.decimals().call()
        return int(Decimal(str(amount)) * Decimal(str(10 ** decimals)))
    
    async def convert_amount_from_decimals(self, amount: int, token_address: str) -> float:
        token_address = self._get_checksum_address(token_address)
        
        if self._is_native_token(token_address):
            return float(self.from_wei(amount, 'ether'))

        contract = await self.get_contract(token_address)
        decimals = await contract.functions.decimals().call()
        return float(Decimal(str(amount)) / Decimal(str(10 ** decimals)))

    async def transactions_count(self) -> Nonce:
        try:
            return await self.eth.get_transaction_count(self.keypair.address, 'pending')
        except Exception as e:
            log.error(f"Error during getting nonce: {str(e)}")
            raise

    async def check_balance(self) -> None:
        balance = await self.eth.get_balance(self.keypair.address)
        if balance <= 0:
            raise InsufficientFundsError("ETH balance is empty")

    async def human_balance(self) -> float:
        balance = await self.eth.get_balance(self.keypair.address)
        return float(self.from_wei(balance, "ether"))

    async def _build_base_transaction(self, contract_function: Any) -> TxParams:
        gas_estimate = await contract_function.estimate_gas({"from": self.keypair.address})
        return {
            "gasPrice": await self.eth.gas_price,
            "nonce": await self.transactions_count(),
            "gas": int(gas_estimate * 1.2),
        }

    async def check_trx_availability(self, transaction: TxParams) -> None:
        balance = await self.human_balance()
        required = float(self.from_wei(int(transaction.get('value', 0)), "ether"))

        if balance < required:
            raise InsufficientFundsError(
                f"ETH balance insufficient. Required: {required} ETH | Available: {balance} ETH"
            )

    async def _process_transaction(self, transaction: Any) -> Tuple[bool, str]:
        try:
            status, result = await self.send_and_verify_transaction(transaction)
            return status, result
        except Exception as error:
            return False, str(error)

    async def get_signature(self, text: str, private_key: Optional[str] = None) -> HexStr:
        encoded_message = encode_defunct(text=text)
        signing_keypair = (self.from_key(private_key) if private_key else self.keypair)
        signature = signing_keypair.sign_message(encoded_message)
        return HexStr(signature.signature.hex())

    async def send_and_verify_transaction(self, trx: Any) -> Tuple[bool, str]:
        max_attempts = 3
        current_attempt = 0
        last_error = None
        
        while current_attempt < max_attempts:
            try:
                signed = self.keypair.sign_transaction(trx)
                tx_hash = await self.eth.send_raw_transaction(signed.raw_transaction)
                receipt = await self.eth.wait_for_transaction_receipt(tx_hash)
                return receipt["status"] == 1, tx_hash.hex()
                
            except Exception as e:
                error_str = str(e)
                last_error = e
                current_attempt += 1
                
                if "NONCE_TOO_SMALL" in error_str or "nonce too low" in error_str.lower():
                    log.warning(f"Nonce too small. Current: {trx.get('nonce')}. Getting new nonce.")
                    try:
                        new_nonce = await self.eth.get_transaction_count(self.keypair.address, 'pending')
                        trx['nonce'] = new_nonce
                    except Exception as nonce_error:
                        log.error(f"Error during getting new nonce: {str(nonce_error)}")
                        
                elif "NONCE_TOO_HIGH" in error_str or "nonce too high" in error_str.lower():
                    log.warning(f"Nonce too high. Current: {trx.get('nonce')}. Decreasing.")
                    if 'nonce' in trx and trx['nonce'] > 0:
                        trx['nonce'] = trx['nonce'] - 1
                        
                else:
                    log.error(f"Error during sending transaction: {error_str}")
                    return False, error_str
                    
                await asyncio.sleep(2)
        
        return False, f"Failed to execute transaction after {max_attempts} attempts. Last error: {str(last_error)}"

    async def _check_and_approve_token(
        self, 
        token_address: str, 
        spender_address: str, 
        amount: int
    ) -> Tuple[bool, str]:
        try:
            token_contract = await self.get_contract(token_address)
            
            current_allowance = await token_contract.functions.allowance(
                self.wallet_address, 
                spender_address
            ).call()

            if current_allowance >= amount:
                return True, "Allowance already sufficient"

            approve_tx = await token_contract.functions.approve(
                spender_address, 
                amount
            ).build_transaction({
                "nonce": await self.transactions_count(),
                "gasPrice": int(await self.eth.gas_price * 1.25),
                "gas": 3_000_000,
                "from": self.wallet_address,
            })

            await asyncio.sleep(5)
            
            success, result = await self._process_transaction(approve_tx)
            if not success:
                raise WalletError(f"Approval failed: {result}")

            return True, "Approval successful"

        except Exception as error:
            return False, f"Error during approval: {str(error)}"