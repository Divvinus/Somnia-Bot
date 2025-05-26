import os
import sys
import inquirer

from inquirer.themes import GreenPassion
from art import text2art
from colorama import Fore
from bot_loader import config

from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

sys.path.append(os.path.realpath("."))


class Console:
    MODULES = (
        "🏆 Account statistics",
        "🔑 Get referral code",
        "💰 Faucet (Account validity check)",
        "💰 Check native balance",
        "👋 Daily GM",
        "🚀 Quick Swap",
        "🏦 Quick Pool",
        "🔄 Generate routes",
        "📝 Update routes with new modules",
        "📊 View route statistics",
        "📈 View full statistics",
        "▶️  Execute route",
        "🚪 Exit",
    )
    
    MODULES_DATA = {
        "🏆 Account statistics": "account_statistics",
        "🔑 Get referral code": "get_referral_code",
        "💰 Faucet (Account validity check)": "faucet",
        "💰 Check native balance": "check_native_balance",
        "👋 Daily GM": "daily_gm",
        "🚀 Quick Swap": "swap",
        "🏦 Quick Pool": "pool",
        "🔄 Generate routes": "generate_routes",
        "📝 Update routes with new modules": "update_routes",
        "📊 View route statistics": "view_routes",
        "📈 View full statistics": "view_statistics",
        "▶️  Execute route": "execute_route",
        "🚪 Exit": "exit"
    }

    def __init__(self):
        self.rich_console = RichConsole()

    def show_dev_info(self):
        os.system("cls" if os.name == "nt" else "clear")

        title = text2art("Somnia", font="doom")
        styled_title = Text(title, style="cyan")

        telegram = Text("👉 Channel: https://t.me/divinus_xyz 💬", style="green")
        github = Text("👉 GitHub: https://github.com/Divvinus 💻", style="green")

        dev_panel = Panel(
            Text.assemble(styled_title, "\n", telegram, "\n", "\n", github, "\n"),
            border_style="yellow",
            expand=False,
            title="[bold green]Welcome[/bold green]",
            subtitle="[italic]Powered by Divinus[/italic]",
        )

        self.rich_console.print(dev_panel)
        print()

    @staticmethod
    def prompt(data: list):
        answers = inquirer.prompt(data, theme=GreenPassion())
        return answers

    def get_module(self):
        questions = [
            inquirer.List(
                "module",
                message=Fore.LIGHTBLACK_EX + "Select the module",
                choices=self.MODULES,
            ),
        ]

        answers = self.prompt(questions)
        return answers.get("module")

    def display_info(self):
        table = Table(title="System Configuration", box=box.ROUNDED)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("Accounts", str(len(config.accounts)))
        table.add_row("Threads", str(config.threads))
        table.add_row(
            "Delay before start",
            f"{config.delay_before_start.min} - {config.delay_before_start.max} sec",
        )

        panel = Panel(
            table,
            expand=False,
            border_style="green",
            title="[bold yellow]System Information[/bold yellow]",
            subtitle="[italic]Use arrow keys to navigate[/italic]",
        )
        self.rich_console.print(panel)

    def build(self) -> None:
        self.show_dev_info()
        self.display_info()

        module = self.get_module()
        config.module = self.MODULES_DATA[module]