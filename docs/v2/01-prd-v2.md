# PRD: Super-Bot v2

## 1) Product Vision
- Build a modular Persian-first super-bot where file transfer is one capability among many.
- Keep current reliability strengths (queue, worker, quotas), then expand to tools, bridges, cloud integrations, and monetization.
- Ship v2 with migration safety: v1 and v2 run side by side until readiness gates are met.

## 2) Scope (v2.0)
### In scope
- New modular bot core with plugin registry.
- Menu engine with strict submenu behavior.
- Billing core, quotas, and package model.
- Transfer stack foundations: Rubika/Bale/Google Drive/link<->file/unzip.
- Toolkit foundations: network/security/markets/world/utility/files.
- Admin operations and KPI instrumentation.

### Out of scope (v2.0 initial)
- Full mini-app parity for every module.
- Advanced enterprise contracts and custom integrations.
- Cross-region HA deployment.

## 3) Primary Personas
- Casual users (free): occasional utility usage.
- Power users (pro): frequent personal productivity workflows.
- Teams (star): shared usage with basic team controls.
- Business (business): higher SLA, priority support, advanced controls.

## 4) Success Metrics
- Activation: user completes first successful task within first session.
- Retention: D7 and D30 improvement compared to v1.
- Conversion: free->paid uplift with clear in-bot upsell moments.
- Reliability: lower failed job ratio and lower time-to-result.

## 5) Functional Requirements
1. Core and plugins:
   - Bot core must support pluggable modules with isolated handlers.
2. Menu UX:
   - `📋 پلن / خرید / محدودیت` is a category entry only.
   - `/plan`, `/purchase`, `/usage`, `/queue` appear only inside plan submenu.
3. Transfer:
   - Unified task model with retries, cancellation, and progress states.
4. Billing:
   - Tier-aware quotas on daily/monthly/parallel/cost dimensions.
5. Admin:
   - Role-based actions, user lookup, quota override, audit logs.

## 6) Non-Functional Requirements
- Security: least-privilege tokens, webhook verification, auditability.
- Scalability: queue-backed async execution, per-plugin rate limits.
- Observability: structured logs + KPI events.
- Extensibility: add/remove plugins without changing core business logic.

## 7) Plugin Taxonomy (v2 baseline)
- `transfer`: Telegram/Rubika/Bale/Drive/link-file/unzip.
- `toolkit-network`: IP, DNS, Whois, ping, SSL, subnet, headers.
- `toolkit-security`: leak checks, speed test wrappers, traceroute, scan.
- `toolkit-markets`: crypto/forex/gold/oil + alerts.
- `toolkit-world`: weather/air quality/sunrise/timezone/calendar.
- `toolkit-utility`: hash/base64/json/QR/password/url shortener/OCR.
- `cloud`: cloud service helpers (Cloudflare-like operations).
- `explorer`: GitHub/search style utilities.

## 8) Delivery Model
- Stage 1: v2 skeleton + menu engine + billing core.
- Stage 2: transfer adapters + first toolkit slice.
- Stage 3: paid tiers + growth loops + hardened ops.
- Stage 4: migration of default traffic to v2.

## 9) Risks
- Over-broad v2 scope causing delayed value delivery.
- Third-party API instability and quota limits.
- Payment gateway failure modes and reconciliation drift.

## 10) Acceptance Criteria for v2.0 kickoff complete
- Technical design approved.
- Menu specification finalized.
- Tier and gateway contracts finalized.
- Transfer adapter contracts documented.
- KPI and ops model ready for implementation.
