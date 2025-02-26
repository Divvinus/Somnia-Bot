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
from models import Erc20Contract


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ETH_ADDRESS = "0x4200000000000000000000000000000000000006"

Account.enable_unaudited_hdwallet_features()


class Wallet(AsyncWeb3, Account):
    """
    Blockchain wallet with AsyncWeb3 functionality and ERC-20 interactions.
    
    Handles blockchain transactions, signatures, token interactions,
    and balance operations.
    """
    def __init__(self, private_key: str, rpc_url: Union[HttpUrl, str], proxy: Optional[Proxy] = None):
        """
        Initialize wallet with private key and connection settings.
        
        Args:
            private_key: Wallet private key or mnemonic phrase
            rpc_url: Blockchain RPC endpoint URL
            proxy: Optional proxy for network requests
        """
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
        
    @staticmethod
    def _initialize_keypair(private_key: str) -> Account:
        """
        Create account from private key or mnemonic.
        
        Args:
            private_key: Wallet private key or mnemonic phrase
            
        Returns:
            Account object
            
        Raises:
            WalletError: If private key is empty
        """
        if not private_key:
            raise WalletError("Empty private_key provided")
        return (Account.from_mnemonic(private_key) 
                if len(private_key.split()) in (12, 24) 
                else Account.from_key(private_key))

    @property
    def wallet_address(self) -> ChecksumAddress:
        """Get checksummed wallet address."""
        return self.keypair.address

    @staticmethod
    @lru_cache(maxsize=1000)
    def _get_checksum_address(address: str) -> ChecksumAddress:
        """
        Convert address to checksum format with caching.
        
        Args:
            address: Ethereum address
            
        Returns:
            Checksummed address
        """
        return AsyncWeb3.to_checksum_address(address)

    def get_contract(self, contract: Union[Erc20Contract, str, object]) -> AsyncContract:
        """
        Get contract instance with caching.
        
        Args:
            contract: Contract address, Erc20Contract, or contract-like object
            
        Returns:
            AsyncContract instance
            
        Raises:
            TypeError: If contract type is invalid
        """
        if isinstance(contract, str):
            address = self._get_checksum_address(contract)
            if address not in self._contracts_cache:
                self._contracts_cache[address] = self.eth.contract(
                    address=address,
                    abi=Erc20Contract().abi
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
            
        raise TypeError(
            "Invalid contract type: expected Erc20Contract, str, or contract-like object"
        )

    async def token_balance(self, token_address: str) -> int:
        """
        Get token balance for wallet address.
        
        Args:
            token_address: ERC-20 token address
            
        Returns:
            Token balance in smallest units
        """
        contract = self.get_contract(token_address)
        return await contract.functions.balanceOf(
            self._get_checksum_address(self.keypair.address)
        ).call()

    @staticmethod
    def _is_native_token(token_address: str) -> bool:
        """
        Check if address represents native token.
        
        Args:
            token_address: Token address to check
            
        Returns:
            True if native token, False otherwise
        """
        return token_address in (ZERO_ADDRESS, ETH_ADDRESS)

    async def convert_amount_to_decimals(self, amount: float, token_address: str) -> int:
        """
        Convert human-readable amount to token-specific decimals.
        
        Args:
            amount: Amount in human-readable form
            token_address: Token address
            
        Returns:
            Amount converted to smallest token units
        """
        token_address = self._get_checksum_address(token_address)
        
        if self._is_native_token(token_address):
            return self.to_wei(Decimal(str(amount)), 'ether')

        contract = self.get_contract(token_address)
        decimals = await contract.functions.decimals().call()
        return int(Decimal(str(amount)) * Decimal(str(10 ** decimals)))
    
    async def convert_amount_from_decimals(self, amount: int, token_address: str) -> float:
        """
        Convert token-specific decimals to human-readable amount.
        
        Args:
            amount: Amount in smallest token units
            token_address: Token address
            
        Returns:
            Human-readable token amount
        """
        token_address = self._get_checksum_address(token_address)
        
        if self._is_native_token(token_address):
            return float(self.from_wei(amount, 'ether'))

        contract = self.get_contract(token_address)
        decimals = await contract.functions.decimals().call()
        return float(Decimal(str(amount)) / Decimal(str(10 ** decimals)))

    async def transactions_count(self) -> Nonce:
        """Get number of transactions sent from wallet address."""
        return await self.eth.get_transaction_count(self.keypair.address)

    async def check_balance(self) -> None:
        """
        Verify wallet has non-zero ETH balance.
        
        Raises:
            InsufficientFundsError: If balance is zero
        """
        balance = await self.eth.get_balance(self.keypair.address)
        if balance <= 0:
            raise InsufficientFundsError("ETH balance is empty")

    async def human_balance(self) -> float:
        """Get ETH balance in human-readable form."""
        balance = await self.eth.get_balance(self.keypair.address)
        return float(self.from_wei(balance, "ether"))

    async def _build_base_transaction(self, contract_function: Any) -> TxParams:
        """
        Create transaction parameters for contract function.
        
        Args:
            contract_function: Contract function to call
            
        Returns:
            Transaction parameters
        """
        gas_estimate = await contract_function.estimate_gas({"from": self.keypair.address})
        return {
            "gasPrice": await self.eth.gas_price,
            "nonce": await self.transactions_count(),
            "gas": int(gas_estimate * 1.2),
        }

    async def check_trx_availability(self, transaction: TxParams) -> None:
        """
        Check if enough ETH balance for transaction.
        
        Args:
            transaction: Transaction parameters
            
        Raises:
            InsufficientFundsError: If balance too low
        """
        balance = await self.human_balance()
        required = float(self.from_wei(int(transaction.get('value', 0)), "ether"))

        if balance < required:
            raise InsufficientFundsError(
                f"ETH balance insufficient. Required: {required} ETH | Available: {balance} ETH"
            )

    async def _process_transaction(self, transaction: Any) -> Tuple[bool, str]:
        """
        Send transaction and handle errors.
        
        Args:
            transaction: Transaction to send
            
        Returns:
            Tuple of (success_status, result_or_error)
        """
        try:
            status, result = await self.send_and_verify_transaction(transaction)
            return status, result
        except Exception as error:
            return False, str(error)

    async def get_signature(self, text: str, private_key: Optional[str] = None) -> HexStr:
        """
        Sign message with wallet private key.
        
        Args:
            text: Message to sign
            private_key: Optional alternative private key
            
        Returns:
            Signature as hex string
        """
        encoded_message = encode_defunct(text=text)
        signing_keypair = (self.from_key(private_key) if private_key else self.keypair)
        signature = signing_keypair.sign_message(encoded_message)
        return HexStr(signature.signature.hex())

    async def send_and_verify_transaction(self, trx: Any) -> Tuple[bool, str]:
        """
        Sign, send and wait for transaction confirmation.
        
        Args:
            trx: Transaction to send
            
        Returns:
            Tuple of (success_status, transaction_hash)
        """
        signed = self.keypair.sign_transaction(trx)
        tx_hash = await self.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.eth.wait_for_transaction_receipt(tx_hash)
        return receipt["status"] == 1, tx_hash.hex()

    async def _check_and_approve_token(
        self, 
        token_address: str, 
        spender_address: str, 
        amount: int
    ) -> Tuple[bool, str]:
        """
        Check token allowance and approve if needed.
        
        Args:
            token_address: Token address
            spender_address: Address to approve spending
            amount: Amount to approve
            
        Returns:
            Tuple of (success_status, result_message)
        """
        try:
            token_contract = self.get_contract(token_address)
            
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

            success, result = await self._process_transaction(approve_tx)
            if not success:
                raise WalletError(f"Approval failed: {result}")

            return True, "Approval successful"

        except Exception as error:
            return False, f"Error during approval: {str(error)}"