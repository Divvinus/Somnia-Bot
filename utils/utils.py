import asyncio
import random
import sys

import urllib3
from eth_account import Account
from faker import Faker

from logger import log


def generate_username(locale='en_US'):
    faker = Faker(locale)
    return faker.user_name()

async def random_sleep(account_name: str = "None", min_sec: int = 30, max_sec: int = 60) -> None:
    delay = random.uniform(min_sec, max_sec)
    
    minutes, seconds = divmod(delay, 60)
    template = (
        f"Account {account_name} | Sleep "
        f"{int(minutes)}m {seconds:.1f}s" if minutes > 0 else 
        f"Account {account_name} | Sleep {seconds:.1f}s"
    )
    log.info(template)
    
    await asyncio.sleep(delay)
        
def setup():
    urllib3.disable_warnings()
    log.remove()
    log.add(
        sys.stdout,
        colorize=True,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )
    log.add("./logs/logs.log", rotation="1 day", retention="7 days")

_ACCOUNT = Account()

def get_address(private_key: str) -> str:    
    return _ACCOUNT.from_key(private_key).address