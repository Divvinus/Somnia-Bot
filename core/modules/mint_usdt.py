from core.wallet import Wallet
from loader import config
from logger import log
from models import Account, UsdtTokensContract
from utils.logger_trx import show_trx_log


class MintUsdtModule(Wallet):
    def __init__(self, account: Account, rpc_url: str) -> None:
        super().__init__(account.private_key, rpc_url, account.proxy)

    async def mint_usdt(self) -> tuple[bool, str]:
        log.info(f"Account {self.wallet_address} | Processing mint 1000 $sUSDT...")

        try:
            contract = await self.get_contract(UsdtTokensContract())
            balance = await contract.functions.balanceOf(self.wallet_address).call()

            if balance > 0:
                msg = f"Account {self.wallet_address} | Mint 1000 $sUSDT had been done before"
                log.success(msg)
                return True, "before"

            tx_params = await self.build_transaction_params(
                contract.functions.mint()
            )
            return await self._process_transaction(tx_params)

        except Exception as error:
            error_msg = f"Account {self.wallet_address} | Error mint 1000 $sUSDT: {error!s}"
            log.error(error_msg)
            return False, str(error)

    async def run(self) -> tuple[bool, str]:
        status, result = await self.mint_usdt()

        if "ACCOUNT_DOES_NOT_EXIST" in result:
            warning_msg = (
                f"Account {self.wallet_address} | "
                "First register an account with the Somnia project, then come back"
            )
            log.warning(warning_msg)
            return status, "First register an account with the Somnia project, then come back"

        if result != "before":
            show_trx_log(
                self.wallet_address,
                "Mint 1000 $sUSDT",
                status,
                result,
                config.somnia_explorer
            )
            return status, "Successfully minted 1000 $sUSDT"

        return status, result