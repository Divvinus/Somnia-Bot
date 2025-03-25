import time

from faker import Faker

from loader import config
from logger import log
from core.api import BaseAPIClient
from core.wallet import Wallet
from models import Account, ERC20Contract
from utils import show_trx_log, ContractGeneratorData


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
        
    async def _process_api_response(self, response: dict, operation_name: str) -> bool:
        if response.get("data", {}).get("success"):
            log.success(f"Account {self.wallet_address} | Successfully {operation_name}")
            return True
        else:
            log.error(f"Account {self.wallet_address} | Unknown error during {operation_name}. Response: {response}")
            return False
    
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
        
        return await self._process_api_response(response, "logged into the site quills.fun")
    
    async def mint_message_nft(self) -> bool:
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
        
        return await self._process_api_response(response, f"minted an nft message: {message}")
    
    async def run(self) -> bool:
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
            
        except (ValueError, ConnectionError) as e:
            log.error(f"Account {self.wallet_address} | Error during contract deployment: {str(e)}")
            return False
        except Exception as e:
            log.error(f"Account {self.wallet_address} | Unexpected error: {str(e)}")
            return False