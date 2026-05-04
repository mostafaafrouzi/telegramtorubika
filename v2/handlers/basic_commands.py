"""Slash handlers with no Rubika/network/admin coupling (extracted from telebot)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from v2.core.menu_sections import MenuSection

TranslateFn = Callable[..., str]


@dataclass(frozen=True)
class BasicCommandDeps:
    tr: TranslateFn
    remember_chat: Callable[[int], None]
    set_menu_section: Callable[[int, MenuSection], None]
    build_main_menu: Callable[[int], Any]
    app_version: str


async def handle_start(deps: BasicCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.remember_chat(message.chat.id)
    deps.set_menu_section(uid, MenuSection.MAIN)
    await message.reply_text(
        deps.tr(uid, "welcome"),
        reply_markup=deps.build_main_menu(uid),
    )


async def handle_menu(deps: BasicCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    await message.reply_text(
        deps.tr(uid, "menu_intro"),
        reply_markup=deps.build_main_menu(uid),
    )


async def handle_lang(deps: BasicCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("فارسی", callback_data="setlang:fa"),
                InlineKeyboardButton("English", callback_data="setlang:en"),
            ],
        ]
    )
    await message.reply_text(deps.tr(uid, "pick_lang"), reply_markup=kb)


async def handle_help(deps: BasicCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    await message.reply_text(deps.tr(uid, "help_short"))


async def handle_log_help(deps: BasicCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    await message.reply_text(deps.tr(uid, "loghelp_body"))


async def handle_version(deps: BasicCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    await message.reply_text(
        deps.tr(uid, "version_line", version=deps.app_version),
    )
