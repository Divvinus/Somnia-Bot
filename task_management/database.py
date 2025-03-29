import asyncio
import os
from collections import deque
from functools import wraps
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import aiosqlite
from pydantic import BaseModel, validate_call

from loader import config
from logger import log
from utils import get_address

class DatabaseError(Exception):
    """Base exception for database errors."""
    pass

class ConnectionError(DatabaseError):
    """Raised when a connection to the database cannot be established."""
    pass

class RouteNotFoundError(DatabaseError):
    """Raised when a route is not found for the specified account and name."""
    pass

def mask_private_key(private_key: str) -> str:
    if len(private_key) <= 8:
        return private_key
    return private_key[:5] + "..." + private_key[-5:]

def get_database_path() -> str:
    current_dir = os.getcwd()
    data_dir = os.path.join(current_dir, "data_bd")
    
    if not os.path.exists(data_dir):
        try:
            os.mkdir(data_dir)
            log.info(f"Created directory: {data_dir}")
        except PermissionError as e:
            log.error(f"Permission denied while creating directory 'data_bd': {str(e)}")
            raise
        except OSError as e:
            log.error(f"Failed to create directory 'data_bd': {str(e)}")
            raise
    
    db_path = os.path.join(data_dir, "somnia_db.sqlite")
    log.info(f"Database path: {db_path}")
    return db_path

DB_PATH = os.getenv("SOMNIA_DB_PATH", get_database_path())
MAX_CONNECTIONS = int(os.getenv("SOMNIA_MAX_CONNECTIONS", f"{config.threads}"))

class AccountModel(BaseModel):
    private_key: str
    address: str | None = None

class TaskUpdateModel(BaseModel):
    task_id: int
    status: str
    result: str | None = None
    error: str | None = None

class RouteStats(BaseModel):
    id: str
    route_name: str
    private_key: str
    status: str
    total_tasks: int
    success_tasks: int
    failed_tasks: int
    pending_tasks: int

def async_lru_cache(maxsize: int = 128):
    cache = {}
    lock = asyncio.Lock()

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            async with lock:
                if key in cache:
                    return cache[key]
            result = await func(*args, **kwargs)
            async with lock:
                if len(cache) >= maxsize:
                    cache.pop(next(iter(cache)))
                cache[key] = result
            return result
        return wrapper
    return decorator

class Database:
    _route_lock = asyncio.Lock()
    _connection_pool: deque = deque()
    _max_connections: int = MAX_CONNECTIONS
    _max_retries: int = 3
    _sqlite_version: tuple[int, int, int] | None = None
    _lock: asyncio.Lock = asyncio.Lock()
    _account_id_cache: dict[str, int] = {}

    @classmethod
    async def _check_sqlite_version(cls, conn: aiosqlite.Connection) -> None:
        try:
            async with await conn.execute("SELECT sqlite_version()") as cursor:
                version_str = (await cursor.fetchone())[0]
                cls._sqlite_version = tuple(map(int, version_str.split(".")))
                log.debug(f"SQLite version detected: {version_str}")
        except aiosqlite.Error as e:
            log.error(f"Failed to check SQLite version: {str(e)}")
            raise

    @classmethod
    async def _create_connection(cls) -> aiosqlite.Connection:
        try:
            conn = await aiosqlite.connect(
                database=DB_PATH,
                timeout=10,
                isolation_level=None,
                cached_statements=50,
            )
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA busy_timeout=10000")
            await conn.execute("PRAGMA wal_autocheckpoint=1000")
            await conn.execute("PRAGMA cache_size=-20000")
            conn.row_factory = aiosqlite.Row
            await cls._check_sqlite_version(conn)
            log.debug("New database connection established")
            return conn
        except aiosqlite.Error as e:
            log.error(f"Failed to create database connection: {str(e)}")
            raise ConnectionError(f"Database connection failed: {str(e)}")

    @classmethod
    async def _reconnect(cls, conn: aiosqlite.Connection) -> aiosqlite.Connection:
        try:
            await conn.execute("SELECT 1")
            try:
                await conn.close()
            except aiosqlite.Error as e:
                log.debug(f"Error closing connection before reconnect: {str(e)}")
        except aiosqlite.Error:
            log.debug("Connection inactive, creating a new one")
        return await cls._create_connection()

    @classmethod
    async def _get_connection(cls) -> aiosqlite.Connection:
        for attempt in range(cls._max_retries):
            try:
                async with cls._lock:
                    if not cls._connection_pool:
                        return await cls._create_connection()
                    conn = cls._connection_pool.popleft()
                    try:
                        await conn.execute("SELECT 1")
                        log.debug("Reusing existing database connection")
                        return conn
                    except aiosqlite.Error:
                        log.debug("Pooled connection unusable, reconnecting")
                        return await cls._reconnect(conn)
            except aiosqlite.Error as e:
                log.warning(f"Connection attempt {attempt + 1} failed: {str(e)}")
                async with cls._lock:
                    while cls._connection_pool:
                        try:
                            conn = cls._connection_pool.popleft()
                            await conn.close()
                        except aiosqlite.Error:
                            pass
                if attempt == cls._max_retries - 1:
                    log.error(f"Failed to connect after {cls._max_retries} attempts")
                    raise ConnectionError(f"Connection failed after {cls._max_retries} attempts")
                await asyncio.sleep(0.5)

    @classmethod
    async def _release_connection(cls, conn: aiosqlite.Connection) -> None:
        try:
            await conn.execute("SELECT 1")
            async with cls._lock:
                if len(cls._connection_pool) >= cls._max_connections:
                    await conn.close()
                    log.debug("Connection closed as pool is full")
                else:
                    cls._connection_pool.append(conn)
                    log.debug("Connection returned to pool")
        except aiosqlite.Error:
            log.debug("Connection closed and not returned to pool")

    @classmethod
    async def init_db(cls) -> None:
        conn = await cls._get_connection()
        try:
            # Создаем все таблицы с новой структурой
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    private_key TEXT UNIQUE NOT NULL,
                    address TEXT
                );
                
                CREATE TABLE IF NOT EXISTS routes (
                    id TEXT PRIMARY KEY,
                    account_id INTEGER,
                    route_name TEXT,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_id TEXT,
                    module_name TEXT NOT NULL,
                    order_num INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    result TEXT,
                    last_executed TIMESTAMP,
                    UNIQUE(route_id, module_name),
                    FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id INTEGER,
                    dependency_id INTEGER,
                    PRIMARY KEY (task_id, dependency_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (dependency_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_routes_account ON routes(account_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_route ON tasks(route_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_route_status ON tasks(route_id, status);
                CREATE INDEX IF NOT EXISTS idx_task_dependencies ON task_dependencies(task_id, dependency_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_module_status ON tasks(module_name, status);
                CREATE INDEX IF NOT EXISTS idx_tasks_last_executed ON tasks(last_executed);
            """)
            
            log.info("Database schema and indexes initialized with addresses as route IDs")
        except aiosqlite.Error as e:
            log.error(f"Failed to initialize database schema: {str(e)}")
            raise DatabaseError(f"Failed to initialize database: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def close_pool(cls) -> None:
        async with cls._lock:
            while cls._connection_pool:
                try:
                    conn = cls._connection_pool.popleft()
                    await conn.close()
                except aiosqlite.Error as e:
                    log.error(f"Failed to close connection: {str(e)}")
            cls._connection_pool.clear()
            cls._sqlite_version = None
            log.info("Database connection pool closed")

    @classmethod
    async def close(cls) -> None:
        await cls.close_pool()
        log.info("Database connections closed")

    @classmethod
    @asynccontextmanager
    async def transaction(cls) -> AsyncIterator[aiosqlite.Connection]:
        conn = await cls._get_connection()
        await conn.execute("BEGIN")
        try:
            yield conn
            await conn.execute("COMMIT")
        except Exception as e:
            await conn.execute("ROLLBACK")
            log.error(f"Transaction rolled back due to: {str(e)}")
            raise DatabaseError(f"Transaction failed: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    @async_lru_cache()
    async def get_account_id(cls, private_key: str) -> int:
        if private_key in cls._account_id_cache:
            return cls._account_id_cache[private_key]
        conn = await cls._get_connection()
        try:
            async with await conn.execute(
                "SELECT id FROM accounts WHERE private_key = ?", (private_key,)
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    raise DatabaseError(f"Account with private key {mask_private_key(private_key)} not found")
                account_id = result["id"]
                cls._account_id_cache[private_key] = account_id
                return account_id
        except aiosqlite.Error as e:
            log.error(f"Failed to retrieve account ID for {mask_private_key(private_key)}: {str(e)}")
            raise DatabaseError(f"Failed to retrieve account ID: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def sync_accounts(cls, accounts: list[AccountModel]) -> None:
        conn = await cls._get_connection()
        try:
            params = [(acc.private_key, get_address(acc.private_key)) for acc in accounts]
            await conn.executemany(
                "INSERT INTO accounts (private_key, address) VALUES (?, ?) "
                "ON CONFLICT(private_key) DO UPDATE SET address = COALESCE(excluded.address, address)",
                params
            )
            cls._account_id_cache.clear()
            log.info(f"Synchronized {len(params)} accounts")
        except aiosqlite.Error as e:
            log.error(f"Failed to synchronize accounts: {str(e)}")
            raise DatabaseError(f"Failed to synchronize accounts: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    @validate_call
    async def create_route(
        cls,
        account_id: int,
        route_id: str,
        route_name: str,
        modules: list[str],
        dependencies: dict[str, list[str]],
        always_run_modules: list[str] = None
    ) -> str:
        always_run_modules = always_run_modules or []

        async with cls._route_lock:
            async with cls.transaction() as conn:
                try:
                    cursor = await conn.execute(
                        "SELECT id FROM routes WHERE id = ?",
                        (route_id,)
                    )
                    existing_route = await cursor.fetchone()

                    if existing_route:
                        await conn.execute("""
                            DELETE FROM tasks 
                            WHERE route_id = ? 
                            AND module_name NOT IN ({})
                        """.format(','.join(['?']*len(always_run_modules))), 
                        (route_id, *always_run_modules))

                        await conn.execute("""
                            UPDATE tasks 
                            SET status = 'pending' 
                            WHERE route_id = ? 
                            AND module_name IN ({})
                        """.format(','.join(['?']*len(always_run_modules))), 
                        (route_id, *always_run_modules))
                    else:
                        await conn.execute(
                            "INSERT INTO routes (id, account_id, route_name) VALUES (?, ?, ?)",
                            (route_id, account_id, route_name)
                        )

                    modules = [*modules, *always_run_modules]
                    modules = list(dict.fromkeys(modules))

                    params_for_insert = [(route_id, module, idx) for idx, module in enumerate(modules)]
                    await conn.executemany(
                        "INSERT INTO tasks (route_id, module_name, order_num) VALUES (?, ?, ?)",
                        params_for_insert
                    )

                    async with await conn.execute(
                        "SELECT id, module_name FROM tasks WHERE route_id = ?",
                        (route_id,)
                    ) as cursor:
                        task_ids = {row["module_name"]: row["id"] for row in await cursor.fetchall()}

                    await conn.execute(
                        "DELETE FROM task_dependencies WHERE task_id IN (SELECT id FROM tasks WHERE route_id = ?)",
                        (route_id,)
                    )

                    dependency_params = []
                    for module, deps in dependencies.items():
                        if module not in task_ids:
                            continue
                        task_id = task_ids[module]
                        for dep in deps:
                            if dep in task_ids:
                                dependency_params.append((task_id, task_ids[dep]))

                    if dependency_params:
                        await conn.executemany(
                            "INSERT INTO task_dependencies (task_id, dependency_id) VALUES (?, ?)",
                            dependency_params
                        )

                    log.info(f"Route '{route_name}' created with {len(modules)} tasks, id: {route_id}")
                    return route_id

                except Exception as e:
                    log.error(f"Route creation error: {str(e)}")
                    raise DatabaseError(f"Database operation failed: {str(e)}")
                
    @classmethod
    async def get_all_tasks(cls, route_id: int) -> list[dict]:
        conn = await cls._get_connection()
        try:
            query = """
            SELECT 
                t.id, 
                t.module_name, 
                t.order_num, 
                t.status,
                t.last_executed
            FROM tasks t
            WHERE t.route_id = ?
            ORDER BY t.order_num
            """
            async with await conn.execute(query, (route_id,)) as cursor:
                return [dict(row) async for row in cursor]
        except aiosqlite.Error as e:
            log.error(f"Failed to get all tasks: {str(e)}")
            raise
        finally:
            await cls._release_connection(conn)
            
    @classmethod
    async def get_tasks_to_run(
        cls,
        route_id: int,
        always_run_modules: list[str]
    ) -> list[dict]:
        conn = await cls._get_connection()
        try:
            query = f"""
            SELECT 
                t.id, 
                t.module_name, 
                t.order_num, 
                t.status,
                t.last_executed
            FROM tasks t
            WHERE t.route_id = ?
            AND (
                (
                    t.status = 'pending'
                    AND NOT EXISTS (
                        SELECT 1 FROM task_dependencies 
                        WHERE task_id = t.id 
                        AND dependency_id NOT IN (
                            SELECT id FROM tasks WHERE status = 'success'
                        )
                    )
                )
                OR (
                    t.module_name IN ({','.join(['?']*len(always_run_modules))})
                    AND (
                        (t.module_name = 'faucet' AND (
                            datetime(t.last_executed, '+24 hours') < CURRENT_TIMESTAMP 
                            OR t.last_executed IS NULL
                        ))
                        OR
                        (t.module_name != 'faucet' AND (
                            datetime(t.last_executed, '+1 hour') < CURRENT_TIMESTAMP 
                            OR t.last_executed IS NULL
                        ))
                    )
                )
            )
            ORDER BY t.order_num
            """
            params = [route_id] + always_run_modules
            async with await conn.execute(query, params) as cursor:
                tasks = [dict(row) async for row in cursor]
                log.debug(f"Tasks to run for route {route_id}: {[task['module_name'] for task in tasks]}")
                return tasks
        finally:
            await cls._release_connection(conn)
            
    @classmethod
    async def get_task_id(cls, route_id: int, module_name: str) -> int | None:
        conn = await cls._get_connection()
        try:
            async with await conn.execute(
                "SELECT id FROM tasks WHERE route_id = ? AND module_name = ?",
                (route_id, module_name)
            ) as cursor:
                result = await cursor.fetchone()
                return result["id"] if result else None
        except aiosqlite.Error as e:
            log.error(f"Failed to get task ID for route {route_id} and module {module_name}: {str(e)}")
            return None
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def get_route_id(cls, account_id: int, route_name: str) -> str:
        conn = await cls._get_connection()
        try:
            async with await conn.execute(
                "SELECT address FROM accounts WHERE id = ?",
                (account_id,)
            ) as cursor:
                account = await cursor.fetchone()
                if not account:
                    raise DatabaseError(f"Account ID {account_id} not found")
                address = account["address"]
            
            async with await conn.execute(
                "SELECT id FROM routes WHERE id = ?",
                (address,)
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    raise RouteNotFoundError(f"Route not found for account ID {account_id}")
                return result["id"]
        except aiosqlite.Error as e:
            log.error(f"Failed to retrieve route ID for account {account_id}: {str(e)}")
            raise DatabaseError(f"Failed to retrieve route ID: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def update_route_status(cls, route_id: str) -> None:
        async with cls.transaction() as conn:
            try:
                async with await conn.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM tasks 
                        WHERE route_id = ? 
                        AND status = 'pending'
                    )""",
                    (route_id,)
                ) as cursor:
                    has_pending = (await cursor.fetchone())[0]
                if not has_pending:
                    await conn.execute(
                        "UPDATE routes SET status = 'completed' WHERE id = ?",
                        (route_id,)
                    )
                    log.info(f"Route {route_id} status updated to 'completed'")
            except aiosqlite.Error as e:
                log.error(f"Failed to update route {route_id} status: {str(e)}")
                raise DatabaseError(f"Failed to update route status: {str(e)}")

    @classmethod
    async def get_route_stats(cls) -> list[RouteStats]:
        conn = await cls._get_connection()
        try:
            async with await conn.execute("""
                WITH task_counts AS (
                    SELECT route_id,
                           SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success,
                           SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                           SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending
                    FROM tasks
                    GROUP BY route_id
                )
                SELECT r.id, r.route_name, a.private_key, r.status,
                       COALESCE(tc.success, 0) + COALESCE(tc.failed, 0) + COALESCE(tc.pending, 0) as total_tasks,
                       COALESCE(tc.success, 0) as success_tasks,
                       COALESCE(tc.failed, 0) as failed_tasks,
                       COALESCE(tc.pending, 0) as pending_tasks
                FROM routes r
                JOIN accounts a ON r.account_id = a.id
                LEFT JOIN task_counts tc ON r.id = tc.route_id
                ORDER BY r.id DESC
            """) as cursor:
                return [
                    RouteStats(
                        id=row["id"],
                        route_name=row["route_name"],
                        private_key=row["private_key"],
                        status=row["status"],
                        total_tasks=row["total_tasks"],
                        success_tasks=row["success_tasks"],
                        failed_tasks=row["failed_tasks"],
                        pending_tasks=row["pending_tasks"],
                    )
                    async for row in cursor
                ]
        except aiosqlite.Error as e:
            log.error(f"Failed to retrieve route statistics: {str(e)}")
            raise DatabaseError(f"Failed to retrieve route statistics: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def get_pending_tasks(
        cls,
        route_id: int,
        always_run_modules: list[str]
    ) -> list[dict]:
        conn = await cls._get_connection()
        try:
            query = f"""
            SELECT 
                t.id, 
                t.module_name, 
                t.order_num, 
                t.status,
                t.last_executed
            FROM tasks t
            WHERE t.route_id = ?
            AND (
                (
                    t.status = 'pending'
                    AND NOT EXISTS (
                        SELECT 1 FROM task_dependencies 
                        WHERE task_id = t.id 
                        AND dependency_id NOT IN (
                            SELECT id FROM tasks WHERE status = 'success'
                        )
                    )
                )
                OR (
                    t.module_name IN ({','.join(['?']*len(always_run_modules))})
                    AND (
                        (t.module_name = 'faucet' AND (
                            datetime(t.last_executed, '+24 hours') < CURRENT_TIMESTAMP 
                            OR t.last_executed IS NULL
                        ))
                        OR
                        (t.module_name != 'faucet' AND (
                            datetime(t.last_executed, '+1 hour') < CURRENT_TIMESTAMP 
                            OR t.last_executed IS NULL
                        ))
                    )
                )
            )
            ORDER BY t.order_num
            """
            params = [route_id] + always_run_modules
            async with await conn.execute(query, params) as cursor:
                return [dict(row) async for row in cursor]
        except aiosqlite.Error as e:
            log.error(f"Failed to get tasks: {str(e)}")
            raise
        finally:
            await cls._release_connection(conn)
        
    @classmethod
    async def update_task_status(cls, task_id: int, status: str, result: str | None = None, error: str | None = None) -> None:
        conn = await cls._get_connection()
        try:
            async with await conn.execute("SELECT EXISTS(SELECT 1 FROM tasks WHERE id = ?)", (task_id,)) as cursor:
                exists = (await cursor.fetchone())[0]
            if not exists:
                log.warning(f"Task with ID {task_id} does not exist. Skipping update.")
                return

            await conn.execute(
                """
                UPDATE tasks 
                SET 
                    status = ?, 
                    result = ?, 
                    error_message = ?, 
                    last_executed = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, result, error, task_id)
            )
            await conn.commit()
            log.info(f"Task {task_id} updated with status '{status}'")
        except aiosqlite.Error as e:
            log.error(f"Failed to update task {task_id} status: {str(e)}")
            raise DatabaseError(f"Failed to update task status: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def update_tasks_batch(cls, tasks: list[TaskUpdateModel]) -> None:
        async with cls.transaction() as conn:
            try:
                params = [(task.status, task.result, task.error, task.task_id) for task in tasks]
                await conn.executemany(
                    """
                    UPDATE tasks 
                    SET status = ?, 
                        result = ?, 
                        error_message = ?, 
                        last_executed = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    params
                )
                log.info(f"Updated status for {len(tasks)} tasks")
            except aiosqlite.Error as e:
                log.error(f"Failed to batch update tasks: {str(e)}")
                raise DatabaseError(f"Failed to batch update tasks: {str(e)}")

    @classmethod
    async def get_task_details(cls, task_id: int) -> dict:
        conn = await cls._get_connection()
        try:
            async with await conn.execute(
                "SELECT t.*, r.route_name, a.private_key FROM tasks t "
                "JOIN routes r ON t.route_id = r.id "
                "JOIN accounts a ON r.account_id = a.id WHERE t.id = ?",
                (task_id,)
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    raise DatabaseError(f"Task {task_id} not found")
                return dict(result)
        except aiosqlite.Error as e:
            log.error(f"Failed to retrieve details for task {task_id}: {str(e)}")
            raise DatabaseError(f"Failed to retrieve task details: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def get_tasks_by_account(cls, private_key: str) -> list[dict]:
        conn = await cls._get_connection()
        try:
            async with await conn.execute(
                "SELECT t.id, t.module_name, t.status, t.error_message, t.result, "
                "r.route_name FROM tasks t "
                "JOIN routes r ON t.route_id = r.id "
                "JOIN accounts a ON r.account_id = a.id WHERE a.private_key = ? "
                "ORDER BY r.route_name, t.order_num",
                (private_key,)
            ) as cursor:
                tasks = [dict(row) async for row in cursor]
                if not tasks:
                    log.info(f"No tasks found for account {mask_private_key(private_key)}")
                return tasks
        except aiosqlite.Error as e:
            log.error(f"Failed to retrieve tasks for account {mask_private_key(private_key)}: {str(e)}")
            raise DatabaseError(f"Failed to retrieve tasks: {str(e)}")
        finally:
            await cls._release_connection(conn)