from abc import ABC
from dataclasses import dataclass
from typing import Any, Self

from config.settings import sleep_between_tasks
from src.api import SomniaClient
from src.tasks import (
    ProfileModule, 
    TransferSTTModule
)
from bot_loader import config
from src.logger import AsyncLogger
from src.models import Account
from src.utils import random_sleep, TwitterWorker


@dataclass
class QuestConfig:
    campaign_id: int
    quest_handlers: dict[int, str]


async def process_transfer_stt(
    account: Account,
    me: bool = False,
) -> tuple[bool, str]:
    async with TransferSTTModule(account, config.somnia_rpc, me) as module:
        return await module.transfer_stt()


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
            headers=self._build_headers(auth=True),
            json_data=json_data,
        )
        return await self._process_response(response, success_msg, error_msg)

    async def check_prerequisites(self) -> tuple[bool, str]:
        required_tokens = []
        
        if any(handler.startswith("handle_twitter") for handler in self.quest_config.quest_handlers.values()):
            required_tokens.append(("Twitter tokens", bool(self.account.auth_tokens_twitter)))
            
        if any(handler.startswith("handle_discord") or handler.endswith("discord") for handler in self.quest_config.quest_handlers.values()):
            required_tokens.append(("Discord tokens", bool(self.account.auth_tokens_discord)))
            
        if any(handler.startswith("handle_telegram") for handler in self.quest_config.quest_handlers.values()):
            required_tokens.append(("Telegram session", bool(self.account.telegram_session)))
        
        missing_tokens = [name for name, exists in required_tokens if not exists]
        
        if missing_tokens:
            missing_str = ", ".join(missing_tokens)
            return False, f"Missing: {missing_str}"
        
        return True, "All prerequisites met"

    async def run(self) -> tuple[bool, str]:
        try:
            class_name = self.__class__.__name__
            quest_name = class_name.replace("Module", "").replace("Quest", "")
            
            prereq_met, prereq_msg = await self.check_prerequisites()
            if not prereq_met:
                await self.logger.logger_msg(
                    msg=f'Quest: "{quest_name}" cannot proceed - {prereq_msg}', 
                    type_msg="error", address=self.wallet_address, class_name=class_name, method_name="run"
                )
                return False, f"Cannot proceed: {prereq_msg}"
            
            if not self.quest_config or not hasattr(self.quest_config, 'quest_handlers') or not self.quest_config.quest_handlers:
                await self.logger.logger_msg(
                    msg=f'Quest: "Somnia Testnet Odyssey - {quest_name}" | No quest handlers defined', 
                    type_msg="error", address=self.wallet_address, class_name=class_name, method_name="run"
                )
                return False, "No quest handlers defined"
            
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
            
            if "twitter" in handler_name and not self.account.auth_tokens_twitter:
                return False, "No Twitter auth tokens"
                
            if "discord" in handler_name and not self.account.auth_tokens_discord:
                return False, "No Discord auth tokens"
                
            if "telegram" in handler_name and not self.account.telegram_session:
                return False, "No Telegram session"
            
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


class QuestSharingModule(BaseQuestModule):
    def __init__(self, account: Account) -> None:
        super().__init__(
            account, 
            QuestConfig(
                campaign_id=7, 
                quest_handlers={
                    46: "handle_in_tx_hash",
                    44: "handle_native_token", 
                    45: "handle_out_tx_hash"
                }
            )
        )

    @BaseQuestModule.safe_quest_handler
    async def handle_in_tx_hash(self) -> tuple[bool, str | None]:
        _, tx_hash = await process_transfer_stt(self.account, me=True)
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        return await self._send_tx_verification(
            quest_id=46,
            tx_hash=tx_hash,
            success_msg="Successfully verified receiving STT tokens",
            error_msg="Failed to verify receiving STT tokens",
        )

    @BaseQuestModule.safe_quest_handler
    async def handle_out_tx_hash(self) -> tuple[bool, str | None]:
        _, tx_hash = await process_transfer_stt(self.account)
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        return await self._send_tx_verification(
            quest_id=45,
            tx_hash=tx_hash,
            success_msg="Successfully verified sending STT tokens",
            error_msg="Failed to verify sending STT tokens",
        )

    @BaseQuestModule.safe_quest_handler
    async def handle_native_token(self) -> tuple[bool, str | None]:
        return await self._send_verification_request(
            quest_id=44,
            endpoint="/onchain/native-token", 
            success_msg="Successfully verified STT token request",
            error_msg="Failed to verify STT token request",
        )

    async def _send_tx_verification(
        self,
        quest_id: int,
        tx_hash: str,
        success_msg: str,
        error_msg: str,
    ) -> tuple[bool, str | None]:
        json_data = {"questId": quest_id, "txHash": f"0x{tx_hash}"}
        response = await self.send_request(
            request_type="POST",
            method="/onchain/tx-hash", 
            headers=self._build_headers(auth=True),
            json_data=json_data,
        )
        return await self._process_response(response, success_msg, error_msg)


class QuestSocialsModule(BaseQuestModule):
    user_id = {
        "somnia": 1757553204747972608
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=8,
                quest_handlers={
                    60: "handle_connect_telegram",
                    61: "handle_link_username",
                    62: "handle_connect_discord", 
                    63: "handle_twitter_follow_somnia",
                    64: "handle_connect_twitter"
                }
            )
        )

    async def handle_connect_telegram(self) -> tuple[bool, str | None]:
        if not self.account.telegram_session:
            return False, "No Telegram session"
        
        await self.logger.logger_msg(
            msg=f'Processing "Connect Telegram"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=60,
            endpoint="/social/telegram/connect",
            success_msg="Successfully verified Telegram connection",
            error_msg="Failed to verify Telegram connection",
        )
        
    async def handle_link_username(self) -> tuple[bool, str | None]:
        await self.logger.logger_msg(
            msg=f'Processing "Link Username"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=61,
            endpoint="/social/verify-username",
            success_msg="Successfully verified username link",
            error_msg="Failed to verify username link",
        )
    
    async def handle_connect_discord(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Connect Discord"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=62,
            endpoint="/social/discord/connect", 
            success_msg="Successfully verified Discord connection",
            error_msg="Failed to verify Discord connection",
        )
    
    async def handle_twitter_follow_somnia(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Twitter Follow"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["somnia"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)  
        
        return await self._send_verification_request(
            quest_id=63,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
    
    async def handle_connect_twitter(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"  
        
        await self.logger.logger_msg(
            msg=f'Processing "Connect Twitter"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=64,
            endpoint="/social/twitter/connect",
            success_msg="Successfully verified Twitter connection",
            error_msg="Failed to verify Twitter connection",
        )
        

class QuestDarktableModule(BaseQuestModule):
    user_id = {
        "darktable": 1528463445745541120
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=10,
                quest_handlers={
                    48: "handle_twitter_follow_darktable",
                    49: "handle_retweet",
                    50: "handle_join_discord"
                }
            )
        )
        
    async def handle_twitter_follow_darktable(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Twitter Follow Darktable"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["darktable"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=48,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_retweet(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Retweet"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            tweet_id=1906754535110090831

            result_retweet = await twitter_module.retweet_tweeet(tweet_id)
            if not result_retweet:
                return False, "Failed to retweet"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=49,
            endpoint="/social/twitter/retweet",
            success_msg="Successfully verified Twitter retweet",
            error_msg="Failed to verify Twitter retweet",
        )
    
    async def handle_join_discord(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )
        
        return await self._send_verification_request(
            quest_id=50,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )


class QuestPlaygroundModule(BaseQuestModule):
    user_id = {
        "playground": 1902733320154152960
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=11,
                quest_handlers={
                    66: "handle_create_world",
                    68: "handle_invite_two_people",
                    69: "handle_twitter_follow_playground",
                    65: "handle_mint_avatar",
                    67: "handle_explore_world"
                }
            )
        )
        
    async def handle_create_world(self) -> tuple[bool, str | None]:
        await self.logger.logger_msg(
            msg=f'Processing "Create one world on the Somnia Playground"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=66,
            endpoint="offchain/arbitrary-api",
            success_msg='Successfully "Create one world on the Somnia Playground"',
            error_msg='Failed "Create one world on the Somnia Playground"',
        )
        
    async def handle_invite_two_people(self) -> tuple[bool, str | None]:
        await self.logger.logger_msg(
            msg=f'Processing "Invite at least 2 people to your world"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=68,
            endpoint="offchain/arbitrary-api",
            success_msg='Successfully "Invite at least 2 people to your world"',
            error_msg='Failed "Invite at least 2 people to your world"',
        )
        
    async def handle_twitter_follow_playground(self) -> tuple[bool, str | None]:
        await self.logger.logger_msg(
            msg=f'Processing "Follow the Somnia Playground"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["playground"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=69,
            endpoint="social/twitter/follow",
            success_msg='Successfully "Follow the Somnia Playground"',
            error_msg='Failed "Follow the Somnia Playground"',
        )
    
    async def handle_mint_avatar(self) -> tuple[bool, str | None]:
        await self.logger.logger_msg(
            msg=f'Processing "Mint an avatar"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=65,
            endpoint="onchain/nft-ownership",
            success_msg='Successfully "Mint an avatar"',
            error_msg='Failed "Mint an avatar"',
        )
        
    async def handle_explore_world(self) -> tuple[bool, str | None]:
        await self.logger.logger_msg(
            msg=f'Processing "Explore a world"', type_msg="info", address=self.wallet_address
        )
        return await self._send_verification_request(
            quest_id=67,
            endpoint="offchain/arbitrary-api",
            success_msg='Successfully "Explore a world"',
            error_msg='Failed "Explore a world"',
        )
        
        
class QuestDemonsModule(BaseQuestModule):
    user_id = {
        "nkdemons": 1603401673728303105
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=13,
                quest_handlers={
                    71: "handle_twitter_follow_nkdemons",
                    72: "handle_retweet",
                    73: "handle_join_discord"
                }
            )
        )
        
    async def handle_twitter_follow_nkdemons(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Twitter Follow Nkdemons"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["nkdemons"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=71,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_retweet(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Retweet"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            tweet_id=1909999965046296577
            
            result_retweet = await twitter_module.retweet_tweeet(tweet_id)
            if not result_retweet:
                return False, "Failed to retweet"
            
            await random_sleep(self.wallet_address, **sleep_between_tasks)
            
            result_like = await twitter_module.like_tweet(tweet_id)
            if not result_like:
                return False, "Failed to like"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=72,
            endpoint="/social/twitter/retweet",
            success_msg="Successfully verified Twitter retweet",
            error_msg="Failed to verify Twitter retweet",
        )
    
    async def handle_join_discord(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )
        
        return await self._send_verification_request(
            quest_id=73,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )
    
    
class QuestGamingFrenzyModule(BaseQuestModule):
    user_id = {
        "dream": 1836667007355207680,
        "sequence": 1270142966527520768
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=14,
                quest_handlers={
                    77: "handle_retweet_one",
                    74: "handle_twitter_follow_dream",
                    75: "handle_twitter_follow_sequence",
                    76: "handle_retweet_two"
                }
            )
        )
        
    async def handle_retweet_one(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Retweet one post"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            tweet_id=1884319440684343507

            result_retweet = await twitter_module.retweet_tweeet(tweet_id)
            if not result_retweet:
                return False, "Failed to retweet"
            
            await random_sleep(self.wallet_address, **sleep_between_tasks)
            
            result_like = await twitter_module.like_tweet(tweet_id)
            if not result_like:
                return False, "Failed to like"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
            
        return await self._send_verification_request(
            quest_id=77,
            endpoint="/social/twitter/retweet",
            success_msg="Successfully verified Twitter retweet",
            error_msg="Failed to verify Twitter retweet",
        )
        
    async def handle_twitter_follow_dream(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Dream"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["dream"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        return await self._send_verification_request(
            quest_id=74,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
    
    async def handle_twitter_follow_sequence(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Sequence"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["sequence"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=75,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
    
    async def handle_retweet_two(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Retweet one post"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            tweet_id=1885339274343551279

            result_retweet = await twitter_module.retweet_tweeet(tweet_id)
            if not result_retweet:
                return False, "Failed to retweet"
            
            await random_sleep(self.wallet_address, **sleep_between_tasks)
            
            result_like = await twitter_module.like_tweet(tweet_id)
            if not result_like:
                return False, "Failed to like"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
            
        return await self._send_verification_request(
            quest_id=77,
            endpoint="/social/twitter/retweet",
            success_msg="Successfully verified Twitter retweet",
            error_msg="Failed to verify Twitter retweet",
        )
        
        
class QuestSomniaGamingRoomModule(BaseQuestModule):
    user_id = {
        "lag": 1860957042430910464,
        "kraftlabs": 1786428970021306368,
        "galeon": 1430367385194700801
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=15,
                quest_handlers={
                    83: "handle_twitter_follow_lag",
                    84: "handle_twitter_follow_kraftlabs",
                    85: "handle_twitter_follow_galeon",
                    86: "handle_join_discord"
                }
            )
        )
        
    async def handle_twitter_follow_lag(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Lag"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["lag"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=83,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_twitter_follow_kraftlabs(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Kraftlabs"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["kraftlabs"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=84,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
    
    async def handle_twitter_follow_galeon(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Galeon"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["galeon"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=85,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
    
    async def handle_join_discord(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )
        
        return await self._send_verification_request(
            quest_id=86,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )
        
    
class QuestMulletCopModule(BaseQuestModule):
    user_id = {
        "mulletcop": 1910155420762800128
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=16,
                quest_handlers={
                    87: "handle_twitter_follow_mulletcop",
                    88: "handle_join_discord",
                    89: "handle_retweet_and_like"
                }
            )
        )
        
    async def handle_twitter_follow_mulletcop(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Mulletcop"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["mulletcop"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=87,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_join_discord(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )
        
        return await self._send_verification_request(
            quest_id=88,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )
    
    async def handle_retweet_and_like(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Retweet and like"', type_msg="info", address=self.wallet_address
        )
        
        tweet_id = 1912536593144967388
        
        async with TwitterWorker(self.account) as twitter_module:
            result_retweet = await twitter_module.retweet_tweeet(tweet_id)
            if not result_retweet:
                return False, "Failed to retweet"
            
            await random_sleep(self.wallet_address, **sleep_between_tasks)
            
            result_like = await twitter_module.like_tweet(tweet_id)
            if not result_like:
                return False, "Failed to like"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=89,
            endpoint="/social/twitter/retweet",
            success_msg="Successfully verified Twitter retweet",
            error_msg="Failed to verify Twitter retweet",
        )
        

class QuestIntersectionCopModule(BaseQuestModule):
    user_id = {
        "standard": 1367396320374190080,
        "haifu": 1870618096173719552,
        "salt": 1815727808447967232,
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=17,
                quest_handlers={
                    100: "handle_twitter_follow_standard",
                    101: "handle_twitter_follow_haifu",
                    102: "handle_twitter_follow_salt",
                    104: "handle_join_discord_standard",
                    108: "handle_retweet_and_like",
                    106: "handle_join_discord_salt",
                    105: "handle_join_discord_haifu",
                    # 107: "handle_join_discord_otomato"
                }
            )
        )
        
    async def handle_twitter_follow_standard(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Standard "', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["standard"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=100,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_twitter_follow_haifu(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Haifu"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["haifu"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=101,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_twitter_follow_salt(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Salt"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["salt"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=102,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_join_discord_standard(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )
        
        return await self._send_verification_request(
            quest_id=104,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )
    
    async def handle_retweet_and_like(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Retweet and like"', type_msg="info", address=self.wallet_address
        )
        
        tweet_id = 1914311210159288769
        
        async with TwitterWorker(self.account) as twitter_module:
            result_retweet = await twitter_module.retweet_tweeet(tweet_id)
            if not result_retweet:
                return False, "Failed to retweet"
            
            await random_sleep(self.wallet_address, **sleep_between_tasks)
            
            result_like = await twitter_module.like_tweet(tweet_id)
            if not result_like:
                return False, "Failed to like"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=89,
            endpoint="/social/twitter/retweet",
            success_msg="Successfully verified Twitter retweet",
            error_msg="Failed to verify Twitter retweet",
        )
        
    async def handle_join_discord_salt(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )
        
        return await self._send_verification_request(
            quest_id=106,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )
        
    async def handle_join_discord_haifu(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )

        return await self._send_verification_request(
            quest_id=105,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )

        
    # async def handle_join_discord_otomato(self) -> tuple[bool, str | None]:
    #     if not self.account.auth_tokens_discord:
    #         return False, "No Discord auth tokens"
        
    #     await self.logger.logger_msg(
    #         msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
    #     )
        
    #     return await self._send_verification_request(
    #         quest_id=107,
    #         endpoint="/social/discord/join",
    #         success_msg="Successfully verified Discord join",
    #         error_msg="Failed to verify Discord join",
    #     )
    
    
class QuestMasksOfTheVoidModule(BaseQuestModule):
    user_id = {
        "masks": 1913357627280805888
    }
    
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=18,
                quest_handlers={
                    112: "handle_twitter_follow_masks",
                    113: "handle_join_discord",
                    114: "handle_retweet_and_like"
                }
            )
        )
        
    async def handle_twitter_follow_masks(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Follow Masks of the Void"', type_msg="info", address=self.wallet_address
        )
        
        async with TwitterWorker(self.account) as twitter_module:
            result_follow = await twitter_module.follow_user(self.user_id["masks"])
            if not result_follow:
                return False, "Failed to follow"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=112,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
        
    async def handle_join_discord(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_discord:
            return False, "No Discord auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Join Discord"', type_msg="info", address=self.wallet_address
        )
        
        return await self._send_verification_request(
            quest_id=113,
            endpoint="/social/discord/join",
            success_msg="Successfully verified Discord join",
            error_msg="Failed to verify Discord join",
        )
    
    async def handle_retweet_and_like(self) -> tuple[bool, str | None]:
        if not self.account.auth_tokens_twitter:
            return False, "No Twitter auth tokens"
        
        await self.logger.logger_msg(
            msg=f'Processing "Retweet and like"', type_msg="info", address=self.wallet_address
        )
        
        tweet_id = 1915073514182189266
        
        async with TwitterWorker(self.account) as twitter_module:
            result_retweet = await twitter_module.retweet_tweeet(tweet_id)
            if not result_retweet:
                return False, "Failed to retweet"
            
            await random_sleep(self.wallet_address, **sleep_between_tasks)
            
            result_like = await twitter_module.like_tweet(tweet_id)
            if not result_like:
                return False, "Failed to like"
            
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        
        return await self._send_verification_request(
            quest_id=114,
            endpoint="/social/twitter/retweet",
            success_msg="Successfully verified Twitter retweet",
            error_msg="Failed to verify Twitter retweet",
        )