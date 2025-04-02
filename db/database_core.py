import asyncio
import os
from asyncio import Queue as AsyncQueue
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cache

import aiosqlite

from db.exceptions import DatabaseError
from db.models import AccountModel
from loader import config
from logger import log
from utils import get_address


@cache
def get_database_path() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data_bd")
    db_path = os.path.join(data_dir, "database.db")
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
            log.info(f"Directory ready: {data_dir}")
        except PermissionError as e:
            log.error(f"Permission error: {str(e)}")
            raise
        except OSError as e:
            log.error(f"Directory creation failed: {str(e)}")
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
        db_path = get_database_path()
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
            log.debug(f"New database connection created to {db_path}")
            return conn
        except aiosqlite.Error as e:
            log.error(f"Failed to create database connection: {str(e)}")
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
                log.error(f"Error getting connection: {str(e)}")
                await asyncio.sleep(1)
                return await cls._create_connection()

    @classmethod
    async def _release_connection(cls, conn: aiosqlite.Connection) -> None:
        if cls._connection_pool.qsize() < cls._connection_pool.maxsize:
            await cls._connection_pool.put(conn)
        else:
            await conn.close()

    @classmethod
    async def init_db(cls) -> None:
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
            log.info("The database is initialized with a new table structure")
        except aiosqlite.Error as e:
            log.error(f"Failed to initialize the database schema: {str(e)}")
            raise DatabaseError(f"Database initialization error: {str(e)}")
        finally:
            await cls._release_connection(conn)

    @classmethod
    async def close_pool(cls) -> None:
        while not cls._connection_pool.empty():
            try:
                conn = await cls._connection_pool.get()
                await conn.close()
                log.debug("Connection closed")
            except aiosqlite.Error as e:
                log.error(f"Error closing connection: {str(e)}")
        log.info("Connection pool cleared")

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
                log.error(f"Error during rollback: {str(rollback_error)}")
            log.error(f"Transaction rolled back due to: {str(e)}")
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
                    log.error(f"Failed to get existing keys: {str(e)}")
                    raise DatabaseError(f"Error getting keys: {str(e)}")

                updates = []
                inserts = []
                for account in accounts:
                    try:
                        address = get_address(account.private_key)
                    except Exception as e:
                        log.error(f"Error in get_address for key {account.private_key}: {str(e)}")
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
                        log.error(f"Failed to update records: {str(e)}")
                        raise DatabaseError(f"Error updating records: {str(e)}")

                if inserts:
                    try:
                        await conn.executemany(
                            "INSERT INTO accounts (private_key, address) VALUES (?, ?)",
                            inserts
                        )
                    except aiosqlite.Error as e:
                        log.error(f"Failed to insert new records: {str(e)}")
                        raise DatabaseError(f"Error inserting records: {str(e)}")