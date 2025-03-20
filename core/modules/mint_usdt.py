from core.wallet import Wallet
from loader import config
from logger import log
from models import Account, UsdtTokensContract
from utils.logger_trx import show_trx_log


class MintUsdtModule(Wallet):
    def __init__(self, account: Account, rpc_url: str) -> None:
        super().__init__(account.private_key, rpc_url, account.proxy)

    async def mint_usdt(self) -> tuple[bool, str] | bool:
        log.info(f"Account {self.wallet_address} | Processing mint 1000 $sUSDT...")

        try:
            contract = await self.get_contract(UsdtTokensContract())
            balance = await contract.functions.balanceOf(self.wallet_address).call()

            if balance > 0:
                msg = f"Account {self.wallet_address} | Mint 1000 $sUSDT had been done before"
                log.success(msg)
                return (True, "before")

            mint_function = contract.functions.mint()
            tx_params = {
                "nonce": await self.transactions_count(),
                "gasPrice": await self.eth.gas_price,
                "from": self.wallet_address,
                "value": 0,
            }

            try:
                gas_estimate = await mint_function.estimate_gas(tx_params)
                tx_params["gas"] = int(gas_estimate * 1.2)
            except Exception as estimate_error:
                log.debug(f"Gas estimate failed: {estimate_error}. Using fallback value")
                tx_params["gas"] = 3_000_000

            transaction = await mint_function.build_transaction(tx_params)
            await self.check_trx_availability(transaction)
            return await self._process_transaction(transaction)

        except Exception as error:
            error_msg = f"Account {self.wallet_address} | Error mint 1000 $sUSDT: {error!s}"
            log.error(error_msg)
            return False

    async def run(self) -> bool:
        mint_result = await self.mint_usdt()

        if isinstance(mint_result, bool):
            return mint_result

        status, result = mint_result

        if "ACCOUNT_DOES_NOT_EXIST" in result:
            warning_msg = (
                f"Account {self.wallet_address} | "
                "First register an account with the Somnia project, then come back"
            )
            log.warning(warning_msg)
            return False

        if result != "before":
            show_trx_log(
                self.wallet_address,
                "Mint 1000 $sUSDT",
                status,
                result,
                config.somnia_explorer
            )
            return True

        return True