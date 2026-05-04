"""Minimal payment webhook parsing + ledger updates (see ``04-billing-pricing-gateway.md`` §5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from queue_db import QueueDB

from v2.billing.paid_entitlements import maybe_grant_plan_after_paid
from v2.billing.status import ALL_STATUSES, PAID


@dataclass(frozen=True)
class VerifiedPaymentEvent:
    payment_id: int
    status: str
    ref_id: Optional[str] = None
    source: str = "webhook"


def verify_bearer_authorization(authorization_header: Optional[str], secret: str) -> bool:
    """Match ``Authorization: Bearer <secret>`` (same as ``tools/payment_webhook_stub``)."""
    if not (secret or "").strip():
        return False
    if not authorization_header:
        return False
    return authorization_header.strip() == f"Bearer {secret.strip()}"


def parse_verified_event_from_dict(body: dict) -> VerifiedPaymentEvent:
    """JSON body: ``payment_id`` (int), ``status`` (str), optional ``ref_id``, optional ``source``."""
    pid = int(body["payment_id"])
    st = str(body["status"]).strip().lower()
    if st not in ALL_STATUSES:
        raise ValueError(f"invalid status {st!r}; expected one of {sorted(ALL_STATUSES)}")
    ref_raw = body.get("ref_id")
    ref: Optional[str]
    if ref_raw is None or ref_raw == "":
        ref = None
    else:
        ref = str(ref_raw).strip() or None
    src = str(body.get("source", "http_stub")).strip() or "http_stub"
    return VerifiedPaymentEvent(payment_id=pid, status=st, ref_id=ref, source=src)


def apply_verified_payment_event(db: QueueDB, event: VerifiedPaymentEvent) -> None:
    """Update ``v2_payments``; raises if ``payment_id`` does not exist."""
    row = db.get_v2_payment_by_id(event.payment_id)
    if not row:
        raise ValueError(f"unknown payment_id {event.payment_id}")
    db.update_v2_payment_status(
        event.payment_id,
        event.status,
        ref_id=event.ref_id,
        raw_patch={"event_source": event.source},
    )
    if event.status == PAID:
        maybe_grant_plan_after_paid(db, event.payment_id)
