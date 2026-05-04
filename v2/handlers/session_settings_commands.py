"""Rubika session slash commands, direct mode toggle, and network status (extracted from telebot)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pyrogram.types import Message

from v2.core.menu_sections import MenuSection

TranslateFn = Callable[..., str]
LogEventFn = Callable[..., None]


@dataclass(frozen=True)
class SessionSettingsCommandDeps:
    tr: TranslateFn
    get_user_session: Callable[[int], Optional[str]]
    check_rubika_session_sync: Callable[[str], tuple[bool, str]]
    set_menu_section: Callable[[int, MenuSection], None]
    set_state_preserving_menu: Callable[..., None]
    log_event: LogEventFn
    set_direct_mode: Callable[[int, bool], None]
    build_settings_menu: Callable[[int], Any]
    build_main_menu: Callable[[int], Any]
    load_network_snapshot: Callable[[], dict]


async def handle_rubika_status(deps: SessionSettingsCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    session_name = deps.get_user_session(uid)
    if not session_name:
        await message.reply_text(deps.tr(uid, "rubika_not_connected"))
        return
    await message.reply_text(deps.tr(uid, "rubika_checking"))
    ok_session, details = await asyncio.to_thread(deps.check_rubika_session_sync, session_name)
    if ok_session:
        await message.reply_text(deps.tr(uid, "rubika_ok", session=session_name, details=details))
    else:
        await message.reply_text(
            deps.tr(uid, "rubika_invalid_session", session=session_name, details=details)
        )


async def handle_rubika_connect(deps: SessionSettingsCommandDeps, client: Any, message: Message) -> None:
    user_id = message.from_user.id
    current_session = deps.get_user_session(user_id)
    if current_session:
        await message.reply_text(
            deps.tr(user_id, "rubika_already_connected", session=current_session)
        )
    deps.set_menu_section(user_id, MenuSection.RUBIKA)
    deps.set_state_preserving_menu(user_id, {"step": "await_phone"})
    deps.log_event("rubika_connect_started", user_id=user_id)
    await message.reply_text(deps.tr(user_id, "rubika_ask_phone"))


async def handle_direct_mode(deps: SessionSettingsCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text(deps.tr(uid, "directmode_usage"))
        return
    action = args[1].strip().lower()
    if action == "on":
        deps.set_direct_mode(uid, True)
        await message.reply_text(deps.tr(uid, "direct_on"), reply_markup=deps.build_settings_menu(uid))
        return
    if action == "off":
        deps.set_direct_mode(uid, False)
        await message.reply_text(
            deps.tr(uid, "direct_off"),
            reply_markup=deps.build_main_menu(uid),
        )
        return
    await message.reply_text(deps.tr(uid, "directmode_usage"))


async def handle_netstatus(deps: SessionSettingsCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    data = deps.load_network_snapshot()
    mode = data.get("mode", "unknown")
    reason = data.get("reason", "") or "---"
    updated = data.get("updated_at", 0)
    await message.reply_text(
        deps.tr(uid, "net_status", mode=mode, reason=reason, updated=updated),
        parse_mode=None,
    )
