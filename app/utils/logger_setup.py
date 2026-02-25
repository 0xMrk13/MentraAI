from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[90m",     # gray
        logging.INFO: "\033[94m",      # blue
        logging.WARNING: "\033[93m",   # yellow
        logging.ERROR: "\033[91m",     # red
        logging.CRITICAL: "\033[95m",  # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


class _DropDiscordNoise(logging.Filter):
    DROP_SUBSTRINGS = (
        "logging in using static token",
        "Shard ID",
        "has connected to Gateway",
        "Starting voice websocket",  
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(s in msg for s in self.DROP_SUBSTRINGS)


def setup_logging(
    *,
    log_dir: str = "logs",
    log_file: str = "bot.log",
    console_level: str = "INFO",
    file_level: str = "DEBUG",
) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / log_file

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    for h in list(root.handlers):
        root.removeHandler(h)

    # -----------------
    # Console handler 
    # -----------------
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    ch.setFormatter(_ColorFormatter(fmt="%(message)s"))
    ch.addFilter(_DropDiscordNoise())
    root.addHandler(ch)

    # -----------------
    # File handler 
    # -----------------
    fh = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
    fh.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s [%(filename)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(fh)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

    logging.getLogger("discord").propagate = False
    logging.getLogger("discord.client").propagate = False
    logging.getLogger("discord.gateway").propagate = False
    logging.getLogger("discord.http").propagate = False

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    root.debug("Logging initialized. log_path=%s", log_path.resolve())
