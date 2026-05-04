"""Admin panel and maintenance slash commands (extracted from telebot)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, FrozenSet

from pyrogram.types import Message

from v2.billing.status import ALL_STATUSES, PAID
from v2.core.menu_sections import MenuSection

TranslateFn = Callable[..., str]
LogEventFn = Callable[..., None]


@dataclass(frozen=True)
class AdminCommandDeps:
    admin_ids: FrozenSet[int]
    tr: TranslateFn
    set_menu_section: Callable[[int, MenuSection], None]
    build_admin_menu: Callable[[int], Any]
    load_network_snapshot: Callable[[], dict]
    queue_count: Callable[[], int]
    queue_cancelled_count: Callable[[], int]
    queue_deleted_count: Callable[[], int]
    failed_count: Callable[[], int]
    max_file_mb_display: Callable[[], str]
    admin_disk_report_text: Callable[[], str]
    set_user_tier: Callable[[int, str, int], None]
    add_bonus_month_mb: Callable[[int, int], None]
    run_admin_cleanup_downloads: Callable[[], tuple[int, int]]
    list_v2_payments_for_user: Callable[[int, int], list[dict]]
    get_v2_payment_by_id: Callable[[int], dict | None]
    update_v2_payment_status: Callable[[int, str, str | None], None]
    maybe_grant_after_paid: Callable[[int], bool]
    run_billing_reconcile: Callable[[], dict]
    log_event: LogEventFn


async def handle_admin_panel(deps: AdminCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if uid not in deps.admin_ids:
        await message.reply_text(deps.tr(uid, "admin_denied"))
        return
    deps.set_menu_section(uid, MenuSection.ADMIN)
    net = deps.load_network_snapshot()
    await message.reply_text(
        deps.tr(
            uid,
            "admin_panel",
            qt=deps.queue_count(),
            cancelled=deps.queue_cancelled_count(),
            deleted=deps.queue_deleted_count(),
            failed=deps.failed_count(),
            net_mode=net.get("mode", "unknown"),
            net_reason=net.get("reason", "") or "---",
        )
        + "\n"
        + deps.tr(uid, "admin_max_file", mb=deps.max_file_mb_display())
        + "\n"
        + deps.tr(uid, "admin_plan_note")
        + "\n"
        + deps.tr(uid, "admin_clear_prefs_hint")
        + "\n"
        + deps.tr(uid, "admin_clear_state_mirrors_hint")
        + "\n"
        + deps.tr(uid, "admin_payment_lookup_hint")
        + "\n"
        + deps.tr(uid, "admin_payment_status_hint")
        + "\n"
        + deps.tr(uid, "admin_reconcile_billing_hint")
        + "\n\n"
        + deps.tr(uid, "rubika_update_hint")
        + "\n\n"
        + deps.admin_disk_report_text(),
        reply_markup=deps.build_admin_menu(uid),
        parse_mode=None,
    )


async def handle_admin_tier(deps: AdminCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if uid not in deps.admin_ids:
        await message.reply_text(deps.tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.reply_text(
            "Usage: `/admin_tier <telegram_user_id> <guest|free|pro> [days_valid_for_pro]`",
            parse_mode=None,
        )
        return
    try:
        target = int(parts[1].strip())
    except ValueError:
        await message.reply_text("Invalid user id.", parse_mode=None)
        return
    tier = parts[2].strip().lower()
    exp = 0
    if len(parts) >= 4:
        try:
            days = int(parts[3].strip())
            if tier == "pro" and days > 0:
                exp = int(time.time()) + days * 86400
        except ValueError:
            pass
    deps.set_user_tier(target, tier, exp)
    await message.reply_text(
        f"OK: user `{target}` tier=`{tier}` expires_at=`{exp}`",
        parse_mode=None,
    )


async def handle_admin_bonus(deps: AdminCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if uid not in deps.admin_ids:
        await message.reply_text(deps.tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.reply_text(
            "Usage: `/admin_bonus <telegram_user_id> <extra_month_mb>`",
            parse_mode=None,
        )
        return
    try:
        target = int(parts[1].strip())
        mb = int(parts[2].strip())
    except ValueError:
        await message.reply_text("Invalid numbers.", parse_mode=None)
        return
    deps.add_bonus_month_mb(target, mb)
    await message.reply_text(f"OK: +{mb} MB monthly bonus for user `{target}`", parse_mode=None)


async def handle_cleanup_downloads(deps: AdminCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if uid not in deps.admin_ids:
        await message.reply_text(deps.tr(uid, "admin_denied"))
        return
    n, freed = deps.run_admin_cleanup_downloads()
    deps.log_event("admin_cleanup_downloads", user_id=uid, files=n, bytes_freed=freed)
    await message.reply_text(
        deps.tr(uid, "cleanup_done", n=n, mb=f"{freed / (1024 * 1024):.2f}"),
        parse_mode=None,
    )


def _format_v2_payment_rows(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        lines.append(
            f"`{r.get('id')}` `{r.get('gateway','')}` {r.get('amount')} {r.get('currency','')} "
            f"`{r.get('status','')}` auth={r.get('authority') or '—'} ref={r.get('ref_id') or '—'} "
            f"t={r.get('created_at')}"
        )
    return "\n".join(lines)


async def handle_admin_payment_lookup(deps: AdminCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if uid not in deps.admin_ids:
        await message.reply_text(deps.tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply_text(
            "Usage: `/admin_payment_lookup <telegram_user_id> [limit]`",
            parse_mode=None,
        )
        return
    try:
        target = int(parts[1].strip())
    except ValueError:
        await message.reply_text("Invalid user id.", parse_mode=None)
        return
    lim = 15
    if len(parts) >= 3:
        try:
            lim = int(parts[2].strip())
        except ValueError:
            lim = 15
    lim = max(1, min(lim, 30))
    rows = deps.list_v2_payments_for_user(target, lim)
    if not rows:
        await message.reply_text(deps.tr(uid, "admin_payment_lookup_empty"), parse_mode=None)
        return
    body = deps.tr(uid, "admin_payment_lookup_title") + _format_v2_payment_rows(rows)
    await message.reply_text(body, parse_mode=None)


async def handle_admin_payment_status(deps: AdminCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if uid not in deps.admin_ids:
        await message.reply_text(deps.tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.reply_text(
            "Usage: `/admin_payment_status <payment_id> <status> [ref_id]`\n"
            f"status ∈ {{{', '.join(sorted(ALL_STATUSES))}}}",
            parse_mode=None,
        )
        return
    try:
        payment_id = int(parts[1].strip())
    except ValueError:
        await message.reply_text("Invalid payment id.", parse_mode=None)
        return
    status = parts[2].strip().lower()
    if status not in ALL_STATUSES:
        await message.reply_text(
            f"Invalid status. Use one of: {', '.join(sorted(ALL_STATUSES))}",
            parse_mode=None,
        )
        return
    ref_id: str | None = None
    if len(parts) >= 4:
        ref_id = parts[3].strip() or None
    row = deps.get_v2_payment_by_id(payment_id)
    if not row:
        await message.reply_text(f"No payment row for id `{payment_id}`.", parse_mode=None)
        return
    try:
        deps.update_v2_payment_status(payment_id, status, ref_id)
    except Exception as e:
        deps.log_event("admin_payment_status_failed", admin_id=uid, payment_id=payment_id, error=str(e))
        await message.reply_text(f"DB error: {e}", parse_mode=None)
        return
    deps.log_event(
        "admin_payment_status_ok",
        admin_id=uid,
        payment_id=payment_id,
        status=status,
        ref_id=ref_id or "",
    )
    granted = False
    if status == PAID:
        granted = bool(deps.maybe_grant_after_paid(payment_id))
    suffix = f" (+grant)" if granted else ""
    await message.reply_text(
        f"OK: payment `{payment_id}` → `{status}`"
        + (f" ref=`{ref_id}`" if ref_id else "")
        + suffix,
        parse_mode=None,
    )


async def handle_admin_reconcile_billing(deps: AdminCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if uid not in deps.admin_ids:
        await message.reply_text(deps.tr(uid, "admin_denied"))
        return
    try:
        stats = deps.run_billing_reconcile()
    except Exception as e:
        deps.log_event("admin_reconcile_billing_failed", admin_id=uid, error=str(e))
        await message.reply_text(f"Error: {e}", parse_mode=None)
        return
    deps.log_event("admin_reconcile_billing_ok", admin_id=uid, **stats)
    await message.reply_text(
        deps.tr(
            uid,
            "admin_reconcile_billing_result",
            expired=stats.get("expired", 0),
            scanned=stats.get("scanned", 0),
        ),
        parse_mode=None,
    )
