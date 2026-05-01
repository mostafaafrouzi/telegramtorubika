import asyncio
import json
import os
import re
import time
import pyzipper
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from rubpy import Client as RubikaClient
from rubpy.crypto import Crypto
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from queue_db import QueueDB

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
APP_VERSION = os.getenv("APP_BUILD_VERSION", "telegramtorubika-dev")

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
QUEUE_DIR = BASE_DIR / "queue"
STATUS_FILE = QUEUE_DIR / "status.jsonl"
SETTINGS_FILE = QUEUE_DIR / "settings.json"
USERS_FILE = QUEUE_DIR / "users.json"
USER_STATES_FILE = QUEUE_DIR / "user_states.json"
BATCH_FILE = QUEUE_DIR / "batch_sessions.json"
NETWORK_FILE = QUEUE_DIR / "network.json"
FAILED_FILE = QUEUE_DIR / "failed.jsonl"
BOT_LOG_FILE = QUEUE_DIR / "bot_events.jsonl"
WORKER_EVENTS_FILE = QUEUE_DIR / "worker_events.jsonl"
KNOWN_CHATS_FILE = QUEUE_DIR / "known_chats.json"

ADMIN_IDS = {
    int(x.strip())
    for x in (os.getenv("ADMIN_IDS", "").split(",") if os.getenv("ADMIN_IDS") else [])
    if x.strip().isdigit()
}

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_DIR.mkdir(parents=True, exist_ok=True)

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise RuntimeError("Please set API_ID, API_HASH and BOT_TOKEN in .env")

app = Client(
    "tel2rub",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)
app.set_parse_mode(ParseMode.MARKDOWN)

I18N = {
    "fa": {
        "welcome": (
            "سلام 💙\n\n"
            "برای هر کاربر، روبیکا به‌صورت جداگانه متصل می‌شود.\n"
            "ابتدا این دستور را بزن:\n"
            "`/rubika_connect`\n\n"
            "از دکمه‌های منو وارد بخش‌های مختلف شو.\n"
            "`/menu` برای نمایش منوی اصلی\n"
            "`/lang` برای تغییر زبان"
        ),
        "menu_intro": (
            "منوی اصلی:\n"
            "- منوی اتصال: مدیریت اتصال روبیکا\n"
            "- منوی فایل‌ها: فایل ZIP، ارسال متن/لینک، مدیریت صف\n"
            "- منوی تنظیمات: حالت مستقیم\n"
            "- راهنما: نمایش دستورهای اصلی"
        ),
        "pick_lang": "زبان را انتخاب کن:",
        "lang_saved": "زبان ذخیره شد.",
        "rubika_menu_title": "منوی اتصال روبیکا",
        "files_menu_title": "منوی فایل‌ها و صف",
        "settings_menu_title": "منوی تنظیمات",
        "admin_menu_title": "منوی ادمین",
        "admin_denied": "دسترسی ادمین ندارید.",
        "no_worker_events": "فایل لاگ worker هنوز ساخته نشده.",
        "no_recent_jobs": "برای این چت رویداد task_done/task_failed اخیری ثبت نشده.",
        "recent_jobs_title": "آخرین کارها (worker):",
        "btn_main_connection": "منوی اتصال",
        "btn_main_files": "منوی فایل‌ها",
        "btn_main_settings": "منوی تنظیمات",
        "btn_main_help": "راهنما",
        "btn_main_net": "وضعیت شبکه",
        "btn_main_queue": "مدیریت صف",
        "btn_main_admin": "منوی ادمین",
        "btn_back_main": "بازگشت به منوی اصلی",
        "btn_rub_connect": "اتصال روبیکا",
        "btn_rub_status": "وضعیت روبیکا",
        "btn_zip_start": "شروع فایل ZIP",
        "btn_zip_end": "پایان فایل ZIP",
        "btn_send_link": "ارسال لینک",
        "btn_send_text": "ارسال متن",
        "btn_queue": "مدیریت صف",
        "btn_clear_all": "حذف همه",
        "btn_direct_on": "حالت مستقیم روشن",
        "btn_direct_off": "حالت مستقیم خاموش",
        "btn_admin_panel": "پنل ادمین",
        "btn_inline_refresh": "بروزرسانی",
        "btn_inline_pending": "نمایش Pending",
        "btn_inline_failed": "نمایش Failed",
        "btn_inline_clear": "پاکسازی صف من",
        "btn_inline_recent": "آخرین کارها",
        "queue_kb_refresh": "بروزرسانی شد",
        "queue_kb_cleared": "صف پاک شد",
        "directmode_usage": "Use: /directmode on یا /directmode off",
        "direct_on": "حالت مستقیم فعال شد.",
        "direct_off": "حالت مستقیم غیرفعال شد.",
        "newbatch_ok": (
            "جلسه فایل ZIP فعال شد.\n"
            "فایل‌ها را ارسال کن. بعد از اتمام، «پایان فایل ZIP» یا `/done` را بزن."
        ),
        "prompt_sendtext": "متن را ارسال کن.",
        "prompt_sendlink": "لینک را ارسال کن.",
        "queue_panel": (
            "مدیریت صف:\n\n"
            "- در انتظار ارسال: `{pending}`\n"
            "- کل خطاها (global): `{failed}`\n"
            "- حذف‌شده‌ها: `{deleted}`\n"
            "- لغوشده‌ها: `{cancelled}`\n\n"
            "برای پاکسازی صف از دکمهٔ «پاکسازی صف من» استفاده کن."
        ),
    },
    "en": {
        "welcome": (
            "Hi 💙\n\n"
            "Rubika is connected per Telegram user.\n"
            "Run:\n"
            "`/rubika_connect`\n\n"
            "Use the menu buttons.\n"
            "`/menu` main menu\n"
            "`/lang` change language"
        ),
        "menu_intro": (
            "Main menu:\n"
            "- Connection: Rubika link\n"
            "- Files: ZIP batch, text/link, queue\n"
            "- Settings: direct mode\n"
            "- Help: commands"
        ),
        "pick_lang": "Choose language:",
        "lang_saved": "Language saved.",
        "rubika_menu_title": "Rubika connection menu",
        "files_menu_title": "Files & queue menu",
        "settings_menu_title": "Settings menu",
        "admin_menu_title": "Admin menu",
        "admin_denied": "You are not an admin.",
        "no_worker_events": "Worker log file not found yet.",
        "no_recent_jobs": "No recent task_done/task_failed for this chat.",
        "recent_jobs_title": "Recent jobs (worker):",
        "btn_main_connection": "Connection menu",
        "btn_main_files": "Files menu",
        "btn_main_settings": "Settings menu",
        "btn_main_help": "Help",
        "btn_main_net": "Network status",
        "btn_main_queue": "Queue",
        "btn_main_admin": "Admin menu",
        "btn_back_main": "Main menu",
        "btn_rub_connect": "Connect Rubika",
        "btn_rub_status": "Rubika status",
        "btn_zip_start": "Start ZIP",
        "btn_zip_end": "End ZIP",
        "btn_send_link": "Send link",
        "btn_send_text": "Send text",
        "btn_queue": "Queue",
        "btn_clear_all": "Clear all",
        "btn_direct_on": "Direct mode on",
        "btn_direct_off": "Direct mode off",
        "btn_admin_panel": "Admin panel",
        "btn_inline_refresh": "Refresh",
        "btn_inline_pending": "Pending",
        "btn_inline_failed": "Failed",
        "btn_inline_clear": "Clear my queue",
        "btn_inline_recent": "Recent jobs",
        "queue_kb_refresh": "Refreshed",
        "queue_kb_cleared": "Queue cleared",
        "directmode_usage": "Use: /directmode on or /directmode off",
        "direct_on": "Direct mode enabled.",
        "direct_off": "Direct mode disabled.",
        "newbatch_ok": (
            "ZIP batch started.\n"
            "Send files, then tap «End ZIP» or `/done`."
        ),
        "prompt_sendtext": "Send the text.",
        "prompt_sendlink": "Send the link.",
        "queue_panel": (
            "Queue:\n\n"
            "- Pending (your session): `{pending}`\n"
            "- Failed (global): `{failed}`\n"
            "- Deleted: `{deleted}`\n"
            "- Cancelled: `{cancelled}`\n\n"
            "Use «Clear my queue» to wipe your pending tasks."
        ),
    },
}


def get_lang(user_id: int) -> str:
    users = load_users()
    lang = users.get(get_user_key(user_id), {}).get("lang")
    if lang in ("fa", "en"):
        return lang
    return "fa"


def set_lang(user_id: int, lang: str):
    if lang not in ("fa", "en"):
        lang = "fa"
    users = load_users()
    key = get_user_key(user_id)
    item = users.get(key, {})
    item["lang"] = lang
    users[key] = item
    save_users(users)


def tr(user_id: int, key: str, **kwargs) -> str:
    lang = get_lang(user_id)
    text = I18N.get(lang, I18N["fa"]).get(key) or I18N["fa"].get(key) or key
    try:
        return text.format(**kwargs)
    except Exception:
        return text


def remember_chat(chat_id: int):
    data = load_json(KNOWN_CHATS_FILE, {"ids": []})
    ids = data.get("ids", [])
    if chat_id not in ids:
        ids.append(chat_id)
        data["ids"] = ids
        save_json(KNOWN_CHATS_FILE, data)


def recent_jobs_summary(user_id: int, limit: int = 10) -> str:
    path = WORKER_EVENTS_FILE
    if not path.exists():
        return tr(user_id, "no_worker_events")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.readlines()
    except Exception:
        return tr(user_id, "no_worker_events")
    interested = []
    for line in reversed(raw[-8000:]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("chat_id") != user_id:
            continue
        ev = row.get("event")
        if ev not in ("task_done", "task_failed", "task_requeued"):
            continue
        interested.append(row)
        if len(interested) >= limit:
            break
    if not interested:
        return tr(user_id, "no_recent_jobs")
    lines = []
    for row in interested:
        ev = row.get("event")
        jid = row.get("job_id", "?")
        dur = row.get("duration_ms")
        err = (row.get("error") or "")[:120]
        if ev == "task_done":
            suf = f" {dur}ms" if dur is not None else ""
            lines.append(f"✅ `{jid}` done{suf}")
        elif ev == "task_failed":
            lines.append(f"❌ `{jid}` failed: `{err}`")
        else:
            lines.append(f"🔄 `{jid}` requeued")
    return "\n".join(lines)


def build_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(tr(user_id, "btn_main_connection")),
            KeyboardButton(tr(user_id, "btn_main_files")),
        ],
        [
            KeyboardButton(tr(user_id, "btn_main_settings")),
            KeyboardButton(tr(user_id, "btn_main_help")),
        ],
        [
            KeyboardButton(tr(user_id, "btn_main_net")),
            KeyboardButton(tr(user_id, "btn_main_queue")),
        ],
    ]
    if user_id in ADMIN_IDS:
        rows.append([KeyboardButton(tr(user_id, "btn_main_admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False)


def build_rubika_menu(user_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(tr(user_id, "btn_rub_connect")),
                KeyboardButton(tr(user_id, "btn_rub_status")),
            ],
            [KeyboardButton(tr(user_id, "btn_back_main"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_files_menu(user_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(tr(user_id, "btn_zip_start")),
                KeyboardButton(tr(user_id, "btn_zip_end")),
            ],
            [
                KeyboardButton(tr(user_id, "btn_send_link")),
                KeyboardButton(tr(user_id, "btn_send_text")),
            ],
            [
                KeyboardButton(tr(user_id, "btn_queue")),
                KeyboardButton(tr(user_id, "btn_clear_all")),
            ],
            [KeyboardButton(tr(user_id, "btn_back_main"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_settings_menu(user_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(tr(user_id, "btn_direct_on")),
                KeyboardButton(tr(user_id, "btn_direct_off")),
            ],
            [KeyboardButton(tr(user_id, "btn_back_main"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_admin_menu(user_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(tr(user_id, "btn_admin_panel")), KeyboardButton("/version")],
            [KeyboardButton(tr(user_id, "btn_back_main"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def safe_filename(name: Optional[str]) -> str:
    name = (name or "file.bin").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = name.rstrip(". ")
    return name[:200] or "file.bin"


def split_name(filename: str) -> tuple[str, str]:
    path = Path(filename)
    return path.stem, path.suffix


def get_media(message: Message):
    media_types = [
        ("document", message.document),
        ("video", message.video),
        ("audio", message.audio),
        ("voice", message.voice),
        ("photo", message.photo),
        ("animation", message.animation),
        ("video_note", message.video_note),
        ("sticker", message.sticker),
    ]

    for media_type, media in media_types:
        if media:
            return media_type, media

    return None, None


def build_download_filename(message: Message, media_type: str, media) -> str:
    original_name = getattr(media, "file_name", None)

    if not original_name:
        file_unique_id = getattr(media, "file_unique_id", None) or "file"

        default_extensions = {
            "document": ".bin",
            "video": ".mp4",
            "audio": ".mp3",
            "voice": ".ogg",
            "photo": ".jpg",
            "animation": ".mp4",
            "video_note": ".mp4",
            "sticker": ".webp",
        }

        original_name = f"{file_unique_id}{default_extensions.get(media_type, '.bin')}"

    original_name = safe_filename(original_name)
    stem, suffix = split_name(original_name)

    unique_name = f"{stem}_{message.id}{suffix or '.bin'}"
    return safe_filename(unique_name)


def make_bundle_zip_local(file_paths: list[Path], zip_name: str, password: str = "") -> Path:
    zip_base = safe_filename(zip_name or f"bundle_{int(time.time())}")
    zip_path = DOWNLOAD_DIR / f"{zip_base}.zip"
    if zip_path.exists():
        zip_path = DOWNLOAD_DIR / f"{zip_base}_{int(time.time())}.zip"
    if password:
        with pyzipper.AESZipFile(
            zip_path,
            "w",
            compression=pyzipper.ZIP_STORED,
            encryption=pyzipper.WZ_AES,
        ) as zip_file:
            zip_file.setpassword(password.encode("utf-8"))
            for file_path in file_paths:
                zip_file.write(file_path, arcname=file_path.name)
    else:
        with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_STORED) as zip_file:
            for file_path in file_paths:
                zip_file.write(file_path, arcname=file_path.name)
    return zip_path

waiting_for_zip_password = False


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_event(event: str, **kwargs):
    payload = {
        "ts": int(time.time()),
        "event": event,
        **kwargs,
    }
    try:
        with open(BOT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_users() -> dict:
    return load_json(USERS_FILE, {})


def save_users(data: dict):
    save_json(USERS_FILE, data)


def get_user_key(user_id: int) -> str:
    return str(user_id)


def get_user_session(user_id: int) -> Optional[str]:
    users = load_users()
    item = users.get(get_user_key(user_id), {})
    if item.get("connected"):
        return item.get("session")
    return None


def check_rubika_session_sync(session_name: str) -> tuple[bool, str]:
    client = RubikaClient(name=session_name)
    try:
        client.start()
        me = client.get_me()
        phone = getattr(getattr(me, "user", None), "phone", "")
        guid = getattr(getattr(me, "user", None), "user_guid", "")
        return True, f"phone={phone or 'unknown'} guid={guid or 'unknown'}"
    except Exception as e:
        return False, str(e)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def is_direct_mode(user_id: int) -> bool:
    users = load_users()
    item = users.get(get_user_key(user_id), {})
    return bool(item.get("direct_mode", False))


def set_direct_mode(user_id: int, enabled: bool):
    users = load_users()
    key = get_user_key(user_id)
    item = users.get(key, {})
    item["direct_mode"] = bool(enabled)
    users[key] = item
    save_users(users)


def load_user_states() -> dict:
    return load_json(USER_STATES_FILE, {})


def save_user_states(data: dict):
    save_json(USER_STATES_FILE, data)


def load_batch_sessions() -> dict:
    return load_json(BATCH_FILE, {})


def save_batch_sessions(data: dict):
    save_json(BATCH_FILE, data)


def get_state(user_id: int) -> dict:
    states = load_user_states()
    return states.get(get_user_key(user_id), {})


def set_state(user_id: int, data: dict):
    states = load_user_states()
    states[get_user_key(user_id)] = data
    save_user_states(states)


def clear_state(user_id: int):
    states = load_user_states()
    states.pop(get_user_key(user_id), None)
    save_user_states(states)


def get_batch(user_id: int) -> dict:
    sessions = load_batch_sessions()
    return sessions.get(get_user_key(user_id), {})


def set_batch(user_id: int, data: dict):
    sessions = load_batch_sessions()
    sessions[get_user_key(user_id)] = data
    save_batch_sessions(sessions)


def clear_batch(user_id: int):
    sessions = load_batch_sessions()
    sessions.pop(get_user_key(user_id), None)
    save_batch_sessions(sessions)


async def rubika_send_code(session_name: str, phone_number: str, pass_key: str = ""):
    client = RubikaClient(name=session_name)
    try:
        if not hasattr(client, "connection"):
            await client.connect()

        phone_number = phone_number.strip().replace(" ", "").replace("-", "").replace("+", "")
        if phone_number.startswith("0"):
            phone_number = f"98{phone_number[1:]}"

        kwargs = {"phone_number": phone_number, "send_type": "SMS"}
        if pass_key:
            kwargs["pass_key"] = pass_key
        result = await client.send_code(**kwargs)
        return result
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


def _deep_find_phone_hash(payload) -> Optional[str]:
    if payload is None:
        return None
    if hasattr(payload, "phone_code_hash"):
        value = getattr(payload, "phone_code_hash", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if hasattr(payload, "__dict__"):
        for value in vars(payload).values():
            found = _deep_find_phone_hash(value)
            if found:
                return found
    if isinstance(payload, dict):
        for key in ("phone_code_hash", "phoneCodeHash", "phone_codeHash", "phone_hash"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _deep_find_phone_hash(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _deep_find_phone_hash(item)
            if found:
                return found
    return None


def _deep_find_status(payload) -> str:
    if payload is None:
        return ""
    if hasattr(payload, "status"):
        value = getattr(payload, "status", "")
        if value:
            return str(value)
    if isinstance(payload, dict):
        if payload.get("status"):
            return str(payload.get("status"))
        for value in payload.values():
            found = _deep_find_status(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _deep_find_status(item)
            if found:
                return found
    if hasattr(payload, "__dict__"):
        for value in vars(payload).values():
            found = _deep_find_status(value)
            if found:
                return found
    return ""


async def rubika_sign_in(session_name: str, phone_number: str, phone_code_hash: str, code: str):
    client = RubikaClient(name=session_name)
    try:
        if not hasattr(client, "connection"):
            await client.connect()

        phone_number = phone_number.strip().replace(" ", "").replace("-", "").replace("+", "")
        if phone_number.startswith("0"):
            phone_number = f"98{phone_number[1:]}"

        public_key, private_key = Crypto.create_keys()
        result = await client.sign_in(
            phone_code=str(code).strip(),
            phone_number=phone_number,
            phone_code_hash=phone_code_hash,
            public_key=public_key,
        )
        status = getattr(result, "status", "")
        if str(status).upper() != "OK":
            raise RuntimeError(f"Rubika sign_in failed: {status}")

        auth = Crypto.decrypt_RSA_OAEP(private_key, result.auth)
        client.key = Crypto.passphrase(auth)
        client.auth = auth
        client.decode_auth = Crypto.decode_auth(auth)
        client.private_key = private_key
        client.import_key = pkcs1_15.new(RSA.import_key(client.private_key.encode()))
        client.session.insert(
            auth=client.auth,
            guid=result.user.user_guid,
            user_agent=client.user_agent,
            phone_number=result.user.phone,
            private_key=client.private_key,
        )
        await client.register_device(device_model=session_name)
        await client.get_me()
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

queue = QueueDB()


def mark_deleted(task: dict):
    queue.mark_deleted(task)


def mark_cancelled(task: dict):
    job_id = str(task.get("job_id", "")).strip()
    if job_id:
        queue.cancel_job(job_id)


def cancel_job(job_id: str):
    queue.cancel_job(str(job_id))


def was_deleted(job_id=None, message_id=None) -> bool:
    return queue.was_deleted(job_id=job_id, message_id=message_id)

def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

    return {"safe_mode": False, "zip_password": ""}

def save_settings(data: dict):
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def is_direct_url(text: str) -> bool:
    if not text:
        return False

    url = extract_first_url(text)
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_first_url(text: str) -> Optional[str]:
    if not text:
        return None

    match = re.search(r"https?://\S+", text)
    return match.group(0) if match else None


def progress_bar(percent: float, length: int = 12) -> str:
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled)


def pretty_size(size) -> str:
    size = float(size or 0)
    units = ["B", "KB", "MB", "GB"]

    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f} {units[index]}"


def eta_text(seconds) -> str:
    if not seconds or seconds <= 0:
        return "نامشخص"

    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


async def download_progress(current, total, status_message, file_name, started_at, state):
    now = time.time()

    if now - state.get("last_update", 0) < 3 and current < total:
        return

    state["last_update"] = now

    percent = current * 100 / total if total else 0
    elapsed = max(now - started_at, 1)
    speed = current / elapsed
    eta = (total - current) / speed if speed else None

    text = (
        f"📥 در حال دریافت فایل از تلگرام\n\n"
        f"فایل: `{file_name}`\n"
        f"حجم: `{pretty_size(total)}`\n"
        f"پیشرفت: `{percent:.1f}%`\n"
        f"`{progress_bar(percent)}`\n"
        f"سرعت: `{pretty_size(speed)}/s`\n"
        f"زمان باقی‌مانده: `{eta_text(eta)}`"
    )

    try:
        await status_message.edit_text(text)
    except Exception:
        pass

async def status_watcher():
    pos = 0
    while True:
        await asyncio.sleep(1)
        if not STATUS_FILE.exists():
            continue
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                f.seek(pos)
                lines = f.readlines()
                pos = f.tell()
            for line in lines:
                if not line.strip():
                    continue
                data = json.loads(line)
                chat_id = data.get("chat_id")
                msg_id = data.get("message_id")
                text = data.get("text", "")
                percent = data.get("percent")
                if not chat_id or not msg_id:
                    continue
                if percent is not None:
                    text += f"\n\n`{progress_bar(float(percent))}` `{float(percent):.1f}%`"
                try:
                    await app.edit_message_text(chat_id, msg_id, text)
                except Exception:
                    pass
        except Exception:
            pass

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    uid = message.from_user.id
    remember_chat(message.chat.id)
    await message.reply_text(
        tr(uid, "welcome"),
        reply_markup=build_main_menu(uid),
    )


@app.on_message(filters.private & filters.command("menu"))
async def menu_handler(client: Client, message: Message):
    uid = message.from_user.id
    await message.reply_text(
        tr(uid, "menu_intro"),
        reply_markup=build_main_menu(uid),
    )


@app.on_message(filters.private & filters.command("lang"))
async def lang_handler(client: Client, message: Message):
    uid = message.from_user.id
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("فارسی", callback_data="setlang:fa"),
                InlineKeyboardButton("English", callback_data="setlang:en"),
            ],
        ]
    )
    await message.reply_text(tr(uid, "pick_lang"), reply_markup=kb)


@app.on_message(filters.private & filters.command("help"))
async def help_handler(client: Client, message: Message):
    await message.reply_text(
        "راهنمای سریع:\n\n"
        "منوی اتصال:\n"
        "- اتصال روبیکا: `/rubika_connect`\n"
        "- وضعیت روبیکا: `/rubika_status`\n\n"
        "منوی فایل‌ها:\n"
        "- شروع فایل ZIP: `/newbatch`\n"
        "- پایان فایل ZIP: `/done`\n"
        "- ارسال متن: `/sendtext متن`\n"
        "- ارسال لینک: `/sendlink https://...`\n"
        "- پاکسازی صف: `/delall`\n\n"
        "منوی تنظیمات:\n"
        "- حالت مستقیم: `/directmode on|off`\n"
        "- safe mode: `/safemode on|off`\n\n"
        "عیب‌یابی:\n"
        "- وضعیت شبکه: `/netstatus`\n"
        "- پنل ادمین: `/admin`\n"
        "- حذف یک job: `/del <job_id>`\n\n"
        "برای راهنمای تحلیل لاگ: `/loghelp`"
    )


@app.on_message(filters.private & filters.command("loghelp"))
async def log_help_handler(client: Client, message: Message):
    await message.reply_text(
        "راهنمای تحلیل لاگ job:\n\n"
        "1) ابتدا `job_id` را از پیام Queued بردار.\n"
        "2) در bot logs دنبال `task_queued` با همان `job_id` بگرد.\n"
        "3) در worker logs باید به‌ترتیب ببینی:\n"
        "   `task_started` -> (`task_done` یا `task_failed`).\n"
        "4) اگر `task_requeued` دیدی، مشکل شبکه/دسترسی بوده و job جدید ساخته شده.\n"
        "5) برای اتصال روبیکا، eventهای `rubika_connect_ok` یا `rubika_connect_failed` را چک کن.\n\n"
        "مسیر لاگ‌ها:\n"
        "- `/opt/tele2rub/queue/bot_events.jsonl`\n"
        "- `/opt/tele2rub/queue/worker_events.jsonl`\n"
        "- `/tmp/tele2rub-installer.jsonl`"
    )


@app.on_message(filters.private & filters.command("version"))
async def version_handler(client: Client, message: Message):
    await message.reply_text(f"telegramtorubika `{APP_VERSION}`")


@app.on_message(filters.private & filters.command("rubika_status"))
async def rubika_status_handler(client: Client, message: Message):
    session_name = get_user_session(message.from_user.id)
    if not session_name:
        await message.reply_text("روبیکا متصل نیست. از `/rubika_connect` استفاده کن.")
        return
    await message.reply_text("در حال بررسی وضعیت واقعی اتصال روبیکا ...")
    ok_session, details = await asyncio.to_thread(check_rubika_session_sync, session_name)
    if ok_session:
        await message.reply_text(
            f"اتصال روبیکا فعال و معتبر است ✅\n"
            f"session: `{session_name}`\n"
            f"جزئیات: `{details}`"
        )
    else:
        await message.reply_text(
            f"اتصال ذخیره‌شده معتبر نیست ❌\n"
            f"session: `{session_name}`\n"
            f"خطا: `{details}`\n\n"
            f"لطفاً دوباره از دکمه «اتصال روبیکا» استفاده کن."
        )


@app.on_message(filters.private & filters.command("rubika_connect"))
async def rubika_connect_handler(client: Client, message: Message):
    user_id = message.from_user.id
    current_session = get_user_session(user_id)
    if current_session:
        await message.reply_text(
            f"اکانت روبیکا از قبل متصل است.\n"
            f"session: `{current_session}`\n\n"
            f"برای اتصال مجدد، شماره جدید را ارسال کن."
        )
    set_state(user_id, {"step": "await_phone"})
    log_event("rubika_connect_started", user_id=user_id)
    await message.reply_text(
        "شماره روبیکا را با پیش‌شماره کشور ارسال کن.\n"
        "مثال: `98912xxxxxxx`"
    )


@app.on_message(filters.private & filters.command("directmode"))
async def direct_mode_handler(client: Client, message: Message):
    uid = message.from_user.id
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text(tr(uid, "directmode_usage"))
        return
    action = args[1].strip().lower()
    if action == "on":
        set_direct_mode(uid, True)
        await message.reply_text(tr(uid, "direct_on"), reply_markup=build_settings_menu(uid))
        return
    if action == "off":
        set_direct_mode(uid, False)
        await message.reply_text(
            tr(uid, "direct_off"),
            reply_markup=build_main_menu(uid),
        )
        return
    await message.reply_text(tr(uid, "directmode_usage"))


@app.on_message(filters.private & filters.command("netstatus"))
async def netstatus_handler(client: Client, message: Message):
    data = load_json(NETWORK_FILE, {"mode": "unknown", "reason": "", "updated_at": 0})
    mode = data.get("mode", "unknown")
    reason = data.get("reason", "")
    updated = data.get("updated_at", 0)
    await message.reply_text(
        f"وضعیت شبکه: `{mode}`\n"
        f"دلیل: `{reason or '---'}`\n"
        f"آخرین بروزرسانی: `{updated}`"
    )


def failed_count() -> int:
    if not FAILED_FILE.exists():
        return 0
    try:
        with open(FAILED_FILE, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


async def queue_or_confirm(message: Message, task: dict, summary: str):
    user_id = message.from_user.id
    if is_direct_mode(user_id):
        status = await message.reply_text("Queued for processing...")
        task["chat_id"] = message.chat.id
        task["status_message_id"] = status.id
        pushed = queue.push_task(task)
        qpos = queue.queue_count_by_session(task.get("rubika_session") or "")
        log_event(
            "task_queued",
            user_id=user_id,
            job_id=pushed.get("job_id"),
            task_type=task.get("type"),
            direct_mode=True,
        )
        await status.edit_text(
            f"در صف قرار گرفت ✅\n"
            f"Job: `{pushed['job_id']}`\n"
            f"جایگاه تقریبی در صف شما: `{qpos}`\n\n"
            f"برای مشاهده جزئیات، «مدیریت صف» را بزن."
        )
        return

    set_state(
        user_id,
        {
            "step": "await_send_confirm",
            "pending_task": task,
            "pending_summary": summary,
        },
    )
    await message.reply_text(
        f"{summary}\n\nSend to Rubika now?",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm Send", callback_data="confirm_send")],
                [InlineKeyboardButton("Cancel", callback_data="cancel_send")],
            ]
        ),
    )
    log_event(
        "task_confirm_requested",
        user_id=user_id,
        task_type=task.get("type"),
    )
    

async def safe_delete_user_message(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


async def edit_wizard(chat_id: int, wizard_message_id: int, text: str):
    try:
        await app.edit_message_text(chat_id=chat_id, message_id=wizard_message_id, text=text)
    except Exception:
        pass


@app.on_message(filters.private & filters.command("admin"))
async def admin_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        await message.reply_text(tr(uid, "admin_denied"))
        return
    net = load_json(NETWORK_FILE, {"mode": "unknown", "reason": "", "updated_at": 0})
    await message.reply_text(
        "پنل ادمین:\n\n"
        f"Queue total: `{queue.queue_count()}`\n"
        f"Cancelled jobs: `{queue.cancelled_count()}`\n"
        f"Deleted jobs: `{queue.deleted_count()}`\n"
        f"Failed jobs: `{failed_count()}`\n"
        f"Network mode: `{net.get('mode', 'unknown')}`\n"
        f"Reason: `{net.get('reason', '')}`",
        reply_markup=build_admin_menu(uid),
    )

@app.on_message(filters.private & filters.command("safemode"))
async def safemode_handler(client: Client, message: Message):
    global waiting_for_zip_password

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.reply_text("برای تغییر وضعیت Safe Mode از `/safemode on` یا `/safemode off` استفاده کن.")
        return

    action = args[1].strip().lower()
    settings = load_settings()

    if action == "on":
        settings["safe_mode"] = True
        save_settings(settings)
        waiting_for_zip_password = True

        await message.reply_text(
            "Safe Mode فعال شد.\n\n"
            "لطفا رمزی که می‌خواهید روی فایل‌های ZIP قرار بگیرد را ارسال کنید.\n"
            "از این به بعد فایل‌ها قبل از ارسال به روبیکا با همین رمز ZIP می‌شوند."
        )
        return

    if action == "off":
        settings["safe_mode"] = False
        settings["zip_password"] = ""
        save_settings(settings)
        waiting_for_zip_password = False

        await message.reply_text(
            "Safe Mode غیرفعال شد.\n\n"
            "از این به بعد فایل‌ها به‌صورت عادی ارسال می‌شوند."
        )
        return

    await message.reply_text("دستور نامعتبر است. از `/safemode on` یا `/safemode off` استفاده کن.")


@app.on_message(filters.private & filters.command("delall"))
async def clear_queue_handler(client: Client, message: Message, acting_user_id: Optional[int] = None):
    uid = acting_user_id if acting_user_id is not None else message.from_user.id
    user_session = get_user_session(uid)
    tasks = [t for t in queue.all_tasks() if t.get("rubika_session") == user_session]

    if not tasks:
        await message.reply_text("صف خالی است.")
        return

    for task in tasks:
        mark_deleted(task)

        old_path = task.get("path")
        if old_path:
            try:
                path = Path(old_path)
                if path.exists():
                    path.unlink()
            except Exception:
                pass

        try:
            await client.edit_message_text(
                chat_id=task["chat_id"],
                message_id=task["status_message_id"],
                text="این مورد از صف حذف شد."
            )
        except Exception:
            pass

    queue.remove_tasks_by_session(user_session)
    await message.reply_text("تمام موارد در صف پاک شد.")

@app.on_message(filters.private & filters.command("newbatch"))
async def new_batch_handler(client: Client, message: Message):
    set_batch(
        message.from_user.id,
        {
            "active": True,
            "files": [],
            "created_at": int(time.time()),
        },
    )
    uid = message.from_user.id
    await message.reply_text(
        tr(uid, "newbatch_ok"),
        reply_markup=build_files_menu(uid),
    )


@app.on_message(filters.private & filters.command("done"))
async def done_batch_handler(client: Client, message: Message):
    batch = get_batch(message.from_user.id)
    files = batch.get("files", [])
    if not batch.get("active") or not files:
        await message.reply_text("جلسه فایل ZIP فعالی پیدا نشد یا فایل ندارد.")
        return
    wizard = await message.reply_text("نام فایل ZIP را ارسال کن (بدون پسوند).")
    set_state(
        message.from_user.id,
        {
            "step": "await_zip_name",
            "batch_files": files,
            "wizard_message_id": wizard.id,
            "wizard_chat_id": message.chat.id,
        },
    )


@app.on_callback_query()
async def callback_handler(client: Client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data or ""
    state = get_state(user_id)

    if data.startswith("setlang:"):
        lang = data.split(":", 1)[1]
        if lang in ("fa", "en"):
            set_lang(user_id, lang)
            await callback_query.answer(tr(user_id, "lang_saved"))
            try:
                await callback_query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback_query.message.reply_text(
                tr(user_id, "lang_saved"),
                reply_markup=build_main_menu(user_id),
            )
        return

    if data.startswith("queue:"):
        action = data.split(":", 1)[1]
        if action == "refresh":
            await callback_query.answer(tr(user_id, "queue_kb_refresh"))
            await queue_manage_handler(
                client,
                callback_query.message,
                edit_existing=True,
                target_user_id=user_id,
            )
            return
        if action == "clearall":
            await clear_queue_handler(client, callback_query.message, acting_user_id=user_id)
            await callback_query.answer(tr(user_id, "queue_kb_cleared"))
            return
        if action == "pending":
            session = get_user_session(user_id)
            count = queue.queue_count_by_session(session or "")
            await callback_query.answer(f"Pending: {count}", show_alert=True)
            return
        if action == "failed":
            await callback_query.answer(f"Failed: {failed_count()}", show_alert=True)
            return
        if action == "history":
            await callback_query.answer()
            body = recent_jobs_summary(user_id)
            title = tr(user_id, "recent_jobs_title")
            await callback_query.message.reply_text(f"{title}\n\n{body}")
            return

    if data == "confirm_send" and state.get("step") == "await_send_confirm":
        task = state.get("pending_task")
        if not task:
            await callback_query.answer("Pending task not found", show_alert=True)
            return
        status = await callback_query.message.reply_text("Queued for processing...")
        task["chat_id"] = callback_query.message.chat.id
        task["status_message_id"] = status.id
        task = queue.push_task(task)
        qpos = queue.queue_count_by_session(task.get("rubika_session") or "")
        clear_state(user_id)
        log_event(
            "task_queued",
            user_id=user_id,
            job_id=task.get("job_id"),
            task_type=task.get("type"),
            direct_mode=False,
        )
        await status.edit_text(
            f"در صف قرار گرفت ✅\n"
            f"Job: `{task['job_id']}`\n"
            f"جایگاه تقریبی در صف شما: `{qpos}`\n\n"
            f"برای مشاهده جزئیات، «مدیریت صف» را بزن."
        )
        await callback_query.answer("Queued")
        return

    if data == "cancel_send" and state.get("step") == "await_send_confirm":
        clear_state(user_id)
        log_event("task_confirm_cancelled", user_id=user_id)
        await callback_query.message.reply_text("Canceled.")
        await callback_query.answer("Canceled")
        return

    await callback_query.answer("این گزینه منقضی شده یا معتبر نیست.", show_alert=True)


@app.on_message(filters.private & filters.command("sendtext"))
async def send_text_handler(client: Client, message: Message):
    session_name = get_user_session(message.from_user.id)
    if not session_name:
        await message.reply_text("ابتدا روبیکا را وصل کن: `/rubika_connect`")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("فرمت درست: `/sendtext متن`")
        return
    task = {
        "type": "text_message",
        "text": parts[1].strip(),
        "rubika_session": session_name,
    }
    status = await message.reply_text("در حال قرار دادن متن در صف ...")
    task["chat_id"] = message.chat.id
    task["status_message_id"] = status.id
    pushed = queue.push_task(task)
    qpos = queue.queue_count_by_session(session_name)
    log_event(
        "task_queued",
        user_id=message.from_user.id,
        job_id=pushed.get("job_id"),
        task_type="text_message",
        direct_mode=is_direct_mode(message.from_user.id),
    )
    await status.edit_text(
        f"متن در صف قرار گرفت ✅\n"
        f"Job: `{pushed['job_id']}`\n"
        f"جایگاه تقریبی در صف شما: `{qpos}`\n\n"
        f"برای مشاهده جزئیات، «مدیریت صف» را بزن."
    )


@app.on_message(filters.private & filters.command("sendlink"))
async def send_link_handler(client: Client, message: Message):
    session_name = get_user_session(message.from_user.id)
    if not session_name:
        await message.reply_text("ابتدا روبیکا را وصل کن: `/rubika_connect`")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("فرمت درست: `/sendlink <url>`")
        return
    url = extract_first_url(parts[1])
    if not url:
        await message.reply_text("لینک نامعتبر است.")
        return
    task = {
        "type": "text_message",
        "text": url,
        "rubika_session": session_name,
    }
    status = await message.reply_text("در حال قرار دادن لینک در صف ...")
    task["chat_id"] = message.chat.id
    task["status_message_id"] = status.id
    pushed = queue.push_task(task)
    qpos = queue.queue_count_by_session(session_name)
    log_event(
        "task_queued",
        user_id=message.from_user.id,
        job_id=pushed.get("job_id"),
        task_type="text_message",
        direct_mode=is_direct_mode(message.from_user.id),
    )
    await status.edit_text(
        f"لینک در صف قرار گرفت ✅\n"
        f"Job: `{pushed['job_id']}`\n"
        f"جایگاه تقریبی در صف شما: `{qpos}`\n\n"
        f"برای مشاهده جزئیات، «مدیریت صف» را بزن."
    )


@app.on_message(filters.private & filters.command("queue"))
async def queue_manage_handler(
    client: Client,
    message: Message,
    edit_existing: bool = False,
    target_user_id: Optional[int] = None,
):
    user_id = target_user_id if target_user_id is not None else message.from_user.id
    session = get_user_session(user_id)
    pending = queue.queue_count_by_session(session or "")
    summary = tr(
        user_id,
        "queue_panel",
        pending=pending,
        failed=failed_count(),
        deleted=queue.deleted_count(),
        cancelled=queue.cancelled_count(),
    )
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr(user_id, "btn_inline_refresh"), callback_data="queue:refresh")],
            [
                InlineKeyboardButton(tr(user_id, "btn_inline_pending"), callback_data="queue:pending"),
                InlineKeyboardButton(tr(user_id, "btn_inline_failed"), callback_data="queue:failed"),
            ],
            [InlineKeyboardButton(tr(user_id, "btn_inline_recent"), callback_data="queue:history")],
            [InlineKeyboardButton(tr(user_id, "btn_inline_clear"), callback_data="queue:clearall")],
        ]
    )
    if edit_existing:
        try:
            await message.edit_text(summary, reply_markup=kb)
            return
        except Exception:
            pass
    await message.reply_text(summary, reply_markup=kb)


@app.on_message(filters.private & filters.command("del"))
async def delete_one_handler(client: Client, message: Message):
    job_id = None
    reply_message_id = None

    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        job_id = parts[1].strip()

    if message.reply_to_message:
        reply_message_id = message.reply_to_message.id

    tasks = queue.all_tasks()

    if not tasks:
        if job_id and was_deleted(job_id=job_id):
            await message.reply_text("این مورد قبلاً از صف حذف شده است.")
            return

        if reply_message_id and was_deleted(message_id=reply_message_id):
            await message.reply_text("این مورد قبلاً از صف حذف شده است.")
            return

        if job_id:
            cancel_job(job_id)
            await message.reply_text(
                "لغو ثبت شد.\n\n"
            )
            return

        await message.reply_text("موردی برای حذف در صف پیدا نشد.")
        return

    removed = queue.remove_task(job_id=job_id, message_id=reply_message_id)

    if removed:
        mark_deleted(removed)

        old_path = removed.get("path")
        if old_path:
            try:
                path = Path(old_path)
                if path.exists():
                    path.unlink()
            except Exception:
                pass

        try:
            await client.edit_message_text(
                chat_id=removed["chat_id"],
                message_id=removed["status_message_id"],
                text="این مورد از صف حذف شد."
            )
        except Exception:
            pass

        await message.reply_text("از صف حذف شد.")
        return

    if job_id and was_deleted(job_id=job_id):
        await message.reply_text("این مورد قبلاً از صف حذف شده است.")
        return

    if reply_message_id and was_deleted(message_id=reply_message_id):
        await message.reply_text("این مورد قبلاً از صف حذف شده است.")
        return

    if job_id:
        cancel_job(job_id)
        await message.reply_text("دستور لغو ثبت شد.") 
        return


@app.on_message(filters.private & filters.text & ~filters.command(["start", "menu", "lang", "help", "loghelp", "version", "rubika_status", "rubika_connect", "directmode", "netstatus", "admin", "safemode", "del", "delall", "newbatch", "done", "sendtext", "sendlink", "queue"]))
async def text_handler(client: Client, message: Message):
    global waiting_for_zip_password

    text = message.text or ""
    user_id = message.from_user.id
    state = get_state(user_id)

    button_map = {
        "menu": "/menu",
        "منو": "/menu",
        "help": "/help",
        "راهنما": "/help",
        "راهنمای لاگ": "/loghelp",
        "back to main menu": "/menu",
        "بازگشت به منوی اصلی": "/menu",
        "rubika menu": "/show_rubika_menu",
        "منوی اتصال": "/show_rubika_menu",
        "files menu": "/show_files_menu",
        "منوی فایل‌ها": "/show_files_menu",
        "zip files start": "/newbatch",
        "شروع فایل zip": "/newbatch",
        "zip files done": "/done",
        "پایان فایل zip": "/done",
        "settings menu": "/show_settings_menu",
        "منوی تنظیمات": "/show_settings_menu",
        "admin menu": "/show_admin_menu",
        "منوی ادمین": "/show_admin_menu",
        "rubika connect": "/rubika_connect",
        "اتصال روبیکا": "/rubika_connect",
        "rubika status": "/rubika_status",
        "وضعیت روبیکا": "/rubika_status",
        "new batch": "/newbatch",
        "شروع بچ": "/newbatch",
        "شروع بچ فایل zip": "/newbatch",
        "done batch": "/done",
        "پایان بچ": "/done",
        "پایان بچ فایل zip": "/done",
        "send text": "/sendtext",
        "ارسال متن": "/sendtext",
        "send link": "/sendlink",
        "ارسال لینک": "/sendlink",
        "delete all": "/delall",
        "حذف همه": "/delall",
        "queue management": "/queue",
        "مدیریت صف": "/queue",
        "network status": "/netstatus",
        "وضعیت شبکه": "/netstatus",
        "admin panel": "/admin",
        "پنل ادمین": "/admin",
        "direct mode on": "/directmode on",
        "حالت مستقیم روشن": "/directmode on",
        "direct mode off": "/directmode off",
        "حالت مستقیم خاموش": "/directmode off",
        "connection menu": "/show_rubika_menu",
        "start zip": "/newbatch",
        "end zip": "/done",
        "main menu": "/menu",
        "queue": "/queue",
    }
    mapped = button_map.get(text.strip().lower())
    if mapped == "/menu":
        await menu_handler(client, message)
        return
    if mapped == "/help":
        await help_handler(client, message)
        return
    if mapped == "/loghelp":
        await log_help_handler(client, message)
        return
    if mapped == "/show_rubika_menu":
        await message.reply_text(tr(user_id, "rubika_menu_title"), reply_markup=build_rubika_menu(user_id))
        return
    if mapped == "/show_files_menu":
        await message.reply_text(tr(user_id, "files_menu_title"), reply_markup=build_files_menu(user_id))
        return
    if mapped == "/show_settings_menu":
        await message.reply_text(tr(user_id, "settings_menu_title"), reply_markup=build_settings_menu(user_id))
        return
    if mapped == "/show_admin_menu":
        if user_id in ADMIN_IDS:
            await message.reply_text(tr(user_id, "admin_menu_title"), reply_markup=build_admin_menu(user_id))
        else:
            await message.reply_text(tr(user_id, "admin_denied"))
        return
    if mapped == "/rubika_connect":
        await rubika_connect_handler(client, message)
        return
    if mapped == "/rubika_status":
        await rubika_status_handler(client, message)
        return
    if mapped == "/newbatch":
        await new_batch_handler(client, message)
        return
    if mapped == "/done":
        await done_batch_handler(client, message)
        return
    if mapped == "/delall":
        await clear_queue_handler(client, message)
        return
    if mapped == "/queue":
        await queue_manage_handler(client, message)
        return
    if mapped == "/netstatus":
        await netstatus_handler(client, message)
        return
    if mapped == "/admin":
        await admin_handler(client, message)
        return
    if mapped == "/directmode on":
        message.text = "/directmode on"
        await direct_mode_handler(client, message)
        return
    if mapped == "/directmode off":
        message.text = "/directmode off"
        await direct_mode_handler(client, message)
        return
    if mapped in {"/sendtext", "/sendlink"}:
        prompt_map = {
            "/sendtext": ("await_sendtext_input", tr(user_id, "prompt_sendtext")),
            "/sendlink": ("await_sendlink_input", tr(user_id, "prompt_sendlink")),
        }
        step, prompt = prompt_map[mapped]
        set_state(user_id, {"step": step})
        await message.reply_text(prompt)
        return

    if state.get("step") == "await_sendtext_input":
        set_state(user_id, {})
        message.text = f"/sendtext {text}"
        await send_text_handler(client, message)
        return

    if state.get("step") == "await_sendlink_input":
        set_state(user_id, {})
        message.text = f"/sendlink {text}"
        await send_link_handler(client, message)
        return

    if state.get("step") == "await_phone":
        phone = text.strip().replace("+", "")
        session_name = f"rubika_{user_id}"
        try:
            result = await rubika_send_code(session_name, phone)
            phone_hash = _deep_find_phone_hash(result)
            status = _deep_find_status(result).upper()
            if status == "SENDPASSKEY":
                set_state(
                    user_id,
                    {
                        "step": "await_pass_key",
                        "session_name": session_name,
                        "phone_number": phone,
                    },
                )
                await message.reply_text("این شماره نیاز به PassKey دارد. PassKey روبیکا را ارسال کن.")
                return
            if not phone_hash:
                raise RuntimeError(f"phone_code_hash پیدا نشد. status={status or 'unknown'}")
            set_state(
                user_id,
                {
                    "step": "await_code",
                    "session_name": session_name,
                    "phone_number": phone,
                    "phone_code_hash": phone_hash,
                },
            )
            await message.reply_text("کد ارسال شد. کد تایید روبیکا را بفرست.")
        except Exception as e:
            clear_state(user_id)
            await message.reply_text(f"خطا در ارسال کد روبیکا: {e}")
        return

    if state.get("step") == "await_pass_key":
        pass_key = text.strip()
        session_name = state.get("session_name", "")
        phone_number = state.get("phone_number", "")
        try:
            result = await rubika_send_code(session_name, phone_number, pass_key=pass_key)
            phone_hash = _deep_find_phone_hash(result)
            status = _deep_find_status(result).upper()
            if not phone_hash:
                raise RuntimeError(f"phone_code_hash پیدا نشد. status={status or 'unknown'}")
            set_state(
                user_id,
                {
                    "step": "await_code",
                    "session_name": session_name,
                    "phone_number": phone_number,
                    "phone_code_hash": phone_hash,
                },
            )
            await message.reply_text("کد ارسال شد. کد تایید روبیکا را بفرست.")
        except Exception as e:
            clear_state(user_id)
            await message.reply_text(f"خطا در ارسال کد روبیکا: {e}")
        return

    if state.get("step") == "await_code":
        code = text.strip()
        session_name = state.get("session_name", "")
        phone_number = state.get("phone_number", "")
        phone_code_hash = state.get("phone_code_hash", "")
        try:
            await rubika_sign_in(session_name, phone_number, phone_code_hash, code)
            users = load_users()
            key = get_user_key(user_id)
            prev = users.get(key, {})
            users[key] = {
                **prev,
                "connected": True,
                "session": session_name,
                "phone_number": phone_number,
                "connected_at": int(time.time()),
            }
            save_users(users)
            clear_state(user_id)
            await message.reply_text("روبیکا با موفقیت متصل شد ✅")
            log_event("rubika_connect_ok", user_id=user_id, session=session_name)
        except Exception as e:
            clear_state(user_id)
            log_event("rubika_connect_failed", user_id=user_id, error=str(e))
            await message.reply_text(f"کد تایید نامعتبر یا خطای ورود: {e}")
        return

    if state.get("step") == "await_zip_name":
        zip_name = safe_filename(text.strip() or "bundle")
        await safe_delete_user_message(message)
        await edit_wizard(
            state.get("wizard_chat_id", message.chat.id),
            int(state.get("wizard_message_id", 0) or 0),
            "سایز هر پارت (MB) را بفرست. مثال: 1900",
        )
        set_state(
            user_id,
            {
                "step": "await_part_mb",
                "zip_name": zip_name,
                "batch_files": state.get("batch_files", []),
                "wizard_message_id": state.get("wizard_message_id"),
                "wizard_chat_id": state.get("wizard_chat_id"),
            },
        )
        return

    if state.get("step") == "await_part_mb":
        try:
            part_mb = int(text.strip())
        except Exception:
            await message.reply_text("عدد معتبر بفرست. مثال: 1900")
            return
        if part_mb < 50:
            await message.reply_text("حداقل سایز پارت 50MB است.")
            return
        await safe_delete_user_message(message)
        files = state.get("batch_files", [])
        session_name = get_user_session(user_id)
        file_paths = [Path(p) for p in files if Path(p).exists()]
        if not file_paths:
            await message.reply_text("فایلی برای ساخت ZIP پیدا نشد.")
            clear_state(user_id)
            clear_batch(user_id)
            return
        settings = load_settings()
        zip_password = settings.get("zip_password", "") if settings.get("safe_mode", False) else ""
        zip_path = make_bundle_zip_local(file_paths, state.get("zip_name", "bundle"), zip_password)
        total_size = sum(p.stat().st_size for p in file_paths if p.exists())
        if zip_path.stat().st_size > 45 * 1024 * 1024:
            await message.reply_text(
                "⚠️ حجم فایل ZIP بزرگ است. تلگرام ممکن است ارسال فایل در چت را رد کند؛ "
                "فایل روی سرور آماده است و می‌تواند به روبیکا ارسال شود."
            )
        for p in file_paths:
            try:
                p.unlink()
            except Exception:
                pass
        try:
            await message.reply_document(
                str(zip_path),
                caption=(
                    f"فایل ZIP آماده شد ✅\n"
                    f"تعداد فایل‌ها: `{len(file_paths)}`\n"
                    f"حجم کل ورودی: `{pretty_size(total_size)}`\n"
                    f"حجم ZIP: `{pretty_size(zip_path.stat().st_size)}`"
                ),
            )
        except Exception:
            await message.reply_text(
                f"فایل ZIP آماده شد ✅\n"
                f"تعداد فایل‌ها: `{len(file_paths)}`\n"
                f"حجم کل ورودی: `{pretty_size(total_size)}`\n"
                f"حجم ZIP: `{pretty_size(zip_path.stat().st_size)}`\n"
                f"(ارسال فایل ZIP در تلگرام ناموفق بود، اما روی سرور آماده است)"
            )
        task = {
            "type": "local_file",
            "path": str(zip_path),
            "file_name": zip_path.name,
            "file_size": zip_path.stat().st_size,
            "part_size_mb": part_mb,
            "rubika_session": session_name,
            "safe_mode": False,
            "zip_password": "",
        }
        clear_state(user_id)
        clear_batch(user_id)
        await queue_or_confirm(message, task, f"ZIP آماده شد: `{zip_path.name}`\nآیا می‌خواهی به روبیکا ارسال شود؟")
        return

    if waiting_for_zip_password:
        password = text.strip()

        if not password:
            await message.reply_text("رمز نمی‌تواند خالی باشد. لطفاً یک رمز معتبر ارسال کنید.")
            return

        settings = load_settings()
        settings["safe_mode"] = True
        settings["zip_password"] = password
        save_settings(settings)

        waiting_for_zip_password = False

        await message.reply_text(
            "رمز ذخیره شد.\n\n"
            "از این به بعد فایل‌ها قبل از ارسال به روبیکا به‌صورت ZIP رمزدار آماده می‌شوند."
        )
        return

    if is_direct_mode(user_id):
        session_name = get_user_session(user_id)
        if not session_name:
            await message.reply_text("برای حالت مستقیم اول /rubika_connect بزن.")
            return
        task = {
            "type": "text_message",
            "text": text,
            "rubika_session": session_name,
        }
        status = await message.reply_text("در حال قرار دادن در صف ...")
        task["chat_id"] = message.chat.id
        task["status_message_id"] = status.id
        pushed = queue.push_task(task)
        qpos = queue.queue_count_by_session(session_name)
        log_event(
            "task_queued",
            user_id=user_id,
            job_id=pushed.get("job_id"),
            task_type="text_message",
            direct_mode=True,
        )
        await status.edit_text(
            f"در صف قرار گرفت ✅\n"
            f"Job: `{pushed['job_id']}`\n"
            f"جایگاه تقریبی در صف شما: `{qpos}`\n\n"
            f"برای مشاهده جزئیات، «مدیریت صف» را بزن."
        )
        return

    url = extract_first_url(text)

    if not url or not is_direct_url(url):
        return
    await message.reply_text("برای لینک از دکمه/دستور «ارسال لینک» استفاده کن.")

    
@app.on_message(
    filters.private
    & (
        filters.document
        | filters.video
        | filters.audio
        | filters.voice
        | filters.photo
        | filters.animation
        | filters.video_note
        | filters.sticker
    )
)
async def media_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session_name = get_user_session(user_id)
    if not session_name:
        await message.reply_text("ابتدا روبیکا را متصل کن: `/rubika_connect`")
        return

    media_type, media = get_media(message)
    if not media:
        await message.reply_text("فایل قابل پردازش نیست.")
        return

    download_name = build_download_filename(message, media_type, media)
    download_path = DOWNLOAD_DIR / download_name

    status = await message.reply_text(
        "فایل دریافت شد.\n\n"
        "وضعیت: آماده‌سازی برای دانلود از تلگرام..."
    )

    try:
        started_at = time.time()
        progress_state = {"last_update": 0}

        downloaded = await client.download_media(
            message,
            file_name=str(download_path),
            progress=download_progress,
            progress_args=(status, download_name, started_at, progress_state),
        )

        if not downloaded:
            raise RuntimeError("Download failed.")

        downloaded_path = Path(downloaded)
        if not downloaded_path.exists():
            raise RuntimeError("Downloaded file not found.")

        file_size = downloaded_path.stat().st_size
        settings = load_settings()
        batch = get_batch(user_id)

        if batch.get("active"):
            files = batch.get("files", [])
            files.append(str(downloaded_path))
            batch["files"] = files
            set_batch(user_id, batch)
            await status.edit_text(
                f"✅ فایل به جلسه ZIP اضافه شد.\n"
                f"تعداد فایل‌های فعلی: `{len(files)}`\n\n"
                f"فایل‌های بیشتری بفرست یا «پایان فایل ZIP» را بزن."
            )
            return

        task = {
            "type": "local_file",
            "path": str(downloaded_path),
            "caption": message.caption or "",
            "file_name": download_name,
            "file_size": file_size,
            "safe_mode": settings.get("safe_mode", False),
            "zip_password": settings.get("zip_password", ""),
            "rubika_session": session_name,
        }

        await status.edit_text(
            f"File ready: `{download_name}` ({pretty_size(file_size)})\nWaiting for your confirmation."
        )
        await queue_or_confirm(message, task, f"File prepared: `{download_name}`")
        log_event(
            "media_prepared",
            user_id=user_id,
            file_name=download_name,
            file_size=file_size,
            task_type="local_file",
        )

    except Exception as e:
        log_event("media_prepare_failed", user_id=user_id, error=str(e))
        await status.edit_text(f"خطا: {str(e)}")

def clear_old_status():
    try:
        if STATUS_FILE.exists():
            STATUS_FILE.unlink()
    except Exception:
        pass

if __name__ == "__main__":
    clear_old_status()
    app.start()
    app.loop.create_task(status_watcher())
    idle()
    app.stop()
