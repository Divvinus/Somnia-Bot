from .profile import ProfileModule
from .faucet import FaucetModule
from .transfer_stt import TransferSTTModule
from src.api.somnia_client import SomniaClient
from .ping_pong import MintPingPongModule, SwapPingPongModule
from .mint_usdt import MintUsdtModule
from .quills import QuillsMessageModule
from .quets import (
    QuestSharingModule,
    QuestSocialsModule, 
    QuestDarktableModule, 
    QuestPlaygroundModule,
    QuestDemonsModule,
    QuestGamingFrenzyModule,
    QuestSomniaGamingRoomModule,
    QuestMulletCopModule,
    QuestIntersectionCopModule
)
from .mint_air import MintairDeployContractModule
from .onchain_gm import OnchainGMModule
from .mint_nft import YappersNFTModule, ShannonNFTModule, NerzoNFTModule
from .mint_domen import MintDomenModule