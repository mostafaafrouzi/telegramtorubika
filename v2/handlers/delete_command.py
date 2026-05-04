"""Delete/cancel queue item slash command (extracted from telebot)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from pyrogram.types import Message


@dataclass(frozen=True)
class DeleteCommandDeps:
    queue_all_tasks: Callable[[], list[dict]]
    queue_remove_task: Callable[..., Optional[dict]]
    was_deleted: Callable[..., bool]
    cancel_job: Callable[[str], None]
    mark_deleted: Callable[[dict], None]


async def handle_delete_one(deps: DeleteCommandDeps, client: Any, message: Message) -> None:
    job_id = None
    reply_message_id = None

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        job_id = parts[1].strip()

    if message.reply_to_message:
        reply_message_id = message.reply_to_message.id

    tasks = deps.queue_all_tasks()

    if not tasks:
        if job_id and deps.was_deleted(job_id=job_id):
            await message.reply_text("این مورد قبلاً از صف حذف شده است.")
            return

        if reply_message_id and deps.was_deleted(message_id=reply_message_id):
            await message.reply_text("این مورد قبلاً از صف حذف شده است.")
            return

        if job_id:
            deps.cancel_job(job_id)
            await message.reply_text("لغو ثبت شد.\n\n")
            return

        await message.reply_text("موردی برای حذف در صف پیدا نشد.")
        return

    removed = deps.queue_remove_task(job_id=job_id, message_id=reply_message_id)

    if removed:
        deps.mark_deleted(removed)

        old_path = removed.get("path")
        if old_path:
            try:
                path = Path(old_path)
                if path.exists():
                    path.unlink()
            except Exception:
                pass

        try:
            await client.edit_message_text(
                chat_id=removed["chat_id"],
                message_id=removed["status_message_id"],
                text="این مورد از صف حذف شد.",
            )
        except Exception:
            pass

        await message.reply_text("از صف حذف شد.")
        return

    if job_id and deps.was_deleted(job_id=job_id):
        await message.reply_text("این مورد قبلاً از صف حذف شده است.")
        return

    if reply_message_id and deps.was_deleted(message_id=reply_message_id):
        await message.reply_text("این مورد قبلاً از صف حذف شده است.")
        return

    if job_id:
        deps.cancel_job(job_id)
        await message.reply_text("دستور لغو ثبت شد.")
        return
