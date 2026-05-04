# Technical Design: Core, Queue, and Storage Migration

## 1) Target Module Layout
```text
v2/
  core/
    bot/              # Telegram app bootstrap, middleware chain
    menu/             # Menu engine (config-driven)
    plugins/          # Plugin registry + lifecycle
    jobs/             # Task dispatcher + workers integration
    billing/          # Entitlements, quotas, usage metering
    auth/             # User identity + admin role checks
    state/            # Session/state access abstraction
    observability/    # Logs, events, metrics emitters
  plugins/
    transfer/
    toolkit_network/
    toolkit_security/
    toolkit_markets/
    toolkit_world/
    toolkit_utility/
  api/
    webhooks/         # payment/provider callbacks
```

## 2) Runtime Topology
- `bot-process`: Telegram updates, menu rendering, command routing.
- `worker-process`: background jobs (transfers, heavy conversions, sync tasks).
- `scheduler-process` (optional in MVP): periodic jobs (alerts, daily digest, refresh).
- Shared storage: Postgres (preferred) + Redis queue, with SQLite fallback in MVP dev mode.

## 3) Data Model (v2)
### Core tables
- `users(id, tg_user_id, lang, created_at, status)`
- `user_profiles(user_id, city, timezone, risk_score, flags_json)`
- `admin_roles(user_id, role, granted_by, granted_at)`
- `subscriptions(id, user_id, tier, starts_at, ends_at, status)`
- `usage_ledger(id, user_id, metric_key, metric_value, bucket_date, bucket_month, source)`
- `tasks(id, user_id, plugin, task_type, payload_json, status, priority, attempts, created_at, updated_at)`
- `task_events(id, task_id, stage, event_json, created_at)`
- `payments(id, user_id, gateway, amount, currency, authority, ref_id, status, raw_json, created_at)`
- `audit_logs(id, actor_user_id, action, target_type, target_id, metadata_json, created_at)`

### Plugin tables (examples)
- `transfer_accounts(user_id, provider, credentials_ref, status, updated_at)`
- `price_alerts(user_id, asset, target_price, direction, status, created_at)`
- `tool_runs(id, user_id, tool_key, cost_units, success, created_at)`

## 4) Queue and Task Lifecycle
States:
- `queued` -> `reserved` -> `running` -> (`succeeded` | `failed` | `cancelled` | `dead_letter`)

Rules:
- Retries with exponential backoff and capped attempts.
- Idempotency key per external operation.
- Cancellation token checked between stages.
- Plan-aware priority queue lanes (`free`, `pro`, `star`, `business`).

## 5) Storage Migration Plan (v1 -> v2)
1. Add migration scripts and create v2 schema in parallel.
2. Mirror-write critical events from v1 to v2 telemetry (shadow mode).
3. Migrate user and entitlement baselines:
   - `users.json` and SQLite entitlement rows -> `users`, `subscriptions`.
4. Shift queue ingestion to v2 for selected beta cohort.
5. Cut over workers, then retire legacy JSON state gradually.

## 6) Compatibility Layer
- `LegacyBridgeService` reads v1 task payloads and maps them to v2 task schema.
- Keep `/start`, `/menu`, and high-traffic commands backward compatible during transition.

## 7) Observability Design
- Structured JSON logs with correlation ids: `trace_id`, `task_id`, `user_id`, `plugin`.
- Event taxonomy:
  - `bot.command.received`
  - `menu.rendered`
  - `quota.blocked`
  - `task.stage.changed`
  - `payment.webhook.verified`
- Metrics:
  - queue depth, success ratio, p95 task duration, payment success ratio.

## 8) Security Baselines
- Encrypt secrets at rest (or external secret manager in production).
- Webhook signature verification + replay protection.
- Per-plugin token scopes and rotation policy.
- RBAC checks in admin handlers and webhook mutation endpoints.

## 9) Definition of Done (Core Design)
- v2 schema reviewed and migration sequence approved.
- Queue lifecycle and retry semantics finalized.
- Plugin interface contract frozen for Phase 1 implementation.
