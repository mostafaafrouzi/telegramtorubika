"""Apply ``user_entitlements`` when a ledger row reaches ``paid`` (optional ``grant_*`` in ``raw_json``)."""

from __future__ import annotations

import json
import time
from typing import Optional

from queue_db import QueueDB

from v2.billing.status import PAID


def maybe_grant_plan_after_paid(db: QueueDB, payment_id: int) -> bool:
    """If metadata requests a tier grant and none applied yet, call ``set_user_tier``. Returns True if granted."""
    row = db.get_v2_payment_by_id(int(payment_id))
    if not row:
        return False
    if str(row.get("status", "")).strip().lower() != PAID:
        return False
    raw = row.get("raw_json")
    if raw is None or not str(raw).strip():
        return False
    try:
        meta = json.loads(str(raw))
    except json.JSONDecodeError:
        return False
    if not isinstance(meta, dict):
        return False
    if meta.get("entitlement_applied_at"):
        return False
    tier_raw = meta.get("grant_tier")
    if tier_raw is None or tier_raw == "":
        return False
    uid = row.get("telegram_user_id")
    if uid is None:
        return False
    tier_s = str(tier_raw).strip().lower()
    days_i = int(meta.get("grant_days") or 0)
    exp = int(time.time()) + days_i * 86400 if tier_s == "pro" and days_i > 0 else 0

    from user_entitlements import set_user_tier

    set_user_tier(int(uid), tier_s, exp)
    db.update_v2_payment_status(
        int(payment_id),
        PAID,
        raw_patch={"entitlement_applied_at": int(time.time())},
    )
    return True
