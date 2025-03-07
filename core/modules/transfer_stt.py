"""Module for checking Reddio verification tasks."""

from typing import Any, TypeAlias
from core.api import BaseAPIClient
from models import Account
from logger import log


JsonDict: TypeAlias = dict[str, Any]

account: Account = Account()
api: BaseAPIClient = BaseAPIClient(proxy=account.proxy)

async def check_verify_task(
    wallet_address: str,
    faucet: bool | None = None,
    transferred: bool | None = None,
    bridged: bool | None = None
) -> bool | None:
    """
    Check the status of verification tasks for a given wallet address.

    Args:
        wallet_address (str): The wallet address to check.
        faucet (bool | None): Check faucet claim status.
        transferred (bool | None): Check daily transfer status.
        bridged (bool | None): Check daily bridge status.

    Returns:
        bool | None: The status of the requested task, or None if an error occurs.
    """
    headers: JsonDict = {
        'authority': 'points-mainnet.reddio.com',
        'accept': 'application/json, text/plain, */*',
        'cache-control': 'no-cache',
        'dnt': '1',
        'origin': 'https://points.reddio.com',
        'pragma': 'no-cache',
        'referer': 'https://points.reddio.com/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
    }
    
    params: JsonDict = {'wallet_address': wallet_address}

    try:
        response = await api.send_request(
            request_type="GET",
            url="https://points-mainnet.reddio.com/v1/userinfo",
            headers=headers,
            params=params,
        )

        response_data: JsonDict = response.json()

        if response_data.get("status") != "OK":
            return None
        
        user_data: JsonDict = response_data.get("data", {})

        if faucet is not None:
            return bool(user_data.get("devnet_faucet_claimed", False))
        if transferred is not None:
            return bool(user_data.get("devnet_daily_transferred", False))
        if bridged is not None:
            return bool(user_data.get("devnet_daily_bridged", False))

        return None

    except Exception as error:
        log.error(f"Error parsing response: {error}")
        return None