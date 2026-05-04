# Billing, Pricing, and Gateway Contract (v2)

## 1) Package Matrix
| Tier | Target | Monthly Credits | Daily Soft Cap | Max Parallel | Queue Priority | Premium Modules |
|---|---|---:|---:|---:|---|---|
| Free | casual | 1,500 | 150 | 1 | standard | limited |
| Pro | personal heavy users | 12,000 | 1,200 | 3 | high | most |
| Star | small teams | 40,000 shared | 4,000 shared | 8 | higher | all toolkit + alerts |
| Business | orgs | custom | custom | custom | top | all + SLA |

Notes:
- Credits are cost units, not raw requests.
- Each task consumes weighted credits by complexity.
- Burst add-on packs can temporarily increase available credits.

## 2) Quota Dimensions
- `requests_day`
- `requests_month`
- `compute_credits_month`
- `bytes_transfer_day` / `bytes_transfer_month`
- `max_parallel_tasks`
- `max_file_mb`

Enforcement points:
- Pre-queue gating.
- Mid-task hard stop for policy breaches.
- Post-task metering in usage ledger.

## 3) Pricing Model (placeholder policy)
- Monthly and yearly billing for all paid tiers.
- Yearly discount target: 15% to 25%.
- Team pricing:
  - base package + seat-based uplift.
- Add-ons:
  - extra credits pack
  - premium data feed pack
  - priority support pack

## 4) Gateway Abstraction
Interface:
- `create_payment_intent(user_id, amount, currency, metadata)`
- `verify_callback(headers, payload) -> verified_event`
- `fetch_payment_status(authority_or_ref)`
- `refund_payment(payment_id, amount)`

Provider adapters:
- `gateway_zarinpal.py`
- `gateway_idpay.py`
- `gateway_nextpay.py`
- `gateway_payir.py` (optional fallback)

## 5) Webhook Contract
- All callbacks must include:
  - signature verification
  - timestamp window check
  - idempotency key dedupe
- Lifecycle:
  - `initiated` -> `pending` -> (`paid` | `failed` | `expired` | `refunded`)
- Never activate subscription before verified webhook and reconciliation check.

## 6) Reconciliation Jobs
- Periodic job every 10 minutes:
  - fetch `pending` intents
  - cross-check provider status
  - repair local status drift
- Daily settlement report for finance/admin.

## 7) Access and Entitlement Rules
- `subscriptions.status=active` gates paid features.
- Grace period configurable (example: 24 hours).
- Downgrade policy:
  - immediate for abuse/fraud.
  - end-of-cycle for voluntary cancellation.

## 8) Fraud Controls
- Limit rapid payment attempts per user/device/IP.
- Delay reward release for referral-based credits.
- Block upgrade if repeated chargeback/refund abuse pattern is detected.

## 9) Required Admin Tools
- Manual plan grant/revoke.
- Credit adjustments with mandatory reason.
- Payment lookup by authority/ref_id/user_id.
- Forced reconciliation run.

## 10) Definition of Done
- Tier matrix finalized and approved.
- At least two gateway adapters implemented with common contract.
- Webhook verification and idempotency tests pass.
