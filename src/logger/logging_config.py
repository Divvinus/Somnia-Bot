import os
import sys
import time
import asyncio
from pathlib import Path
from typing import Literal

import aiofiles
from aiologger import Logger
from aiologger.levels import LogLevel
from aiologger.handlers.base import Handler
from colorama import init, Fore, Style

init(autoreset=True)

ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
LOGS_FILE_PATH = os.path.join(ROOT_DIR, "logs")


class FileFormatter:
    def format(self, record) -> str:
        formatted_time = time.strftime(
            "%H:%M:%S", 
            time.localtime(record.created)
        )
        levelname = record.levelname
        
        if record.levelname == "INFO":
            msg_parts = record.msg.split(" ", 1)
            if msg_parts and msg_parts[0].lower() == "[success]":
                levelname = "SUCCESS"
                record.msg = msg_parts[1] if len(msg_parts) > 1 else ""
        
        max_level_length = 8
        padding = " " * (max_level_length - len(levelname))
        
        return (
            f"[{formatted_time}] | [{record.name}] | "
            f"[{record.filename}:{record.lineno}] | "
            f"[{levelname}]{padding} | {record.msg}"
        )


class AsyncLevelFileHandler(Handler):
    def __init__(self, base_name: str = "file", level=LogLevel.DEBUG) -> None:
        super().__init__(level=level)
        self.base_name = base_name
        self.file_path = os.path.join(LOGS_FILE_PATH, f"{base_name}.log")
        self.formatter = FileFormatter()
        self._initialized = False

    async def initialize(self) -> None:
        if not os.path.exists(LOGS_FILE_PATH):
            os.makedirs(LOGS_FILE_PATH, exist_ok=True)
        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def emit(self, record) -> None:
        if not self.initialized:
            await self.initialize()
        message = self.formatter.format(record)
        async with aiofiles.open(self.file_path, mode="a", encoding="utf-8") as f:
            await f.write(message + "\n")

    async def close(self) -> None:
        self._initialized = False


class ColoredFormatter:
    LEVEL_COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.WHITE,
        "SUCCESS": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.MAGENTA + Style.BRIGHT,
    }

    def format(self, record) -> str:
        formatted_time = time.strftime(
            "%H:%M:%S", 
            time.localtime(record.created)
        )
        levelname = record.levelname
        level_color = self.LEVEL_COLORS.get(levelname, Fore.WHITE)

        if record.levelname == "INFO":
            msg_parts = record.msg.split(" ", 1)
            if msg_parts and msg_parts[0].lower() == "[success]":
                levelname = "SUCCESS"
                level_color = self.LEVEL_COLORS["SUCCESS"]
                record.msg = msg_parts[1] if len(msg_parts) > 1 else ""

        max_level_length = 8
        padding = " " * (max_level_length - len(levelname))

        time_part = f"{Fore.CYAN}[{formatted_time}]{Style.RESET_ALL}"
        name_part = f"{Fore.WHITE}[{record.name}]{Style.RESET_ALL}"
        level_part = f"{level_color}[{levelname}]{padding}{Style.RESET_ALL}"
        msg_part = f"{level_color}{record.msg}{Style.RESET_ALL}"

        return (
            f"{time_part} | {name_part} | "
            f"{level_part} | {msg_part}"
        )


class AsyncConsoleHandler(Handler):
    def __init__(self, level=LogLevel.DEBUG) -> None:
        super().__init__(level=level)
        self.formatter = ColoredFormatter()
        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def emit(self, record) -> None:
        message = self.formatter.format(record)
        sys.stdout.write(message + "\n")
        sys.stdout.flush()
        await asyncio.sleep(0)

    async def close(self) -> None:
        self._initialized = False


class AsyncLogger:
    def __init__(
        self,
        name: str = "Somnia Bot",
        file_base_name: str = "app_log"
    ) -> None:
        self._logger = Logger(name=name, level=LogLevel.INFO)

        if not os.path.exists(LOGS_FILE_PATH):
            os.makedirs(LOGS_FILE_PATH, exist_ok=True)

        console_handler = AsyncConsoleHandler(level=LogLevel.DEBUG)
        file_handler = AsyncLevelFileHandler(base_name=file_base_name, level=LogLevel.DEBUG)
        
        self._logger.add_handler(console_handler)
        self._logger.add_handler(file_handler)

    async def logger_msg(
        self,
        msg: str = "",
        type_msg: Literal["info", "error", "success", "warning", "debug"] = "info",
        account_name: str | None = "Account",
        address: str | None = None,
        class_name: str | None = None,
        method_name: str | None = None,
    ) -> None:
        if class_name is None:
            class_name = self.__class__.__name__
            if class_name == "AsyncLogger" and type(self) != AsyncLogger:
                class_name = type(self).__name__

        info = self._build_info(
            account_name,
            address,
            class_name,
            method_name
        )
        full_msg = f"{info} {msg}"
        
        log_method = {
            "success": self._logger.info,
            "info": self._logger.info,
            "error": self._logger.error,
            "warning": self._logger.warning,
            "debug": self._logger.debug
        }[type_msg]

        prefix = "[success] " if type_msg == "success" else ""
        await log_method(f"{prefix}{full_msg}")

    def _build_info(
        self,
        account_name: str | None,
        address: str | None,
        class_name: str | None,
        method_name: str | None,
    ) -> str:
        info_parts = []
        if account_name:
            info_parts.append(f"[{account_name}]")
        if address:
            info_parts.append(f"[{address}]")
        if class_name:
            info_parts.append(f"[{class_name}]")
        if method_name:
            info_parts.append(f"[{method_name}]")
        return " | ".join(info_parts)

    def get_logger(self) -> Logger:
        return self._logger