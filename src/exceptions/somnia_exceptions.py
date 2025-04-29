class SomniaClientError(Exception):
    """Base exception for all Somnia API client errors"""

class SomniaAuthError(SomniaClientError):
    """Error during Somnia authentication"""

class SomniaOnboardingError(SomniaClientError):
    """Error during Somnia onboarding process"""

class SomniaAPIError(SomniaClientError):
    """Error during Somnia API request"""
    def __init__(self, message: str, response_data=None):
        super().__init__(message)
        self.response_data = response_data

class SomniaReferralError(SomniaClientError):
    """Error during referral code operations"""

class SomniaServerError(SomniaAPIError):
    """Somnia server returned an error"""

class SomniaRateLimitError(SomniaAPIError):
    """Somnia API rate limit exceeded"""

class SomniaStatsError(SomniaClientError):
    """Error when retrieving Somnia stats""" 