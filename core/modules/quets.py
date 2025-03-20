from typing import Any

from config.settings import sleep_between_tasks
from core.api import SomniaClient
from core.modules import ProfileModule, TransferSTTModule
from loader import config
from logger import log
from models import Account
from utils import random_sleep


async def process_transfer_stt(
    account: Account,
    me: bool = False,
) -> tuple[bool, str]:
    async with TransferSTTModule(account, config.somnia_rpc, me) as module:
        return await module.transfer_stt()


class QuestSharingModule(SomniaClient):
    ID_CAMPAINGS: int = 7
    QUEST_HANDLERS: dict[int, str] = {
        46: "handle_in_tx_hash",
        44: "handle_native_token",
        45: "handle_out_tx_hash",
    }

    def __init__(self, account: Account) -> None:
        super().__init__(account)
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
            method=f"/campaigns/{self.ID_CAMPAINGS}",
            headers=self._get_base_headers(
                auth=True,
                custom_referer=(
                    f"https://quest.somnia.network/campaigns/{self.ID_CAMPAINGS}"
                ),
            ),
        )

    async def handle_in_tx_hash(self) -> bool:
        log.info(f'Account {self.wallet_address} | Processing "Receive STT tokens"')
        
        _, tx_hash = await process_transfer_stt(self.account, me=True)
        
        await random_sleep(
            self.wallet_address,
            **sleep_between_tasks
        )

        return await self._send_tx_verification(
            quest_id=46,
            tx_hash=tx_hash,
            success_msg="Successfully verified receiving STT tokens",
            error_msg="Failed to verify receiving STT tokens",
        )

    async def handle_out_tx_hash(self) -> bool:
        log.info(f'Account {self.wallet_address} | Processing "Send STT tokens"')
        
        _, tx_hash = await process_transfer_stt(self.account)
        
        await random_sleep(
            self.wallet_address,
            **sleep_between_tasks
        )

        return await self._send_tx_verification(
            quest_id=45,
            tx_hash=tx_hash,
            success_msg="Successfully verified sending STT tokens",
            error_msg="Failed to verify sending STT tokens",
        )

    async def handle_native_token(self) -> bool:
        log.info(f'Account {self.wallet_address} | Processing "Request STT tokens"')
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
    ) -> bool:
        json_data = {"questId": quest_id, "txHash": f"0x{tx_hash}"}
        response = await self.send_request(
            request_type="POST",
            method="/onchain/tx-hash",
            headers=self._get_base_headers(auth=True),
            json_data=json_data,
            verify=False,
        )
        return self._process_response(response, success_msg, error_msg)

    async def _send_verification_request(
        self,
        quest_id: int,
        endpoint: str,
        success_msg: str,
        error_msg: str,
    ) -> bool:
        json_data = {"questId": quest_id}
        response = await self.send_request(
            request_type="POST",
            method=endpoint,
            headers=self._get_base_headers(auth=True),
            json_data=json_data,
            verify=False,
        )
        return self._process_response(response, success_msg, error_msg)

    def _process_response(
        self,
        response: dict[str, Any],
        success_msg: str,
        error_msg: str,
    ) -> bool:
        if response.get("status_code") != 200:
            log.error(f"{error_msg} | Code: {response.get('status_code')}")
            return False

        response_data = response.get("data", {})
        if response_data.get("success"):
            log.success(f"{self.wallet_address} | {success_msg}")
            return True

        log.error(f"{self.wallet_address} | {error_msg} | Response: {response_data}")
        return False

    async def run(self) -> bool:
        try:
            log.info(f"Account {self.wallet_address} | Starting quest processing")
            for attempt in range(1, 4):
                log.info(f"Attempt {attempt}/3")
                quests_data = await self.get_quests()
                incomplete = self.get_incomplete_quests(quests_data)

                if not incomplete:
                    log.success("All quests completed!")
                    return True

                results = []
                for quest_id in incomplete:
                    handler_name = self.QUEST_HANDLERS.get(quest_id, "")
                    if handler := getattr(self, handler_name, None):
                        results.append(await handler())

                if all(results):
                    log.success("Completed all quests!")
                    return True

                log.warning(f"Attempt {attempt} failed")

            log.error("All 3 attempts failed")
            return False

        except Exception as error:
            log.error(f"Critical error: {error!s}")
            return False