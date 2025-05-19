from src.tasks import *
from bot_loader import config
from src.models import Account
from src.logger import AsyncLogger
from src.utils import get_address

logger = AsyncLogger()

class SomniaBot:
    # === Base operations with account ===
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
        wallet_address = get_address(account.private_key)
        async with ProfileModule(account, config.referral_code) as module:
            await logger.logger_msg("Requesting statistics on accounts...", type_msg="info", address=wallet_address)
            status, result = await module.get_account_statistics()
            if status:
                await logger.logger_msg(f"{result}", type_msg="success", address=wallet_address)
                return True, result
            else:
                await logger.logger_msg(
                    f"Failed to get account statistics: {result}", type_msg="error", 
                    address=wallet_address, method_name="process_account_statistics"
                )
                return False, result

    @staticmethod
    async def process_get_referral_code(account: Account) -> tuple[bool, str]:
        wallet_address = get_address(account.private_key)
        async with SomniaClient(account) as module:
            await logger.logger_msg("Requesting referral code...", type_msg="info", address=wallet_address)
            referral_code = await module.get_referral_code()
            if referral_code:
                await logger.logger_msg(f"Referral code: {referral_code}", type_msg="success", address=wallet_address)
                return True, referral_code
            else:
                await logger.logger_msg("Failed to get referral code", type_msg="error", address=wallet_address, method_name="process_get_referral_code")
                return False, "Failed to get referral code"
            
    @staticmethod
    async def process_check_native_balance(account: Account) -> tuple[bool, str]:
        async with CheckNativeBalanceModule(account, config.somnia_rpc) as module:
            return await module.check_native_balance()
        
    @staticmethod
    async def process_daily_gm(account: Account) -> tuple[bool, str]:
        async with GmModule(account) as module:
            return await module.run()

    # === Minting tokens and Messages operations ===
    @staticmethod
    async def process_mint_ping_pong(account: Account) -> tuple[bool, str]:
        async with MintPingPongModule(account, config.somnia_rpc) as module:
            return await module.run()
    
    @staticmethod
    async def process_mint_usdt(account: Account) -> tuple[bool, str]:
        async with MintUsdtModule(account, config.somnia_rpc) as module:
            return await module.run()
    
    @staticmethod
    async def process_mint_message_nft(account: Account) -> tuple[bool, str]:
        async with QuillsMessageModule(account) as module:
            return await module.run()   

    # === NFT operations ===
    @staticmethod
    async def process_yappers_nft(account: Account) -> tuple[bool, str]:
        async with YappersNFTModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_shannon_nft(account: Account) -> tuple[bool, str]:
        async with ShannonNFTModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_nerzo_nft(account: Account) -> tuple[bool, str]:
        async with NerzoNFTModule(account) as module:
            return await module.run()
    
    @staticmethod
    async def process_somni_nft(account: Account) -> tuple[bool, str]:
        async with SomniNFTModule(account) as module:
            return await module.run()
        
    # === Onchain operations ===
    @staticmethod
    async def process_onchain_gm(account: Account) -> tuple[bool, str]:
        async with OnchainGMModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_swap_ping_pong(account: Account) -> tuple[bool, str]:
        async with SwapPingPongModule(account, config.somnia_rpc) as module:
            return await module.run()
        
    @staticmethod
    async def process_transfer_stt(account: Account) -> tuple[bool, str]:
        async with TransferSTTModule(account, config.somnia_rpc) as module:
            return await module.transfer_stt()
        
    @staticmethod
    async def process_mint_domen(account: Account) -> tuple[bool, str]:
        async with MintDomenModule(account) as module:
            return await module.run()
        
    @staticmethod
    async def process_mint_air(account: Account) -> tuple[bool, str]:
        async with MintairDeployContractModule(account) as module:
            return await module.run()

    # === Quests ===