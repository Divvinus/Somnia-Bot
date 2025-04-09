import asyncio
from decimal import Decimal
from typing import Any, Union, Self

from asyncio_throttle import Throttler
from better_proxy import Proxy
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress, HexStr
from pydantic import HttpUrl
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.contract import AsyncContract
from web3.eth import AsyncEth
from web3.types import Nonce, TxParams

from src.exceptions.custom_exceptions import InsufficientFundsError, WalletError
from src.models.onchain_model import BaseContract, ERC20Contract
from src.logger import AsyncLogger


logger = AsyncLogger()


class BlockchainError(Exception):
    """
    Base class for blockchain-related errors.
    """


class Wallet(AsyncWeb3, Account):
    ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
    
    def __init__(
        self, 
        private_key: str, 
        rpc_url: Union[HttpUrl, str], 
        proxy: Proxy | None = None
    ) -> None:
        self._provider = AsyncHTTPProvider(
            str(rpc_url),
            request_kwargs={
                "proxy": proxy.as_url if proxy else None,
                "ssl": False
            }
        )
        super().__init__(self._provider, modules={"eth": AsyncEth})
        
        self.private_key = self._initialize_private_key(private_key)
        self._contracts_cache: dict[str, AsyncContract] = {}
        self._throttler = Throttler(rate_limit=10, period=1)
        
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    @staticmethod
    def _initialize_private_key(private_key: str) -> Account:
        try:
            stripped_key = private_key.strip().lower()
            if not stripped_key.startswith("0x"):
                formatted_key = f"0x{stripped_key}"
            else:
                formatted_key = stripped_key
            return Account.from_key(formatted_key)
        except (ValueError, AttributeError) as error:
            raise WalletError(f"Invalid private key format: {error}") from error
        
    @property
    def wallet_address(self) -> ChecksumAddress:
        return self.private_key.address

    @property
    async def use_eip1559(self) -> bool:
        try:
            latest_block = await self.eth.get_block('latest')
            return 'baseFeePerGas' in latest_block
        except Exception as e:
            await logger.logger_msg(
                msg=f"Error checking EIP-1559 support: {e}", type_msg="error", 
                class_name=self.__class__.__name__, method_name="use_eip1559"
            )
            return False

    @staticmethod
    def _get_checksum_address(address: str) -> ChecksumAddress:
        return AsyncWeb3.to_checksum_address(address)   

    async def get_contract(self, contract: Union[BaseContract, str, object]) -> AsyncContract:
        if isinstance(contract, str):
            address = self._get_checksum_address(contract)
            if address not in self._contracts_cache:
                temp_contract = ERC20Contract(address="")
                abi = await temp_contract.get_abi()
                contract_instance = self.eth.contract(address=address, abi=abi)
                self._contracts_cache[address] = contract_instance
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
            self._get_checksum_address(self.private_key.address)
        ).call()

    def _is_native_token(self, token_address: str) -> bool:
        return token_address == self.ZERO_ADDRESS

    async def _get_cached_contract(self, token_address: str) -> AsyncContract:
        checksum_address = self._get_checksum_address(token_address)
        if checksum_address not in self._contracts_cache:
            self._contracts_cache[checksum_address] = await self.get_contract(checksum_address)
        return self._contracts_cache[checksum_address]

    async def convert_amount_to_decimals(self, amount: Decimal, token_address: str) -> int:
        checksum_address = self._get_checksum_address(token_address)
    
        if self._is_native_token(checksum_address):
            return self.to_wei(Decimal(str(amount)), 'ether')
        
        contract = await self._get_cached_contract(checksum_address)
        decimals = await contract.functions.decimals().call()
        return int(Decimal(str(amount)) * Decimal(10 ** decimals))
    
    async def convert_amount_from_decimals(self, amount: int, token_address: str) -> float:
        checksum_address = self._get_checksum_address(token_address)
    
        if self._is_native_token(checksum_address):
            return float(self.from_wei(amount, 'ether'))
        
        contract = await self._get_cached_contract(checksum_address)
        decimals = await contract.functions.decimals().call()
        return float(Decimal(amount) / Decimal(10 ** decimals))

    async def get_nonce(self) -> Nonce:
        for attempt in range(3):
            try:
                count = await self.eth.get_transaction_count(self.wallet_address, 'pending')
                return Nonce(count)
            except Exception as e:
                await logger.logger_msg(
                    msg=f"Failed to get nonce (attempt {attempt + 1}): {e}", type_msg="warning", 
                    class_name=self.__class__.__name__, method_name="get_nonce"
                )
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError("Failed to get nonce after 3 attempts") from e

    async def check_balance(self) -> None:
        balance = await self.eth.get_balance(self.private_key.address)
        if balance <= 0:
            raise InsufficientFundsError("ETH balance is empty")

    async def human_balance(self) -> float:
        balance = await self.eth.get_balance(self.private_key.address)
        return float(self.from_wei(balance, "ether"))
    
    async def has_sufficient_funds_for_tx(self, transaction: TxParams) -> bool:
        try:
            balance = await self.eth.get_balance(self.private_key.address)
            required = int(transaction.get('value', 0))
            
            if balance < required:
                required_eth = self.from_wei(required, 'ether')
                balance_eth = self.from_wei(balance, 'ether')
                raise InsufficientFundsError(
                    f"Insufficient ETH balance. Required: {required_eth:.6f} ETH, Available: {balance_eth:.6f} ETH"
                )
                
            return True
            
        except ValueError as error:
            raise ValueError(f"Invalid transaction parameters: {str(error)}") from error
        except Exception as error:
            raise BlockchainError(f"Failed to check transaction availability: {str(error)}") from error

    async def get_signature(self, text: str, private_key: str | None = None) -> HexStr:
        try:
            signing_key = (
                self.from_key(private_key) 
                if private_key 
                else self.private_key
            )

            encoded = encode_defunct(text=text)
            signature = signing_key.sign_message(encoded).signature
            
            return HexStr(signature.hex())

        except Exception as error:
            raise ValueError(f"Signing failed: {str(error)}") from error

    async def _estimate_gas_params(
        self,
        tx_params: dict,
        gas_buffer: float = 1.2,
        gas_price_buffer: float = 1.15
    ) -> dict:
        try:
            gas_estimate = await self.eth.estimate_gas(tx_params)
            tx_params["gas"] = int(gas_estimate * gas_buffer)
            
            if await self.use_eip1559:
                latest_block = await self.eth.get_block('latest')
                base_fee = latest_block['baseFeePerGas']
                priority_fee = await self.eth.max_priority_fee
                
                tx_params.update({
                    "maxPriorityFeePerGas": int(priority_fee * gas_price_buffer),
                    "maxFeePerGas": int((base_fee * 2 + priority_fee) * gas_price_buffer)
                })
            else:
                tx_params["gasPrice"] = int(await self.eth.gas_price * gas_price_buffer)
                
            return tx_params
        except Exception as error:
            await logger.logger_msg(
                msg=f"Gas estimation failed: {error}", type_msg="error", 
                class_name=self.__class__.__name__, method_name="_estimate_gas_params"
            )
            raise BlockchainError(f"Failed to estimate gas: {error}") from error

    async def build_transaction_params(
        self,
        contract_function: Any = None,
        to: str = None,
        value: int = 0,
        gas_buffer: float = 1.2,
        gas_price_buffer: float = 1.15,
        **kwargs
    ) -> dict:
        base_params = {
            "from": self.wallet_address,
            "nonce": await self.get_nonce(),
            "value": value,
            **kwargs
        }

        try:
            chain_id = await self.eth.chain_id
            base_params["chainId"] = chain_id
        except Exception as e:
            await logger.logger_msg(
                msg=f"Failed to get chain_id: {e}", type_msg="warning", 
                class_name=self.__class__.__name__, method_name="build_transaction_params"
            )

        if contract_function is None:
            if to is None:
                raise ValueError("'to' address required for ETH transfers")
            base_params.update({"to": to})
            return await self._estimate_gas_params(base_params, gas_buffer, gas_price_buffer)

        tx_params = await contract_function.build_transaction(base_params)
        return await self._estimate_gas_params(tx_params, gas_buffer, gas_price_buffer)

    async def _check_and_approve_token(
        self, 
        token_address: str, 
        spender_address: str, 
        amount: int
    ) -> tuple[bool, str]:
        try:
            token_contract = await self.get_contract(token_address)
            
            current_allowance = await token_contract.functions.allowance(
                self.wallet_address, 
                spender_address
            ).call()

            if current_allowance >= amount:
                return True, "Allowance already sufficient"

            approve_params = await self.build_transaction_params(
                contract_function=token_contract.functions.approve(spender_address, amount)
            )

            success, result = await self._process_transaction(approve_params)
            if not success:
                raise WalletError(f"Approval failed: {result}")

            return True, "Approval successful"

        except Exception as error:
            return False, f"Error during approval: {str(error)}"
        
    async def send_and_verify_transaction(self, transaction: Any) -> tuple[bool, str]:
        async with self._throttler:
            max_attempts = 3
            current_attempt = 0
            last_error = None
            
            while current_attempt < max_attempts:
                try:
                    signed = self.private_key.sign_transaction(transaction)
                    tx_hash = await self.eth.send_raw_transaction(signed.raw_transaction)
                    receipt = await self.eth.wait_for_transaction_receipt(tx_hash)
                    return receipt["status"] == 1, tx_hash.hex()
                    
                except Exception as error:
                    error_str = str(error)
                    last_error = error
                    current_attempt += 1
                    
                    if "NONCE_TOO_SMALL" in error_str or "nonce too low" in error_str.lower():
                        await logger.logger_msg(
                            msg=f"Nonce too small. Current: {transaction.get('nonce')}. Getting new nonce.", 
                            type_msg="warning", 
                            class_name=self.__class__.__name__, method_name="send_and_verify_transaction"
                        )
                        try:
                            new_nonce = await self.get_nonce()
                            transaction['nonce'] = new_nonce
                        except Exception as nonce_error:
                            await logger.logger_msg(
                                msg=f"Error during getting new nonce: {str(nonce_error)}", 
                                type_msg="error", 
                                class_name=self.__class__.__name__, method_name="send_and_verify_transaction"
                            )
                    elif "too many requests" in error_str.lower():
                        await logger.logger_msg(
                            msg=f"Received too many requests. Waiting before retrying...", 
                            type_msg="warning", 
                            class_name=self.__class__.__name__, method_name="send_and_verify_transaction"
                        )
                        await asyncio.sleep(2 * current_attempt)
                    else:
                        await logger.logger_msg(
                            msg=f"Error during sending transaction: {error_str}", 
                            type_msg="error", 
                            class_name=self.__class__.__name__, method_name="send_and_verify_transaction"
                        )
                        return False, error_str
                        
                    await asyncio.sleep(2)
            
            return False, f"Failed to execute transaction after {max_attempts} attempts. Last error: {str(last_error)}"
    
    async def _process_transaction(self, transaction: Any) -> tuple[bool, str]:
        try:
            status, result = await self.send_and_verify_transaction(transaction)
            return status, result
        except Exception as error:
            return False, str(error)