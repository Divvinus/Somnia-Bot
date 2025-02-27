from dataclasses import dataclass, field
from typing import Optional, Union, List, Tuple
from pathlib import Path

from better_proxy import Proxy
from pydantic import BaseModel, ConfigDict, Field, validator


@dataclass
class Account:
    """
    Represents a user account with authentication credentials and proxy settings.
    
    Attributes:
        private_key: Account's private key for authentication
        proxy: Optional proxy for network requests
        auth_tokens_twitter: Optional authentication tokens for Twitter
        auth_tokens_discord: Optional authentication tokens for Discord
        referral_codes: List of referral codes with their associated values
        telegram_session: Optional path to the Telegram session file (.session)
    """
    private_key: str
    proxy: Optional[Proxy] = None
    auth_tokens_twitter: Optional[str] = None
    auth_tokens_discord: Optional[str] = None
    telegram_session: Optional[Union[str, Path]] = None
    referral_codes: List[Tuple[str, int]] = field(default_factory=list)


class DelayRange(BaseModel):
    """
    Defines a range for time delays.
    
    Attributes:
        min: Minimum delay time in seconds
        max: Maximum delay time in seconds (must be >= min)
    """
    min: int
    max: int

    @validator('max')
    def max_greater_than_or_equal_to_min(cls, v, values):
        """Validates that max value is greater than or equal to min value."""
        if 'min' in values and v < values['min']:
            raise ValueError('max must be greater than or equal to min')
        return v


class Token(BaseModel):
    """
    Represents a blockchain token.
    
    Attributes:
        name: Token name
        address: Token contract address
    """
    name: str
    address: str


class ActivePair(BaseModel):
    """
    Represents a trading pair.
    
    Attributes:
        input: Input token identifier
        output: Output token identifier
    """
    input: str
    output: str


class Config(BaseModel):
    """
    Application configuration settings.
    
    Attributes:
        accounts: List of account credentials
        cap_monster: CapMonster API key
        two_captcha: 2Captcha API key
        capsolver: Capsolver API key
        telegram_api_hash: Telegram API hash
        telegram_api_id: Telegram API ID
        somnia_rpc: Somnia RPC endpoint URL
        somnia_explorer: Somnia explorer URL
        referral_code: Global referral code
        tokens: List of token definitions
        delay_before_start: Range for initial delay
        threads: Number of concurrent threads
        module: Module name to execute
    """
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra="forbid"
    )

    accounts: list[Account] = Field(default_factory=list)
    cap_monster: str = ""
    two_captcha: str = ""
    capsolver: str = ""
    somnia_rpc: str = ""
    somnia_explorer: str = ""
    telegram_api_hash: str = ""
    telegram_api_id: str = ""
    referral_code: str = ""
    tokens: list[Token] = Field(default_factory=list)
    delay_before_start: DelayRange
    threads: int
    module: str = ""