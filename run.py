import asyncio
import os
import sys

from bot_loader import progress
from src.db import Database
from module_processor import ModuleProcessor
from src.logger import AsyncLogger


async def main_loop() -> None:
    logger = AsyncLogger()
    await logger.logger_msg("✅ Program start", type_msg="info")
    
    try:
        await logger.logger_msg("✅ Database initialized", type_msg="success")
    except Exception as e:
        await logger.logger_msg(f"❌ Database init error: {str(e)}", type_msg="error", method_name="main_loop")
        return

    while True:
        progress.reset()
        try:
            exit_flag = await ModuleProcessor().execute()
            if exit_flag:
                break
        except KeyboardInterrupt:
            await logger.logger_msg("🚨 Manual interruption!", type_msg="warning", method_name="main_loop")
            break
        except asyncio.CancelledError:
            break

        input("\nPress Enter to return to menu...")
        os.system("cls" if os.name == "nt" else "clear")

    await Database.close_pool()
    await logger.logger_msg("👋 Goodbye! Terminal is ready for commands.", type_msg="info")

async def shutdown(loop):
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    for task in tasks:
        task.cancel()
    
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n\n🚨 Program stopped. Terminal is ready for commands.")
    finally:
        if sys.platform != "win32":
            os.system("stty sane")
        print("👋 Program finished. Terminal is ready for commands.")