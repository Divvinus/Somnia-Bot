from logger import log

def show_trx_log(address: str, trx_type: str, status: bool, result: str, explorer_url: str):
    """
    Display formatted transaction log with status and explorer link.
    
    Args:
        address: Wallet address
        trx_type: Type of transaction
        status: Success (True) or failure (False)
        result: Transaction hash or result message
        explorer_url: Base URL for blockchain explorer
    """
    status_icon = "✅" if status else "❌"
    
    explorer_link = f"{explorer_url}/tx/{result}" if isinstance(result, str) and result.startswith('0x') else None
    
    log_message = (
        f"\n{'=' * 50}\n"
        f"Transaction Type: {trx_type}\n"
        f"Status: {status_icon} {'SUCCESS' if status else 'FAILED'}\n"
        f"Wallet: {address}\n"
        f"{f'Explorer: {explorer_link}' if explorer_link else f'Message: {result}'}\n"
        f"{'=' * 50}"
    )

    if status:
        log.success(log_message)
    else:
        log.error(log_message)