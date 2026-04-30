# telegramtorubika

Telegram to Rubika transfer bot with queueing, batch zip/split, yt-dlp download, per-user Rubika sessions, and server installer.

Repository: [github.com/mostafaafrouzi/telegramtorubika](http://github.com/mostafaafrouzi/telegramtorubika)

## Features

- Per-user Rubika connection from Telegram bot (`/rubika_connect`)
- Queue-based processing (SQLite)
- Batch mode: collect many files, zip, split parts
- yt-dlp video/audio download with quality selection
- Direct URL download
- Safe mode (zip with password)
- Direct mode (send everything immediately to queue)
- Interactive server installer (install/update/uninstall/backup/restore)

## Fast server install (curl)

```bash
curl -fsSL http://raw.githubusercontent.com/mostafaafrouzi/telegramtorubika/main/installer.sh -o installer.sh
sudo bash installer.sh
```

One-line update mode:

```bash
curl -fsSL http://raw.githubusercontent.com/mostafaafrouzi/telegramtorubika/main/installer.sh | sudo bash -s -- --update
```

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
- Service logs

## Troubleshooting

- Service logs:
  ```bash
  journalctl -u tele2rub -f -n 120
  ```
- Installer logs:
  ```bash
  tail -n 200 /tmp/tele2rub-installer.log
  ```
- Quick installer flags:
  ```bash
  sudo bash installer.sh --install
  sudo bash installer.sh --update
  sudo bash installer.sh --uninstall
  sudo bash installer.sh --backup
  sudo bash installer.sh --restore
  sudo bash installer.sh --logs
  ```

## Credits

Original project creator: **caffeinexz**.
