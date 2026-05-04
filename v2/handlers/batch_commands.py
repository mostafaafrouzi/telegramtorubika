"""Batch slash commands for multi-file zip flow (extracted from telebot)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from pyrogram.types import Message

from v2.core.menu_sections import MenuSection

TranslateFn = Callable[..., str]


@dataclass(frozen=True)
class BatchCommandDeps:
    tr: TranslateFn
    set_batch: Callable[[int, dict], None]
    get_batch: Callable[[int], dict]
    set_menu_section: Callable[[int, MenuSection], None]
    build_files_menu: Callable[[int], Any]
    set_state_preserving_menu: Callable[[int, dict], None]


async def handle_new_batch(deps: BatchCommandDeps, client: Any, message: Message) -> None:
    deps.set_batch(
        message.from_user.id,
        {
            "active": True,
            "files": [],
            "created_at": int(time.time()),
        },
    )
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.FILES)
    await message.reply_text(
        deps.tr(uid, "newbatch_ok"),
        reply_markup=deps.build_files_menu(uid),
    )


async def handle_done_batch(deps: BatchCommandDeps, client: Any, message: Message) -> None:
    batch = deps.get_batch(message.from_user.id)
    files = batch.get("files", [])
    uid = message.from_user.id
    if not batch.get("active") or not files:
        await message.reply_text(deps.tr(uid, "done_no_batch"))
        return
    wizard = await message.reply_text(deps.tr(uid, "zip_name_prompt"))
    deps.set_state_preserving_menu(
        message.from_user.id,
        {
            "step": "await_zip_name",
            "batch_files": files,
            "wizard_message_id": wizard.id,
            "wizard_chat_id": message.chat.id,
        },
    )
