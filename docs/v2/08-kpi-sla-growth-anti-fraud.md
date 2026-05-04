# KPI Dashboard, SLA, Growth, and Anti-Fraud Model

## 1) KPI Framework
## Product KPIs
- Activation rate (first successful task within first day).
- Retention: D1, D7, D30 by cohort.
- Feature adoption by plugin category.

## Monetization KPIs
- Free->Paid conversion rate.
- MRR and ARPPU.
- Churn rate by tier.
- Payment success ratio by gateway.

## Reliability KPIs
- Queue depth and age.
- Task success rate and p95 completion time.
- Error rate by plugin/provider.

## Support KPIs
- Ticket volume per 1k users.
- First response time.
- Resolution SLA attainment.

## Risk KPIs
- Abuse detection hit rate.
- False-positive moderation ratio.
- Chargeback/refund anomaly rate.

## 2) Dashboard Layers
- Exec dashboard: growth, revenue, reliability summary.
- Ops dashboard: queue, workers, incidents, gateways.
- Product dashboard: feature usage and funnel.
- Trust dashboard: abuse/fraud and mitigation outcomes.

## 3) SLA by Tier
| Tier | Availability Target | Support Response Target | Queue Priority |
|---|---|---|---|
| Free | best effort | best effort | standard |
| Pro | 99.0% | <24h | high |
| Star | 99.5% | <8h | higher |
| Business | 99.9% (target) | <2-4h | top |

Notes:
- SLA requires clear maintenance window policy.
- Incident postmortems mandatory for star/business-impacting incidents.

## 4) Support Workflow
- In-bot ticket intake with category:
  - billing
  - technical
  - abuse report
  - feature request
- Routing:
  - L1 support -> L2 ops -> engineering escalation.
- Standardized runbooks:
  - payment failures
  - queue congestion
  - provider outage
  - suspected abuse.

## 5) Growth and Referral Model
- Referral rewards tied to retained activity, not first click.
- Delayed reward release (anti-farm window).
- Campaign engine:
  - promo codes
  - time-boxed upgrade offers
  - reactivation offers for churned users.

## 6) Anti-Fraud and Abuse Controls
- Behavioral scoring:
  - request velocity
  - repeated failures
  - suspicious account clusters
- Risk states:
  - `normal`
  - `limited`
  - `blocked`
  - `manual_review`
- Payment risk controls:
  - attempt throttling
  - duplicate authority detection
  - cooldown before high-cost actions for new payers.

## 7) Event Instrumentation Contract
Mandatory fields in events:
- `event_name`
- `timestamp`
- `user_id`
- `tier`
- `plugin`
- `trace_id`
- `task_id` (when applicable)
- `result` / `error_code`

## 8) Rollout Targets (first 90 days post v2 launch)
- Payment success ratio > 95%.
- D30 retention improved over v1 baseline.
- Queue p95 below target SLO for paid tiers.
- Ticket SLA attainment > 90% for star/business.
- Controlled fraud loss threshold with decreasing trend.
