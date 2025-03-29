import asyncio
import os
import random
import sys
from typing import Callable

from console import Console
from core.bot import SomniaBot
from task_management.database import Database
from task_management.route_manager import RouteManager
from loader import config, progress, semaphore
from logger import log
from models import Account
from utils import get_address, setup

async def apply_delay(min_delay: float | int, max_delay: float | int) -> None:
    if 0 < min_delay <= max_delay:
        delay = random.uniform(min_delay, max_delay)
        log.info(f"🔄 Applying delay of {delay:.2f} seconds")
        await asyncio.sleep(delay)

async def process_execution(account: Account, process_func: Callable) -> tuple[bool, str]:
    address = get_address(account.private_key)
    async with semaphore:
        try:
            await apply_delay(config.delay_before_start.min, config.delay_before_start.max)
            result = await process_func(account)
            if isinstance(result, tuple) and len(result) == 2:
                success, message = result
            else:
                success = bool(result)
                message = "Completed successfully" if success else "Execution failed"
            progress.increment()
            log.info(f"Processed accounts: {progress.processed}/{progress.total}")
            return success, message
        except Exception as e:
            log.error(f"Account: {address} | Error: {str(e)}")
            return False, str(e)

class ModuleProcessor:
    def __init__(self) -> None:
        self.console = Console()
        self.module_functions: dict[str, Callable] = {
            name: getattr(SomniaBot, f"process_{name}")
            for name in Console.MODULES_DATA.values()
            if name not in ["exit", "generate_routes", "view_routes", "execute_route", "manage_tasks"]
        }

    async def init_database(self):
        try:
            await Database.init_db()
            await Database.sync_accounts(config.accounts)
        except Exception as e:
            log.error(f"Database init error: {str(e)}")

    async def process_route_execution(self) -> None:
        for account in config.accounts:
            address = get_address(account.private_key)
            log.info(f"Processing route for account: {address}")
            
            route_id = address
            
            account_id = await Database.get_account_id(account.private_key)
            try:
                async with Database.transaction() as conn:
                    cursor = await conn.execute(
                        "SELECT 1 FROM routes WHERE id = ?", 
                        (route_id,)
                    )
                    route_exists = await cursor.fetchone() is not None
                
                if not route_exists:
                    log.error(f"Route not found for account {address}")
                    log.info(f"Attempting to create route for account: {address}")
                    created_route_id = await RouteManager.create_route_for_account(account)
                    if not created_route_id:
                        log.error(f"Failed to create route for account: {address}")
                        continue
            except Exception as e:
                log.error(f"Error checking route existence: {str(e)}")
                continue

            while True:
                tasks_to_run = await Database.get_tasks_to_run(route_id, config.always_run_tasks.modules)
                if not tasks_to_run:
                    log.info(f"All available tasks completed for account: {address}")
                    break
                
                for task in tasks_to_run:
                    module_name = task["module_name"]
                    if module_name not in self.module_functions:
                        log.warning(f"Module '{module_name}' not implemented!")
                        continue
                    
                    if task["last_executed"]:
                        if module_name == "faucet":
                            pass
                        else:
                            log.info(f"Executing task: {module_name} for account: {address}")
                    else:
                        log.info(f"First execution of task: {module_name} for account: {address}")
                    
                    success, message = await process_execution(account, self.module_functions[module_name])

                    await Database.update_task_status(
                        task["id"],
                        "success" if success else "failed",
                        result=message if success else None,
                        error=message if not success else None
                    )

                    if module_name == "faucet" and not success:
                        log.error(f"Route interrupted for {address} due to faucet failure")
                        break

                    log.info(f"Task '{module_name}' for {address} | Result: {'✅' if success else '❌'} | Message: {message}")
                    
                    await apply_delay(
                        config.delay_between_tasks.min,
                        config.delay_between_tasks.max
                    )

                await Database.update_route_status(route_id)

            log.info(f"Route execution fully completed for account: {address}")

    async def process_view_routes(self) -> None:
        try:
            routes_stats = await Database.get_route_stats()
            if not routes_stats:
                log.info("No route statistics found")
                return

            log.info("=== Route Statistics ===")
            for route in routes_stats:
                status = (
                    f"ID: {route.id} | "
                    f"Route: {route.route_name} | "
                    f"Account: {get_address(route.private_key)} | "
                    f"Status: {route.status} | "
                    f"Tasks: ✅ {route.success_tasks} ❌ {route.failed_tasks} ⏳ {route.pending_tasks}"
                )
                log.info(status)
            log.info("=======================\n")

        except Exception as e:
            log.error(f"Failed to get route stats: {str(e)}")

    async def execute(self) -> bool:
        await self.init_database()
        self.console.build()

        if config.module == "exit":
            log.info("🔴 Exiting program...")
            return True

        if config.module in self.module_functions:
            tasks = []
            for account in config.accounts:
                task = process_execution(account, self.module_functions[config.module])
                tasks.append(task)
            await asyncio.gather(*tasks)
            return False

        if config.module == "generate_routes":
            await RouteManager.create_routes_for_all_accounts(config.accounts)
            return False

        if config.module == "view_routes":
            await self.process_view_routes()
            return False

        if config.module == "execute_route":
            await self.process_route_execution()
            return False

        log.error(f"Module {config.module} not implemented!")
        return False

async def main_loop() -> None:
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

    await Database.close()
    log.info("👋 Goodbye! Terminal is ready for commands.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    setup()
    asyncio.run(main_loop())