"""Bot bootstrap: client factory and process entry (incremental split from telebot.py)."""

from v2.bot.client_factory import build_bot_client
from v2.bot.register_handlers import register_handlers
from v2.bot.startup import run_bot

__all__ = ["build_bot_client", "register_handlers", "run_bot"]
