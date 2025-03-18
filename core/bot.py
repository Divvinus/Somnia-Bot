from core.modules import *
from loader import config
from models import Account

class SomniaBot:
    
    @staticmethod
    async def process_get_referral_code(account: Account) -> tuple[bool, str]:
        async with SomniaClient(account) as module:
                return await module.get_referral_code()

    @staticmethod
    async def process_account_statistics(account: Account) -> tuple[bool, str]:
        async with ProfileModule(account, config.referral_code) as module:
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
        async with ProfileModule(account, config.referral_code) as module:
            return await module.run()
    
    @staticmethod
    async def process_faucet(account: Account) -> tuple[bool, str]:
        async with FaucetModule(account) as module:
            return await module.faucet()    
    
    @staticmethod
    async def process_transfer_stt(account: Account) -> tuple[bool, str]:
        async with TransferSTTModule(account, config.somnia_rpc) as module:
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
    
    @staticmethod
    async def process_mint_ping_pong(account: Account) -> tuple[bool, str]:    
        async with MintPingPongModule(account, config.somnia_rpc) as module:
            return await module.run()
    
    @staticmethod
    async def process_swap_ping_pong(account: Account) -> tuple[bool, str]:    
        async with SmapPingPongModule(account, config.somnia_rpc) as module:
            return await module.run()
        
    @staticmethod
    async def process_faucet_usdt(account: Account) -> tuple[bool, str]:    
        async with FaucetUsdtModule(account, config.somnia_rpc) as module:
            return await module.run()
    