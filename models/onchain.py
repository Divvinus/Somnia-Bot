import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from web3 import Web3
from typing import Any, ClassVar

import aiofiles
import orjson

class ContractError(Exception):
    """Base exception for contract-related errors"""

@dataclass
class BaseContract:
    """Base contract class with async ABI loading and caching"""
    address: str
    abi_file: str = "erc_20.json"
    
    _abi_cache: ClassVar[dict[str, tuple[list[dict[str, Any]], datetime]]] = {}
    _cache_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _abi_path: ClassVar[Path] = Path("./abi")
    CACHE_TTL: ClassVar[int] = 3600  # 1 hour in seconds

    async def get_abi(self) -> list[dict[str, Any]]:
        """Get ABI with caching and automatic refresh"""
        async with self._cache_lock:
            await self._validate_cache()
            return self._abi_cache[self.abi_file][0]

    async def _validate_cache(self) -> None:
        """Validate and refresh cache if needed"""
        current_time = datetime.now()
        
        if (cached := self._abi_cache.get(self.abi_file)):
            cached_time = cached[1]
            if (current_time - cached_time).seconds < self.CACHE_TTL:
                return

        await self._load_abi_file(current_time)

    async def _load_abi_file(self, timestamp: datetime) -> None:
        """Async load ABI file with error handling"""
        file_path = self._abi_path / self.abi_file
        
        try:
            async with aiofiles.open(file_path, "rb") as f:
                content = await f.read()
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
        """Clear cache with optional selective removal"""
        async with cls._cache_lock:
            if abi_file:
                cls._abi_cache.pop(abi_file, None)
            else:
                cls._abi_cache.clear()

@dataclass
class ERC20Contract(BaseContract):
    """ERC-20 contract with optimized ABI loading"""
    address: str = ""
    abi_file: str = "erc_20.json"
    
@dataclass
class PingPongRouterContract(ERC20Contract):
    address: str = Web3.to_checksum_address("0x6aac14f090a35eea150705f72d90e4cdc4a49b2c")
    abi_file: str = "ping_pong_router.json"

@dataclass
class PingTokensContract(ERC20Contract):
    address: str = Web3.to_checksum_address("0x33e7fab0a8a5da1a923180989bd617c9c2d1c493")
    abi_file: str = "erc_721.json"

@dataclass
class PongTokensContract(ERC20Contract):
    address: str = Web3.to_checksum_address("0x9beaA0016c22B646Ac311Ab171270B0ECf23098F")
    abi_file: str = "erc_721.json"
    
@dataclass
class UsdtTokensContract(ERC20Contract):
    address: str = Web3.to_checksum_address("0x65296738d4e5edb1515e40287b6fdf8320e6ee04")
    abi_file: str = "erc_721.json"
    
@dataclass
class NFTContract(BaseContract):
    """Base NFT contract (ERC-721)"""
    abi_file: str = "erc_721.json"
