from typing import Union
from src.logger import AsyncLogger


async def show_trx_log(
    address: str,
    trx_type: str,
    status: bool,
    result: Union[str, dict, Exception],
    explorer_url: str = "Developer didn't specify explorer_url"
) -> None:
    logger = AsyncLogger()
    
    if status:
        tx_hash = _normalize_hash(result)
        explorer_link = f"{explorer_url.rstrip('/')}/tx/{tx_hash}"
        await logger.logger_msg(
            f"Transaction Type: {trx_type}. Explorer: {explorer_link}",
            type_msg="success", address=address
        )
    else:
        error_msg = _get_error_message(result)
        await logger.logger_msg(
            f"Message: {error_msg}",
            type_msg="error", address=address
        )


def _normalize_hash(raw_hash: Union[str, dict, Exception]) -> str:
    hash_str = str(raw_hash)
    return hash_str if hash_str.startswith("0x") else f"0x{hash_str}"


def _get_error_message(error: Union[str, dict, Exception]) -> str:
    if isinstance(error, dict):
        return error.get("message", str(error))
    return str(error)