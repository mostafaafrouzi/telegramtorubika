# Toolkit Prioritization and Staged Release Plan

## Prioritization Framework
Each tool is scored by:
- User demand in Persian Telegram ecosystem.
- API reliability and integration complexity.
- Monetization potential.
- Operational risk/cost.

Score bands:
- `P0` launch now
- `P1` launch in next wave
- `P2` experimental/backlog

## Wave 1 (P0, first 4-6 weeks after core)
### Network
- IP info
- DNS lookup
- Whois
- Ping
- SSL check

### Security
- My IP
- Basic port check
- Traceroute (text mode)

### Utility
- Hash (MD5/SHA256)
- Base64 encode/decode
- JSON formatter
- Password generator
- QR code generator/reader

### World
- Weather (current)
- Sunrise/sunset
- Timezone now

## Wave 2 (P1)
### Network/Security
- HTTP headers analyzer
- Site status/uptime quick check
- Subnet calculator
- VPN leak checks
- Speed test integration
- Advanced port scan profiles

### Markets
- Crypto top pairs
- FX converter (major currencies first)
- Gold and oil prices
- Price alert v1

### Files
- WebP/PNG/JPG convert
- Image -> PDF
- PDF merge/compress basic

## Wave 3 (P1/P2 mixed)
### Markets advanced
- 150+ currency conversion
- Multi-asset alerts (crypto, fx, metals, oil)
- Smarter alert rules (crossing, percentage move)

### World advanced
- Air quality
- Calendar converters (Persian/Gregorian)
- Age calculator
- Daily digest orchestration

### Sports and live modules
- Football standings/schedules
- Live score premium feed
- Formula 1 standings/schedule

## Wave 4 (P2, premium and heavy integrations)
- OCR at scale
- Screenshot engine (headless browser infra)
- Tweet/stream style social summaries
- Advanced mini-app tools and dashboards

## Packaging Strategy by Wave
- Free:
  - P0 basics with stricter quotas.
- Pro:
  - P0 + most P1 tools.
- Star:
  - P0/P1 full + alerts and team pools.
- Business:
  - All + priority queue + support SLA.

## Operational Gate for each release wave
- Error rate below threshold.
- API spend within budget.
- Abuse control enabled.
- Documentation and localized help completed.
