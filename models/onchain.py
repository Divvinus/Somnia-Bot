from dataclasses import dataclass


@dataclass
class Erc20Contract:
    """
    Represents an ERC-20 token contract with its ABI.
    
    Loads the ERC-20 ABI from a JSON file upon initialization.
    """
    abi: list = open("./abi/erc_20.json", "r").read()