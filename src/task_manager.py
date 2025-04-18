from src.tasks import *
from bot_loader import config
from src.models import Account


class SomniaBot:
    @staticmethod
    async def process_faucet(account: Account) -> tuple[bool, str]:
        async with FaucetModule(account) as module:
            return await module.run()
    
    @staticmethod
    async def process_profile(account: Account) -> tuple[bool, str]:
        async with ProfileModule(account, config.referral_code) as module:
            return await module.run()

    @staticmethod
    async def process_account_statistics(account: Account) -> tuple[bool, str]:
        async with ProfileModule(account, config.referral_code) as module:
            return await module.get_account_statistics()

    @staticmethod
    async def process_get_referral_code(account: Account) -> tuple[bool, str]:
        async with SomniaClient(account) as module:
            return await module.get_referral_code()
        
    @staticmethod
    async def process_transfer_stt(account: Account) -> tuple[bool, str]:
        async with TransferSTTModule(account, config.somnia_rpc) as module:
            return await module.transfer_stt()

    @staticmethod
    async def process_mint_ping_pong(account: Account) -> tuple[bool, str]:
        async with MintPingPongModule(account, config.somnia_rpc) as module:
            return await module.run()

    @staticmethod
    async def process_swap_ping_pong(account: Account) -> tuple[bool, str]:
        async with SwapPingPongModule(account, config.somnia_rpc) as module:
            return await module.run()

    @staticmethod
    async def process_mint_usdt(account: Account) -> tuple[bool, str]:
        async with MintUsdtModule(account, config.somnia_rpc) as module:
            return await module.run()
        
    @staticmethod
    async def process_mint_message_nft(account: Account) -> tuple[bool, str]:
        async with QuillsMessageModule(account) as module:
            return await module.run()
    
    @staticmethod
    async def process_quest_socials(account: Account) -> tuple[bool, str]:
        async with QuestSocialsModule(account) as module:
            return await module.run()

    @staticmethod
    async def process_quest_sharing(account: Account) -> tuple[bool, str]:
        async with QuestSharingModule(account) as module:
            return await module.run()
    
    @staticmethod
    async def process_quest_darktable(account: Account) -> tuple[bool, str]:
        async with QuestDarktableModule(account) as module:
            return await module.run()
    
    @staticmethod
    async def process_quest_playground(account: Account) -> tuple[bool, str]:
        async with QuestPlaygroundModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_quest_demons(account: Account) -> tuple[bool, str]:
        async with QuestDemonsModule(account) as module:
            return await module.run()

    @staticmethod
    async def process_quest_gaming_frenzy(account: Account) -> tuple[bool, str]:
        async with QuestGamingFrenzyModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_quest_somnia_gaming_room(account: Account) -> tuple[bool, str]:
        async with QuestSomniaGamingRoomModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_quest_mullet(account: Account) -> tuple[bool, str]:
        async with QuestMulletCopModule(account) as module:
            return await module.run()

    @staticmethod
    async def process_mint_air(account: Account) -> tuple[bool, str]:
        async with MintairDeployContractModule(account) as module:
            return await module.run()

    @staticmethod
    async def process_onchain_gm(account: Account) -> tuple[bool, str]:
        async with OnchainGMModule(account) as module:
            return await module.run()

    @staticmethod
    async def process_yappers_nft(account: Account) -> tuple[bool, str]:
        async with YappersNFTModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_shannon_nft(account: Account) -> tuple[bool, str]:
        async with ShannonNFTModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_mint_domen(account: Account) -> tuple[bool, str]:
        async with MintDomenModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_nerzo_nft(account: Account) -> tuple[bool, str]:
        async with NerzoNFTModule(account) as module:
            return await module.run()