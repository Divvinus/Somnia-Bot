import asyncio
import os
import random
import sys
from typing import Callable

from console import Console
from core.bot import SomniaBot
from loader import config, progress, semaphore
from logger import log
from models import Account
from utils import get_address, setup


async def apply_delay(min_delay: float | int, max_delay: float | int) -> None:
    if 0 < min_delay <= max_delay:
        delay = random.uniform(min_delay, max_delay)
        log.info(f"🔄 Applying delay of {delay:.2f} seconds")
        await asyncio.sleep(delay)


async def process_execution(account: Account, process_func: Callable) -> bool:
    address = get_address(account.private_key)

    async with semaphore:
        try:
            await apply_delay(
                config.delay_before_start.min,
                config.delay_before_start.max
            )

            if status := await process_func(account):
                progress.increment()
                log.info(
                    f"🔄 Accounts processed: {progress.processed}/"
                    f"{progress.total}"
                )
                return isinstance(status, tuple) and status[0] if isinstance(status, tuple) else bool(status)

        except Exception as e:
            log.error(f"Account: {address} | Error: {str(e)}")
    
    return False


class ModuleProcessor:    
    def __init__(self) -> None:
        self.console = Console()
        self.module_functions: dict[str, Callable] = {
            name: getattr(SomniaBot, f"process_{name}")
            for name in Console.MODULES_DATA.values()
            if name != "exit"
        }
        
    async def process_regular_module(self) -> None:
        tasks = [
            process_execution(account, self.module_functions[config.module])
            for account in config.accounts
        ]
        results = await asyncio.gather(*tasks)
        
        success_count = sum(1 for result in results if result)
        failed_count = progress.total - success_count
        
        log.info(f"🌐 ==================================================")
        log.info(f"🌐 📊 TOTAL STATISTICS")
        log.info(f"🌐 ✅ Processed: {progress.processed}/{progress.total}")
        log.info(f"🌐 ✅ Success: {success_count}/{progress.total}")
        log.info(f"🌐 ❌ Failed: {failed_count}/{progress.total}")
        log.info(f"🌐 ==================================================")

    async def execute(self) -> None:
        self.console.build()
        
        if config.module == "exit":
            sys.exit(0)
            
        if not (process_func := self.module_functions.get(config.module)):
            address = get_address(config.accounts[0].private_key)
            log.warning(
                f"Account: {address} | "
                f"Module {config.module} not implemented!"
            )
            return

        try:
            await self.process_regular_module()                
        except Exception as e:
            address = get_address(config.accounts[0].private_key)
            log.error(f"Account: {address} | Error: {str(e)}")


async def main_loop() -> None:
    while True:
        await ModuleProcessor().execute()
        
        progress.processed = 0
        input("\nPress Enter to continue...")
        os.system("cls" if os.name == "nt" else "clear")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    setup()
    asyncio.run(main_loop())