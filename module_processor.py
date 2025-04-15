import asyncio
from typing import Callable
from datetime import datetime
import os

from src.console import Console
from src.task_manager import SomniaBot
from src.db import Database
from src.db.route_manager import RouteManager
from src.db.models import SummaryStatistics
from bot_loader import config, progress, semaphore
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address, random_sleep
from src.utils.send_tg_message import SendTgMessage
from src.db.database_operations import DatabaseError


async def process_execution(account: Account, process_func: Callable) -> tuple[bool, str]:
    logger = AsyncLogger()

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
            await logger.logger_msg(
                f"Error: {str(e)}",
                address=address,
                type_msg="error", 
                method_name="process_execution"
            )
            return False, str(e)


class ModuleProcessor(AsyncLogger):
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
        super().__init__()
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
            await self.logger_msg(
                f"Database init error: {str(e)}", 
                type_msg="error",
                method_name="init_database"
            )

    async def get_account_stats_message(self, address: str) -> list[str]:
        try:
            async with Database.transaction() as conn:
                cursor = await conn.execute(
                    """
                    SELECT
                        a.address,
                        COUNT(st.id) as total_tasks,
                        SUM(CASE WHEN st.status = 'success' THEN 1 ELSE 0 END) as completed_tasks,
                        SUM(CASE WHEN st.status = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
                        SUM(CASE WHEN st.status = 'pending' THEN 1 ELSE 0 END) as pending_tasks,
                        sa.percentage_completed
                    FROM accounts a
                    LEFT JOIN statistics_account sa ON a.address = sa.name
                    LEFT JOIN statistics_tasks st ON a.address = st.name
                    WHERE a.address = ?
                    GROUP BY a.address
                    """,
                    (address,),
                )
                acc_stats = await cursor.fetchone()
                
                cursor = await conn.execute(
                    """
                    SELECT module_name, status, last_executed
                    FROM statistics_tasks
                    WHERE name = ?
                    ORDER BY module_name
                    """,
                    (address,),
                )
                task_details = await cursor.fetchall()
                
            if not acc_stats:
                return [f"Statistics for {address} not found"]
                
            messages = []
            messages.append(f"📊 Account statistics 📊\n")
            messages.append(f"👤 Account: {address}\n")
            
            total = acc_stats["total_tasks"] or 0
            completed = acc_stats["completed_tasks"] or 0
            failed = acc_stats["failed_tasks"] or 0
            pending = acc_stats["pending_tasks"] or 0
            percentage = acc_stats["percentage_completed"] or 0.0
            
            messages.append(f"\n✅ Completed: {completed}/{total} ({percentage:.1f}%) \n❌ Errors: {failed} \n⏳ Pending: {pending}\n")
            
            if task_details:
                messages.append("📋 Tasks:")
                for task in task_details:
                    last_exec = task["last_executed"] or "Not started"
                    match task["status"]:
                        case "success":
                            messages.append(f"✅ {task['module_name']}: successfully (last run: {last_exec})")
                        case "failed":
                            messages.append(f"❌ {task['module_name']}: error (last run: {last_exec})")
                        case "pending":
                            messages.append(f"⏳ {task['module_name']}: waiting (last run: {last_exec})")
                        case _:
                            messages.append(f"❓ {task['module_name']}: unknown (last run: {last_exec})")
            
            return messages
        except Exception as e:
            await self.logger_msg(
                f"Error getting account statistics: {str(e)}", 
                type_msg="error",
                method_name="get_account_stats_message"
            )
            return [f"Error getting statistics: {str(e)}"]

    async def send_stats_to_telegram(self, account: Account, messages: list[str]) -> None:
        try:
            sender = SendTgMessage(account)
            await sender.send_tg_message(messages, disable_notification=True)
        except Exception as e:
            await self.logger_msg(
                f"Error sending statistics to Telegram: {str(e)}", 
                type_msg="error",
                method_name="send_stats_to_telegram"
            )

    async def process_route_execution(self) -> None:
        try:
            async with Database.transaction() as conn:
                await conn.execute("SELECT 1 FROM routes LIMIT 1")
        except DatabaseError as e:
            if "no such table" in str(e):
                await self.logger_msg(
                    "Database not initialized. Please create routes using 'Generate routes'", 
                    type_msg="warning"
                )
                return
            else:
                await self.logger_msg(
                    f"Error checking database: {str(e)}", type_msg="error",
                    method_name="process_route_execution"
                )
                return

        async def process_account(account: Account) -> None:
            address = get_address(account.private_key)
            
            await self.logger_msg(
                f"Processing route", type_msg="info", address=address
            )
            
            route_id = address
            try:
                async with Database.transaction() as conn:
                    cursor = await conn.execute(
                        "SELECT 1 FROM routes WHERE name = ?", (route_id,)
                    )
                    route_exists = await cursor.fetchone() is not None
                    
                if not route_exists:
                    await self.logger_msg(
                        f"Creating route", type_msg="info", address=address
                    )
                    created_route_id = await RouteManager.create_route_for_account(
                        account
                    )
                    
                    if not created_route_id:
                        await self.logger_msg(
                            f"Failed to create route", type_msg="error",
                            address=address, method_name="process_route_execution"
                        )
                        return
                    
            except Exception as e:
                await self.logger_msg(
                    f"Error checking route: {str(e)}", type_msg="error",
                    method_name="process_route_execution"
                )
                return

            tasks_to_run = await Database.get_tasks_to_run(
                route_id, config.always_run_tasks.modules
            )
            
            if not tasks_to_run:
                await self.logger_msg(
                    f"All tasks completed", type_msg="info", address=address
                )
                return

            faucet_failed = False
            for task in tasks_to_run:
                if faucet_failed:
                    break

                module_name = task["module_name"]
                if module_name not in self.module_functions:
                    await self.logger_msg(
                        f"Module '{module_name}' not implemented!", 
                        type_msg="warning",
                        method_name="process_route_execution"
                    )
                    continue

                await self.logger_msg(
                    f"Executing task: {module_name}", type_msg="info", address=address
                )
                
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
                    await self.logger_msg(
                        f"Route interrupted due to faucet failure", type_msg="error",
                        address=address, method_name="process_route_execution"
                    )
                    faucet_failed = True
                    break

            try:
                await Database.update_account_statistics(address)
                
                if config.send_stats_to_telegram:
                    stats_messages = await self.get_account_stats_message(address)
                    await self.send_stats_to_telegram(account, stats_messages)
                
                progress.increment()
                await self.logger_msg(
                    f"Processed accounts: {progress.processed}/{progress.total}",
                    type_msg="info"
                )
            except Exception as e:
                await self.logger_msg(
                    f"Error updating statistics: {str(e)}", type_msg="error",
                    address=address, method_name="process_route_execution"
                )

        batch_size = config.threads
        for i in range(0, len(config.accounts), batch_size):
            batch = config.accounts[i : i + batch_size]

            async with asyncio.TaskGroup() as tg:
                for account in batch:
                    tg.create_task(process_account(account))

            if i + batch_size < len(config.accounts):
                await asyncio.sleep(0.5)

        if config.send_stats_to_telegram and config.accounts:
            try:
                accounts_stats, summary = await Database.get_accounts_statistics()
                summary_messages = await self.get_summary_stats_message(summary)
                await self.send_stats_to_telegram(config.accounts[0], summary_messages)
            except Exception as e:
                await self.logger_msg(
                    f"Error sending final statistics: {str(e)}", 
                    type_msg="error",
                    method_name="process_route_execution"
                )

    async def process_view_routes(self) -> None:
        try:
            routes_stats = await Database.get_route_stats()
            if not routes_stats:
                await self.logger_msg("No route statistics. Please create routes using 'Generate routes'", type_msg="info")
                return
            await self.logger_msg("=== Route Statistics ===", type_msg="info")
            for route in routes_stats:
                await self.logger_msg(
                    f"Account: {get_address(route.private_key)} | "
                    f"Status: {route.status} | "
                    f"Tasks: ✅ {route.success_tasks} ❌ {route.failed_tasks} "
                    f"⏳ {route.pending_tasks}",
                    type_msg="info"
                )
            await self.logger_msg("=======================\n", type_msg="info")
        except DatabaseError as e:
            if "no such table" in str(e):
                await self.logger_msg(
                    "Database not initialized. Please create routes using 'Generate routes'", 
                    type_msg="warning"
                )
            else:
                await self.logger_msg(
                    f"Failed to get route statistics: {str(e)}", 
                    type_msg="error",
                    method_name="process_view_routes"
                )

    async def process_view_statistics(self) -> None:
        try:
            await self.logger_msg("Getting detailed statistics...", type_msg="info")
            accounts_stats, summary = await Database.get_accounts_statistics()
            await self.logger_msg("\n📊 Detailed account statistics 📊", type_msg="info")
            await self.logger_msg("=" * 100, type_msg="info")
            for i, acc in enumerate(accounts_stats, 1):
                await self.logger_msg(
                    f"👤 Account {i}: {acc.address}", 
                    type_msg="info"
                )
                await self.logger_msg(
                    f"✅ Completed: {acc.completed_tasks}/{acc.total_tasks} "
                    f"({acc.percentage_completed:.1f}%) | ❌ Errors: {acc.failed_tasks} "
                    f"| ⏳ Pending: {acc.pending_tasks}"
                    " ",
                    type_msg="info"
                )
                if acc.task_details:
                    await self.logger_msg("📋 Tasks:", type_msg="info")
                    for task in acc.task_details:
                        last_exec = task["last_executed"] or "Not started"
                        match task["status"]:
                            case "success":
                                await self.logger_msg(
                                    f"✅ {task['module_name']}: "
                                    f"success (last run: {last_exec})",
                                    type_msg="info"
                                )
                            case "failed":
                                await self.logger_msg(
                                    f"❌ {task['module_name']}: "
                                    f"failed (last run: {last_exec})",
                                    type_msg="info"
                                )
                            case "pending":
                                await self.logger_msg(
                                    f"⏳ {task['module_name']}: "
                                    f"pending (last run: {last_exec})",
                                    type_msg="info"
                                )
                            case _:
                                await self.logger_msg(
                                    f"❓ {task['module_name']}: "
                                    f"unknown (last run: {last_exec})",
                                    type_msg="info"
                                )
                await self.logger_msg("-" * 100, type_msg="info")
            await self.logger_msg("📈 Summary statistics 📈", type_msg="info")
            await self.logger_msg("=" * 100, type_msg="info")
            await self.logger_msg(f"📚 Total accounts: {summary.total_accounts}", type_msg="info")
            await self.logger_msg(" ", type_msg="info")
            await self.logger_msg(
                f"✅ Successfully executed modules: {summary.success_percentage:.1f}%",
                type_msg="info"
            )
            await self.logger_msg(
                f"❌ Failed modules: {summary.failed_percentage:.1f}%", type_msg="info"
            )
            await self.logger_msg(
                f"⏳ Pending modules: {summary.pending_percentage:.1f}%", type_msg="info"
            )
            await self.logger_msg(" ", type_msg="info")
            if summary.error_modules:
                await self.logger_msg("-" * 100, type_msg="info")
                await self.logger_msg("⚠️  Modules with errors:", type_msg="info")
                for err_mod in summary.error_modules:
                    await self.logger_msg(
                        f"❌ {err_mod.module_name}: "
                        f"in {len(err_mod.accounts_affected)} accounts",
                        type_msg="info"
                    )
            else:
                await self.logger_msg("✨ No modules with errors!", type_msg="info")
            await self.logger_msg("=" * 100, type_msg="info")
        except DatabaseError as e:
            if "no such table" in str(e):
                await self.logger_msg(
                    "Database not initialized. Please create routes using 'Generate routes'", 
                    type_msg="warning"
                )
            else:
                await self.logger_msg(
                    f"Error getting statistics: {str(e)}", 
                    type_msg="error",
                    method_name="process_view_statistics"
                )

    async def get_summary_stats_message(self, summary: SummaryStatistics) -> list[str]:
        messages = []
        messages.append("📈 Summary statistics 📈\n")
        messages.append(f"📚 Total accounts: {summary.total_accounts}\n")
        messages.append(f"✅ Successfully executed modules: {summary.success_percentage:.1f}%")
        messages.append(f"❌ Modules with errors: {summary.failed_percentage:.1f}%")
        messages.append(f"⏳ Pending modules: {summary.pending_percentage:.1f}%\n")
        
        if summary.error_modules:
            messages.append("⚠️ Modules with errors:\n")
            for err_mod in summary.error_modules:
                messages.append(f"❌ {err_mod.module_name}: in {len(err_mod.accounts_affected)} accounts\n")
        else:
            messages.append("✨ No modules with errors!")
        
        return messages

    async def execute(self) -> bool:
        self.console.build()
        match config.module:
            case "exit":
                await self.logger_msg("🔴 Exit program...", type_msg="info")
                return True
            case "view_statistics":
                try:
                    await self.process_view_statistics()
                except Exception as e:
                    await self.logger_msg(
                        f"Error in view_statistics: {str(e)}", type_msg="error",
                        method_name="execute"
                    )

                try:
                    if config.send_stats_to_telegram and config.accounts:
                        accounts_stats, summary = await Database.get_accounts_statistics()
                        summary_messages = await self.get_summary_stats_message(summary)
                        await self.send_stats_to_telegram(config.accounts[0], summary_messages)
                except Exception as e:
                    pass
                
                return False
            case "view_routes":
                await self.process_view_routes()
                return False
            case "generate_routes":
                await self.init_database()
                await RouteManager.create_routes_for_all_accounts(config.accounts)
                return False
            case "execute_route":
                await self.process_route_execution()
                return False
            case "update_routes":
                try:
                    db_path = await Database.get_db_path()
                    if not os.path.exists(db_path):
                        await self.logger_msg(
                            "Database not found. Please create routes first using 'Generate routes'", 
                            type_msg="warning"
                        )
                        return False
                    
                    db_dir = os.path.dirname(db_path)
                    if not os.path.exists(db_dir):
                        await self.logger_msg(
                            "Database directory not found. Please create routes first using 'Generate routes'", 
                            type_msg="warning"
                        )
                        return False
                    
                    await RouteManager.update_routes_with_new_modules()
                except Exception as e:
                    await self.logger_msg(
                        f"Error updating routes: {str(e)}", 
                        type_msg="error",
                        method_name="execute"
                    )
                return False
            case module if module in self.module_functions:
                async def process_account(account):
                    success, message = await process_execution(account, self.module_functions[module])
                    progress.increment()
                    await self.logger_msg(
                        f"Processed accounts: {progress.processed}/{progress.total}",
                        type_msg="info"
                    )
                    return success, message
                    
                tasks = []
                async with asyncio.TaskGroup() as tg:
                    for account in config.accounts:
                        tasks.append(tg.create_task(process_account(account)))
                    
                results = [task.result() for task in tasks]
                
                return False
            case _:
                await self.logger_msg(
                    f"Module {config.module} not implemented!", 
                    type_msg="error",
                    method_name="execute"
                )
                return False