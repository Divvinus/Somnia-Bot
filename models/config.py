import json
from pathlib import Path
from typing import Self

from better_proxy import Proxy
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator
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
        telegram_session: Path | None = None
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

    model_config = ConfigDict(
        frozen=True,
        validate_assignment=False,
    )


class Config(BaseModel):
    accounts: list[Account] = Field(default_factory=list)
    somnia_rpc: str = ''
    somnia_explorer: str = ''
    referral_code: str = ''
    telegram_api_id: str = ''
    telegram_api_hash: str = ''
    delay_before_start: DelayRange
    threads: int
    module: str = ''

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=False,
        extra='forbid',
    )

    @classmethod
    def load(cls, config_path: str | Path) -> Self:
        if isinstance(config_path, str):
            config_path = Path(config_path)

        raw_data = json.loads(config_path.read_text(encoding='utf-8'))
        return cls.model_validate(raw_data)