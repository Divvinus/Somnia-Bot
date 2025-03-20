from typing import Literal, TypedDict


ModuleType = Literal["register", "tasks", "stats"]
"""Type for supported module names in the application."""


class OperationResult(TypedDict):
    identifier: str
    data: str
    status: bool


class StatisticData(TypedDict):
    success: bool
    referralPoint: dict | None
    rewardPoint: dict | None