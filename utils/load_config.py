import os
import random
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path
from sys import exit

from better_proxy import Proxy
from ruamel.yaml import YAML

from config.settings import shuffle_flag
from core.exceptions.base import ConfigurationError
from logger import log
from models import Account, Config


yaml = YAML(typ='safe')


@dataclass
class FileData:
    path: Path
    required: bool = True
    allow_empty: bool = False


class ConfigLoader:
    REQUIRED_PARAMS: set[str] = frozenset({
        'referral_code',
        'threads'
    })

    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(base_path or Path(__file__).parent.parent)
        self.config_path = self.base_path / 'config'
        
        self.data_client_path = self.config_path / 'data' / 'client'
        self.settings_path = self.config_path / 'settings.yaml'
        
        self.file_paths = {
            'proxies': FileData(self.data_client_path / 'proxies.txt'),
            'private_keys': FileData(self.data_client_path / 'private_keys.txt'),
            'auth_tokens_twitter': FileData(
                self.data_client_path / 'auth_tokens_twitter.txt',
                required=False,
                allow_empty=True
            ),
            'auth_tokens_discord': FileData(
                self.data_client_path / 'auth_tokens_discord.txt',
                required=False,
                allow_empty=True
            ),
            'telegram_session': FileData(
                self.data_client_path / 'telegram_session',
                required=False,
                allow_empty=True
            )
        }

    def _read_file(self, file_data: FileData) -> list[str]:
        try:
            if not file_data.path.exists():
                if file_data.required:
                    raise ConfigurationError(
                        f'Required file not found: {file_data.path}'
                    )
                return []

            content = file_data.path.read_text(encoding='utf-8').strip()
            
            if not content and not file_data.allow_empty and file_data.required:
                raise ConfigurationError(
                    f'Required file is empty: {file_data.path}'
                )
                
            return [
                line.strip() 
                for line in content.splitlines() 
                if line.strip()
            ]
            
        except Exception as error:
            if file_data.required:
                raise ConfigurationError(
                    f'Error reading {file_data.path}: {str(error)}'
                )
            log.warning(
                f'Non-critical error reading {file_data.path}: {str(error)}'
            )
            return []

    def _load_yaml(self) -> dict:
        try:
            with open(self.settings_path, 'r', encoding='utf-8') as file:
                config = yaml.load(file)

            if not isinstance(config, dict):
                raise ConfigurationError('Configuration must be a dictionary')

            missing_fields = self.REQUIRED_PARAMS - set(config.keys())
            if missing_fields:
                raise ConfigurationError(
                    f'Missing required fields: {", ".join(missing_fields)}'
                )

            return config

        except Exception as error:
            raise ConfigurationError(
                f'Error loading configuration: {error}'
            ) from error

    def _parse_proxies(self) -> list[Proxy]:
        proxy_lines = self._read_file(self.file_paths['proxies'])
        
        def validate_proxy(proxy_str: str) -> Proxy | None:
            try: 
                return Proxy.from_str(proxy_str)
            except ValueError:
                return None
        
        max_workers = min(32, (os.cpu_count() or 1) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(validate_proxy, proxy_lines))
        
        return [proxy for proxy in results if proxy is not None]

    def _get_accounts(self) -> Generator[Account, None, None]:
        proxies = self._parse_proxies()
        proxy_cycle = cycle(proxies) if proxies else None

        with ThreadPoolExecutor(
            max_workers=min(len(self.file_paths), 3)
        ) as executor:
            private_keys, auth_tokens_twitter, auth_tokens_discord = executor.map(
                self._read_file,
                [
                    self.file_paths['private_keys'],
                    self.file_paths['auth_tokens_twitter'],
                    self.file_paths['auth_tokens_discord']
                ]
            )
        
        telegram_session_dir = self.file_paths['telegram_session'].path
        telegram_session_exists = telegram_session_dir.exists() and telegram_session_dir.is_dir()
                
        for index, private_key in enumerate(private_keys):
            try:            
                yield Account(
                    private_key=private_key,
                    proxy=next(proxy_cycle) if proxy_cycle else None,
                    auth_tokens_twitter=(
                        auth_tokens_twitter[index] 
                        if index < len(auth_tokens_twitter) 
                        else None
                    ),
                    auth_tokens_discord=(
                        auth_tokens_discord[index] 
                        if index < len(auth_tokens_discord) 
                        else None
                    ),
                    telegram_session=(
                        telegram_session_dir / private_key
                        if telegram_session_exists
                        else None
                    )
                )
            except Exception as error:
                log.error(
                    'Failed to create account for private_key %s: %s',
                    private_key,
                    str(error)
                )

    def load(self) -> Config:
        try:
            params = self._load_yaml()
            accounts = list(self._get_accounts())
            
            if not accounts:
                raise ConfigurationError('No valid accounts found')
                
            if shuffle_flag:
                random.shuffle(accounts)
            return Config(accounts=accounts, **params)

        except ConfigurationError as error:
            log.error('Configuration error: %s', error)
            exit(1)
        except Exception as error:
            log.error('Unexpected error during configuration loading: %s', error)
            exit(1)


def load_config() -> Config:
    return ConfigLoader().load()