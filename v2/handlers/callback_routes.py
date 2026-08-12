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
    count_tasks_for_user: Callable[[int], int]
    failed_count: Callable[[], int]
    recent_failed_detail_text: Callable[[Optional[str], int], str]
    recent_jobs_summary: Callable[[int], str]
    gate_quota: AsyncGateQuotaFn
    queue_push_task: Callable[[dict], dict]
    clear_state: Callable[[int], None]
    log_event: Callable[..., None]
    handle_link_dest_callback: Callable[..., Awaitable[bool]]
    handle_link_quality_callback: Callable[..., Awaitable[bool]]
    handle_media_dest_callback: Callable[..., Awaitable[bool]]
    dispatch_inline_menu_callback: Callable[..., Awaitable[bool]]
    handle_feed_callback: Callable[..., Awaitable[bool]]
    handle_fx_quick_callback: Callable[..., Awaitable[bool]]
    dispatch_cf_menu_callback: Callable[..., Awaitable[bool]]
    handle_cf_dns_zone_callback: Callable[..., Awaitable[bool]]
    handle_cf_dns_add_zone_callback: Callable[..., Awaitable[bool]]
    handle_cf_dns_del_zone_callback: Callable[..., Awaitable[bool]]
    handle_cf_dns_delete_callback: Callable[..., Awaitable[bool]]
    handle_ssh_op_callback: Callable[..., Awaitable[bool]]
    dispatch_drive_auth_callback: Callable[..., Awaitable[bool]]
    handle_cta_callback: Callable[..., Awaitable[bool]] | None = None
    handle_calc_mode_callback: Callable[..., Awaitable[bool]] | None = None
    handle_fx_from_callback: Callable[..., Awaitable[bool]] | None = None
    handle_fx_calc_callback: Callable[..., Awaitable[bool]] | None = None
    handle_ssh_auth_callback: Callable[..., Awaitable[bool]] | None = None
    handle_clear_chat_callback: Callable[..., Awaitable[bool]] | None = None
    handle_alert_kind_callback: Callable[..., Awaitable[bool]] | None = None
    handle_alert_schedule_callback: Callable[..., Awaitable[bool]] | None = None
    handle_alert_hour_callback: Callable[..., Awaitable[bool]] | None = None
    handle_alert_spike_callback: Callable[..., Awaitable[bool]] | None = None
    handle_alert_free_callback: Callable[..., Awaitable[bool]] | None = None
    handle_alert_manage_callback: Callable[..., Awaitable[bool]] | None = None
    handle_market_page_callback: Callable[..., Awaitable[bool]] | None = None
    handle_quake_mag_callback: Callable[..., Awaitable[bool]] | None = None
    handle_alert_quake_mag_callback: Callable[..., Awaitable[bool]] | None = None


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
            count = deps.count_tasks_for_user(user_id)
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

    if data == "confirm_send":
        from v2.handlers.confirm_state import get_pending_confirm, pop_pending_confirm

        task = state.get("pending_task") or get_pending_confirm(user_id)
        if not task:
            await callback_query.answer(deps.tr(user_id, "confirm_already_handled"), show_alert=True)
            return True
        if not await deps.gate_quota(callback_query.message, user_id, task):
            await callback_query.answer("Quota", show_alert=True)
            return True
        anchor = callback_query.message
        task["chat_id"] = anchor.chat.id
        task["status_message_id"] = anchor.id
        task = deps.queue_push_task(task)
        qpos = deps.queue_count_by_session(task.get("rubika_session") or "")
        pop_pending_confirm(user_id)
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

    if data.startswith("linkquality:"):
        quality = data.split(":", 1)[1]
        return await deps.handle_link_quality_callback(client, callback_query, quality)

    if data.startswith("linkdest:"):
        dest = data.split(":", 1)[1]
        return await deps.handle_link_dest_callback(client, callback_query, dest)

    if data.startswith("mediadest:"):
        dest = data.split(":", 1)[1]
        return await deps.handle_media_dest_callback(client, callback_query, dest)

    if data.startswith("imenu:"):
        key = data.split(":", 1)[1]
        return await deps.dispatch_inline_menu_callback(client, callback_query, key)

    if data.startswith("fxquick:"):
        parts = data.split(":")
        if len(parts) < 4:
            return False
        return await deps.handle_fx_quick_callback(
            client, callback_query, parts[1], parts[2], parts[3]
        )

    if data.startswith("cta:") and deps.handle_cta_callback:
        return await deps.handle_cta_callback(client, callback_query, data.split(":", 1)[1])

    if data.startswith("calcmode:") and deps.handle_calc_mode_callback:
        parts = data.split(":")
        if len(parts) >= 3:
            return await deps.handle_calc_mode_callback(client, callback_query, parts[1], parts[2])

    if data.startswith("fxfrom:") and deps.handle_fx_from_callback:
        return await deps.handle_fx_from_callback(client, callback_query, data.split(":", 1)[1])

    if data.startswith("fxcalc:") and deps.handle_fx_calc_callback:
        return await deps.handle_fx_calc_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("mktpage:") and deps.handle_market_page_callback:
        parts = data.split(":")
        if len(parts) >= 3:
            try:
                page = int(parts[2])
            except ValueError:
                page = 0
            return await deps.handle_market_page_callback(
                client, callback_query, parts[1], page
            )

    if data.startswith("quake:") and deps.handle_quake_mag_callback:
        return await deps.handle_quake_mag_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("alertqmag:") and deps.handle_alert_quake_mag_callback:
        return await deps.handle_alert_quake_mag_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("sshauth:") and deps.handle_ssh_auth_callback:
        return await deps.handle_ssh_auth_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("clearchat:") and deps.handle_clear_chat_callback:
        return await deps.handle_clear_chat_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("alertkind:") and deps.handle_alert_kind_callback:
        return await deps.handle_alert_kind_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("alertsch:") and deps.handle_alert_schedule_callback:
        return await deps.handle_alert_schedule_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("alerthour:") and deps.handle_alert_hour_callback:
        return await deps.handle_alert_hour_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("alertspike:") and deps.handle_alert_spike_callback:
        return await deps.handle_alert_spike_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith("alertfree:") and deps.handle_alert_free_callback:
        return await deps.handle_alert_free_callback(
            client, callback_query, data.split(":", 1)[1]
        )

    if data.startswith(("alertdel:", "alerttog:", "alerttest:", "alertmute:")) and deps.handle_alert_manage_callback:
        parts = data.split(":")
        try:
            action = parts[0].replace("alert", "", 1)
            aid = int(parts[1])
        except (ValueError, IndexError):
            return False
        extra = parts[2] if len(parts) > 2 else None
        return await deps.handle_alert_manage_callback(
            client, callback_query, action, aid, extra
        )

    if data.startswith("feedview:"):
        try:
            feed_id = int(data.split(":", 1)[1])
        except ValueError:
            return False
        return await deps.handle_feed_callback(client, callback_query, "view", feed_id)

    if data.startswith("feeddel:"):
        try:
            feed_id = int(data.split(":", 1)[1])
        except ValueError:
            return False
        return await deps.handle_feed_callback(client, callback_query, "del", feed_id)

    if data.startswith("feedpush:"):
        parts = data.split(":")
        if len(parts) >= 3 and parts[1] == "toggle":
            try:
                feed_id = int(parts[2])
            except ValueError:
                return False
            return await deps.handle_feed_callback(client, callback_query, "toggle", feed_id)

    if data.startswith("feeddigest:"):
        parts = data.split(":")
        if len(parts) >= 3 and parts[1] == "toggle":
            try:
                feed_id = int(parts[2])
            except ValueError:
                return False
            return await deps.handle_feed_callback(
                client, callback_query, "digest_toggle", feed_id
            )

    if data.startswith("feedpage:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            return False
        return await deps.handle_feed_callback(client, callback_query, "page", page)

    if data.startswith("feedmenu:"):
        action = data.split(":", 1)[1]
        return await deps.handle_feed_callback(client, callback_query, action, 0)

    if data.startswith("rsspush:"):
        parts = data.split(":")
        if len(parts) >= 3:
            leg = parts[1]
            try:
                feed_id = int(parts[2])
            except ValueError:
                return False
            if leg in ("on", "off"):
                return await deps.handle_feed_callback(client, callback_query, leg, feed_id)

    if data.startswith("rssview:"):
        try:
            feed_id = int(data.split(":", 1)[1])
        except ValueError:
            return False
        return await deps.handle_feed_callback(client, callback_query, "view", feed_id)

    if data.startswith("cfmenu:"):
        action = data.split(":", 1)[1]
        return await deps.dispatch_cf_menu_callback(client, callback_query, action)

    if data.startswith("cfdnsadd:"):
        zone_id = data.split(":", 1)[1].strip()
        if not zone_id:
            return False
        return await deps.handle_cf_dns_add_zone_callback(client, callback_query, zone_id)

    if data.startswith("cfdnsdelz:"):
        zone_id = data.split(":", 1)[1].strip()
        if not zone_id:
            return False
        return await deps.handle_cf_dns_del_zone_callback(client, callback_query, zone_id)

    if data.startswith("cfdnsdel:"):
        record_id = data.split(":", 1)[1].strip()
        if not record_id:
            return False
        return await deps.handle_cf_dns_delete_callback(client, callback_query, record_id)

    if data.startswith("cfdns:"):
        zone_id = data.split(":", 1)[1].strip()
        if not zone_id:
            return False
        return await deps.handle_cf_dns_zone_callback(client, callback_query, zone_id)

    if data.startswith("sshop:"):
        parts = data.split(":")
        if len(parts) < 3:
            return False
        op = parts[1].strip()
        try:
            server_id = int(parts[2])
        except ValueError:
            return False
        return await deps.handle_ssh_op_callback(client, callback_query, op, server_id)

    if data.startswith("driveauth:"):
        action = data.split(":", 1)[1]
        return await deps.dispatch_drive_auth_callback(client, callback_query, action)

    if data == "cancel_send":
        from pathlib import Path

        from v2.handlers.confirm_state import get_pending_confirm, pop_pending_confirm

        if not (state.get("step") == "await_send_confirm" or state.get("pending_task") or get_pending_confirm(user_id)):
            return False
        task = state.get("pending_task") or get_pending_confirm(user_id) or {}
        for key in ("path", "local_path", "file_path"):
            raw = task.get(key) if isinstance(task, dict) else None
            if not raw:
                continue
            try:
                p = Path(str(raw))
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
        pop_pending_confirm(user_id)
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
