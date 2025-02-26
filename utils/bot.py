class AccountProgress:
    """
    Tracks progress of account processing operations.
    
    Args:
        total_accounts: Total number of accounts to process
    """
    def __init__(self, total_accounts: int = 0):
        self.processed = 0
        self.total = total_accounts

    def increment(self):
        """Increment the count of processed accounts by one."""
        self.processed += 1

    def reset(self):
        """Reset the processed accounts counter to zero."""
        self.processed = 0