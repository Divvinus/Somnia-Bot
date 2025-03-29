from datetime import datetime

from core.modules import *
from loader import config
from models import Account
from task_management.database import Database
from utils.utils import get_address
from logger import log

class SomniaBot:
    @staticmethod
    async def process_faucet(account: Account) -> tuple[bool, str]:
        address = get_address(account.private_key)
        route_id = await Database.get_route_id(
            await Database.get_account_id(account.private_key), "default"
        )
        task_id = await Database.get_task_id(route_id, "faucet")
        
        conn = await Database._get_connection()
        try:
            async with await conn.execute(
                "SELECT last_executed FROM tasks WHERE id = ?", (task_id,)
            ) as cursor:
                result = await cursor.fetchone()
                last_executed = result["last_executed"] if result else None
        finally:
            await Database._release_connection(conn)
        
        current_time = datetime.now()
        if last_executed:
            last_executed_dt = datetime.strptime(last_executed, "%Y-%m-%d %H:%M:%S.%f")
            if (current_time - last_executed_dt).total_seconds() < 24 * 3600:
                log.info(f"Faucet skipped for {address}: less than 24 hours since last execution")
                await Database.update_task_status(
                    task_id,
                    "success",
                    result="Faucet skipped due to time interval"
                )
                return True, "Faucet skipped due to time interval"

        async with FaucetModule(account) as module:
            success, message = await module.run()
        
        await Database.update_task_status(
            task_id,
            "success" if success else "failed",
            result=message if success else None,
            error=message if not success else None
        )
        
        if not success:
            log.error(f"Faucet failed for {address}: {message}")
            return False, message
        
        log.success(f"Faucet executed for {address}: {message}")
        return True, message
    
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