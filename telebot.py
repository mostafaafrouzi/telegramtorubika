import asyncio
import json
import os
import re
import shutil
import time
import pyzipper
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified
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
from user_entitlements import (
    DISABLE_USAGE_LIMITS,
    add_bonus_month_mb,
    can_enqueue,
    estimate_task_bytes,
    effective_max_file_bytes,
    get_usage_snapshot,
    parallel_job_count,
    set_user_tier,
)

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
BROADCAST_STATE_FILE = QUEUE_DIR / "broadcast_state.json"
PROCESSING_FILE = QUEUE_DIR / "processing.json"
DISABLE_UPDATE_BROADCAST = os.getenv("DISABLE_UPDATE_BROADCAST", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def max_file_bytes() -> Optional[int]:
    """If set, reject queued uploads larger than this (from MAX_FILE_MB in .env). 0 or empty = no limit."""
    raw = (os.getenv("MAX_FILE_MB") or "").strip()
    if not raw or raw == "0":
        return None
    try:
        mb = int(raw)
        if mb <= 0:
            return None
        return mb * 1024 * 1024
    except ValueError:
        return None


def max_file_mb_display() -> str:
    b = max_file_bytes()
    if b is None:
        return "∞"
    return str(b // (1024 * 1024))


def effective_max_mb_display(user_id: int) -> str:
    b = effective_max_file_bytes(user_id)
    if b is None:
        return "∞"
    return f"{b / (1024 * 1024):.0f}"


def fmt_mb_bytes(n: int) -> str:
    return f"{n / (1024 * 1024):.1f}"


def quota_fail_text(user_id: int, code: str, detail: dict) -> str:
    if code == "quota_parallel":
        return tr(
            user_id,
            "quota_parallel_msg",
            cur=detail.get("parallel", 0),
            maxp=detail.get("max_parallel", 0),
        )
    if code == "quota_day":
        return tr(
            user_id,
            "quota_day_msg",
            need=detail.get("need_mb", "?"),
            left=f'{detail.get("remain_day_mb", 0):.1f}',
        )
    if code == "quota_month":
        return tr(
            user_id,
            "quota_month_msg",
            need=detail.get("need_mb", "?"),
            left=f'{detail.get("remain_month_mb", 0):.1f}',
        )
    if code == "quota_file_cap":
        return tr(
            user_id,
            "quota_file_cap_msg",
            max_mb=detail.get("max_mb", 0),
            need_mb=detail.get("need_mb", "?"),
        )
    return tr(user_id, "quota_unknown")


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
        "btn_send_content": "ارسال متن یا لینک",
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
        "btn_inline_faildetail": "جزئیات خطا",
        "queue_kb_refresh": "بروزرسانی شد",
        "queue_kb_cleared": "صف پاک شد",
        "directmode_usage": "استفاده: `/directmode on` یا `/directmode off`",
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
            "- در انتظار در صف SQLite: `{pending}`\n"
            "- هم‌اکنون در حال پردازش (worker): `{processing}`\n"
            "- کل خطاها (global): `{failed}`\n"
            "- حذف‌شده‌ها: `{deleted}`\n"
            "- لغوشده‌ها: `{cancelled}`\n\n"
            "اگر آپلود گیر کرد ولی اینجا `۰` بود، یعنی کار از صف بیرون آمده و worker مشغول است.\n\n"
            "برای پاکسازی صف از دکمهٔ «پاکسازی صف من» استفاده کن."
        ),
        "queue_processing_none": "`—`",
        "queue_processing_detail": "`{job_id}` نوع `{task_type}` — `{file}` (~{size})",
        "help_short": (
            "راهنمای سریع:\n\n"
            "منوی اتصال:\n"
            "- اتصال روبیکا: `/rubika_connect`\n"
            "- وضعیت روبیکا: `/rubika_status`\n\n"
            "منوی فایل‌ها:\n"
            "- شروع فایل ZIP: `/newbatch`\n"
            "- پایان فایل ZIP: `/done`\n"
            "- متن یا لینک به روبیکا: دکمهٔ «ارسال متن یا لینک» یا `/sendtext` / `/sendlink`\n"
            "- پاکسازی صف: `/delall`\n\n"
            "منوی تنظیمات:\n"
            "- حالت مستقیم: `/directmode on|off`\n"
            "- safe mode: `/safemode on|off`\n\n"
            "عیب‌یابی:\n"
            "- وضعیت شبکه: `/netstatus`\n"
            "- پنل ادمین: `/admin`\n"
            "- حذف یک job: `/del <job_id>`\n\n"
            "برای راهنمای تحلیل لاگ: `/loghelp`\n"
            "• مصرف و سهمیه: `/usage` — پلن و خرید: `/plan`"
        ),
        "loghelp_body": (
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
        ),
        "rubika_not_connected": "روبیکا متصل نیست. از `/rubika_connect` استفاده کن.",
        "rubika_checking": "در حال بررسی وضعیت واقعی اتصال روبیکا ...",
        "rubika_ok": (
            "اتصال روبیکا فعال و معتبر است ✅\n"
            "session: `{session}`\n"
            "جزئیات: `{details}`"
        ),
        "rubika_invalid_session": (
            "اتصال ذخیره‌شده معتبر نیست ❌\n"
            "session: `{session}`\n"
            "خطا: `{details}`\n\n"
            "لطفاً دوباره از دکمه «اتصال روبیکا» استفاده کن."
        ),
        "rubika_already_connected": (
            "اکانت روبیکا از قبل متصل است.\n"
            "session: `{session}`\n\n"
            "برای اتصال مجدد، شماره جدید را ارسال کن."
        ),
        "rubika_ask_phone": (
            "شماره روبیکا را با پیش‌شماره کشور ارسال کن.\n"
            "مثال: `98912xxxxxxx`"
        ),
        "rubika_passkey_needed": "این شماره نیاز به PassKey دارد. PassKey روبیکا را ارسال کن.",
        "rubika_code_sent": "کد ارسال شد. کد تایید روبیکا را بفرست.",
        "rubika_send_code_error": "خطا در ارسال کد روبیکا: {error}",
        "rubika_connected_ok": "روبیکا با موفقیت متصل شد ✅",
        "rubika_bad_code": "کد تایید نامعتبر یا خطای ورود: {error}",
        "version_line": "telegramtorubika `{version}`",
        "update_notice": (
            "ربات به‌روز شد ✅\n"
            "نسخه: `{version}`\n"
            "`/menu` منوی اصلی · `/lang` زبان"
        ),
        "prompt_quick_message": (
            "پیام بعدی‌ات را بفرست (متن خالی، فقط لینک، یا متن همراه لینک).\n"
            "بدون تأیید اضافه در صف روبیکا قرار می‌گیرد."
        ),
        "empty_message": "پیام خالی است.",
        "text_queueing": "در حال قرار دادن در صف ...",
        "text_queued": (
            "در صف قرار گرفت ✅\n"
            "Job: `{job_id}`\n"
            "جایگاه تقریبی در صف شما: `{qpos}`\n\n"
            "برای جزئیات «مدیریت صف» را بزن."
        ),
        "sendtext_usage": "فرمت: `/sendtext متن`",
        "sendlink_usage": "فرمت: `/sendlink <url>`",
        "invalid_link": "در این متن لینک http(s) معتبر پیدا نشد.",
        "safemode_usage": "از `/safemode on` یا `/safemode off` استفاده کن.",
        "safemode_on": (
            "Safe Mode فعال شد.\n\n"
            "رمزی که می‌خواهی روی ZIP باشد را بفرست.\n"
            "از این به بعد فایل‌ها قبل از روبیکا با این رمز ZIP می‌شوند."
        ),
        "safemode_off": "Safe Mode غیرفعال شد.\n\nاز این به بعد فایل‌ها به‌صورت عادی ارسال می‌شوند.",
        "safemode_bad": "دستور نامعتبر. `/safemode on` یا `/safemode off`",
        "queue_empty": "صف خالی است.",
        "queue_cleared_all": "تمام موارد در صف پاک شد.",
        "removed_from_queue": "این مورد از صف حذف شد.",
        "done_no_batch": "جلسه فایل ZIP فعالی پیدا نشد یا فایل ندارد.",
        "zip_name_prompt": "نام فایل ZIP را ارسال کن (بدون پسوند).",
        "part_mb_prompt": "سایز هر پارت (MB) را بفرست. مثال: 1900",
        "part_mb_invalid": "عدد معتبر بفرست. مثال: 1900",
        "part_mb_min": "حداقل سایز پارت 50MB است.",
        "zip_no_files": "فایلی برای ساخت ZIP پیدا نشد.",
        "zip_large_warn": (
            "⚠️ حجم فایل ZIP بزرگ است. تلگرام ممکن است ارسال فایل را رد کند؛ "
            "فایل روی سرور آماده است و می‌تواند به روبیکا ارسال شود."
        ),
        "zip_ready_caption": (
            "فایل ZIP آماده شد ✅\n"
            "تعداد فایل‌ها: `{n}`\n"
            "حجم کل ورودی: `{insize}`\n"
            "حجم ZIP: `{zsize}`"
        ),
        "zip_ready_no_doc": (
            "فایل ZIP آماده شد ✅\n"
            "تعداد فایل‌ها: `{n}`\n"
            "حجم کل ورودی: `{insize}`\n"
            "حجم ZIP: `{zsize}`\n"
            "(ارسال فایل در تلگرام ناموفق؛ روی سرور آماده است)"
        ),
        "zip_queue_summary": "ZIP آماده شد: `{name}`\nآیا به روبیکا ارسال شود؟",
        "password_empty": "رمز نمی‌تواند خالی باشد.",
        "password_saved_zip": (
            "رمز ذخیره شد.\n\n"
            "از این به بعد فایل‌ها قبل از روبیکا به‌صورت ZIP رمزدار آماده می‌شوند."
        ),
        "net_status": (
            "وضعیت شبکه: `{mode}`\n"
            "دلیل: `{reason}`\n"
            "آخرین بروزرسانی: `{updated}`"
        ),
        "admin_panel": (
            "پنل ادمین:\n\n"
            "Queue total: `{qt}`\n"
            "Cancelled jobs: `{cancelled}`\n"
            "Deleted jobs: `{deleted}`\n"
            "Failed jobs: `{failed}`\n"
            "Network mode: `{net_mode}`\n"
            "Reason: `{net_reason}`"
        ),
        "eta_unknown": "نامشخص",
        "download_progress_line": (
            "📥 در حال دریافت از تلگرام\n\n"
            "فایل: `{file_name}`\n"
            "حجم: `{total}`\n"
            "پیشرفت: `{percent:.1f}%`\n"
            "`{bar}`\n"
            "سرعت: `{speed}/s`\n"
            "زمان باقی‌مانده: `{eta}`"
        ),
        "media_need_rubika": "ابتدا روبیکا را متصل کن: `/rubika_connect`",
        "media_bad_type": "فایل قابل پردازش نیست.",
        "media_download_status": "فایل دریافت شد.\n\nوضعیت: آماده‌سازی برای دانلود از تلگرام...",
        "media_zip_added": (
            "✅ فایل به جلسه ZIP اضافه شد.\n"
            "تعداد فایل‌های فعلی: `{n}`\n"
            "حجم خام تقریبی: ~`{raw_mb}` مگابایت\n\n"
            "فایل بیشتر بفرست یا «پایان فایل ZIP» را بزن."
        ),
        "media_file_ready": (
            "فایل آماده است: `{name}` ({size})\n"
            "در انتظار تأیید ارسال به روبیکا..."
        ),
        "media_error": "خطا: {error}",
        "file_prepared_summary": "فایل آماده شد: `{name}`",
        "queued_processing": "Queued for processing...",
        "confirm_send_suffix": "به روبیکا همین حالا ارسال شود؟",
        "failed_detail_title": "آخرین خطاهای ثبت‌شده برای نشست شما:",
        "confirm_cancelled": "ارسال لغو شد.",
        "cleanup_done": "پاکسازی `downloads/`: {n} فایل، حدود {mb} MB آزاد شد.",
        "direct_need_rubika": "برای حالت مستقیم اول `/rubika_connect` بزن.",
        "file_too_large": "فایل از سقف مجاز بزرگ‌تر است (حداکثر ~`{max_mb}` مگابایت با توجه به پلن و `MAX_FILE_MB`). حجم این فایل: ~`{size_mb}` مگابایت.",
        "admin_max_file": "`MAX_FILE_MB` (سقف آپلود env): `{mb}` (`0` یا خالی = بدون سقف env)",
        "admin_plan_note": "سهمیه پلن‌ها در SQLite (`user_entitlements`) — `/usage` برای کاربران.",
        "quota_parallel_msg": "سقف کارهای همزمان در صف پر است (`{cur}` / `{maxp}`). بعد از اتمام یکی دوباره تلاش کن.",
        "quota_day_msg": "سقف حجم روزانه پر است. این کار ~{need} MB است؛ حدود `{left}` MB امروز باقی مانده.",
        "quota_month_msg": "سقف حجم ماهانه پر است. این کار ~{need} MB است؛ حدود `{left}` MB این ماه باقی مانده.",
        "quota_file_cap_msg": "حجم این کار از سقف هر فایل بیشتر است (حداکثر `{max_mb}` MB، این فایل ~{need_mb} MB).",
        "quota_unknown": "سقف مجاز پر است. `/usage` را بزن یا با ادمین تماس بگیر.",
        "usage_panel": (
            "مصرف و محدودیت:\n"
            "• پلن: `{tier}`\n"
            "• امروز: ~{day_used} / {day_cap} MB\n"
            "• این ماه: ~{month_used} / {month_cap} MB\n"
            "• حداکثر هر فایل: `{max_file}` MB\n"
            "• همزمان در صف/پردازش: `{parallel}` / `{max_parallel}`\n\n"
            "موفقیت ارسال به روبیکا به مصرف اضافه می‌شود."
        ),
        "usage_disabled_hint": "سهمیه‌گذاری با `DISABLE_USAGE_LIMITS` خاموش است (فقط محدودیت env در صورت تنظیم).",
        "batch_raw_hint": "جمع حجم خام فعلی: ~`{raw_mb}` MB ({n} فایل). بعد از ZIP ممکن است کمی فرق کند.",
        "direct_url_use_sendlink": "برای لینک از دکمه یا دستور `/sendlink` استفاده کن.",
        "purchase_info_body": (
            "💳 خرید / ارتقای پلن\n\n"
            "درگاه پرداخت خودکار هنوز وصل نیست. فعلاً:\n"
            "• از ادمین بخواه پلن را با `/admin_tier` یا `/admin_bonus` برایت تنظیم کند؛ یا\n"
            "• اسکریپت `tools/grant_plan.py` روی سرور؛ یا\n"
            "• `tools/payment_webhook_stub.py` با کلید `PAYMENT_WEBHOOK_SECRET`.\n\n"
            "بعد از پرداخت واقعی، درگاه را به همین webhook وصل کن."
        ),
        "rubika_update_hint": (
            "اگر بعد از به‌روزرسانی سرور روبیکا «قطع» شد: یک‌بار `/rubika_connect` بزن. "
            "فایل‌های session از rsync پاک نمی‌شوند؛ خطای 502 از سرورهای روبیکا هم رایج است."
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
        "btn_send_content": "Send text or link",
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
        "btn_inline_faildetail": "Error details",
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
            "- Pending in SQLite (your session): `{pending}`\n"
            "- Currently processing (worker): `{processing}`\n"
            "- Failed (global): `{failed}`\n"
            "- Deleted: `{deleted}`\n"
            "- Cancelled: `{cancelled}`\n\n"
            "If upload looks stuck but Pending is `0`, the job left the queue and the worker is busy.\n\n"
            "Use «Clear my queue» to wipe your pending tasks."
        ),
        "queue_processing_none": "`—`",
        "queue_processing_detail": "`{job_id}` type `{task_type}` — `{file}` (~{size})",
        "help_short": (
            "Quick help:\n\n"
            "Connection:\n"
            "- Connect Rubika: `/rubika_connect`\n"
            "- Rubika status: `/rubika_status`\n\n"
            "Files:\n"
            "- Start ZIP batch: `/newbatch`\n"
            "- Finish ZIP: `/done`\n"
            "- Text/link to Rubika: «Send text or link» or `/sendtext` / `/sendlink`\n"
            "- Clear queue: `/delall`\n\n"
            "Settings:\n"
            "- Direct mode: `/directmode on|off`\n"
            "- Safe mode: `/safemode on|off`\n\n"
            "Troubleshooting:\n"
            "- Network: `/netstatus`\n"
            "- Admin: `/admin`\n"
            "- Remove one job: `/del <job_id>`\n\n"
            "Log analysis: `/loghelp`\n"
            "Usage & limits: `/usage` — plan / purchase info: `/plan`"
        ),
        "loghelp_body": (
            "Job log analysis:\n\n"
            "1) Copy `job_id` from the Queued message.\n"
            "2) In bot logs, find `task_queued` with that `job_id`.\n"
            "3) In worker logs you should see:\n"
            "   `task_started` -> (`task_done` or `task_failed`).\n"
            "4) If you see `task_requeued`, network/access failed and a new job was created.\n"
            "5) For Rubika login, check `rubika_connect_ok` / `rubika_connect_failed`.\n\n"
            "Log paths:\n"
            "- `/opt/tele2rub/queue/bot_events.jsonl`\n"
            "- `/opt/tele2rub/queue/worker_events.jsonl`\n"
            "- `/tmp/tele2rub-installer.jsonl`"
        ),
        "rubika_not_connected": "Rubika is not linked. Use `/rubika_connect`.",
        "rubika_checking": "Checking live Rubika session...",
        "rubika_ok": (
            "Rubika session is valid ✅\n"
            "session: `{session}`\n"
            "details: `{details}`"
        ),
        "rubika_invalid_session": (
            "Saved session is not valid ❌\n"
            "session: `{session}`\n"
            "error: `{details}`\n\n"
            "Use «Connect Rubika» again."
        ),
        "rubika_already_connected": (
            "Rubika is already linked.\n"
            "session: `{session}`\n\n"
            "To reconnect, send a new phone number."
        ),
        "rubika_ask_phone": (
            "Send your Rubika phone with country code.\n"
            "Example: `98912xxxxxxx`"
        ),
        "rubika_passkey_needed": "This number needs a PassKey. Send your Rubika PassKey.",
        "rubika_code_sent": "Code sent. Send the Rubika verification code.",
        "rubika_send_code_error": "Error sending Rubika code: {error}",
        "rubika_connected_ok": "Rubika linked successfully ✅",
        "rubika_bad_code": "Invalid code or sign-in error: {error}",
        "version_line": "telegramtorubika `{version}`",
        "update_notice": (
            "Bot updated ✅\n"
            "Version: `{version}`\n"
            "`/menu` main menu · `/lang` language"
        ),
        "prompt_quick_message": (
            "Send your next message (plain text, a link, or both).\n"
            "It is queued for Rubika without an extra confirmation step."
        ),
        "empty_message": "Message is empty.",
        "text_queueing": "Queueing...",
        "text_queued": (
            "Queued ✅\n"
            "Job: `{job_id}`\n"
            "Approx. position in your queue: `{qpos}`\n\n"
            "Use «Queue» for details."
        ),
        "sendtext_usage": "Format: `/sendtext ...`",
        "sendlink_usage": "Format: `/sendlink <url>`",
        "invalid_link": "No valid http(s) link found in that text.",
        "safemode_usage": "Use `/safemode on` or `/safemode off`.",
        "safemode_on": (
            "Safe Mode enabled.\n\n"
            "Send the password you want on ZIP files.\n"
            "Files will be ZIP-encrypted before Rubika."
        ),
        "safemode_off": "Safe Mode disabled.\n\nFiles will upload normally.",
        "safemode_bad": "Invalid command. Use `/safemode on` or `/safemode off`.",
        "queue_empty": "Your queue is empty.",
        "queue_cleared_all": "All your queued tasks were removed.",
        "removed_from_queue": "Removed from queue.",
        "done_no_batch": "No active ZIP batch or no files collected.",
        "zip_name_prompt": "Send the ZIP base name (no extension).",
        "part_mb_prompt": "Part size in MB, e.g. `1900`",
        "part_mb_invalid": "Send a valid number, e.g. `1900`",
        "part_mb_min": "Minimum part size is 50 MB.",
        "zip_no_files": "No files left to build the ZIP.",
        "zip_large_warn": (
            "⚠️ ZIP is large; Telegram may refuse sending the file. "
            "It is still on the server and can go to Rubika."
        ),
        "zip_ready_caption": (
            "ZIP ready ✅\n"
            "Files: `{n}`\n"
            "Input size: `{insize}`\n"
            "ZIP size: `{zsize}`"
        ),
        "zip_ready_no_doc": (
            "ZIP ready ✅\n"
            "Files: `{n}`\n"
            "Input size: `{insize}`\n"
            "ZIP size: `{zsize}`\n"
            "(Telegram upload failed; file is on the server)"
        ),
        "zip_queue_summary": "ZIP ready: `{name}`\nSend to Rubika?",
        "password_empty": "Password cannot be empty.",
        "password_saved_zip": (
            "Password saved.\n\n"
            "Files will be prepared as passworded ZIP before Rubika."
        ),
        "net_status": (
            "Network: `{mode}`\n"
            "Reason: `{reason}`\n"
            "Updated: `{updated}`"
        ),
        "admin_panel": (
            "Admin panel:\n\n"
            "Queue total: `{qt}`\n"
            "Cancelled jobs: `{cancelled}`\n"
            "Deleted jobs: `{deleted}`\n"
            "Failed jobs: `{failed}`\n"
            "Network mode: `{net_mode}`\n"
            "Reason: `{net_reason}`"
        ),
        "eta_unknown": "unknown",
        "download_progress_line": (
            "📥 Downloading from Telegram\n\n"
            "File: `{file_name}`\n"
            "Size: `{total}`\n"
            "Progress: `{percent:.1f}%`\n"
            "`{bar}`\n"
            "Speed: `{speed}/s`\n"
            "ETA: `{eta}`"
        ),
        "media_need_rubika": "Link Rubika first: `/rubika_connect`",
        "media_bad_type": "Unsupported media type.",
        "media_download_status": "Received.\n\nPreparing download from Telegram...",
        "media_zip_added": (
            "✅ Added to ZIP batch.\n"
            "Files in batch: `{n}`\n"
            "Approx. raw total: ~`{raw_mb}` MB\n\n"
            "Send more or tap «End ZIP»."
        ),
        "media_file_ready": (
            "File ready: `{name}` ({size})\n"
            "Waiting for confirmation to send to Rubika..."
        ),
        "media_error": "Error: {error}",
        "file_prepared_summary": "File prepared: `{name}`",
        "queued_processing": "Queued for processing...",
        "confirm_send_suffix": "Send to Rubika now?",
        "failed_detail_title": "Recent failures for your Rubika session:",
        "confirm_cancelled": "Send cancelled.",
        "cleanup_done": "Cleaned `downloads/`: {n} files, ~{mb} MB freed.",
        "direct_need_rubika": "Link Rubika first: `/rubika_connect`",
        "file_too_large": "File exceeds the limit (max ~`{max_mb}` MB from plan + `MAX_FILE_MB`). This file is ~`{size_mb}` MB.",
        "admin_max_file": "`MAX_FILE_MB` (env cap): `{mb}` (`0` or empty = no env cap)",
        "admin_plan_note": "Per-user plans live in SQLite (`user_entitlements`). Users: `/usage`.",
        "quota_parallel_msg": "Too many jobs at once for your plan (`{cur}` / `{maxp}`). Wait for one to finish.",
        "quota_day_msg": "Daily data limit reached. This job ~{need} MB; ~{left} MB left today.",
        "quota_month_msg": "Monthly data limit reached. This job ~{need} MB; ~{left} MB left this month.",
        "quota_file_cap_msg": "This file exceeds the per-file cap (`{max_mb}` MB max; yours ~{need_mb} MB).",
        "quota_unknown": "Quota blocked. Try `/usage` or contact admin.",
        "usage_panel": (
            "Usage & limits:\n"
            "• Tier: `{tier}`\n"
            "• Today: ~{day_used} / {day_cap} MB\n"
            "• This month: ~{month_used} / {month_cap} MB\n"
            "• Max per file: `{max_file}` MB\n"
            "• Parallel jobs: `{parallel}` / `{max_parallel}`\n\n"
            "Usage increments when Rubika upload succeeds."
        ),
        "usage_disabled_hint": "Quotas are off (`DISABLE_USAGE_LIMITS`). Only optional env caps apply.",
        "batch_raw_hint": "Current raw total ~`{raw_mb}` MB ({n} files). ZIP size may differ slightly.",
        "direct_url_use_sendlink": "For links use the button or `/sendlink`.",
        "purchase_info_body": (
            "💳 Plans / purchase\n\n"
            "Automatic checkout is not wired yet. For now:\n"
            "• Ask an admin to run `/admin_tier` or `/admin_bonus`; or\n"
            "• Use `tools/grant_plan.py` on the server; or\n"
            "• `tools/payment_webhook_stub.py` + `PAYMENT_WEBHOOK_SECRET`.\n\n"
            "Connect your real PSP to that webhook when ready."
        ),
        "rubika_update_hint": (
            "If Rubika breaks after a server update: run `/rubika_connect` once. "
            "Session files are excluded from rsync; 502s from Rubika edges are common."
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


def dir_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def admin_disk_report_text() -> str:
    du = shutil.disk_usage(BASE_DIR)
    dl = dir_bytes(DOWNLOAD_DIR)
    qz = dir_bytes(QUEUE_DIR)
    return (
        f"💾 Storage\n"
        f"- Free / total: `{pretty_size(float(du.free))}` / `{pretty_size(float(du.total))}`\n"
        f"- `{DOWNLOAD_DIR.name}/`: `{pretty_size(float(dl))}`\n"
        f"- `{QUEUE_DIR.name}/`: `{pretty_size(float(qz))}`"
    )


def recent_failed_detail_text(session: Optional[str], limit: int = 8) -> str:
    if not session or not FAILED_FILE.exists():
        return "—"
    rows = []
    try:
        with open(FAILED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                task = row.get("task") or {}
                if task.get("rubika_session") != session:
                    continue
                jid = task.get("job_id", "?")
                fn = task.get("file_name") or ""
                if not fn and task.get("path"):
                    fn = Path(str(task.get("path"))).name
                if not fn:
                    fn = task.get("type", "?")
                err = (row.get("error") or "")[:900]
                rows.append(f"`{jid}` `{fn}`\n`{err}`")
                if len(rows) >= limit:
                    break
    except Exception:
        return "—"
    return "\n\n".join(rows) if rows else "—"


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
            [KeyboardButton(tr(user_id, "btn_send_content"))],
            [
                KeyboardButton("/plan"),
                KeyboardButton("/usage"),
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


async def gate_quota(message: Message, user_id: int, task: dict) -> bool:
    """Return True if the user may enqueue this task."""
    task["telegram_user_id"] = user_id
    est = estimate_task_bytes(task)
    ok, code, det = can_enqueue(user_id, est, queue)
    if ok:
        return True
    await message.reply_text(quota_fail_text(user_id, code, det), parse_mode=None)
    log_event("quota_blocked", user_id=user_id, code=code)
    return False


def usage_report_text(user_id: int) -> str:
    if DISABLE_USAGE_LIMITS:
        return tr(user_id, "usage_disabled_hint")
    u = get_usage_snapshot(user_id)
    day_u = u["day_bytes"] / (1024 * 1024)
    month_u = u["month_bytes"] / (1024 * 1024)
    cur_par = parallel_job_count(user_id, queue)
    return tr(
        user_id,
        "usage_panel",
        tier=u["tier"],
        day_used=f"{day_u:.1f}",
        day_cap=u["quota_day_mb"],
        month_used=f"{month_u:.1f}",
        month_cap=u["quota_month_mb"],
        max_file=u["max_file_mb"],
        parallel=cur_par,
        max_parallel=u["max_parallel"],
    )


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


def processing_display_for_queue(user_id: int) -> str:
    """Current worker job for this user's Rubika session (reads queue/processing.json)."""
    if not PROCESSING_FILE.exists():
        return tr(user_id, "queue_processing_none")
    try:
        data = json.loads(PROCESSING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return tr(user_id, "queue_processing_none")
    session = get_user_session(user_id)
    if not session or data.get("rubika_session") != session:
        return tr(user_id, "queue_processing_none")
    jid = str(data.get("job_id", "?"))
    typ = str(data.get("type", "?"))
    fn = ""
    if data.get("file_name"):
        fn = str(data["file_name"])
    elif data.get("path"):
        fn = Path(str(data["path"])).name
    sz = data.get("file_size")
    sz_txt = pretty_size(sz) if sz else "?"
    return tr(
        user_id,
        "queue_processing_detail",
        job_id=jid,
        task_type=typ,
        file=fn or "—",
        size=sz_txt,
    )


def eta_text(seconds, user_id: int = 0) -> str:
    if not seconds or seconds <= 0:
        return tr(user_id, "eta_unknown") if user_id else "نامشخص"

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
    uid = int(state.get("user_id") or 0)

    text = tr(
        uid,
        "download_progress_line",
        file_name=file_name,
        total=pretty_size(total),
        percent=percent,
        bar=progress_bar(percent),
        speed=pretty_size(speed),
        eta=eta_text(eta, uid),
    )

    try:
        await status_message.edit_text(text, parse_mode=None)
    except MessageNotModified:
        pass
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
                    await app.edit_message_text(chat_id, msg_id, text, parse_mode=None)
                except MessageNotModified:
                    pass
                except Exception:
                    pass
        except Exception:
            pass


async def maybe_broadcast_update():
    """Notify known private chats once per APP_VERSION (disable with DISABLE_UPDATE_BROADCAST=1)."""
    await asyncio.sleep(2)
    if DISABLE_UPDATE_BROADCAST:
        return
    state = load_json(BROADCAST_STATE_FILE, {})
    if state.get("last_broadcast_version") == APP_VERSION:
        return
    data = load_json(KNOWN_CHATS_FILE, {"ids": []})
    ids = list(dict.fromkeys(data.get("ids", [])))
    for cid in ids:
        try:
            uid = int(cid)
            await app.send_message(
                uid,
                tr(uid, "update_notice", version=APP_VERSION),
                reply_markup=build_main_menu(uid),
            )
        except Exception:
            log_event("update_broadcast_skip", chat_id=cid)
        await asyncio.sleep(0.06)
    state["last_broadcast_version"] = APP_VERSION
    save_json(BROADCAST_STATE_FILE, state)
    log_event("update_broadcast_done", version=APP_VERSION, chats=len(ids))


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
    uid = message.from_user.id
    await message.reply_text(tr(uid, "help_short"))


@app.on_message(filters.private & filters.command("loghelp"))
async def log_help_handler(client: Client, message: Message):
    uid = message.from_user.id
    await message.reply_text(tr(uid, "loghelp_body"))


@app.on_message(filters.private & filters.command("version"))
async def version_handler(client: Client, message: Message):
    uid = message.from_user.id
    await message.reply_text(tr(uid, "version_line", version=APP_VERSION))


@app.on_message(filters.private & filters.command("rubika_status"))
async def rubika_status_handler(client: Client, message: Message):
    uid = message.from_user.id
    session_name = get_user_session(uid)
    if not session_name:
        await message.reply_text(tr(uid, "rubika_not_connected"))
        return
    await message.reply_text(tr(uid, "rubika_checking"))
    ok_session, details = await asyncio.to_thread(check_rubika_session_sync, session_name)
    if ok_session:
        await message.reply_text(tr(uid, "rubika_ok", session=session_name, details=details))
    else:
        await message.reply_text(
            tr(uid, "rubika_invalid_session", session=session_name, details=details)
        )


@app.on_message(filters.private & filters.command("rubika_connect"))
async def rubika_connect_handler(client: Client, message: Message):
    user_id = message.from_user.id
    current_session = get_user_session(user_id)
    if current_session:
        await message.reply_text(
            tr(user_id, "rubika_already_connected", session=current_session)
        )
    set_state(user_id, {"step": "await_phone"})
    log_event("rubika_connect_started", user_id=user_id)
    await message.reply_text(tr(user_id, "rubika_ask_phone"))


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
    uid = message.from_user.id
    data = load_json(NETWORK_FILE, {"mode": "unknown", "reason": "", "updated_at": 0})
    mode = data.get("mode", "unknown")
    reason = data.get("reason", "") or "---"
    updated = data.get("updated_at", 0)
    await message.reply_text(
        tr(uid, "net_status", mode=mode, reason=reason, updated=updated),
        parse_mode=None,
    )


def failed_count() -> int:
    if not FAILED_FILE.exists():
        return 0
    try:
        with open(FAILED_FILE, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


async def enqueue_rubika_text_message(message: Message, text_body: str) -> None:
    user_id = message.from_user.id
    session_name = get_user_session(user_id)
    if not session_name:
        await message.reply_text(tr(user_id, "rubika_not_connected"))
        return
    text_body = (text_body or "").strip()
    if not text_body:
        await message.reply_text(tr(user_id, "empty_message"))
        return
    task = {
        "type": "text_message",
        "text": text_body,
        "rubika_session": session_name,
    }
    if not await gate_quota(message, user_id, task):
        return
    status = await message.reply_text(tr(user_id, "text_queueing"))
    task["chat_id"] = message.chat.id
    task["status_message_id"] = status.id
    pushed = queue.push_task(task)
    qpos = queue.queue_count_by_session(session_name)
    log_event(
        "task_queued",
        user_id=user_id,
        job_id=pushed.get("job_id"),
        task_type="text_message",
        direct_mode=is_direct_mode(user_id),
    )
    try:
        await status.edit_text(
            tr(user_id, "text_queued", job_id=pushed["job_id"], qpos=qpos),
            parse_mode=None,
        )
    except MessageNotModified:
        pass


async def queue_or_confirm(
    message: Message,
    task: dict,
    summary: str,
    status_message: Optional[Message] = None,
):
    user_id = message.from_user.id
    task["telegram_user_id"] = user_id
    if is_direct_mode(user_id):
        if not await gate_quota(message, user_id, task):
            return
        anchor = status_message
        if anchor:
            task["chat_id"] = message.chat.id
            task["status_message_id"] = anchor.id
            try:
                await anchor.edit_text(tr(user_id, "text_queueing"), parse_mode=None)
            except Exception:
                pass
            pushed = queue.push_task(task)
            qpos = queue.queue_count_by_session(task.get("rubika_session") or "")
            log_event(
                "task_queued",
                user_id=user_id,
                job_id=pushed.get("job_id"),
                task_type=task.get("type"),
                direct_mode=True,
            )
            try:
                await anchor.edit_text(
                    tr(user_id, "text_queued", job_id=pushed["job_id"], qpos=qpos),
                    parse_mode=None,
                )
            except MessageNotModified:
                pass
            return

        status = await message.reply_text(tr(user_id, "queued_processing"))
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
        try:
            await status.edit_text(
                tr(user_id, "text_queued", job_id=pushed["job_id"], qpos=qpos),
                parse_mode=None,
            )
        except MessageNotModified:
            pass
        return

    set_state(
        user_id,
        {
            "step": "await_send_confirm",
            "pending_task": task,
            "pending_summary": summary,
            "confirm_target_msg_id": status_message.id if status_message else None,
        },
    )
    suffix = tr(user_id, "confirm_send_suffix")
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Send", callback_data="confirm_send")],
            [InlineKeyboardButton("Cancel", callback_data="cancel_send")],
        ]
    )
    body = f"{summary}\n\n{suffix}"
    if status_message:
        try:
            await status_message.edit_text(body, reply_markup=kb, parse_mode=None)
        except Exception:
            await message.reply_text(body, reply_markup=kb)
    else:
        await message.reply_text(body, reply_markup=kb)
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
        tr(
            uid,
            "admin_panel",
            qt=queue.queue_count(),
            cancelled=queue.cancelled_count(),
            deleted=queue.deleted_count(),
            failed=failed_count(),
            net_mode=net.get("mode", "unknown"),
            net_reason=net.get("reason", "") or "---",
        )
        + "\n"
        + tr(uid, "admin_max_file", mb=max_file_mb_display())
        + "\n"
        + tr(uid, "admin_plan_note")
        + "\n\n"
        + tr(uid, "rubika_update_hint")
        + "\n\n"
        + admin_disk_report_text(),
        reply_markup=build_admin_menu(uid),
        parse_mode=None,
    )


@app.on_message(filters.private & filters.command("usage"))
async def usage_handler(client: Client, message: Message):
    await message.reply_text(usage_report_text(message.from_user.id), parse_mode=None)


@app.on_message(filters.private & filters.command("plan"))
async def plan_handler(client: Client, message: Message):
    uid = message.from_user.id
    body = usage_report_text(uid) + "\n\n" + tr(uid, "purchase_info_body")
    await message.reply_text(body, parse_mode=None)


@app.on_message(filters.private & filters.command("admin_tier"))
async def admin_tier_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        await message.reply_text(tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.reply_text(
            "Usage: `/admin_tier <telegram_user_id> <guest|free|pro> [days_valid_for_pro]`",
            parse_mode=None,
        )
        return
    try:
        target = int(parts[1].strip())
    except ValueError:
        await message.reply_text("Invalid user id.", parse_mode=None)
        return
    tier = parts[2].strip().lower()
    exp = 0
    if len(parts) >= 4:
        try:
            days = int(parts[3].strip())
            if tier == "pro" and days > 0:
                exp = int(time.time()) + days * 86400
        except ValueError:
            pass
    set_user_tier(target, tier, exp)
    await message.reply_text(
        f"OK: user `{target}` tier=`{tier}` expires_at=`{exp}`",
        parse_mode=None,
    )


@app.on_message(filters.private & filters.command("admin_bonus"))
async def admin_bonus_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        await message.reply_text(tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.reply_text(
            "Usage: `/admin_bonus <telegram_user_id> <extra_month_mb>`",
            parse_mode=None,
        )
        return
    try:
        target = int(parts[1].strip())
        mb = int(parts[2].strip())
    except ValueError:
        await message.reply_text("Invalid numbers.", parse_mode=None)
        return
    add_bonus_month_mb(target, mb)
    await message.reply_text(f"OK: +{mb} MB monthly bonus for user `{target}`", parse_mode=None)


@app.on_message(filters.private & filters.command("cleanup_downloads"))
async def cleanup_downloads_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        await message.reply_text(tr(uid, "admin_denied"))
        return
    n = 0
    freed = 0
    for p in DOWNLOAD_DIR.glob("*"):
        try:
            if p.is_file():
                freed += p.stat().st_size
                p.unlink()
                n += 1
        except OSError:
            pass
    log_event("admin_cleanup_downloads", user_id=uid, files=n, bytes_freed=freed)
    await message.reply_text(
        tr(uid, "cleanup_done", n=n, mb=f"{freed / (1024 * 1024):.2f}"),
        parse_mode=None,
    )

@app.on_message(filters.private & filters.command("safemode"))
async def safemode_handler(client: Client, message: Message):
    global waiting_for_zip_password

    args = message.text.split(maxsplit=1)

    uid = message.from_user.id
    if len(args) < 2:
        await message.reply_text(tr(uid, "safemode_usage"))
        return

    action = args[1].strip().lower()
    settings = load_settings()

    if action == "on":
        settings["safe_mode"] = True
        save_settings(settings)
        waiting_for_zip_password = True

        await message.reply_text(tr(uid, "safemode_on"))
        return

    if action == "off":
        settings["safe_mode"] = False
        settings["zip_password"] = ""
        save_settings(settings)
        waiting_for_zip_password = False

        await message.reply_text(tr(uid, "safemode_off"))
        return

    await message.reply_text(tr(uid, "safemode_bad"))


@app.on_message(filters.private & filters.command("delall"))
async def clear_queue_handler(client: Client, message: Message, acting_user_id: Optional[int] = None):
    uid = acting_user_id if acting_user_id is not None else message.from_user.id
    user_session = get_user_session(uid)
    tasks = [t for t in queue.all_tasks() if t.get("rubika_session") == user_session]

    tr_uid = uid
    if not tasks:
        await message.reply_text(tr(tr_uid, "queue_empty"))
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
                text=tr(task.get("chat_id") or tr_uid, "removed_from_queue"),
                parse_mode=None,
            )
        except MessageNotModified:
            pass
        except Exception:
            pass

    queue.remove_tasks_by_session(user_session)
    await message.reply_text(tr(tr_uid, "queue_cleared_all"))

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
    uid = message.from_user.id
    if not batch.get("active") or not files:
        await message.reply_text(tr(uid, "done_no_batch"))
        return
    wizard = await message.reply_text(tr(uid, "zip_name_prompt"))
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
        if action == "faildetail":
            await callback_query.answer()
            sess = get_user_session(user_id)
            body = recent_failed_detail_text(sess, limit=8)
            title = tr(user_id, "failed_detail_title")
            await callback_query.message.reply_text(
                f"{title}\n\n{body}",
                parse_mode=None,
            )
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
        if not await gate_quota(callback_query.message, user_id, task):
            await callback_query.answer("Quota", show_alert=True)
            return
        anchor = callback_query.message
        task["chat_id"] = anchor.chat.id
        task["status_message_id"] = anchor.id
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
        try:
            await anchor.edit_text(
                tr(user_id, "text_queued", job_id=task["job_id"], qpos=qpos),
                reply_markup=None,
                parse_mode=None,
            )
        except MessageNotModified:
            pass
        await callback_query.answer("Queued")
        return

    if data == "cancel_send" and state.get("step") == "await_send_confirm":
        clear_state(user_id)
        log_event("task_confirm_cancelled", user_id=user_id)
        try:
            await callback_query.message.edit_text(
                tr(user_id, "confirm_cancelled"),
                reply_markup=None,
                parse_mode=None,
            )
        except Exception:
            await callback_query.message.reply_text(tr(user_id, "confirm_cancelled"))
        await callback_query.answer("Canceled")
        return

    await callback_query.answer("این گزینه منقضی شده یا معتبر نیست.", show_alert=True)


@app.on_message(filters.private & filters.command("sendtext"))
async def send_text_handler(client: Client, message: Message):
    uid = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(tr(uid, "sendtext_usage"))
        return
    await enqueue_rubika_text_message(message, parts[1])


@app.on_message(filters.private & filters.command("sendlink"))
async def send_link_handler(client: Client, message: Message):
    uid = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(tr(uid, "sendlink_usage"))
        return
    url = extract_first_url(parts[1])
    if not url:
        await message.reply_text(tr(uid, "invalid_link"))
        return
    await enqueue_rubika_text_message(message, url)


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
    proc = processing_display_for_queue(user_id)
    summary = tr(
        user_id,
        "queue_panel",
        pending=pending,
        processing=proc,
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
            [InlineKeyboardButton(tr(user_id, "btn_inline_faildetail"), callback_data="queue:faildetail")],
            [InlineKeyboardButton(tr(user_id, "btn_inline_clear"), callback_data="queue:clearall")],
        ]
    )
    if edit_existing:
        try:
            await message.edit_text(summary, reply_markup=kb, parse_mode=None)
            return
        except MessageNotModified:
            return
        except Exception:
            pass
    await message.reply_text(summary, reply_markup=kb, parse_mode=None)


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


@app.on_message(filters.private & filters.text & ~filters.command(["start", "menu", "lang", "help", "loghelp", "version", "rubika_status", "rubika_connect", "directmode", "netstatus", "admin", "safemode", "del", "delall", "newbatch", "done", "sendtext", "sendlink", "queue", "usage", "plan", "admin_tier", "admin_bonus"]))
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
        "send text or link": "/quick_send_prompt",
        "ارسال متن یا لینک": "/quick_send_prompt",
        "send text": "/quick_send_prompt",
        "ارسال متن": "/quick_send_prompt",
        "send link": "/quick_send_prompt",
        "ارسال لینک": "/quick_send_prompt",
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
    if mapped == "/quick_send_prompt":
        set_state(user_id, {"step": "await_quick_message"})
        await message.reply_text(tr(user_id, "prompt_quick_message"))
        return

    if state.get("step") == "await_quick_message":
        clear_state(user_id)
        await enqueue_rubika_text_message(message, text)
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
                await message.reply_text(tr(user_id, "rubika_passkey_needed"))
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
            await message.reply_text(tr(user_id, "rubika_code_sent"))
        except Exception as e:
            clear_state(user_id)
            await message.reply_text(tr(user_id, "rubika_send_code_error", error=str(e)))
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
            await message.reply_text(tr(user_id, "rubika_code_sent"))
        except Exception as e:
            clear_state(user_id)
            await message.reply_text(tr(user_id, "rubika_send_code_error", error=str(e)))
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
            await message.reply_text(tr(user_id, "rubika_connected_ok"))
            log_event("rubika_connect_ok", user_id=user_id, session=session_name)
        except Exception as e:
            clear_state(user_id)
            log_event("rubika_connect_failed", user_id=user_id, error=str(e))
            await message.reply_text(tr(user_id, "rubika_bad_code", error=str(e)))
        return

    if state.get("step") == "await_zip_name":
        zip_name = safe_filename(text.strip() or "bundle")
        await safe_delete_user_message(message)
        bf = state.get("batch_files", [])
        fps = [Path(p) for p in bf if Path(p).exists()]
        raw_sum = sum(p.stat().st_size for p in fps)
        prompt_body = (
            tr(user_id, "part_mb_prompt")
            + "\n\n"
            + tr(user_id, "batch_raw_hint", raw_mb=fmt_mb_bytes(raw_sum), n=len(fps))
        )
        await edit_wizard(
            state.get("wizard_chat_id", message.chat.id),
            int(state.get("wizard_message_id", 0) or 0),
            prompt_body,
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
            await message.reply_text(tr(user_id, "part_mb_invalid"))
            return
        if part_mb < 50:
            await message.reply_text(tr(user_id, "part_mb_min"))
            return
        await safe_delete_user_message(message)
        files = state.get("batch_files", [])
        session_name = get_user_session(user_id)
        file_paths = [Path(p) for p in files if Path(p).exists()]
        if not file_paths:
            await message.reply_text(tr(user_id, "zip_no_files"))
            clear_state(user_id)
            clear_batch(user_id)
            return
        settings = load_settings()
        zip_password = settings.get("zip_password", "") if settings.get("safe_mode", False) else ""
        zip_path = make_bundle_zip_local(file_paths, state.get("zip_name", "bundle"), zip_password)
        total_size = sum(p.stat().st_size for p in file_paths if p.exists())
        zip_sz = zip_path.stat().st_size
        lim_b = effective_max_file_bytes(user_id)
        if lim_b is not None and zip_sz > lim_b:
            try:
                zip_path.unlink()
            except Exception:
                pass
            await message.reply_text(
                tr(
                    user_id,
                    "file_too_large",
                    max_mb=effective_max_mb_display(user_id),
                    size_mb=fmt_mb_bytes(zip_sz),
                ),
                parse_mode=None,
            )
            clear_state(user_id)
            clear_batch(user_id)
            return
        qt = {"type": "local_file", "file_size": zip_sz, "rubika_session": session_name}
        if not await gate_quota(message, user_id, qt):
            try:
                zip_path.unlink()
            except Exception:
                pass
            clear_state(user_id)
            clear_batch(user_id)
            return
        if zip_sz > 45 * 1024 * 1024:
            await message.reply_text(tr(user_id, "zip_large_warn"))
        for p in file_paths:
            try:
                p.unlink()
            except Exception:
                pass
        zip_status_msg = None
        try:
            zip_status_msg = await message.reply_document(
                str(zip_path),
                caption=tr(
                    user_id,
                    "zip_ready_caption",
                    n=len(file_paths),
                    insize=pretty_size(total_size),
                    zsize=pretty_size(zip_sz),
                ),
            )
        except Exception:
            zip_status_msg = await message.reply_text(
                tr(
                    user_id,
                    "zip_ready_no_doc",
                    n=len(file_paths),
                    insize=pretty_size(total_size),
                    zsize=pretty_size(zip_sz),
                )
            )
        task = {
            "type": "local_file",
            "path": str(zip_path),
            "file_name": zip_path.name,
            "file_size": zip_sz,
            "part_size_mb": part_mb,
            "rubika_session": session_name,
            "safe_mode": False,
            "zip_password": "",
            "telegram_user_id": user_id,
        }
        clear_state(user_id)
        clear_batch(user_id)
        await queue_or_confirm(
            message,
            task,
            tr(user_id, "zip_queue_summary", name=zip_path.name),
            status_message=zip_status_msg,
        )
        return

    if waiting_for_zip_password:
        password = text.strip()

        if not password:
            await message.reply_text(tr(user_id, "password_empty"))
            return

        settings = load_settings()
        settings["safe_mode"] = True
        settings["zip_password"] = password
        save_settings(settings)

        waiting_for_zip_password = False

        await message.reply_text(tr(user_id, "password_saved_zip"))
        return

    if is_direct_mode(user_id):
        session_name = get_user_session(user_id)
        if not session_name:
            await message.reply_text(tr(user_id, "direct_need_rubika"))
            return
        task = {
            "type": "text_message",
            "text": text,
            "rubika_session": session_name,
        }
        if not await gate_quota(message, user_id, task):
            return
        status = await message.reply_text(tr(user_id, "text_queueing"))
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
        try:
            await status.edit_text(
                tr(user_id, "text_queued", job_id=pushed["job_id"], qpos=qpos),
                parse_mode=None,
            )
        except MessageNotModified:
            pass
        return

    url = extract_first_url(text)

    if not url or not is_direct_url(url):
        return
    await message.reply_text(tr(user_id, "direct_url_use_sendlink"), parse_mode=None)

    
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
        await message.reply_text(tr(user_id, "media_need_rubika"))
        return

    media_type, media = get_media(message)
    if not media:
        await message.reply_text(tr(user_id, "media_bad_type"))
        return

    download_name = build_download_filename(message, media_type, media)
    download_path = DOWNLOAD_DIR / download_name

    status = await message.reply_text(tr(user_id, "media_download_status"))

    try:
        started_at = time.time()
        progress_state = {"last_update": 0, "user_id": user_id}

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
        lim_b = effective_max_file_bytes(user_id)
        if lim_b is not None and file_size > lim_b:
            try:
                downloaded_path.unlink()
            except Exception:
                pass
            await status.edit_text(
                tr(
                    user_id,
                    "file_too_large",
                    max_mb=effective_max_mb_display(user_id),
                    size_mb=fmt_mb_bytes(file_size),
                ),
                parse_mode=None,
            )
            return
        settings = load_settings()
        batch = get_batch(user_id)

        if batch.get("active"):
            files = batch.get("files", [])
            files.append(str(downloaded_path))
            batch["files"] = files
            set_batch(user_id, batch)
            raw_tot = 0
            for pstr in files:
                try:
                    pp = Path(pstr)
                    if pp.exists():
                        raw_tot += pp.stat().st_size
                except OSError:
                    pass
            await status.edit_text(
                tr(
                    user_id,
                    "media_zip_added",
                    n=len(files),
                    raw_mb=fmt_mb_bytes(raw_tot),
                ),
                parse_mode=None,
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
            "telegram_user_id": user_id,
        }

        await status.edit_text(
            tr(
                user_id,
                "media_file_ready",
                name=download_name,
                size=pretty_size(file_size),
            ),
            parse_mode=None,
        )
        await queue_or_confirm(
            message,
            task,
            tr(user_id, "file_prepared_summary", name=download_name),
            status_message=status,
        )
        log_event(
            "media_prepared",
            user_id=user_id,
            file_name=download_name,
            file_size=file_size,
            task_type="local_file",
        )

    except Exception as e:
        log_event("media_prepare_failed", user_id=user_id, error=str(e))
        await status.edit_text(tr(user_id, "media_error", error=str(e)), parse_mode=None)

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
    app.loop.create_task(maybe_broadcast_update())
    idle()
    app.stop()
