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

async def random_sleep(account_name: str = "Referral", min_sec: int = 30, max_sec: int = 60) -> None:
    delay = random.uniform(min_sec, max_sec)
    minutes = int(delay // 60)
    seconds = round(delay % 60, 1)

    if minutes > 0:
        log.info(f"Account {account_name} | Sleep {minutes}m {seconds}s")
    else:
        log.info(f"Account {account_name} | Sleep {seconds}s")

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
    
def get_address(mnemonic: str) -> str:
    account = Account()
    keypair = account.from_mnemonic(mnemonic) if len(mnemonic.split()) in (12, 24) else account.from_key(mnemonic)
    return keypair.address