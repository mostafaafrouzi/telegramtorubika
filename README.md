# telegramtorubika

Telegram to Rubika transfer bot with queueing, batch zip/split, per-user Rubika sessions, and server installer.

Repository: [github.com/mostafaafrouzi/telegramtorubika](http://github.com/mostafaafrouzi/telegramtorubika)

## Features

- Per-user Rubika connection from Telegram bot (`/rubika_connect`)
- Queue-based processing (SQLite)
- Batch mode: collect many files, zip, split parts
- Direct URL download
- Safe mode (zip with password)
- Direct mode (send everything immediately to queue)
- Interactive server installer (install/update/uninstall/backup/restore)
- Per-user **plans & quotas** (default tiers guest/free/pro in SQLite; `/usage` for users; `/admin_tier`, `/admin_bonus` for admins; optional `DISABLE_USAGE_LIMITS=1` for private hosts)
- Optional **`ENABLE_UPLOAD_CHECKSUM`** on worker (MD5 logged before Rubika upload); optional **`tools/payment_webhook_stub.py`** to activate paid tiers via HTTP

## Fast server install (curl)

```bash
curl -fsSL http://raw.githubusercontent.com/mostafaafrouzi/telegramtorubika/main/installer.sh -o installer.sh
sudo bash installer.sh
```

One-line update mode:

```bash
curl -fsSL http://raw.githubusercontent.com/mostafaafrouzi/telegramtorubika/main/installer.sh | sudo bash -s -- --update
```

In non-interactive flag mode, the installer auto-selects the first detected instance.

## Required environment values

The installer asks for these values:

- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `ADMIN_IDS` (comma-separated Telegram user IDs)
- `RUBIKA_SESSION` (default session name)
- `DEFAULT_PART_SIZE_MB` (default split size)

## How to get each field

### Telegram API_ID and API_HASH

1. Open [my.telegram.org](https://my.telegram.org)
2. Login with your Telegram number
3. Open **API development tools**
4. Create an app (title + short name)
5. Copy:
   - `api_id` -> `API_ID`
   - `api_hash` -> `API_HASH`

### Telegram BOT_TOKEN

1. Open `@BotFather` in Telegram
2. Run `/newbot`
3. Create bot username
4. Copy token -> `BOT_TOKEN`

### Telegram user ID (for ADMIN_IDS)

Use one of:

- `@userinfobot`
- `@RawDataBot`

Send `/start` and copy your numeric Telegram ID.

### RUBIKA_SESSION

Any unique string, for example:

```env
RUBIKA_SESSION=rubika_session
```

### DEFAULT_PART_SIZE_MB

Recommended:

```env
DEFAULT_PART_SIZE_MB=1900
```

## Manual run (development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Split bot and worker (optional, less RAM per process)

By default `main.py` runs **both** `telebot.py` and `rub.py` in one parent process (two children). On small VPS instances, large Telegram downloads can compete with the Rubika worker and trigger OOM. You can run them as **two systemd services** instead (same repo dir and `.env`):

- **Installer:** during **Install**, answer *yes* when asked for separate units — or copy the examples below manually.
- Example units: `deploy/systemd/tele2rub-bot.service.example` and `deploy/systemd/tele2rub-worker.service.example`
- Use either **one** combined `main.py` service **or** the `*-bot` + `*-worker` pair for the same install dir — not both.

Live logs on a split install:

```bash
journalctl -u tele2rub-bot -u tele2rub-worker -f -n 120
```

### Upload size cap (`MAX_FILE_MB`)

Set `MAX_FILE_MB` in `.env` to reject files (and batch ZIPs) over that size in megabytes before queueing. Use `0` or leave empty for no limit. Shown on `/admin`.

## Bot usage basics

1. `/start`
2. `/rubika_connect` and complete phone/code flow
3. Send files or links
4. Confirm before sending to Rubika
5. Use `/directmode on` for immediate queueing mode

## Installer menu

- Install
- Update
- Uninstall
- Backup
- Restore
- Service logs (live)
- Installer logs
- Installer JSON logs
- Bot logs
- Worker logs
- Export + show all logs (copy-friendly bundle)

## Troubleshooting

- Service logs (combined `main.py` unit):
  ```bash
  journalctl -u tele2rub -f -n 120
  ```
  If you use split bot/worker units instead, follow both: `journalctl -u tele2rub-bot -u tele2rub-worker -f -n 120`.
- Installer logs:
  ```bash
  tail -n 200 /tmp/tele2rub-installer.log
  ```
- Installer JSON logs (machine-readable for deeper debugging):
  ```bash
  tail -n 200 /tmp/tele2rub-installer.jsonl
  ```
- Bot event logs:
  ```bash
  tail -n 200 /opt/tele2rub/queue/bot_events.jsonl
  ```
- Worker event logs:
  ```bash
  tail -n 200 /opt/tele2rub/queue/worker_events.jsonl
  ```
- Analyze one specific job by id:
  ```bash
  JOB_ID=YOUR_JOB_ID
  rg "$JOB_ID|task_queued|task_started|task_done|task_failed|task_requeued" /opt/tele2rub/queue/bot_events.jsonl /opt/tele2rub/queue/worker_events.jsonl
  ```
- Human-readable analyzer (from project root):
  ```bash
  python3 log_analyzer.py --job-id YOUR_JOB_ID --queue-dir /opt/tele2rub/queue
  ```
- JSON analyzer output (for automation or sharing):
  ```bash
  python3 log_analyzer.py --job-id YOUR_JOB_ID --queue-dir /opt/tele2rub/queue --json
  ```
- Brief one-line summary:
  ```bash
  python3 log_analyzer.py --job-id YOUR_JOB_ID --queue-dir /opt/tele2rub/queue --brief
  ```
- Live follow mode (waits for new worker events of one job):
  ```bash
  python3 log_analyzer.py --job-id YOUR_JOB_ID --queue-dir /opt/tele2rub/queue --follow
  ```
- Quick installer flags:
  ```bash
  sudo bash installer.sh --install
  sudo bash installer.sh --update
  sudo bash installer.sh --uninstall
  sudo bash installer.sh --backup
  sudo bash installer.sh --restore
  sudo bash installer.sh --logs
  sudo bash installer.sh --installer-logs
  sudo bash installer.sh --installer-json-logs
  sudo bash installer.sh --bot-logs
  sudo bash installer.sh --worker-logs
  sudo bash installer.sh --all-logs
  ```

Export **all** logs to `/tmp/tele2rub-all-logs-*.txt` (service journal + bot/worker JSONL + installer logs). Requires `bash` (not plain `sh`). Only the **first** CLI argument is used as the mode flag.

```bash
curl -fsSL https://raw.githubusercontent.com/mostafaafrouzi/telegramtorubika/main/installer.sh -o /tmp/tele2rub-installer.sh
sudo bash /tmp/tele2rub-installer.sh --all-logs
```

### Large ZIP / heavy uploads (why Rubika may “do nothing”)

Typical causes seen in production logs:

| Symptom | Likely cause | Mitigation |
|--------|----------------|------------|
| `502` / `Bad Gateway` on `*.iranlms.ir` | Rubika edge/API instability or routing | Retry later; try another egress/VPS region |
| `Error uploading chunk` | Unstable upload session to Rubika | Already retried in worker; check network |
| `tele2rub.service: ... killed by the OOM killer` during Telegram upload | **Low RAM** while Pyrogram uploads large files (`SaveBigFilePart`) | Add **swap**, increase VPS RAM, avoid multi‑GB single uploads off tiny instances, or split archives |

Admin helpers on the bot (see `/admin`): disk summary is shown there; `/cleanup_downloads` removes files under `downloads/` (admin only).

### Log interpretation checklist

- Successful flow: `task_queued` -> `task_started` -> `task_done`
- Failed flow: `task_queued` -> `task_started` -> `task_failed`
- Requeue flow (network degradation): `task_failed` + `task_requeued` with a `new_job_id`
- Rubika auth issues: check `rubika_connect_failed` in bot log before re-testing queue jobs
- Performance timing: check `duration_ms` in `task_done` and phase events like `bundle_zip_done`, `split_done`, `upload_part_done`

## Credits

Original project creator: **caffeinexz**.
