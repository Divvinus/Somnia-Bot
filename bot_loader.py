import asyncio

from src.utils import load_config, AccountProgress

config = load_config()
semaphore = asyncio.Semaphore(config.threads)
progress = AccountProgress(len(config.accounts))