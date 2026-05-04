"""Stale payment reconciliation (MVP: expire old ``pending`` / ``initiated`` rows without PSP polling)."""

from __future__ import annotations

import time
from typing import Any

from queue_db import QueueDB

from v2.billing.status import EXPIRED, INITIATED, PENDING


def run_reconcile(db: QueueDB, *, pending_max_age_sec: int = 86400) -> dict[str, Any]:
    """Expire rows stuck in ``pending`` or ``initiated`` longer than ``pending_max_age_sec``."""
    now = int(time.time())
    max_age = max(60, int(pending_max_age_sec))
    expired = 0
    scanned = 0
    for st in (PENDING, INITIATED):
        rows = db.list_v2_payments_by_status(st, limit=500)
        scanned += len(rows)
        for r in rows:
            created = int(r.get("created_at") or 0)
            if created and (now - created) > max_age:
                db.update_v2_payment_status(
                    int(r["id"]),
                    EXPIRED,
                    raw_patch={"reconcile": f"stale_{st}"},
                )
                expired += 1
    return {"expired": expired, "scanned": scanned, "ts": now}
