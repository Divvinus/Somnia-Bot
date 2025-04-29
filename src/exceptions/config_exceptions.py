class ConfigError(Exception):
    """Basic exception for all configuration errors"""
    
class MissingConfigError(ConfigError):
    """Error of missing mandatory parameter in the configuration"""
    
class TelegramConfigError(ConfigError):
    """Error in Telegram configuration"""