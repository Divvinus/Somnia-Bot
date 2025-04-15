import aiosqlite
from datetime import datetime, timedelta

import orjson

from .database_core import Database
from .models import (
    RouteStats,
    AccountStatistics,
    SummaryStatistics,
    ModuleErrorStat,
)
from .exceptions import DatabaseError
from src.logger import AsyncLogger
from src.utils import get_address


class OptimizedDatabase(Database):
    logger = AsyncLogger()
    
    @classmethod
    async def get_tasks_to_run(
        cls, route_name: str, always_run_modules: list[str] = None
    ) -> list[dict]:
        conn = await cls._get_connection()
        try:
            async with await conn.execute(
                "SELECT route FROM routes WHERE name = ?", (route_name,)
            ) as cursor:
                route = await cursor.fetchone()
                if not route:
                    await OptimizedDatabase.logger.logger_msg(
                        msg=f"Route {route_name} not found", type_msg="warning", 
                        method_name="get_tasks_to_run"
                    )
                    return []
                
                modules = orjson.loads(route["route"])

            async with await conn.execute(
                """SELECT id, module_name, status, last_executed, error_count
                FROM statistics_tasks WHERE name = ?""",
                (route_name,),
            ) as cursor:
                tasks_data = await cursor.fetchall()

            unique_modules = list(dict.fromkeys(modules))
            
            tasks_dict = {task["module_name"]: task for task in tasks_data}
            now = datetime.now()
            tasks = []

            already_scheduled = set()

            for i, module in enumerate(unique_modules):
                if module in already_scheduled:
                    continue
                
                task_data = tasks_dict.get(module)
                should_run = False

                if not task_data:
                    should_run = True
                    await OptimizedDatabase.logger.logger_msg(
                        msg=f"Task {module} for {route_name} never executed before, will run", 
                        type_msg="debug", method_name="get_tasks_to_run"
                    )
                    
                elif task_data["status"] != "success":
                    error_count = task_data["error_count"] or 0
                    max_attempts = 3

                    last_executed_naive = datetime.strptime(
                        task_data["last_executed"], "%Y-%m-%d %H:%M:%S"
                    ) if task_data["last_executed"] else None
                    last_executed = last_executed_naive.replace() if last_executed_naive else None

                    if last_executed and (now - last_executed) >= timedelta(hours=24):
                        error_count = 0
                        await OptimizedDatabase.logger.logger_msg(
                            msg=f"Reset error_count for {module} due to timeout", 
                            type_msg="debug", method_name="get_tasks_to_run"
                        )

                    if error_count < max_attempts:
                        should_run = True
                        await OptimizedDatabase.logger.logger_msg(
                            msg=f"Task {module} has status {task_data['status']}, "
                            f"attempt {error_count + 1}/{max_attempts}, will run", 
                            type_msg="debug", method_name="get_tasks_to_run"
                        )
                        
                    else:
                        await OptimizedDatabase.logger.logger_msg(
                            msg=f"Task {module} has exhausted {max_attempts} attempts. "
                            f"Next attempt will be in 24 hours after {last_executed}.", 
                            type_msg="warning", method_name="get_tasks_to_run"
                        )
                        
                elif module in (always_run_modules or []):
                    should_run = False
                    required_hours = 24 if module in ("faucet", "onchain_gm") else 1
                    min_interval = timedelta(hours=required_hours)

                    if task_data["last_executed"] is None:
                        should_run = True
                    else:
                        last_executed_naive = datetime.strptime(
                            task_data["last_executed"], 
                            "%Y-%m-%d %H:%M:%S"
                        )
                        last_executed = last_executed_naive.replace()
                        now = datetime.now()

                        if (now - last_executed) >= min_interval:
                            should_run = True
                        else:
                            next_run_time = last_executed + min_interval
                            time_left = next_run_time - now
                            
                            total_seconds = time_left.total_seconds()
                            if total_seconds > 0:
                                hours_left = int(total_seconds // 3600)
                                minutes_left = int((total_seconds % 3600) // 60)
                                
                                module_display_names = {
                                    "faucet": "Faucet", 
                                    "onchain_gm": "Onchain GM", 
                                }
                                module_name = module_display_names.get(module, module.capitalize())
                                
                                await OptimizedDatabase.logger.logger_msg(
                                    msg=f"{module_name} for account {route_name} will be available in "
                                    f"{hours_left} hours {minutes_left} minutes", 
                                    type_msg="warning", method_name="get_tasks_to_run"
                                )

                if should_run:
                    already_scheduled.add(module)
                    tasks.append(
                        {
                            "id": task_data["id"] if task_data else None,
                            "module_name": module,
                            "route_name": route_name,
                            "order_num": i,
                            "status": task_data["status"] if task_data else "pending",
                            "last_executed": task_data["last_executed"]
                            if task_data
                            else None,
                            "error_count": task_data["error_count"]
                            if task_data
                            else 0,
                        }
                    )
            return tasks
        except aiosqlite.Error as e:
            await OptimizedDatabase.logger.logger_msg(
                msg=f"Failed to get tasks to run: {str(e)}", 
                type_msg="error", method_name="get_tasks_to_run"
            )
            raise DatabaseError(f"Failed to get tasks: {str(e)}")
        
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def update_task_status(
        cls,
        task_id: int,
        status: str,
        result: str | None = None,
        error: str | None = None,
        existing_conn=None,
    ) -> None:
        connection_owned = existing_conn is None
        conn = existing_conn or await cls._get_connection()
        try:
            if connection_owned:
                async with cls._db_write_semaphore:
                    await conn.execute("BEGIN")

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            async with await conn.execute(
                """
                UPDATE statistics_tasks
                SET status = ?, result_message = ?, error_message = ?,
                    last_executed = ?,
                    error_count = CASE WHEN ? = 'failed'
                    THEN COALESCE(error_count, 0) + 1 ELSE 0 END
                WHERE id = ?
                """,
                (status, result, error, current_time, status, task_id),
            ) as cursor:
                if cursor.rowcount == 0:
                    await OptimizedDatabase.logger.logger_msg(
                        msg=f"Task with ID {task_id} does not exist. Skipping update.", 
                        type_msg="warning", method_name="update_task_status"
                    )
                    return

            if connection_owned:
                await conn.execute("COMMIT")
                await OptimizedDatabase.logger.logger_msg(
                    msg=f"Task {task_id} updated with status '{status}'", type_msg="info"
                )
                
        except aiosqlite.Error as e:
            if connection_owned:
                try:
                    await conn.execute("ROLLBACK")
                except Exception:
                    pass
                await OptimizedDatabase.logger.logger_msg(
                    msg=f"Failed to update task {task_id}: {str(e)}", 
                    type_msg="error", method_name="update_task_status"
                )
                raise DatabaseError(f"Failed to update task: {str(e)}")
            
        finally:
            if connection_owned:
                await cls._release_connection(conn)

    @classmethod
    async def create_route(
        cls, private_key: str, route_name: str, modules: list[str], preserve_status: bool = True
    ) -> None:
        address = get_address(private_key)
        async with cls._db_write_semaphore:
            async with cls.transaction() as conn:
                try:
                    await conn.execute(
                        "INSERT OR IGNORE INTO accounts (private_key, address) VALUES (?, ?)",
                        (private_key, address),
                    )

                    cursor = await conn.execute(
                        "SELECT name, status FROM routes WHERE name = ?", (address,)
                    )
                    existing_route = await cursor.fetchone()
                    
                    route_json = orjson.dumps(modules)
                    
                    if existing_route and preserve_status:
                        await conn.execute(
                            """
                            UPDATE routes SET route = ? WHERE name = ?
                            """,
                            (route_json, address),
                        )
                        await OptimizedDatabase.logger.logger_msg(
                            msg=f"Route updated while preserving status", 
                            type_msg="info", method_name="create_route"
                        )
                    else:
                        # Create new route or update and reset status
                        await conn.execute(
                            """
                            INSERT INTO routes (name, route, status) VALUES (?, ?, 'pending')
                            ON CONFLICT(name) DO UPDATE SET route = excluded.route,
                            status = 'pending'
                            """,
                            (address, route_json),
                        )

                    for module in modules:
                        await conn.execute(
                            """
                            INSERT INTO statistics_tasks (name, module_name, status)
                            VALUES (?, ?, 'pending')
                            ON CONFLICT(name, module_name) DO NOTHING
                            """,
                            (address, module),
                        )
                except aiosqlite.Error as e:
                    await OptimizedDatabase.logger.logger_msg(
                        msg=f"Database operation failed during route creation: {str(e)}", 
                        type_msg="error", method_name="create_route"
                    )
                    raise DatabaseError(f"Route creation failed: {str(e)}")

    @classmethod
    async def get_route_stats(cls) -> list[RouteStats]:
        conn = await cls._get_connection()
        try:
            try:
                async with await conn.execute(
                    """
                    SELECT
                        r.name,
                        r.name as route_name,
                        a.private_key,
                        r.status,
                        COUNT(st.id) as total_tasks,
                        SUM(CASE WHEN st.status = 'success' THEN 1 ELSE 0 END)
                        as success_tasks,
                        SUM(CASE WHEN st.status = 'failed' THEN 1 ELSE 0 END)
                        as failed_tasks,
                        SUM(CASE WHEN st.status = 'pending' THEN 1 ELSE 0 END)
                        as pending_tasks
                    FROM routes r
                    JOIN accounts a ON r.name = a.address
                    LEFT JOIN statistics_tasks st ON st.name = r.name
                    GROUP BY r.name, a.private_key, r.status
                    ORDER BY r.name
                    """
                ) as cursor:
                    routes = [
                        RouteStats(
                            id=row["name"],
                            route_name=row["route_name"],
                            private_key=row["private_key"],
                            status=row["status"],
                            total_tasks=row["total_tasks"] or 0,
                            success_tasks=row["success_tasks"] or 0,
                            failed_tasks=row["failed_tasks"] or 0,
                            pending_tasks=row["pending_tasks"] or 0,
                        )
                        for row in await cursor.fetchall()
                    ]
                    return routes
            except aiosqlite.OperationalError as e:
                if "no such table" in str(e):
                    raise DatabaseError(f"Database not initialized: {str(e)}")
                raise
        except aiosqlite.Error as e:
            await OptimizedDatabase.logger.logger_msg(
                msg=f"Failed to get route statistics: {str(e)}", 
                type_msg="error", method_name="get_route_stats"
            )
            raise DatabaseError(f"Failed to get route statistics: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def get_accounts_statistics(
        cls,
    ) -> tuple[list[AccountStatistics], SummaryStatistics]:
        conn = await cls._get_connection()
        try:
            try:
                async with await conn.execute(
                    """
                    SELECT
                        a.address,
                        a.private_key,
                        sa.percentage_completed,
                        COUNT(st.id) as total_tasks,
                        SUM(CASE WHEN st.status = 'success' THEN 1 ELSE 0 END)
                        as completed_tasks,
                        SUM(CASE WHEN st.status = 'failed' THEN 1 ELSE 0 END)
                        as failed_tasks,
                        SUM(CASE WHEN st.status = 'pending' THEN 1 ELSE 0 END)
                        as pending_tasks
                    FROM accounts a
                    LEFT JOIN statistics_account sa ON a.address = sa.name
                    LEFT JOIN statistics_tasks st ON a.address = st.name
                    GROUP BY a.address, a.private_key
                    ORDER BY sa.percentage_completed DESC
                    """
                ) as cursor:
                    accounts_stats = []
                    for row in await cursor.fetchall():
                        address = row["address"]
                        async with await conn.execute(
                            """
                            SELECT module_name, status, result_message, error_message,
                            last_executed
                            FROM statistics_tasks
                            WHERE name = ?
                            ORDER BY module_name
                            """,
                            (address,),
                        ) as task_cursor:
                            task_details = [dict(task) async for task in task_cursor]
                        accounts_stats.append(
                            AccountStatistics(
                                address=address,
                                private_key=row["private_key"],
                                total_tasks=row["total_tasks"] or 0,
                                completed_tasks=row["completed_tasks"] or 0,
                                failed_tasks=row["failed_tasks"] or 0,
                                pending_tasks=row["pending_tasks"] or 0,
                                percentage_completed=row["percentage_completed"] or 0.0,
                                task_details=task_details,
                            )
                        )

                total_accounts = len(accounts_stats)
                total_modules = sum(acc.total_tasks for acc in accounts_stats)
                total_completed = sum(acc.completed_tasks for acc in accounts_stats)
                total_failed = sum(acc.failed_tasks for acc in accounts_stats)
                total_pending = sum(acc.pending_tasks for acc in accounts_stats)

                module_errors = {}
                for acc in accounts_stats:
                    for task in acc.task_details:
                        if task["status"] == "failed":
                            module_name = task["module_name"]
                            module_errors.setdefault(module_name, {"count": 0, "accounts": []})
                            module_errors[module_name]["count"] += 1
                            module_errors[module_name]["accounts"].append(acc.address)

                error_modules = [
                    ModuleErrorStat(
                        module_name=module,
                        error_count=stats["count"],
                        accounts_affected=stats["accounts"],
                    )
                    for module, stats in module_errors.items()
                ]
                error_modules.sort(key=lambda x: x.error_count, reverse=True)

                success_percentage = (
                    (total_completed / total_modules * 100) if total_modules > 0 else 0
                )
                failed_percentage = (
                    (total_failed / total_modules * 100) if total_modules > 0 else 0
                )
                pending_percentage = (
                    (total_pending / total_modules * 100) if total_modules > 0 else 0
                )

                summary = SummaryStatistics(
                    total_accounts=total_accounts,
                    success_percentage=success_percentage,
                    failed_percentage=failed_percentage,
                    pending_percentage=pending_percentage,
                    error_modules=error_modules,
                )
                return accounts_stats, summary
            except aiosqlite.OperationalError as e:
                if "no such table" in str(e):
                    raise DatabaseError(f"Database not initialized: {str(e)}")
                raise
        except aiosqlite.Error as e:
            await OptimizedDatabase.logger.logger_msg(
                msg=f"Failed to get account statistics: {str(e)}", 
                type_msg="error", method_name="get_accounts_statistics"
            )
            raise DatabaseError(f"Failed to get account statistics: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def update_account_statistics(cls, address: str) -> None:
        async with cls._db_write_semaphore:
            async with cls.transaction() as conn:
                try:
                    async with await conn.execute(
                        """
                        SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END)
                            as completed,
                            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
                            as failed,
                            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)
                            as pending
                        FROM statistics_tasks
                        WHERE name = ?
                        """,
                        (address,),
                    ) as cursor:
                        stats = await cursor.fetchone()
                        if not stats or stats["total"] == 0:
                            return
                        total = stats["total"]
                        percentage = (stats["completed"] / total * 100) if total > 0 else 0

                    async with await conn.execute(
                        """
                        SELECT module_name, status, error_message
                        FROM statistics_tasks
                        WHERE name = ? AND status != 'success'
                        """,
                        (address,),
                    ) as cursor:
                        pending_tasks = [
                            f"{row['module_name']}({row['error_message']})"
                            if row["status"] == "failed" and row["error_message"]
                            else f"{row['module_name']}(error)"
                            if row["status"] == "failed"
                            else row["module_name"]
                            async for row in cursor
                        ]

                    await conn.execute(
                        """
                        INSERT INTO statistics_account
                        (name, percentage_completed, pending_tasks)
                        VALUES (?, ?, ?)
                        ON CONFLICT(name) DO UPDATE SET
                        percentage_completed = excluded.percentage_completed,
                        pending_tasks = excluded.pending_tasks
                        """,
                        (address, percentage, orjson.dumps(pending_tasks)),
                    )
                except aiosqlite.Error as e:
                    await OptimizedDatabase.logger.logger_msg(
                        msg=f"Error updating account statistics: {str(e)}", type_msg="error", 
                        address=address, method_name="update_account_statistics"
                    )
                    raise


Database.get_tasks_to_run = OptimizedDatabase.get_tasks_to_run
Database.update_task_status = OptimizedDatabase.update_task_status
Database.create_route = OptimizedDatabase.create_route
Database.get_route_stats = OptimizedDatabase.get_route_stats
Database.get_accounts_statistics = OptimizedDatabase.get_accounts_statistics
Database.update_account_statistics = OptimizedDatabase.update_account_statistics