from core.modules import *
from loader import config
from models import Account


class SomniaBot:
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
    async def process_faucet(account: Account) -> tuple[bool, str]:
        async with FaucetModule(account) as module:
            return await module.run()

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
        async with SmapPingPongModule(account, config.somnia_rpc) as module:
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
    async def process_deploy_token_contract(account: Account) -> tuple[bool, str]:
        async with QuillsDeployContractModule(account) as module:
            return await module.run()
    
    @staticmethod
    async def process_quest_socials(account: Account) -> tuple[bool, str]:
        async with QuestSocialsModule(account) as module:
            return await module.run()

    @staticmethod
    async def process_quest_sharing(account: Account) -> tuple[bool, str]:
        async with QuestSharingModule(account) as module:
            return await module.run()