import re
import random
from faker import Faker

class ContractGeneratorData:
    def __init__(self):
        self.fake = Faker()

    def generate_contract_name(self) -> str:
        word = self.fake.word()
        contract_name = ''.join(x.capitalize() for x in word.split())
        contract_name = re.sub(r'[^a-zA-Z]', '', contract_name)
        return contract_name

    def generate_token_details(self) -> dict:
        return {
            'token_name': f"{self.fake.company()}",
            'token_symbol': self.generate_token_symbol(),
            'total_supply': self.generate_total_supply()
        }

    def generate_token_symbol(self, max_length: int = 5) -> str:
        symbol = ''.join(self.fake.random_uppercase_letter() for _ in range(min(max_length, 5)))
        return symbol

    def generate_total_supply(self) -> int:
        round_multipliers = [1000, 10_000, 100_000, 1_000_000]
        base_numbers = [1, 5, 10, 25, 50, 100]
        base = random.choice(base_numbers)
        multiplier = random.choice(round_multipliers)
        total_supply = base * multiplier
        return max(10_000, min(total_supply, 1_000_000))