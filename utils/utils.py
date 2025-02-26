import asyncio
import random
import sys
from functools import lru_cache

import urllib3
from eth_account import Account
from faker import Faker

from logger import log


def generate_username(locale='en_US'):
    """
    Generate a random username using Faker.
    
    Args:
        locale: Locale to use for username generation (default: 'en_US')
        
    Returns:
        A randomly generated username string
    """
    faker = Faker(locale)
    return faker.user_name()

async def random_sleep(account_name: str = "Referral", min_sec: int = 30, max_sec: int = 60) -> None:
    """
    Pause execution for a random amount of time within the specified range.
    
    Args:
        account_name: Name of account for logging purposes (default: "Referral")
        min_sec: Minimum sleep time in seconds (default: 30)
        max_sec: Maximum sleep time in seconds (default: 60)
    """
    delay = random.uniform(min_sec, max_sec)
    minutes = int(delay // 60)
    seconds = round(delay % 60, 1)

    if minutes > 0:
        log.info(f"Account {account_name} | Sleep {minutes}m {seconds}s")
    else:
        log.info(f"Account {account_name} | Sleep {seconds}s")

    await asyncio.sleep(delay)    
        
def setup():
    """
    Configure application setup.
    
    Disables urllib3 warnings and sets up logging to both console and file.
    """
    urllib3.disable_warnings()
    log.remove()
    log.add(
        sys.stdout,
        colorize=True,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )
    log.add("./logs/logs.log", rotation="1 day", retention="7 days")
    
@lru_cache(maxsize=1000)
def get_address(mnemonic: str) -> str:
    """
    Get Ethereum address from a mnemonic phrase or private key.
    
    Uses LRU cache to improve performance for repeated lookups.
    
    Args:
        mnemonic: Mnemonic phrase (12 or 24 words) or private key
        
    Returns:
        Ethereum address as a string
    """
    account = Account()
    keypair = account.from_mnemonic(mnemonic) if len(mnemonic.split()) in (12, 24) else account.from_key(mnemonic)
    return keypair.address