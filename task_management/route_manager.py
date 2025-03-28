import random
import asyncio
from collections import defaultdict, deque

from task_management.database import Database, mask_private_key
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
    ]

    DEPENDENCIES: dict[str, list[str]] = {
        "profile": [],
        "faucet": ["profile"],
        "mint_ping_pong": ["faucet"],
        "swap_ping_pong": ["mint_ping_pong"],
        "transfer_stt": ["faucet"],
        "mint_usdt": ["faucet"],
        "mint_message_nft": ["faucet"],
        "deploy_token_contract": ["faucet"],
        "quest_socials": ["profile"],
        "quest_sharing": ["faucet"],
    }

    @staticmethod
    def _topological_sort(modules: list[str]) -> list[str]:
        graph: defaultdict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {module: 0 for module in modules}

        for module in modules:
            for dep in RouteManager.DEPENDENCIES.get(module, []):
                if dep in modules:
                    graph[dep].append(module)
                    in_degree[module] += 1

        queue: deque[str] = deque([module for module in modules if in_degree[module] == 0])
        sorted_modules: list[str] = []

        while queue:
            node = queue.popleft()
            sorted_modules.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_modules) != len(modules):
            raise ValueError("Cyclic dependency detected")

        return sorted_modules

    @staticmethod
    def generate_route_modules(shuffle: bool = True) -> list[str]:
        modules = RouteManager.DEFAULT_MODULES.copy()
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

        return ordered_modules

    @staticmethod
    async def create_route_for_account(
        account: Account, 
        route_name: str = "default", 
        shuffle: bool = True
    ) -> int:
        async with RouteManager._semaphore:
            address = get_address(account.private_key)
            route_name = route_name or f"route_{address[:8]}"

            try:
                account_id = await Database.get_account_id(account.private_key)
                if not account_id:
                    await Database.sync_accounts([account])
                    account_id = await Database.get_account_id(account.private_key)
                    if not account_id:
                        raise Exception("Failed to create account in database")

                modules = RouteManager.generate_route_modules(shuffle=shuffle)
                if not modules:
                    log.error("No modules available for route creation")
                    return 0

                route_id = await Database.create_route(
                    account_id=account_id,
                    route_name=route_name,
                    modules=modules,
                    dependencies=RouteManager.DEPENDENCIES,
                    always_run_modules=config.always_run_tasks.modules
                )
                log.success(f"Account: {address} | Route '{route_name}' created")
                return route_id
            except Exception as e:
                log.error(f"Failed to create route: {str(e)}")
                return 0
    
    @staticmethod
    async def create_routes_for_all_accounts(accounts: list[Account]) -> None:
        tasks = [
            RouteManager.create_route_for_account(account, shuffle=True)
            for account in accounts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for acc, res in zip(accounts, results):
            if isinstance(res, Exception):
                log.error(f"Failed for {get_address(acc.private_key)}: {str(res)}")

        # await RouteManager.print_detailed_routes()

    @staticmethod
    async def get_tasks_to_run(account: Account, route_name: str = "default") -> list[dict]:
        try:
            account_id = await Database.get_account_id(account.private_key)
            if not account_id:
                return []

            route_id = await Database.get_route_id(account_id, route_name)
            return await Database.get_tasks_to_run(route_id, config.always_run_tasks.modules)
        except Exception as e:
            log.error(f"Error getting tasks to run: {str(e)}")
            return []

    @staticmethod
    async def print_detailed_routes() -> None:
        try:
            routes = await Database.get_route_stats()
            if not routes:
                print("No routes found in database")
                return

            print("\nDetailed Routes:")
            print("-" * 120)
            for route in routes:
                tasks = await Database.get_all_tasks(route.id)
                masked_key = mask_private_key(route.private_key)

                print(
                    f"| ID: {route.id} | Route: {route.route_name} | Status: {route.status}\n"
                    f"| Private Key: {masked_key}\n"
                    f"| Tasks: {route.total_tasks} (✅{route.success_tasks} ❌{route.failed_tasks} ⏳{route.pending_tasks})\n"
                    f"| Modules:"
                )

                if tasks:
                    for task in tasks:
                        status_icon = {
                            "pending": "🟡",
                            "success": "🟢",
                            "failed": "🔴"
                        }.get(task["status"], "⚪")
                        print(
                            f"  - {status_icon} [{task['order_num']}] {task['module_name']} "
                            f"(Status: {task['status']})"
                        )
                else:
                    print("  No tasks found")

                print("-" * 120)
        except Exception as e:
            log.error(f"Failed to print routes: {str(e)}")