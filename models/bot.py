from typing import Literal, TypedDict


ModuleType = Literal["register", "tasks", "stats"]
"""Type for supported module names in the application."""


class OperationResult(TypedDict):
    """
    Represents the result of an operation.
    
    Attributes:
        identifier: Unique operation identifier
        data: Operation result data
        status: Operation success status
    """
    identifier: str
    data: str
    status: bool


class StatisticData(TypedDict):
    """
    Contains statistics and reward information.
    
    Attributes:
        success: Whether statistics were retrieved successfully
        referralPoint: Data about referral points (may be None)
        rewardPoint: Data about reward points (may be None)
    """
    success: bool
    referralPoint: dict | None
    rewardPoint: dict | None