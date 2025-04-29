from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

from src.api import BaseAPIClient
from src.exceptions.api_exceptions import (
    APIClientError,
    APIClientSideError,
    APIServerSideError,
)
from src.exceptions.somnia_exceptions import (
    SomniaAPIError,
    SomniaAuthError,
    SomniaClientError,
    SomniaOnboardingError,
    SomniaReferralError,
    SomniaServerError,
    SomniaStatsError,
)
from src.models import Account
from src.utils import random_sleep
from src.wallet import Wallet


@dataclass(frozen=True)
class SomniaConfig:
    """
    Configuration constants for Somnia API interactions.
    """
    BASE_URL: str = "https://quest.somnia.network"
    API_URL: str = f"{BASE_URL}/api"
    ONBOARDING_URL: str = BASE_URL
    DOMAIN: str = "quest.somnia.network"
    MAX_RETRIES: int = 3
    RETRY_DELAY_MIN: int = 2
    RETRY_DELAY_MAX: int = 5
    DATA_DIR: Path = Path("config/data/client")
    REFERRAL_FILE: Path = DATA_DIR / "my_referral_codes.txt"


@dataclass
class StatsResponse:
    """
    Data model for user statistics.
    """
    total_points: float = 0.0
    total_boosters: float = 0.0
    final_points: float = 0.0
    rank: str = "N/A"
    season_id: str = "N/A"
    total_referrals: int = 0
    quests_completed: int = 0
    daily_booster: float = 0.0
    streak_count: int = 0
    referral_code: str = "N/A"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "StatsResponse":
        return cls(
            total_points=float(data.get("totalPoints", 0)),
            total_boosters=float(data.get("totalBoosters", 0)),
            final_points=float(data.get("finalPoints", 0)),
            rank=data.get("rank") or "N/A",
            season_id=data.get("seasonId", "N/A"),
            total_referrals=int(data.get("totalReferrals", 0)),
            quests_completed=int(data.get("questsCompleted", 0)),
            daily_booster=float(data.get("dailyBooster", 0)),
            streak_count=int(data.get("streakCount", 0)),
            referral_code=data.get("referralCode", "N/A"),
        )

    def __str__(self) -> str:
        sep = "=" * 50
        return (
            f"\n🔗 Referral Code: {self.referral_code}\n"
            f"🏆 Total Points: {self.total_points}\n"
            f"🚀 Total Boosters: {self.total_boosters}\n"
            f"🎯 Final Points: {self.final_points}\n"
            f"📊 Rank: {self.rank}\n"
            f"🔄 Season ID: {self.season_id}\n"
            f"👥 Total Referrals: {self.total_referrals}\n"
            f"✅ Quests Completed: {self.quests_completed}\n"
            f"⚡ Daily Booster: {self.daily_booster}\n"
            f"🔥 Streak Count: {self.streak_count}\n{sep}"
        )


class SomniaClient(Wallet):
    """
    Client for interacting with Somnia API, including onboarding,
    stats retrieval, and referral management.
    """

    def __init__(self, account: Account) -> None:
        super().__init__(account.private_key, account.proxy)
        self._account = account
        self._config = SomniaConfig()
        self._api: BaseAPIClient | None = None
        self._token: str | None = None
        self._me_info_cache: dict[str, Any] | None = None

    @property
    def api(self) -> BaseAPIClient:
        if not self._api:
            raise SomniaClientError(
                "API client not initialized. Use 'async with SomniaClient(...)'."
            )
        return self._api

    async def __aenter__(self) -> "SomniaClient":
        await super().__aenter__()
        self._api = BaseAPIClient(
            base_url=self._config.API_URL,
            proxy=self._account.proxy,
        )
        await self._api.__aenter__()
        return self

    async def __aexit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> None:
        if self._api:
            await self._api.__aexit__(exc_type, exc_val, exc_tb)
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def send_request(
        self, *args: Any, **kwargs: Any
    ) -> Any:
        """
        Wraps BaseAPIClient.send_request to map API exceptions.
        """
        try:
            return await self.api.send_request(*args, **kwargs)
        except APIServerSideError as e:
            raise SomniaServerError(
                f"Server error: {e}", e.response_data
            )
        except APIClientSideError as e:
            raise SomniaAPIError(
                f"Client-side API error: {e}", e.response_data
            )
        except APIClientError as e:
            raise SomniaAPIError(f"API client error: {e}")

    def _build_headers(
        self,
        auth: bool = True,
        referer: str | None = None,
    ) -> dict[str, str]:
        """
        Constructs HTTP headers for requests.
        """
        headers = {
            "authority": self._config.DOMAIN,
            "accept": "application/json",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": self._config.BASE_URL,
            "referer": referer or f"{self._config.BASE_URL}/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        if auth and self._token:
            headers["authorization"] = f"Bearer {self._token}"
        return headers

    async def onboarding(self) -> tuple[bool, str]:
        """
        Performs user onboarding, retrieving authorization token.
        Retries up to MAX_RETRIES on server errors.
        """
        for attempt in range(1, self._config.MAX_RETRIES + 1):
            try:
                signature = await self.get_signature('{"onboardingUrl":"https://quest.somnia.network"}')                
                data = {"signature": f"0x{signature}", "walletAddress": self.wallet_address}
                headers = self._build_headers(
                    auth=False,
                    referer=f"{self._config.BASE_URL}/connect?redirect=%2F",
                )
                response = await self.send_request(
                    request_type="POST",
                    method="/auth/onboard",
                    json_data=data,
                    headers=headers,
                    verify=False,
                )
                code = response.get("status_code")
                if code == 500:
                    if attempt == self._config.MAX_RETRIES:
                        raise SomniaServerError(
                            "Server error during onboarding", response
                        )
                    await random_sleep(
                        self.wallet_address,
                        self._config.RETRY_DELAY_MIN,
                        self._config.RETRY_DELAY_MAX,
                    )
                    continue
                token = response.get("data", {}).get("token")
                if not token:
                    raise SomniaAuthError("Auth token missing")
                self._token = token
                return True, "Successfully onboarded"
            except (SomniaServerError, SomniaAuthError) as err:
                if attempt == self._config.MAX_RETRIES:
                    raise SomniaOnboardingError(str(err))
                await random_sleep(
                    self.wallet_address,
                    self._config.RETRY_DELAY_MIN,
                    self._config.RETRY_DELAY_MAX,
                )
            except Exception as err:
                raise SomniaOnboardingError(f"Onboarding error: {err}")

    async def get_stats(self) -> StatsResponse:
        """
        Retrieves user statistics and updates referral code if available.
        """
        try:
            response = await self.send_request(
                request_type="GET",
                method="/stats",
                headers=self._build_headers(),
            )
            data = response.get("data")
            if not data:
                raise SomniaStatsError("No stats data returned")
            stats = StatsResponse.from_json(data)
            ref = await self.get_me_info(get_referral_code=True)
            if isinstance(ref, str):
                stats.referral_code = ref
            return stats
        except SomniaStatsError:
            raise
        except Exception as err:
            raise SomniaStatsError(f"Stats retrieval failed: {err}")

    async def get_me_info(
        self, get_referral_code: bool = False
    ) -> Union[dict[str, Any], str]:
        """
        Fetches or returns cached user profile info.
        If get_referral_code=True, returns referral code string.
        Otherwise, returns dict of missing fields.
        """
        if self._me_info_cache is None:
            response = await self.send_request(
                request_type="GET",
                method="/users/me",
                headers=self._build_headers(),
                verify=False,
            )
            if response.get("status_code") != 200 or not response.get("data"):
                raise SomniaAPIError("Failed to fetch user info", response)
            self._me_info_cache = response["data"]
        if get_referral_code:
            return self._me_info_cache.get("referralCode", "")
        return {
            field: None
            for field in (
                "username",
                "discordName",
                "twitterName",
                "telegramName",
                "imgUrl",
            )
            if self._me_info_cache.get(field) is None
        }

    async def activate_referral(self) -> str:
        """
        Activates user referral code with retries on server error.
        """
        for attempt in range(1, self._config.MAX_RETRIES + 1):
            try:
                response = await self.send_request(
                    request_type="POST",
                    method="/referrals",
                    headers=self._build_headers(),
                    verify=False,
                )
                code = response.get("status_code")
                if code == 200:
                    return "Referral activated"
                if code == 500:
                    if attempt == self._config.MAX_RETRIES:
                        raise SomniaServerError(
                            "Server error activating referral", response
                        )
                    await random_sleep(
                        self.wallet_address,
                        self._config.RETRY_DELAY_MIN,
                        self._config.RETRY_DELAY_MAX,
                    )
                    continue
                raise SomniaReferralError(f"Activation failed: {response}")
            except (SomniaServerError, SomniaReferralError) as err:
                if attempt == self._config.MAX_RETRIES:
                    raise
        raise SomniaReferralError("Referral activation failed after retries")

    async def get_referral_code(self) -> str:
        """
        Onboards user if needed and returns referral code, saving it to file.
        """
        try:
            await self.onboarding()
            code = await self.get_me_info(get_referral_code=True)
            if not isinstance(code, str) or not code:
                raise SomniaReferralError("No referral code available")
            self._save_referral_code(self.wallet_address, code)
            return code
        except Exception as err:
            raise SomniaReferralError(f"Referral code retrieval failed: {err}")

    def _save_referral_code(self, wallet_address: str, code: str) -> None:
        """
        Saves unique referral code per wallet to a file.
        """
        try:
            self._config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = self._config.REFERRAL_FILE
            entry = f"{wallet_address}:{code}\n"
            if path.exists() and entry in path.read_text(encoding="utf-8"):
                return
            path.write_text(entry, encoding="utf-8", append=False)
        except Exception as err:
            raise SomniaClientError(f"Saving referral code failed: {err}")