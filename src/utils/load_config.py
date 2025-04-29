import random
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import openpyxl
from better_proxy import Proxy
from ruamel.yaml import YAML

from config.settings import shuffle_flag
from src.exceptions.custom_exceptions import ConfigurationError
from src.models import Account, Config


yaml = YAML(typ='safe')


@dataclass
class FileData:
    path: Path
    required: bool = True
    allow_empty: bool = False


class ConfigLoader:
    REQUIRED_PARAMS: set[str] = frozenset({
        'threads',
        'delay_before_start',
        'delay_between_tasks'
    })

    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(base_path or Path(__file__).parent.parent.parent)
        self.config_path = self.base_path / 'config'
        self.data_client_path = self.config_path / 'data' / 'client'
        self.settings_path = self.config_path / 'settings.yaml'
        self.file_paths = {
            'accounts': FileData(self.data_client_path / 'accounts.xlsx'),
            'telegram_session': FileData(
                self.data_client_path / 'telegram_session',
                required=False,
                allow_empty=True
            )
        }

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
            
            if 'delay_between_tasks' not in config:
                config['delay_between_tasks'] = {'min': 30, 'max': 120}
            
            if 'always_run_tasks' not in config:
                config['always_run_tasks'] = {'by_id': [], 'by_module': []}
            
            return config
        
        except Exception as error:
            raise ConfigurationError(
                f'Error loading configuration: {error}'
            ) from error

    def _get_accounts(self) -> Generator[Account, None, None]:
        accounts_path = self.file_paths['accounts'].path
        
        if not accounts_path.exists():
            raise ConfigurationError(f'Accounts file not found: {accounts_path}')
        
        wb = openpyxl.load_workbook(accounts_path, read_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        
        try:
            header = next(rows)
        except StopIteration:
            raise ConfigurationError('Accounts file is empty')
        
        col_map = {
            cell.strip(): idx 
            for idx, cell in enumerate(header) 
            if cell
        }
        
        required_cols = {'Private Key'}
        for col in required_cols:
            if col not in col_map:
                raise ConfigurationError(f'Missing required column: {col}')
        
        telegram_session_dir = self.file_paths['telegram_session'].path
        telegram_session_exists = (
            telegram_session_dir.exists() 
            and telegram_session_dir.is_dir()
        )
        
        for row in rows:
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue
            
            private_key = row[col_map['Private Key']]
            if not private_key or str(private_key).strip() == '':
                continue
            
            private_key = str(private_key).strip()
            proxy_str = (
                row[col_map.get('Proxy')] 
                if 'Proxy' in col_map 
                else None
            )
            twitter_token = (
                row[col_map.get('Twitter Token')] 
                if 'Twitter Token' in col_map 
                else None
            )
            reconnect_twitter = (
                row[col_map.get('Reconnect Twitter')] 
                if 'Reconnect Twitter' in col_map 
                else None
            )
            discord_token = (
                row[col_map.get('Discord Token')] 
                if 'Discord Token' in col_map 
                else None
            )
            reconnect_discord = (
                row[col_map.get('Reconnect Discord')] 
                if 'Reconnect Discord' in col_map 
                else None
            )
            
            proxy = None
            if proxy_str:
                proxy = Proxy.from_str(str(proxy_str).strip())
                
            session_path = (
                telegram_session_dir / f"{private_key}.session" 
                if telegram_session_exists 
                else None
            )
            if session_path and not session_path.exists():
                session_path = None
            
            yield Account(
                private_key=private_key,
                proxy=proxy,
                auth_tokens_twitter=(
                    str(twitter_token).strip() 
                    if twitter_token 
                    else None
                ),
                reconnect_twitter=reconnect_twitter,
                auth_tokens_discord=(
                    str(discord_token).strip() 
                    if discord_token 
                    else None
                ),
                reconnect_discord=reconnect_discord,
                telegram_session=session_path
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
            raise ConfigurationError(
                f'Configuration error: {error}'
            ) from error
        
        except Exception as error:
            raise ConfigurationError(
                f'Unexpected error during configuration loading: {error}'
            ) from error
            exit(1)


def load_config() -> Config:
    return ConfigLoader().load()