from dataclasses import dataclass

@dataclass
class AccountModel:
    private_key: str
    address: str | None = None

@dataclass
class TaskUpdateModel:
    task_id: int
    status: str
    result: str | None = None
    error: str | None = None

@dataclass
class RouteStats:
    id: str
    route_name: str
    private_key: str
    status: str
    total_tasks: int
    success_tasks: int
    failed_tasks: int
    pending_tasks: int

@dataclass
class AccountStatistics:
    address: str
    private_key: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    pending_tasks: int
    percentage_completed: float
    task_details: list[dict]

@dataclass
class ModuleErrorStat:
    module_name: str
    error_count: int
    accounts_affected: list[str]

@dataclass
class SummaryStatistics:
    total_accounts: int
    success_percentage: float
    failed_percentage: float
    pending_percentage: float
    error_modules: list[ModuleErrorStat]