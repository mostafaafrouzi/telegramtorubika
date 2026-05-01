# Monetization & plans (roadmap)

This repository currently focuses on transfer reliability (Telegram → Rubika). A **full** subscription / payment stack is a separate product surface. Recommended phased approach:

## Phase 1 — Metering (no payments yet)

- Persist per-user counters in SQLite: `bytes_uploaded_today`, `jobs_today`, `plan` (`free` | `manual_pro`).
- Enforce soft limits for `free` (e.g. max file size, max jobs/day) before queueing.
- Admin commands: `/grant_plan <user_id> pro`, `/revoke_plan <user_id>`.

## Phase 2 — Payments

- Use one Iranian PSP with a **documented** REST API and webhook callbacks.
- Store `transactions` table (amount, authority, status, user_id, plan_id).
- Never trust client-side “paid”; only activate plan on **verified webhook**.

## Phase 3 — Product packaging

- Define plans in JSON or DB: price, duration, limits (size, parallel jobs, ZIP batch size).
- Feature flags: “VIP upload”, “priority queue”, “no confirmation step”.

## Operations

- Metrics: queue depth, worker failure rate by error class, disk usage (already partially exposed to admin).
- Abuse: rate-limit `/rubika_connect` and media handlers per user.

Implementing Phases 2–3 correctly requires legal/compliance review for your jurisdiction and PSP contracts; keep payment keys only on the server and rotate on leak.
