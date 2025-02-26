import logging
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from colorama import Fore, Style, init
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

init(autoreset=True)

class CustomFormatter(logging.Formatter):
    """
    Formatter with colored output, icons, and timestamps.
    
    Customizes log messages with colors, emojis, and precise timestamps.
    """
    
    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.WHITE,
        'SUCCESS': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }

    ICONS = {
        'DEBUG': '🔍',
        'INFO': '🌐',
        'SUCCESS': '✅',
        'WARNING': '⚠️ ',
        'ERROR': '❌',
        'CRITICAL': '💀'
    }

    def __init__(self, with_colors: bool = True, fmt: str = None):
        """
        Initialize formatter with color options.
        
        Args:
            with_colors: Enable colored output
            fmt: Custom format string
        """
        super().__init__(fmt or "%(asctime)s | %(levelname)-8s | %(message)s")
        self.with_colors = with_colors
        self._start_time = time.time()

    def _get_timestamp(self) -> str:
        """Get current time formatted as HH:MM:SS."""
        return datetime.now().strftime('%H:%M:%S')

    def _get_elapsed_time(self) -> str:
        """Get time elapsed since formatter creation."""
        elapsed = time.time() - self._start_time
        return f"{elapsed:.3f}s"

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with colors, icons and timestamps.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted log message
        """
        level_name = record.levelname
        color = self.COLORS.get(level_name, '')
        icon = self.ICONS.get(level_name, '')
        
        if not record.msg:
            return ''
            
        timestamp = self._get_timestamp()
        elapsed = self._get_elapsed_time()
        
        if self.with_colors:
            header = f"{color}{timestamp}{Style.RESET_ALL}"
            level = f"{color}{level_name:8}{Style.RESET_ALL}"
        else:
            header = timestamp
            level = f"{level_name:8}"
            
        thread_info = ""
        if record.threadName != "MainThread":
            thread_info = f"[Thread: {record.threadName}] "
            
        message = (
            f"{header} | "
            f"{level} | "
            f"{icon} | "
            f"{thread_info}"
            f"{record.getMessage()}"
        )
        
        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"
            
        return message

class Logger:
    """
    Enhanced logger with rich formatting and multiple outputs.
    
    Supports colored console output, file logging, and custom log levels.
    """
    
    def __init__(
        self,
        name: str = "CustomLogger",
        log_file: Optional[Path] = None,
        level: int = logging.INFO,
        with_colors: bool = True,
        rich_logging: bool = True
    ):
        """
        Initialize logger with desired configuration.
        
        Args:
            name: Logger name
            log_file: Optional path for log file
            level: Minimum log level to display
            with_colors: Enable colored output
            rich_logging: Use Rich library for console formatting
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Add SUCCESS level
        logging.SUCCESS = 25  # Between INFO and WARNING
        logging.addLevelName(logging.SUCCESS, 'SUCCESS')
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Console handler setup
        if rich_logging:
            console_handler = RichHandler(
                console=Console(theme=Theme({
                    "info": "cyan",
                    "warning": "yellow",
                    "error": "red",
                    "critical": "red bold"
                })),
                show_time=False,
                show_path=False
            )
        else:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(CustomFormatter(with_colors=with_colors))
            
        self.logger.addHandler(console_handler)
        
        if log_file:
            self._setup_file_handler(log_file)
            
        setattr(self.logger, 'success', self._log_success)

    def _setup_file_handler(self, log_file: Path) -> None:
        """Setup file handler for logging to disk."""
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(CustomFormatter(with_colors=False))
        self.logger.addHandler(file_handler)

    def _log_success(self, message: str, *args, **kwargs) -> None:
        """Log message with SUCCESS level."""
        self.logger.log(logging.SUCCESS, message, *args, **kwargs)

    def remove(self) -> None:
        """Remove all handlers from the logger."""
        self.logger.handlers.clear()

    def add(self, sink, *, colorize: bool = False, format: str = None, rotation: str = None, retention: str = None) -> None:
        """
        Add a handler to the logger with custom options.
        
        Args:
            sink: Output destination (stdout or file path)
            colorize: Enable colored output
            format: Custom format string
            rotation: Log rotation settings
            retention: Log retention period
        """
        handler = None
        
        if sink is sys.stdout:
            handler = logging.StreamHandler(sink)
            handler.setFormatter(CustomFormatter(with_colors=colorize, fmt=format))
        
        elif isinstance(sink, (str, Path)):
            if rotation:
                handler = RotatingFileHandler(
                    sink,
                    maxBytes=1024 * 1024 * 1000,
                    backupCount=7 if retention == "7 days" else 1,
                    encoding='utf-8'
                )
            else:
                handler = logging.FileHandler(sink, encoding='utf-8')
            handler.setFormatter(CustomFormatter(with_colors=False, fmt=format))
        
        if handler:
            self.logger.addHandler(handler)

    @property
    def debug(self):
        """Log message at DEBUG level."""
        return self.logger.debug

    @property
    def info(self):
        """Log message at INFO level."""
        return self.logger.info

    @property
    def success(self):
        """Log message at SUCCESS level."""
        return self.logger.success

    @property
    def warning(self):
        """Log message at WARNING level."""
        return self.logger.warning

    @property
    def error(self):
        """Log message at ERROR level."""
        return self.logger.error

    @property
    def critical(self):
        """Log message at CRITICAL level."""
        return self.logger.critical

    def exception(self, msg: str, *args, **kwargs) -> None:
        """Log exception with traceback at ERROR level."""
        self.logger.exception(msg, *args, **kwargs)


# Create a default configured logger instance
log = Logger(
    name="AppLogger",
    log_file=Path("logs/app.log"),
    level=logging.INFO,
    rich_logging=True
)