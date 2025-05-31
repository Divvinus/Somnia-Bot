from .profile import ProfileModule
from .faucet import FaucetModule
from .transfer_stt import TransferSTTModule
from src.api.somnia_client import SomniaClient
from .ping_pong import MintPingPongModule, SwapPingPongModule
from .mint_usdt import MintUsdtModule
from .quills import QuillsMessageModule
from .quets import (
    QuestSomniaHorrorModule,
    QuestRubyScoreModule,
    Quest1BILLIONQUESTModule
)
from .mint_air import MintairDeployContractModule
from .onchain_gm import OnchainGMModule
from .mint_nft import (
    YappersNFTModule, 
    ShannonNFTModule, 
    NerzoNFTModule, 
    SomniNFTModule,
    CommunityNFTModule
)
from .mint_domen import MintDomenModule
from .check_native_balance import CheckNativeBalanceModule
from .daily_gm import GmModule
from .somnia_domain import SomniaDomainsModule
from .quickswap import QuickSwapModule