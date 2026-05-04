"""ZIP batch wizard: await_zip_name -> await_part_mb -> bundle zip -> queue_or_confirm."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from pyrogram.types import Message

TranslateFn = Callable[[int, str], str]


@dataclass(frozen=True)
class ZipBatchWizardDeps:
    tr: TranslateFn
    safe_filename: Callable[[str], str]
    safe_delete_user_message: Callable[[Message], Awaitable[None]]
    edit_wizard: Callable[[int, int, str], Awaitable[None]]
    set_state_preserving_menu: Callable[..., None]
    clear_state: Callable[[int], None]
    clear_batch: Callable[[int], None]
    load_settings: Callable[[], dict]
    make_bundle_zip_local: Callable[..., Path]
    effective_max_file_bytes: Callable[[int], Optional[int]]
    effective_max_mb_display: Callable[[int], str]
    fmt_mb_bytes: Callable[[int], str]
    gate_quota: Callable[..., Awaitable[bool]]
    get_user_session: Callable[[int], Optional[str]]
    pretty_size: Callable[[int], str]
    queue_or_confirm: Callable[..., Awaitable[None]]


async def dispatch_zip_batch_wizard(
    message: Message,
    user_id: int,
    state: dict,
    text: str,
    deps: ZipBatchWizardDeps,
) -> bool:
    """Returns True if the ZIP wizard handled this text message."""
    tr = deps.tr
    step = state.get("step")

    if step == "await_zip_name":
        zip_name = deps.safe_filename(text.strip() or "bundle")
        await deps.safe_delete_user_message(message)
        bf = state.get("batch_files", [])
        fps = [Path(p) for p in bf if Path(p).exists()]
        raw_sum = sum(p.stat().st_size for p in fps)
        prompt_body = (
            tr(user_id, "part_mb_prompt")
            + "\n\n"
            + tr(user_id, "batch_raw_hint", raw_mb=deps.fmt_mb_bytes(raw_sum), n=len(fps))
        )
        await deps.edit_wizard(
            state.get("wizard_chat_id", message.chat.id),
            int(state.get("wizard_message_id", 0) or 0),
            prompt_body,
        )
        deps.set_state_preserving_menu(
            user_id,
            {
                "step": "await_part_mb",
                "zip_name": zip_name,
                "batch_files": state.get("batch_files", []),
                "wizard_message_id": state.get("wizard_message_id"),
                "wizard_chat_id": state.get("wizard_chat_id"),
            },
        )
        return True

    if step == "await_part_mb":
        try:
            part_mb = int(text.strip())
        except Exception:
            await message.reply_text(tr(user_id, "part_mb_invalid"))
            return True
        if part_mb < 50:
            await message.reply_text(tr(user_id, "part_mb_min"))
            return True
        await deps.safe_delete_user_message(message)
        files = state.get("batch_files", [])
        session_name = deps.get_user_session(user_id)
        file_paths = [Path(p) for p in files if Path(p).exists()]
        if not file_paths:
            await message.reply_text(tr(user_id, "zip_no_files"))
            deps.clear_state(user_id)
            deps.clear_batch(user_id)
            return True
        settings = deps.load_settings()
        zip_password = settings.get("zip_password", "") if settings.get("safe_mode", False) else ""
        zip_path = deps.make_bundle_zip_local(file_paths, state.get("zip_name", "bundle"), zip_password)
        total_size = sum(p.stat().st_size for p in file_paths if p.exists())
        zip_sz = zip_path.stat().st_size
        lim_b = deps.effective_max_file_bytes(user_id)
        if lim_b is not None and zip_sz > lim_b:
            try:
                zip_path.unlink()
            except OSError:
                pass
            await message.reply_text(
                tr(
                    user_id,
                    "file_too_large",
                    max_mb=deps.effective_max_mb_display(user_id),
                    size_mb=deps.fmt_mb_bytes(zip_sz),
                ),
                parse_mode=None,
            )
            deps.clear_state(user_id)
            deps.clear_batch(user_id)
            return True
        qt: dict[str, Any] = {"type": "local_file", "file_size": zip_sz, "rubika_session": session_name}
        if not await deps.gate_quota(message, user_id, qt):
            try:
                zip_path.unlink()
            except OSError:
                pass
            deps.clear_state(user_id)
            deps.clear_batch(user_id)
            return True
        if zip_sz > 45 * 1024 * 1024:
            await message.reply_text(tr(user_id, "zip_large_warn"))
        for p in file_paths:
            try:
                p.unlink()
            except OSError:
                pass
        zip_status_msg = None
        try:
            zip_status_msg = await message.reply_document(
                str(zip_path),
                caption=tr(
                    user_id,
                    "zip_ready_caption",
                    n=len(file_paths),
                    insize=deps.pretty_size(total_size),
                    zsize=deps.pretty_size(zip_sz),
                ),
            )
        except Exception:
            zip_status_msg = await message.reply_text(
                tr(
                    user_id,
                    "zip_ready_no_doc",
                    n=len(file_paths),
                    insize=deps.pretty_size(total_size),
                    zsize=deps.pretty_size(zip_sz),
                )
            )
        task = {
            "type": "local_file",
            "path": str(zip_path),
            "file_name": zip_path.name,
            "file_size": zip_sz,
            "part_size_mb": part_mb,
            "rubika_session": session_name,
            "safe_mode": False,
            "zip_password": "",
            "telegram_user_id": user_id,
        }
        deps.clear_state(user_id)
        deps.clear_batch(user_id)
        await deps.queue_or_confirm(
            message,
            task,
            tr(user_id, "zip_queue_summary", name=zip_path.name),
            status_message=zip_status_msg,
        )
        return True

    return False
