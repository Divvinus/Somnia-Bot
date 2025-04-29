class WalletError(Exception):
    """
    Base class for wallet-related errors.

    Used as a parent class for all wallet-related exceptions.
    """


class InsufficientFundsError(WalletError):
    """
    Exception for insufficient funds on the wallet.

    Occurs when the wallet balance is insufficient to complete the operation.
    """

class ConfigurationError(Exception):
    """
    Base class for configuration errors.

    Used for handling errors related to application settings.
    """