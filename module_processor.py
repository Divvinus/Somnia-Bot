import asyncio
from typing import Callable, AsyncGenerator
from datetime import datetime

from console import Console
from core.bot import SomniaBot
from db import Database
from db.route_manager import RouteManager
from loader import config, progress, semaphore
from logger import log
from models import Account
from utils import get_address, random_sleep


async def process_execution(account: Account, process_func: Callable) -> tuple[bool, str]:
    address = get_address(account.private_key)
    async with semaphore:
        try:
            if config.delay_before_start.min > 0:
                await random_sleep(
                    address, config.delay_before_start.min, config.delay_before_start.max
                )
            result = await process_func(account)
            success = (
                result[0]
                if isinstance(result, tuple) and len(result) == 2
                else bool(result)
            )
            message = (
                result[1]
                if isinstance(result, tuple) and len(result) == 2
                else (
                    "Completed successfully" if success else "Execution failed"
                )
            )
            return success, message
        except Exception as e:
            log.error(f"Account: {address} | Error: {str(e)}")
            return False, str(e)


class ModuleProcessor:
    __slots__ = ("console", "module_functions")
    EXCLUDED_MODULES = {
        "exit",
        "generate_routes",
        "view_routes",
        "view_statistics",
        "execute_route",
        "manage_tasks",
    }

    def __init__(self) -> None:
        self.console = Console()
        
        self.module_functions: dict[str, Callable] = {}
        
        for attr_name in dir(SomniaBot):
            if attr_name.startswith('process_'):
                module_name = attr_name[8:]
                if module_name not in self.EXCLUDED_MODULES:
                    self.module_functions[module_name] = getattr(SomniaBot, attr_name)

    async def init_database(self) -> None:
        try:
            await Database.init_db()
            await Database.sync_accounts(config.accounts)
            for account in config.accounts:
                await Database.update_account_statistics(
                    get_address(account.private_key)
                )
        except Exception as e:
            log.error(f"Database init error: {str(e)}")

    async def process_route_execution(self) -> None:
        async def process_account(account: Account) -> None:
            address = get_address(account.private_key)
            log.info(f"Processing route for account: {address}")
            route_id = address
            try:
                async with Database.transaction() as conn:
                    cursor = await conn.execute(
                        "SELECT 1 FROM routes WHERE name = ?", (route_id,)
                    )
                    route_exists = await cursor.fetchone() is not None
                if not route_exists:
                    log.info(f"Creating route for account: {address}")
                    created_route_id = await RouteManager.create_route_for_account(
                        account
                    )
                    if not created_route_id:
                        log.error(f"Failed to create route for account: {address}")
                        return
            except Exception as e:
                log.error(f"Error checking route: {str(e)}")
                return

            tasks_to_run = await Database.get_tasks_to_run(
                route_id, config.always_run_tasks.modules
            )
            if not tasks_to_run:
                log.info(f"All tasks completed for account: {address}")
                return

            faucet_failed = False
            for task in tasks_to_run:
                if faucet_failed:
                    break

                module_name = task["module_name"]
                if module_name not in self.module_functions:
                    log.warning(f"Module '{module_name}' not implemented!")
                    continue

                log.info(f"Executing task: {module_name} for account: {address}")
                success, message = await process_execution(
                    account, self.module_functions[module_name]
                )

                async with Database.transaction() as conn:
                    if "id" in task and task["id"] is not None:
                        await Database.update_task_status(
                            task["id"],
                            "success" if success else "failed",
                            result=message if success else None,
                            error=message if not success else None,
                            existing_conn=conn,
                        )
                    else:
                        cursor = await conn.execute(
                            "SELECT id FROM statistics_tasks WHERE name = ? AND module_name = ?",
                            (task["route_name"], module_name),
                        )
                        existing_task = await cursor.fetchone()
                        status = "success" if success else "failed"
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        if existing_task:
                            await conn.execute(
                                """
                                UPDATE statistics_tasks 
                                SET status = ?, result_message = ?, error_message = ?, 
                                    last_executed = ? 
                                WHERE id = ?
                                """,
                                (
                                    status,
                                    message if success else None,
                                    message if not success else None,
                                    current_time,
                                    existing_task["id"],
                                ),
                            )
                        else:
                            await conn.execute(
                                """
                                INSERT INTO statistics_tasks 
                                    (name, module_name, status, result_message, 
                                     error_message, last_executed) 
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    task["route_name"],
                                    module_name,
                                    status,
                                    message if success else None,
                                    message if not success else None,
                                    current_time,
                                ),
                            )

                if success and task != tasks_to_run[-1] and not faucet_failed:
                    await random_sleep(
                        address,
                        config.delay_between_tasks.min,
                        config.delay_between_tasks.max,
                    )

                if module_name == "faucet" and not success:
                    log.error(
                        f"Route interrupted for {address} due to faucet failure"
                    )
                    faucet_failed = True
                    break

            try:
                await Database.update_account_statistics(address)
                progress.increment()
                log.info(f"Processed accounts: {progress.processed}/{progress.total}")
            except Exception as e:
                log.error(f"Error updating statistics for {address}: {str(e)}")

        batch_size = config.threads
        for i in range(0, len(config.accounts), batch_size):
            batch = config.accounts[i : i + batch_size]

            async with asyncio.TaskGroup() as tg:
                for account in batch:
                    tg.create_task(process_account(account))

            if i + batch_size < len(config.accounts):
                await asyncio.sleep(0.5)

    async def process_view_routes(self) -> None:
        try:
            routes_stats = await Database.get_route_stats()
            if not routes_stats:
                log.info("No route statistics found")
                return
            log.info("=== Route Statistics ===")
            for route in routes_stats:
                log.info(
                    f"Account: {get_address(route.private_key)} | "
                    f"Status: {route.status} | "
                    f"Tasks: ✅ {route.success_tasks} ❌ {route.failed_tasks} "
                    f"⏳ {route.pending_tasks}"
                )
            log.info("=======================\n")
        except Exception as e:
            log.error(f"Failed to get route stats: {str(e)}")

    async def process_view_statistics(self) -> None:
        try:
            log.info("Getting detailed statistics...")
            accounts_stats, summary = await Database.get_accounts_statistics()
            log.info("\n📊 Detailed statistics by accounts 📊")
            log.info("=" * 100)
            for i, acc in enumerate(accounts_stats, 1):
                log.info(f"👤 Account {i}: {acc.address}")
                log.info(
                    f"✅ Completed: {acc.completed_tasks}/{acc.total_tasks} "
                    f"({acc.percentage_completed:.1f}%) | ❌ Errors: {acc.failed_tasks} "
                    f"| ⏳ Pending: {acc.pending_tasks}"
                    " "
                )
                if acc.task_details:
                    log.info("📋 Tasks:")
                    for task in acc.task_details:
                        last_exec = task["last_executed"] or "Not started"
                        match task["status"]:
                            case "success":
                                log.info(
                                    f"✅ {task['module_name']}: "
                                    f"success (last run: {last_exec})"
                                )
                            case "failed":
                                log.info(
                                    f"❌ {task['module_name']}: "
                                    f"failed (last run: {last_exec})"
                                )
                            case "pending":
                                log.info(
                                    f"⏳ {task['module_name']}: "
                                    f"pending (last run: {last_exec})"
                                )
                            case _:
                                log.info(
                                    f"❓ {task['module_name']}: "
                                    f"unknown (last run: {last_exec})"
                                )
                log.info("-" * 100)
            log.info("📈 Summary statistics 📈")
            log.info("=" * 100)
            log.info(f"📚 Total accounts: {summary.total_accounts}")
            log.info(" ")
            log.info(
                f"✅ Successfully executed modules: {summary.success_percentage:.1f}%"
            )
            log.info(f"❌ Failed modules: {summary.failed_percentage:.1f}%")
            log.info(f"⏳ Pending modules: {summary.pending_percentage:.1f}%")
            log.info(" ")
            if summary.error_modules:
                log.info("-" * 100)
                log.info("⚠️  Modules with errors:")
                for err_mod in summary.error_modules:
                    log.info(
                        f"❌ {err_mod.module_name}: "
                        f"in {len(err_mod.accounts_affected)} accounts"
                    )
            else:
                log.info("✨ No modules with errors!")
            log.info("=" * 100)
        except Exception as e:
            log.error(f"Error getting statistics: {str(e)}")

    async def execute(self) -> bool:
        await self.init_database()
        self.console.build()
        match config.module:
            case "exit":
                log.info("🔴 Exiting program...")
                return True
            case "view_statistics":
                await self.process_view_statistics()
                return False
            case "view_routes":
                await self.process_view_routes()
                return False
            case "generate_routes":
                await RouteManager.create_routes_for_all_accounts(config.accounts)
                return False
            case "execute_route":
                await self.process_route_execution()
                return False
            case module if module in self.module_functions:
                async def process_account(account):
                    success, message = await process_execution(account, self.module_functions[module])
                    progress.increment()
                    log.info(f"Processed accounts: {progress.processed}/{progress.total}")
                    return success, message
                    
                tasks = []
                async with asyncio.TaskGroup() as tg:
                    for account in config.accounts:
                        tasks.append(tg.create_task(process_account(account)))
                    
                results = [task.result() for task in tasks]
                
                return False
            case _:
                log.error(f"Module {config.module} not implemented!")
                return False