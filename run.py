import asyncio
import os
import sys

from loader import config, progress, semaphore
from logger import log
from db import Database
from utils import setup
from module_processor import ModuleProcessor

async def main_loop() -> None:
    log.info("✅ Program start")
    
    try:
        await Database.init_db()
        await Database.sync_accounts(config.accounts)
        log.info("✅ Database initialized")
    except Exception as e:
        log.error(f"❌ Database init error: {str(e)}")
        return

    while True:
        progress.reset()
        try:
            exit_flag = await ModuleProcessor().execute()
            if exit_flag:
                break
        except KeyboardInterrupt:
            log.warning("🚨 Manual interruption!")
            break

        input("\nPress Enter to return to menu...")
        os.system("cls" if os.name == "nt" else "clear")

    await Database.close_pool()
    log.info("👋 Goodbye! Terminal is ready for commands.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    setup()
    asyncio.run(main_loop())