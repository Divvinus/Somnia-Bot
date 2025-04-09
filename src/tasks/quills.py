import time

from faker import Faker
from contextlib import asynccontextmanager

from bot_loader import config
from src.logger import AsyncLogger
from src.api import BaseAPIClient
from src.wallet import Wallet
from src.models import Account, ERC20Contract
from src.utils import show_trx_log, ContractGeneratorData, random_sleep


def _get_headers() -> dict[str, str]:
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
    

class QuillsMessageModule(Wallet, AsyncLogger):
    def __init__(self, account: Account):
        Wallet.__init__(self, account.private_key, account.proxy)
        AsyncLogger.__init__(self)
        
        self._api = BaseAPIClient(base_url="https://quills.fun/api", proxy=account.proxy)
        self.fake = Faker()
    
    @property
    def api(self) -> BaseAPIClient:
        return self._api

    @api.setter
    def api(self, value: BaseAPIClient) -> None:
        self._api = value
        
    async def __aenter__(self):
        return self
    
    @asynccontextmanager
    async def api_context(self):
        try:
            yield self.api
        finally:
            pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.api and hasattr(self.api, "session") and self.api.session and not self.api.session.closed:
            if hasattr(self.api, "_safely_close_session"):
                await self.api._safely_close_session(self.api.session)
            else:
                await self.api.session.close()
            self.api.session = None
        pass
    
    async def _process_api_response(self, response: dict, operation_name: str) -> tuple[bool, str]:
        if response.get("data", {}).get("success"):
            await self.logger_msg(
                msg=f"Successfully {operation_name}", 
                type_msg="success", address=self.wallet_address
            )
            return True, "Successfully completed operation"
        
        else:
            await self.logger_msg(
                msg=f"Unknown error during {operation_name}. Response: {response}", 
                type_msg="error", address=self.wallet_address, method_name="_process_api_response"
            )
            return False, "Unknown error"
    
    async def auth(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Beginning the authorization process on the site quills.fun...", 
            type_msg="info", address=self.wallet_address
        )
        
        message = f"I accept the Quills Adventure Terms of Service at https://quills.fun/terms\n\nNonce: {int(time.time() * 1000)}"
        signature = await self.get_signature(message)
        
        json_data = {
            'address': self.wallet_address,
            'signature': f"0x{signature}",
            'message': message,
        }
        
        async with self.api_context() as api:
            response = await api.send_request(
                request_type="POST",
                method="/auth/wallet",
                json_data=json_data,
                headers=_get_headers(),
                verify=False
            )
        
        return await self._process_api_response(response, "logged into the site quills.fun")

    async def mint_message_nft(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"Beginning the process of sending a message...", 
            type_msg="info", address=self.wallet_address
        )
        
        message = self.fake.word()
        
        json_data = {
            'walletAddress': self.wallet_address,
            'message': message,
        }
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                await self.logger_msg(
                    msg=f"Attempt to mint a message {attempt}/{max_attempts}", 
                    type_msg="info", address=self.wallet_address
                )
                
                async with self.api_context() as api:
                    response = await api.send_request(
                        request_type="POST",
                        method="/mint-nft",
                        json_data=json_data,
                        headers=_get_headers(),
                        verify=False
                    )
                
                status, result = await self._process_api_response(response, f"minted an nft message: {message}")
                if status:
                    return status, result
                    
                if attempt < max_attempts:
                    await random_sleep(self.wallet_address)
            except Exception as e:
                await self.logger_msg(
                    msg=f"Error during minting a message (attempt {attempt}): {str(e)}", 
                    type_msg="error", address=self.wallet_address, method_name="mint_message_nft"
                )
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
        
        await self.logger_msg(
            msg=f"All attempts to mint a message have been exhausted", 
            type_msg="error", address=self.wallet_address, method_name="mint_message_nft"
        )
        return False, "Failed to mint an nft message"
    
    async def run(self) -> tuple[bool, str]:
        await self.logger_msg(
            msg=f"I perform tasks on sending and minting nft message on the site quills.fun...", 
            type_msg="info", address=self.wallet_address
        )
        
        if not await self.auth():
            return False, "Failed to authorize on the site quills.fun"
        
        return await self.mint_message_nft()
    

class QuillsDeployContractModule(Wallet, AsyncLogger):
    def __init__(self, account: Account):
        Wallet.__init__(
            self, 
            account.private_key, 
            config.somnia_rpc, 
            account.proxy
        )
        AsyncLogger.__init__(self)
        
        self.fake = Faker()
        self.erc20_contract = ERC20Contract()
        self.explorer_url = config.somnia_explorer
        
    async def __aenter__(self):
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

        await self.logger_msg(
            msg=f"Preparing to deploy a contract {name} ({symbol})", 
            type_msg="info", address=self.wallet_address
        )
        
        abi = await self.erc20_contract.get_abi()
        bytecode = await self.erc20_contract.get_bytecode()
        contract = self.eth.contract(abi=abi, bytecode=bytecode)

        deploy_tx = await contract.constructor(name, symbol, initial_supply_wei).build_transaction({
            'from': self.wallet_address,
            'nonce': await self.get_nonce(),
            'gasPrice': await self.eth.gas_price,
        })

        gas_estimate = await self.eth.estimate_gas(deploy_tx)
        deploy_tx['gas'] = int(gas_estimate * 1.2)
        
        result, tx_hash = await self.send_and_verify_transaction(deploy_tx)
        
        if result:
            receipt = await self.eth.wait_for_transaction_receipt(tx_hash)
            deployed_address = receipt['contractAddress']
            await self.logger_msg(
                msg=f"Contract deployed successfully at address: {deployed_address}", 
                type_msg="success", address=self.wallet_address
            )
            return result, tx_hash
        else:
            await self.logger_msg(
                msg=f"Error deploying contract", type_msg="error",
                address=self.wallet_address, method_name="deploy_contract"
            )
            return result, tx_hash

    async def run(self):
        await self.logger_msg(
            msg=f"Beginning the contract deployment process...", 
            type_msg="info", address=self.wallet_address
        )
        try:            
            status, result = await self.deploy_contract()
            
            await show_trx_log(
                address=self.wallet_address,
                trx_type="Deploy ERC20 Contract",
                status=status,
                result=result,
                explorer_url=self.explorer_url
            )
            return status, result
            
        except (ValueError, ConnectionError) as e:
            await self.logger_msg(
                msg=f"Error during contract deployment: {str(e)}", 
                type_msg="error", address=self.wallet_address, method_name="run"
            )
            return False, str(e)
        except Exception as e:
            await self.logger_msg(
                msg=f"Unexpected error: {str(e)}", 
                type_msg="error", address=self.wallet_address, method_name="run"
            )
            return False, str(e)