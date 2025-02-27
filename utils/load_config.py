import os
import random
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path
from sys import exit
from typing import Generator, List, Optional, Set, Tuple, Union

import yaml
from better_proxy import Proxy

from core.exceptions.base import ConfigurationError
from logger import log
from models import Account, Config


@dataclass
class FileData:
    """
    Stores information about configuration files and their requirements.
    
    Attributes:
        path: Path to the file
        required: If True, file must exist
        allow_empty: If True, file can be empty
    """
    path: Path
    required: bool = True
    allow_empty: bool = False

class ConfigLoader:
    """
    Loads and parses configuration from files to create a Config object.
    
    Handles reading various configuration files, validating their contents,
    and assembling the data into a cohesive configuration.
    """
    REQUIRED_PARAMS: Set[str] = frozenset({
        "cap_monster",
        "two_captcha",
        "capsolver",
        "telegram_api_hash",
        "telegram_api_id",
        "referral_code",
        "threads"
    })

    def __init__(self, base_path: Union[str, Path] = None):
        """
        Initialize the ConfigLoader with file paths.
        
        Args:
            base_path: Root directory for configuration files (defaults to current working directory)
        """
        self.base_path = Path(base_path or os.getcwd())
        self.config_path = self.base_path / "config"
        self.data_client_path = self.config_path / "data/client"
        self.data_referral_path = self.config_path / "data/referrals"
        self.settings_path = self.config_path / "settings.yaml"
        self.tg_sessions_path = self.config_path / "data/tg_sessions" 
        
        self.file_paths = {
            'proxies': FileData(self.data_client_path / "proxies.txt"),
            'private_keys': FileData(self.data_client_path / "private_keys.txt"),
            'auth_tokens_twitter': FileData(self.data_client_path / "auth_tokens_twitter.txt", required=False, allow_empty=True),
            'auth_tokens_discord': FileData(self.data_client_path / "auth_tokens_discord.txt", required=False, allow_empty=True),
            'referral_codes': FileData(self.data_referral_path / "referral_codes.txt", required=False, allow_empty=True)
        }

    def _read_file(self, file_data: FileData) -> List[str]:
        """
        Read and parse a configuration file.
        
        Args:
            file_data: FileData object containing path and requirements
            
        Returns:
            List of non-empty lines from the file
            
        Raises:
            ConfigurationError: If required file is missing or empty
        """
        try:
            if not file_data.path.exists():
                if file_data.required:
                    raise ConfigurationError(f"Required file not found: {file_data.path}")
                return []

            content = file_data.path.read_text(encoding='utf-8').strip()
            
            if not content and not file_data.allow_empty and file_data.required:
                raise ConfigurationError(f"Required file is empty: {file_data.path}")
                
            return [line.strip() for line in content.splitlines() if line.strip()]
            
        except Exception as e:
            if file_data.required:
                raise ConfigurationError(f"Error reading {file_data.path}: {str(e)}")
            log.warning(f"Non-critical error reading {file_data.path}: {str(e)}")
            return []

    def _load_yaml(self) -> dict:
        """
        Load and validate settings from YAML configuration file.
        
        Returns:
            Dictionary containing configuration settings
            
        Raises:
            ConfigurationError: If YAML is invalid or missing required fields
        """
        try:
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                raise ConfigurationError("Configuration must be a dictionary")

            missing_fields = self.REQUIRED_PARAMS - set(config.keys())
            if missing_fields:
                raise ConfigurationError(f"Missing required fields: {', '.join(missing_fields)}")

            return config

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML format: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration: {e}")

    def _parse_proxies(self) -> Optional[List[Proxy]]:
        """
        Parse proxy strings into Proxy objects.
        
        Returns:
            List of valid Proxy objects or None if no valid proxies
        """
        proxy_lines = self._read_file(self.file_paths['proxies'])
        if not proxy_lines:
            return None

        valid_proxies = []
        for proxy in proxy_lines:
            try:
                valid_proxies.append(Proxy.from_str(proxy))
            except Exception as e:
                log.warning(f"Invalid proxy format: {proxy}. Error: {e}")
                continue

        return valid_proxies if valid_proxies else None

    def _parse_referral_codes(self, lines: List[str]) -> List[Tuple[str, int]]:
        """
        Parse referral code strings into tuples of (code, count).
        
        Args:
            lines: List of strings in format "code:count"
            
        Returns:
            List of tuples containing (code, count)
        """
        codes = []
        for line in lines:
            try:
                code, count = line.split(':')
                codes.append((code.strip(), int(count.strip())))
            except (ValueError, AttributeError) as e:
                log.warning(f"Invalid referral code format: {line}. Error: {e}")
                continue
        return codes

    def _get_accounts(self) -> Generator[Account, None, None]:
        """
        Create Account objects from configuration files.
        
        Yields:
            Account objects with private keys, proxies and other credentials
        """
        proxies = self._parse_proxies()
        proxy_cycle = cycle(proxies) if proxies else None

        private_keys = self._read_file(self.file_paths['private_keys'])
        auth_tokens_twitter = self._read_file(self.file_paths['auth_tokens_twitter'])
        auth_tokens_discord = self._read_file(self.file_paths['auth_tokens_discord'])
        referral_codes = self._read_file(self.file_paths['referral_codes'])
        
        codes = self._parse_referral_codes(referral_codes) if referral_codes else None

        for i, private_key in enumerate(private_keys):
            try:
                session_file_path = self.tg_sessions_path / f"{private_key}.session"
                telegram_session = session_file_path if session_file_path.exists() else None
            
                yield Account(
                    private_key=private_key,
                    proxy=next(proxy_cycle) if proxy_cycle else None,
                    auth_tokens_twitter=auth_tokens_twitter[i] if i < len(auth_tokens_twitter) else None,
                    referral_codes=codes,
                    telegram_session=telegram_session,
                    auth_tokens_discord=auth_tokens_discord[i] if i < len(auth_tokens_discord) else None
                )
            except Exception as e:
                log.error(f"Failed to create account for private_key {private_key}: {str(e)}")

    def load(self) -> Optional[Config]:
        """
        Load and assemble complete configuration.
        
        Returns:
            Config object with all settings and accounts
            
        Raises:
            ConfigurationError: If configuration is invalid
            SystemExit: On critical configuration errors
        """
        try:
            params = self._load_yaml()
            accounts = list(self._get_accounts())
            
            if not accounts:
                raise ConfigurationError("No valid accounts found")
                
            random.shuffle(accounts)
            return Config(accounts=accounts, **params)

        except ConfigurationError as e:
            log.error(f"Configuration error: {e}")
            exit(1)
        except Exception as e:
            log.error(f"Unexpected error during configuration loading: {e}")
            exit(1)

def load_config() -> Config:
    """
    Convenience function to load configuration with default settings.
    
    Returns:
        Config object with all settings loaded
    """
    return ConfigLoader().load()