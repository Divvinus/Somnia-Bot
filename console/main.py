import os
import sys
import time
import readchar
from typing import Dict, Optional

from art import text2art
from colorama import Fore
import inquirer
from inquirer.themes import GreenPassion
from rich import box
from rich.align import Align
from rich.console import Console as RichConsole
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.console import Group

from loader import config

sys.path.append(os.path.realpath("."))


class Console:
    """Enhanced console interface with animated elements and modern styling."""
    
    MODULES = (
        "🔑 Get referral code",
        "🏆 Account statistics",
        "🤖 Recruiting referrals",
        "👤 Profile",
        "💰 Faucet",
        "💸 Transfer STT",
        "👥 Socials quests 1",
        "🚪 Exit",
    )
    
    MODULES_DATA = {
        "🔑 Get referral code": "get_referral_code",
        "🏆 Account statistics": "account_statistics",
        "🤖 Recruiting referrals": "recruiting_referrals",
        "👤 Profile": "profile",
        "💰 Faucet": "faucet",
        "💸 Transfer STT": "transfer_stt",
        "👥 Socials quests 1": "socials_quests_1",
        "🚪 Exit": "exit"
    }
    
    MODULE_DESCRIPTIONS = {
        "get_referral_code": "Get referral code for the account",
        "account_statistics": "View detailed account metrics and progress",
        "recruiting_referrals": "Automate referral acquisition process",
        "profile": "Set up profile and connect social accounts",
        "faucet": "Claim test tokens from the Somnia faucet",
        "transfer_stt": "Transfer STT tokens between wallets",
        "socials_quests_1": "Complete social media tasks and earn rewards",
        "exit": "Exit the application"
    }
    
    MODULE_COLORS = {
        "get_referral_code": "cyan",
        "account_statistics": "cyan",
        "recruiting_referrals": "green",
        "profile": "blue",
        "faucet": "yellow",
        "transfer_stt": "magenta",
        "socials_quests_1": "red",
        "exit": "white"
    }

    def __init__(self):
        """Initialize console interface with enhanced styling."""
        self.rich_console = RichConsole()
        self._setup_styles()
        self.current_selection = 0
        self.wallet_address = "0x15c27c9B32C7cbaE0cD4eB0f42f45F529bda8aE1"

    def _setup_styles(self) -> None:
        """Initialize advanced styling constants."""
        self.styles = {
            'title': "bold cyan",
            'subtitle': "dim cyan",
            'version': "bold blue",
            'links': "green",
            'border': "yellow",
            'welcome': "[bold green]Welcome to Somnia Bot[/bold green]",
            'powered': "[italic cyan]Powered by Divinus[/italic cyan]",
            'system_info': "[bold yellow]System Information[/bold yellow]",
            'navigation': "[italic]Use arrow keys to navigate and Enter to select[/italic]",
            'donation': "[bold magenta]Support Development[/bold magenta]",
            'donation_address': "bold yellow",
            'selected': "bold white on blue",
            'unselected': "white"
        }

    def show_animated_logo(self) -> None:
        """Display an animated ASCII logo with loading effect without flickering."""
        os.system("cls" if os.name == "nt" else "clear")
        
        logo_text = "Somnia"
        fonts = ["small", "standard", "big"]
        frames = [text2art(logo_text, font=font) for font in fonts]
        
        progress_display = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Loading Somnia Quest Bot...[/bold cyan]"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        task = progress_display.add_task("Loading...", total=100)
        
        def get_combined_display(progress_value):
            frame_idx = (progress_value // 33) % len(frames)
            styled_frame = Text(frames[frame_idx], style=self.styles['title'])
            
            return Group(
                Align.center(styled_frame),
                Text("", style="default"),
                Align.center(progress_display)
            )
        
        with Live(get_combined_display(0), refresh_per_second=10) as live:
            for i in range(0, 101, 5):
                progress_display.update(task, completed=i)
                live.update(get_combined_display(i))
                time.sleep(0.1)

    def show_dev_info(self) -> None:
        """Display developer information with modern styling without flickering."""
        title = text2art("SOMNIA BOT", font="small")
        styled_title = Text(title, style=self.styles['title'])

        version = Text("VERSION: 1.0.0", style=self.styles['version'])
        telegram_channel = Text("Channel: https://t.me/divinus_xyz", style=self.styles['links'])
        telegram_contact = Text("Contact: https://t.me/divinus_py", style=self.styles['links'])
        github = Text("GitHub: https://github.com/Divvinus", style=self.styles['links'])
        
        donation_text = Text("Donations: ", style=self.styles['donation_address'])
        donation_address = Text(f"{self.wallet_address}", style=self.styles['donation_address'])
        
        version.justify = "center"
        telegram_channel.justify = "center"
        telegram_contact.justify = "center"
        github.justify = "center"
        
        main_content = Group(
            styled_title,
            Text(""),
            version,
            Text(""),
            telegram_channel,
            telegram_contact,
            github,
            Text(""),
            Text.assemble(donation_text, donation_address, justify="center")
        )

        dev_panel = Panel(
            main_content,
            border_style=self.styles['border'],
            expand=False,
            title=self.styles['welcome'],
            subtitle=self.styles['powered'],
            width=70
        )

        self.rich_console.print(Align.center(dev_panel))
        print()

    def custom_list_modules(self) -> str:
        """Display enhanced module selection with descriptions without screen flicker."""
        os.system("cls" if os.name == "nt" else "clear")
        
        self.show_dev_info()
        self.display_info()
        
        def get_menu_content():
            """Generate menu content that will be updated dynamically."""
            module_table = Table(
                box=box.ROUNDED,
                border_style="blue",
                title="[bold blue]Available Modules[/bold blue]",
                title_style="bold blue",
                title_justify="center",
                highlight=True,
                width=80
            )
            
            module_table.add_column("", style="dim", width=3)
            module_table.add_column("Module", style="bold white", justify="center")
            module_table.add_column("Description", style="dim white", justify="center")
            
            for i, module_name in enumerate(self.MODULES):
                module_key = self.MODULES_DATA[module_name]
                is_selected = i == self.current_selection
                color = self.MODULE_COLORS.get(module_key, "white")
                
                if is_selected:
                    style_start = "[bold white on blue]"
                    style_end = "[/bold white on blue]"
                else:
                    style_start = f"[bold {color}]"
                    style_end = f"[/bold {color}]"
                    
                indicator = "➤" if is_selected else " "
                description = self.MODULE_DESCRIPTIONS.get(module_key, "")
                
                module_table.add_row(
                    indicator,
                    f"{style_start}{module_name}{style_end}",
                    f"{style_start}{description}{style_end}"
                )
            
            navigation_hint = "[dim italic]↑/↓: Navigate   Enter: Select   Q: Quit[/dim italic]"
            panel = Panel(
                Align.center(module_table),
                border_style="blue",
                subtitle=navigation_hint,
                width=85
            )
            
            return Align.center(panel)
        
        with Live(get_menu_content(), refresh_per_second=10, screen=False) as live:
            while True:
                key = self._get_key_input()
                
                if key == "UP" and self.current_selection > 0:
                    self.current_selection -= 1
                    live.update(get_menu_content())
                elif key == "DOWN" and self.current_selection < len(self.MODULES) - 1:
                    self.current_selection += 1
                    live.update(get_menu_content())
                elif key == "ENTER":
                    return self.MODULES_DATA[self.MODULES[self.current_selection]]
                elif key.upper() == "Q":
                    return "exit"
    
    def _get_key_input(self) -> str:
        """Alternative input method for Linux compatibility"""
        key = readchar.readkey()
        if key == readchar.key.UP:
            return "UP"
        elif key == readchar.key.DOWN:
            return "DOWN"
        elif key == readchar.key.ENTER:
            return "ENTER"
        elif key.lower() == 'q':
            return "Q"
        return "NONE"
            
    def _fallback_input(self) -> str:
        """Fallback for systems where keyboard library doesn't work."""
        self.rich_console.print("\n[dim]Navigation: [↑] Up, [↓] Down, [Enter] Select, [Q] Exit[/dim]")
        user_input = input("Your choice (u/d/e/q): ").lower()
        if user_input == 'u':
            return "UP"
        elif user_input == 'd':
            return "DOWN"
        elif user_input == 'e':
            return "ENTER"
        elif user_input == 'q':
            return "Q"
        return "NONE"
    
    def display_info(self) -> None:
        """Display system configuration with visual enhancement."""
        try:
            layout = Layout()
            layout.split_column(
                Layout(name="header"),
                Layout(name="main"),
                Layout(name="footer")
            )
            
            table = Table(
                title="System Configuration", 
                box=box.ROUNDED, 
                border_style="green",
                title_justify="center"
            )
            table.add_column("Parameter", style="cyan", justify="center")
            table.add_column("Value", style="magenta", justify="center")

            account_count = 0
            threads_count = 0
            delay_min = 0
            delay_max = 0
            has_proxies = False
            
            if hasattr(config, 'accounts'):
                account_count = len(config.accounts)
                has_proxies = any(getattr(account, 'proxy', None) for account in config.accounts)
            
            if hasattr(config, 'threads'):
                threads_count = config.threads
                
            if hasattr(config, 'delay_before_start'):
                delay_min = getattr(config.delay_before_start, 'min', 0)
                delay_max = getattr(config.delay_before_start, 'max', 0)

            table.add_row("Accounts", f"[bold green]{account_count}[/bold green]")
            table.add_row("Threads", f"[bold yellow]{threads_count}[/bold yellow]")
            table.add_row(
                "Delay before start",
                f"[bold cyan]{delay_min}[/bold cyan] - [bold cyan]{delay_max}[/bold cyan] sec",
            )
            
            proxy_status = "[bold green]Enabled[/bold green]" if has_proxies else "[bold red]Disabled[/bold red]"
            table.add_row("Proxies", proxy_status)
            
            status_panel = Panel(
                Align.center(table),
                expand=False,
                border_style="green",
                title=self.styles['system_info'],
                subtitle=self.styles['navigation'],
                width=60
            )
            
            self.rich_console.print(Align.center(status_panel))
            print()
            
        except Exception as e:
            self.rich_console.print(
                Panel(
                    Align.center(f"[yellow]System configuration loading...[/yellow]"),
                    border_style="yellow",
                    width=60
                )
            )
            print()

    def get_module(self) -> Optional[str]:
        """Get selected module from user using inquirer library."""
        questions = [
            inquirer.List(
                "module",
                message=Fore.LIGHTBLACK_EX + "Select the module",
                choices=self.MODULES,
            ),
        ]

        answers = self.prompt(questions)
        return answers.get("module") if answers else None

    @staticmethod
    def prompt(data: list) -> Optional[Dict]:
        """Process user input with theme."""
        return inquirer.prompt(data, theme=GreenPassion())

    def build(self) -> None:
        """Build and display the enhanced console interface with smooth navigation."""
        try:
            self.show_animated_logo()
            
            selected_module = self.custom_list_modules()
            if selected_module:
                config.module = selected_module

                self.rich_console.clear()
                
                if config.module == "exit":
                    self.show_exit_message()
                    sys.exit(0)
                    
        except KeyboardInterrupt:
            self.rich_console.clear()
            self.rich_console.print("\n[yellow]Operation cancelled by user.[/yellow]")
            sys.exit(0)
        except Exception as e:
            print(f"\nError building interface: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def show_exit_message(self) -> None:
        """Show a friendly exit message."""
        message = Panel(
            Align.center(
                "[bold green]Thank you for using Somnia Quest Bot![/bold green]\n\n"
                "[cyan]Visit our Telegram channel for updates:[/cyan]\n"
                "[blue]https://t.me/divinus_xyz[/blue]\n\n"
                "[magenta]Goodbye![/magenta]"
            ),
            border_style="green",
            title="[bold]See you soon![/bold]",
            width=60
        )
        
        self.rich_console.clear()
        self.rich_console.print(Align.center(message))