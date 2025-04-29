class DiscordClientError(Exception):
    """Basic exception for all errors DiscordClient"""

class DiscordAuthError(DiscordClientError):
    """Discord authorization error"""

class DiscordNetworkError(DiscordClientError):
    """Discord network error"""

class DiscordInvalidTokenError(DiscordClientError):
    """Discord invalid token error"""

class DiscordRateLimitError(DiscordClientError):
    """Discord rate limit error"""

class DiscordServerError(DiscordClientError):
    """Discord server-side error""" 