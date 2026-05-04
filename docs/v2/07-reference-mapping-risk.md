# Reference Project Mapping -> v2 Plugin Backlog

## 1) mirzabot (menu/admin/payment patterns)
Reference: [mahdiMGF2/mirzabot](https://github.com/mahdiMGF2/mirzabot)

### Extractable patterns
- Structured category menus and icon-first navigation.
- Multi-admin operational workflows.
- Paid-feature surfacing and lifecycle touchpoints.

### v2 mapping
- `core/menu`: category-first menu conventions.
- `core/auth` + `admin_roles`: role-based admin visibility.
- `core/billing`: lifecycle events (trial, renew, expire).

### Risks
- Over-coupling UI labels with routing logic.
- Complex admin actions without audit trails.

### Mitigation
- i18n key-based routing only.
- mandatory audit log for every admin mutation.

## 2) telegram-to-bale-file-transfer-bot
Reference: [ixabolfazl/telegram-to-bale-file-transfer-bot](https://github.com/ixabolfazl/telegram-to-bale-file-transfer-bot)

### Extractable patterns
- Telegram->Bale bridge flow.
- User mapping/allowlist concept.

### v2 mapping
- `plugins/transfer/bale_adapter.py`
- `transfer_accounts` mapping table for user/provider identities.

### Risks
- API size limits and platform constraints.
- Message mapping drift and partial transfer failures.

### Mitigation
- adapter capability matrix with hard limits.
- retry policy + dead-letter queue + user-visible error reason.

## 3) eazy-ssh
Reference: [Schmi7zz/eazy-ssh](https://github.com/Schmi7zz/eazy-ssh)

### Extractable patterns
- Mini-app style user journey for advanced operations.
- secure session boundary mindset and terminal-like workflows.

### v2 mapping
- long-term `plugins/remote_ops` (optional, not v2.0 core).
- secure session manager concept reused in heavy integrations.

### Risks
- High security blast radius for remote execution features.
- Support overhead and abuse vectors.

### Mitigation
- keep remote-ops behind business tier and strict ACL.
- separate runtime boundary for privileged operations.

## 4) EazyFlare (Cloud operations archetype)
Reference: [Schmi7zz/EazyFlare](https://github.com/Schmi7zz/EazyFlare)

### Extractable patterns
- Cloud account integration as utility plugin.
- Domain/zone operation flows suitable for chat UI.

### v2 mapping
- `plugins/cloud/cloudflare_service.py`
- token vault + scoped permissions.

### Risks
- token leakage and over-scoped credentials.
- accidental destructive operations.

### Mitigation
- read-only by default, confirm step for destructive actions.
- token encryption + rotation policy.

## 5) EazyGoogle (Google utility archetype)
Reference: [Schmi7zz/EazyGoogle](https://github.com/Schmi7zz/EazyGoogle)

### Extractable patterns
- search-driven utility UX.
- quota-aware API key handling.

### v2 mapping
- `plugins/explorer/google_search_service.py`
- per-provider quota tracking.

### Risks
- API limits and ToS constraints.
- low answer quality without ranking/caching strategy.

### Mitigation
- provider fallback and cached query responses.
- strict policy compliance and observability.

## 6) GithubExplorer
Reference: [Schmi7zz/GithubExplorer](https://github.com/Schmi7zz/GithubExplorer)

### Extractable patterns
- repository exploration and digest notifications in chat.
- command and callback patterns for structured browsing.

### v2 mapping
- `plugins/explorer/github_service.py`
- scheduled digest jobs and subscription tables.

### Risks
- API rate limits for popular repositories.
- noisy alerts reducing retention.

### Mitigation
- backoff + ETag caching.
- user-configurable digest frequency and mute controls.

## 7) Backlog Prioritization Outcome
### Immediate (Phase 1-3)
- Menu/admin/billing patterns.
- Transfer adapters (Rubika, Bale, Drive, link-file).

### Mid-term (Phase 4-5)
- Toolkit and cloud helpers.
- Explorer modules (GitHub/Search).

### Later
- High-risk remote operation modules (SSH-style).
