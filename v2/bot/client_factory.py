"""Construct configured Pyrogram Client (parse mode, session name)."""

from __future__ import annotations

from pyrogram import Client
from pyrogram.enums import ParseMode


def build_bot_client(
    session_name: str,
    *,
    api_id: int,
    api_hash: str,
    bot_token: str,
) -> Client:
    app = Client(
        session_name,
        api_id=api_id,
        api_hash=api_hash,
        bot_token=bot_token,
    )
    app.set_parse_mode(ParseMode.MARKDOWN)
    return app
