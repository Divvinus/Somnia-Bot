import json
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from eth_keys import keys
from eth_keys.datatypes import PrivateKey
from eth_utils import to_checksum_address

from core.api import SomniaClient
from core.modules import ProfileModule
from logger import log
from models import Account


@dataclass
class QuestResponse:
    """Structure of the quests API response"""
    success: bool
    reason: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class SocialsQuest1Module(SomniaClient):
    """
    Module for managing social quests on Somnia.
    
    Manages social network account connections, referrals,
    and completing quests on the Somnia platform.
    """
    
    QUEST_IDS = {
        "DISCORD": 12,
        "TWITTER": 3
    }
    
    def __init__(self, account: Account) -> None:
        """
        Initialization of the socials quests module.
        
        Args:
            account: User credentials
        """
        super().__init__(account)
        self.profile_module = ProfileModule(account)
        self.quest_headers: Optional[Dict[str, str]] = self._get_base_headers(auth=True)

    @staticmethod
    def get_incomplete_quests(response: Dict[str, Any]) -> List[str]:
        """
        Extracting incomplete quests from the API response.
        
        Args:
            response: API response with quests data
            
        Returns:
            List of types of incomplete quests
        """
        quests = response.get("quests", [])
        return [
            quest["type"] for quest in quests 
            if not quest.get("isParticipated", False)
        ]

    @staticmethod
    def generate_eth_address() -> Tuple[PrivateKey, str]:
        """
        Generating a new EVM address and private key.
        
        Returns:
            Tuple (private_key, eth_address)
        """
        private_key_bytes = secrets.token_bytes(32)
        private_key = keys.PrivateKey(private_key_bytes)
        public_key = private_key.public_key
        address = to_checksum_address(public_key.to_address())
        return private_key, address

    async def get_quests(self) -> Dict[str, Any]:
        """
        Getting available quests from Somnia.
        
        Returns:
            Dictionary with quests data
        """
        response = await self.send_request(
            request_type="GET", 
            method="/campaigns/2", 
            headers=self._get_base_headers(
                auth=True, 
                custom_referer="https://quest.somnia.network/campaigns/2"
            )
        )
        return response if isinstance(response, dict) else response.json()

    async def _handle_social_connection(
        self, 
        social_type: str,
        quest_id: int,
        connect_method: str,
        token_field: str
    ) -> bool:
        """
        Processing social network connection.
        
        Args:
            social_type: Type of social network (Discord/Twitter)
            quest_id: Quest ID
            connect_method: API method for connection
            token_field: Field with token in account
            
        Returns:
            True if connection is successful, False otherwise
        """
        json_data = {"questId": quest_id}
        
        while True:
            response = await self.send_request(
                request_type="POST",
                method=connect_method,
                headers=self.quest_headers,
                json_data=json_data,
            )
            response_data = response.json()
            
            if response_data.get("success") is True:
                log.success(f"Account {self.wallet_address} | {social_type} connected successfully")
                return True
                
            if response_data.get("success") is False:
                if response_data.get("reason") == "Verification conditions not met":
                    tokens = getattr(self.account, token_field)
                    if tokens:
                        connect_account_method = getattr(self.profile_module, f"connect_{social_type.lower()}_account")
                        if await connect_account_method():
                            continue
                        return False
                    else:
                        log.warning(f"Account {self.wallet_address} | No {social_type} token found")
                        return False
                else:
                    log.error(f"Account {self.wallet_address} | Failed to connect {social_type}: {response_data.get('reason')}")
                    return False
            else:
                log.error(f"Account {self.wallet_address} | Failed to connect {social_type}. Response: {response_data}")
                return False

    async def connect_discord(self) -> bool:
        """
        Confirming Discord account connection to Somnia profile.
        
        Returns:
            True if connection is successful, False otherwise
        """            
        log.info(f"Account {self.wallet_address} | Confirming connection to Discord...")
        
        return await self._handle_social_connection(
            "Discord",
            self.QUEST_IDS["DISCORD"],
            "/social/discord/connect",
            "auth_tokens_discord"
        )

    async def connect_twitter(self) -> bool:
        """
        Confirming Twitter account connection to Somnia profile.
        
        Returns:
            True if connection is successful, False otherwise
        """            
        log.info(f"Account {self.wallet_address} | Confirming connection to Twitter...")
        
        return await self._handle_social_connection(
            "Twitter", 
            self.QUEST_IDS["TWITTER"],
            "/social/twitter/connect",
            "auth_tokens_twitter"
        )

    async def _get_or_activate_referral_code(self) -> Optional[str]:
        """
        Getting or activating referral code.
        
        Returns:
            Referral code or None in case of an error
        """
        log.info(f"Account {self.wallet_address} | Getting or activating referral code...")
        
        for _ in range(3):
            referral_code = await self.get_me_info(get_referral_code=True)
            if referral_code:
                return referral_code
            if await self.activate_referral():
                continue
            return None
        return None

    async def onboarding_referral(self, private_key: PrivateKey, address: str) -> str:
        """
        Performing the onboarding process for the referral account.
        
        Args:
            private_key: Private key of the referral account
            address: EVM address of the referral account
            
        Returns:
            Authentication token for the referral account
        """
        log.info("Referral Account | Onboarding...")

        signature = await self.get_signature(
            '{"onboardingUrl":"https://quest.somnia.network"}',
            private_key=str(private_key),
        )

        headers = {
            "authority": "quest.somnia.network",
            "accept": "application/json",
            "content-type": "application/json",
            "dnt": "1",
            "origin": "https://quest.somnia.network",
            "referer": "https://quest.somnia.network/connect?redirect=%2F",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

        json_data = {
            "signature": signature,
            "walletAddress": address,
        }

        response = await self.send_request(
            request_type="POST",
            method="/auth/onboard",
            json_data=json_data,
            headers=headers,
        )
        response_data = response.json()
        return cast(str, response_data["token"])

    async def register_referral(self, token: str, referral_code: str, private_key: PrivateKey) -> bool:
        """
        Registering a referral with the specified code.
        
        Args:
            token: Authentication token for the referral account
            referral_code: Referral code to use
            private_key: Private key of the referral account
            
        Returns:
            True if registration is successful, False otherwise
        """
        self.base_url = "https://quest.somnia.network/api"

        try:
            message_to_sign = json.dumps(
                {"referralCode": referral_code, "product": "QUEST_PLATFORM"},
                separators=(",", ":"),
            )
            signature = await self.get_signature(message_to_sign, private_key=str(private_key))

            headers = {
                "accept": "application/json",
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "origin": "https://quest.somnia.network",
                "priority": "u=1, i",
                "referer": f"https://quest.somnia.network/referrals/{referral_code}",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            }

            json_data = {
                "referralCode": referral_code,
                "product": "QUEST_PLATFORM",
                "signature": signature,
            }

            response = await self.send_request(
                request_type="POST",
                method="/users/referrals",
                json_data=json_data,
                headers=headers,
            )
            response_data = response.json()

            if not response_data:
                log.info(f"Successfully registered referral for code {referral_code}")
                return True

            try:
                parsed_data = response_data if isinstance(response_data, dict) else json.loads(response_data)
                if parsed_data.get("message") == "Success":
                    log.info(f"Successfully registered referral for code {referral_code}")
                    return True
                else:
                    log.error(f"Failed to register referral for code {referral_code}. Response: {parsed_data}")
                    return False
            except (json.JSONDecodeError, AttributeError) as e:
                log.error(f"Failed to parse response: {response_data}. Error: {e}")
                return False

        except Exception as e:
            log.error(f"Error processing referral for code {referral_code}: {str(e)}")
            return False

    async def process_referral(self) -> bool:
        """
        Processing the referral quest by generating a new account and registering a referral.
        
        Returns:
            True if the referral is successfully processed, False otherwise
        """
        try:
            referral_code = await self._get_or_activate_referral_code()
            if not referral_code:
                log.error(f"Account {self.wallet_address} | Failed to get referral code")
                return False
                
            private_key, address = self.generate_eth_address()
            token = await self.onboarding_referral(private_key, address)
            
            return await self.register_referral(token, referral_code, private_key)
            
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error in referral method: {e}")
            return False

    async def run(self) -> bool:
        """
        Starting the social quests module.
        
        Performs all available social network quests, including:
        - Connecting Discord account
        - Connecting Twitter account
        - Processing referrals
        
        Returns:
            True if all quests are successfully completed, False otherwise
        """
        try:
            log.info(f"Account {self.wallet_address} | Starting the socials quests module...")

            if not await self.onboarding():
                log.error(f"Account {self.wallet_address} | Failed to authorize on Somnia")
                return False

            completed_all = True
            
            for attempt in range(3):
                log.info(f"Account {self.wallet_address} | Getting quests...")
                quests_data = await self.get_quests()
                incomplete_quests = self.get_incomplete_quests(quests_data)
                
                if not incomplete_quests:
                    log.success(f"Account {self.wallet_address} | All quests are completed")
                    return True
                
                quest_handlers = {
                    "CONNECT_DISCORD": self.connect_discord,
                    "CONNECT_TWITTER": self.connect_twitter,
                    "REFERRAL": self.process_referral
                }
                
                for quest_type in incomplete_quests:
                    if handler := quest_handlers.get(quest_type):
                        result = await handler()
                        completed_all = completed_all and result
                
                if completed_all or attempt == 2:
                    return completed_all
                    
            return False
            
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error in run method: {str(e)}")
            return False