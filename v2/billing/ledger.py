from __future__ import annotations

from typing import Optional

from queue_db import QueueDB

from v2.billing.status import INITIATED


def record_initiated_payment(
    db: QueueDB,
    telegram_user_id: int,
    gateway: str,
    amount: int,
    *,
    currency: str = "IRR",
    authority: Optional[str] = None,
    metadata: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
) -> int:
    """Persist a new payment row in ``v2_payments``; returns row ``id``."""
    return db.insert_v2_payment(
        telegram_user_id,
        gateway,
        amount,
        currency=currency,
        authority=authority,
        status=INITIATED,
        raw_json=metadata,
        idempotency_key=idempotency_key,
    )
