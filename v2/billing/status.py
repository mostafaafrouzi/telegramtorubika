"""Payment lifecycle strings (aligned with ``docs/v2/04-billing-pricing-gateway.md``)."""

INITIATED = "initiated"
PENDING = "pending"
PAID = "paid"
FAILED = "failed"
EXPIRED = "expired"
REFUNDED = "refunded"

ALL_STATUSES = frozenset({INITIATED, PENDING, PAID, FAILED, EXPIRED, REFUNDED})
