import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from web3 import AsyncWeb3
from typing import Any, ClassVar

import aiofiles
import orjson

class ContractError(Exception):
    """Base exception for contract-related errors"""
    pass

@dataclass(slots=True)
class BaseContract:
    address: str
    abi_file: str = "erc_20.json"
    
    _abi_cache: ClassVar[dict[str, tuple[list[dict[str, Any]], float]]] = {}
    _cache_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _abi_path: ClassVar[Path] = Path("./abi")
    CACHE_TTL: ClassVar[int] = 3600

    async def get_abi(self) -> list[dict[str, Any]]:
        async with self._cache_lock:
            await self._validate_cache()
            return self._abi_cache[self.abi_file][0]
        
    async def _validate_cache(self) -> None:
        current_time = time.time()
        if (cached := self._abi_cache.get(self.abi_file)) and (current_time - cached[1]) < self.CACHE_TTL:
            return
        await self._load_abi_file(current_time)

    async def _load_abi_file(self, timestamp: float) -> None:
        file_path = self._abi_path / self.abi_file
        try:
            async with aiofiles.open(file_path, "rb") as f:
                content = await asyncio.to_thread(file_path.read_bytes)
                abi_data = orjson.loads(content)
                if not isinstance(abi_data, list):
                    raise ContractError(f"Invalid ABI structure in {file_path}")
                self._abi_cache[self.abi_file] = (abi_data, timestamp)
        except FileNotFoundError as e:
            raise ContractError(f"ABI file not found: {file_path}") from e
        except orjson.JSONDecodeError as e:
            raise ContractError(f"Invalid JSON in ABI file: {file_path}") from e

    @classmethod
    async def clear_cache(cls, abi_file: str | None = None) -> None:
        async with cls._cache_lock:
            if abi_file:
                cls._abi_cache.pop(abi_file, None)
            else:
                cls._abi_cache.clear()

@dataclass(slots=True)
class ERC20Contract(BaseContract):
    address: str = ""
    abi_file: str = "erc_20.json"
    _bytecode: str | None = None
    
    _bytecode_path: ClassVar[Path] = Path("./config/data")
    _bytecode_file: ClassVar[str] = "bytecode_erc_20.txt"
    _bytecode_cache: ClassVar[dict[str, str]] = {}
    _bytecode_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    
    @property
    def bytecode(self) -> str | None:
        return self._bytecode
        
    @bytecode.setter
    def bytecode(self, value: str | None) -> None:
        self._bytecode = value
    
    async def get_bytecode(self) -> str:
        if self._bytecode is not None:
            return self._bytecode
        cache_key = str(self._bytecode_path / self._bytecode_file)
        async with self._bytecode_lock:
            if cache_key in self._bytecode_cache:
                self._bytecode = self._bytecode_cache[cache_key]
                return self._bytecode
            file_path = self._bytecode_path / self._bytecode_file
            try:
                async with aiofiles.open(file_path, "r") as f:
                    bytecode = await f.read()
                    bytecode = bytecode.strip()
                    self._bytecode_cache[cache_key] = bytecode
                    self._bytecode = bytecode
                    return bytecode
            except FileNotFoundError as e:
                raise ContractError(f"Bytecode not found: {file_path}") from e
            except Exception as e:
                raise ContractError(f"Error reading bytecode: {e}") from e
    
    @classmethod
    async def clear_bytecode_cache(cls) -> None:
        async with cls._bytecode_lock:
            cls._bytecode_cache.clear()

@dataclass(slots=True)
class PingPongRouterContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x6aac14f090a35eea150705f72d90e4cdc4a49b2c")
    abi_file: str = "ping_pong_router.json"

@dataclass(slots=True)
class PingTokensContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x33e7fab0a8a5da1a923180989bd617c9c2d1c493")
    abi_file: str = "mint_tokens.json"

@dataclass(slots=True)
class PongTokensContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x9beaA0016c22B646Ac311Ab171270B0ECf23098F")
    abi_file: str = "mint_tokens.json"
    
@dataclass(slots=True)
class UsdtTokensContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x65296738d4e5edb1515e40287b6fdf8320e6ee04")
    abi_file: str = "mint_tokens.json"
    
@dataclass(slots=True)
class OnchainGMContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0xA0692f67ffcEd633f9c5CfAefd83FC4F21973D01")

@dataclass(slots=True)
class YappersNFTContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0xF6e220FA8d944B512e9ef2b1d732C3a12F156B3c")
    abi_file: str = "claim_nft.json"
    
@dataclass(slots=True)
class ShannonNFTContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x715A73f6C71aB9cB32c7Cc1Aa95967a1b5da468D")
    abi_file: str = "claim_nft.json"
    
@dataclass(slots=True)
class NerzoNFTContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x939cCD6129561EFcBE8402a7159C1c09b9D34231")
    abi_file: str = "claim_nft.json"
    
@dataclass(slots=True)
class SomniNFTContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0xfA139F427a667b56d93946c2FD2c03601BaD033A")
    abi_file: str = "claim_nft.json"
    
@dataclass(slots=True)
class BeaconNFTContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x055ed4Be04Fad6BD5EeDc0A799E55b93210BCcf9")
    abi_file: str = "claim_nft.json"
    
@dataclass(slots=True)
class CommunityNFTContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0xFC79f0EaC5bEcf21fDcf037bAdb977b2b43DE497")
    abi_file: str = "community_nft.json"

@dataclass(slots=True)
class ZNSContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0xf180136DdC9e4F8c9b5A9FE59e2b1f07265C5D4D")
    abi_file: str = "zns_domen.json"
    
@dataclass(slots=True)
class SomniaDomainsContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0xDB4e0A5E7b0d03aA41cBB7940c5e9Bab06cc7157")
    abi_file: str = "somnia_domain.json"
    
@dataclass(slots=True)
class QuickSwapRouterContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0xE94de02e52Eaf9F0f6Bf7f16E4927FcBc2c09bC7")
    abi_file: str = "quick_swap_router.json"
    
@dataclass(slots=True)
class QuickSwapFactoryContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x0BFaCE9a5c9F884a4f09fadB83b69e81EA41424B")
    abi_file: str = "quick_swap_factory.json"
    
@dataclass(slots=True)
class QuickSwapAddressPairContract(BaseContract):
    address: str 
    abi_file: str = "quick_swap_address_pair.json"
    
@dataclass(slots=True)
class QuickPoolContract(BaseContract):
    address: str = AsyncWeb3.to_checksum_address("0x37A4950b4ea0C46596404895c5027B088B0e70e7")
    abi_file: str = "quick_pool.json"