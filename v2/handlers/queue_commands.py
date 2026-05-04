"""Queue and quick-send slash commands (extracted from telebot)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from v2.core.menu_sections import MenuSection

TranslateFn = Callable[..., str]


@dataclass(frozen=True)
class QueueCommandDeps:
    tr: TranslateFn
    set_menu_section: Callable[[int, MenuSection], None]
    enqueue_rubika_text_message: Callable[[Message, str], Any]
    extract_first_url: Callable[[str], Optional[str]]
    get_user_session: Callable[[int], Optional[str]]
    queue_count_by_session: Callable[[str], int]
    processing_display_for_queue: Callable[[int], str]
    failed_count: Callable[[], int]
    queue_deleted_count: Callable[[], int]
    queue_cancelled_count: Callable[[], int]
    queue_all_tasks: Callable[[], list[dict]]
    queue_remove_tasks_by_session: Callable[[Optional[str]], None]
    mark_deleted: Callable[[dict], None]


async def handle_send_text(deps: QueueCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(deps.tr(uid, "sendtext_usage"))
        return
    await deps.enqueue_rubika_text_message(message, parts[1])


async def handle_send_link(deps: QueueCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(deps.tr(uid, "sendlink_usage"))
        return
    url = deps.extract_first_url(parts[1])
    if not url:
        await message.reply_text(deps.tr(uid, "invalid_link"))
        return
    await deps.enqueue_rubika_text_message(message, url)


async def handle_queue_manage(
    deps: QueueCommandDeps,
    client: Any,
    message: Message,
    edit_existing: bool = False,
    target_user_id: Optional[int] = None,
) -> None:
    user_id = target_user_id if target_user_id is not None else message.from_user.id
    deps.set_menu_section(user_id, MenuSection.PLAN)
    session = deps.get_user_session(user_id)
    pending = deps.queue_count_by_session(session or "")
    proc = deps.processing_display_for_queue(user_id)
    summary = deps.tr(
        user_id,
        "queue_panel",
        pending=pending,
        processing=proc,
        failed=deps.failed_count(),
        deleted=deps.queue_deleted_count(),
        cancelled=deps.queue_cancelled_count(),
    )
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(deps.tr(user_id, "btn_inline_refresh"), callback_data="queue:refresh")],
            [
                InlineKeyboardButton(deps.tr(user_id, "btn_inline_pending"), callback_data="queue:pending"),
                InlineKeyboardButton(deps.tr(user_id, "btn_inline_failed"), callback_data="queue:failed"),
            ],
            [InlineKeyboardButton(deps.tr(user_id, "btn_inline_recent"), callback_data="queue:history")],
            [InlineKeyboardButton(deps.tr(user_id, "btn_inline_faildetail"), callback_data="queue:faildetail")],
            [InlineKeyboardButton(deps.tr(user_id, "btn_inline_clear"), callback_data="queue:clearall")],
        ]
    )
    if edit_existing:
        try:
            await message.edit_text(summary, reply_markup=kb, parse_mode=None)
            return
        except MessageNotModified:
            return
        except Exception:
            pass
    await message.reply_text(summary, reply_markup=kb, parse_mode=None)


async def handle_clear_queue(
    deps: QueueCommandDeps,
    client: Any,
    message: Message,
    acting_user_id: Optional[int] = None,
) -> None:
    uid = acting_user_id if acting_user_id is not None else message.from_user.id
    user_session = deps.get_user_session(uid)
    tasks = [t for t in deps.queue_all_tasks() if t.get("rubika_session") == user_session]
    if not tasks:
        await message.reply_text(deps.tr(uid, "queue_empty"))
        return

    for task in tasks:
        deps.mark_deleted(task)

        old_path = task.get("path")
        if old_path:
            try:
                path = Path(old_path)
                if path.exists():
                    path.unlink()
            except Exception:
                pass

        try:
            await client.edit_message_text(
                chat_id=task["chat_id"],
                message_id=task["status_message_id"],
                text=deps.tr(task.get("chat_id") or uid, "removed_from_queue"),
                parse_mode=None,
            )
        except MessageNotModified:
            pass
        except Exception:
            pass

    deps.queue_remove_tasks_by_session(user_session)
    await message.reply_text(deps.tr(uid, "queue_cleared_all"))
