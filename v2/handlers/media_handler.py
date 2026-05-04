"""Media message pipeline extracted from telebot."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from pyrogram.types import Message

TranslateFn = Callable[..., str]


@dataclass(frozen=True)
class MediaHandlerDeps:
    tr: TranslateFn
    get_user_session: Callable[[int], Optional[str]]
    get_media: Callable[[Message], tuple[str, Any]]
    build_download_filename: Callable[[Message, str, Any], str]
    download_dir: Path
    download_progress: Callable[..., Any]
    effective_max_file_bytes: Callable[[int], Optional[int]]
    effective_max_mb_display: Callable[[int], str]
    fmt_mb_bytes: Callable[[int], str]
    load_settings: Callable[[], dict]
    get_batch: Callable[[int], dict]
    set_batch: Callable[[int, dict], None]
    pretty_size: Callable[[int], str]
    queue_or_confirm: Callable[..., Any]
    log_event: Callable[..., None]


async def handle_media_message(deps: MediaHandlerDeps, client: Any, message: Message) -> None:
    user_id = message.from_user.id
    session_name = deps.get_user_session(user_id)
    if not session_name:
        await message.reply_text(deps.tr(user_id, "media_need_rubika"))
        return

    media_type, media = deps.get_media(message)
    if not media:
        await message.reply_text(deps.tr(user_id, "media_bad_type"))
        return

    download_name = deps.build_download_filename(message, media_type, media)
    download_path = deps.download_dir / download_name
    status = await message.reply_text(deps.tr(user_id, "media_download_status"))

    try:
        started_at = time.time()
        progress_state = {"last_update": 0, "user_id": user_id}

        downloaded = await client.download_media(
            message,
            file_name=str(download_path),
            progress=deps.download_progress,
            progress_args=(status, download_name, started_at, progress_state),
        )
        if not downloaded:
            raise RuntimeError("Download failed.")

        downloaded_path = Path(downloaded)
        if not downloaded_path.exists():
            raise RuntimeError("Downloaded file not found.")

        file_size = downloaded_path.stat().st_size
        lim_b = deps.effective_max_file_bytes(user_id)
        if lim_b is not None and file_size > lim_b:
            try:
                downloaded_path.unlink()
            except Exception:
                pass
            await status.edit_text(
                deps.tr(
                    user_id,
                    "file_too_large",
                    max_mb=deps.effective_max_mb_display(user_id),
                    size_mb=deps.fmt_mb_bytes(file_size),
                ),
                parse_mode=None,
            )
            return

        settings = deps.load_settings()
        batch = deps.get_batch(user_id)
        if batch.get("active"):
            files = batch.get("files", [])
            files.append(str(downloaded_path))
            batch["files"] = files
            deps.set_batch(user_id, batch)
            raw_tot = 0
            for pstr in files:
                try:
                    pp = Path(pstr)
                    if pp.exists():
                        raw_tot += pp.stat().st_size
                except OSError:
                    pass
            await status.edit_text(
                deps.tr(
                    user_id,
                    "media_zip_added",
                    n=len(files),
                    raw_mb=deps.fmt_mb_bytes(raw_tot),
                ),
                parse_mode=None,
            )
            return

        task = {
            "type": "local_file",
            "path": str(downloaded_path),
            "caption": message.caption or "",
            "file_name": download_name,
            "file_size": file_size,
            "safe_mode": settings.get("safe_mode", False),
            "zip_password": settings.get("zip_password", ""),
            "rubika_session": session_name,
            "telegram_user_id": user_id,
        }
        await status.edit_text(
            deps.tr(
                user_id,
                "media_file_ready",
                name=download_name,
                size=deps.pretty_size(file_size),
            ),
            parse_mode=None,
        )
        await deps.queue_or_confirm(
            message,
            task,
            deps.tr(user_id, "file_prepared_summary", name=download_name),
            status_message=status,
        )
        deps.log_event(
            "media_prepared",
            user_id=user_id,
            file_name=download_name,
            file_size=file_size,
            task_type="local_file",
        )

    except Exception as e:
        deps.log_event("media_prepare_failed", user_id=user_id, error=str(e))
        await status.edit_text(deps.tr(user_id, "media_error", error=str(e)), parse_mode=None)
