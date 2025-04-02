import orjson
from pathlib import Path
from typing import Self

from better_proxy import Proxy
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)


class Account:
    __slots__ = (
        'private_key',
        'proxy',
        'auth_tokens_twitter',
        'auth_tokens_discord',
        'telegram_session',
    )

    def __init__(
        self,
        private_key: str,
        proxy: Proxy | None = None,
        auth_tokens_twitter: str | None = None,
        auth_tokens_discord: str | None = None,
        telegram_session: Path | None = None,
    ) -> None:
        self.private_key = private_key
        self.proxy = proxy
        self.auth_tokens_twitter = auth_tokens_twitter
        self.auth_tokens_discord = auth_tokens_discord
        self.telegram_session = telegram_session

    def __repr__(self) -> str:
        return f'Account({self.private_key!r})'


class DelayRange(BaseModel):
    min: int
    max: int

    @field_validator('max')
    @classmethod
    def validate_max(cls, value: int, info: ValidationInfo) -> int:
        if value < info.data['min']:
            raise ValueError('max must be greater than or equal to min')
        return value

    model_config = ConfigDict(frozen=True)


class PercentRange(BaseModel):
    min: int = Field(ge=0, le=100)
    max: int = Field(ge=0, le=100)

    @field_validator('max')
    @classmethod
    def validate_max(cls, value: int, info: ValidationInfo) -> int:
        if value < info.data['min']:
            raise ValueError('max must be greater than or equal to min')
        return value


class TokenConfig(BaseModel):
    percent_range: PercentRange
    contract_address: str | None = None


class AlwaysRunTasks(BaseModel):
    modules: list[str] = Field(default_factory=list)


class Config(BaseModel):
    accounts: list[Account] = Field(default_factory=list)
    threads: int
    delay_before_start: DelayRange
    delay_between_tasks: DelayRange
    referral_code: str
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    somnia_rpc: str = ""
    somnia_explorer: str = ""
    tokens: dict[str, TokenConfig] = Field(default_factory=dict)
    always_run_tasks: AlwaysRunTasks = Field(default_factory=AlwaysRunTasks)
    module: str = ""
    route_name: str = "default"
    available_modules: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='forbid',
    )

    @classmethod
    def load(cls, config_path: str | Path) -> Self:
        if isinstance(config_path, str):
            config_path = Path(config_path)
        
        try:
            raw_data = orjson.loads(config_path.read_text(encoding='utf-8'))
            return cls.model_validate(raw_data)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Config file not found: {config_path}") from e
        except orjson.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {config_path}") from e