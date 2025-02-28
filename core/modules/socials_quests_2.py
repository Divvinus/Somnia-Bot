from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from Jam_Twitter_API.account_sync import TwitterAccountSync

from core.api import SomniaClient, TwitterClient
from core.modules import ProfileModule
from logger import log
from models import Account
from utils import random_sleep
from config.settings import sleep_after_telegram_connection, sleep_after_username_creation


@dataclass
class QuestResponse:
    """Structure of the quests API response"""
    success: bool
    reason: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class SocialsQuest2Module(SomniaClient):
    """
    Module for managing social quests on Somnia.
    
    Manages social network account connections, referrals,
    and completing quests on the Somnia platform.
    """
    
    def __init__(self, account: Account) -> None:
        """
        Initialization of the socials quests module.
        
        Args:
            account: User credentials
        """
        super().__init__(account)
        self.twitter_worker = TwitterClient(account)
        self.twitter_client: TwitterAccountSync = None
        self.profile_module = ProfileModule(account)
        self.quest_headers: Optional[Dict[str, str]] = self._get_base_headers(auth=True)
        
    async def _get_twitter_client(self):
        self.twitter_client = await self.twitter_worker.get_account()
        
    async def _get_user_info(self):
        log.info(f'Account {self.wallet_address} | Check if the conditions for "Socials Quests 2"')
        for _ in range(3):
            null_fields = await self.get_me_info()
            if null_fields is None:
                log.success(f'Account {self.wallet_address} | Telegram account is linked and user name is set, continue with the execution "Socials Quests 2"')
                return True
            
            if "username" in null_fields:
                await self.profile_module.create_username()
                await random_sleep(self.wallet_address, **sleep_after_username_creation)
            
            if "telegramName" in null_fields and self.account.telegram_session:
                await self.profile_module.connect_telegram_account()
                await random_sleep(self.wallet_address, **sleep_after_telegram_connection)
        
        log.error(f'Account {self.wallet_address} | Failed to fully complete the profile to prepare it for execution "Socials Quests 2"')
        return False      

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
            quest["id"] for quest in quests 
            if not quest.get("isParticipated", False)
        ]

    async def get_quests(self) -> Dict[str, Any]:
        """
        Getting available quests from Somnia.
        
        Returns:
            Dictionary with quests data
        """
        response = await self.send_request(
            request_type="GET", 
            method="/campaigns/5", 
            headers=self._get_base_headers(
                auth=True, 
                custom_referer="https://quest.somnia.network/campaigns/5"
            )
        )
        return response if isinstance(response, dict) else response.json()

    async def link_username(self) -> bool:
        """
        Linking username to Somnia profile.
        """
        pass
    
    async def confirm_connect_telegram(self) -> bool:
        """
        Confirming Telegram account connection to Somnia profile.
        """
        pass
    
    async def follow_dreamcatalysts(self) -> bool:
        """
        Following Dream Catalysts on X.
        """
        await self.twitter_client.follow(1836667007355207680)
    
    async def follow_0xpaulthomas(self) -> bool:
        """
        Following 0xPaulThomas on X.
        """
        await self.twitter_client.follow(1446133668913692674)

    async def follow_isaacpaaessuman(self) -> bool:
        """
        Following IsaacPaaessuman on X.
        """
        await self.twitter_client.follow(214034931)
    
    async def follow_aleksamil(self) -> bool:
        """
        Following Aleksa on X.
        """
        await self.twitter_client.follow(844482627885240320)
    
    async def follow_MichelleKa70364(self) -> bool:
        """
        Following MichelleKa70364 on X.
        """
        await self.twitter_client.follow(1729899519498670080)
    
    async def follow_numbernine_eth(self) -> bool:
        """
        Following numbernine_eth on X.
        """
        await self.twitter_client.follow(1454085020201652224)
    
    async def follow_JohnGVibes(self) -> bool:
        """
        Following JohnGVibes on X.
        """
        await self.twitter_client.follow(90813976)
    
    async def follow_ironsidecrypto(self) -> bool:
        """
        Following ironsidecrypto on X.
        """
        await self.twitter_client.follow(886054588477915137)
    
    async def follow_OGSomniac(self) -> bool:
        """
        Following OGSomniac on X.
        """
        await self.twitter_client.follow(1804258995198398464)
    
    async def retweet_tweet(self) -> bool:
        """
        Retweeting a tweet.
        """
        await self.twitter_client.tweet_retweeters(1890113814328164850)
    
    async def follow_murmurnika_(self) -> bool:
        """
        Following murmurnika_ on X.
        """
        await self.twitter_client.follow(1133993428646154241)
    
    async def run(self) -> bool:
        """
        Starting the social quests module.
        
        Performs all available social network quests, including:
        - 
        
        Returns:
            True if all quests are successfully completed, False otherwise
        """
        try:
            log.info(f"Account {self.wallet_address} | Starting the socials quests module...")

            if not await self.onboarding():
                log.error(f"Account {self.wallet_address} | Failed to authorize on Somnia")
                return False
            
            user = await self._get_user_info()
            if not user: return False
            
            if not await self._get_twitter_client(): return False
            
            completed_all = True
            
            for attempt in range(3):
                log.info(f"Account {self.wallet_address} | Getting quests...")
                quests_data = await self.get_quests()
                incomplete_quests = self.get_incomplete_quests(quests_data)
                
                if not incomplete_quests:
                    log.success(f"Account {self.wallet_address} | All quests are completed")
                    return True                
                
                quest_handlers = {
                    "13": self.confirm_connect_telegram,
                    "37": self.follow_dreamcatalysts,
                    "27": self.link_username,
                    "30": self.follow_0xpaulthomas,
                    "28": self.follow_isaacpaaessuman,
                    "33": self.follow_aleksamil,
                    "34": self.follow_MichelleKa70364,
                    "29": self.follow_numbernine_eth,
                    "31": self.follow_JohnGVibes,
                    "32": self.follow_ironsidecrypto,
                    "38": self.follow_OGSomniac,
                    "39": self.retweet_tweet,
                    "40": self.follow_murmurnika_,
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