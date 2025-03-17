from typing import Union
from logger import log

_SEPARATOR = "=" * 50


def show_trx_log(
    address: str,
    trx_type: str,
    status: bool,
    result: Union[str, dict, Exception],
    explorer_url: str = "Developer didn't specify explorer_url"
) -> None:
    status_icon = "✅" if status else "❌"
    status_text = "SUCCESS" if status else "FAILED"
    
    base = (
        f"\n{_SEPARATOR}\n"
        f"Transaction Type: {trx_type}\n"
        f"Status: {status_icon} {status_text}\n"
        f"Wallet: {address}\n"
    )

    if status:
        tx_hash = _normalize_hash(result)
        explorer_link = f"{explorer_url.rstrip('/')}/tx/{tx_hash}"
        log.success(f"{base}Explorer: {explorer_link}\n{_SEPARATOR}")
    else:
        error_msg = _get_error_message(result)
        log.error(f"{base}Message: {error_msg}\n{_SEPARATOR}")


def _normalize_hash(raw_hash: Union[str, dict, Exception]) -> str:
    hash_str = str(raw_hash)
    return hash_str if hash_str.startswith("0x") else f"0x{hash_str}"


def _get_error_message(error: Union[str, dict, Exception]) -> str:
    if isinstance(error, dict):
        return error.get("message", str(error))
    return str(error)