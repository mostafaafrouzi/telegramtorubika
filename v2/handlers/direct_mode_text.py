"""Direct mode: arbitrary plain text -> queued text_message task."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from pyrogram.errors import MessageNotModified
from pyrogram.types import Message

TranslateFn = Callable[[int, str], str]


@dataclass(frozen=True)
class DirectModeTextDeps:
    tr: TranslateFn
    is_direct_mode: Callable[[int], bool]
    get_user_session: Callable[[int], Optional[str]]
    gate_quota: Callable[..., Awaitable[bool]]
    push_task: Callable[[Dict[str, Any]], Dict[str, Any]]
    queue_count_by_session: Callable[[str], int]
    log_event: Callable[..., None]


async def handle_direct_mode_plain_text(
    message: Message,
    user_id: int,
    text: str,
    deps: DirectModeTextDeps,
) -> bool:
    """Returns True when direct mode consumed this message."""
    if not deps.is_direct_mode(user_id):
        return False

    session_name = deps.get_user_session(user_id)
    if not session_name:
        await message.reply_text(deps.tr(user_id, "direct_need_rubika"))
        return True

    task: Dict[str, Any] = {
        "type": "text_message",
        "text": text,
        "rubika_session": session_name,
    }
    if not await deps.gate_quota(message, user_id, task):
        return True

    status = await message.reply_text(deps.tr(user_id, "text_queueing"))
    task["chat_id"] = message.chat.id
    task["status_message_id"] = status.id
    pushed = deps.push_task(task)
    qpos = deps.queue_count_by_session(session_name)
    deps.log_event(
        "task_queued",
        user_id=user_id,
        job_id=pushed.get("job_id"),
        task_type="text_message",
        direct_mode=True,
    )
    try:
        await status.edit_text(
            deps.tr(user_id, "text_queued", job_id=pushed["job_id"], qpos=qpos),
            parse_mode=None,
        )
    except MessageNotModified:
        pass
    return True
