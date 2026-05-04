"""Glue between legacy worker queue tasks and ``TransferAdapter`` (no imports from ``telebot``)."""

from __future__ import annotations

from typing import Optional

from v2.transfer.rubika_adapter import RubikaTransferAdapter


def _telegram_uid(task: dict) -> int:
    try:
        return int(task.get("telegram_user_id") or task.get("chat_id") or 0)
    except (TypeError, ValueError):
        return 0


def validate_transfer_task_v2(task: dict, *, fallback_session: str = "") -> tuple[bool, str]:
    """
    Pre-flight Rubika session check using :class:`RubikaTransferAdapter`.

    Uses ``task["rubika_session"]`` or ``fallback_session`` (e.g. worker ``RUBIKA_SESSION`` env).
    """
    uid = _telegram_uid(task)
    if uid <= 0:
        return True, ""
    eff = (task.get("rubika_session") or "").strip() or (fallback_session or "").strip()
    if not eff:
        return (
            False,
            "نشست روبیکا برای این کار مشخص نیست. در ربات `/rubika_connect` را بزن یا برای اپ قدیمی `RUBIKA_SESSION` را تنظیم کن.",
        )

    def get_session(u: int) -> Optional[str]:
        if int(u) != uid:
            return None
        return eff

    adapter = RubikaTransferAdapter(get_session)
    if not adapter.validate_account({"telegram_user_id": uid}):
        return False, "اعتبارسنجی نشست روبیکا ناموفق بود."
    return True, ""
