from dataclasses import dataclass
from functools import cached_property
from typing import Any, Dict, Optional, Union
from pathlib import Path
from core.api import BaseAPIClient
from core.wallet import Wallet
from logger import log
from models import Account
from utils import random_sleep


@dataclass
class SomniaConfig:
    """Configuration for Somnia API"""
    BASE_URL: str = "https://quest.somnia.network"
    API_URL: str = f"{BASE_URL}/api"
    ONBOARDING_URL: str = f"{BASE_URL}"
    DOMAIN: str = "quest.somnia.network"
    MAX_RETRIES: int = 3
    RETRY_DELAY_MIN: int = 2
    RETRY_DELAY_MAX: int = 5

@dataclass
class StatsResponse:
    """Structure of the response with statistics"""
    total_points: int = 0
    total_boosters: int = 0
    final_points: int = 0
    rank: str = "N/A"
    season_id: str = "N/A"
    total_referrals: int = 0
    quests_completed: int = 0
    daily_booster: int = 0
    streak_count: int = 0
    referral_code: str = "N/A"

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'StatsResponse':
        return cls(
            total_points=float(data.get('totalPoints', 0)),
            total_boosters=float(data.get('totalBoosters', 0)),
            final_points=float(data.get('finalPoints', 0)),
            rank=data.get('rank', 'N/A') or 'N/A',
            season_id=data.get('seasonId', 'N/A'),
            total_referrals=int(data.get('totalReferrals', 0)),
            quests_completed=int(data.get('questsCompleted', 0)),
            daily_booster=float(data.get('dailyBooster', 0)),
            streak_count=int(data.get('streakCount', 0)),
            referral_code=data.get('referralCode', 'N/A')
        )

    def __str__(self) -> str:
        return (
            f"{'='*50}\n"
            f"🔗 Referral Code: {self.referral_code}\n"
            f"🏆 Total Points: {self.total_points}\n"
            f"🚀 Total Boosters: {self.total_boosters}\n"
            f"🎯 Final Points: {self.final_points}\n"
            f"📊 Rank: {self.rank}\n"
            f"🔄 Season ID: {self.season_id}\n"
            f"👥 Total Referrals: {self.total_referrals}\n"
            f"✅ Quests Completed: {self.quests_completed}\n"
            f"⚡ Daily Booster: {self.daily_booster}\n"
            f"🔥 Streak Count: {self.streak_count}\n"
            f"{'='*50}"
        )

class SomniaClient:
    """Client for working with Somnia API"""
    
    def __init__(self, account: Account):
        self.account = account
        self.config = SomniaConfig()
        self.wallet = Wallet(account.private_key, account.proxy)
        self.api = BaseAPIClient(base_url=self.config.API_URL, proxy=account.proxy)
        self._authorization_token: Optional[str] = None
        self._me_info_cache: Optional[Dict[str, Any]] = None
        
    @cached_property
    def wallet_address(self) -> str:
        """Cached wallet address"""
        return self.wallet.wallet_address
    
    async def __aenter__(self):
        """Support for async context manager protocol"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.api and self.api.session:
            await self.api._safely_close_session(self.api.session)
            self.api.session = None

    async def get_signature(self, *args, **kwargs) -> str:
        """Getting signature"""
        return await self.wallet.get_signature(*args, **kwargs)

    async def send_request(self, *args, **kwargs) -> Any:
        """Sending request to API"""
        return await self.api.send_request(*args, **kwargs)

    def _get_base_headers(self, auth: bool = True, custom_referer: Optional[str] = None) -> Dict[str, str]:
        """Forming base headers"""
        headers = {
            'authority': self.config.DOMAIN,
            'accept': 'application/json',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'origin': self.config.BASE_URL,
            'referer': f'{self.config.BASE_URL}/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin'
        }
        
        if custom_referer:
            headers['referer'] = custom_referer
        
        if auth and self._authorization_token:
            headers['authorization'] = f'Bearer {self._authorization_token}'
            
        return headers

    async def onboarding(self) -> tuple[bool, str]:
        """Onboarding process"""
        try:
            for attempt in range(self.config.MAX_RETRIES):
                signature = await self.get_signature('{"onboardingUrl":"https://quest.somnia.network"}')
                
                json_data = {
                    'signature': f'0x{signature}',
                    'walletAddress': self.wallet_address,
                }
                
                custom_referer = 'https://quest.somnia.network/connect?redirect=%2F'
                response = await self.send_request(
                    request_type="POST",
                    method="/auth/onboard",
                    json_data=json_data,
                    headers=self._get_base_headers(auth=False, custom_referer=custom_referer),
                    verify=False
                )
                
                if response.get("status_code") == 500:
                    continue
                    
                token = response.get("data").get("token")
                if not token:
                    log.error(f"Account {self.wallet_address} | No token in response")
                    return False, "No token in response 'onboarding'"
                    
                self._authorization_token = token
                return True, "Successfully onboarded"
                
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Onboarding error: {e}")
            return False, str(e)

    async def get_stats(self) -> Optional[StatsResponse]:
        try:
            response = await self.send_request(
                request_type="GET",
                method="/stats",
                headers=self._get_base_headers()
            )
            stats = StatsResponse.from_json(response['data'])
            
            referral_code = await self.get_me_info(get_referral_code=True)
            if referral_code:
                stats.referral_code = referral_code
            
            log.info(f"Account: {self.wallet_address}\n{stats}")
            return stats
            
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Failed to get stats: {e}")
            return None

    async def get_me_info(self, get_referral_code: bool = False) -> tuple[bool, str | dict[str, None]]:
        try:
            if self._me_info_cache is None:
                response = await self.send_request(
                    request_type="GET",
                    method="/users/me",
                    headers=self._get_base_headers(),
                    verify=False
                )
                
                if response.get("status_code") != 200:
                    log.error(f"Account {self.wallet_address} | Server error: {response.get('status_code')}")
                    return False, "Server error"
                    
                if response.get("data") is None:
                    log.error(f"Account {self.wallet_address} | No data in response")
                    return False, "No data in response"

                self._me_info_cache = response.get("data")

            if get_referral_code:
                return self._me_info_cache.get("referralCode")

            return {
                key: None for key in ['username', 'discordName', 'twitterName', 'telegramName', 'imgUrl']
                if self._me_info_cache.get(key) is None
            }

        except Exception as e:
            log.error(f"Account {self.wallet_address} | Failed to get user info: {str(e)}")
            return False, str(e)

    async def activate_referral(self) -> tuple[bool, str]:
        """Activation of referral code"""
        log.info(f"Account {self.wallet_address} | Activating account")
        
        for attempt in range(self.config.MAX_RETRIES):
            try:
                response = await self.send_request(
                    request_type="POST",
                    method="/referrals",
                    headers=self._get_base_headers(),
                    verify=False
                )
                if response.get("status_code") == 200:
                    log.success(f"Account {self.wallet_address} | Account activated")
                    return True, "Successfully activated referral code"
                    
                if response.get("status_code") == 500:
                    log.warning(
                        f"Account {self.wallet_address} | Server error, "
                        f"retrying... (attempt {attempt + 1}/{self.config.MAX_RETRIES})"
                    )
                    await random_sleep(
                        self.wallet_address,
                        self.config.RETRY_DELAY_MIN,
                        self.config.RETRY_DELAY_MAX
                    )
                    continue
                    
                log.error(
                    f"Account {self.wallet_address} | "
                    f"Activation failed: {response}"
                )
                return False, "Activation failed"
                
            except Exception as e:
                log.error(f"Account {self.wallet_address} | Activation error: {str(e)}")
                return False, str(e)
                
        log.warning(
            f"Account {self.wallet_address} | "
            f"Failed after {self.config.MAX_RETRIES} attempts"
        )
        return False, "Activation failed"
    
    async def get_referral_code(self) -> Optional[str]:
        """Getting referral code and saving to file"""
        log.info(f"Getting referral code for account: {self.wallet_address}")
        await self.onboarding()
        referral_code = await self.get_me_info(get_referral_code=True)
        log.success(f"Account {self.wallet_address} | Referral code: {referral_code}")
        
        if referral_code:
            await self.save_referral_code(self.wallet_address, referral_code)
        
        return referral_code

    async def save_referral_code(self, wallet_address: str, referral_code: str) -> None:
        """Save wallet address and referral code to file if it doesn't exist"""
        try:
            file_path = Path("config/data/client/my_refferal_codes.txt")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            data_to_write = f"{wallet_address}:{referral_code}"
            
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    existing_data = f.read()
                    
                if data_to_write in existing_data:
                    log.info(f"Referral code for {wallet_address} already exists in file")
                    return
            
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"{data_to_write}\n")
                
            log.success(f"Saved referral code {referral_code} for wallet {wallet_address} to file")
        except Exception as e:
            log.error(f"Failed to save referral code: {str(e)}")