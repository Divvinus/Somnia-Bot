import telebot
import re

from src.logger import AsyncLogger
from src.wallet import Wallet
from src.models import Account


class SendTgMessage(Wallet, AsyncLogger):
    def __init__(self, account: Account):
        Wallet.__init__(self, account.private_key, account.proxy)
        AsyncLogger.__init__(self)
        
        from bot_loader import config
        self.bot = telebot.TeleBot(config.tg_token)
        self.chat_id = config.tg_id

    async def send_tg_message(self, message_to_send: list[str], disable_notification: bool = False) -> None:
        try:
            markdown_escape_pattern = re.compile(r'([_*\[\]()~`>#+\-=|{}.!])')

            formatted = []
            for line in message_to_send:
                escaped_line = markdown_escape_pattern.sub(r'\\\1', line)
                if any(c in line for c in ['=', '-', '📊', '📈']):
                    formatted.append(f"*{escaped_line}*")
                else:
                    formatted.append(escaped_line)
            
            str_send = '\n'.join(formatted)

            self.bot.send_message(
                self.chat_id, 
                str_send, 
                parse_mode='MarkdownV2', 
                disable_notification=disable_notification
            )
            
            await self.logger_msg(
                msg=f"The message was sent in Telegram", 
                type_msg="success", 
                address=self.wallet_address
            )

        except Exception as error:
            await self.logger_msg(
                msg=f"Telegram | Error API: {error}", type_msg="error", 
                address=self.wallet_address, method_name="send_tg_message"
            )