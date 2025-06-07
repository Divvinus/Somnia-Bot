from abc import ABC
from dataclasses import dataclass
from typing import Any, Self

from config.settings import sleep_between_tasks
from src.api import SomniaClient
from .profile import ProfileModule
from .quickswap import QuickSwapModule
from src.logger import AsyncLogger
from src.models import Account
from src.utils import random_sleep, TwitterWorker


@dataclass
class QuestConfig:
    campaign_id: int
    quest_handlers: dict[int, str]
    
async def process_swap(account: Account) -> tuple[bool, str]:
    async with QuickSwapModule(account) as swap:
        return await swap.run_quick_swap(pair_swap={1: ["STT", "USDC", 25]})
    
async def process_pool(account: Account) -> tuple[bool, str]:
    async with QuickSwapModule(account) as pool:
        return await pool.run_quick_pool(lower_token_persentage=10, range_ticks=5)


class BaseQuestModule(SomniaClient, ABC):
    logger = AsyncLogger()
    def __init__(self, account: Account, quest_config: QuestConfig) -> None:
        super().__init__(account)
        self.quest_config = quest_config
        self.profile_module: ProfileModule = ProfileModule(account)
        self.quest_headers: dict[str, str] = self._build_headers(auth=True)
        self.account: Account = account

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.profile_module = ProfileModule(self.account)
        await self.profile_module.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if hasattr(self, 'profile_module'):
            await self.profile_module.__aexit__(exc_type, exc_val, exc_tb)
        await super().__aexit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def get_incomplete_quests(response: dict[str, Any]) -> list[int]:
        if not response or not isinstance(response, dict):
            return []
        quests = response.get("data", {}).get("quests", [])
        return [
            quest["id"]
            for quest in quests
            if not quest.get("isParticipated", False)
        ]

    async def get_quests(self) -> dict[str, Any] | bool:
        try:
            if not await self.onboarding():
                await self.logger.logger_msg(
                    msg=f"Authorization failed", type_msg="error", 
                    address=self.wallet_address, class_name=self.__class__.__name__, method_name="get_quests"
                )
                return False

            response = await self.send_request(
                request_type="GET",
                method=f"/campaigns/{self.quest_config.campaign_id}",
                headers=self._build_headers(
                    auth=True,
                    referer=(
                        f"https://quest.somnia.network/campaigns/{self.quest_config.campaign_id}"
                    ),
                ),
            )
            
            if not isinstance(response, dict):
                await self.logger.logger_msg(
                    msg=f"Unexpected response type: {type(response)}", type_msg="error", 
                    address=self.wallet_address, class_name=self.__class__.__name__, method_name="get_quests"
                )
                return {}
            
            return response
        except Exception as e:
            await self.logger.logger_msg(
                msg=f"Error in get_quests: {str(e)}", type_msg="error", 
                address=self.wallet_address, class_name=self.__class__.__name__, method_name="get_quests"
            )
            return {}

    async def _process_response(
        self,
        response: dict[str, Any],
        success_msg: str,
        error_msg: str,
    ) -> tuple[bool, str | None]:
        if response is None or response.get("status_code") != 200:
            status_code = response.get("status_code", "N/A") if response else "N/A"
            
            if isinstance(response, dict) and response.get("error"):
                error_details = f"API Error: {response.get('error')}"
            else:
                error_details = f"Code: {status_code}"
                
            await self.logger.logger_msg(
                msg=f"{error_msg} | {error_details}", 
                type_msg="error", 
                address=self.wallet_address
            )
            return False, f"http_error: {error_details}"

        response_data = response.get("data", {}) if response else {}
        if response_data and response_data.get("success"):
            await self.logger.logger_msg(
                msg=f"{success_msg}", type_msg="success", address=self.wallet_address
            )
            return True, success_msg

        error_reason = response_data.get("reason", "") if response_data else "Unknown error"
        log_msg = f"Account: {self.wallet_address} | {error_msg} | Reason: {error_reason}"
        
        if error_reason == "Verification conditions not met":
            await self.logger.logger_msg(
                msg=log_msg, type_msg="warning", address=self.wallet_address,
                class_name=self.__class__.__name__, method_name="_process_response"
            )
            return False, "conditions_not_met"
        
        await self.logger.logger_msg(
            msg=log_msg, type_msg="error", address=self.wallet_address,
            class_name=self.__class__.__name__, method_name="_process_response"
        )
        return False, "other_error"

    async def _send_verification_request(
        self,
        quest_id: int,
        endpoint: str,
        success_msg: str,
        error_msg: str,
    ) -> tuple[bool, str | None]:
        json_data = {"questId": quest_id}
        response = await self.send_request(
            request_type="POST",
            method=endpoint,
            headers = self._build_headers(
                auth=True,
                referer=f"{self._config.BASE_URL}/campaigns/{self.quest_config.campaign_id}"
            ),
            json_data=json_data,
        )
        return await self._process_response(response, success_msg, error_msg)

    async def run(self) -> tuple[bool, str]:
        try:
            class_name = self.__class__.__name__
            quest_name = class_name.replace("Module", "").replace("Quest", "")
            
            await self.logger.logger_msg(
                msg=f'Starting quest: "Somnia Testnet Odyssey - {quest_name}" processing...', 
                type_msg="info", address=self.wallet_address
            )
            
            excluded_quests = set()
            fatal_error = False

            for attempt in range(1, 4):
                if fatal_error:
                    break
                    
                await self.logger.logger_msg(
                    msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | Attempt {attempt}/3', 
                    type_msg="info", address=self.wallet_address
                )
                
                quests_data = await self.get_quests()
                if not quests_data or not isinstance(quests_data, dict):
                    await self.logger.logger_msg(
                        msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | Failed to get quests data', 
                        type_msg="error", address=self.wallet_address, class_name=class_name, method_name="run"
                    )
                    if attempt == 3:
                        return False, "Failed to get quests data"
                    continue
                    
                incomplete = self.get_incomplete_quests(quests_data)
                if not incomplete:
                    await self.logger.logger_msg(
                        msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | All quests completed!', 
                        type_msg="success", address=self.wallet_address
                    )
                    return True, "All quests completed"
                    
                filtered_quests = [q for q in incomplete if q not in excluded_quests]
                if not filtered_quests:
                    await self.logger.logger_msg(
                        msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | No processable quests remaining', 
                        type_msg="error", address=self.wallet_address, class_name=class_name, method_name="run"
                    )
                    return False, "No processable quests remaining"

                results = []
                for quest_id in filtered_quests:
                    handler_name = self.quest_config.quest_handlers.get(quest_id, "")
                    if not handler_name or quest_id in excluded_quests:
                        continue
                        
                    handler = getattr(self, handler_name, None)
                    if not handler:
                        await self.logger.logger_msg(
                            msg=f'Handler "{handler_name}" not found for quest ID {quest_id}',
                            type_msg="error", 
                            address=self.wallet_address,
                            class_name=class_name, 
                            method_name="run"
                        )
                        continue
                        
                    try:
                        success, error_code = await handler()
                        await self.logger.logger_msg(
                            msg=f'Quest ID {quest_id}, handler "{handler_name}": result {success}, error code {error_code}',
                            type_msg="info" if success else "error", 
                            address=self.wallet_address
                        )
                        results.append(success)
                        
                        if error_code == "conditions_not_met":
                            excluded_quests.add(quest_id)
                            if not results:
                                fatal_error = True
                    except Exception as e:
                        await self.logger.logger_msg(
                            msg=f'Error executing handler "{handler_name}": {str(e)}',
                            type_msg="error", 
                            address=self.wallet_address,
                            class_name=class_name, 
                            method_name="run"
                        )
                        continue

                if all(results):
                    await self.logger.logger_msg(
                        msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | Completed available quests!', 
                        type_msg="success", address=self.wallet_address
                    )
                    return True, "Completed available quests"
                    
                if not any(results):
                    break

            final_check = await self.get_quests()
            if final_check and not self.get_incomplete_quests(final_check):
                await self.logger.logger_msg(
                    msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | All quests completed!', 
                    type_msg="success", address=self.wallet_address
                )
                return True, "All quests completed"
            
            await self.logger.logger_msg(
                msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | Failed to complete all quests', 
                type_msg="error", address=self.wallet_address, class_name=class_name, method_name="run"
            )
            return False, "Failed to complete all quests"

        except Exception as error:
            await self.logger.logger_msg(
                msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | Critical error: {error!s}', 
                type_msg="error", address=self.wallet_address, class_name=class_name, method_name="run"
            )
            return False, f"Critical error: {error!s}"

    def safe_quest_handler(handler_func):
        async def wrapper(self, *args, **kwargs):
            handler_name = handler_func.__name__
            
            token_checks = {
                "twitter": ("Twitter auth tokens", self.account.auth_tokens_twitter),
                "discord": ("Discord tokens", self.account.auth_tokens_discord),
                "telegram": ("Telegram session", self.account.telegram_session)
            }

            missing = []
            for key, (name, token) in token_checks.items():
                if key in handler_name and not token:
                    missing.append(name)
            
            if missing:
                msg = f"Missing required: {', '.join(missing)}"
                return False, msg
                
            try:
                handler_type = handler_name.replace("handle_", "")
                quest_desc = f"{handler_type.replace('_', ' ').title()}"
                
                await self.logger.logger_msg(
                    msg=f'Processing "{quest_desc}"', 
                    type_msg="info", address=self.wallet_address
                )
                
                return await handler_func(self, *args, **kwargs)
                
            except Exception as e:
                error_msg = f"Error in {handler_name}: {str(e)}"
                await self.logger.logger_msg(
                    msg=error_msg, 
                    type_msg="error",
                    address=self.wallet_address, 
                    class_name=self.__class__.__name__, 
                    method_name=handler_name
                )
                return False, error_msg
        return wrapper
    
        
class QuestSparkballOne(BaseQuestModule):
    CAMPAIGN_ID = 46
    QUEST_HANDLERS = {
        180: "handle_follow_twitter_games",
        179: "handle_follow_twitter_sparkball",
        183: "handle_retweet_post"
    }

    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=self.CAMPAIGN_ID,
                quest_handlers=self.QUEST_HANDLERS
            )
        )
    
    @BaseQuestModule.safe_quest_handler
    async def handle_follow_twitter_games(self) -> tuple[bool, str]:
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(1920722477686431744)
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=180,
            endpoint="/social/twitter/follow",
            success_msg="Follow Somnia Games on X verified",
            error_msg=f"Failed verified Follow Somnia Games on X"
        )
        
    @BaseQuestModule.safe_quest_handler
    async def handle_follow_twitter_sparkball(self) -> tuple[bool, str]:
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(1537880021259280385)
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=179,
            endpoint="/social/twitter/follow",
            success_msg="Follow Sparkball on X verified",
            error_msg=f"Failed verified Follow Sparkball on X"
        )
        
    @BaseQuestModule.safe_quest_handler
    async def handle_retweet_post(self) -> tuple[bool, str]:
        async with TwitterWorker(self.account) as twitter_module:
            if not await twitter_module.retweet_tweet(1930610651942064516):
                return False, "Retweet failed"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=183,
            endpoint="/social/twitter/retweet",
            success_msg="Retweet Sparkball's announcement on X verified",
            error_msg=f"Failed verified Retweet Sparkball's announcement on X"
        )
        

class QuestSparkballThree(BaseQuestModule):
    CAMPAIGN_ID = 48
    QUEST_HANDLERS = {
        185: "handle_create_nft",
    }

    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=self.CAMPAIGN_ID,
                quest_handlers=self.QUEST_HANDLERS
            )
        )
    
    async def handle_create_nft(self) -> tuple[bool, str]:        
        return await self._send_verification_request(
            quest_id=185,
            endpoint="/onchain/nft-ownership",
            success_msg="Create a NFT art of your Quills playing Sparkball verified",
            error_msg=f"Failed verified Create a NFT art of your Quills playing Sparkball"
        )