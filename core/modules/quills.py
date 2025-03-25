import asyncio
import random
import time

from faker import Faker

from loader import config
from logger import log
from core.api import BaseAPIClient, DiscordClient
from core.wallet import Wallet
from models import Account, ERC20Contract
from utils import show_trx_log, random_sleep, ContractGeneratorData


def _get_headers():
    return {
        'authority': 'quills.fun',
        'accept': '*/*',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'dnt': '1',
        'origin': 'https://quills.fun',
        'pragma': 'no-cache',
        'referer': 'https://quills.fun/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin'
    }
    

class QuillsMessageModule:
    def __init__(self, account: Account):
        self.wallet = Wallet(account.private_key, account.proxy)
        self.api = BaseAPIClient(base_url="https://quills.fun/api", proxy=account.proxy)
        
        self.wallet_address = self.wallet.wallet_address
        self.fake = Faker()
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.api and self.api.session:
            await self.api._safely_close_session(self.api.session)
            self.api.session = None
        
    async def auth(self) -> bool:
        log.info(f"Account {self.wallet_address} | Beginning the authorization process on the site quills.fun...")
        
        message = f"I accept the Quills Adventure Terms of Service at https://quills.fun/terms\n\nNonce: {int(time.time() * 1000)}"
        signature = await self.wallet.get_signature(message)
        
        json_data = {
            'address': self.wallet_address,
            'signature': f"0x{signature}",
            'message': message,
        }
        
        response = await self.api.send_request(
            request_type="POST",
            method="/auth/wallet",
            json_data=json_data,
            headers=_get_headers(),
            verify=False
        )
        
        if response.get("data").get("success"):
            log.success(f"Account {self.wallet_address} | Successfully logged into the site quills.fun")
            return True
        else:
            log.error(f"Account {self.wallet_address} | Unknown error during authentication. Responce: {response}")
            return False
    
    async def mint_message_nft(self):
        log.info(f"Account {self.wallet_address} | Beginning the process of sending a message...")
        
        message = self.fake.word()
        
        json_data = {
            'walletAddress': self.wallet_address,
            'message': message,
        }
        
        response = await self.api.send_request(
            request_type="POST",
            method="/mint-nft",
            json_data=json_data,
            headers=_get_headers(),
            verify=False
        )
        
        if response.get("data").get("success"):
            log.success(f"Account {self.wallet_address} | Successfully minted an nft message: {message}")
            return True
        else:
            log.error(f"Account {self.wallet_address} | Unknown error minted an nft message. Responce: {response}")
            return False
    
    async def run(self):
        log.info(
            f"Account {self.wallet_address} | I perform tasks on sending and minting nft message on the site quills.fun..."
        )
        
        if not await self.auth():
            return False
        
        if not await self.mint_message_nft():
            return False
        
        return True
    

class QuillsDeployContractModule(Wallet):
    def __init__(self, account: Account):
        super().__init__(
            private_key=account.private_key,
            rpc_url=config.somnia_rpc,
            proxy=account.proxy
        )
        self.fake = Faker()
        self.erc20_contract = ERC20Contract()
        self.explorer_url = config.somnia_explorer
        
    async def __aenter__(self):
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def deploy_contract(self) -> tuple[bool, str]:        
        generator = ContractGeneratorData()
        token_details = generator.generate_token_details()
        name = token_details['token_name']
        symbol = token_details['token_symbol']
        total_supply = token_details['total_supply']
        decimals = 18
        initial_supply_wei = total_supply * 10**decimals

        log.info(f"Account {self.wallet_address} | Preparing to deploy a contract {name} ({symbol})")
        
        abi = await self.erc20_contract.get_abi()
        bytecode = await self.erc20_contract.get_bytecode()
        contract = self.eth.contract(abi=abi, bytecode=bytecode)

        deploy_tx = await contract.constructor(name, symbol, initial_supply_wei).build_transaction({
            'from': self.wallet_address,
            'nonce': await self.transactions_count(),
            'gasPrice': await self.eth.gas_price,
        })

        gas_estimate = await self.eth.estimate_gas(deploy_tx)
        deploy_tx['gas'] = int(gas_estimate * 1.2)
        
        success, tx_hash = await self.send_and_verify_transaction(deploy_tx)
        
        if success:
            receipt = await self.eth.wait_for_transaction_receipt(tx_hash)
            deployed_address = receipt['contractAddress']
            log.success(f"Account {self.wallet_address} | Contract deployed successfully at address: {deployed_address}")
            return success, tx_hash
        else:
            log.error(f"Account {self.wallet_address} | Error deploying contract")
            return success, tx_hash

    async def run(self):
        log.info(f"Account {self.wallet_address} | Beginning the contract deployment process...")
        try:            
            status, result = await self.deploy_contract()
            
            show_trx_log(
                address=self.wallet_address,
                trx_type="Deploy ERC20 Contract",
                status=status,
                result=result,
                explorer_url=self.explorer_url
            )
            return status
            
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Error: {str(e)}")
    
    
class QuillsDiscordConnectModule:
    pass
    # def __init__(self, account: Account):
    #     self.wallet = Wallet(account.private_key, account.proxy)
    #     self.api = BaseAPIClient(base_url="https://quills.fun/api", proxy=account.proxy)
        
    #     self.account = account
    #     self.wallet_address = self.wallet.wallet_address
    #     self._discord_worker = None
        
    # @property
    # def discord_worker(self) -> DiscordClient | None:
    #     if self._discord_worker is None and self.account.auth_tokens_discord:
    #         self._discord_worker = DiscordClient(self.account)
    #     return self._discord_worker
    
    # def _get_auth_url(self):
    #     return (
    #         "https://discord.com/api/oauth2/authorize?"
    #         "client_id=1343648099842916402&"
    #         "redirect_uri=https%3A%2F%2Fquills.fun%2Fapi%2Fauth%2Fdiscord%2Fcallback&"
    #         "response_type=code&"
    #         "scope=identify+email+guilds+guilds.members.read&"
    #         f"state={self.wallet_address}"
    #     )
        
    # async def connect_discord_account(self) -> bool:
    #     log.info(f"Account {self.wallet_address} | Trying to link a Discord account to a website quills.fun...")
    #     try:

    #         headers = {
    #             **self._base_headers,
    #             "accept": "*/*",
    #             "referer": f"https://quest.somnia.network/discord?code={code}&state=eyJ0eXBlIjoiQ09OTkVDVF9ESVNDT1JEIn0%3D",
    #         }

    #         response = await self.send_request(
    #             request_type="POST",
    #             method="/auth/socials",
    #             headers=headers,
    #             json_data={"code": code, "provider": "discord"}
    #         )

    #         success = response.get('status_code') == 200 and response.get("success", False)
    #         if success:
    #             log.success(f"Account {self.wallet_address} | Discord account connected successfully")
    #             self._me_info_cache = None
    #         else:
    #             log.error(f"Account {self.wallet_address} | Failed to connect Discord account")
    #             log.error(f"Account {self.wallet_address} | Error: {response}")

    #         return success

    #     except Exception as e:
    #         log.error(f"Account {self.wallet_address} | Error: {e}")
    #         return False