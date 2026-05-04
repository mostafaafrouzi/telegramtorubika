"""Payment gateway abstraction (see ``docs/v2/04-billing-pricing-gateway.md`` §4)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from queue_db import QueueDB

from v2.billing.ledger import record_initiated_payment


@dataclass(frozen=True)
class PaymentIntentResult:
    payment_id: int
    gateway: str
    authority: Optional[str]


@runtime_checkable
class PaymentGateway(Protocol):
    def create_payment_intent(
        self,
        telegram_user_id: int,
        amount: int,
        *,
        currency: str = "IRR",
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentIntentResult:
        ...


class StubPaymentGateway:
    """Records a real ``v2_payments`` row with a synthetic authority (dev / tests)."""

    def __init__(self, db: QueueDB, gateway_name: str = "stub") -> None:
        self._db = db
        self._name = gateway_name

    def create_payment_intent(
        self,
        telegram_user_id: int,
        amount: int,
        *,
        currency: str = "IRR",
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentIntentResult:
        authority = f"{self._name}-{int(time.time())}-{int(telegram_user_id)}"
        meta = dict(metadata or {})
        meta.setdefault("stub", True)
        pid = record_initiated_payment(
            self._db,
            int(telegram_user_id),
            self._name,
            int(amount),
            currency=currency,
            authority=authority,
            metadata=meta,
            idempotency_key=idempotency_key,
        )
        return PaymentIntentResult(payment_id=pid, gateway=self._name, authority=authority)
