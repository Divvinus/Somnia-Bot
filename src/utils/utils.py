import asyncio
import random

from eth_account import Account
from faker import Faker

from src.logger import AsyncLogger


def generate_username(locale='en_US'):
    faker = Faker(locale)
    return faker.user_name()

async def random_sleep(
    address: str | None = None, 
    min_sec: int = 30, 
    max_sec: int = 60
) -> None:
    logger = AsyncLogger()
    delay = random.uniform(min_sec, max_sec)
    
    minutes, seconds = divmod(delay, 60)
    template = (
        f"Sleep "
        f"{int(minutes)} minutes {seconds:.1f} seconds" if minutes > 0 else 
        f"Sleep {seconds:.1f} seconds"
    )
    await logger.logger_msg(template, type_msg="info", address=address)
    
    chunk_size = 0.1
    chunks = int(delay / chunk_size)
    remainder = delay - (chunks * chunk_size)
    
    try:
        for _ in range(chunks):
            await asyncio.sleep(chunk_size)
            
        if remainder > 0:
            await asyncio.sleep(remainder)
            
    except asyncio.CancelledError:
        await logger.logger_msg(
            f"Sleep interrupted", type_msg="warning", address=address
        )
        raise

_ACCOUNT = Account()

def get_address(private_key: str) -> str:    
    return _ACCOUNT.from_key(private_key).address