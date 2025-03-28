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

async def process_execution(account: Account, process_func: Callable) -> bool:
    address = get_address(account.private_key)
    async with semaphore:
        try:
            await apply_delay(config.delay_before_start.min, config.delay_before_start.max)
            status = await process_func(account)
            success = bool(status)
            progress.increment()
            log.info(f"Processed accounts: {progress.processed}/{progress.total}")
            return success
        except Exception as e:
            log.error(f"Account: {address} | Error: {str(e)}")
            return False

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
            
    async def execute_always_run_modules(self):
        if not config.always_run_tasks.modules:
            return
            
        log.info("Running always-run tasks...")
        for account in config.accounts:
            for module in config.always_run_tasks.modules:
                if module not in self.module_functions:
                    log.warning(f"Module '{module}' not implemented!")
                    continue
                
                success = await process_execution(account, self.module_functions[module])
                log.info(
                    f"Always-run: {module} | "
                    f"Account: {get_address(account.private_key)} | "
                    f"Result: {'✅' if success else '❌'}"
                )

    async def process_route_execution(self) -> None:
        route_name = getattr(config, 'route_name', "default")
        
        total_tasks = 0
        completed_tasks = 0
        
        for account in config.accounts:
            address = get_address(account.private_key)
            log.info(f"Processing route for account: {address}")
            
            tasks_to_run = await RouteManager.get_tasks_to_run(account, route_name)
            if not tasks_to_run:
                log.info(f"No tasks to run for account: {address}")
                continue
            
            total_tasks += len(tasks_to_run)
            
            for task in tasks_to_run:
                module_name = task['module_name']
                if module_name not in self.module_functions:
                    log.warning(f"Module '{module_name}' not implemented!")
                    continue
                
                try:
                    log.info(f"Executing task: {module_name} for account: {address}")
                    success = await process_execution(account, self.module_functions[module_name])
                    
                    if success:
                        await Database.update_task_status(task['id'], 'success', result="Completed successfully")
                        completed_tasks += 1
                        log.success(f"Task '{module_name}' completed successfully for account: {address}")
                    else:
                        await Database.update_task_status(task['id'], 'failed', error="Execution failed")
                        log.error(f"Task '{module_name}' failed for account: {address}")
                    
                    route_id = await Database.get_route_id(
                        await Database.get_account_id(account.private_key), 
                        route_name
                    )
                    await Database.update_route_status(route_id)
                    
                except Exception as e:
                    log.error(f"Task '{module_name}' execution error for account {address}: {str(e)}")
                    await Database.update_task_status(task['id'], 'failed', error=str(e))
        
        log.info(f"Route execution completed: {completed_tasks}/{total_tasks} tasks successful")
        await self.execute_always_run_modules()
        
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
                task = process_execution(
                    account, 
                    self.module_functions[config.module]
                )
                tasks.append(task)
            
            await asyncio.gather(*tasks)
            return
        
        if config.module == "generate_routes":
            await RouteManager.create_routes_for_all_accounts(config.accounts)
            return
            
        if config.module == "view_routes":
            await self.process_view_routes()
            return
            
        if config.module == "execute_route":
            await self.process_route_execution()
            return

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
            # Запускаем обработчик
            exit_flag = await ModuleProcessor().execute()
            
            # Если получен флаг выхода
            if exit_flag:
                break
                
        except KeyboardInterrupt:
            log.warning("🚨 Manual interruption!")
            break
            
        input("\nPress Enter to return to menu...")
        os.system("cls" if os.name == "nt" else "clear")
    
    # Корректное завершение
    await Database.close()
    log.info("👋 Goodbye! Terminal is ready for commands.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    setup()
    asyncio.run(main_loop())