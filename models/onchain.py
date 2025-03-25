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
