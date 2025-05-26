import asyncio
import time
from typing import Self, Union, Any

from src.wallet import Wallet
from bot_loader import config
from src.logger import AsyncLogger
from src.models import (
    Account, 
    QuickSwapRouterContract,
    QuickSwapFactoryContract,
    QuickSwapAddressPairContract,
    QuickPoolContract
)
from src.utils import show_trx_log, random_sleep
from config.settings import (
    MAX_RETRY_ATTEMPTS, 
    RETRY_SLEEP_RANGE,
    PAIR_QUICK_SWAP,
    TOKENS_DATA_SOMNIA,
    LOWER_TOKEN_PERCENTAGE_QUICK_POOL,
    PRICE_RANGE_PERCENT_QUICK_POOL
)


class QuickSwapModule(Wallet, AsyncLogger):
    def __init__(self, account: Account) -> None:
        Wallet.__init__(self, account.private_key, config.somnia_rpc, account.proxy)
        AsyncLogger.__init__(self)
        self.slippage = 1

    async def __aenter__(self) -> Self:
        await Wallet.__aenter__(self)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await Wallet.__aexit__(self, exc_type, exc_val, exc_tb)
        
    async def check_config_quick_swap(self, pair_swap) -> tuple[bool, str]:
        await self.logger_msg("Checking swap configuration", "info", self.wallet_address)
        
        has_active_pairs = False
        for pair_id, swap_data in pair_swap.items():
            if len(swap_data) != 3:
                error_msg = f"Pair {pair_id}: Invalid format. Expected [token_out, token_in, min_amount]"
                await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
                return False, error_msg

            token_out, token_in, min_amount = swap_data

            if not (token_out or token_in):
                if min_amount != 0:
                    error_msg = f"Pair {pair_id}: Empty pair requires min_amount = 0"
                    await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
                    return False, error_msg
                continue

            has_active_pairs = True
            
            if not all((token_out, token_in)):
                error_msg = f"Pair {pair_id}: Partial configuration. Out: '{token_out}', In: '{token_in}'"
                await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
                return False, error_msg

            if not all(isinstance(t, str) for t in (token_out, token_in)):
                error_msg = f"Pair {pair_id}: Invalid token types. Must be strings"
                await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
                return False, error_msg

            if token_out.lower() == token_in.lower():
                error_msg = f"Pair {pair_id}: Same tokens ({token_out}/{token_in})"
                await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
                return False, error_msg

            if not isinstance(min_amount, (int, float)) or min_amount <= 0:
                error_msg = f"Pair {pair_id}: Invalid percentage {min_amount}. Must be > 0"
                await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
                return False, error_msg

        if not has_active_pairs:
            error_msg = "No active swap pairs configured. Add at least one valid pair"
            await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
            return False, error_msg

        if (balance := await self.human_balance()) <= 0:
            error_msg = "No $STT tokens in wallet. Deposit required"
            await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_swap")
            return False, error_msg

        return True, "Config validation passed"
    
    async def swap(self, name_token1, name_token2, amount_in) -> tuple[bool, str]:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                contract_router = await self.get_contract(QuickSwapRouterContract())
                contract_router_address = self._get_checksum_address(QuickSwapRouterContract().address)  
                contract_factory = await self.get_contract(QuickSwapFactoryContract())
                 
                address_token1 = self._get_checksum_address(TOKENS_DATA_SOMNIA.get(name_token1))
                address_token2 = self._get_checksum_address(TOKENS_DATA_SOMNIA.get(name_token2))
                
                deadline = int(time.time() + 12 * 3600)
                
                await self.logger_msg("Get the address of the pool", "info", self.wallet_address)
                if name_token1 == "STT":
                    pair_address = await contract_factory.functions.poolByPair(self._get_checksum_address(TOKENS_DATA_SOMNIA.get("WSTT")), address_token2).call()
                elif name_token2 == "STT":
                    pair_address = await contract_factory.functions.poolByPair(address_token1, self._get_checksum_address(TOKENS_DATA_SOMNIA.get("WSTT"))).call()
                else:
                    pair_address = await contract_factory.functions.poolByPair(address_token1, address_token2).call()
                    
                pool_contract = await self.get_contract(QuickSwapAddressPairContract(self._get_checksum_address(pair_address)))
                await self.logger_msg("Calculating the amounts", "info", self.wallet_address)
                sqrt_price, _, last_fee, _, _, _, _ = await pool_contract.functions.safelyGetStateOfAMM().call()

                if name_token1 == "STT":
                    token_in = self._get_checksum_address(TOKENS_DATA_SOMNIA.get("WSTT"))
                    token_out = address_token2
                elif name_token2 == "STT":
                    token_in = address_token1
                    token_out = self._get_checksum_address(TOKENS_DATA_SOMNIA.get("WSTT"))
                else:
                    token_in = address_token1
                    token_out = address_token2

                zero_to_one = token_in < token_out

                price = (sqrt_price / (2 ** 96)) ** 2
                if zero_to_one:
                    amount_out = amount_in * price * (1 - last_fee / 1000000)
                else:
                    amount_out = amount_in / price * (1 - last_fee / 1000000)

                amount_out_min = int(amount_out * (1 - 0.5/100))
                
                if token_in != "0x0000000000000000000000000000000000000000":
                    status, result = await self._check_and_approve_token(token_in, contract_router_address, amount_in)
                    if not status:
                        return False, result    
                
                await self.logger_msg("Sending the transaction", "info", self.wallet_address)
                if name_token1 == "STT":        
                    tx_params = await self.build_transaction_params(
                        contract_router.functions.exactInputSingle([
                            token_in,
                            token_out,
                            "0x0000000000000000000000000000000000000000",
                            self.wallet_address,
                            deadline,
                            amount_in,
                            amount_out_min,
                            0
                            ]),
                        value=amount_in
                    )
                
                elif name_token2 == "STT":
                    exact_input_params = {
                        "tokenIn": token_in, 
                        "tokenOut": token_out,
                        "deployer": "0x0000000000000000000000000000000000000000",
                        "recipient": "0x0000000000000000000000000000000000000000",
                        "deadline": deadline,
                        "amountIn": amount_in, 
                        "amountOutMinimum": amount_out_min,
                        "limitSqrtPrice": 0
                    }
                    exact_input_calldata = contract_router.encode_abi(
                        'exactInputSingle',
                        args=[(
                            exact_input_params["tokenIn"],
                            exact_input_params["tokenOut"],
                            exact_input_params["deployer"],
                            exact_input_params["recipient"],
                            exact_input_params["deadline"],
                            exact_input_params["amountIn"],
                            exact_input_params["amountOutMinimum"],
                            exact_input_params["limitSqrtPrice"]
                        )]
                    )
                    
                    unwrap_calldata = contract_router.encode_abi(
                        'unwrapWNativeToken',
                        args=[amount_out_min, self.wallet_address]
                    )

                    multicall_args = [exact_input_calldata, unwrap_calldata]

                    tx_params = await self.build_transaction_params(
                        contract_function=contract_router.functions.multicall(multicall_args)
                    )
                else:
                    error_msg =f"For the pair {name_token1} - {name_token2} there is not enough liquidity in the pools, choose another pair"
                    return False, error_msg
                    
                await self.logger_msg(
                    f"Sending a transaction swap {name_token1} - {name_token2} on QuickSwap", "info", self.wallet_address
                )
                
                status, tx_hash = await self._process_transaction(tx_params)
                
                await show_trx_log(self.wallet_address, f"Swap {name_token1} - {name_token2} on QuickSwap", status, tx_hash)
                
                if status:
                    return status, tx_hash
            except Exception as e:
                error_msg = f"Error swap {name_token1} - {name_token2} on QuickSwap: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "swap")
                
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)
                
        return False, f"Failed swap {name_token1} - {name_token2} on QuickSwap after {MAX_RETRY_ATTEMPTS} attempts"
        
    async def run_quick_swap(self, pair_swap = PAIR_QUICK_SWAP) -> tuple[bool, str]:
        await self.logger_msg(f"Starting swap tokens on QuickSwap", "info", self.wallet_address)
        
        status, msg = await self.check_config_quick_swap(pair_swap)
        if not status: 
            return status, msg
        
        failed_swaps = []
        success_count = 0
        
        for key, (name_token1, name_token2, percentage) in pair_swap.items():
            try:
                await self.logger_msg(f"Processing pair №{key}: {name_token1} - {name_token2}", "info", self.wallet_address)
                
                token1_data = TOKENS_DATA_SOMNIA.get(name_token1)
                token2_data = TOKENS_DATA_SOMNIA.get(name_token2)
                
                if not token1_data or not token2_data:
                    error = f"Token data not found for pair #{key}"
                    await self.logger_msg(error, "error", self.wallet_address)
                    failed_swaps.append(error)
                    continue
                
                balance = await self.token_balance(token1_data)
                if balance <= 0:
                    error = f"Insufficient {name_token1} balance for pair #{key}"
                    await self.logger_msg(error, "error", self.wallet_address)
                    failed_swaps.append(error)
                    continue
                    
                amount_in = int(balance * (percentage / 100))
                
                success, result_msg = await self.swap(name_token1, name_token2, amount_in)
                
                if not success: 
                    await self.logger_msg(f"Swap failed: {result_msg}", "error", self.wallet_address)
                    failed_swaps.append(f"Pair #{key}: {result_msg}")
                else: 
                    success_count += 1
                    await self.logger_msg(f"Swap successful: {name_token1} -> {name_token2}", "success", self.wallet_address)
                    
            except Exception as e:
                error = f"Unexpected error in pair #{key}: {str(e)}"
                await self.logger_msg(error, "error", self.wallet_address)
                failed_swaps.append(error)
        
        total_pairs = len(pair_swap)
        summary = f"Completed {success_count}/{total_pairs} swaps. Failed: {len(failed_swaps)}"
        
        if success_count == 0:
            error_msg = f"{summary}\nAll swaps failed."
            if failed_swaps:
                error_msg += "\nErrors:\n" + "\n".join(failed_swaps)
            return False, error_msg
        else:
            success_msg = summary
            if failed_swaps:
                success_msg += "\nErrors:\n" + "\n".join(failed_swaps)
            return True, success_msg
    
    async def check_config_quick_pool(self, lower_token_persentage, range_ticks) -> tuple[bool, str]:
        await self.logger_msg("Checking add liquidity configuration", "info", self.wallet_address)
        
        config_checks = [
            ("LOWER_TOKEN_PERCENTAGE_QUICK_POOL", lower_token_persentage, lambda x: x > 0),
            ("PRICE_RANGE_PERCENT_QUICK_POOL", range_ticks, lambda x: x > 0),
        ]

        errors = []
        for name, value, condition in config_checks:
            if not condition(value):
                error_msg = f"You have not specified the correct value for {name} in the configs. Please specify the correct value and try again"
                errors.append(error_msg)
                await self.logger_msg(
                    error_msg, "error", self.wallet_address, "check_config_quick_pool"
                )

        if errors:
            return False, "\n".join(errors)

        elif (balance := await self.human_balance()) <= 0:
            error_msg = "No $STT tokens in wallet. Deposit required"
            await self.logger_msg(error_msg, "error", self.wallet_address, "check_config_quick_pool")
            return False, error_msg

        return True, "Config validation passed"
    
    async def get_token_data(self, symbol_token_a: str = "STT", symbol_token_b: str = "USDC") -> dict:
        await self.logger_msg(f"Get tokens data", "info", self.wallet_address)
        try:
            token_address_a = self._get_checksum_address(TOKENS_DATA_SOMNIA.get(symbol_token_a))
            token_address_b = self._get_checksum_address(TOKENS_DATA_SOMNIA.get(symbol_token_b))
            
            decimals_token_a, decimals_token_b = await asyncio.gather(
                self.get_decimals(token_address_a),
                self.get_decimals(token_address_b),
            )
            return {
                "token_a": {
                    "symbol": "STT",
                    "address": token_address_a,
                    "decimals": decimals_token_a
                },
                "token_b": {
                    "symbol": "USDC",
                    "address": token_address_b,
                    "decimals": decimals_token_b
                }
            }
        except Exception as e:
            error_msg = f"Get token data error: {str(e)}"
            await self.logger_msg(
                error_msg, "error", self.wallet_address, "get_token_data"
            )
            return {'error': error_msg}
    
    async def get_input_amount(
        self,
        token_a_data: dict,
        token_b_data: dict,
        percentage: float = LOWER_TOKEN_PERCENTAGE_QUICK_POOL
    ) -> tuple[bool, Union[float, str], str]:
        await self.logger_msg(f"Get input amount", "info", self.wallet_address)
        try:
            price_stt = 0.115
            price_usdc = 1
            
            balances = await asyncio.gather(
                self.token_balance(token_a_data.get('address')),
                self.token_balance(token_b_data.get('address'))
            ) 
            converted = await asyncio.gather(
                self.convert_amount_from_decimals(balances[0], token_a_data.get('address')),
                self.convert_amount_from_decimals(balances[1], token_b_data.get('address'))
            )

            usd_values = (converted[0] * price_stt, converted[1] * price_usdc)
            
            min_index = 0 if usd_values[0] <= usd_values[1] else 1
            low_name = (token_a_data.get('symbol'), token_b_data.get('symbol'))[min_index]
            low_balance = converted[min_index]

            amount = low_balance * (percentage / 100)
            if amount <= 0:
                error_msg = f"Invalid {low_name} amount: {amount:.6f}"
                await self.logger_msg(error_msg, "error", self.wallet_address, "get_input_amount")
                return False, error_msg, low_name

            return True, amount, low_name

        except Exception as e:
            error_msg = f"{token_a_data.get('symbol')}/{token_b_data.get('symbol')} calculation error: {str(e)}"
            await self.logger_msg(error_msg, "error", self.wallet_address, "get_input_amount")
            return False, error_msg, ""
        
    async def calculate_token_pair(self, token_a_data, token_b_data, input_amount, input_token, pool_contract):
        await self.logger_msg(f"Calculate amount", "info", self.wallet_address)
        try:
            slot0 = await pool_contract.functions.safelyGetStateOfAMM().call()
            sqrt_price_x96 = slot0[0]
            
            price = (sqrt_price_x96 / (2**96)) ** 2
            price_adjusted = price * (10**int(token_a_data.get('decimals')) / 10**int(token_b_data.get('decimals')))
            
            is_sorted = token_a_data["address"].lower() < token_b_data["address"].lower()
            if not is_sorted:
                price_adjusted = 1 / price_adjusted
            
            is_token_a_input = token_a_data['symbol'] == input_token
            
            if is_token_a_input:
                amount_a = input_amount
                amount_b = input_amount * price_adjusted
            else:
                amount_b = input_amount
                amount_a = input_amount / price_adjusted
            
            return {
                'amount_a': amount_a,
                'amount_b': amount_b
            }
        except Exception as e:
            await self.logger_msg(f"Calculation error: {str(e)}", "error", self.wallet_address, "calculate_token_pair")
            return {'error': f'Calculation error: {str(e)}'}
    
    async def calculate_ticks(
        self,
        pool_contract,
        price_range_percent: float = LOWER_TOKEN_PERCENTAGE_QUICK_POOL
    ) -> tuple[bool, dict[str, Any]] | tuple[bool, str]:
        await self.logger_msg(f"Calculate ticks", "info", self.wallet_address)
        try:
            slot0 = await pool_contract.functions.safelyGetStateOfAMM().call()
            tick_spacing = await pool_contract.functions.tickSpacing().call()
            current_tick = slot0[1]

            current_tick = slot0[1]
            if price_range_percent <= 0:
                raise ValueError(f"Invalid price range percentage: {price_range_percent}")

            tick_range = int(abs(current_tick) * (price_range_percent / 100))
            tick_lower = ((current_tick - tick_range) // tick_spacing) * tick_spacing
            tick_upper = ((current_tick + tick_range) // tick_spacing) * tick_spacing

            if tick_lower >= tick_upper:
                tick_lower, tick_upper = (
                    (current_tick // tick_spacing - 1) * tick_spacing,
                    (current_tick // tick_spacing + 1) * tick_spacing
                )

            return True, {
                "current_tick": current_tick,
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "tick_spacing": tick_spacing
            }
        except Exception as e:
            error_data = f"Error when calculating ticks: {str(e)}"
            await self.logger_msg(error_data, "error", self.wallet_address, "calculate_ticks")
            return False, error_data
        
    async def run_quick_pool(
        self, 
        lower_token_persentage = LOWER_TOKEN_PERCENTAGE_QUICK_POOL,
        range_ticks = PRICE_RANGE_PERCENT_QUICK_POOL
    ) -> tuple[bool, str]:
        await self.logger_msg(f"Starting add liquidity on QuickSwap", "info", self.wallet_address)
        
        status, msg = await self.check_config_quick_pool(lower_token_persentage, range_ticks)
        if not status: return status, msg
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                contract = await self.get_contract(QuickPoolContract())
                contract_factory = await self.get_contract(QuickSwapFactoryContract())

                tokens_data = await self.get_token_data()
            
                if 'error' in tokens_data:
                    return False, tokens_data['error']
                token_a_data = tokens_data["token_a"]
                token_b_data = tokens_data["token_b"]

                status, input_amount, low_token_name = await self.get_input_amount(token_a_data, token_b_data)
                if not status: return False, input_amount
                
                pair_address = await contract_factory.functions.poolByPair(self._get_checksum_address(TOKENS_DATA_SOMNIA.get("WSTT")), token_b_data["address"]).call()
                pool_contract = await self.get_contract(QuickSwapAddressPairContract(self._get_checksum_address(pair_address)))
                
                pair_data = await self.calculate_token_pair(token_a_data, token_b_data, input_amount, low_token_name, pool_contract)
                if 'error' in pair_data:
                    return False, pair_data['error']
                amount_a = pair_data['amount_a']
                amount_b = pair_data['amount_b']

                amount_a_wei = int(amount_a * (10 ** int(token_a_data['decimals'])))
                amount_b_wei = int(amount_b * (10 ** int(token_b_data['decimals'])))

                status, ticks_data = await self.calculate_ticks(pool_contract)
                if not status: return False, ticks_data

                amount_a_min = int(amount_a_wei * (1 - self.slippage / 100))
                amount_b_min = int(amount_b_wei * (1 - self.slippage / 100))

                is_token_a_lower = token_a_data["address"].lower() < token_b_data["address"].lower()
                token0_address = token_a_data["address"] if is_token_a_lower else token_b_data["address"]
                token1_address = token_b_data["address"] if is_token_a_lower else token_a_data["address"]
                amount0 = amount_a_wei if is_token_a_lower else amount_b_wei
                amount1 = amount_b_wei if is_token_a_lower else amount_a_wei
                amount0_min = amount_a_min if is_token_a_lower else amount_b_min
                amount1_min = amount_b_min if is_token_a_lower else amount_a_min

                native_token_address = TOKENS_DATA_SOMNIA["STT"].lower()
                npm_address = self._get_checksum_address(QuickPoolContract().address)
                for token_address, amount in [(token0_address, amount0), (token1_address, amount1)]:
                    if token_address.lower() != native_token_address and amount > 0:
                        status, result = await self._check_and_approve_token(token_address, npm_address, amount)
                        if not status:
                            return False, result
                        await self.logger_msg(f"Approval for {token_address}: {result}", "info", self.wallet_address)

                mint_params = {
                    "token0": self._get_checksum_address("0x4a3bc48c156384f9564fd65a53a2f3d534d8f2b7"),
                    "token1": token1_address,
                    "deployer": "0x0000000000000000000000000000000000000000",
                    "tickLower": ticks_data['tick_lower'],
                    "tickUpper": ticks_data['tick_upper'],
                    "amount0Desired": amount0,
                    "amount1Desired": amount1,
                    "amount0Min": amount0_min,
                    "amount1Min": amount1_min,
                    "recipient": self.wallet_address,
                    "deadline": int(time.time()) + 1800
                }
                
                mint_args = (
                    mint_params['token0'],
                    mint_params['token1'],
                    mint_params['deployer'],
                    mint_params['tickLower'],
                    mint_params['tickUpper'],
                    mint_params['amount0Desired'],
                    mint_params['amount1Desired'],
                    mint_params['amount0Min'],
                    mint_params['amount1Min'],
                    mint_params['recipient'],
                    mint_params['deadline']
                )
                mint_data = contract.encode_abi('mint', args=[mint_args])
                refund_data = "0x41865270" 

                value = amount0 if token0_address.lower() == native_token_address else (
                    amount1 if token1_address.lower() == native_token_address else 0
                )

                tx_params = await self.build_transaction_params(
                    contract_function=contract.functions.multicall([mint_data, refund_data]),
                    value=value
                )
                
                await self.logger_msg(
                    f"Sending transaction. Adding liquidity: {token_a_data['symbol']} - {token_b_data['symbol']}",
                    "info", self.wallet_address
                )
                status, tx_hash = await self._process_transaction(tx_params)
                await show_trx_log(
                    self.wallet_address,
                    f"Add liquidity: {token_a_data['symbol']} - {token_b_data['symbol']}",
                    status, tx_hash,
                )
                if status:
                    return status, tx_hash

            except Exception as e:
                error_msg = f"Error Add liquidity: {str(e)}"
                await self.logger_msg(error_msg, "error", self.wallet_address)
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    return False, error_msg
                await random_sleep(self.wallet_address, *RETRY_SLEEP_RANGE)

        return False, f"Error Add liquidity: {token_a_data['symbol']} - {token_b_data['symbol']} after {MAX_RETRY_ATTEMPTS} attempts"