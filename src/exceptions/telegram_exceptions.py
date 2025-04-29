class TelegramClientError(Exception):
    """Base exception for all TelegramClient errors"""

class TelegramAuthError(TelegramClientError):
    """Telegram authorization error"""

class TelegramNetworkError(TelegramClientError):
    """Telegram network error"""

class TelegramTimeoutError(TelegramClientError):
    """Telegram timeout error"""