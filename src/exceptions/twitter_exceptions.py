class TwitterClientError(Exception):
    """Basic exception for all errors TwitterClient"""

class TwitterAuthError(TwitterClientError):
    """Twitter authorization error"""

class TwitterNetworkError(TwitterClientError):
    """Twitter network error"""

class TwitterInvalidTokenError(TwitterClientError):
    """Twitter invalid token error"""

class TwitterAccountSuspendedError(TwitterClientError):
    """Twitter account suspended error"""