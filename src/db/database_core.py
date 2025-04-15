import asyncio
import os
from asyncio import Queue as AsyncQueue
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from aiocache import cached

import aiosqlite

from src.db.exceptions import DatabaseError
from src.db.models import AccountModel
from bot_loader import config
from src.logger import AsyncLogger
from src.utils import get_address

logger = AsyncLogger()

@cached()
async def get_database_path() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(script_dir))
    data_dir = os.path.join(root_dir, "data_bd")
    db_path = os.path.join(data_dir, "database.db")
    return db_path

@cached()
async def get_and_ensure_database_path() -> str:
    """Get database path and ensure the directory exists"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(script_dir))
    data_dir = os.path.join(root_dir, "data_bd")
    db_path = os.path.join(data_dir, "database.db")
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
            await logger.logger_msg(
                msg=f"Directory ready: {data_dir}", type_msg="info"
            )
        except PermissionError as e:
            await logger.logger_msg(
                msg=f"Permission error: {str(e)}", type_msg="error", 
                method_name="get_and_ensure_database_path"
            )
            raise
        except OSError as e:
            await logger.logger_msg(
                msg=f"Directory creation failed: {str(e)}", type_msg="error", 
                method_name="get_and_ensure_database_path"
            )
            raise
    return db_path

class Database:    
    _db_write_semaphore = asyncio.Semaphore(1)
    _connection_pool: AsyncQueue[aiosqlite.Connection] = AsyncQueue(maxsize=config.threads)
    _pool_semaphore = asyncio.Semaphore(config.threads)
    _max_connections = config.threads
    _lock = asyncio.Lock()

    @classmethod
    async def _create_connection(cls) -> aiosqlite.Connection:
        db_path = await get_database_path()
        
        if not os.path.exists(os.path.dirname(db_path)):
            raise DatabaseError("Database directory does not exist. Please create routes first.")
        
        try:
            conn = await aiosqlite.connect(
                database=db_path,
                timeout=30.0,
                isolation_level=None
            )
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute("PRAGMA busy_timeout = 10000")
            await conn.execute("PRAGMA foreign_keys = ON")
            await logger.logger_msg(
                msg=f"New database connection created to {db_path}", type_msg="debug", 
                class_name=cls.__name__, method_name="_create_connection"
            )
            return conn
        except aiosqlite.Error as e:
            await logger.logger_msg(
                msg=f"Failed to create database connection: {str(e)}", 
                type_msg="error", class_name=cls.__name__, method_name="_create_connection"
            )
            raise ConnectionError(f"Database connection creation failed: {str(e)}")
        
    @classmethod
    async def _get_connection(cls) -> aiosqlite.Connection:
        async with cls._pool_semaphore:
            try:
                if not cls._connection_pool.empty():
                    return await cls._connection_pool.get()
                conn = await cls._create_connection()
                await conn.execute("PRAGMA busy_timeout = 30000")
                return conn
            except Exception as e:
                await logger.logger_msg(
                    msg=f"Error getting connection: {str(e)}", type_msg="error", 
                    class_name=cls.__name__, method_name="_get_connection"
                )
                return await cls._create_connection()

    @classmethod
    async def _release_connection(cls, conn: aiosqlite.Connection) -> None:
        if cls._connection_pool.qsize() < cls._connection_pool.maxsize:
            await cls._connection_pool.put(conn)
        else:
            await conn.close()

    @classmethod
    async def init_db(cls) -> None:
        db_path = await get_and_ensure_database_path()
        conn = await cls._get_connection()
        try:
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    private_key TEXT UNIQUE NOT NULL,
                    address TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS routes (
                    name TEXT PRIMARY KEY,
                    route TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (name) REFERENCES accounts(address) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS statistics_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    module_name TEXT NOT NULL,
                    error_message TEXT,
                    result_message TEXT,
                    status TEXT DEFAULT 'pending',
                    last_executed TIMESTAMP,
                    UNIQUE(name, module_name),
                    FOREIGN KEY (name) REFERENCES accounts(address) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS statistics_account (
                    name TEXT PRIMARY KEY,
                    percentage_completed REAL DEFAULT 0.0,
                    pending_tasks TEXT DEFAULT '[]',
                    FOREIGN KEY (name) REFERENCES accounts(address) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_statistics_tasks_name ON statistics_tasks(name);
                CREATE INDEX IF NOT EXISTS idx_statistics_tasks_status ON statistics_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_statistics_tasks_module ON statistics_tasks(module_name);
                CREATE INDEX IF NOT EXISTS idx_statistics_tasks_last_executed ON statistics_tasks(last_executed);
            """)
            try:
                await conn.execute("ALTER TABLE statistics_tasks ADD COLUMN error_count INTEGER DEFAULT 0")
            except aiosqlite.OperationalError:
                pass
            await logger.logger_msg(
                msg="The database is initialized with a new table structure", type_msg="info", 
                class_name=cls.__name__
            )
        except aiosqlite.Error as e:
            await logger.logger_msg(
                msg=f"Failed to initialize the database schema: {str(e)}", 
                type_msg="error", class_name=cls.__name__, method_name="init_db"
            )
            raise DatabaseError(f"Database initialization error: {str(e)}")

        finally:
            await cls._release_connection(conn)

    @classmethod
    async def close_pool(cls) -> None:
        while not cls._connection_pool.empty():
            try:
                conn = await cls._connection_pool.get()
                await conn.close()
                await logger.logger_msg(
                    msg="Connection closed", type_msg="debug", 
                    class_name=cls.__name__, method_name="close_pool"
                )
            except aiosqlite.Error as e:
                await logger.logger_msg(
                    msg=f"Error closing connection: {str(e)}", type_msg="error", 
                    class_name=cls.__name__, method_name="close_pool"
                )
        await logger.logger_msg(msg="Connection pool cleared", type_msg="info", 
            class_name=cls.__name__
        )

    @classmethod
    @asynccontextmanager
    async def transaction(cls) -> AsyncIterator[aiosqlite.Connection]:
        conn = await cls._get_connection()
        try:
            await conn.execute("BEGIN")
            yield conn
            await conn.execute("COMMIT")
        except Exception as e:
            try:
                await conn.execute("ROLLBACK")
            except Exception as rollback_error:
                await logger.logger_msg(
                    msg=f"Error during rollback: {str(rollback_error)}", type_msg="error", 
                    class_name=cls.__name__, method_name="transaction"
                )
            await logger.logger_msg(
                msg=f"Transaction rolled back due to: {str(e)}", type_msg="error", 
                class_name=cls.__name__, method_name="transaction"
            )
            raise DatabaseError(f"Transaction failed: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def sync_accounts(cls, accounts: list[AccountModel]) -> None:
        async with cls._db_write_semaphore:
            async with cls.transaction() as conn:
                try:
                    cursor = await conn.execute("SELECT private_key FROM accounts")
                    existing_keys = {row[0] for row in await cursor.fetchall()}
                except aiosqlite.Error as e:
                    await logger.logger_msg(
                        msg=f"Failed to get existing keys: {str(e)}", type_msg="error", 
                        class_name=cls.__name__, method_name="sync_accounts"
                    )
                    raise DatabaseError(f"Error getting keys: {str(e)}")

                updates = []
                inserts = []
                for account in accounts:
                    try:
                        address = get_address(account.private_key)
                    except Exception as e:
                        await logger.logger_msg(
                            msg=f"Error in get_address for key {account.private_key}: {str(e)}", 
                            type_msg="error", class_name=cls.__name__, method_name="sync_accounts"
                        )
                        raise DatabaseError(f"Error in get_address: {str(e)}")

                    if account.private_key in existing_keys:
                        updates.append((address, account.private_key))
                    else:
                        inserts.append((account.private_key, address))

                if updates:
                    try:
                        await conn.executemany(
                            "UPDATE accounts SET address = ? WHERE private_key = ?",
                            updates
                        )
                    except aiosqlite.Error as e:
                        await logger.logger_msg(
                            msg=f"Failed to update records: {str(e)}", type_msg="error", 
                            class_name=cls.__name__, method_name="sync_accounts"
                        )
                        raise DatabaseError(f"Error updating records: {str(e)}")

                if inserts:
                    try:
                        await conn.executemany(
                            "INSERT INTO accounts (private_key, address) VALUES (?, ?)",
                            inserts
                        )
                    except aiosqlite.Error as e:
                        await logger.logger_msg(
                            msg=f"Failed to insert new records: {str(e)}", type_msg="error", 
                            class_name=cls.__name__, method_name="sync_accounts"
                        )
                        raise DatabaseError(f"Error inserting records: {str(e)}")

    @classmethod
    async def get_db_path(cls) -> str:
        return await get_database_path()