"""Safe mode slash command (extracted from telebot)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pyrogram.types import Message

TranslateFn = Callable[..., str]


@dataclass(frozen=True)
class SafeModeCommandDeps:
    tr: TranslateFn
    load_settings: Callable[[], dict]
    save_settings: Callable[[dict], None]
    set_waiting_for_zip_password: Callable[[bool], None]


async def handle_safemode(deps: SafeModeCommandDeps, client: Any, message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    uid = message.from_user.id
    if len(args) < 2:
        await message.reply_text(deps.tr(uid, "safemode_usage"))
        return

    action = args[1].strip().lower()
    settings = deps.load_settings()

    if action == "on":
        settings["safe_mode"] = True
        deps.save_settings(settings)
        deps.set_waiting_for_zip_password(True)
        await message.reply_text(deps.tr(uid, "safemode_on"))
        return

    if action == "off":
        settings["safe_mode"] = False
        settings["zip_password"] = ""
        deps.save_settings(settings)
        deps.set_waiting_for_zip_password(False)
        await message.reply_text(deps.tr(uid, "safemode_off"))
        return

    await message.reply_text(deps.tr(uid, "safemode_bad"))
