import asyncio
import random
from collections import defaultdict, deque
import orjson
import os

from src.db import Database
from bot_loader import config
from src.logger import AsyncLogger
from src.models import Account
from src.utils import get_address
from src.db.database_core import get_database_path


class RouteManager:
    _semaphore = asyncio.Semaphore(config.threads)
    logger = AsyncLogger()

    DEFAULT_MODULES: list[str] = [
        "profile",
        "faucet",
        "transfer_stt",
        "mint_ping_pong",
        "swap_ping_pong",
        "mint_usdt",
        "mint_message_nft",
        "mint_air",
        "onchain_gm",
        "shannon_nft",
        "yappers_nft",
        "mint_domen",
        "nerzo_nft",
        "somni_nft",
        "daily_gm",
        "quest_yapper",
        "community_nft",
        "somnia_domain"
    ]

    DEPENDENCIES: dict[str, list[str]] = {
        "profile": [],
        "faucet": [],
        "mint_ping_pong": ["faucet"],
        "swap_ping_pong": ["mint_ping_pong"],
        "transfer_stt": ["faucet"],
        "mint_usdt": ["faucet"],
        "mint_message_nft": ["faucet"],
        "mint_air": ["faucet"],
        "onchain_gm": ["faucet"],
        "shannon_nft": ["faucet"],
        "yappers_nft": ["faucet"],
        "mint_domen": ["faucet"],
        "nerzo_nft": ["faucet"],
        "somni_nft": ["faucet"],
        "daily_gm": ["profile"],
        "quest_yapper": ["profile"],
        "community_nft": ["faucet"],
        "somnia_domain": ["faucet"]
    }
    
    @staticmethod
    async def _topological_sort(modules: list[str]) -> list[str]:
        dependencies = RouteManager.DEPENDENCIES
        graph = {m: [] for m in modules}
        in_degrees = {m: 0 for m in modules}

        for module in modules:
            for dep in dependencies.get(module, []):
                if dep in modules:
                    graph[dep].append(module)
                    in_degrees[module] += 1

        queue = deque(m for m in modules if in_degrees[m] == 0)
        sorted_modules = []

        while queue:
            node = queue.popleft()
            sorted_modules.append(node)
            for neighbor in graph[node]:
                in_degrees[neighbor] -= 1
                if in_degrees[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_modules) != len(modules):
            raise ValueError("Cyclic dependency detected")

        return sorted_modules
    
    @staticmethod
    async def generate_route_modules(shuffle: bool = True) -> list[str]:
        modules = list(dict.fromkeys(RouteManager.DEFAULT_MODULES))
        graph: defaultdict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {module: 0 for module in modules}

        for module in modules:
            for dep in RouteManager.DEPENDENCIES.get(module, []):
                if dep in modules:
                    graph[dep].append(module)
                    in_degree[module] += 1

        queue: deque[str] = deque([module for module in modules if in_degree[module] == 0])
        levels: defaultdict[int, list[str]] = defaultdict(list)
        level = 0

        while queue:
            level_size = len(queue)
            for _ in range(level_size):
                node = queue.popleft()
                levels[level].append(node)
                for neighbor in graph[node]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            level += 1

        if sum(len(tasks) for tasks in levels.values()) != len(modules):
            await RouteManager.logger.logger_msg(
                msg="Cyclic dependency detected", type_msg="error", 
                method_name="generate_route_modules"
            )
            return []

        ordered_modules: list[str] = []
        if shuffle:
            for lvl in levels:
                random.shuffle(levels[lvl])
                ordered_modules.extend(levels[lvl])
        else:
            for lvl in levels:
                ordered_modules.extend(levels[lvl])

        return list(dict.fromkeys(ordered_modules))
    
    @staticmethod
    async def create_route_for_account(
        account: Account, 
        route_name: str = None, 
        shuffle: bool = True
    ) -> str:
        address = get_address(account.private_key)
        route_name = route_name or address

        try:
            await Database.sync_accounts([account])
            modules = await RouteManager.generate_route_modules(shuffle=shuffle)
            if not modules:
                await RouteManager.logger.logger_msg(
                    msg=f"No modules available for route creation", type_msg="error", 
                    address=address, method_name="create_route_for_account"
                )
                return ""
            await Database.create_route(
                private_key=account.private_key,
                route_name=route_name,
                modules=modules
            )
            await RouteManager.logger.logger_msg(
                msg=f"Route created successfully", type_msg="success", address=address
            )
            return address
        except Exception as e:
            await RouteManager.logger.logger_msg(
                msg=f"Failed to create route: {str(e)}", type_msg="error", 
                address=address, method_name="create_route_for_account"
            )
            return ""
        
    @staticmethod
    async def create_routes_for_all_accounts(accounts: list[Account]) -> None:
        async def create_route_task(account: Account) -> None:
            async with RouteManager._semaphore:
                try:
                    await RouteManager.create_route_for_account(
                        account,
                        route_name=get_address(account.private_key),
                        shuffle=True
                    )
                except Exception as e:
                    await RouteManager.logger.logger_msg(
                        msg=f"Failed: {str(e)}", 
                        type_msg="error", address=get_address(account.private_key), 
                        method_name="create_routes_for_all_accounts"
                    )

        await asyncio.gather(*(create_route_task(account) for account in accounts))

    @staticmethod
    async def update_routes_with_new_modules() -> None:
        try:
            db_path = await get_database_path()
            
            if not os.path.exists(db_path):
                await RouteManager.logger.logger_msg(
                    msg="Database file not found. Please create routes using 'Generate routes'", 
                    type_msg="warning", 
                    method_name="update_routes_with_new_modules"
                )
                return
            
            conn = await Database._get_connection()
            try:
                try:
                    cursor = await conn.execute("SELECT name, route FROM routes")
                    routes = await cursor.fetchall()
                except Exception as e:
                    if "no such table" in str(e):
                        await RouteManager.logger.logger_msg(
                            msg="Database not initialized. Please create routes using 'Generate routes'", 
                            type_msg="warning", 
                            method_name="update_routes_with_new_modules"
                        )
                        return
                    raise
            finally:
                await Database._release_connection(conn)
            
            if not routes:
                await RouteManager.logger.logger_msg(
                    msg="No existing routes found to update", 
                    type_msg="warning", 
                    method_name="update_routes_with_new_modules"
                )
                return
            
            updated_count = 0
            for route in routes:
                route_name = route["name"]
                existing_modules = orjson.loads(route["route"])
                
                new_modules = [m for m in RouteManager.DEFAULT_MODULES if m not in existing_modules]
                
                if new_modules:
                    updated_modules = list(dict.fromkeys(existing_modules + new_modules))
                    
                    account_conn = await Database._get_connection()
                    try:
                        cursor = await account_conn.execute(
                            "SELECT private_key FROM accounts WHERE address = ?", 
                            (route_name,)
                        )
                        account_row = await cursor.fetchone()
                        if not account_row:
                            await RouteManager.logger.logger_msg(
                                msg=f"Cannot find account for route: {route_name}", 
                                type_msg="warning", 
                                method_name="update_routes_with_new_modules"
                            )
                            continue
                        
                        private_key = account_row["private_key"]
                    finally:
                        await Database._release_connection(account_conn)
                    
                    await Database.create_route(
                        private_key=private_key,
                        route_name=route_name,
                        modules=updated_modules,
                        preserve_status=True
                    )
                    updated_count += 1
                    
                    await RouteManager.logger.logger_msg(
                        msg=f"Added {len(new_modules)} new modules to route", 
                        type_msg="success", 
                        address=route_name
                    )
            
            await RouteManager.logger.logger_msg(
                msg=f"Updated {updated_count} routes with new modules", 
                type_msg="info", 
                method_name="update_routes_with_new_modules"
            )
        except Exception as e:
            await RouteManager.logger.logger_msg(
                msg=f"Failed to update routes with new modules: {str(e)}", 
                type_msg="error", 
                method_name="update_routes_with_new_modules"
            )