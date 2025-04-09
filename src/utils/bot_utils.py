class AccountProgress:
    def __init__(self, total_accounts: int = 0):
        self.processed = 0
        self.total = total_accounts

    def increment(self):
        self.processed += 1

    def reset(self):
        self.processed = 0