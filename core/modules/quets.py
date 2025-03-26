from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from config.settings import sleep_between_tasks
from core.api import SomniaClient
from core.modules import ProfileModule, TransferSTTModule
from loader import config
from logger import log
from models import Account
from utils import random_sleep


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
    def __init__(self, account: Account, quest_config: QuestConfig) -> None:
        super().__init__(account)
        self.quest_config = quest_config
        self.profile_module: ProfileModule = ProfileModule(account)
        self.quest_headers: dict[str, str] = self._get_base_headers(auth=True)
        self.account: Account = account

    @staticmethod
    def get_incomplete_quests(response: dict[str, Any]) -> list[int]:
        quests = response.get("data", {}).get("quests", [])
        return [
            quest["id"]
            for quest in quests
            if not quest.get("isParticipated", False)
        ]

    async def get_quests(self) -> dict[str, Any] | bool:
        if not await self.onboarding():
            log.error(f"Account {self.wallet_address} | Authorization failed")
            return False

        return await self.send_request(
            request_type="GET",
            method=f"/campaigns/{self.quest_config.campaign_id}",
            headers=self._get_base_headers(
                auth=True,
                custom_referer=(
                    f"https://quest.somnia.network/campaigns/{self.quest_config.campaign_id}"
                ),
            ),
        )

    def _process_response(
        self,
        response: dict[str, Any],
        success_msg: str,
        error_msg: str,
    ) -> tuple[bool, str | None]:
        if response.get("status_code") != 200:
            log.error(f"Account {self.wallet_address} | {error_msg} | Code: {response.get('status_code')}")
            return False, "http_error"

        response_data = response.get("data", {})
        if response_data.get("success"):
            log.success(f"Account {self.wallet_address} | {success_msg}")
            return True, None

        error_reason = response_data.get("reason", "")
        log_msg = f"Account {self.wallet_address} | {error_msg} | Reason: {error_reason}"
        
        if error_reason == "Verification conditions not met":
            log.warning(log_msg)
            return False, "conditions_not_met"
        
        log.error(log_msg)
        return False, "other_error"

    @abstractmethod
    async def _send_verification_request(
        self,
        quest_id: int,
        endpoint: str,
        success_msg: str,
        error_msg: str,
    ) -> tuple[bool, str | None]:
        pass

    async def run(self) -> tuple[bool, str]:
        try:
            quest_name = self.__class__.__name__.replace("QuestModule", "")
            log.info(f'Account {self.wallet_address} | Starting quest: "Somnia Testnet Odyssey - {quest_name}" processing...')
            
            excluded_quests = set()
            fatal_error = False

            for attempt in range(1, 4):
                if fatal_error:
                    break
                    
                log.info(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | Attempt {attempt}/3')
                
                quests_data = await self.get_quests()
                if not quests_data or not isinstance(quests_data, dict):
                    log.error(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | Failed to get quests data')
                    continue
                    
                incomplete = self.get_incomplete_quests(quests_data)
                if not incomplete:
                    log.success(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | All quests completed!')
                    return True, "All quests completed"
                    
                filtered_quests = [q for q in incomplete if q not in excluded_quests]
                if not filtered_quests:
                    log.error(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | No processable quests remaining')
                    return False, "No processable quests remaining"

                results = []
                for quest_id in filtered_quests:
                    handler_name = self.quest_config.quest_handlers.get(quest_id, "")
                    if not handler_name or quest_id in excluded_quests:
                        continue
                        
                    handler = getattr(self, handler_name, None)
                    if not handler:
                        continue
                        
                    success, error_code = await handler()
                    results.append(success)
                    
                    if error_code == "conditions_not_met":
                        excluded_quests.add(quest_id)
                        if not results:
                            fatal_error = True

                if all(results):
                    log.success(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | Completed available quests!')
                    return True, "Completed available quests"
                    
                if not any(results):
                    break

            final_check = await self.get_quests()
            if final_check and not self.get_incomplete_quests(final_check):
                log.success(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | All quests completed!')
                return True, "All quests completed"
            
            log.error(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | Failed to complete all quests')
            return False, "Failed to complete all quests"

        except Exception as error:
            log.error(f'Account {self.wallet_address} | Quest: "Somnia Testnet Odyssey - {quest_name}" | Critical error: {error!s}')
            return False, f"Critical error: {error!s}"


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

    async def handle_in_tx_hash(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Receive STT tokens"')
        _, tx_hash = await process_transfer_stt(self.account, me=True)
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        return await self._send_tx_verification(
            quest_id=46,
            tx_hash=tx_hash,
            success_msg="Successfully verified receiving STT tokens",
            error_msg="Failed to verify receiving STT tokens",
        )

    async def handle_out_tx_hash(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Send STT tokens"')
        _, tx_hash = await process_transfer_stt(self.account)
        await random_sleep(self.wallet_address, **sleep_between_tasks)
        return await self._send_tx_verification(
            quest_id=45,
            tx_hash=tx_hash,
            success_msg="Successfully verified sending STT tokens",
            error_msg="Failed to verify sending STT tokens",
        )

    async def handle_native_token(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Request STT tokens"')
        return await self._send_verification_request(
            quest_id=44,
            endpoint="/onchain/native-token", 
            success_msg="Successfully verified STT token request",
            error_msg="Failed to verify STT token request",
        )

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
            headers=self._get_base_headers(auth=True),
            json_data=json_data,
        )
        return self._process_response(response, success_msg, error_msg)

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
            headers=self._get_base_headers(auth=True),
            json_data=json_data,
        )
        return self._process_response(response, success_msg, error_msg)


class QuestSocialsModule(BaseQuestModule):
    def __init__(self, account: Account) -> None:
        super().__init__(
            account,
            QuestConfig(
                campaign_id=8,
                quest_handlers={
                    60: "handle_connect_telegram",
                    61: "handle_link_username",
                    62: "handle_connect_discord", 
                    63: "handle_twitter_follow",
                    64: "handle_connect_twitter"
                }
            )
        )

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
            headers=self._get_base_headers(auth=True),
            json_data=json_data,
        )
        return self._process_response(response, success_msg, error_msg)

    async def handle_connect_telegram(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Connect Telegram"')
        return await self._send_verification_request(
            quest_id=60,
            endpoint="/social/telegram/connect",
            success_msg="Successfully verified Telegram connection",
            error_msg="Failed to verify Telegram connection",
        )
        
    async def handle_link_username(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Link Username"')
        return await self._send_verification_request(
            quest_id=61,
            endpoint="/social/verify-username",
            success_msg="Successfully verified username link",
            error_msg="Failed to verify username link",
        )
    
    async def handle_connect_discord(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Connect Discord"')
        return await self._send_verification_request(
            quest_id=62,
            endpoint="/social/discord/connect", 
            success_msg="Successfully verified Discord connection",
            error_msg="Failed to verify Discord connection",
        )
    
    async def handle_twitter_follow(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Twitter Follow"')
        return await self._send_verification_request(
            quest_id=63,
            endpoint="/social/twitter/follow",
            success_msg="Successfully verified Twitter follow",
            error_msg="Failed to verify Twitter follow",
        )
    
    async def handle_connect_twitter(self) -> tuple[bool, str | None]:
        log.info(f'Account {self.wallet_address} | Processing "Connect Twitter"')
        return await self._send_verification_request(
            quest_id=64,
            endpoint="/social/twitter/connect",
            success_msg="Successfully verified Twitter connection",
            error_msg="Failed to verify Twitter connection",
        )