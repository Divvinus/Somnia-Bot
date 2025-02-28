from core.modules import *
from loader import config
from models import Account

class SomniaBot:
    """
    Bot for interacting with Somnia platform features.
    
    Provides static methods to process various account operations.
    """
    
    @staticmethod
    async def process_get_referral_code(account: Account) -> tuple[bool, str]:
        """
        Get referral code for the account.
        """
        module = SomniaClient(account)
        return await module.get_referral_code()

    @staticmethod
    async def process_account_statistics(account: Account) -> tuple[bool, str]:
        """
        Retrieve account statistics from Somnia.
        
        Args:
            account: User account credentials
            
        Returns:
            Tuple of (success_status, result_message)
        """
        module = ProfileModule(account, config.referral_code)
        return await module.get_account_statistics()
    
    @staticmethod
    async def process_recruiting_referrals(account: Account) -> tuple[bool, str]:
        """
        Process referral recruiting operations.
        
        Args:
            account: User account credentials
            
        Returns:
            Tuple of (success_status, result_message)
        """
        module = RecruitingReferralsModule(account)
        await module.recruiting_referrals()
        return True
    
    @staticmethod
    async def process_profile(account: Account) -> tuple[bool, str]:
        """
        Process profile setup and configuration.
        
        Args:
            account: User account credentials
            
        Returns:
            Tuple of (success_status, result_message)
        """
        module = ProfileModule(account, config.referral_code)
        return await module.run()
    
    @staticmethod
    async def process_faucet(account: Account) -> tuple[bool, str]:
        """
        Claim tokens from Somnia faucet.
        
        Args:
            account: User account credentials
            
        Returns:
            Tuple of (success_status, result_message)
        """
        module = FaucetModule(account)
        return await module.faucet()
    
    
    @staticmethod
    async def process_transfer_stt(account: Account) -> tuple[bool, str]:
        """
        Transfer STT tokens to another address.
        
        Args:
            account: User account credentials
            
        Returns:
            Tuple of (success_status, result_message)
        """
        module = TransferSTTModule(account, config.somnia_rpc)
        return await module.transfer_stt()
    
    @staticmethod
    async def process_socials_quests_1(account: Account) -> tuple[bool, str]:
        """
        Complete social media quests (set 1).
        
        Args:
            account: User account credentials
            
        Returns:
            Tuple of (success_status, result_message)
        """
        module = SocialsQuest1Module(account)
        return await module.run()
    
    @staticmethod
    async def process_socials_quests_2(account: Account) -> tuple[bool, str]:
        """
        Complete social media quests (set 2).
        """
        module = SocialsQuest2Module(account)
        return await module.run()
