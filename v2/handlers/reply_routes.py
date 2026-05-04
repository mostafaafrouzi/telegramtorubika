"""Dispatch reply-keyboard pseudo-routes produced by menu_engine.resolve_reply_button_route."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, FrozenSet, Optional

from pyrogram.types import Message

from v2.core.menu_sections import MenuSection

ClientRef = Any
MessageHandler = Callable[[ClientRef, Message], Awaitable[None]]
TranslateFn = Callable[[int, str], str]
MenuBuilder = Callable[[int], Any]


@dataclass(frozen=True)
class ReplyRouteDeps:
    """Stable dependency bundle built once in telebot (after handlers are defined)."""

    admin_ids: FrozenSet[int]
    tr: TranslateFn
    set_menu_section: Callable[[int, MenuSection], None]
    set_state_preserving_menu: Callable[..., None]
    menu_handler: MessageHandler
    help_handler: MessageHandler
    log_help_handler: MessageHandler
    rubika_connect_handler: MessageHandler
    rubika_status_handler: MessageHandler
    new_batch_handler: MessageHandler
    done_batch_handler: MessageHandler
    clear_queue_handler: MessageHandler
    queue_manage_handler: MessageHandler
    netstatus_handler: MessageHandler
    admin_handler: MessageHandler
    direct_mode_handler: MessageHandler
    build_rubika_menu: MenuBuilder
    build_files_menu: MenuBuilder
    build_settings_menu: MenuBuilder
    build_admin_menu: MenuBuilder


async def dispatch_reply_keyboard_route(
    client: ClientRef,
    message: Message,
    user_id: int,
    mapped: Optional[str],
    deps: ReplyRouteDeps,
) -> bool:
    """Run handler for mapped reply route. Returns True if consumed."""
    if not mapped:
        return False
    tr = deps.tr
    if mapped == "/menu":
        await deps.menu_handler(client, message)
        return True
    if mapped == "/help":
        await deps.help_handler(client, message)
        return True
    if mapped == "/loghelp":
        await deps.log_help_handler(client, message)
        return True
    if mapped == "/show_rubika_menu":
        deps.set_menu_section(user_id, MenuSection.RUBIKA)
        await message.reply_text(tr(user_id, "rubika_menu_title"), reply_markup=deps.build_rubika_menu(user_id))
        return True
    if mapped == "/show_files_menu":
        deps.set_menu_section(user_id, MenuSection.FILES)
        await message.reply_text(tr(user_id, "files_menu_title"), reply_markup=deps.build_files_menu(user_id))
        return True
    if mapped == "/show_settings_menu":
        deps.set_menu_section(user_id, MenuSection.SETTINGS)
        await message.reply_text(tr(user_id, "settings_menu_title"), reply_markup=deps.build_settings_menu(user_id))
        return True
    if mapped == "/show_admin_menu":
        if user_id in deps.admin_ids:
            deps.set_menu_section(user_id, MenuSection.ADMIN)
            await message.reply_text(tr(user_id, "admin_menu_title"), reply_markup=deps.build_admin_menu(user_id))
        else:
            await message.reply_text(tr(user_id, "admin_denied"))
        return True
    if mapped == "/rubika_connect":
        await deps.rubika_connect_handler(client, message)
        return True
    if mapped == "/rubika_status":
        await deps.rubika_status_handler(client, message)
        return True
    if mapped == "/newbatch":
        await deps.new_batch_handler(client, message)
        return True
    if mapped == "/done":
        await deps.done_batch_handler(client, message)
        return True
    if mapped == "/delall":
        await deps.clear_queue_handler(client, message)
        return True
    if mapped == "/queue":
        await deps.queue_manage_handler(client, message)
        return True
    if mapped == "/netstatus":
        await deps.netstatus_handler(client, message)
        return True
    if mapped == "/admin":
        await deps.admin_handler(client, message)
        return True
    if mapped == "/directmode on":
        message.text = "/directmode on"
        await deps.direct_mode_handler(client, message)
        return True
    if mapped == "/directmode off":
        message.text = "/directmode off"
        await deps.direct_mode_handler(client, message)
        return True
    if mapped == "/quick_send_prompt":
        deps.set_state_preserving_menu(user_id, {"step": "await_quick_message"})
        await message.reply_text(tr(user_id, "prompt_quick_message"))
        return True
    return False
