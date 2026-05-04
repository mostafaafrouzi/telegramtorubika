"""Callback-query dispatcher extracted from telebot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from pyrogram.errors import MessageNotModified

TranslateFn = Callable[..., str]
AsyncHandler = Callable[..., Awaitable[None]]
AsyncGateQuotaFn = Callable[..., Awaitable[bool]]


@dataclass(frozen=True)
class CallbackRouteDeps:
    tr: TranslateFn
    get_state: Callable[[int], dict]
    set_lang: Callable[[int, str], None]
    set_menu_section_main: Callable[[int], None]
    build_main_menu: Callable[[int], Any]
    queue_manage_handler: AsyncHandler
    clear_queue_handler: AsyncHandler
    get_user_session: Callable[[int], Optional[str]]
    queue_count_by_session: Callable[[str], int]
    failed_count: Callable[[], int]
    recent_failed_detail_text: Callable[[Optional[str], int], str]
    recent_jobs_summary: Callable[[int], str]
    gate_quota: AsyncGateQuotaFn
    queue_push_task: Callable[[dict], dict]
    clear_state: Callable[[int], None]
    log_event: Callable[..., None]


async def dispatch_callback_route(client: Any, callback_query: Any, deps: CallbackRouteDeps) -> bool:
    user_id = callback_query.from_user.id
    data = callback_query.data or ""
    state = deps.get_state(user_id)

    if data.startswith("setlang:"):
        lang = data.split(":", 1)[1]
        if lang in ("fa", "en"):
            deps.set_lang(user_id, lang)
            deps.set_menu_section_main(user_id)
            await callback_query.answer(deps.tr(user_id, "lang_saved"))
            try:
                await callback_query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback_query.message.reply_text(
                deps.tr(user_id, "lang_saved"),
                reply_markup=deps.build_main_menu(user_id),
            )
        return True

    if data.startswith("queue:"):
        action = data.split(":", 1)[1]
        if action == "refresh":
            await callback_query.answer(deps.tr(user_id, "queue_kb_refresh"))
            await deps.queue_manage_handler(
                client,
                callback_query.message,
                edit_existing=True,
                target_user_id=user_id,
            )
            return True
        if action == "clearall":
            await deps.clear_queue_handler(client, callback_query.message, acting_user_id=user_id)
            await callback_query.answer(deps.tr(user_id, "queue_kb_cleared"))
            return True
        if action == "pending":
            session = deps.get_user_session(user_id)
            count = deps.queue_count_by_session(session or "")
            await callback_query.answer(f"Pending: {count}", show_alert=True)
            return True
        if action == "failed":
            await callback_query.answer(f"Failed: {deps.failed_count()}", show_alert=True)
            return True
        if action == "faildetail":
            await callback_query.answer()
            sess = deps.get_user_session(user_id)
            body = deps.recent_failed_detail_text(sess, limit=8)
            title = deps.tr(user_id, "failed_detail_title")
            await callback_query.message.reply_text(
                f"{title}\n\n{body}",
                parse_mode=None,
            )
            return True
        if action == "history":
            await callback_query.answer()
            body = deps.recent_jobs_summary(user_id)
            title = deps.tr(user_id, "recent_jobs_title")
            await callback_query.message.reply_text(f"{title}\n\n{body}")
            return True
        return False

    if data == "confirm_send" and state.get("step") == "await_send_confirm":
        task = state.get("pending_task")
        if not task:
            await callback_query.answer("Pending task not found", show_alert=True)
            return True
        if not await deps.gate_quota(callback_query.message, user_id, task):
            await callback_query.answer("Quota", show_alert=True)
            return True
        anchor = callback_query.message
        task["chat_id"] = anchor.chat.id
        task["status_message_id"] = anchor.id
        task = deps.queue_push_task(task)
        qpos = deps.queue_count_by_session(task.get("rubika_session") or "")
        deps.clear_state(user_id)
        deps.log_event(
            "task_queued",
            user_id=user_id,
            job_id=task.get("job_id"),
            task_type=task.get("type"),
            direct_mode=False,
        )
        try:
            await anchor.edit_text(
                deps.tr(user_id, "text_queued", job_id=task["job_id"], qpos=qpos),
                reply_markup=None,
                parse_mode=None,
            )
        except MessageNotModified:
            pass
        await callback_query.answer("Queued")
        return True

    if data == "cancel_send" and state.get("step") == "await_send_confirm":
        deps.clear_state(user_id)
        deps.log_event("task_confirm_cancelled", user_id=user_id)
        try:
            await callback_query.message.edit_text(
                deps.tr(user_id, "confirm_cancelled"),
                reply_markup=None,
                parse_mode=None,
            )
        except Exception:
            await callback_query.message.reply_text(deps.tr(user_id, "confirm_cancelled"))
        await callback_query.answer("Canceled")
        return True

    return False
