import asyncio
import random
from collections import defaultdict, deque

from db import Database
from loader import config
from logger import log
from models import Account
from utils import get_address


class RouteManager:
    _semaphore = asyncio.Semaphore(config.threads)

    DEFAULT_MODULES: list[str] = [
        "profile",
        "faucet",
        "transfer_stt",
        "mint_ping_pong",
        "swap_ping_pong",
        "mint_usdt",
        "mint_message_nft",
        "deploy_token_contract",
        "quest_socials",
        "quest_sharing",
        "quest_darktable",
    ]

    DEPENDENCIES: dict[str, list[str]] = {
        "profile": [],
        "faucet": [],
        "mint_ping_pong": ["faucet"],
        "swap_ping_pong": ["mint_ping_pong"],
        "transfer_stt": ["faucet"],
        "mint_usdt": ["faucet"],
        "mint_message_nft": ["faucet"],
        "deploy_token_contract": ["faucet"],
        "quest_socials": ["profile"],
        "quest_sharing": ["faucet"],
        "quest_darktable": ["profile"],
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
            log.error("Cyclic dependency detected")
            return []

        ordered_modules: list[str] = []
        if shuffle:
            for lvl in levels:
                random.shuffle(levels[lvl])
                ordered_modules.extend(levels[lvl])
        else:
            for lvl in levels:
                ordered_modules.extend(levels[lvl])

        # Проверяем, что нет дубликатов в результате
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
                log.error(f"No modules available for route creation for {address}")
                return ""
            await Database.create_route(
                private_key=account.private_key,
                route_name=route_name,
                modules=modules
            )
            log.success(f"Account: {address} | Route created successfully")
            return address
        except Exception as e:
            log.error(f"Failed to create route for {address}: {str(e)}")
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
                    log.error(f"Failed for {get_address(account.private_key)}: {str(e)}")

        await asyncio.gather(*(create_route_task(account) for account in accounts))