import asyncio
import json
from functools import partial
import os
import re
import shutil
import time
import pyzipper
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pyrogram import Client, filters
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
    effective_feed_max,
    effective_toolkit_daily_limit,
    effective_world_daily_limit,
    estimate_task_bytes,
    effective_max_file_bytes,
    feed_push_allowed,
    get_usage_snapshot,
    parallel_job_count,
    plan_matrix_text,
    set_user_tier,
)
from v2.core import menu_engine
from v2.core.interaction_log import log_interaction
from v2.core.direct_mode import load_direct_mode_target, save_direct_mode_target
from v2.core.menu_sections import MenuSection
from v2.core.network_status import load_network_snapshot
from v2.handlers.reply_routes import ReplyRouteDeps, dispatch_reply_keyboard_route
from v2.handlers.rubika_wizard import RubikaWizardDeps, dispatch_rubika_connect_wizard
from v2.handlers.provider_connect_wizards import (
    ProviderConnectWizardDeps,
    dispatch_provider_connect_wizard,
    handle_bale_connect,
    handle_bale_disconnect,
    handle_drive_connect,
    handle_drive_disconnect,
    save_drive_sa_from_downloaded_file,
)
from v2.handlers.zip_batch_wizard import ZipBatchWizardDeps, dispatch_zip_batch_wizard
from v2.handlers.zip_password_prompt import ZipPasswordPromptDeps, handle_zip_password_text
from v2.handlers.direct_mode_text import DirectModeTextDeps, handle_direct_mode_plain_text
from v2.handlers.direct_url_hint import DirectUrlHintDeps, handle_direct_url_sendlink_hint
from v2.handlers.basic_commands import BasicCommandDeps, handle_help, handle_lang, handle_log_help, handle_menu, handle_start, handle_version
from v2.billing import (
    claim_pending_entitlement_notifies,
    maybe_grant_plan_after_paid,
    run_reconcile,
)
from v2.handlers.admin_commands import (
    AdminCommandDeps,
    dispatch_admin_wizard,
    dispatch_admin_inline_callbacks,
    handle_admin_users_list,
    handle_admin_bonus,
    handle_admin_panel,
    handle_admin_payment_lookup,
    handle_admin_payment_status,
    handle_admin_reconcile_billing,
    handle_admin_tier,
    handle_cleanup_downloads,
)
from v2.handlers.admin_ops import (
    AdminOpsDeps,
    dispatch_admin_ops_wizard,
    handle_admin_job_help,
    handle_admin_service_status,
    handle_admin_stats,
    handle_admin_tail_logs,
    handle_show_admin_broadcast_menu,
    start_broadcast_segment,
)

from v2.handlers.plan_commands import (
    PlanCommandDeps,
    handle_plan,
    handle_plan_compare,
    handle_purchase,
    handle_usage,
)
from v2.handlers.queue_commands import QueueCommandDeps, handle_clear_queue, handle_queue_manage, handle_send_link, handle_send_text
from v2.handlers.safemode_command import SafeModeCommandDeps, handle_safemode
from v2.handlers.delete_command import DeleteCommandDeps, handle_delete_one
from v2.handlers.callback_routes import CallbackRouteDeps, dispatch_callback_route
from v2.handlers.media_dest_handler import MediaDestHandlerDeps, handle_media_dest_callback
from v2.handlers.inline_menu_handler import (
    InlineMenuDeps,
    dispatch_inline_menu_callback,
    show_inline_menu,
)
from v2.handlers.world_commands import (
    WorldCommandDeps,
    dispatch_world_wizard,
    handle_calendar,
    handle_markets,
    handle_earthquakes,
    handle_fx_calc_callback,
    handle_market_page_callback,
    handle_quake_mag_callback,
    handle_fx_quick_callback,
    start_age_wizard,
    start_currency_wizard,
    start_timezone_wizard,
    start_weather_wizard,
)
from v2.handlers.batch_commands import BatchCommandDeps, handle_done_batch, handle_new_batch
from v2.handlers.text_entry import TextEntryDeps, handle_text_entry
from v2.handlers.media_handler import MediaHandlerDeps, handle_media_message
from v2.handlers.session_settings_commands import (
    SessionSettingsCommandDeps,
    handle_netstatus,
    handle_rubika_connect,
    handle_rubika_status,
)
from v2.handlers.direct_send_commands import DirectSendCommandDeps, handle_direct_mode
from v2.handlers.clear_chat_commands import ClearChatDeps, handle_clear_chat_callback, handle_clear_chat_prompt
from v2.handlers.alert_commands import (
    AlertCommandDeps,
    dispatch_alert_wizard,
    handle_alert_hour_callback,
    handle_alert_kind_callback,
    handle_alert_manage_callback,
    handle_alert_quake_mag_callback,
    handle_alert_schedule_callback,
    handle_alert_spike_callback,
    start_alert_wizard,
)
from v2.handlers.link_direct_commands import LinkDirectCommandDeps, handle_show_link_direct_menu
from v2.handlers.link_direct_handler import (
    LinkDirectHandlerDeps,
    handle_link_dest_callback,
    handle_link_direct_for_direct_mode,
    handle_link_direct_text,
    handle_link_quality_callback,
)
from v2.transfer.user_credentials import load_bale_credentials, load_drive_credentials
from v2.handlers.toolkit_commands import (
    ToolkitCommandDeps,
    handle_b64_decode,
    handle_b64_encode,
    handle_dns_lookup,
    handle_google_search,
    handle_ipinfo,
    handle_md5,
    handle_my_id,
    handle_my_ip,
    handle_sha256,
    handle_tcp_ping,
    handle_whois,
)
from v2.handlers.feed_reader_commands import (
    FeedReaderDeps,
    dispatch_feed_wizard,
    handle_feed_callback,
    handle_show_feed_menu,
    list_feeds_inline,
    maybe_send_daily_digest,
    poll_rss_pushes,
    start_add_feed_wizard,
)
from v2.handlers.cloudflare_menu_callbacks import dispatch_cf_menu_callback
from v2.handlers.drive_auth_callbacks import dispatch_drive_auth_callback
from v2.handlers.drive_oauth_flow import connect_drive_with_auth_code, notify_oauth_success
from v2.handlers.toolkit_extra_commands import (
    ToolkitExtraDeps,
    handle_email_check,
    handle_lorem,
    handle_mac_lookup,
    handle_password,
    handle_reverse_dns,
    handle_timestamp,
    handle_url_expand,
)
from v2.toolkit.drive_oauth_light import oauth_configured
from v2.handlers.toolkit_net_extra_commands import (
    ToolkitNetExtraDeps,
    dispatch_toolkit_net_extra_wizard,
    handle_blacklist_check,
    handle_http_headers,
    handle_port_check,
    handle_ssl_check,
    handle_subnet_calc,
    handle_website_status,
)
from v2.handlers.ssh_wizard import (
    SshWizardDeps,
    dispatch_ssh_wizard,
    handle_ssh_auth_callback,
    handle_ssh_op_callback,
    start_ssh_add_wizard,
    start_ssh_op_wizard,
)
from v2.handlers.cloudflare_commands import (
    CloudflareCommandDeps,
    dispatch_cloudflare_wizard,
    handle_cf_connect,
    handle_cf_disconnect,
    handle_cf_dns,
    handle_cf_dns_add_zone_callback,
    handle_cf_dns_del_zone_callback,
    handle_cf_dns_delete_callback,
    handle_cf_dns_zone_callback,
    handle_cf_status,
    handle_cf_zones,
    handle_show_cloudflare_menu,
)
from v2.handlers.toolkit_menu_commands import (
    ToolkitMenuDeps,
    handle_show_toolkit_calc_menu,
    handle_show_calc_finance_menu,
    handle_show_calc_numbers_menu,
    handle_show_calc_convert_menu,
    handle_show_calc_math_menu,
    handle_show_calc_text_menu,
    handle_show_calc_other_menu,
    handle_show_toolkit_crypto_menu,
    handle_show_toolkit_menu,
    handle_show_toolkit_network_menu,
)
from v2.handlers.calc_kit_commands import (
    CalcKitDeps,
    dispatch_calc_wizard,
    run_calc_command,
)
from v2.handlers.transfer_hub_commands import (
    TransferHubDeps,
    handle_bale_set_chat,
    handle_bale_status,
    handle_drive_ls,
    handle_drive_status,
    handle_show_bale_menu,
    handle_show_drive_menu,
    handle_show_files_menu as handle_show_files_menu_hub,
    handle_show_rubika_menu as handle_show_rubika_menu_hub,
    handle_show_ssh_menu,
    handle_show_transfer_menu,
    handle_ssh_add,
    handle_ssh_del,
    handle_ssh_ls,
    handle_ssh_list,
)
from v2.bot.client_factory import build_bot_client
from v2.bot.register_handlers import register_handlers

load_dotenv()

# v2: logical keyboard section for analytics / future routing (stored in user_states.json)
MENU_SECTION_KEY = "menu_section"

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

# When true, get_state/get_batch read SQLite mirrors first; JSON is fallback.
# Writes remain dual (JSON + mirror). See docs/v2/09-implementation-roadmap.md.
V2_EPHEMERAL_READ_PRIMARY_SQLITE = (os.getenv("V2_EPHEMERAL_READ_PRIMARY_SQLITE") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
    "sqlite",
)

BILLING_STUB_CHECKOUT = (os.getenv("BILLING_STUB_CHECKOUT") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
BILLING_RECONCILE_ENABLE = (os.getenv("BILLING_RECONCILE_ENABLE") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
try:
    BILLING_RECONCILE_INTERVAL_SEC = max(60, int((os.getenv("BILLING_RECONCILE_INTERVAL_SEC") or "600").strip()))
except ValueError:
    BILLING_RECONCILE_INTERVAL_SEC = 600
try:
    BILLING_RECONCILE_PENDING_MAX_AGE_SEC = max(300, int((os.getenv("BILLING_RECONCILE_PENDING_MAX_AGE_SEC") or "86400").strip()))
except ValueError:
    BILLING_RECONCILE_PENDING_MAX_AGE_SEC = 86400

def _env_flag_on(name: str, *, default_when_unset: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default_when_unset
    return raw in ("1", "true", "yes", "on")


# Phase 4 toolkit: default ON when unset (see installer merge_env_defaults).
TOOLKIT_NETWORK_LIGHT = _env_flag_on("TOOLKIT_NETWORK_LIGHT", default_when_unset=True)
TOOLKIT_UTILITY_LIGHT = _env_flag_on("TOOLKIT_UTILITY_LIGHT", default_when_unset=True)

MINIAPP_BASE_URL = (os.getenv("MINIAPP_BASE_URL") or "").strip().rstrip("/")
try:
    MINIAPP_PORT = int((os.getenv("MINIAPP_PORT") or "8788").strip())
except ValueError:
    MINIAPP_PORT = 8788
MINIAPP_SERVE_LOCAL = _env_flag_on("MINIAPP_SERVE_LOCAL")
RSS_POLL_ENABLE = _env_flag_on("RSS_POLL_ENABLE", default_when_unset=True)
try:
    RSS_POLL_INTERVAL_SEC = max(120, int((os.getenv("RSS_POLL_INTERVAL_SEC") or "900").strip()))
except ValueError:
    RSS_POLL_INTERVAL_SEC = 900


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

app = build_bot_client(
    "tel2rub",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

I18N = {
    "fa": {
        "welcome": (
            "سلام 💙 به TelegramToolsBot\n\n"
            "یک سوئیت کامل ابزار در تلگرام:\n"
            "📁 انتقال — روبیکا · بله · درایو · SSH · لینک مستقیم\n"
            "🧰 ابزارها — شبکه/IP · هش/Base64 · محاسبات (وام، درصد، واحد، پلاک، …)\n"
            "🌍 جهان — آب‌وهوا · تابلوی ارز و طلا · تبدیل ارز · زلزله · تقویم · زمان\n"
            "📰 فیدخوان — RSS / یوتیوب / X با push و خلاصه روزانه\n"
            "☁️ Cloudflare — DNS شخصی · 📋 حساب — پلن و مصرف\n\n"
            "هر بخش منو راهنمای همان بخش را نشان می‌دهد.\n"
            "/menu · /help · /lang · /world_gold"
        ),
        "onboard_next_steps": "از کجا شروع کنیم؟",
        "onboard_checklist": "وضعیت اتصال (اختیاری):\n{rubika} روبیکا\n{bale} بله\n{drive} گوگل درایو",
        "btn_onboard_rubika": "💬 روبیکا",
        "btn_onboard_transfer": "📁 انتقال",
        "btn_onboard_tools": "🧰 ابزارها",
        "btn_onboard_feed": "📰 فید",
        "btn_onboard_world": "🌍 جهان",
        "btn_onboard_plan": "📋 پلن",
        "btn_buy_pro_cta": "💳 ارتقا به Pro",
        "quota_soft_warn": (
            "⚠️ نزدیک سقف سهمیه هستی.\n"
            "امروز حدود {day_pct}% · این ماه حدود {month_pct}%\n"
            "برای فضای بیشتر می‌توانی ارتقا بدهی."
        ),
        "menu_intro": (
            "🏠 منوی اصلی\n\n"
            "📁 انتقال — روبیکا/بله/درایو/فایل و ارسال مستقیم\n"
            "🧰 ابزارها — شبکه، هش، محاسبات\n"
            "🌍 جهان — آب‌وهوا، ارز، طلا، تقویم\n"
            "📰 فیدخوان — RSS و اعلان\n"
            "📋 حساب — پلن و صف\n\n"
            "در هر بخش راهنمای همان منو نشان داده می‌شود."
        ),
        "plan_menu_opened": (
            "📋 حساب و پلن\n"
            "پلن، مصرف، خرید و مدیریت صف."
        ),
        "pick_lang": "زبان را انتخاب کن:",
        "lang_saved": "زبان ذخیره شد.",
        "transfer_menu_title": (
            "📁 انتقال فایل\n\n"
            "مقصد را وصل کن، بعد فایل بفرست یا ارسال مستقیم را روشن کن.\n"
            "💬 روبیکا — اتصال و ارسال\n"
            "📨 بله — ربات و چت مقصد\n"
            "☁️ درایو — آپلود به Google Drive\n"
            "📦 فایل و صف — صف کارها و ZIP\n"
            "📤 ارسال مستقیم — بدون انتخاب مقصد هر بار"
        ),
        "toolkit_menu_title": (
            "🧰 ابزارها\n\n"
            "مستقل از انتقال فایل — دسته را انتخاب کن:\n"
            "🌐 شبکه و IP — DNS، پینگ، Whois، SSL، …\n"
            "🔐 هش و Base64 — MD5، SHA256، رمز، تایم‌استمپ\n"
            "🧮 محاسبات — وام، درصد، تبدیل واحد، پلاک، تاریخ، …"
        ),
        "toolkit_network_menu_title": (
            "🌐 ابزار شبکه\n\n"
            "• Mini App = از دستگاه/شبکهٔ شما (IP واقعی، تأخیر، DoH)\n"
            "• دکمه‌های کیبورد = از سرور ربات (پینگ TCP، SSL، پورت، …)\n"
            "بعد از انتخاب دکمهٔ سرور، مقدار را بفرست (مثل `/dns google.com`)."
        ),
        "toolkit_network_miniapp_hint": (
            "📱 میان‌بر Mini App — ابزارهایی که روی دستگاه شما اجرا می‌شوند:\n"
            "(IP واقعی، دسترسی/پینگ مرورگر، DNS DoH، ابزارک‌ها)\n"
            "برای پینگ TCP / SSL / پورت از سرور ربات از کیبورد پایین یا دکمهٔ «Ping سرور» استفاده کن."
        ),
        "btn_miniapp_reach_device": "📡 پینگ دستگاه",
        "btn_miniapp_reach_server": "🖥 پینگ سرور",
        "btn_miniapp_utils": "🧰 ابزارک‌ها",
        "toolkit_crypto_menu_title": (
            "🔐 هش و Base64\n\n"
            "MD5 / SHA256 / Base64 / رمز تصادفی / تایم‌استمپ / لورم.\n"
            "مثال: `/md5 متن` یا `/b64e سلام`"
        ),
        "toolkit_zip_menu_title": "📦 ساخت فایل zip\nفایل‌ها را ارسال کن، سپس ZIP کن و به مقصد بفرست.",
        "rubika_menu_title": "💬 روبیکا\nاتصال و وضعیت حساب خودت.",
        "bale_menu_title": "📨 بله\nربات و مقصد خودت — `/bale_connect`",
        "drive_menu_title": "☁️ گوگل درایو\n`/drive_connect` سپس ارسال فایل.",
        "ssh_menu_title": "🖥 مدیریت و اتصال به سرور از طریق ربات\nلیست سرورهای خودت. آپلود: `/ssh_put id مسیر`",
        "files_menu_title": "📦 فایل و صف\nروبیکا باید متصل باشد.",
        "settings_menu_title": "📤 ارسال مستقیم\nفقط یک مقصد فعال — قبل از فعال‌سازی اتصال همان مقصد را برقرار کن.",
        "direct_send_menu_title": "📤 ارسال مستقیم",
        "admin_menu_title": "🛡 پنل ادمین",
        "admin_users_menu_title": "👥 مدیریت کاربران\nبرای کارهای نیازمند شناسه، ابتدا از ابزار «آیدی من» یا پیام کاربر ID را بگیر.",
        "admin_billing_menu_title": "💳 مدیریت مالی و پرداخت",
        "admin_maintenance_menu_title": "🧹 نگهداری و وضعیت سیستم",
        "admin_denied": "دسترسی ادمین ندارید.",
        "no_worker_events": "فایل لاگ worker هنوز ساخته نشده.",
        "no_recent_jobs": "برای این چت رویداد task_done/task_failed اخیری ثبت نشده.",
        "recent_jobs_title": "آخرین کارها (worker):",
        "btn_main_transfer": "📤 ارسال فایل",
        "btn_main_network": "🌐 شبکه و IP",
        "btn_main_crypto": "#️⃣ هش و Base64",
        "btn_main_calc": "🧮 ابزارهای محاسباتی",
        "btn_main_toolkit": "🧰 سایر ابزارها",
        "btn_main_miniapp": "📱 Mini App",
        "btn_main_settings": "📤 ارسال مستقیم",
        "btn_main_link_direct": "⬇️ دانلود از لینک",
        "btn_main_cloudflare": "☁️ مدیریت Cloudflare",
        "btn_main_ssh": "🖥 مدیریت و اتصال به سرور از طریق ربات",
        "btn_main_help": "❓ راهنما",
        "btn_main_plan_section": "📋 حساب و پلن",
        "btn_main_admin": "🛡 پنل ادمین",
        "btn_back_main": "برگشت",
        "btn_back_transfer": "برگشت",
        "btn_back_toolkit": "برگشت",
        "btn_transfer_rubika": "💬 روبیکا",
        "btn_transfer_bale": "📨 بله",
        "btn_transfer_drive": "☁️ درایو",
        "btn_transfer_ssh": "🖥 مدیریت و اتصال به سرور از طریق ربات",
        "btn_transfer_files": "📦 فایل و صف",
        "btn_rub_connect": "🔗 اتصال",
        "btn_rub_status": "✅ وضعیت",
        "btn_zip_start": "📥 شروع ZIP",
        "btn_zip_end": "✅ پایان ZIP",
        "btn_send_content": "✉️ متن / لینک",
        "btn_queue": "📋 صف",
        "btn_clear_all": "🗑 پاکسازی",
        "btn_toolkit_network": "🌐 شبکه و IP",
        "btn_toolkit_crypto": "🔐 هش و Base64",
        "btn_toolkit_calc": "🧮 محاسبات",
        "calc_cat_finance_title": "💰 مالی",
        "calc_cat_numbers_title": "🔢 اعداد",
        "calc_cat_convert_title": "🔄 تبدیل",
        "calc_cat_math_title": "∑ ریاضی",
        "calc_cat_text_title": "📝 متن",
        "calc_cat_other_title": "🧩 سایر",
        "toolkit_calc_menu_title": (
            "🧮 محاسبات\n"
            "ابزارهای مستقل (الهام از kitset) — هر دکمه راهنمای ورودی خودش را دارد.\n"
            "• درصد / وام / سپرده / ریال↔تومان\n"
            "• تبدیل واحد و مبنا / باینری / شمارش متن\n"
            "• پلاک و پیش‌شماره کد ملی / اختلاف تاریخ\n"
            "• ریاضی پایه، IELTS، مصرف بنزین/سیگار"
        ),
        "btn_calc_cat_finance": "💰 مالی",
        "btn_calc_cat_numbers": "🔢 اعداد",
        "btn_calc_cat_convert": "🔄 تبدیل",
        "btn_calc_cat_math": "∑ ریاضی",
        "btn_calc_cat_text": "📝 متن",
        "btn_calc_cat_other": "🧩 سایر",
        "btn_back_calc": "برگشت",
        "btn_calc_bmi": "⚖ BMI",
        "btn_calc_compound": "📈 سود مرکب",
        "btn_calc_log": "㏒ لگاریتم",
        "btn_calc_pct_error": "٪ خطا",
        "btn_calc_linear": "𝒙 معادله خطی",
        "btn_calc_quadratic": "𝒙² درجه۲",
        "btn_calc_add_days": "📅 افزودن روز",
        "btn_calc_percent": "٪ درصد",
        "btn_calc_loan": "🏦 قسط وام",
        "btn_calc_deposit": "💰 سود سپرده",
        "btn_calc_rial": "🔄 ریال/تومان",
        "btn_calc_words": "🔤 عدد به حروف",
        "btn_calc_unit": "📐 تبدیل واحد",
        "btn_calc_base": "🔢 تبدیل مبنا",
        "btn_calc_binary": "01 باینری",
        "btn_calc_fuel": "⛽ بنزین",
        "btn_calc_plate": "🚗 شهر پلاک",
        "btn_calc_nid": "🪪 شهر کدملی",
        "btn_calc_datediff": "📆 اختلاف تاریخ",
        "btn_calc_dateconv": "🗓 تبدیل تاریخ",
        "btn_calc_random": "🎲 تصادفی",
        "btn_calc_mean": "📊 میانگین",
        "btn_calc_power": "⬆ توان",
        "btn_calc_sqrt": "√ جذر",
        "btn_calc_fact": "! فاکتوریل",
        "btn_calc_prime": "🔢 عدد اول",
        "btn_calc_ielts": "🎓 IELTS",
        "btn_calc_cig": "🚬 سیگار",
        "btn_calc_rect": "▭ مستطیل",
        "btn_calc_square": "▢ مربع",
        "btn_calc_case": "Aa حروف",
        "btn_calc_wordcount": "📝 شمارش متن",
        "calc_error": "خطا: {detail}",
        "calc_hint_percent": "٪ درصد\nفرمت: `جزء کل` یا `of مقدار درصد` یا `chg قدیم جدید` یا `inc|dec مقدار درصد`",
        "calc_hint_loan": "قسط وام\nفرمت: `اصل نرخ_سالانه_٪ تعداد_ماه`",
        "calc_hint_deposit": "سود سپرده ساده\nفرمت: `اصل نرخ_سالانه_٪ تعداد_ماه`",
        "calc_hint_rial": "ریال↔تومان\nفرمت: `عدد toman` یا `عدد rial`",
        "calc_hint_words": "عدد به حروف فارسی\nیک عدد صحیح بفرست.",
        "calc_hint_unit": "تبدیل واحد\nفرمت: `length|weight|volume|speed|data|temp مقدار از به`\nمثال: `length 10 km m` یا `temp 32 f c`",
        "calc_hint_base": "تبدیل مبنا\nفرمت: `مقدار مبنا_از مبنا_به` مثال: `ff 16 10`",
        "calc_hint_binary": "باینری↔متن\nفرمت: `to متن` یا `from 01001000...`",
        "calc_hint_fuel": "مصرف بنزین\nفرمت: `مسافت_km مصرف_L/100 قیمت_لیتر`",
        "calc_hint_plate": "شهر پلاک\nکد دو رقمی پلاک را بفرست (مثلاً 22).",
        "calc_hint_nid": "شهر کد ملی\nحداقل ۳ رقم اول کد ملی را بفرست.",
        "calc_hint_datediff": "اختلاف تاریخ\nدو تاریخ با فاصله: `1400/01/01 1403/06/15`",
        "calc_hint_dateconv": "تبدیل تاریخ\nیک تاریخ شمسی یا میلادی: `YYYY/MM/DD`",
        "calc_hint_random": "اعداد تصادفی\nفرمت: `تعداد حداقل حداکثر`",
        "calc_hint_mean": "میانگین\nاعداد را با فاصله بفرست.",
        "calc_hint_power": "توان\nفرمت: `پایه توان`",
        "calc_hint_sqrt": "جذر\nیک عدد بفرست.",
        "calc_hint_fact": "فاکتوریل\nیک عدد ۰ تا ۲۰۰ بفرست.",
        "calc_hint_prime": "تشخیص عدد اول\nیک عدد صحیح بفرست.",
        "calc_hint_ielts": "IELTS Overall\nچهار نمره: `L R W S` (گام ۰٫۵)",
        "calc_hint_cig": "هزینه سیگار\nفرمت: `نخ_روزانه قیمت_پاکت [تعداد_در_پاکت] [روز]`",
        "calc_hint_rect": "مستطیل\nفرمت: `عرض طول`",
        "calc_hint_square": "مربع\nضلع را بفرست.",
        "calc_hint_case": "حروف انگلیسی\nفرمت: `upper|lower|title متن`",
        "calc_hint_wordcount": "شمارش متن\nمتن را بفرست.",
        "btn_world_markets": "🏛 تابلوها",
        "btn_world_gold": "🥇 طلا و سکه",
        "btn_world_usd": "💵 دلار",
        "btn_world_eur": "💶 یورو",
        "btn_world_gbp": "💷 پوند",
        "btn_world_jpy": "💴 ین",
        "btn_world_majors": "🌍 ارزهای مهم",
        "currency_ask_from": "ارز مبدأ را بفرست (مثل USD) یا از دکمه‌ها انتخاب کن:",
        "currency_ask_to": "ارز مقصد را بفرست (مثل IRR):",
        "world_menu_title": (
            "🌍 جهان\n\n"
            "ابزارهای زمان، آب‌وهوا و بازار ایران (بازار آزاد ایران).\n\n"
            "🌤 آب‌وهوا — وضعیت و کیفیت هوا بر اساس شهر\n"
            "🕒 ساعت جهانی — زمان محلی شهر/منطقه زمانی\n"
            "📅 تقویم — امروز میلادی و شمسی\n"
            "🎂 سن — محاسبه سن از تاریخ تولد\n"
            "💱 ارز — تبدیل بین ارزها و ریال/تومان\n"
            "📈 ارز و طلا — تابلوی دلار، یورو، ین، طلا و سکه\n"
            "🌋 زلزله — رویدادهای اخیر"
        ),
        "btn_toolkit_zip": "📦 ساخت فایل zip",
        "btn_tool_dns": "🔍 DNS",
        "btn_tool_myip": "📍 IP من",
        "btn_tool_ping": "📡 Ping",
        "btn_tool_ipinfo": "🧭 IP Info",
        "btn_tool_whois": "🧾 Whois",
        "btn_tool_myid": "🆔 آیدی من",
        "btn_tool_google": "🔎 Google",
        "btn_tool_md5": "#️⃣ MD5",
        "btn_tool_sha256": "🔒 SHA256",
        "btn_tool_b64e": "📤 B64 encode",
        "btn_tool_b64d": "📥 B64 decode",
        "btn_plan_plan": "📊 پلن",
        "btn_plan_usage": "📈 مصرف",
        "btn_plan_buy": "💳 خرید",
        "btn_direct_rubika_on": "🚀 مستقیم روبیکا",
        "btn_direct_bale_on": "📨 مستقیم بله",
        "btn_direct_drive_on": "☁️ مستقیم درایو",
        "btn_direct_rubika_off": "⏸ غیرفعال مستقیم روبیکا",
        "btn_direct_bale_off": "⏸ غیرفعال مستقیم بله",
        "btn_direct_drive_off": "⏸ غیرفعال مستقیم درایو",
        "btn_netstatus": "📶 وضعیت شبکه",
        "btn_ssh_list": "📋 لیست سرور",
        "btn_ssh_add_help": "➕ افزودن سرور",
        "btn_ssh_put_help": "⬆️ آپلود SFTP",
        "btn_ssh_get_help": "⬇️ دانلود SFTP",
        "btn_ssh_ls_help": "📂 لیست مسیر",
        "btn_ssh_del_help": "🗑 حذف سرور",
        "btn_drive_ls": "📂 لیست فایل‌ها",
        "btn_drive_download_help": "⬇️ دانلود درایو",
        "btn_admin_panel": "🛡 پنل",
        "btn_admin_users": "👥 کاربران",
        "btn_admin_billing": "💳 مالی",
        "btn_admin_maintenance": "🧹 نگهداری",
        "btn_back_admin": "برگشت",
        "btn_admin_version": "🏷 نسخه",
        "btn_admin_tier_help": "ارتقای پلن",
        "btn_admin_bonus_help": "افزودن حجم",
        "btn_admin_clear_prefs_help": "پاکسازی prefs",
        "btn_admin_payment_lookup_help": "جستجوی پرداخت",
        "btn_admin_payment_status_help": "تغییر وضعیت پرداخت",
        "btn_admin_reconcile": "تطبیق پرداخت‌ها",
        "btn_admin_cleanup": "پاکسازی دانلودها",
        "btn_admin_users_list": "📋 لیست کاربران",
        "btn_admin_broadcast": "📣 پیام‌رسانی",
        "btn_admin_stats": "📊 آمار",
        "btn_admin_service_status": "⚙️ وضعیت سرویس",
        "btn_admin_tail_logs": "📜 لاگ‌ها",
        "btn_admin_job_help": "🔎 جستجوی job",
        "btn_admin_bc_all": "همه",
        "btn_admin_bc_known": "چت‌های شناخته",
        "btn_admin_bc_new7": "جدید ۷روز",
        "btn_admin_bc_guest": "پلن guest",
        "btn_admin_bc_free": "پلن free",
        "btn_admin_bc_pro": "پلن pro",
        "btn_admin_bc_star": "پلن star",
        "btn_admin_bc_expiring": "نزدیک انقضا",
        "btn_admin_bc_expired": "منقضی‌شده",
        "btn_admin_bc_inactive": "غیرفعال ۳۰روز",
        "admin_broadcast_menu_title": "📣 پیام‌رسانی ادمین\nسگمنت را انتخاب کن؛ بعد متن پیام را بفرست و با بله تأیید کن.",
        "admin_stats_body": (
            "📊 آمار کاربران\n"
            "کل فعالیت: {users_total}\n"
            "چت شناخته: {known_chats}\n"
            "جدید ۷روز: {new_7d}\n"
            "غیرفعال ۳۰روز: {inactive_30d}\n"
            "نزدیک انقضا ۷روز: {expiring_7d}\n"
            "منقضی‌شده: {expired}\n"
            "پلن‌ها — guest:{tier_guest} free:{tier_free} pro:{tier_pro} star:{tier_star}"
        ),
        "admin_broadcast_ask_body": "سگمنت `{segment}` ({label}) — مخاطب: {count}\nمتن پیام همگانی را بفرست (یا لغو).",
        "admin_broadcast_body_empty": "متن پیام خالی است. متن را بفرست یا بگو لغو.",
        "admin_broadcast_confirm": "ارسال به {count} نفر (سگمنت {segment})؟\n\nپیش‌نمایش:\n{preview}\n\nبرای تأیید: بله · برای لغو: خیر",
        "admin_broadcast_confirm_hint": "بله / خیر را بفرست.",
        "admin_broadcast_cancelled": "پیام‌رسانی لغو شد.",
        "admin_broadcast_empty": "مخاطب یا متن خالی است.",
        "admin_broadcast_sending": "در حال ارسال به {total} نفر…",
        "admin_broadcast_progress": "پیشرفت {done}/{total} · موفق {sent} · ناموفق {failed}",
        "admin_broadcast_done": "ارسال تمام شد.\nسگمنت: {segment}\nموفق: {sent} · ناموفق: {failed} · کل: {total}",
        "admin_service_status_body": "⚙️ وضعیت سرویس\n\n{detail}",
        "admin_tail_logs_body": "📜 لاگ‌های اخیر\n\n{detail}",
        "admin_job_ask": "job_id را بفرست (یا لغو).",
        "admin_job_not_found": "job پیدا نشد: {job_id}",
        "feed_added_empty_warning": "فید ذخیره شد ولی فعلاً آیتمی نداشت. بعداً push یا مشاهده را امتحان کن.",
        "feed_err_no_entries": "فید خوانده شد ولی آیتمی نداشت",
        "feed_err_parse_failed": "ساختار فید قابل‌خواندن نبود",
        "feed_err_http_error": "خطای HTTP هنگام دریافت فید",
        "feed_err_timeout": "زمان دریافت فید تمام شد",

        "admin_users_list_empty": "هنوز کاربری ثبت نشده.",
        "btn_cf_connect": "🔐 اتصال CF",
        "btn_cf_status": "✅ وضعیت CF",
        "btn_cf_zones": "🌐 دامنه‌ها",
        "btn_cf_dns_help": "📋 DNS رکوردها",
        "btn_cf_disconnect": "❌ قطع Cloudflare",
        "btn_inline_refresh": "بروزرسانی",
        "btn_inline_pending": "نمایش Pending",
        "btn_inline_failed": "نمایش Failed",
        "btn_inline_clear": "پاکسازی صف من",
        "btn_inline_recent": "آخرین کارها",
        "btn_inline_faildetail": "جزئیات خطا",
        "queue_kb_refresh": "بروزرسانی شد",
        "queue_kb_cleared": "صف پاک شد",
        "directmode_usage": (
            "ارسال مستقیم (یک مقصد):\n"
            "`/directmode rubika on` · `/directmode bale on` · `/directmode drive on`\n"
            "خاموش: `/directmode rubika off` (یا bale/drive)\n"
            "قدیمی: `/directmode on` = روبیکا"
        ),
        "direct_on_rubika": "ارسال مستقیم به روبیکا فعال شد.",
        "direct_on_bale": "ارسال مستقیم به بله فعال شد.",
        "direct_on_drive": "ارسال مستقیم به Google Drive فعال شد.",
        "direct_on_explain": (
            "حالت ارسال مستقیم فعال است.\n"
            "از این به بعد هر فایل/متنی که ارسال کنید، مستقیم به مقصد انتخاب‌شده ارسال می‌شود."
        ),
        "direct_switched_off": "ارسال مستقیم {old} غیرفعال شد. در حال فعال‌سازی حالت جدید…",
        "net_reason_ok": "بدون مشکل",
        "direct_off": "ارسال مستقیم غیرفعال شد.",
        "direct_off_wrong_target": "مقصد فعال `{active}` است — ابتدا همان را خاموش کن.",
        "direct_url_only_for_bale_drive": "در مستقیم بله/درایو فقط لینک/ویدیو پشتیبانی می‌شود.",
        "link_menu_opened": (
            "🔗 دانلود لینک / ویدیو\n\n"
            "📌 لینک‌های پشتیبانی‌شده:\n"
            "• لینک مستقیم فایل (HTTP/HTTPS)\n"
            "• یوتیوب (ویدیو و صدا، انتخاب کیفیت)\n"
            "• هر سایتی که yt-dlp پشتیبانی کند\n\n"
            "📖 نحوه استفاده:\n"
            "1️⃣ لینک را بفرست\n"
            "2️⃣ اطلاعات فایل نمایش داده می‌شود\n"
            "3️⃣ کیفیت و مقصد (روبیکا/بله/درایو) را انتخاب کن\n"
            "4️⃣ دانلود و ارسال خودکار انجام می‌شود"
        ),
        "link_send_url": "لطفاً یک لینک معتبر (http/https یا یوتیوب) بفرست.",
        "link_probing": "در حال بررسی لینک (بدون دانلود)…",
        "link_probe_summary": "📎 `{title}`\nنوع: {link_type}\nحجم تقریبی: {size}",
        "link_size_unknown": "نامشخص",
        "link_type_direct": "لینک مستقیم",
        "link_type_youtube": "یوتیوب",
        "link_type_magnet": "تورنت",
        "link_pick_dest": "مقصد را انتخاب کن:",
        "link_pick_quality": "کیفیت را انتخاب کن:",
        "link_dest_telegram": "تلگرام (همین چت)",
        "link_sending_telegram": "در حال ارسال فایل در همین چت…",
        "btn_clear_chat": "🧹 پاک کردن چت",
        "clear_chat_confirm": "پیام‌های ربات در این چت پاک می‌شوند.\nاشتراک و تنظیماتت حفظ می‌شود.\nبرای تایید دکمه زیر را بزن.",
        "clear_chat_done": "چت پاک شد ✅ ({n} پیام ربات حذف شد). اشتراک و تنظیمات دست‌نخورده ماند.",
        "clear_chat_done_full": "چت پاک شد ✅ ({n} پیام ربات، {u} پیام کاربر در صورت امکان). اشتراک حفظ شد.",
        "quake_pick_mag": "حداقل شدت زلزله (ریشتر) را انتخاب کن:",
        "alerts_ask_quake_mag": "حداقل شدت هشدار زلزله (ریشتر) را انتخاب کن:",
        "alerts_quake_added_ok": "هشدار زلزله ثبت شد ✅ (حداقل {mag} ریشتر)",
        "clear_chat_none": "پیام قابل حذفی پیدا نشد (بعد از این آپدیت پیام‌های جدید ربات قابل پاک‌سازی‌اند).",
        "btn_world_alerts": "🔔 هشدارها",
        "alerts_paid_only": "هشدارهای زمان‌بندی فقط برای پلن Pro/Star است.",
        "alerts_pick_kind": "نوع هشدار را انتخاب کن:",
        "alerts_ask_fx_asset": "کد ارز را بفرست (مثل USD یا EUR):",
        "alerts_ask_gold_asset": "دارایی طلا را بفرست (مثل SEKEE یا GOLD18 یا سکه امامی):",
        "alerts_ask_weather_city": "نام شهر را برای آب‌وهوا بفرست:",
        "alerts_ask_quake_city": "نام شهر/منطقه برای فیلتر زلزله بفرست (یا `همه`):",
        "alerts_ask_schedule": "بازه ارسال را انتخاب کن:",
        "alerts_ask_hour": "ساعت ارسال به وقت تهران را انتخاب کن:",
        "alerts_ask_spike": "آستانه جهش قیمت را انتخاب کن (یا سفارشی):",
        "alerts_ask_spike_custom": "آستانه جهش٪ را بفرست (مثلاً ۳). برای بدون شرط جهش `-` بفرست:",
        "alerts_added_ok": "هشدار ثبت شد ✅ — می‌توانی الان تست بگیری.",
        "alerts_add_fail": "ثبت هشدار نشد: {detail}",
        "alerts_empty": "هنوز هشداری ثبت نکرده‌ای.",
        "alerts_list_title": "هشدارهای تو (حذف / خاموش / تست):",
        "alerts_btn_delete": "🗑",
        "alerts_btn_enable": "▶️",
        "alerts_btn_disable": "⏸",
        "alerts_btn_test": "🧪 تست",
        "alerts_btn_list": "📋 لیست",
        "alerts_btn_new": "➕ هشدار جدید",
        "alerts_btn_mute_24h": "🔇 ۲۴س",
        "alerts_btn_mute_7d": "🔇 ۷روز",
        "alerts_btn_unmute": "🔔 لغو سکوت",
        "alerts_muted_24h": "۲۴ ساعت سکوت شد",
        "alerts_muted_7d": "۷ روز سکوت شد",
        "alerts_unmuted": "سکوت برداشته شد",
        "alerts_deleted": "حذف شد",
        "alerts_not_found": "هشدار پیدا نشد",
        "alerts_enabled": "فعال شد",
        "alerts_disabled": "خاموش شد",
        "alerts_test_sending": "در حال ارسال تست…",
        "alerts_test_prefix": "🧪 پیام آزمایشی هشدار",
        "alerts_test_fail": "تست ناموفق: {detail}",
        "btn_calc_digits": "۱۲۳ ارقام FA/EN",
        "calc_ask_digits": "متن دارای عدد را بفرست تا ارقام فارسی↔انگلیسی تبدیل شوند:",
        "link_dest_rubika": "روبیکا",
        "link_dest_bale": "بله",
        "link_dest_drive": "Google Drive",
        "link_dest_cancel": "لغو",
        "link_dest_invalid": "مقصد نامعتبر است.",
        "link_quality_best": "بهترین",
        "link_quality_1080": "1080p",
        "link_quality_720": "720p",
        "link_quality_480": "480p",
        "link_quality_audio_only": "فقط صدا",
        "link_quality_best_set": "کیفیت بهترین حالت انتخاب شد. حالا مقصد را انتخاب کن.",
        "link_need_rubika": "روبیکا متصل نیست. `/rubika_connect`",
        "link_probe_unsupported": "این لینک قابل دانلود نیست. ({detail})",
        "link_youtube_needs_cookies": "یوتیوب ربات را بلاک کرده (bot-check).\nادمین باید فایل کوکی Netscape را روی سرور بگذارد و `YTDLP_COOKIES` را در `.env` ست کند.\nراهنما: https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies",
        "link_html_landing": "این آدرس صفحه وب است نه فایل مستقیم. لینک دانلود واقعی پیدا نشد.",
        "link_telegram_too_large": "فایل {size_mb}MB است؛ سقف ارسال در تلگرام برای ربات حدود {max_mb}MB است.\nمقصد روبیکا/درایو را انتخاب کن یا فایل کوچک‌تر بفرست.",
        "link_telegram_size_warn": "⚠️ سایز تقریبی {size_mb}MB — ارسال به تلگرام ممکن است به‌خاطر سقف {max_mb}MB شکست بخورد. روبیکا/درایو بهتر است.",
        "link_youtube_needs_cookies": "YouTube blocked the bot (bot-check).\nAdmin must place a Netscape cookies file and set `YTDLP_COOKIES` in `.env`.\nGuide: https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies",
        "link_html_landing": "This URL is a web page, not a direct file. No download URL found.",
        "link_telegram_too_large": "File is {size_mb}MB; Telegram bot upload limit is about {max_mb}MB.\nPick Rubika/Drive or a smaller file.",
        "link_telegram_size_warn": "⚠️ About {size_mb}MB — Telegram send may fail (limit ~{max_mb}MB). Prefer Rubika/Drive.",
        "link_ytdlp_missing": "یوتیوب نیاز به `yt-dlp` روی سرور دارد.",
        "link_magnet_unsupported": "لینک magnet هنوز پشتیبانی نمی‌شود.",
        "link_session_expired": "انتخاب منقضی شد — لینک را دوباره بفرست.",
        "link_cancelled": "لغو شد.",
        "link_audio_only": "فقط صدا",
        "link_quality_set": "کیفیت {quality}p انتخاب شد. حالا مقصد را انتخاب کن.",
        "link_quality_audio_set": "حالت فقط صدا فعال شد. حالا مقصد را انتخاب کن.",
        "link_downloading": "در حال دانلود روی سرور…",
        "link_download_failed": "دانلود ناموفق: {error}",
        "link_download_done_queue": "دانلود شد؛ در صف ارسال…",
        "link_media_hint": "در بخش ⬇️ دانلود از لینک باید لینک بفرستی. برای ارسال فایل از «📤 ارسال فایل» مقصد را انتخاب کن.",
        "cf_menu_title": "☁️ Cloudflare\nاتصال per-user با API Token. مشاهده و ایجاد/حذف DNS با تأیید.",
        "cf_ask_token": (
            "☁️ اتصال Cloudflare (گام‌به‌گام)\n\n"
            "۱) وارد حساب Cloudflare شو\n"
            "۲) برو به: پروفایل → API Tokens → Create Token\n"
            "۳) قالب Edit zone DNS را انتخاب کن (خواندن/ویرایش DNS دامنه)\n"
            "۴) دامنه را محدود کن و Create بزن\n"
            "۵) توکن را کپی کن و همین‌جا بفرست (مثل رمز است؛ به کسی نده)\n\n"
            "لینک مستقیم: https://dash.cloudflare.com/profile/api-tokens"
        ),
        "cf_token_invalid": "توکن Cloudflare نامعتبر است: {detail}",
        "cf_connected_ok": "Cloudflare متصل شد ✅ وضعیت توکن: {detail}",
        "cf_disconnected": "اتصال Cloudflare قطع شد.",
        "cf_not_connected": "Cloudflare هنوز متصل نیست.\nبرای اتصال دکمه زیر را بزن.",
        "cf_status_ok": "Cloudflare OK ✅ {detail}",
        "cf_status_bad": "Cloudflare نامعتبر است: {detail}",
        "cf_zones_result": "دامنه‌ها:\n{detail}",
        "cf_dns_usage": "استفاده: `/cf_dns <zone_id> [record-name]`\nیا از دکمه DNS یک دامنه را انتخاب کن.",
        "cf_dns_pick_zone": "دامنه را برای مشاهده رکوردهای DNS انتخاب کن:",
        "cf_dns_pick_zone_add": "دامنه را برای ایجاد رکورد DNS انتخاب کن:",
        "cf_dns_pick_zone_del": "دامنه را برای حذف رکورد DNS انتخاب کن:",
        "cf_dns_pick_record_del": "رکوردی که باید حذف شود را انتخاب کن:",
        "cf_dns_ask_type": "نوع رکورد را بفرست (A, AAAA, CNAME, TXT, MX, …) یا /cancel",
        "cf_dns_ask_name": "نام رکورد را بفرست (مثلاً www یا @):",
        "cf_dns_ask_content": "مقدار رکورد را بفرست (IP، هدف CNAME، متن TXT، …):",
        "cf_dns_confirm_create": "ایجاد `{type}` `{name}` → `{content}`؟\nبله / خیر",
        "cf_dns_write_ok": "DNS: {detail}",
        "cf_dns_empty": "رکوردی برای حذف پیدا نشد.",
        "cf_dns_del_need_zone": "ابتدا دامنه را از منوی حذف DNS انتخاب کن.",
        "btn_cf_dns_add": "➕ DNS جدید",
        "btn_cf_dns_del": "🗑 حذف DNS",
        "cf_zones_empty": "هیچ دامنه‌ای روی این توکن پیدا نشد.",
        "cf_dns_result": "DNS records:\n{detail}",
        "cf_error": "خطای Cloudflare: {error}",
        "cf_media_hint": "در منوی Cloudflare فقط توکن API (متن) می‌پذیریم. برای ارسال فایل به «تنظیمات» یا «انتقال فایل» برو.",
        "wizard_cancelled": "ویزارد لغو شد.",
        "wizard_send_file_hint": "در این مرحله یک فایل/سند بفرست (نه متن). برای لغو: /cancel",
        "bale_ask_chat_id": "شناسه چت مقصد بله را بفرست (مثلاً عددی یا @channel):",
        "newbatch_ok": (
            "جلسه فایل ZIP فعال شد.\n"
            "فایل‌ها را ارسال کن. بعد از اتمام، «پایان فایل ZIP» یا `/done` را بزن."
        ),
        "prompt_sendtext": "متن را ارسال کن.",
        "prompt_sendlink": "لینک را ارسال کن.",
        "queue_panel": (
            "مدیریت صف:\n\n"
            "- در انتظار در صف SQLite (همه مقصدهای تو): `{pending}`\n"
            "- هم‌اکنون در حال پردازش (worker): `{processing}`\n"
            "- کل خطاها (global): `{failed}`\n"
            "- حذف‌شده‌ها: `{deleted}`\n"
            "- لغوشده‌ها: `{cancelled}`\n\n"
            "اگر آپلود گیر کرد ولی اینجا `۰` بود، یعنی کار از صف بیرون آمده و worker مشغول است.\n\n"
            "برای پاکسازی صف از دکمهٔ «پاکسازی صف من» استفاده کن."
        ),
        "queue_processing_none": "`—`",
        "queue_processing_detail": "`{job_id}` نوع `{task_type}` — `{file}` (~{size})",
        "bale_not_connected": "بله هنوز متصل نیست.\nبرای اتصال دکمه زیر را بزن.",
        "bale_ask_token": (
            "📖 راهنمای اتصال بله:\n\n"
            "1️⃣ اپلیکیشن بله را باز کنید\n"
            "2️⃣ به @botfather پیام دهید و `/newbot` بفرستید\n"
            "3️⃣ نام و یوزرنیم ربات را وارد کنید\n"
            "4️⃣ توکنی که دریافت می‌کنید را همینجا بفرستید\n\n"
            "این توکن فقط برای حساب تلگرام شما ذخیره می‌شود."
        ),
        "bale_token_invalid": "توکن بله نامعتبر است: {detail}",
        "bale_token_ok": "ربات بله تأیید شد (@{bot}).\nحالا `chat_id` مقصد را بفرست (گروه/کاربر در بله).",
        "bale_chat_id_empty": "chat_id خالی است. دوباره بفرست.",
        "bale_chat_invalid": "chat_id بله تأیید نشد: {detail}",
        "bale_connected_ok": (
            "بله متصل شد ✅\n"
            "مقصد: {chat_id}\n\n"
            "چطور فایل بفرستی:\n"
            "• در منوی بله بمان و فایل را مستقیم بفرست\n"
            "• یا 📁 انتقال → 📤 ارسال مستقیم → مستقیم بله"
        ),
        "bale_already_connected": "بله قبلاً متصل است. برای اتصال مجدد `/bale_disconnect` سپس `/bale_connect`.",
        "bale_disconnected": "اتصال بله قطع شد.",
        "btn_bale_connect": "🔗 اتصال بله",
        "btn_bale_status": "✅ وضعیت بله",
        "btn_bale_set_chat": "🎯 تغییر مقصد بله",
        "btn_bale_disconnect": "❌ قطع بله",
        "bale_status_no_chat": "توکن OK ({detail}). chat_id نداری — در ویزارد `/bale_connect` ادامه بده.",
        "bale_status_ok": "بله: chat_id=`{chat_id}` — {detail}",
        "bale_set_chat_usage": (
            "شناسه چت بله را بفرست.\n"
            "اگر نمی‌دانی chat_id چیست: ربات را به گروه اضافه کن یا در چت خصوصی "
            "یک پیام بفرست و از ابزار «آیدی من» استفاده کن؛ یا عدد منفی گروه را از ادمین بپرس."
        ),
        "bale_set_chat_saved": "مقصد بله ذخیره شد: `{chat_id}`",
        "drive_not_connected": (
            "گوگل درایو هنوز متصل نیست.\n"
            "برای شروع دکمه «اتصال درایو» را بزن — ورود با Google ساده‌ترین راه است."
        ),
        "drive_connect_choose": "روش اتصال Google Drive را انتخاب کن:",
        "btn_drive_auth_sa": "📄 سرویس‌اکانت (JSON)",
        "btn_drive_auth_oauth": "🔐 ورود با Google",
        "btn_drive_oauth_open": "باز کردن صفحه ورود Google",
        "drive_oauth_start": (
            "۱) دکمه زیر را بزن و با حساب Google خودت وارد شو.\n"
            "۲) بعد از تأیید، اگر به ربات برنگشتی، کد authorization را اینجا paste کن."
        ),
        "drive_oauth_ok_ask_folder": "ورود Google موفق ✅\nلینک یا ID پوشه Drive را بفرست:",
        "drive_oauth_failed": "ورود Google ناموفق: {detail}",
        "drive_oauth_code_empty": "کد authorization خالی است.",
        "drive_oauth_not_configured": "ورود Google روی سرور فعال نیست (OAuth env).",
        "drive_ask_sa_json": (
            "☁️ اتصال Google Drive\n\n"
            "پیشنهادی: از دکمه «ورود با Google» استفاده کن (ساده‌تر برای همه).\n\n"
            "حالت پیشرفته — فقط اگر فایل JSON سرویس‌اکانت داری:\n"
            "۱) همان فایل JSON را به‌صورت سند اینجا بفرست\n"
            "۲) بعد لینک پوشه‌ای که می‌خواهی فایل‌ها آنجا بروند را بفرست\n"
            "۳) پوشه را با ایمیل سرویس‌اکانت به‌صورت Editor به‌اشتراک بگذار"
        ),
        "drive_sa_already_uploaded": "فایل JSON قبلاً ذخیره شده ✅\nپوشه را با این ایمیل Share کن:\n`{email}`\n\nحالا لینک پوشه یا folder ID را بفرست.",
        "drive_share_email_hint": "✅ JSON دریافت شد.\nپوشه Drive را با این ایمیل **Editor** کن:\n`{email}`",
        "drive_ask_folder_id": "لینک پوشه Drive یا folder ID را بفرست (مثلاً `https://drive.google.com/drive/folders/XXXX`):",
        "drive_folder_empty": "folder_id خالی است.",
        "drive_sa_missing_retry": "فایل سرویس‌اکانت پیدا نشد. دوباره اتصال درایو را شروع کن.",
        "drive_connected_ok": (
            "درایو متصل شد ✅\n"
            "پوشه: {folder_id}\n\n"
            "چطور فایل بفرستی:\n"
            "• در منوی درایو بمان و فایل را بفرست\n"
            "• یا 📁 انتقال → 📤 ارسال مستقیم → مستقیم درایو"
        ),
        "drive_disconnected": "اتصال درایو قطع شد.",
        "btn_drive_connect": "🔗 اتصال درایو",
        "btn_drive_status": "✅ وضعیت درایو",
        "btn_drive_disconnect": "❌ قطع درایو",
        "drive_sa_need_document": "JSON را به‌صورت فایل (document) بفرست، نه متن.",
        "drive_sa_need_json": "نام فایل باید `.json` باشد.",
        "drive_sa_invalid": "JSON نامعتبر: {error}",
        "drive_status_line": "درایو ({mode}): {ok}\n{detail}",
        "drive_ls_result": "فایل‌های Drive:\n{detail}",
        "drive_ls_error": "لیست Drive ناموفق: {error}",
        "ssh_list_empty": "هیچ سرور SSH ثبت نشده. از دکمه «افزودن سرور» استفاده کن.",
        "ssh_list_title": "سرورهای SSH:",
        "ssh_list_row": "#{id} · {label}\n  {ssh_user}@{host}:{port}",
        "ssh_add_usage": "استفاده: `/ssh_add <label> <host> <port> <user> [password]`\nیا دکمه «➕ افزودن سرور» را بزن تا مرحله‌به‌مرحله راهنمایی شوی.",
        "ssh_wizard_ask_label": "نام کوتاه برای این سرور بفرست (مثلاً `vps1`):",
        "ssh_wizard_ask_host": "آدرس host یا IP سرور را بفرست:",
        "ssh_wizard_ask_port": "پورت SSH را بفرست (معمولاً `22`):",
        "ssh_wizard_ask_user": "نام کاربر SSH را بفرست (مثلاً `root`):",
        "ssh_wizard_ask_auth": "روش ورود را با یکی از دکمه‌های زیر انتخاب کن:",
        "ssh_wizard_ask_password": "رمز SSH را بفرست (در پیام بعدی حذف می‌شود):",
        "ssh_wizard_ask_key_paste": (
            "متن کامل کلید خصوصی PEM را در یک پیام بفرست "
            "(از `-----BEGIN` تا `-----END`)"
        ),
        "ssh_wizard_ask_key_file": "فایل کلید خصوصی (`.pem` یا `.key`) را به‌صورت **سند** بفرست (نه عکس).",
        "ssh_wizard_bad_port": "پورت باید عدد بین ۱ تا ۶۵۵۳۵ باشد.",
        "ssh_wizard_key_invalid": "کلید نامعتبر: {error}",
        "ssh_op_pick_server": "سرور را برای عملیات `{op}` انتخاب کن:",
        "ssh_op_ask_path": "مسیر remote را برای `{op}` بفرست (مثلاً `/home` یا `.`):",
        "ssh_add_ok": "سرور `{label}` ({host}:{port}) ذخیره شد.",
        "ssh_put_usage": "استفاده: `/ssh_put <server_id> <remote_path>` سپس فایل را بفرست",
        "ssh_ls_usage": "استفاده: `/ssh_ls <server_id> [remote_path]`",
        "ssh_del_usage": "استفاده: `/ssh_del <server_id>`",
        "ssh_put_await_file": "مسیر روی سرور ثبت شد. حالا فایل را در تلگرام بفرست.",
        "ssh_server_not_found": "سرور SSH پیدا نشد.",
        "ssh_auth_missing": "برای این سرور رمز یا کلید SSH ثبت نشده. از «➕ افزودن سرور» دوباره اضافه کن.",
        "ssh_ls_result": "لیست `{path}`:\n{detail}",
        "ssh_ls_error": "SSH ls ناموفق: {error}",
        "ssh_del_ok": "سرور SSH `#{id}` حذف شد.",
        "bale_active_hint": "پس از `/bale_connect`، همین‌جا فایل بفرست تا با ربات بله خودت ارسال شود (~۲۰ مگ).",
        "drive_active_hint": "پس از `/drive_connect`، فایل بفرست تا در Drive خودت آپلود شود. دانلود: `/drive_download <id>`",
        "drive_download_usage": "استفاده: `/drive_download <google_drive_file_id>`",
        "drive_download_send_only": "شناسه فایل Google Drive را بفرست:",
        "ssh_get_usage": "استفاده: `/ssh_get <server_id> <remote_path>`",
        "help_short": (
            "📖 راهنمای کامل ربات\n\n"
            "🏠 /menu — منوی اصلی\n"
            "📤 ارسال فایل — روبیکا / بله / گوگل‌درایو / SSH / ارسال مستقیم\n"
            "⬇️ دانلود از لینک — لینک مستقیم، تصویر، PDF، ویدیو (یوتیوب با کوکی سرور)\n"
            "🌐 شبکه و IP — DNS، Ping، Whois، IP Info، پورت، SSL\n"
            "#️⃣ هش و Base64 — MD5، SHA256، Encode/Decode\n"
            "🧮 ابزارهای محاسباتی — مالی، ریاضی، واحد، ارقام\n"
            "🌍 بازار و آب‌وهوا — تابلوها، ماشین‌حساب ارز (متن آزاد مثل `100 دلار`)، زلزله با فیلتر ریشتر، هشدار Pro\n"
            "📰 فیدها — RSS و اعلان\n"
            "☁️ مدیریت Cloudflare — DNS دامنه\n"
            "🖥 مدیریت سرور — SSH از تلگرام\n"
            "📋 حساب و پلن — /usage · /plan · /purchase\n"
            "🧹 پاک کردن چت — حذف پیام‌های ربات (و در صورت اجازه، پیام‌های نزدیک کاربر)\n\n"
            "زبان: /lang · منوی شیشه‌ای: /imenu · حذف کار: /del <job_id>\n"
            "وضعیت شبکه: /netstatus"
        ),
        "help_short_admin_extra": (
            "🛡 ادمین:\n"
            "/admin · /loghelp · لاگ‌ها و مصرف\n"
            "YTDLP_COOKIES برای یوتیوب · MINIAPP_BASE_URL برای مینی‌اپ"
        ),
        "help_short_admin": (
            "🛡 میان‌بر ادمین:\n"
            "/admin · /loghelp · /usage · /plan"
        ),
        "loghelp_body": (
            "اگر ارسال فایل مشکل داشت:\n\n"
            "1) شناسه کار (job_id) را از پیام صف کپی کن.\n"
            "2) همان شناسه را برای پشتیبانی بفرست.\n"
            "3) یک‌بار /netstatus و وضعیت اتصال مقصد را چک کن.\n"
            "4) در صورت نیاز با /del <job_id> لغو و دوباره بفرست."
        ),
        "loghelp_body_admin": (
            "راهنمای تحلیل لاگ job:\n\n"
            "1) job_id را از پیام Queued بردار.\n"
            "2) bot logs: task_queued\n"
            "3) worker: task_started -> task_done|task_failed\n"
            "4) task_requeued = مشکل شبکه/دسترسی\n"
            "5) rubika_connect_ok / rubika_connect_failed\n\n"
            "مسیر لاگ‌ها:\n"
            "- /opt/tele2rub/queue/bot_events.jsonl\n"
            "- /opt/tele2rub/queue/worker_events.jsonl\n"
            "- /tmp/tele2rub-installer.jsonl"
        ),
        "rubika_not_connected": "روبیکا هنوز متصل نیست.\nبرای اتصال دکمه زیر را بزن.",
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
        "rubika_connected_ok": ("روبیکا متصل شد ✅\n\n""چطور فایل بفرستی:\n""• 📁 انتقال → 📤 ارسال مستقیم → مستقیم روبیکا را روشن کن، بعد فایل بفرست\n""• یا فایل را بفرست و مقصد را از دکمه‌ها انتخاب کن"),
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
        "btn_confirm_send": "✅ تأیید ارسال",
        "btn_cancel_send": "❌ لغو",
        "btn_main_world": "🌍 بازار و آب‌وهوا",
        "failed_detail_title": "آخرین خطاهای ثبت‌شده برای نشست شما:",
        "confirm_cancelled": "ارسال لغو شد.",
        "confirm_already_handled": "این درخواست قبلاً پردازش شده است.",
        "confirm_use_buttons": "برای تأیید یا لغو ارسال، از دکمه‌های زیر همان پیام استفاده کن.",
        "cleanup_done": "پاکسازی `downloads/`: {n} فایل، حدود {mb} MB آزاد شد.",
        "direct_need_rubika": "برای حالت مستقیم اول `/rubika_connect` بزن.",
        "file_too_large": "فایل از سقف پلن بزرگ‌تر است (حداکثر ~{max_mb} مگابایت). حجم این فایل: ~{size_mb} مگابایت.\nبرای ارتقا: /purchase",
        "file_too_large_admin": "فایل از سقف مجاز بزرگ‌تر است (حداکثر ~{max_mb} مگابایت با توجه به پلن و MAX_FILE_MB). حجم: ~{size_mb} مگابایت.",
        "bale_file_too_large": "بله این فایل را نمی‌پذیرد (حداکثر `{max_mb}` MB). حجم فایل: ~`{size_mb}` MB.",
        "text_unhandled_hint": "متوجه این پیام نشدم. از دکمه‌های منو استفاده کن یا `/help` را بزن.",
        "admin_max_file": "`MAX_FILE_MB` (سقف آپلود env): `{mb}` (`0` یا خالی = بدون سقف env)",
        "admin_plan_note": "سهمیه پلن‌ها در SQLite (`user_entitlements`) — `/usage` برای کاربران.",
        "admin_clear_prefs_hint": "پاک کردن ردیف mirror prefs در SQLite: `/admin_clear_prefs <telegram_user_id>`",
        "admin_clear_state_mirrors_hint": "پاک mirror ویزارد/بچ در SQLite (JSON را عوض نمی‌کند): `/admin_clear_state_mirrors <telegram_user_id>`",
        "admin_tier_usage": "استفاده: `/admin_tier <telegram_user_id> <guest|free|pro|star> [days]`",
        "admin_bonus_usage": "استفاده: `/admin_bonus <telegram_user_id> <extra_month_mb>`",
        "admin_wizard_user_ask": "شناسه عددی تلگرام کاربر را بفرست:",
        "admin_wizard_need_user_id": "لطفاً فقط شناسه عددی معتبر بفرست.",
        "admin_wizard_tier_ask": "پلن را بفرست: `guest`، `free`، `pro` یا `star`",
        "admin_wizard_days_ask": "برای pro تعداد روز اعتبار را بفرست:",
        "admin_wizard_tier_done": "پلن کاربر `{target}` روی `{tier}` تنظیم شد.",
        "admin_wizard_bonus_ask": "حجم اضافه ماهانه را به MB بفرست:",
        "admin_wizard_bonus_done": "برای کاربر `{target}` مقدار `{mb}` MB حجم اضافه ثبت شد.",
        "admin_wizard_tier_for_user": "کاربر `{target}` — پلن را بفرست: `guest`، `free`، `pro` یا `star`",
        "admin_wizard_bonus_for_user": "کاربر `{target}` — حجم اضافه ماهانه را به MB بفرست:",
        "admin_payment_lookup_hint": "لیست آخرین پرداخت‌های SQLite (`v2_payments`): `/admin_payment_lookup <telegram_user_id> [limit]`",
        "admin_payment_lookup_empty": "هیچ ردیف پرداختی برای این کاربر نیست.",
        "admin_payment_lookup_title": "پرداخت‌ها (جدیدترین اول):\n",
        "admin_payment_status_hint": "به‌روزرسانی وضعیت یک ردیف: `/admin_payment_status <payment_id> <status> [ref_id]`",
        "admin_wizard_payment_id_ask": "شناسه عددی payment_id را بفرست:",
        "admin_wizard_payment_not_found": "پرداخت `{id}` پیدا نشد.",
        "admin_wizard_payment_status_ask": "وضعیت را بفرست ({statuses}) و اختیاری ref_id:",
        "admin_wizard_payment_status_done": "OK: payment `{payment_id}` → `{status}`{grant}",
        "admin_wizard_clear_prefs_done": "prefs کاربر `{target}` پاک شد.",
        "admin_reconcile_billing_hint": "انقضای ردیف‌های قدیمی pending/initiated: `/admin_reconcile_billing`",
        "admin_reconcile_billing_result": "Reconcile: منقضی‌شده `{expired}`، اسکن‌شده `{scanned}`.",
        "purchase_stub_started": (
            "💳 درخواست خرید ثبت شد.\n\n"
            "کد پیگیری: {payment_id}\n"
            "پس از تأیید پرداخت، پلن Pro فعال می‌شود.\n"
            "وضعیت مصرف: /usage"
        ),
        "purchase_stub_started_admin": (
            "💳 خرید تست (BILLING_STUB_CHECKOUT)\n\n"
            "ردیف v2_payments ساخته شد.\n"
            "• payment_id: {payment_id}\n"
            "• authority: {authority}\n\n"
            "برای اعمال پرو: POST …/v2_payment_event یا /admin_payment_status <id> paid"
        ),
        "purchase_gateway_started": (
            "💳 پرداخت زرین‌پال — Pro سی‌روزه\n\n"
            "۱) روی دکمه «پرداخت» بزن\n"
            "۲) در زرین‌پال پرداخت را کامل کن\n"
            "۳) پس از تأیید، پلن Pro خودکار فعال می‌شود و پیام می‌گیری\n\n"
            "کد پیگیری: {payment_id}\n"
            "لینک: {pay_url}"
        ),
        "btn_open_pay_url": "💳 پرداخت در زرین‌پال",
        "purchase_gateway_error": "خطای درگاه پرداخت: {error}",
        "toolkit_network_disabled": "ابزارهای شبکه فعلاً در دسترس نیست.",
        "toolkit_network_disabled_admin": "ابزارهای شبکه خاموش است — TOOLKIT_NETWORK_LIGHT را در .env روشن کن.",
        "toolkit_utility_disabled": "این ابزار فعلاً در دسترس نیست.",
        "toolkit_utility_disabled_admin": "ابزارهای متنی خاموش است — TOOLKIT_UTILITY_LIGHT را در .env روشن کن.",
        "toolkit_quota_exceeded": (
            "سهمیهٔ روزانهٔ ابزار تمام شد ({used}/{limit}). فردا دوباره امتحان کنید."
        ),
        "toolkit_dns_usage": "استفاده: `/dns <hostname>` — مثال: `/dns example.com`",
        "toolkit_dns_result": "`{host}`:\n{ips}",
        "toolkit_dns_error": "DNS برای `{host}`:\n{error}",
        "toolkit_myip_result": "IP خروجی سرور (اینترنت):\n`{ip}`",
        "toolkit_myip_error": "خطا در گرفتن IP:\n{error}",
        "toolkit_ping_usage": "استفاده: `/ping <host> [port]` — پیش‌فرض پورت 443 (TCP). مثال: `/ping example.com 80`",
        "toolkit_ping_result": "TCP `{host}:{port}` ≈ `{ms}` ms",
        "toolkit_ping_error": "`{host}:{port}` — {error}",
        "toolkit_ipinfo_usage": "استفاده: `/ipinfo <ip>`",
        "toolkit_ipinfo_send_only": "IP یا آدرس را بفرست:",
        "toolkit_ipinfo_result": "{data}",
        "toolkit_ipinfo_error": "IP info ناموفق: {error}",
        "toolkit_whois_usage": "استفاده: `/whois <domain-or-ip>`",
        "toolkit_whois_send_only": "آدرس/دامین یا IP را بفرست:",
        "toolkit_whois_result": "{data}",
        "toolkit_whois_error": "whois/RDAP ناموفق: {error}",
        "toolkit_myid_result": "User ID: `{user_id}`\nUsername: `{username}`\nChat ID: `{chat_id}`",
        "toolkit_gsearch_usage": "جستجوی گوگل فعلاً در دسترس نیست.",
        "toolkit_gsearch_usage_admin": "استفاده: /gsearch <query> یا /gisearch <query>\nنیازمند env: GOOGLE_CSE_API_KEYS و GOOGLE_CSE_ID",
        "toolkit_gsearch_send_only": "عبارت جستجو را بفرست:",
        "toolkit_gisearch_send_only": "عبارت جستجوی تصویر را بفرست:",
        "toolkit_gsearch_result": "{data}",
        "toolkit_gsearch_error": "جستجوی گوگل ناموفق: {error}",
        "toolkit_md5_usage": "استفاده: `/md5 <متن>` — MD5 روی UTF-8",
        "toolkit_md5_result": "`{digest}`",
        "toolkit_sha256_usage": "استفاده: `/sha256 <متن>`",
        "toolkit_sha256_result": "`{digest}`",
        "toolkit_b64e_usage": "استفاده: `/b64e <متن>` — Base64 استاندارد",
        "toolkit_b64e_result": "`{data}`",
        "toolkit_b64d_usage": "استفاده: `/b64d <رشته Base64>`",
        "toolkit_b64d_result": "{data}",
        "toolkit_b64d_error": "decode ناموفق: {error}",
        "toolkit_input_truncated": "(ورودی به سقف ۱۲۰۰۰ نویسه بریده شد.)",
        "toolkit_dns_send_only": "نام دامنه یا IP را بفرست:",
        "toolkit_ping_send_only": "هاست را بفرست (پورت اختیاری است؛ پیش‌فرض 443 و 80).",
        "btn_tool_http_headers": "📬 HTTP Headers",
        "btn_tool_website_status": "🌐 وضعیت سایت",
        "btn_tool_port_check": "🔌 Port Check",
        "btn_tool_subnet": "📡 Subnet Calc",
        "btn_tool_blacklist": "🛡 Blacklist",
        "btn_tool_ssl": "🔒 SSL Check",
        "toolkit_http_headers_send_only": "آدرس URL را بفرست (مثلاً example.com)",
        "toolkit_website_status_send_only": "آدرس سایت را بفرست",
        "toolkit_port_ask_host": "آدرس host یا IP را بفرست:",
        "toolkit_port_ask_port": "شماره پورت را بفرست (مثلاً ۸۰ یا ۴۴۳):",
        "toolkit_port_check_send_only": "هاست و پورت را بفرست: `google.com 443`",
        "toolkit_subnet_send_only": "شبکه CIDR بفرست: `192.168.1.0/24`",
        "toolkit_blacklist_send_only": "IP را برای بررسی بلک‌لیست بفرست",
        "toolkit_ssl_send_only": "دامنه را برای بررسی SSL بفرست",
        "toolkit_net_error": "خطا: {error}",
        "cf_menu_connected": "☁️ Cloudflare متصل است ✅\nاز دکمه‌های زیر استفاده کنید.",
        "cf_quick_help": "راهنما:\n• «وضعیت CF» — اعتبار توکن\n• «دامنه‌ها» — لیست zone\n• «DNS رکوردها» — `/cf_dns <zone_id>`\n• قطع: «قطع Cloudflare»",
        "toolkit_md5_send_only": "متن را برای MD5 بفرست.",
        "toolkit_sha256_send_only": "متن را برای SHA256 بفرست.",
        "toolkit_b64e_send_only": "متن را برای Base64 encode بفرست.",
        "toolkit_b64d_send_only": "رشته Base64 را برای decode بفرست.",
        "toolkit_myip_server_fallback": "IP خروجی فعلی: {ip}\n\nبرای دیدن IP واقعی دستگاه خودت، Mini App باید فعال باشد. اگر فعال نیست با پشتیبانی هماهنگ کن.",
        "toolkit_myip_server_fallback_admin": "IP خروجی سرور: {ip}\n\nبرای IP واقعی کاربر، MINIAPP_BASE_URL را در .env تنظیم کن.",
        "miniapp_myip_open": "ابزارهای مرورگر (IP واقعی شما، DNS، تأخیر شبکه، رمز و …) — دکمه‌ها را بزن:",
        "btn_open_myip_app": "📍 IP من",
        "btn_open_miniapp_hub": "🧰 مرکز ابزار Mini App",
        "miniapp_setup_hint": (
            "ابزارهای مرورگر فعلاً در دسترس نیست.\n"
            "لطفاً بعداً دوباره امتحان کن یا با پشتیبانی در تماس باش."
        ),
        "miniapp_setup_hint_admin": (
            "Mini App فعال نیست.\n"
            "در .env مقدار MINIAPP_BASE_URL (HTTPS عمومی تا پوشه web/) را تنظیم کن.\n"
            "راهنما: README → Telegram Mini App."
        ),
        "media_pick_dest": "مقصد ارسال فایل را انتخاب کن:",
        "media_dest_session_expired": "انتخاب منقضی شد — فایل را دوباره بفرست.",
        "inline_main_title": "میان‌بر منو — بخش را انتخاب کن (ادامه با دکمه‌های پایین صفحه):",
        "inline_world_menu": "🌍 بازار و آب‌وهوا",
        "inline_world_title": "بازار، ارز، آب‌وهوا و هشدارها",
        "btn_world_weather": "🌤 آب‌وهوا",
        "btn_world_time": "🕒 ساعت جهانی",
        "btn_world_calendar": "📅 تقویم",
        "btn_world_age": "🎂 سن",
        "btn_world_currency": "🧮 ماشین‌حساب ارز",
        "btn_world_earthquake": "🌋 زلزله",
        "btn_world_rss": "➕ افزودن فید",
        "btn_world_rss_list": "📋 فیدها",
        "weather_ask_city": "نام شهر را بفرست (مثلاً Tehran):",
        "timezone_ask_place": "نام شهر یا منطقه زمانی را بفرست (مثلاً Tehran یا Asia/Tehran):",
        "age_ask_date": "تاریخ تولد را بفرست (YYYY/MM/DD میلادی یا شمسی):",
        "fx_calc_ask": "مبلغ و واحد را آزاد بنویس، مثلاً:\n`100000 تومان` · `50 دلار` · `1 سکه امامی`\nیا از دکمه‌های آماده / اخیر استفاده کن:",
        "currency_ask_amount": "مبلغ را بفرست (عدد) یا از دکمه‌های سریع استفاده کن:",
        "currency_ask_pair": "ارز مبدأ و مقصد را مرحله‌به‌مرحله می‌گیریم.",
        "currency_bad_amount": "مبلغ نامعتبر است.",
        "rss_ask_url": "آدرس فید RSS/Atom را بفرست:",
        "rss_bad_url": "آدرس http/https معتبر بفرست.",
        "rss_added": "فید #{feed_id} ذخیره شد.",
        "rss_push_ask": "اعلان فوری برای آیتم‌های جدید؟ (digest روزانه هم برای فیدهای با پوش فعال است)",
        "rss_push_on": "🔔 اعلان روشن",
        "rss_push_off": "🔕 اعلان خاموش",
        "rss_view_now": "👁 مشاهده",
        "rss_push_enabled": "اعلان فعال شد.",
        "rss_push_disabled": "اعلان غیرفعال شد.",
        "rss_not_found": "فید پیدا نشد.",
        "rss_list_empty": "فیدی ثبت نشده. از «➕ افزودن فید» یا مدیریت فیدها استفاده کن.",
        "rss_list_title": "فیدهای شما:",
        "rss_push_new": "📰 آیتم جدید: {label}",
        "world_error": "خطا: {detail}",
        "world_digest_title": "📰 خلاصه روزانه فیدها — {date}",
        "btn_main_feed": "📰 فید خوان",
        "btn_feed_reader": "📰 مدیریت فیدها",
        "btn_feed_list": "📋 لیست فیدها",
        "btn_feed_add": "➕ افزودن فید",
        "btn_feed_help": "ℹ️ راهنمای فید",
        "btn_plan_compare": "📊 مقایسه پلن‌ها",
        "feed_section_opened": (
            "📰 فیدخوان\n\n"
            "RSS، YouTube و X/Twitter را دنبال کن.\n"
            "➕ افزودن فید — لینک کانال/فید را بفرست\n"
            "📋 فیدها — لیست، مشاهده و اعلان push\n"
            "❓ راهنما — نکات فرمت و سهمیه"
        ),
        "feed_help_body": (
            "📰 راهنمای Feed Reader\n"
            "• لینک RSS، کانال YouTube یا حساب X را بفرست\n"
            "• Push: اعلان فوری آیتم جدید (طبق پلن)\n"
            "• Digest: خلاصه روزانه تهران برای فیدهای انتخابی\n"
            "• /cancel برای لغو ویزارد"
        ),
        "feed_quota_line": "سهمیه فید: {used}/{limit}",
        "feed_page_prev": "‹ قبلی",
        "feed_page_next": "بعدی ›",
        "feed_digest_on": "📰 خلاصه روزانه: روشن",
        "feed_digest_off": "📰 خلاصه روزانه: خاموش",
        "feed_digest_enabled": "خلاصه روزانه روشن شد",
        "feed_digest_disabled": "خلاصه روزانه خاموش شد",
        "feed_push_plan_blocked": "پلن فعلی اجازه push ندارد. ارتقا بده یا digest را روشن کن.",
        "feed_resolve_failed": "نتوانستم این آدرس را به فید تبدیل کنم: {url}",
        "world_quota_exceeded": "سقف ابزارهای جهان امروز پر است ({used}/{limit}). فردا یا با ارتقای پلن دوباره امتحان کن.",
        "plan_compare_title": "📊 مقایسه پلن‌ها",
        "feed_menu_title": "📰 Feed Reader\nRSS · YouTube · X/Twitter\nافزودن فید، اعلان push، یا مشاهده دستی.",
        "feed_digest_hint": "پوش = اعلان فوری · digest = خلاصه روزانه تهران (قابل تنظیم جداگانه برای هر فید).",
        "feed_digest_schedule": "ساعت خلاصه روزانه: حدود {hour}:00 به وقت تهران.",
        "feed_empty_state": (
            "هنوز فیدی نداری.\n"
            "➕ افزودن فید را بزن و آدرس RSS، یوتیوب یا X را بفرست.\n"
            "بعد می‌توانی push یا خلاصه روزانه را برای هر فید جدا روشن کنی."
        ),
        "payment_granted_dm": (
            "✅ پرداخت تأیید شد.\n"
            "پلن {tier} برای {days} روز فعال شد.\n"
            "جزئیات: /usage"
        ),
        "payment_expiry_soon_dm": (
            "⏰ پلن {tier} تا حدود {days_left} روز دیگر منقضی می‌شود.\n"
            "برای تمدید: /purchase · مقایسه: /plan_compare"
        ),
        "feed_ask_url": (
            "آدرس فید یا صفحه را بفرست:\n"
            "• RSS/Atom مستقیم\n"
            "• `youtube.com/@handle` یا `channel/UC…` یا پلی‌لیست\n"
            "• `x.com/username` یا `twitter.com/username`"
        ),
        "feed_added": "فید #{feed_id} ({kind}) ذخیره شد.",
        "feed_already_added": "این فید از قبل ذخیره شده (#{feed_id}).",
        "feed_limit_reached": "سقف تعداد فید ({limit}) پر شده. یکی را حذف کن یا پلن را ارتقا بده.",
        "feed_fetch_failed": "فید باز نشد: {detail}\nURL: {url}",
        "feed_delete": "🗑 حذف فید",
        "feed_deleted": "فید حذف شد.",
        "feed_add_btn": "➕ افزودن فید",
        "btn_tool_password": "🔑 پسورد",
        "btn_tool_rev_dns": "↩️ Reverse DNS",
        "btn_tool_mac": "🔌 MAC Vendor",
        "btn_tool_email": "✉️ Email Check",
        "btn_tool_url_expand": "🔗 باز کردن URL",
        "btn_tool_timestamp": "🕐 Timestamp",
        "btn_tool_lorem": "📝 Lorem",
        "toolkit_password_result": "رمز پیشنهادی:\n`{password}`",
        "toolkit_rev_dns_send_only": "IP را برای Reverse DNS بفرست.",
        "toolkit_mac_send_only": "آدرس MAC را بفرست (مثلاً `AA:BB:CC:DD:EE:FF`):",
        "toolkit_email_send_only": "آدرس ایمیل را بفرست:",
        "toolkit_url_expand_send_only": "URL کوتاه‌شده را بفرست.",
        "toolkit_timestamp_send_only": "عدد Unix یا تاریخ `YYYY-MM-DD HH:MM:SS` بفرست.",
        "quota_parallel_msg": "سقف کارهای همزمان در صف پر است (`{cur}` / `{maxp}`). بعد از اتمام یکی دوباره تلاش کن.",
        "quota_day_msg": "سقف حجم روزانه پر است.\nاین کار ~{need} MB است؛ حدود {left} MB امروز باقی مانده.\nبرای ارتقا: /purchase",
        "quota_month_msg": "سقف حجم ماهانه پر است.\nاین کار ~{need} MB است؛ حدود {left} MB این ماه باقی مانده.\nبرای ارتقا: /purchase",
        "quota_file_cap_msg": "حجم این کار از سقف هر فایل بیشتر است (حداکثر `{max_mb}` MB، این فایل ~{need_mb} MB).",
        "quota_unknown": "سقف مجاز پر است.\n/usage را ببین یا برای ارتقا /purchase را بزن.",
        "usage_panel": (
            "📊 مصرف و محدودیت\n\n"
            "پلن\n"
            "• {tier} (انقضا: {expires})\n\n"
            "انتقال\n"
            "• امروز: ~{day_used} / {day_cap} MB\n"
            "• این ماه: ~{month_used} / {month_cap} MB\n"
            "• حداکثر فایل: {max_file} MB\n"
            "• همزمان: {parallel} / {max_parallel}\n\n"
            "ابزارها\n"
            "• ابزارک روزانه: {toolkit_used_cap}\n"
            "• جهان/ارز روزانه: {world_used_cap}\n"
            "• فیدها: {feed_used}/{feed_cap} (push: {feed_push})\n\n"
            "ارتقای پلن: /purchase · مقایسه: /plan_compare"
        ),
        "usage_disabled_hint": "سهمیه‌گذاری برای این ربات فعلاً غیرفعال است.",
        "usage_disabled_hint_admin": "سهمیه‌گذاری با DISABLE_USAGE_LIMITS خاموش است (فقط محدودیت env در صورت تنظیم).",
        "batch_raw_hint": "جمع حجم خام فعلی: ~`{raw_mb}` MB ({n} فایل). بعد از ZIP ممکن است کمی فرق کند.",
        "direct_url_use_sendlink": "برای لینک از دکمه یا دستور `/sendlink` استفاده کن.",
        "direct_url_use_link_menu": "برای دانلود لینک/ویدیو از منوی اصلی «🔗 لینک / ویدیو» استفاده کن.",
        "purchase_info_body": (
            "💳 خرید / ارتقای پلن\n\n"
            "• خرید آنلاین Pro (۳۰ روز): /purchase\n"
            "• مقایسه پلن‌ها: /plan_compare\n"
            "• وضعیت مصرف: /usage\n\n"
            "برای پلن بالاتر (Star) با پشتیبانی هماهنگ کن."
        ),
        "purchase_info_body_admin": (
            "💳 خرید / ارتقای پلن (ادمین)\n\n"
            "• خرید Pro: /purchase (زرین‌پال)\n"
            "• مقایسه: /plan_compare\n"
            "• اعطای دستی: /admin_tier <uid> free|pro|star [days]\n"
            "• یا tools/grant_plan.py روی سرور"
        ),
        "rubika_update_hint": (
            "اگر بعد از به‌روزرسانی سرور روبیکا «قطع» شد: یک‌بار `/rubika_connect` بزن. "
            "فایل‌های session از rsync پاک نمی‌شوند؛ خطای 502 از سرورهای روبیکا هم رایج است."
        ),
    },
    "en": {
        "welcome": (
            "Hi 💙 Welcome to TelegramToolsBot\n\n"
            "A full tools suite in Telegram:\n"
            "📁 Transfer — Rubika · Bale · Drive · SSH · direct links\n"
            "🧰 Tools — network/IP · hash/Base64 · calculators\n"
            "🌍 World — weather · FX/gold board · convert · quakes · calendar\n"
            "📰 Feed Reader — RSS / YouTube / X with push & digest\n"
            "☁️ Cloudflare — personal DNS · 📋 Account — plan & usage\n\n"
            "Each menu section shows its own short guide.\n"
            "/menu · /help · /lang · /world_gold"
        ),
        "onboard_next_steps": "Where do you want to start?",
        "onboard_checklist": "Optional connections:\n{rubika} Rubika\n{bale} Bale\n{drive} Google Drive",
        "btn_onboard_rubika": "💬 Rubika",
        "btn_onboard_transfer": "📁 Transfer",
        "btn_onboard_tools": "🧰 Tools",
        "btn_onboard_feed": "📰 Feed",
        "btn_onboard_world": "🌍 World",
        "btn_onboard_plan": "📋 Plan",
        "btn_buy_pro_cta": "💳 Upgrade to Pro",
        "quota_soft_warn": (
            "⚠️ You are nearing your quota.\n"
            "Today ~{day_pct}% · This month ~{month_pct}%\n"
            "Upgrade for more room."
        ),
        "menu_intro": (
            "🏠 Main menu\n\n"
            "📁 **Transfer** — send & move files\n"
            "🧰 **Tools** — independent utilities\n"
            "📋 **Account** — plan & queue\n"
            "⚙️ **Settings** — direct mode & network\n\n"
            "Use «🏠 Main menu» or «◀️» to go back."
        ),
        "plan_menu_opened": (
            "📋 Account & plan\n"
            "Plan, usage, purchase, and queue."
        ),
        "pick_lang": "Choose language:",
        "lang_saved": "Language saved.",
        "transfer_menu_title": (
            "📁 File transfer\n\n"
            "Send media or connect a destination first.\n"
            "Rubika · Bale · Drive · SSH · Files/queue"
        ),
        "toolkit_menu_title": (
            "🧰 Tools\n\n"
            "Separate from file transfer — pick a category:\n"
            "🌐 Network & IP · 🔐 Hash & Base64 · 🧮 Calculators"
        ),
        "toolkit_network_menu_title": (
            "🌐 Network tools\n\n"
            "• Mini App = from your device/network (real IP, latency, DoH)\n"
            "• Keyboard buttons = from bot server (TCP ping, SSL, port, …)\n"
            "After picking a server tool, send the value (e.g. `/dns google.com`)."
        ),
        "toolkit_network_miniapp_hint": (
            "📱 Mini App shortcuts — tools that run on your device:\n"
            "(real IP, browser reach/ping, DoH DNS, utilities)\n"
            "For TCP ping / SSL / port from the bot VPS use the reply keyboard or «Server ping»."
        ),
        "btn_miniapp_reach_device": "📡 Device ping",
        "btn_miniapp_reach_server": "🖥 Server ping",
        "btn_miniapp_utils": "🧰 Utilities",
        "toolkit_crypto_menu_title": "🔐 Hash & Base64\ne.g. `/md5 text` or `/b64e hello`",
        "toolkit_zip_menu_title": "📦 Create ZIP file\nSend files, then ZIP and send to destination.",
        "rubika_menu_title": "💬 Rubika\nConnect and check your account.",
        "bale_menu_title": "📨 Bale\nYour bot & destination — `/bale_connect`",
        "drive_menu_title": "☁️ Google Drive\n`/drive_connect` then send files.",
        "ssh_menu_title": "🖥 SSH servers\nYour servers. Upload: `/ssh_put id path`",
        "files_menu_title": "📦 Files, ZIP & queue\nRubika must be linked.",
        "settings_menu_title": "📤 Direct send\nOnly one destination at a time — connect it before enabling.",
        "direct_send_menu_title": "📤 Direct send",
        "admin_menu_title": "🛡 Admin",
        "admin_users_menu_title": "👥 User management\nUse My ID or the user's message to get a Telegram ID first.",
        "admin_billing_menu_title": "💳 Billing management",
        "admin_maintenance_menu_title": "🧹 Maintenance and system status",
        "admin_denied": "You are not an admin.",
        "no_worker_events": "Worker log file not found yet.",
        "no_recent_jobs": "No recent task_done/task_failed for this chat.",
        "recent_jobs_title": "Recent jobs (worker):",
        "btn_main_transfer": "📤 Send files",
        "btn_main_network": "🌐 Network & IP",
        "btn_main_crypto": "#️⃣ Hash & Base64",
        "btn_main_calc": "🧮 Calculators",
        "btn_main_toolkit": "🧰 More tools",
        "btn_main_miniapp": "📱 Mini App",
        "btn_main_settings": "📤 Direct send",
        "btn_main_link_direct": "⬇️ Download from link",
        "btn_main_cloudflare": "☁️ مدیریت Cloudflare",
        "btn_main_ssh": "🖥 Server Management via Bot",
        "btn_main_help": "❓ Help",
        "btn_main_plan_section": "📋 Account & plan",
        "btn_main_admin": "🛡 Admin",
        "btn_back_main": "Back",
        "btn_back_transfer": "Back",
        "btn_back_toolkit": "Back",
        "btn_transfer_rubika": "💬 Rubika",
        "btn_transfer_bale": "📨 Bale",
        "btn_transfer_drive": "☁️ Drive",
        "btn_transfer_ssh": "🖥 Server Management via Bot",
        "btn_transfer_files": "📦 Files & Queue",
        "btn_rub_connect": "🔗 Connect",
        "btn_rub_status": "✅ Status",
        "btn_zip_start": "📥 Start ZIP",
        "btn_zip_end": "✅ End ZIP",
        "btn_send_content": "✉️ Text / link",
        "btn_queue": "📋 Queue",
        "btn_clear_all": "🗑 Clear all",
        "btn_toolkit_network": "🌐 Network & IP",
        "btn_toolkit_crypto": "🔐 Hash & Base64",
        "btn_toolkit_calc": "🧮 Calculators",
        "calc_cat_finance_title": "💰 Finance",
        "calc_cat_numbers_title": "🔢 Numbers",
        "calc_cat_convert_title": "🔄 Convert",
        "calc_cat_math_title": "∑ Math",
        "calc_cat_text_title": "📝 Text",
        "calc_cat_other_title": "🧩 Other",
        "toolkit_calc_menu_title": (
            "🧮 Calculators\n"
            "Independent tools (kitset-inspired). Each button shows its own input guide.\n"
            "Percent / loan / deposit / rial↔toman · units · plate/NID · dates · math"
        ),
        "btn_calc_cat_finance": "💰 Finance",
        "btn_calc_cat_numbers": "🔢 Numbers",
        "btn_calc_cat_convert": "🔄 Convert",
        "btn_calc_cat_math": "∑ Math",
        "btn_calc_cat_text": "📝 Text",
        "btn_calc_cat_other": "🧩 Other",
        "btn_back_calc": "Back",
        "btn_calc_bmi": "⚖ BMI",
        "btn_calc_compound": "📈 Compound",
        "btn_calc_log": "㏒ Log",
        "btn_calc_pct_error": "% Error",
        "btn_calc_linear": "𝒙 Linear eq",
        "btn_calc_quadratic": "𝒙² Quadratic",
        "btn_calc_add_days": "📅 Add days",
        "btn_calc_percent": "% Percent",
        "btn_calc_loan": "🏦 Loan EMI",
        "btn_calc_deposit": "💰 Deposit",
        "btn_calc_rial": "🔄 Rial/Toman",
        "btn_calc_words": "🔤 Number words",
        "btn_calc_unit": "📐 Units",
        "btn_calc_base": "🔢 Base convert",
        "btn_calc_binary": "01 Binary",
        "btn_calc_fuel": "⛽ Fuel",
        "btn_calc_plate": "🚗 Plate city",
        "btn_calc_nid": "🪪 NID city",
        "btn_calc_datediff": "📆 Date diff",
        "btn_calc_dateconv": "🗓 Date convert",
        "btn_calc_random": "🎲 Random",
        "btn_calc_mean": "📊 Mean",
        "btn_calc_power": "⬆ Power",
        "btn_calc_sqrt": "√ Sqrt",
        "btn_calc_fact": "! Factorial",
        "btn_calc_prime": "🔢 Prime",
        "btn_calc_ielts": "🎓 IELTS",
        "btn_calc_cig": "🚬 Cigarette",
        "btn_calc_rect": "▭ Rectangle",
        "btn_calc_square": "▢ Square",
        "btn_calc_case": "Aa Case",
        "btn_calc_wordcount": "📝 Word count",
        "calc_error": "Error: {detail}",
        "calc_hint_percent": "Percent\n`part whole` or `of value pct` or `chg old new` or `inc|dec value pct`",
        "calc_hint_loan": "Loan EMI\n`principal annual_rate_pct months`",
        "calc_hint_deposit": "Deposit interest\n`principal annual_rate_pct months`",
        "calc_hint_rial": "Rial↔Toman\n`amount toman` or `amount rial`",
        "calc_hint_words": "Persian number words\nSend an integer.",
        "calc_hint_unit": "Unit convert\n`kind amount from to` e.g. `length 10 km m`",
        "calc_hint_base": "Base convert\n`value from_base to_base`",
        "calc_hint_binary": "Binary↔text\n`to text` or `from 0100...`",
        "calc_hint_fuel": "Fuel cost\n`km L_per_100 price_per_liter`",
        "calc_hint_plate": "Plate city\nSend 2-digit plate code.",
        "calc_hint_nid": "National ID city\nSend first 3 digits.",
        "calc_hint_datediff": "Date diff\n`YYYY/MM/DD YYYY/MM/DD`",
        "calc_hint_dateconv": "Date convert\n`YYYY/MM/DD` (Gregorian or Solar)",
        "calc_hint_random": "Random\n`count min max`",
        "calc_hint_mean": "Mean\nSpace-separated numbers.",
        "calc_hint_power": "Power\n`base exp`",
        "calc_hint_sqrt": "Sqrt\nSend a number.",
        "calc_hint_fact": "Factorial\nInteger 0..200",
        "calc_hint_prime": "Prime check\nSend an integer.",
        "calc_hint_ielts": "IELTS\n`L R W S`",
        "calc_hint_cig": "Cigarette cost\n`per_day pack_price [pack_size] [days]`",
        "calc_hint_rect": "Rectangle\n`width height`",
        "calc_hint_square": "Square\nSend side length.",
        "calc_hint_case": "Case\n`upper|lower|title text`",
        "calc_hint_wordcount": "Word count\nSend text.",
        "btn_world_markets": "🏛 Boards",
        "btn_world_gold": "🥇 Gold & coins",
        "btn_world_usd": "💵 USD",
        "btn_world_eur": "💶 EUR",
        "btn_world_gbp": "💷 GBP",
        "btn_world_jpy": "💴 JPY",
        "btn_world_majors": "🌍 Major FX",
        "currency_ask_from": "Send source currency (e.g. USD) or tap a button:",
        "currency_ask_to": "Send target currency (e.g. IRR):",
        "world_menu_title": (
            "🌍 World\n\n"
            "Time, weather, and Iran free-market board (Iran free market).\n\n"
            "🌤 Weather · 🕒 Time · 📅 Calendar · 🎂 Age\n"
            "💱 Convert · 📈 FX & Gold board · 🌋 Earthquakes"
        ),
        "btn_toolkit_zip": "📦 Create ZIP file",
        "btn_tool_dns": "🔍 DNS",
        "btn_tool_myip": "📍 My IP",
        "btn_tool_ping": "📡 Ping",
        "btn_tool_ipinfo": "🧭 IP Info",
        "btn_tool_whois": "🧾 Whois",
        "btn_tool_myid": "🆔 My ID",
        "btn_tool_google": "🔎 Google",
        "btn_tool_md5": "#️⃣ MD5",
        "btn_tool_sha256": "🔒 SHA256",
        "btn_tool_b64e": "📤 B64 encode",
        "btn_tool_b64d": "📥 B64 decode",
        "btn_plan_plan": "📊 Plan",
        "btn_plan_usage": "📈 Usage",
        "btn_plan_buy": "💳 Purchase",
        "btn_direct_rubika_on": "🚀 Direct Rubika",
        "btn_direct_bale_on": "📨 Direct Bale",
        "btn_direct_drive_on": "☁️ Direct Drive",
        "btn_direct_rubika_off": "⏸ Off direct Rubika",
        "btn_direct_bale_off": "⏸ Off direct Bale",
        "btn_direct_drive_off": "⏸ Off direct Drive",
        "btn_netstatus": "📶 Network",
        "btn_ssh_list": "📋 Server list",
        "btn_ssh_add_help": "➕ Add server",
        "btn_ssh_put_help": "⬆️ SFTP upload",
        "btn_ssh_get_help": "⬇️ SFTP download",
        "btn_ssh_ls_help": "📂 List path",
        "btn_ssh_del_help": "🗑 Delete server",
        "btn_drive_ls": "📂 List files",
        "btn_drive_download_help": "⬇️ Drive download",
        "btn_admin_panel": "🛡 Panel",
        "btn_admin_users": "👥 Users",
        "btn_admin_billing": "💳 Billing",
        "btn_admin_maintenance": "🧹 Maintenance",
        "btn_back_admin": "Back",
        "btn_admin_version": "🏷 Version",
        "btn_admin_tier_help": "Set tier",
        "btn_admin_bonus_help": "Add quota",
        "btn_admin_clear_prefs_help": "Clear prefs",
        "btn_admin_payment_lookup_help": "Payment lookup",
        "btn_admin_payment_status_help": "Set payment status",
        "btn_admin_reconcile": "Reconcile billing",
        "btn_admin_cleanup": "Cleanup downloads",
        "btn_admin_users_list": "📋 User List",
        "btn_admin_broadcast": "📣 Broadcast",
        "btn_admin_stats": "📊 Stats",
        "btn_admin_service_status": "⚙️ Service status",
        "btn_admin_tail_logs": "📜 Tail logs",
        "btn_admin_job_help": "🔎 Job lookup",
        "btn_admin_bc_all": "All",
        "btn_admin_bc_known": "Known chats",
        "btn_admin_bc_new7": "New 7d",
        "btn_admin_bc_guest": "Tier guest",
        "btn_admin_bc_free": "Tier free",
        "btn_admin_bc_pro": "Tier pro",
        "btn_admin_bc_star": "Tier star",
        "btn_admin_bc_expiring": "Expiring soon",
        "btn_admin_bc_expired": "Expired",
        "btn_admin_bc_inactive": "Inactive 30d",
        "admin_broadcast_menu_title": "📣 Admin broadcast\nPick a segment, then send the message text and confirm with yes.",
        "admin_stats_body": (
            "📊 User stats\n"
            "Activity users: {users_total}\n"
            "Known chats: {known_chats}\n"
            "New 7d: {new_7d}\n"
            "Inactive 30d: {inactive_30d}\n"
            "Expiring 7d: {expiring_7d}\n"
            "Expired: {expired}\n"
            "Tiers — guest:{tier_guest} free:{tier_free} pro:{tier_pro} star:{tier_star}"
        ),
        "admin_broadcast_ask_body": "Segment `{segment}` ({label}) — audience: {count}\nSend the broadcast text (or cancel).",
        "admin_broadcast_body_empty": "Message body is empty. Send text or cancel.",
        "admin_broadcast_confirm": "Send to {count} users (segment {segment})?\n\nPreview:\n{preview}\n\nConfirm: yes · Cancel: no",
        "admin_broadcast_confirm_hint": "Send yes or no.",
        "admin_broadcast_cancelled": "Broadcast cancelled.",
        "admin_broadcast_empty": "Audience or body is empty.",
        "admin_broadcast_sending": "Sending to {total} users…",
        "admin_broadcast_progress": "Progress {done}/{total} · ok {sent} · fail {failed}",
        "admin_broadcast_done": "Broadcast finished.\nSegment: {segment}\nOK: {sent} · fail: {failed} · total: {total}",
        "admin_service_status_body": "⚙️ Service status\n\n{detail}",
        "admin_tail_logs_body": "📜 Recent logs\n\n{detail}",
        "admin_job_ask": "Send a job_id (or cancel).",
        "admin_job_not_found": "Job not found: {job_id}",
        "feed_added_empty_warning": "Feed saved but currently has no items. Try push/view later.",
        "feed_err_no_entries": "Feed parsed but has no items",
        "feed_err_parse_failed": "Could not parse feed structure",
        "feed_err_http_error": "HTTP error fetching feed",
        "feed_err_timeout": "Timed out fetching feed",

        "admin_users_list_empty": "No users recorded yet.",
        "btn_cf_connect": "🔐 CF Connect",
        "btn_cf_status": "✅ CF Status",
        "btn_cf_zones": "🌐 Zones",
        "btn_cf_dns_help": "📋 DNS records",
        "btn_cf_disconnect": "❌ CF Disconnect",
        "btn_inline_refresh": "Refresh",
        "btn_inline_pending": "Pending",
        "btn_inline_failed": "Failed",
        "btn_inline_clear": "Clear my queue",
        "btn_inline_recent": "Recent jobs",
        "btn_inline_faildetail": "Error details",
        "queue_kb_refresh": "Refreshed",
        "queue_kb_cleared": "Queue cleared",
        "directmode_usage": (
            "Direct send (one target):\n"
            "`/directmode rubika on` · `/directmode bale on` · `/directmode drive on`\n"
            "Off: `/directmode rubika off` (or bale/drive)\n"
            "Legacy: `/directmode on` = Rubika"
        ),
        "direct_on_rubika": "Direct send to Rubika enabled.",
        "direct_on_bale": "Direct send to Bale enabled.",
        "direct_on_drive": "Direct send to Google Drive enabled.",
        "direct_on_explain": (
            "Direct send is enabled.\n"
            "From now on, any file/text you send will be delivered directly to the selected destination."
        ),
        "direct_switched_off": "Direct send to {old} disabled. Enabling the new target…",
        "net_reason_ok": "OK",
        "direct_off": "Direct send disabled.",
        "direct_off_wrong_target": "Active target is `{active}` — turn that off first.",
        "direct_url_only_for_bale_drive": "Bale/Drive direct mode supports links/videos only.",
        "link_menu_opened": (
            "🔗 Link / video download\n"
            "Send an HTTP(S) or YouTube link.\n"
            "Metadata first, then pick destination.\n"
            "No server download until destination is connected."
        ),
        "link_send_url": "Send a valid http/https or YouTube link.",
        "link_probing": "Checking link (no download yet)…",
        "link_probe_summary": "📎 `{title}`\nType: {link_type}\nApprox. size: {size}",
        "link_size_unknown": "unknown",
        "link_type_direct": "direct link",
        "link_type_youtube": "YouTube",
        "link_type_magnet": "torrent",
        "link_pick_dest": "Choose destination:",
        "link_pick_quality": "Choose quality:",
        "link_dest_telegram": "Telegram (this chat)",
        "link_sending_telegram": "Sending file in this chat…",
        "btn_clear_chat": "🧹 Clear chat",
        "clear_chat_confirm": "Bot messages in this chat will be deleted.\nYour plan and settings stay intact.\nTap the button below to confirm.",
        "clear_chat_done": "Chat cleared ✅ ({n} bot messages deleted). Plan/settings unchanged.",
        "clear_chat_done_full": "Chat cleared ✅ ({n} bot msgs, {u} user msgs if allowed). Plan kept.",
        "quake_pick_mag": "Pick minimum earthquake magnitude (Richter):",
        "alerts_ask_quake_mag": "Pick minimum Richter for quake alerts:",
        "alerts_quake_added_ok": "Quake alert saved ✅ (min {mag} Richter)",
        "clear_chat_none": "No deletable bot messages found yet (new bot replies after this update are tracked).",
        "btn_world_alerts": "🔔 Alerts",
        "alerts_paid_only": "Scheduled alerts are Pro/Star only.",
        "alerts_pick_kind": "Pick an alert type:",
        "alerts_ask_fx_asset": "Send FX code (e.g. USD or EUR):",
        "alerts_ask_gold_asset": "Send gold asset (e.g. SEKEE or GOLD18):",
        "alerts_ask_weather_city": "Send city name for weather:",
        "alerts_ask_quake_city": "Send city/region filter for quakes (or `all`):",
        "alerts_ask_schedule": "Pick a schedule:",
        "alerts_ask_hour": "Pick send hour (Tehran time):",
        "alerts_ask_spike": "Pick a price-spike threshold (or custom):",
        "alerts_ask_spike_custom": "Send spike threshold % (e.g. 3). Send `-` for schedule-only:",
        "alerts_added_ok": "Alert saved ✅ — you can send a test now.",
        "alerts_add_fail": "Could not save alert: {detail}",
        "alerts_empty": "No alerts yet.",
        "alerts_list_title": "Your alerts (delete / pause / test):",
        "alerts_btn_delete": "🗑",
        "alerts_btn_enable": "▶️",
        "alerts_btn_disable": "⏸",
        "alerts_btn_test": "🧪 Test",
        "alerts_btn_list": "📋 List",
        "alerts_btn_new": "➕ New alert",
        "alerts_btn_mute_24h": "🔇 24h",
        "alerts_btn_mute_7d": "🔇 7d",
        "alerts_btn_unmute": "🔔 Unmute",
        "alerts_muted_24h": "Muted 24h",
        "alerts_muted_7d": "Muted 7 days",
        "alerts_unmuted": "Unmuted",
        "alerts_deleted": "Deleted",
        "alerts_not_found": "Alert not found",
        "alerts_enabled": "Enabled",
        "alerts_disabled": "Paused",
        "alerts_test_sending": "Sending test…",
        "alerts_test_prefix": "🧪 Alert test message",
        "alerts_test_fail": "Test failed: {detail}",
        "btn_calc_digits": "123 Digits FA/EN",
        "calc_ask_digits": "Send text with numbers to convert Persian↔English digits:",
        "link_dest_rubika": "Rubika",
        "link_dest_bale": "Bale",
        "link_dest_drive": "Google Drive",
        "link_dest_cancel": "Cancel",
        "link_dest_invalid": "Invalid destination.",
        "link_quality_best": "Best",
        "link_quality_1080": "1080p",
        "link_quality_720": "720p",
        "link_quality_480": "480p",
        "link_quality_audio_only": "Audio only",
        "link_quality_best_set": "Best quality selected. Now pick a destination.",
        "link_need_rubika": "Rubika not connected. `/rubika_connect`",
        "link_probe_unsupported": "Cannot download this link. ({detail})",
        "link_ytdlp_missing": "YouTube needs `yt-dlp` on the server.",
        "link_magnet_unsupported": "Magnet links are not supported yet.",
        "link_session_expired": "Selection expired — send the link again.",
        "link_cancelled": "Cancelled.",
        "link_audio_only": "Audio only",
        "link_quality_set": "Quality {quality}p selected. Now pick a destination.",
        "link_quality_audio_set": "Audio-only mode enabled. Now pick a destination.",
        "link_downloading": "Downloading on server…",
        "link_download_failed": "Download failed: {error}",
        "link_download_done_queue": "Downloaded; queuing upload…",
        "link_media_hint": "This section expects a link/video URL. To send a file, open File transfer and choose a destination.",
        "cf_menu_title": "☁️ Cloudflare\nPer-user API Token. List and create/delete DNS with confirmation.",
        "cf_ask_token": "Send your Cloudflare API token. Recommended: Zone/DNS Read + Edit.",
        "cf_token_invalid": "Invalid Cloudflare token: {detail}",
        "cf_connected_ok": "Cloudflare linked ✅ token status: {detail}",
        "cf_disconnected": "Cloudflare disconnected.",
        "cf_not_connected": "Cloudflare is not linked yet.\nTap the button below to connect.",
        "cf_status_ok": "Cloudflare OK ✅ {detail}",
        "cf_status_bad": "Cloudflare invalid: {detail}",
        "cf_zones_result": "Zones:\n{detail}",
        "cf_dns_usage": "Usage: `/cf_dns <zone_id> [record-name]`\nOr tap DNS and pick a zone.",
        "cf_dns_pick_zone": "Pick a zone to list DNS records:",
        "cf_dns_pick_zone_add": "Pick a zone to create a DNS record:",
        "cf_dns_pick_zone_del": "Pick a zone to delete a DNS record:",
        "cf_dns_pick_record_del": "Pick the DNS record to delete:",
        "cf_dns_ask_type": "Send record type (A, AAAA, CNAME, TXT, MX, …) or /cancel",
        "cf_dns_ask_name": "Send record name (e.g. www or @):",
        "cf_dns_ask_content": "Send record content (IP, CNAME target, TXT, …):",
        "cf_dns_confirm_create": "Create `{type}` `{name}` → `{content}`?\nyes / no",
        "cf_dns_write_ok": "DNS: {detail}",
        "cf_dns_empty": "No records to delete.",
        "cf_dns_del_need_zone": "Pick a zone from the delete DNS menu first.",
        "btn_cf_dns_add": "➕ Add DNS",
        "btn_cf_dns_del": "🗑 Delete DNS",
        "cf_zones_empty": "No zones found for this token.",
        "cf_dns_result": "DNS records:\n{detail}",
        "cf_error": "Cloudflare error: {error}",
        "cf_media_hint": "In Cloudflare menu send only your API token as text. For file uploads use Settings or Transfer.",
        "wizard_cancelled": "Wizard cancelled.",
        "wizard_send_file_hint": "Send a file/document in this step (not text). Cancel: /cancel",
        "bale_ask_chat_id": "Send the Bale destination chat id (numeric or @channel):",
        "newbatch_ok": (
            "ZIP batch started.\n"
            "Send files, then tap «End ZIP» or `/done`."
        ),
        "prompt_sendtext": "Send the text.",
        "prompt_sendlink": "Send the link.",
        "queue_panel": (
            "Queue:\n\n"
            "- Pending in SQLite (all your destinations): `{pending}`\n"
            "- Currently processing (worker): `{processing}`\n"
            "- Failed (global): `{failed}`\n"
            "- Deleted: `{deleted}`\n"
            "- Cancelled: `{cancelled}`\n\n"
            "If upload looks stuck but Pending is `0`, the job left the queue and the worker is busy.\n\n"
            "Use «Clear my queue» to wipe your pending tasks."
        ),
        "queue_processing_none": "`—`",
        "queue_processing_detail": "`{job_id}` type `{task_type}` — `{file}` (~{size})",
        "bale_not_connected": "Bale is not linked yet.\nTap the button below to connect.",
        "bale_ask_token": (
            "📖 How to connect Bale:\n\n"
            "1️⃣ Open Bale app\n"
            "2️⃣ Message @botfather and send `/newbot`\n"
            "3️⃣ Enter bot name and username\n"
            "4️⃣ Send the token you receive here\n\n"
            "The token is stored only for your Telegram account."
        ),
        "bale_token_invalid": "Invalid Bale token: {detail}",
        "bale_token_ok": "Bale bot verified (@{bot}). Send the destination `chat_id`.",
        "bale_chat_id_empty": "chat_id is empty.",
        "bale_chat_invalid": "Bale chat_id check failed: {detail}",
        "bale_connected_ok": (
            "Bale linked ✅ chat: `{chat_id}`\n\n"
            "How to send:\n"
            "• Transfer → Direct send → turn on Bale, then send a file\n"
            "• Or send a file and pick Bale as destination"
        ),
        "bale_already_connected": "Bale already linked. `/bale_disconnect` then `/bale_connect` to replace.",
        "bale_disconnected": "Bale disconnected.",
        "btn_bale_connect": "🔗 Bale Connect",
        "btn_bale_status": "✅ Bale Status",
        "btn_bale_set_chat": "🎯 Bale Set destination",
        "btn_bale_disconnect": "❌ Bale Disconnect",
        "bale_status_no_chat": "Token OK ({detail}). Missing chat_id — continue `/bale_connect`.",
        "bale_status_ok": "Bale: chat_id=`{chat_id}` — {detail}",
        "bale_set_chat_usage": (
            "Send the Bale chat_id.\n"
            "Tip: add the bot to a group, or ask an admin for the numeric chat id."
        ),
        "bale_set_chat_saved": "Bale destination saved: `{chat_id}`",
        "drive_not_connected": (
            "Google Drive is not linked yet.\n"
            "Tap Connect Drive — Google sign-in is the easiest path."
        ),
        "drive_connect_choose": "Choose how to connect Google Drive:",
        "btn_drive_auth_sa": "📄 Service account (JSON)",
        "btn_drive_auth_oauth": "🔐 Sign in with Google",
        "btn_drive_oauth_open": "Open Google sign-in",
        "drive_oauth_start": (
            "1) Tap the button below and sign in with your Google account.\n"
            "2) If you are not redirected to the bot, paste the authorization code here."
        ),
        "drive_oauth_ok_ask_folder": "Google sign-in OK ✅\nSend your Drive folder link or folder ID:",
        "drive_oauth_failed": "Google sign-in failed: {detail}",
        "drive_oauth_code_empty": "Authorization code is empty.",
        "drive_oauth_not_configured": "Google sign-in is not enabled on this server (OAuth env).",
        "drive_ask_sa_json": (
            "📖 Google Drive (2 steps)\n\n"
            "Step 1 — Send the service-account **JSON** as a document.\n"
            "Step 2 — After upload, send your folder link or folder ID."
        ),
        "drive_sa_already_uploaded": "JSON already saved ✅\nShare your folder with:\n`{email}`\n\nNow send the folder link or ID.",
        "drive_share_email_hint": "✅ JSON received.\nShare the Drive folder with (Editor):\n`{email}`",
        "drive_ask_folder_id": "Send the Drive folder URL or folder ID:",
        "drive_folder_empty": "folder_id is empty.",
        "drive_sa_missing_retry": "Service account file missing. Start Drive connect again.",
        "drive_connected_ok": "Drive linked ✅ folder=`{folder_id}`",
        "drive_disconnected": "Drive disconnected.",
        "btn_drive_connect": "🔗 Drive Connect",
        "btn_drive_status": "✅ Drive Status",
        "btn_drive_disconnect": "❌ Drive Disconnect",
        "drive_sa_need_document": "Send the JSON as a document file, not plain text.",
        "drive_sa_need_json": "File name must end with `.json`.",
        "drive_sa_invalid": "Invalid JSON: {error}",
        "drive_status_line": "Drive ({mode}): {ok}\n{detail}",
        "drive_ls_result": "Drive files:\n{detail}",
        "drive_ls_error": "Drive list failed: {error}",
        "ssh_list_empty": "No SSH servers yet. Use the Add server button.",
        "ssh_list_title": "SSH servers:",
        "ssh_list_row": "#{id} · {label}\n  {ssh_user}@{host}:{port}",
        "ssh_add_usage": "Usage: `/ssh_add <label> <host> <port> <user> [password]`\nOr tap «➕ Add server» for a step-by-step wizard.",
        "ssh_wizard_ask_label": "Send a short label for this server (e.g. `vps1`):",
        "ssh_wizard_ask_host": "Send the server host or IP:",
        "ssh_wizard_ask_port": "Send the SSH port (usually `22`):",
        "ssh_wizard_ask_user": "Send the SSH username (e.g. `root`):",
        "ssh_wizard_ask_auth": "Pick an auth method with the buttons below:",
        "ssh_wizard_ask_password": "Send the SSH password:",
        "ssh_wizard_ask_key_paste": "Paste the full PEM private key in one message (from `-----BEGIN` to `-----END`):",
        "ssh_wizard_ask_key_file": "Send the private key file (`.pem` or `.key`) as a **document** (not a photo).",
        "ssh_wizard_bad_port": "Port must be a number from 1 to 65535.",
        "ssh_wizard_key_invalid": "Invalid key: {error}",
        "ssh_op_pick_server": "Pick a server for `{op}`:",
        "ssh_op_ask_path": "Send the remote path for `{op}` (e.g. `/home` or `.`):",
        "ssh_add_ok": "Saved server `{label}` ({host}:{port}).",
        "ssh_put_usage": "Usage: `/ssh_put <server_id> <remote_path>` then send the file",
        "ssh_ls_usage": "Usage: `/ssh_ls <server_id> [remote_path]`",
        "ssh_del_usage": "Usage: `/ssh_del <server_id>`",
        "ssh_put_await_file": "Remote path saved. Send the file in Telegram now.",
        "ssh_server_not_found": "SSH server not found.",
        "ssh_auth_missing": "No password/key for this server. Use «➕ Add server» to register again.",
        "ssh_ls_result": "Listing `{path}`:\n{detail}",
        "ssh_ls_error": "SSH ls failed: {error}",
        "ssh_del_ok": "SSH server `#{id}` deleted.",
        "bale_active_hint": "After `/bale_connect`, send a file here to upload via your Bale bot (~20 MB max).",
        "drive_active_hint": "After `/drive_connect`, send a file to upload to your Drive. Download: `/drive_download <id>`",
        "drive_download_usage": "Usage: `/drive_download <google_drive_file_id>`",
        "drive_download_send_only": "Send a Google Drive file id:",
        "ssh_get_usage": "Usage: `/ssh_get <server_id> <remote_path>`",
        "help_short": (
            "📖 Full bot guide\n\n"
            "🏠 /menu — main menu\n"
            "📤 Send files — Rubika / Bale / Drive / SSH / direct\n"
            "⬇️ Download from link — direct/image/PDF/video (YouTube needs server cookies)\n"
            "🌐 Network & IP — DNS, Ping, Whois, IP Info, port, SSL\n"
            "#️⃣ Hash & Base64 — MD5, SHA256, Encode/Decode\n"
            "🧮 Calculators — finance, math, units, digits\n"
            "🌍 Markets & weather — boards, free-form FX calc, quake Richter filter, Pro alerts\n"
            "📰 Feeds — RSS\n"
            "☁️ Cloudflare — DNS\n"
            "🖥 Server — SSH from Telegram\n"
            "📋 Account — /usage · /plan · /purchase\n"
            "🧹 Clear chat — delete bot messages (and nearby user msgs if API allows)\n\n"
            "Language: /lang · Glass menu: /imenu · Cancel job: /del <job_id>\n"
            "Network: /netstatus"
        ),
        "help_short_admin_extra": (
            "🛡 Admin:\n"
            "/admin · /loghelp · logs & usage\n"
            "YTDLP_COOKIES for YouTube · MINIAPP_BASE_URL for Mini App"
        ),
        "help_short_admin": (
            "🛡 Admin shortcuts:\n"
            "/admin · /loghelp · /usage · /plan"
        ),
        "loghelp_body": (
            "If a transfer failed:\n\n"
            "1) Copy the job_id from the queued message.\n"
            "2) Send that id to support.\n"
            "3) Check /netstatus and destination connection.\n"
            "4) Cancel with /del <job_id> and retry if needed."
        ),
        "loghelp_body_admin": (
            "Job log triage:\n\n"
            "1) Take job_id from Queued message.\n"
            "2) bot logs: task_queued\n"
            "3) worker: task_started -> task_done|task_failed\n"
            "4) task_requeued = network/access issue\n"
            "Paths:\n"
            "- /opt/tele2rub/queue/bot_events.jsonl\n"
            "- /opt/tele2rub/queue/worker_events.jsonl"
        ),
        "rubika_not_connected": "Rubika is not linked yet.\nTap the button below to connect.",
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
        "rubika_connected_ok": (
            "Rubika linked ✅\n\n"
            "How to send:\n"
            "• Transfer → Direct send → Rubika on, then send a file\n"
            "• Or send a file and pick the destination"
        ),
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
        "btn_confirm_send": "✅ Confirm send",
        "btn_cancel_send": "❌ Cancel",
        "btn_main_world": "🌍 Markets & weather",
        "failed_detail_title": "Recent failures for your Rubika session:",
        "confirm_cancelled": "Send cancelled.",
        "confirm_already_handled": "This request was already handled.",
        "confirm_use_buttons": "Use the Confirm / Cancel buttons under that message to finish sending.",
        "cleanup_done": "Cleaned `downloads/`: {n} files, ~{mb} MB freed.",
        "direct_need_rubika": "Link Rubika first: `/rubika_connect`",
        "file_too_large": "File exceeds your plan limit (max ~{max_mb} MB). This file is ~{size_mb} MB.\nUpgrade: /purchase",
        "file_too_large_admin": "File exceeds limit (max ~{max_mb} MB from plan + MAX_FILE_MB). This file is ~{size_mb} MB.",
        "bale_file_too_large": "Bale cannot accept this file (max `{max_mb}` MB). This file is ~`{size_mb}` MB.",
        "text_unhandled_hint": "I did not understand that message. Use the menu buttons or send `/help`.",
        "admin_max_file": "`MAX_FILE_MB` (env cap): `{mb}` (`0` or empty = no env cap)",
        "admin_plan_note": "Per-user plans live in SQLite (`user_entitlements`). Users: `/usage`.",
        "admin_clear_prefs_hint": "Clear cached `v2_user_prefs` row: `/admin_clear_prefs <telegram_user_id>`",
        "admin_clear_state_mirrors_hint": "Clear wizard/batch SQLite mirrors only (not JSON files): `/admin_clear_state_mirrors <telegram_user_id>`",
        "admin_tier_usage": "Usage: `/admin_tier <telegram_user_id> <guest|free|pro|star> [days]`",
        "admin_bonus_usage": "Usage: `/admin_bonus <telegram_user_id> <extra_month_mb>`",
        "admin_wizard_user_ask": "Send the numeric Telegram user ID:",
        "admin_wizard_need_user_id": "Send a valid numeric user ID.",
        "admin_wizard_tier_ask": "Send tier: `guest`, `free`, `pro`, or `star`",
        "admin_wizard_days_ask": "For pro, send validity days:",
        "admin_wizard_tier_done": "User `{target}` tier set to `{tier}`.",
        "admin_wizard_bonus_ask": "Send extra monthly quota in MB:",
        "admin_wizard_bonus_done": "Added `{mb}` MB bonus for user `{target}`.",
        "admin_wizard_tier_for_user": "User `{target}` — send tier: `guest`, `free`, `pro`, or `star`",
        "admin_wizard_bonus_for_user": "User `{target}` — send extra monthly quota in MB:",
        "admin_payment_lookup_hint": "Recent `v2_payments` rows: `/admin_payment_lookup <telegram_user_id> [limit]`",
        "admin_payment_lookup_empty": "No payment rows for this user.",
        "admin_payment_lookup_title": "Payments (newest first):\n",
        "admin_payment_status_hint": "Set one payment row status: `/admin_payment_status <payment_id> <status> [ref_id]`",
        "admin_wizard_payment_id_ask": "Send numeric payment_id:",
        "admin_wizard_payment_not_found": "Payment `{id}` not found.",
        "admin_wizard_payment_status_ask": "Send status ({statuses}) and optional ref_id:",
        "admin_wizard_payment_status_done": "OK: payment `{payment_id}` → `{status}`{grant}",
        "admin_wizard_clear_prefs_done": "Cleared prefs for user `{target}`.",
        "admin_reconcile_billing_hint": "Expire stale pending/initiated payments: `/admin_reconcile_billing`",
        "admin_reconcile_billing_result": "Reconcile: expired `{expired}`, scanned `{scanned}`.",
        "purchase_stub_started": (
            "💳 Purchase request recorded.\n\n"
            "Reference: {payment_id}\n"
            "After payment is confirmed, Pro will activate.\n"
            "Check usage: /usage"
        ),
        "purchase_stub_started_admin": (
            "💳 Test checkout (BILLING_STUB_CHECKOUT)\n\n"
            "Created v2_payments row.\n"
            "• payment_id: {payment_id}\n"
            "• authority: {authority}\n\n"
            "Grant Pro via POST …/v2_payment_event or /admin_payment_status <id> paid"
        ),
        "purchase_gateway_started": (
            "💳 Zarinpal — Pro 30 days\n\n"
            "1) Tap the Pay button\n"
            "2) Complete payment in Zarinpal\n"
            "3) After confirmation Pro activates and you get a DM\n\n"
            "Tracking id: {payment_id}\n"
            "Link: {pay_url}"
        ),
        "btn_open_pay_url": "💳 Pay with Zarinpal",
        "purchase_gateway_error": "Payment gateway error: {error}",
        "toolkit_network_disabled": "Network tools are temporarily unavailable.",
        "toolkit_network_disabled_admin": "Network toolkit is off — set TOOLKIT_NETWORK_LIGHT in .env.",
        "toolkit_utility_disabled": "This tool is temporarily unavailable.",
        "toolkit_utility_disabled_admin": "Text toolkit is off — set TOOLKIT_UTILITY_LIGHT in .env.",
        "toolkit_quota_exceeded": "Daily toolkit quota reached ({used}/{limit}). Try again tomorrow.",
        "toolkit_dns_usage": "Usage: `/dns <hostname>` — e.g. `/dns example.com`",
        "toolkit_dns_result": "`{host}`:\n{ips}",
        "toolkit_dns_error": "DNS error for `{host}`:\n{error}",
        "toolkit_myip_result": "Server egress IP:\n`{ip}`",
        "toolkit_myip_error": "Could not fetch IP:\n{error}",
        "toolkit_ping_usage": "Usage: `/ping <host> [port]` — default port 443 (TCP). E.g. `/ping example.com 80`",
        "toolkit_ping_result": "TCP `{host}:{port}` ~ `{ms}` ms",
        "toolkit_ping_error": "`{host}:{port}` — {error}",
        "toolkit_ipinfo_usage": "Usage: `/ipinfo <ip>`",
        "toolkit_ipinfo_send_only": "Send an IP or host:",
        "toolkit_ipinfo_result": "{data}",
        "toolkit_ipinfo_error": "IP info failed: {error}",
        "toolkit_whois_usage": "Usage: `/whois <domain-or-ip>`",
        "toolkit_whois_send_only": "Send a domain or IP:",
        "toolkit_whois_result": "{data}",
        "toolkit_whois_error": "whois/RDAP failed: {error}",
        "toolkit_myid_result": "User ID: `{user_id}`\nUsername: `{username}`\nChat ID: `{chat_id}`",
        "toolkit_gsearch_usage": "Google search is temporarily unavailable.",
        "toolkit_gsearch_usage_admin": "Usage: /gsearch <query> or /gisearch <query>\nRequires env: GOOGLE_CSE_API_KEYS and GOOGLE_CSE_ID",
        "toolkit_gsearch_send_only": "Send a search query:",
        "toolkit_gisearch_send_only": "Send an image search query:",
        "toolkit_gsearch_result": "{data}",
        "toolkit_gsearch_error": "Google search failed: {error}",
        "toolkit_md5_usage": "Usage: `/md5 <text>` — MD5 (UTF-8)",
        "toolkit_md5_result": "`{digest}`",
        "toolkit_sha256_usage": "Usage: `/sha256 <text>`",
        "toolkit_sha256_result": "`{digest}`",
        "toolkit_b64e_usage": "Usage: `/b64e <text>` — standard Base64",
        "toolkit_b64e_result": "`{data}`",
        "toolkit_b64d_usage": "Usage: `/b64d <base64 string>`",
        "toolkit_b64d_result": "{data}",
        "toolkit_b64d_error": "Decode failed: {error}",
        "toolkit_input_truncated": "(Input truncated to 12000 characters.)",
        "toolkit_dns_send_only": "Send a hostname or IP:",
        "toolkit_ping_send_only": "Send host (port optional; tries 443 then 80).",
        "btn_tool_http_headers": "📬 HTTP Headers",
        "btn_tool_website_status": "🌐 Website status",
        "btn_tool_port_check": "🔌 Port check",
        "btn_tool_subnet": "📡 Subnet calc",
        "btn_tool_blacklist": "🛡 Blacklist",
        "btn_tool_ssl": "🔒 SSL check",
        "toolkit_http_headers_send_only": "Send a URL (e.g. example.com)",
        "toolkit_website_status_send_only": "Send a website URL",
        "toolkit_port_ask_host": "Send host or IP:",
        "toolkit_port_ask_port": "Send port number (e.g. 80 or 443):",
        "toolkit_port_check_send_only": "Send host and port: `google.com 443`",
        "toolkit_subnet_send_only": "Send CIDR: `192.168.1.0/24`",
        "toolkit_blacklist_send_only": "Send an IP to check blacklists",
        "toolkit_ssl_send_only": "Send a domain for SSL check",
        "toolkit_net_error": "Error: {error}",
        "cf_menu_connected": "☁️ Cloudflare connected ✅\nUse the buttons below.",
        "cf_quick_help": "Tips:\n• «CF status» — token check\n• «Domains» — zone list\n• «DNS records» — `/cf_dns <zone_id>`\n• Disconnect — «Disconnect Cloudflare»",
        "toolkit_md5_send_only": "Send text to hash with MD5.",
        "toolkit_sha256_send_only": "Send text to hash with SHA256.",
        "toolkit_b64e_send_only": "Send text to Base64-encode.",
        "toolkit_b64d_send_only": "Send a Base64 string to decode.",
        "toolkit_myip_server_fallback": "Current egress IP: {ip}\n\nFor your real device IP, Mini App must be enabled. Contact support if unavailable.",
        "toolkit_myip_server_fallback_admin": "Server egress IP: {ip}\n\nSet MINIAPP_BASE_URL in .env for real user IP.",
        "miniapp_myip_open": "Browser tools (your real IP, DNS, latency, password, …) — tap a button:",
        "btn_open_myip_app": "📍 My IP",
        "btn_open_miniapp_hub": "🧰 Mini App hub",
        "miniapp_setup_hint": (
            "Browser tools are temporarily unavailable.\n"
            "Please try again later or contact support."
        ),
        "miniapp_setup_hint_admin": (
            "Mini App is not configured.\n"
            "Set MINIAPP_BASE_URL (public HTTPS URL to web/) in .env.\n"
            "See README → Telegram Mini App."
        ),
        "media_pick_dest": "Choose where to send this file:",
        "media_dest_session_expired": "Selection expired — send the file again.",
        "inline_main_title": "Menu shortcut — pick a section (continue with the reply keyboard):",
        "inline_world_menu": "🌍 Markets & weather",
        "inline_world_title": "Markets, FX, weather & alerts",
        "btn_world_weather": "🌤 Weather",
        "btn_world_time": "🕒 World clock",
        "btn_world_calendar": "📅 Calendar",
        "btn_world_age": "🎂 Age",
        "btn_world_currency": "🧮 FX calculator",
        "btn_world_earthquake": "🌋 Earthquakes",
        "btn_world_rss": "➕ Add feed",
        "btn_world_rss_list": "📋 Feeds",
        "weather_ask_city": "Send a city name (e.g. London):",
        "timezone_ask_place": "Send a city or IANA zone (e.g. London or Europe/London):",
        "age_ask_date": "Send birth date as YYYY/MM/DD (Gregorian or Solar Hijri):",
        "fx_calc_ask": "Type any amount + unit freely, e.g.:\n`100000 toman` · `50 USD` · `1 sekkee`\nor use quick / recent buttons:",
        "currency_ask_amount": "Send an amount (number) or use a quick button:",
        "currency_ask_pair": "We will ask source and target step by step.",
        "currency_bad_amount": "Invalid amount.",
        "rss_ask_url": "Send an RSS/Atom feed URL:",
        "rss_bad_url": "Send a valid http(s) URL.",
        "rss_added": "Feed #{feed_id} saved.",
        "rss_push_ask": "Enable instant push for new items? (daily digest also runs for push-enabled feeds)",
        "rss_push_on": "🔔 Push on",
        "rss_push_off": "🔕 Push off",
        "rss_view_now": "👁 View now",
        "rss_push_enabled": "Push enabled.",
        "rss_push_disabled": "Push disabled.",
        "rss_not_found": "Feed not found.",
        "rss_list_empty": "No feeds yet. Use «➕ Add feed» or Manage feeds.",
        "rss_list_title": "Your feeds:",
        "rss_push_new": "📰 New items: {label}",
        "world_error": "Error: {detail}",
        "world_digest_title": "📰 Daily feed digest — {date}",
        "btn_main_feed": "📰 Feed Reader",
        "btn_feed_reader": "📰 Manage feeds",
        "btn_feed_list": "📋 Feed list",
        "btn_feed_add": "➕ Add feed",
        "btn_feed_help": "ℹ️ Feed help",
        "btn_plan_compare": "📊 Compare plans",
        "feed_section_opened": "Feed Reader — RSS, YouTube, X/Twitter",
        "feed_help_body": (
            "📰 Feed Reader help\n"
            "• Send an RSS URL, YouTube channel, or X account\n"
            "• Push: instant new-item alerts (plan-gated)\n"
            "• Digest: daily Tehran summary for selected feeds\n"
            "• /cancel to abort wizards"
        ),
        "feed_quota_line": "Feed quota: {used}/{limit}",
        "feed_page_prev": "‹ Prev",
        "feed_page_next": "Next ›",
        "feed_digest_on": "📰 Daily digest: on",
        "feed_digest_off": "📰 Daily digest: off",
        "feed_digest_enabled": "Daily digest enabled",
        "feed_digest_disabled": "Daily digest disabled",
        "feed_push_plan_blocked": "Your plan cannot enable push. Upgrade or use digest-only.",
        "feed_resolve_failed": "Could not resolve this URL to a feed: {url}",
        "world_quota_exceeded": "World tools daily limit reached ({used}/{limit}). Try tomorrow or upgrade.",
        "plan_compare_title": "📊 Plan comparison",
        "feed_menu_title": "📰 Feed Reader\nRSS · YouTube · X/Twitter\nAdd feeds, push alerts, or view on demand.",
        "feed_digest_hint": "Push = instant alerts · Digest = Tehran morning summary (per-feed toggle).",
        "feed_digest_schedule": "Daily digest hour: ~{hour}:00 Tehran time.",
        "feed_empty_state": (
            "No feeds yet.\n"
            "Tap ➕ Add feed and send an RSS, YouTube, or X URL.\n"
            "Then enable push or daily digest per feed."
        ),
        "payment_granted_dm": (
            "✅ Payment confirmed.\n"
            "Plan {tier} is active for {days} days.\n"
            "Details: /usage"
        ),
        "payment_expiry_soon_dm": (
            "⏰ Your {tier} plan expires in about {days_left} days.\n"
            "Renew: /purchase · Compare: /plan_compare"
        ),
        "feed_ask_url": (
            "Send a feed URL or profile page:\n"
            "• Direct RSS/Atom\n"
            "• `youtube.com/@handle`, `channel/UC…`, or playlist\n"
            "• `x.com/username`"
        ),
        "feed_added": "Feed #{feed_id} ({kind}) saved.",
        "feed_already_added": "This feed is already saved (#{feed_id}).",
        "feed_limit_reached": "Feed limit reached ({limit}). Delete one or upgrade your plan.",
        "feed_fetch_failed": "Could not load feed: {detail}\nURL: {url}",
        "feed_delete": "🗑 Delete feed",
        "feed_deleted": "Feed deleted.",
        "feed_add_btn": "➕ Add feed",
        "btn_tool_password": "🔑 Password",
        "btn_tool_rev_dns": "↩️ Reverse DNS",
        "btn_tool_mac": "🔌 MAC Vendor",
        "btn_tool_email": "✉️ Email Check",
        "btn_tool_url_expand": "🔗 Expand URL",
        "btn_tool_timestamp": "🕐 Timestamp",
        "btn_tool_lorem": "📝 Lorem",
        "toolkit_password_result": "Suggested password:\n`{password}`",
        "toolkit_rev_dns_send_only": "Send an IP for reverse DNS.",
        "toolkit_mac_send_only": "Send a MAC address (e.g. `AA:BB:CC:DD:EE:FF`):",
        "toolkit_email_send_only": "Send an email address:",
        "toolkit_url_expand_send_only": "Send a short URL to expand.",
        "toolkit_timestamp_send_only": "Send a Unix timestamp or `YYYY-MM-DD HH:MM:SS`.",
        "quota_parallel_msg": "Too many jobs at once for your plan (`{cur}` / `{maxp}`). Wait for one to finish.",
        "quota_day_msg": "Daily data limit reached.\nThis job ~{need} MB; ~{left} MB left today.\nUpgrade: /purchase",
        "quota_month_msg": "Monthly data limit reached.\nThis job ~{need} MB; ~{left} MB left this month.\nUpgrade: /purchase",
        "quota_file_cap_msg": "This file exceeds the per-file cap (`{max_mb}` MB max; yours ~{need_mb} MB).",
        "quota_unknown": "Quota blocked.\nCheck /usage or upgrade with /purchase.",
        "usage_panel": (
            "📊 Usage & limits\n\n"
            "Plan\n"
            "• {tier} (expires: {expires})\n\n"
            "Transfer\n"
            "• Today: ~{day_used} / {day_cap} MB\n"
            "• This month: ~{month_used} / {month_cap} MB\n"
            "• Max file: {max_file} MB\n"
            "• Parallel: {parallel} / {max_parallel}\n\n"
            "Tools\n"
            "• Toolkit daily: {toolkit_used_cap}\n"
            "• World/FX daily: {world_used_cap}\n"
            "• Feeds: {feed_used}/{feed_cap} (push: {feed_push})\n\n"
            "Upgrade: /purchase · Compare: /plan_compare"
        ),
        "usage_disabled_hint": "Usage quotas are currently disabled for this bot.",
        "usage_disabled_hint_admin": "Quotas are off (DISABLE_USAGE_LIMITS). Only optional env caps apply.",
        "batch_raw_hint": "Current raw total ~`{raw_mb}` MB ({n} files). ZIP size may differ slightly.",
        "direct_url_use_sendlink": "For links use the button or `/sendlink`.",
        "direct_url_use_link_menu": "For link/video download use main menu «🔗 Link / video».",
        "purchase_info_body": (
            "💳 Plans / purchase\n\n"
            "• Buy Pro (30 days): /purchase\n"
            "• Compare plans: /plan_compare\n"
            "• Usage: /usage\n\n"
            "For Star or custom plans, contact support."
        ),
        "purchase_info_body_admin": (
            "💳 Plans / purchase (admin)\n\n"
            "• Buy Pro: /purchase (Zarinpal)\n"
            "• Compare: /plan_compare\n"
            "• Grant: /admin_tier <uid> free|pro|star [days]\n"
            "• Or tools/grant_plan.py on the server"
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
    try:
        db_lang = queue.get_lang(user_id)
    except Exception as e:
        log_event("v2_user_prefs_lang_read_failed", user_id=user_id, error=str(e))
        return "fa"
    if db_lang in ("fa", "en"):
        return db_lang
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
    try:
        queue.upsert_lang(user_id, lang)
    except Exception as e:
        log_event("v2_user_prefs_lang_upsert_failed", user_id=user_id, error=str(e))


def is_admin(user_id: int) -> bool:
    try:
        return int(user_id) in ADMIN_IDS
    except (TypeError, ValueError):
        return False


def tr(user_id: int, key: str, **kwargs) -> str:
    """Translate i18n key. Admins prefer ``{key}_admin`` when that variant exists."""
    lang = get_lang(user_id)
    pack = I18N.get(lang, I18N["fa"])
    fa = I18N["fa"]
    lookup = key
    if is_admin(user_id):
        admin_key = f"{key}_admin"
        if admin_key in pack or admin_key in fa:
            lookup = admin_key
    text = pack.get(lookup) or fa.get(lookup) or pack.get(key) or fa.get(key) or key
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
    return menu_engine.build_main_menu(user_id, tr, user_id in ADMIN_IDS)


def build_plan_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_plan_menu(user_id, tr)


def build_transfer_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_transfer_menu(user_id, tr)


def build_toolkit_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_toolkit_menu(user_id, tr)


def build_world_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_world_menu(user_id, tr)


def build_feed_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_feed_menu(user_id, tr)


def build_toolkit_network_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_toolkit_network_menu(user_id, tr)


def build_toolkit_crypto_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_toolkit_crypto_menu(user_id, tr)

def build_toolkit_calc_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_toolkit_calc_menu(user_id, tr)


def build_calc_finance_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_calc_finance_menu(user_id, tr)


def build_calc_numbers_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_calc_numbers_menu(user_id, tr)


def build_calc_convert_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_calc_convert_menu(user_id, tr)


def build_calc_math_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_calc_math_menu(user_id, tr)


def build_calc_text_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_calc_text_menu(user_id, tr)


def build_calc_other_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_calc_other_menu(user_id, tr)


def build_toolkit_zip_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_toolkit_zip_menu(user_id, tr)


def build_bale_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_bale_menu(user_id, tr)


def build_drive_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_drive_menu(user_id, tr)


def build_ssh_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_ssh_menu(user_id, tr)


def build_rubika_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_rubika_menu(user_id, tr)


def build_files_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_files_menu(user_id, tr)


def build_link_direct_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_link_direct_menu(user_id, tr)


def build_cloudflare_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_cloudflare_menu(user_id, tr)


def build_settings_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_settings_menu(user_id, tr, get_direct_mode_target(user_id))


def build_admin_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_admin_menu(user_id, tr)


def build_admin_users_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_admin_users_menu(user_id, tr)


def build_admin_billing_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_admin_billing_menu(user_id, tr)


def build_admin_maintenance_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_admin_maintenance_menu(user_id, tr)


def build_admin_broadcast_menu(user_id: int) -> ReplyKeyboardMarkup:
    return menu_engine.build_admin_broadcast_menu(user_id, tr)


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

waiting_for_zip_password_users: set[int] = set()


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
    try:
        db_sess = queue.get_rubika_session(user_id)
    except Exception as e:
        log_event("v2_user_prefs_rubika_session_read_failed", user_id=user_id, error=str(e))
        return None
    if db_sess:
        return db_sess
    return None


def _persist_rubika_session_prefs(user_id: int, session_name: str) -> None:
    try:
        queue.upsert_rubika_session(user_id, session_name)
    except Exception as e:
        log_event("v2_user_prefs_rubika_session_upsert_failed", user_id=user_id, error=str(e))


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


def get_direct_mode_target(user_id: int) -> Optional[str]:
    return load_direct_mode_target(
        user_id,
        load_users=load_users,
        get_user_key=get_user_key,
        queue=queue,
    )


def set_direct_mode_target(user_id: int, target: Optional[str]) -> None:
    save_direct_mode_target(
        user_id,
        target,  # type: ignore[arg-type]
        load_users=load_users,
        save_users=save_users,
        get_user_key=get_user_key,
        queue=queue,
    )


def is_direct_mode(user_id: int) -> bool:
    return get_direct_mode_target(user_id) is not None


def set_direct_mode(user_id: int, enabled: bool):
    """Legacy bool API: True → rubika, False → off."""
    set_direct_mode_target(user_id, "rubika" if enabled else None)


def load_user_states() -> dict:
    return load_json(USER_STATES_FILE, {})


def save_user_states(data: dict):
    save_json(USER_STATES_FILE, data)


def load_batch_sessions() -> dict:
    return load_json(BATCH_FILE, {})


def save_batch_sessions(data: dict):
    save_json(BATCH_FILE, data)


_WIZARD_TTL_SEC = int((os.getenv("WIZARD_TTL_SEC") or "1800").strip() or "1800")


def get_state(user_id: int) -> dict:
    key = get_user_key(user_id)
    file_s: dict = {}
    states = load_user_states()
    if key in states and isinstance(states[key], dict):
        file_s = dict(states[key])
    mirror_s: dict = {}
    try:
        mirrored = queue.get_user_state_mirror(user_id)
        if mirrored:
            mirror_s = dict(mirrored)
    except Exception as e:
        log_event("v2_user_state_mirror_read_failed", user_id=user_id, error=str(e))
    # Merge: JSON file wins on conflicts (wizard keys often missing from stale mirror).
    s = {**mirror_s, **file_s}
    # Expire stale wizard steps (keep menu_section).
    try:
        ts = int(s.get("_state_ts") or 0)
        step = s.get("step")
        if step and ts > 0 and _WIZARD_TTL_SEC > 0 and (time.time() - ts) > _WIZARD_TTL_SEC:
            keep = {MENU_SECTION_KEY: s.get(MENU_SECTION_KEY)} if s.get(MENU_SECTION_KEY) else {}
            s = keep
            set_state(user_id, keep)
            log_event("wizard_ttl_expired", user_id=user_id, step=str(step)[:80])
    except Exception:
        pass
    if MENU_SECTION_KEY in s:
        pass
    elif MENU_SECTION_KEY in mirror_s:
        s[MENU_SECTION_KEY] = mirror_s[MENU_SECTION_KEY]
    try:
        sec = queue.get_menu_section(user_id)
    except Exception as e:
        log_event("v2_user_prefs_read_failed", user_id=user_id, error=str(e))
        return s
    if not sec:
        return s
    out = dict(s)
    out[MENU_SECTION_KEY] = sec
    return out


def set_state(user_id: int, data: dict):
    payload = dict(data or {})
    if payload.get("step"):
        payload["_state_ts"] = int(time.time())
    states = load_user_states()
    states[get_user_key(user_id)] = payload
    save_user_states(states)
    try:
        queue.upsert_user_state_mirror(user_id, payload)
    except Exception as e:
        log_event("v2_user_state_mirror_upsert_failed", user_id=user_id, error=str(e))


def clear_state(user_id: int):
    """Drop wizard keys from ``user_states.json`` only.

    Does **not** delete ``v2_user_prefs`` so mirrors for menu/lang/direct_mode/rubika_session stay intact.
    """
    from v2.handlers.confirm_state import pop_pending_confirm

    pop_pending_confirm(user_id)
    states = load_user_states()
    states.pop(get_user_key(user_id), None)
    save_user_states(states)
    try:
        queue.delete_user_state_mirror(user_id)
    except Exception as e:
        log_event("v2_user_state_mirror_delete_failed", user_id=user_id, error=str(e))


def merge_user_state(user_id: int, patch: dict) -> None:
    cur = dict(get_state(user_id))
    cur.update(patch)
    set_state(user_id, cur)


def _strip_wizard_keys(state: dict) -> dict:
    """Remove ephemeral wizard keys when navigating menus."""
    drop_exact = {
        "step",
        "pending_task",
        "admin_target_user_id",
        "admin_target_tier",
        "ssh_server_id",
        "ssh_remote_path",
    }
    cleaned = dict(state)
    for key in drop_exact:
        cleaned.pop(key, None)
    return cleaned


def set_menu_section(user_id: int, section: MenuSection) -> None:
    cur = dict(get_state(user_id))
    cur = _strip_wizard_keys(cur)
    cur[MENU_SECTION_KEY] = section.value
    set_state(user_id, cur)
    try:
        queue.upsert_menu_section(user_id, section.value)
    except Exception as e:
        log_event("v2_user_prefs_upsert_failed", user_id=user_id, error=str(e))


def get_effective_menu_section(user_id: int) -> Optional[str]:
    """Read menu section from the same merged state source used by text routing."""
    state = get_state(user_id)
    section = state.get(MENU_SECTION_KEY)
    if section:
        return str(section)
    try:
        return queue.get_menu_section(user_id)
    except Exception as e:
        log_event("v2_user_prefs_read_failed", user_id=user_id, error=str(e))
        return None


def set_state_preserving_menu(user_id: int, new_state: dict) -> None:
    """Merge wizard/session keys; keep ``MENU_SECTION_KEY`` when omitted."""
    prev = get_state(user_id)
    merged = dict(prev)
    merged.update(new_state)
    if MENU_SECTION_KEY in prev and MENU_SECTION_KEY not in new_state:
        merged[MENU_SECTION_KEY] = prev[MENU_SECTION_KEY]
    set_state(user_id, merged)


def get_batch(user_id: int) -> dict:
    key = get_user_key(user_id)
    if V2_EPHEMERAL_READ_PRIMARY_SQLITE:
        try:
            mirrored = queue.get_batch_session_mirror(user_id)
            if mirrored:
                return dict(mirrored)
        except Exception as e:
            log_event("v2_batch_session_mirror_read_failed", user_id=user_id, error=str(e))
        sessions = load_batch_sessions()
        if key in sessions:
            raw = sessions[key]
            return dict(raw) if isinstance(raw, dict) else {}
        return {}
    sessions = load_batch_sessions()
    if key in sessions:
        raw = sessions[key]
        return dict(raw) if isinstance(raw, dict) else {}
    try:
        mirrored = queue.get_batch_session_mirror(user_id)
        return dict(mirrored) if mirrored else {}
    except Exception as e:
        log_event("v2_batch_session_mirror_read_failed", user_id=user_id, error=str(e))
        return {}


def set_batch(user_id: int, data: dict):
    sessions = load_batch_sessions()
    sessions[get_user_key(user_id)] = data
    save_batch_sessions(sessions)
    try:
        queue.upsert_batch_session_mirror(user_id, data)
    except Exception as e:
        log_event("v2_batch_session_mirror_upsert_failed", user_id=user_id, error=str(e))


def clear_batch(user_id: int):
    sessions = load_batch_sessions()
    sessions.pop(get_user_key(user_id), None)
    save_batch_sessions(sessions)
    try:
        queue.delete_batch_session_mirror(user_id)
    except Exception as e:
        log_event("v2_batch_session_mirror_delete_failed", user_id=user_id, error=str(e))


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


def _upsert_bale_bot_token_persist(user_id: int, token: str) -> None:
    from v2.core.user_prefs_sync import mirror_bale_to_users_json

    queue.upsert_bale_bot_token(user_id, token)
    mirror_bale_to_users_json(
        user_id,
        load_users=load_users,
        save_users=save_users,
        get_user_key=get_user_key,
        bot_token=token,
    )


def _upsert_bale_chat_id_persist(user_id: int, chat_id: str) -> None:
    from v2.core.user_prefs_sync import mirror_bale_to_users_json

    queue.upsert_bale_chat_id(user_id, chat_id)
    mirror_bale_to_users_json(
        user_id,
        load_users=load_users,
        save_users=save_users,
        get_user_key=get_user_key,
        chat_id=chat_id,
    )


def _clear_bale_credentials_persist(user_id: int) -> None:
    from v2.core.user_prefs_sync import mirror_bale_to_users_json

    queue.clear_bale_credentials(user_id)
    mirror_bale_to_users_json(
        user_id,
        load_users=load_users,
        save_users=save_users,
        get_user_key=get_user_key,
        clear=True,
    )


def _upsert_cloudflare_token_persist(user_id: int, token: str) -> None:
    from v2.core.user_prefs_sync import mirror_cloudflare_to_users_json

    queue.upsert_cloudflare_api_token(user_id, token)
    mirror_cloudflare_to_users_json(
        user_id,
        token,
        load_users=load_users,
        save_users=save_users,
        get_user_key=get_user_key,
    )


def _clear_cloudflare_token_persist(user_id: int) -> None:
    from v2.core.user_prefs_sync import mirror_cloudflare_to_users_json

    queue.clear_cloudflare_api_token(user_id)
    mirror_cloudflare_to_users_json(
        user_id,
        None,
        load_users=load_users,
        save_users=save_users,
        get_user_key=get_user_key,
        clear=True,
    )


def sync_v2_ephemeral_mirrors_from_json() -> None:
    """Copy existing ``user_states.json`` / ``batch_sessions.json`` into SQLite mirrors.

    Runs once per process start so mirrors match on-disk JSON without waiting for
    the next ``set_state`` / ``set_batch`` per user.
    """
    n_state = 0
    n_batch = 0
    try:
        raw_states = load_user_states()
    except Exception as e:
        log_event("v2_state_mirror_backfill_failed", phase="load_user_states", error=str(e))
        raw_states = {}
    for key, value in (raw_states or {}).items():
        if not isinstance(key, str) or not key.isdigit():
            continue
        if not isinstance(value, dict):
            continue
        uid = int(key)
        try:
            queue.upsert_user_state_mirror(uid, value)
            n_state += 1
        except Exception as e:
            log_event(
                "v2_state_mirror_backfill_row_failed",
                user_id=uid,
                kind="user_state",
                error=str(e),
            )
    try:
        raw_batches = load_batch_sessions()
    except Exception as e:
        log_event("v2_state_mirror_backfill_failed", phase="load_batch_sessions", error=str(e))
        raw_batches = {}
    for key, value in (raw_batches or {}).items():
        if not isinstance(key, str) or not key.isdigit():
            continue
        if not isinstance(value, dict):
            continue
        uid = int(key)
        try:
            queue.upsert_batch_session_mirror(uid, value)
            n_batch += 1
        except Exception as e:
            log_event(
                "v2_state_mirror_backfill_row_failed",
                user_id=uid,
                kind="batch_session",
                error=str(e),
            )
    if n_state or n_batch:
        log_event("v2_state_mirror_backfill_done", user_states=n_state, batch_sessions=n_batch)


def sync_v2_provider_credentials_from_users_json() -> None:
    """Keep SQLite and ``users.json`` provider prefs in sync across restarts/updates."""
    from v2.core.user_prefs_sync import (
        backup_sqlite_provider_prefs_to_users_json,
        sync_provider_credentials_from_users_json,
    )

    try:
        n_back = backup_sqlite_provider_prefs_to_users_json(
            queue,
            load_users=load_users,
            save_users=save_users,
            get_user_key=get_user_key,
        )
        if n_back:
            log_event("v2_provider_prefs_backed_to_json", rows=n_back)
    except Exception as e:
        log_event("v2_provider_prefs_backup_failed", error=str(e))
    try:
        n = sync_provider_credentials_from_users_json(
            queue,
            load_users=load_users,
            get_user_key=get_user_key,
        )
        if n:
            log_event("v2_provider_prefs_restored_from_json", rows=n)
    except Exception as e:
        log_event("v2_provider_prefs_restore_failed", error=str(e))


async def gate_quota(message: Message, user_id: int, task: dict) -> bool:
    """Return True if the user may enqueue this task."""
    from v2.core.upgrade_cta import buy_pro_keyboard

    task["telegram_user_id"] = user_id
    est = estimate_task_bytes(task)
    ok, code, det = can_enqueue(user_id, est, queue)
    if ok:
        if code == "ok_warn" and det.get("quota_soft_warn"):
            warn = tr(
                user_id,
                "quota_soft_warn",
                day_pct=det.get("day_pct", "-"),
                month_pct=det.get("month_pct", "-"),
            )
            try:
                await message.reply_text(
                    warn,
                    reply_markup=buy_pro_keyboard(user_id, tr),
                    parse_mode=None,
                )
            except Exception:
                pass
        return True
    await message.reply_text(
        quota_fail_text(user_id, code, det),
        reply_markup=buy_pro_keyboard(user_id, tr),
        parse_mode=None,
    )
    log_event("quota_blocked", user_id=user_id, code=code)
    return False


def usage_report_text(user_id: int) -> str:
    if DISABLE_USAGE_LIMITS:
        return tr(user_id, "usage_disabled_hint")
    u = get_usage_snapshot(user_id)
    day_u = u["day_bytes"] / (1024 * 1024)
    month_u = u["month_bytes"] / (1024 * 1024)
    cur_par = parallel_job_count(user_id, queue)
    tk_lim = effective_toolkit_daily_limit(user_id)
    wd_lim = effective_world_daily_limit(user_id)
    tk_used = queue.toolkit_daily_get_count(user_id)
    wd_used = queue.world_daily_get_count(user_id)
    feed_used = queue.count_feeds(user_id)
    feed_cap = effective_feed_max(user_id)
    exp = int(u.get("expires_at") or 0)
    exp_s = "-" if exp <= 0 else time.strftime("%Y-%m-%d", time.localtime(exp))
    tk_s = "∞" if tk_lim <= 0 else f"{tk_used}/{tk_lim}"
    wd_s = "∞" if wd_lim <= 0 else f"{wd_used}/{wd_lim}"
    push_s = "yes" if feed_push_allowed(user_id) else "no"
    if get_lang(user_id) != "en":
        push_s = "بله" if feed_push_allowed(user_id) else "خیر"
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
        toolkit_used_cap=tk_s,
        world_used_cap=wd_s,
        feed_used=feed_used,
        feed_cap=feed_cap,
        feed_push=push_s,
        expires=exp_s,
    )


def plan_compare_text_for_user(user_id: int) -> str:
    lang = "en" if get_lang(user_id) == "en" else "fa"
    return tr(user_id, "plan_compare_title") + "\n" + plan_matrix_text(lang=lang)


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
    if match:
        return match.group(0).rstrip(".,)")
    match = re.search(r"(?:www\.|youtu\.be/|youtube\.com/)[^\s]+", text, flags=re.IGNORECASE)
    if not match:
        return None
    return f"https://{match.group(0).rstrip('.,)')}"


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


async def payment_reconcile_loop():
    """Periodic stale-payment expiry when ``BILLING_RECONCILE_ENABLE`` is set."""
    await asyncio.sleep(90)
    while True:
        await asyncio.sleep(BILLING_RECONCILE_INTERVAL_SEC)
        if not BILLING_RECONCILE_ENABLE:
            continue
        try:
            stats = run_reconcile(queue, pending_max_age_sec=BILLING_RECONCILE_PENDING_MAX_AGE_SEC)
            if stats.get("expired", 0):
                log_event("billing_reconcile_tick", **stats)
        except Exception as e:
            log_event("billing_reconcile_error", error=str(e))


_EXPIRY_REMINDED: set[str] = set()


async def payment_notify_loop():
    """DM users after paid grant; soft reminder ~3 days before pro/star expiry."""
    await asyncio.sleep(45)
    while True:
        await asyncio.sleep(60)
        try:
            for item in claim_pending_entitlement_notifies(queue, limit=40):
                uid = int(item["telegram_user_id"])
                try:
                    await app.send_message(
                        uid,
                        tr(
                            uid,
                            "payment_granted_dm",
                            tier=item.get("tier") or "pro",
                            days=item.get("days") or 0,
                        ),
                        parse_mode=None,
                    )
                except Exception as e:
                    log_event("payment_grant_dm_failed", user_id=uid, error=str(e)[:200])
        except Exception as e:
            log_event("payment_notify_loop_error", error=str(e)[:200])
        try:
            from user_entitlements import list_expiring_paid_tiers

            for row in list_expiring_paid_tiers(within_sec=3 * 86400, limit=80):
                uid = int(row["user_id"])
                exp = int(row["expires_at"] or 0)
                day_key = time.strftime("%Y-%m-%d", time.localtime(exp))
                key = f"{uid}:{row.get('tier')}:{day_key}"
                if key in _EXPIRY_REMINDED:
                    continue
                days_left = max(1, int((exp - time.time()) // 86400) or 1)
                try:
                    await app.send_message(
                        uid,
                        tr(
                            uid,
                            "payment_expiry_soon_dm",
                            tier=row.get("tier") or "pro",
                            days_left=days_left,
                        ),
                        parse_mode=None,
                    )
                    _EXPIRY_REMINDED.add(key)
                except Exception:
                    pass
        except Exception as e:
            log_event("payment_expiry_loop_error", error=str(e)[:200])


async def alert_poll_loop():
    from v2.alerts.poller import alert_poll_loop as _loop
    await _loop(app, is_paid=_is_paid_user, interval=120.0, get_lang=get_lang)


async def rss_poll_loop():
    """Notify users when push-enabled RSS feeds change; also daily digest."""
    await asyncio.sleep(120)
    while True:
        await asyncio.sleep(RSS_POLL_INTERVAL_SEC)
        if not RSS_POLL_ENABLE:
            continue
        try:
            await poll_rss_pushes(
                app,
                queue,
                tr,
                log_event=log_event,
                feed_push_allowed=feed_push_allowed,
            )
        except Exception as e:
            log_event("rss_poll_error", error=str(e))
        try:
            await maybe_send_daily_digest(app, queue, tr, log_event=log_event)
        except Exception as e:
            log_event("world_digest_error", error=str(e))
        try:
            from v2.handlers.market_digest import maybe_send_market_digest

            await maybe_send_market_digest(
                app,
                list_user_ids=lambda: queue.list_activity_user_ids(limit=500),
                tr=tr,
                get_lang=get_lang,
                log_event=log_event,
            )
        except Exception as e:
            log_event("market_digest_error", error=str(e))


def _create_stub_purchase_checkout(user_id: int) -> tuple[int, str]:
    from v2.billing import StubPaymentGateway

    gw = StubPaymentGateway(queue)
    r = gw.create_payment_intent(
        user_id,
        0,
        currency="IRR",
        metadata={"grant_tier": "pro", "grant_days": 30, "stub_checkout": True},
    )
    return r.payment_id, (r.authority or "")


def _create_gateway_purchase_checkout(user_id: int) -> tuple[int, str, str]:
    from v2.billing import build_payment_gateway, zarinpal_configured
    from v2.billing.zarinpal import zarinpal_startpay_url

    if not zarinpal_configured():
        raise RuntimeError("ZARINPAL_MERCHANT_ID not set")
    amount = int((os.getenv("ZARINPAL_PLAN_AMOUNT_IRR") or "500000").strip() or "500000")
    gw = build_payment_gateway(queue)
    r = gw.create_payment_intent(
        user_id,
        amount,
        currency="IRR",
        metadata={"grant_tier": "pro", "grant_days": 30, "description": "tele2rub pro 30d"},
    )
    pay_url = ""
    if r.authority and not str(r.authority).startswith("pending-callback-"):
        pay_url = zarinpal_startpay_url(r.authority)
    return r.payment_id, (r.authority or ""), pay_url


def connection_checklist_text(user_id: int) -> str:
    rub = "✅" if get_user_session(user_id) else "⬜"
    bale_tok, bale_chat = (None, None)
    try:
        bale_tok, bale_chat = queue.get_bale_credentials(user_id)
    except Exception:
        pass
    bale = "✅" if bale_tok and bale_chat else "⬜"
    drive = "⬜"
    try:
        from v2.transfer.user_credentials import load_drive_credentials

        dc = load_drive_credentials(queue, BASE_DIR, user_id)
        if dc and dc.ready:
            drive = "✅"
    except Exception:
        pass
    return tr(
        user_id,
        "onboard_checklist",
        rubika=rub,
        bale=bale,
        drive=drive,
    )


BASIC_COMMAND_DEPS = BasicCommandDeps(
    tr=tr,
    remember_chat=remember_chat,
    set_menu_section=set_menu_section,
    get_direct_mode_target=get_direct_mode_target,
    set_direct_mode_target=set_direct_mode_target,
    build_main_menu=build_main_menu,
    app_version=APP_VERSION,
    clear_state=clear_state,
    connection_checklist=connection_checklist_text,
    is_admin=is_admin,
)

SESSION_SETTINGS_COMMAND_DEPS = SessionSettingsCommandDeps(
    tr=tr,
    get_user_session=get_user_session,
    check_rubika_session_sync=check_rubika_session_sync,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    log_event=log_event,
    build_settings_menu=build_settings_menu,
    build_main_menu=build_main_menu,
    network_file=NETWORK_FILE,
)


def _is_paid_user(uid: int) -> bool:
    try:
        from user_entitlements import resolved_limits
        return resolved_limits(uid).tier in ("pro", "star")
    except Exception:
        return uid in ADMIN_IDS


CLEAR_CHAT_DEPS = ClearChatDeps(tr=tr, set_menu_section=set_menu_section)

ALERT_COMMAND_DEPS = AlertCommandDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    get_state=get_state,
    is_paid_user=_is_paid_user,
    get_lang=get_lang,
)


async def clear_chat_handler(client: Client, message: Message):
    await handle_clear_chat_prompt(CLEAR_CHAT_DEPS, client, message)


async def world_alerts_handler(client: Client, message: Message):
    await start_alert_wizard(ALERT_COMMAND_DEPS, message)


async def calc_digits_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "digits")


DIRECT_SEND_COMMAND_DEPS = DirectSendCommandDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    get_direct_mode_target=get_direct_mode_target,
    set_direct_mode_target=set_direct_mode_target,
    get_user_session=get_user_session,
    get_bale_ready=lambda uid: load_bale_credentials(queue, uid).ready,
    get_drive_ready=lambda uid: load_drive_credentials(queue, BASE_DIR, uid).ready,
    build_settings_menu=build_settings_menu,
    build_main_menu=build_main_menu,
    build_transfer_menu=build_transfer_menu,
)

LINK_DIRECT_COMMAND_DEPS = LinkDirectCommandDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    build_link_direct_menu=build_link_direct_menu,
)

def _gateway_checkout_or_none():
    from v2.billing import zarinpal_configured

    return _create_gateway_purchase_checkout if zarinpal_configured() else None


PLAN_COMMAND_DEPS = PlanCommandDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    usage_report_text=usage_report_text,
    stub_checkout_enabled=BILLING_STUB_CHECKOUT,
    create_stub_checkout=_create_stub_purchase_checkout,
    create_gateway_checkout=_gateway_checkout_or_none(),
    plan_compare_text=plan_compare_text_for_user,
)


def _toolkit_quota_try(uid: int) -> tuple[bool, str]:
    """Pre-flight quota check (does not consume). Handlers call ``_toolkit_quota_commit`` after success."""
    lim = effective_toolkit_daily_limit(uid)
    if lim <= 0:
        return True, ""
    cur = queue.toolkit_daily_get_count(uid)
    if cur >= lim:
        return False, tr(
            uid,
            "toolkit_quota_exceeded",
            used=cur,
            limit=lim,
        )
    return True, ""


def _toolkit_quota_commit(uid: int) -> None:
    """Count one successful toolkit invocation (atomic; skips if already at cap)."""
    lim = effective_toolkit_daily_limit(uid)
    if lim <= 0:
        return
    queue.toolkit_daily_increment_if_under_cap(uid, daily_limit=lim)


def _world_quota_try(uid: int) -> tuple[bool, str]:
    lim = effective_world_daily_limit(uid)
    if lim <= 0:
        return True, ""
    cur = queue.world_daily_get_count(uid)
    if cur >= lim:
        return False, tr(
            uid,
            "world_quota_exceeded",
            used=cur,
            limit=lim,
        )
    return True, ""


def _world_quota_commit(uid: int) -> None:
    lim = effective_world_daily_limit(uid)
    if lim <= 0:
        return
    queue.world_daily_increment_if_under_cap(uid, daily_limit=lim)


TOOLKIT_COMMAND_DEPS = ToolkitCommandDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    toolkit_network_light_enabled=TOOLKIT_NETWORK_LIGHT,
    toolkit_utility_light_enabled=TOOLKIT_UTILITY_LIGHT,
    toolkit_quota_try=_toolkit_quota_try,
    toolkit_quota_commit=_toolkit_quota_commit,
    miniapp_base_url=MINIAPP_BASE_URL,
)

TOOLKIT_NET_EXTRA_DEPS = ToolkitNetExtraDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    toolkit_network_light_enabled=TOOLKIT_NETWORK_LIGHT,
    toolkit_quota_try=_toolkit_quota_try,
    toolkit_quota_commit=_toolkit_quota_commit,
    get_state=get_state,
)

async def safe_delete_user_message(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


WORLD_COMMAND_DEPS = WorldCommandDeps(
    tr=tr,
    queue=queue,
    get_state=get_state,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    extract_first_url=extract_first_url,
    get_lang=get_lang,
    log_event=log_event,
    set_menu_section=set_menu_section,
    world_quota_try=_world_quota_try,
    world_quota_commit=_world_quota_commit,
)

FEED_READER_DEPS = FeedReaderDeps(
    tr=tr,
    queue=queue,
    get_state=get_state,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    extract_first_url=extract_first_url,
    get_user_tier=lambda uid: str(get_usage_snapshot(uid).get("tier") or "free"),
    feed_max_for_user=effective_feed_max,
    feed_push_allowed=feed_push_allowed,
    set_menu_section=set_menu_section,
)

TOOLKIT_EXTRA_DEPS = ToolkitExtraDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    toolkit_utility_light_enabled=TOOLKIT_UTILITY_LIGHT,
    toolkit_network_light_enabled=TOOLKIT_NETWORK_LIGHT,
    toolkit_quota_try=_toolkit_quota_try,
    toolkit_quota_commit=_toolkit_quota_commit,
)

TOOLKIT_MENU_DEPS = ToolkitMenuDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    build_toolkit_menu=build_toolkit_menu,
    build_toolkit_network_menu=build_toolkit_network_menu,
    build_toolkit_crypto_menu=build_toolkit_crypto_menu,
    build_toolkit_calc_menu=build_toolkit_calc_menu,
    build_calc_finance_menu=build_calc_finance_menu,
    build_calc_numbers_menu=build_calc_numbers_menu,
    build_calc_convert_menu=build_calc_convert_menu,
    build_calc_math_menu=build_calc_math_menu,
    build_calc_text_menu=build_calc_text_menu,
    build_calc_other_menu=build_calc_other_menu,
    miniapp_base_url=MINIAPP_BASE_URL,
)

CALC_KIT_DEPS = CalcKitDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    get_state=get_state,
    toolkit_quota_try=_toolkit_quota_try,
    toolkit_quota_commit=_toolkit_quota_commit,
    toolkit_utility_light_enabled=TOOLKIT_UTILITY_LIGHT,
)

TRANSFER_HUB_DEPS = TransferHubDeps(
    tr=tr,
    base_dir=BASE_DIR,
    queue=queue,
    set_menu_section=set_menu_section,
    build_transfer_menu=build_transfer_menu,
    build_rubika_menu=build_rubika_menu,
    build_files_menu=build_files_menu,
    build_bale_menu=build_bale_menu,
    build_drive_menu=build_drive_menu,
    build_ssh_menu=build_ssh_menu,
    get_bale_credentials=queue.get_bale_credentials,
    set_bale_chat_id=queue.upsert_bale_chat_id,
    list_ssh_servers=queue.list_ssh_servers,
    get_ssh_server=queue.get_ssh_server,
    ssh_add_server=queue.add_ssh_server,
    ssh_delete_server=queue.delete_ssh_server,
)

CLOUDFLARE_COMMAND_DEPS = CloudflareCommandDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    get_state=get_state,
    get_token=queue.get_cloudflare_api_token,
    upsert_token=_upsert_cloudflare_token_persist,
    clear_token=_clear_cloudflare_token_persist,
    build_cloudflare_menu=build_cloudflare_menu,
    log_event=log_event,
)

PROVIDER_CONNECT_DEPS = ProviderConnectWizardDeps(
    tr=tr,
    base_dir=BASE_DIR,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    get_bale_credentials=queue.get_bale_credentials,
    upsert_bale_bot_token=_upsert_bale_bot_token_persist,
    upsert_bale_chat_id=_upsert_bale_chat_id_persist,
    clear_bale_credentials=_clear_bale_credentials_persist,
    upsert_drive_folder_id=queue.upsert_drive_folder_id,
    upsert_drive_sa_path=queue.upsert_drive_sa_path,
    upsert_drive_oauth_path=queue.upsert_drive_oauth_path,
    clear_drive_credentials=queue.clear_drive_credentials,
    log_event=log_event,
)


async def show_transfer_menu_handler(client: Client, message: Message):
    await handle_show_transfer_menu(TRANSFER_HUB_DEPS, client, message)


async def show_plan_menu_handler(client: Client, message: Message):
    uid = message.from_user.id
    set_menu_section(uid, MenuSection.PLAN)
    await message.reply_text(
        tr(uid, "plan_menu_opened"),
        reply_markup=build_plan_menu(uid),
        parse_mode=None,
    )


async def show_settings_menu_handler(client: Client, message: Message):
    uid = message.from_user.id
    set_menu_section(uid, MenuSection.SETTINGS)
    await message.reply_text(
        tr(uid, "settings_menu_title"),
        reply_markup=build_settings_menu(uid),
        parse_mode=None,
    )


async def show_toolkit_menu_handler(client: Client, message: Message):
    await handle_show_toolkit_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_toolkit_network_menu_handler(client: Client, message: Message):
    await handle_show_toolkit_network_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_toolkit_crypto_menu_handler(client: Client, message: Message):
    await handle_show_toolkit_crypto_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_toolkit_calc_menu_handler(client: Client, message: Message):
    await handle_show_toolkit_calc_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_calc_finance_menu_handler(client: Client, message: Message):
    await handle_show_calc_finance_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_calc_numbers_menu_handler(client: Client, message: Message):
    await handle_show_calc_numbers_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_calc_convert_menu_handler(client: Client, message: Message):
    await handle_show_calc_convert_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_calc_math_menu_handler(client: Client, message: Message):
    await handle_show_calc_math_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_calc_text_menu_handler(client: Client, message: Message):
    await handle_show_calc_text_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_calc_other_menu_handler(client: Client, message: Message):
    await handle_show_calc_other_menu(TOOLKIT_MENU_DEPS, client, message)


async def show_rubika_menu_handler(client: Client, message: Message):
    await handle_show_rubika_menu_hub(TRANSFER_HUB_DEPS, client, message)


async def show_bale_menu_handler(client: Client, message: Message):
    await handle_show_bale_menu(TRANSFER_HUB_DEPS, client, message)


async def show_drive_menu_handler(client: Client, message: Message):
    await handle_show_drive_menu(TRANSFER_HUB_DEPS, client, message)


async def show_ssh_menu_handler(client: Client, message: Message):
    await handle_show_ssh_menu(TRANSFER_HUB_DEPS, client, message)


async def show_files_menu_handler(client: Client, message: Message):
    await handle_show_files_menu_hub(TRANSFER_HUB_DEPS, client, message)


async def bale_status_handler(client: Client, message: Message):
    await handle_bale_status(TRANSFER_HUB_DEPS, client, message)


async def bale_set_chat_handler(client: Client, message: Message):
    await handle_bale_set_chat(
        TRANSFER_HUB_DEPS,
        client,
        message,
        set_state_preserving_menu=set_state_preserving_menu,
    )


async def bale_connect_handler(client: Client, message: Message):
    await handle_bale_connect(PROVIDER_CONNECT_DEPS, client, message)


async def bale_disconnect_handler(client: Client, message: Message):
    await handle_bale_disconnect(PROVIDER_CONNECT_DEPS, client, message)


async def drive_connect_handler(client: Client, message: Message):
    await handle_drive_connect(PROVIDER_CONNECT_DEPS, client, message)


async def drive_disconnect_handler(client: Client, message: Message):
    await handle_drive_disconnect(PROVIDER_CONNECT_DEPS, client, message)


async def drive_status_handler(client: Client, message: Message):
    await handle_drive_status(TRANSFER_HUB_DEPS, client, message)


async def drive_ls_handler(client: Client, message: Message):
    await handle_drive_ls(TRANSFER_HUB_DEPS, client, message)


async def ssh_list_handler(client: Client, message: Message):
    await handle_ssh_list(TRANSFER_HUB_DEPS, client, message)


async def ssh_add_handler(client: Client, message: Message):
    await handle_ssh_add(TRANSFER_HUB_DEPS, client, message)


async def ssh_add_wizard_handler(client: Client, message: Message):
    await start_ssh_add_wizard(SSH_WIZARD_DEPS, message)


async def ssh_op_wizard_handler(client: Client, message: Message, op: str = "ls"):
    await start_ssh_op_wizard(SSH_WIZARD_DEPS, message, op)


async def ssh_ls_handler(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        await start_ssh_op_wizard(SSH_WIZARD_DEPS, message, "ls")
        return
    await handle_ssh_ls(TRANSFER_HUB_DEPS, client, message)


async def ssh_del_handler(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        await start_ssh_op_wizard(SSH_WIZARD_DEPS, message, "del")
        return
    await handle_ssh_del(TRANSFER_HUB_DEPS, client, message)


async def ssh_put_handler(client: Client, message: Message):
    from v2.handlers.transfer_hub_commands import handle_ssh_put_command

    parts = (message.text or "").split()
    if len(parts) < 3:
        await start_ssh_op_wizard(SSH_WIZARD_DEPS, message, "put")
        return
    await handle_ssh_put_command(
        TRANSFER_HUB_DEPS,
        client,
        message,
        set_state_preserving_menu=set_state_preserving_menu,
    )


async def drive_download_handler(client: Client, message: Message):
    from v2.handlers.transfer_hub_commands import handle_drive_download_command

    await handle_drive_download_command(
        TRANSFER_HUB_DEPS,
        client,
        message,
        push_task_direct=push_task_direct,
        set_state_preserving_menu=set_state_preserving_menu,
    )


async def ssh_get_handler(client: Client, message: Message):
    from v2.handlers.transfer_hub_commands import handle_ssh_get_command

    parts = (message.text or "").split()
    if len(parts) < 3:
        await start_ssh_op_wizard(SSH_WIZARD_DEPS, message, "get")
        return
    await handle_ssh_get_command(
        TRANSFER_HUB_DEPS,
        client,
        message,
        push_task_direct=push_task_direct,
    )


async def start_handler(client: Client, message: Message):
    await handle_start(BASIC_COMMAND_DEPS, client, message)


async def menu_handler(client: Client, message: Message):
    await handle_menu(BASIC_COMMAND_DEPS, client, message)


async def lang_handler(client: Client, message: Message):
    await handle_lang(BASIC_COMMAND_DEPS, client, message)


async def help_handler(client: Client, message: Message):
    await handle_help(BASIC_COMMAND_DEPS, client, message)


async def log_help_handler(client: Client, message: Message):
    await handle_log_help(BASIC_COMMAND_DEPS, client, message)


async def version_handler(client: Client, message: Message):
    await handle_version(BASIC_COMMAND_DEPS, client, message)


async def rubika_status_handler(client: Client, message: Message):
    await handle_rubika_status(SESSION_SETTINGS_COMMAND_DEPS, client, message)


async def rubika_connect_handler(client: Client, message: Message):
    await handle_rubika_connect(SESSION_SETTINGS_COMMAND_DEPS, client, message)


async def direct_mode_handler(client: Client, message: Message):
    await handle_direct_mode(DIRECT_SEND_COMMAND_DEPS, client, message)


async def show_link_direct_menu_handler(client: Client, message: Message):
    await handle_show_link_direct_menu(LINK_DIRECT_COMMAND_DEPS, client, message)


async def show_cloudflare_menu_handler(client: Client, message: Message):
    await handle_show_cloudflare_menu(CLOUDFLARE_COMMAND_DEPS, client, message)


async def cf_connect_handler(client: Client, message: Message):
    await handle_cf_connect(CLOUDFLARE_COMMAND_DEPS, client, message)


async def cf_disconnect_handler(client: Client, message: Message):
    await handle_cf_disconnect(CLOUDFLARE_COMMAND_DEPS, client, message)


async def cf_status_handler(client: Client, message: Message):
    await handle_cf_status(CLOUDFLARE_COMMAND_DEPS, client, message)


async def cf_zones_handler(client: Client, message: Message):
    await handle_cf_zones(CLOUDFLARE_COMMAND_DEPS, client, message)


async def cf_dns_handler(client: Client, message: Message):
    await handle_cf_dns(CLOUDFLARE_COMMAND_DEPS, client, message)


async def netstatus_handler(client: Client, message: Message):
    await handle_netstatus(SESSION_SETTINGS_COMMAND_DEPS, client, message)


def failed_count() -> int:
    if not FAILED_FILE.exists():
        return 0
    try:
        with open(FAILED_FILE, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _run_admin_cleanup_downloads() -> tuple[int, int]:
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
    return n, freed


ADMIN_COMMAND_DEPS = AdminCommandDeps(
    admin_ids=frozenset(ADMIN_IDS),
    tr=tr,
    set_menu_section=set_menu_section,
    build_admin_menu=build_admin_menu,
    load_network_snapshot=partial(load_network_snapshot, NETWORK_FILE),
    queue_count=queue.queue_count,
    queue_cancelled_count=queue.cancelled_count,
    queue_deleted_count=queue.deleted_count,
    failed_count=failed_count,
    max_file_mb_display=max_file_mb_display,
    admin_disk_report_text=admin_disk_report_text,
    set_user_tier=set_user_tier,
    add_bonus_month_mb=add_bonus_month_mb,
    run_admin_cleanup_downloads=_run_admin_cleanup_downloads,
    list_v2_payments_for_user=lambda uid, lim: queue.list_v2_payments_for_user(uid, limit=lim),
    get_v2_payment_by_id=queue.get_v2_payment_by_id,
    update_v2_payment_status=lambda pid, st, ref: queue.update_v2_payment_status(
        pid, st, ref_id=ref
    ),
    maybe_grant_after_paid=lambda pid: maybe_grant_plan_after_paid(queue, pid),
    run_billing_reconcile=lambda: run_reconcile(
        queue,
        pending_max_age_sec=BILLING_RECONCILE_PENDING_MAX_AGE_SEC,
    ),
    set_state_preserving_menu=set_state_preserving_menu,
    list_users=queue.list_users,
    count_users=queue.count_users,
    get_user_info=queue.get_user_info,
    get_usage_snapshot=get_usage_snapshot,
    log_event=log_event,
    delete_v2_user_prefs=queue.delete_v2_user_prefs,
)


def _list_known_chat_ids() -> list[int]:
    data = load_json(KNOWN_CHATS_FILE, {"ids": []})
    out = []
    for x in data.get("ids", []):
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out


def _list_expiring_user_ids(days: int) -> list[int]:
    from user_entitlements import list_expiring_paid_tiers

    rows = list_expiring_paid_tiers(within_sec=max(1, int(days)) * 86400, limit=5000)
    return [int(r["user_id"]) for r in rows]


def _admin_job_summary(job_id: str) -> str:
    jid = (job_id or "").strip()
    if not jid:
        return ""
    for task in queue.all_tasks():
        if str(task.get("job_id") or "") == jid:
            return (
                f"job_id: {jid}\n"
                f"status: queued\n"
                f"type: {task.get('type')}\n"
                f"user: {task.get('telegram_user_id')}\n"
                f"session: {task.get('session_name')}\n"
                f"file: {task.get('file_name') or task.get('path') or '-'}"
            )
    # failed / deleted markers
    try:
        from pathlib import Path as _P
        failed = QUEUE_DIR / "failed.json"
        if failed.is_file():
            import json as _json
            rows = _json.loads(failed.read_text(encoding="utf-8") or "[]")
            for row in rows:
                if str(row.get("job_id") or "") == jid:
                    return f"job_id: {jid}\nstatus: failed\nerror: {row.get('error')}"
    except Exception:
        pass
    return ""


ADMIN_OPS_DEPS = AdminOpsDeps(
    admin_ids=frozenset(ADMIN_IDS),
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    build_admin_broadcast_menu=build_admin_broadcast_menu,
    build_admin_menu=build_admin_menu,
    list_known_chat_ids=_list_known_chat_ids,
    list_activity_user_ids=queue.list_activity_user_ids,
    list_new_user_ids=queue.list_new_user_ids,
    list_inactive_user_ids=queue.list_inactive_user_ids,
    list_tier_user_ids=lambda tier: __import__("user_entitlements", fromlist=["list_tier_user_ids"]).list_tier_user_ids(tier),
    list_expiring_user_ids=_list_expiring_user_ids,
    list_expired_user_ids=lambda: __import__("user_entitlements", fromlist=["list_expired_paid_user_ids"]).list_expired_paid_user_ids(),
    count_users=queue.count_users,
    tier_counts=lambda: __import__("user_entitlements", fromlist=["tier_counts"]).tier_counts(),
    service_unit="tele2rub",
    queue_dir=QUEUE_DIR,
    base_dir=BASE_DIR,
    log_event=log_event,
    get_job_summary=_admin_job_summary,
)


async def admin_stats_handler(client: Client, message: Message):
    await handle_admin_stats(ADMIN_OPS_DEPS, client, message)


async def admin_service_status_handler(client: Client, message: Message):
    await handle_admin_service_status(ADMIN_OPS_DEPS, client, message)


async def admin_tail_logs_handler(client: Client, message: Message):
    await handle_admin_tail_logs(ADMIN_OPS_DEPS, client, message)


async def admin_job_help_handler(client: Client, message: Message):
    await handle_admin_job_help(ADMIN_OPS_DEPS, client, message)


async def show_admin_broadcast_menu_handler(client: Client, message: Message):
    await handle_show_admin_broadcast_menu(ADMIN_OPS_DEPS, client, message)


async def admin_broadcast_seg_handler(client: Client, message: Message, segment: str):
    await start_broadcast_segment(ADMIN_OPS_DEPS, message, segment)

QUEUE_COMMAND_DEPS = QueueCommandDeps(
    tr=tr,
    set_menu_section=set_menu_section,
    enqueue_rubika_text_message=lambda message, text: enqueue_rubika_text_message(message, text),
    extract_first_url=extract_first_url,
    get_user_session=get_user_session,
    queue_count_by_session=queue.queue_count_by_session,
    count_tasks_for_user=queue.count_tasks_for_user,
    processing_display_for_queue=processing_display_for_queue,
    failed_count=failed_count,
    queue_deleted_count=queue.deleted_count,
    queue_cancelled_count=queue.cancelled_count,
    queue_all_tasks=queue.all_tasks,
    queue_remove_tasks_by_session=queue.remove_tasks_by_session,
    queue_remove_tasks_for_user=queue.remove_tasks_for_user,
    mark_deleted=mark_deleted,
)

DELETE_COMMAND_DEPS = DeleteCommandDeps(
    queue_all_tasks=queue.all_tasks,
    queue_remove_task=queue.remove_task,
    was_deleted=was_deleted,
    cancel_job=cancel_job,
    mark_deleted=mark_deleted,
)

BATCH_COMMAND_DEPS = BatchCommandDeps(
    tr=tr,
    set_batch=set_batch,
    get_batch=get_batch,
    set_menu_section=set_menu_section,
    build_files_menu=build_files_menu,
    set_state_preserving_menu=set_state_preserving_menu,
)


async def enqueue_rubika_text_message(message: Message, text_body: str) -> None:
    user_id = message.from_user.id
    session_name = get_user_session(user_id)
    if not session_name:
        from v2.core.connect_cta import connect_keyboard
        await message.reply_text(
            tr(user_id, "rubika_not_connected"),
            reply_markup=connect_keyboard(rubika=True),
        )
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
) -> bool:
    user_id = message.from_user.id
    task["telegram_user_id"] = user_id
    if get_direct_mode_target(user_id):
        if not await gate_quota(message, user_id, task):
            return False
        anchor = status_message
        if anchor:
            task["chat_id"] = message.chat.id
            task["status_message_id"] = anchor.id
            try:
                await anchor.edit_text(tr(user_id, "text_queueing"), parse_mode=None)
            except Exception:
                pass
            pushed = queue.push_task(task)
            qpos = queue.count_tasks_for_user(user_id)
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
            return True

        status = await message.reply_text(tr(user_id, "queued_processing"))
        task["chat_id"] = message.chat.id
        task["status_message_id"] = status.id
        pushed = queue.push_task(task)
        qpos = queue.count_tasks_for_user(user_id)
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
        return True

    from v2.handlers.confirm_state import set_pending_confirm

    set_pending_confirm(user_id, task)
    set_state_preserving_menu(
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
            [InlineKeyboardButton(tr(user_id, "btn_confirm_send"), callback_data="confirm_send")],
            [InlineKeyboardButton(tr(user_id, "btn_cancel_send"), callback_data="cancel_send")],
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
    return True


async def push_task_direct(
    message: Message,
    task: dict,
    status_message: Optional[Message] = None,
) -> bool:
    """Queue non-Rubika transfer tasks immediately (Bale, Drive, SSH)."""
    user_id = message.from_user.id
    task["telegram_user_id"] = user_id
    task["chat_id"] = message.chat.id
    if not await gate_quota(message, user_id, task):
        return False
    anchor = status_message
    if not anchor:
        anchor = await message.reply_text(tr(user_id, "text_queueing"), parse_mode=None)
    task["status_message_id"] = anchor.id
    pushed = queue.push_task(task)
    qpos = queue.count_tasks_for_user(user_id)
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
    st = get_state(user_id)
    if st.get("step") == "await_ssh_put_file":
        clear_state(user_id)
    return True


SSH_WIZARD_DEPS = SshWizardDeps(
    tr=tr,
    base_dir=BASE_DIR,
    get_state=get_state,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    ssh_add_server=queue.add_ssh_server,
    build_ssh_menu=build_ssh_menu,
    list_ssh_servers=queue.list_ssh_servers,
    get_ssh_server=queue.get_ssh_server,
    ssh_delete_server=queue.delete_ssh_server,
    push_task_direct=push_task_direct,
    safe_delete_user_message=safe_delete_user_message,
)


async def edit_wizard(chat_id: int, wizard_message_id: int, text: str):
    try:
        await app.edit_message_text(chat_id=chat_id, message_id=wizard_message_id, text=text)
    except Exception:
        pass


async def admin_handler(client: Client, message: Message):
    await handle_admin_panel(ADMIN_COMMAND_DEPS, client, message)


async def usage_handler(client: Client, message: Message):
    await handle_usage(PLAN_COMMAND_DEPS, client, message)


async def plan_handler(client: Client, message: Message):
    await handle_plan(PLAN_COMMAND_DEPS, client, message)


async def purchase_handler(client: Client, message: Message):
    await handle_purchase(PLAN_COMMAND_DEPS, client, message)


async def dns_lookup_handler(client: Client, message: Message):
    await handle_dns_lookup(TOOLKIT_COMMAND_DEPS, client, message)


async def my_ip_handler(client: Client, message: Message):
    await handle_my_ip(TOOLKIT_COMMAND_DEPS, client, message)


async def tcp_ping_handler(client: Client, message: Message):
    await handle_tcp_ping(TOOLKIT_COMMAND_DEPS, client, message)


async def ipinfo_handler(client: Client, message: Message):
    await handle_ipinfo(TOOLKIT_COMMAND_DEPS, client, message)


async def whois_handler(client: Client, message: Message):
    await handle_whois(TOOLKIT_COMMAND_DEPS, client, message)


async def my_id_handler(client: Client, message: Message):
    await handle_my_id(TOOLKIT_COMMAND_DEPS, client, message)


async def google_search_handler(client: Client, message: Message):
    await handle_google_search(TOOLKIT_COMMAND_DEPS, client, message)


async def google_image_search_handler(client: Client, message: Message):
    await handle_google_search(TOOLKIT_COMMAND_DEPS, client, message)


async def md5_handler(client: Client, message: Message):
    await handle_md5(TOOLKIT_COMMAND_DEPS, client, message)


async def sha256_handler(client: Client, message: Message):
    await handle_sha256(TOOLKIT_COMMAND_DEPS, client, message)


async def b64_encode_handler(client: Client, message: Message):
    await handle_b64_encode(TOOLKIT_COMMAND_DEPS, client, message)


async def b64_decode_handler(client: Client, message: Message):
    await handle_b64_decode(TOOLKIT_COMMAND_DEPS, client, message)


async def http_headers_handler(client: Client, message: Message):
    await handle_http_headers(TOOLKIT_NET_EXTRA_DEPS, client, message)


async def website_status_handler(client: Client, message: Message):
    await handle_website_status(TOOLKIT_NET_EXTRA_DEPS, client, message)


async def port_check_handler(client: Client, message: Message):
    await handle_port_check(TOOLKIT_NET_EXTRA_DEPS, client, message)


async def subnet_calc_handler(client: Client, message: Message):
    await handle_subnet_calc(TOOLKIT_NET_EXTRA_DEPS, client, message)


async def blacklist_check_handler(client: Client, message: Message):
    await handle_blacklist_check(TOOLKIT_NET_EXTRA_DEPS, client, message)


async def ssl_check_handler(client: Client, message: Message):
    await handle_ssl_check(TOOLKIT_NET_EXTRA_DEPS, client, message)


async def show_world_menu_handler(client: Client, message: Message):
    uid = message.from_user.id
    set_menu_section(uid, MenuSection.WORLD)
    await message.reply_text(
        tr(uid, "world_menu_title"),
        reply_markup=build_world_menu(uid),
        parse_mode=None,
    )


async def world_weather_handler(client: Client, message: Message):
    await start_weather_wizard(WORLD_COMMAND_DEPS, message)


async def world_calendar_handler(client: Client, message: Message):
    await handle_calendar(WORLD_COMMAND_DEPS, client, message)


async def world_currency_handler(client: Client, message: Message):
    await start_currency_wizard(WORLD_COMMAND_DEPS, message)


async def world_markets_handler(client: Client, message: Message):
    await handle_markets(WORLD_COMMAND_DEPS, client, message)


async def world_gold_handler(client: Client, message: Message):
    await handle_markets(WORLD_COMMAND_DEPS, client, message, board="gold")


async def world_usd_handler(client: Client, message: Message):
    await handle_markets(WORLD_COMMAND_DEPS, client, message, board="usd")


async def world_eur_handler(client: Client, message: Message):
    await handle_markets(WORLD_COMMAND_DEPS, client, message, board="eur")


async def world_gbp_handler(client: Client, message: Message):
    await handle_markets(WORLD_COMMAND_DEPS, client, message, board="gbp")


async def world_jpy_handler(client: Client, message: Message):
    await handle_markets(WORLD_COMMAND_DEPS, client, message, board="jpy")


async def world_majors_handler(client: Client, message: Message):
    await handle_markets(WORLD_COMMAND_DEPS, client, message, board="majors")


async def calc_percent_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "percent")


async def calc_loan_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "loan")


async def calc_deposit_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "deposit")


async def calc_rial_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "rial")


async def calc_words_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "words")


async def calc_unit_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "unit")


async def calc_base_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "base")


async def calc_binary_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "binary")


async def calc_fuel_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "fuel")


async def calc_plate_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "plate")


async def calc_nid_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "nid")


async def calc_datediff_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "datediff")


async def calc_dateconv_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "dateconv")


async def calc_random_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "random")


async def calc_mean_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "mean")


async def calc_power_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "power")


async def calc_sqrt_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "sqrt")


async def calc_fact_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "fact")


async def calc_prime_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "prime")


async def calc_ielts_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "ielts")


async def calc_cig_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "cig")


async def calc_rect_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "rect")


async def calc_square_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "square")


async def calc_case_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "case")


async def calc_wordcount_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "wordcount")

async def calc_bmi_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "bmi")


async def calc_compound_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "compound")


async def calc_log_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "log")


async def calc_pct_error_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "pct_error")


async def calc_linear_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "linear")


async def calc_quadratic_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "quadratic")


async def calc_add_days_handler(client: Client, message: Message):
    await run_calc_command(CALC_KIT_DEPS, message, "add_days")






async def world_quake_handler(client: Client, message: Message):
    await handle_earthquakes(WORLD_COMMAND_DEPS, client, message)


async def world_time_handler(client: Client, message: Message):
    await start_timezone_wizard(WORLD_COMMAND_DEPS, message)


async def world_age_handler(client: Client, message: Message):
    await start_age_wizard(WORLD_COMMAND_DEPS, message)


async def world_rss_handler(client: Client, message: Message):
    await start_add_feed_wizard(FEED_READER_DEPS, message)


async def world_rss_list_handler(client: Client, message: Message):
    await list_feeds_inline(FEED_READER_DEPS, message)


async def show_feed_menu_handler(client: Client, message: Message):
    uid = message.from_user.id
    set_menu_section(uid, MenuSection.FEED)
    await message.reply_text(
        tr(uid, "feed_section_opened"),
        reply_markup=build_feed_menu(uid),
        parse_mode=None,
    )
    await handle_show_feed_menu(FEED_READER_DEPS, client, message)


async def feed_add_handler(client: Client, message: Message):
    await start_add_feed_wizard(FEED_READER_DEPS, message)


async def feed_help_handler(client: Client, message: Message):
    uid = message.from_user.id
    set_menu_section(uid, MenuSection.FEED)
    await message.reply_text(tr(uid, "feed_help_body"), parse_mode=None)


async def plan_compare_handler(client: Client, message: Message):
    await handle_plan_compare(PLAN_COMMAND_DEPS, client, message)


async def password_handler(client: Client, message: Message):
    await handle_password(TOOLKIT_EXTRA_DEPS, client, message)


async def reverse_dns_handler(client: Client, message: Message):
    await handle_reverse_dns(TOOLKIT_EXTRA_DEPS, client, message)


async def url_expand_handler(client: Client, message: Message):
    await handle_url_expand(TOOLKIT_EXTRA_DEPS, client, message)


async def timestamp_handler(client: Client, message: Message):
    await handle_timestamp(TOOLKIT_EXTRA_DEPS, client, message)


async def lorem_handler(client: Client, message: Message):
    await handle_lorem(TOOLKIT_EXTRA_DEPS, client, message)


async def mac_lookup_handler(client: Client, message: Message):
    await handle_mac_lookup(TOOLKIT_EXTRA_DEPS, client, message)


async def email_check_handler(client: Client, message: Message):
    await handle_email_check(TOOLKIT_EXTRA_DEPS, client, message)


async def admin_tier_handler(client: Client, message: Message):
    await handle_admin_tier(ADMIN_COMMAND_DEPS, client, message)


async def admin_bonus_handler(client: Client, message: Message):
    await handle_admin_bonus(ADMIN_COMMAND_DEPS, client, message)


async def cleanup_downloads_handler(client: Client, message: Message):
    await handle_cleanup_downloads(ADMIN_COMMAND_DEPS, client, message)


async def admin_payment_lookup_handler(client: Client, message: Message):
    await handle_admin_payment_lookup(ADMIN_COMMAND_DEPS, client, message)


async def admin_payment_status_handler(client: Client, message: Message):
    await handle_admin_payment_status(ADMIN_COMMAND_DEPS, client, message)


async def admin_users_list_handler(client: Client, message: Message):
    await handle_admin_users_list(ADMIN_COMMAND_DEPS, client, message)


async def admin_reconcile_billing_handler(client: Client, message: Message):
    await handle_admin_reconcile_billing(ADMIN_COMMAND_DEPS, client, message)


async def admin_clear_prefs_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        await message.reply_text(tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply_text(
            "Usage: `/admin_clear_prefs <telegram_user_id>`",
            parse_mode=None,
        )
        return
    try:
        target = int(parts[1].strip())
    except ValueError:
        await message.reply_text("Invalid user id.", parse_mode=None)
        return
    try:
        queue.delete_v2_user_prefs(target)
    except Exception as e:
        log_event("admin_clear_prefs_failed", admin_id=uid, target=target, error=str(e))
        await message.reply_text(f"DB error: {e}", parse_mode=None)
        return
    log_event("admin_clear_prefs_ok", admin_id=uid, target=target)
    await message.reply_text(f"OK: cleared v2_user_prefs for `{target}`", parse_mode=None)


async def admin_clear_state_mirrors_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        await message.reply_text(tr(uid, "admin_denied"))
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply_text(
            "Usage: `/admin_clear_state_mirrors <telegram_user_id>`",
            parse_mode=None,
        )
        return
    try:
        target = int(parts[1].strip())
    except ValueError:
        await message.reply_text("Invalid user id.", parse_mode=None)
        return
    try:
        queue.delete_user_state_mirror(target)
        queue.delete_batch_session_mirror(target)
    except Exception as e:
        log_event("admin_clear_state_mirrors_failed", admin_id=uid, target=target, error=str(e))
        await message.reply_text(f"DB error: {e}", parse_mode=None)
        return
    log_event("admin_clear_state_mirrors_ok", admin_id=uid, target=target)
    await message.reply_text(
        f"OK: cleared `v2_user_state_mirror` + `v2_batch_session_mirror` for `{target}` (JSON unchanged).",
        parse_mode=None,
    )


async def safemode_handler(client: Client, message: Message):
    await handle_safemode(SAFEMODE_COMMAND_DEPS, client, message)


async def clear_queue_handler(client: Client, message: Message, acting_user_id: Optional[int] = None):
    await handle_clear_queue(QUEUE_COMMAND_DEPS, client, message, acting_user_id=acting_user_id)

async def new_batch_handler(client: Client, message: Message):
    await handle_new_batch(BATCH_COMMAND_DEPS, client, message)


async def done_batch_handler(client: Client, message: Message):
    await handle_done_batch(BATCH_COMMAND_DEPS, client, message)


async def imenu_handler(client: Client, message: Message):
    uid = message.from_user.id
    await show_inline_menu(INLINE_MENU_DEPS, client, message, uid, "main", edit=False)


async def callback_handler(client: Client, callback_query):
    uid = callback_query.from_user.id if callback_query.from_user else 0
    log_interaction(
        "user_callback",
        user_id=uid,
        data=callback_query.data or "",
        message_id=callback_query.message.id if callback_query.message else None,
    )
    if await dispatch_admin_inline_callbacks(ADMIN_COMMAND_DEPS, client, callback_query):
        return

    handled = await dispatch_callback_route(client, callback_query, CALLBACK_ROUTE_DEPS)
    if handled:
        return
    await callback_query.answer("این گزینه منقضی شده یا معتبر نیست.", show_alert=True)


async def send_text_handler(client: Client, message: Message):
    await handle_send_text(QUEUE_COMMAND_DEPS, client, message)


async def send_link_handler(client: Client, message: Message):
    await handle_send_link(QUEUE_COMMAND_DEPS, client, message)


async def queue_manage_handler(
    client: Client,
    message: Message,
    edit_existing: bool = False,
    target_user_id: Optional[int] = None,
):
    await handle_queue_manage(
        QUEUE_COMMAND_DEPS,
        client,
        message,
        edit_existing=edit_existing,
        target_user_id=target_user_id,
    )


async def delete_one_handler(client: Client, message: Message):
    await handle_delete_one(DELETE_COMMAND_DEPS, client, message)


def _zip_password_waiting(user_id: int | None = None) -> bool:
    if user_id is None:
        return bool(waiting_for_zip_password_users)
    return int(user_id) in waiting_for_zip_password_users


def _set_zip_password_waiting(v: bool, user_id: int | None = None) -> None:
    if user_id is None:
        if not v:
            waiting_for_zip_password_users.clear()
        return
    uid = int(user_id)
    if v:
        waiting_for_zip_password_users.add(uid)
    else:
        waiting_for_zip_password_users.discard(uid)


REPLY_ROUTE_DEPS = ReplyRouteDeps(
    admin_ids=frozenset(ADMIN_IDS),
    tr=tr,
    set_menu_section=set_menu_section,
    set_state_preserving_menu=set_state_preserving_menu,
    menu_handler=menu_handler,
    help_handler=help_handler,
    log_help_handler=log_help_handler,
    version_handler=version_handler,
    cleanup_downloads_handler=cleanup_downloads_handler,
    admin_reconcile_billing_handler=admin_reconcile_billing_handler,
    admin_users_list_handler=admin_users_list_handler,
    rubika_connect_handler=rubika_connect_handler,
    rubika_status_handler=rubika_status_handler,
    bale_status_handler=bale_status_handler,
    bale_connect_handler=bale_connect_handler,
    bale_disconnect_handler=bale_disconnect_handler,
    bale_set_chat_handler=bale_set_chat_handler,
    drive_status_handler=drive_status_handler,
    drive_connect_handler=drive_connect_handler,
    drive_disconnect_handler=drive_disconnect_handler,
    drive_download_handler=drive_download_handler,
    drive_ls_handler=drive_ls_handler,
    ssh_list_handler=ssh_list_handler,
    ssh_add_wizard_handler=ssh_add_wizard_handler,
    ssh_op_wizard_handler=ssh_op_wizard_handler,
    ssh_ls_handler=ssh_ls_handler,
    ssh_del_handler=ssh_del_handler,
    new_batch_handler=new_batch_handler,
    done_batch_handler=done_batch_handler,
    clear_queue_handler=clear_queue_handler,
    queue_manage_handler=queue_manage_handler,
    netstatus_handler=netstatus_handler,
    admin_handler=admin_handler,
    direct_mode_handler=direct_mode_handler,
    plan_handler=plan_handler,
    usage_handler=usage_handler,
    purchase_handler=purchase_handler,
    show_transfer_menu_handler=show_transfer_menu_handler,
    show_toolkit_menu_handler=show_toolkit_menu_handler,
    show_toolkit_network_menu_handler=show_toolkit_network_menu_handler,
    show_toolkit_crypto_menu_handler=show_toolkit_crypto_menu_handler,
    show_toolkit_calc_menu_handler=show_toolkit_calc_menu_handler,
    show_calc_finance_menu_handler=show_calc_finance_menu_handler,
    show_calc_numbers_menu_handler=show_calc_numbers_menu_handler,
    show_calc_convert_menu_handler=show_calc_convert_menu_handler,
    show_calc_math_menu_handler=show_calc_math_menu_handler,
    show_calc_text_menu_handler=show_calc_text_menu_handler,
    show_calc_other_menu_handler=show_calc_other_menu_handler,
    show_rubika_menu_handler=show_rubika_menu_handler,
    show_bale_menu_handler=show_bale_menu_handler,
    show_drive_menu_handler=show_drive_menu_handler,
    show_ssh_menu_handler=show_ssh_menu_handler,
    show_files_menu_handler=show_files_menu_handler,
    show_link_direct_menu_handler=show_link_direct_menu_handler,
    show_cloudflare_menu_handler=show_cloudflare_menu_handler,
    dns_lookup_handler=dns_lookup_handler,
    my_ip_handler=my_ip_handler,
    tcp_ping_handler=tcp_ping_handler,
    ipinfo_handler=ipinfo_handler,
    whois_handler=whois_handler,
    my_id_handler=my_id_handler,
    google_search_handler=google_search_handler,
    google_image_search_handler=google_image_search_handler,
    md5_handler=md5_handler,
    sha256_handler=sha256_handler,
    b64_encode_handler=b64_encode_handler,
    b64_decode_handler=b64_decode_handler,
    cf_connect_handler=cf_connect_handler,
    cf_status_handler=cf_status_handler,
    cf_zones_handler=cf_zones_handler,
    cf_dns_handler=cf_dns_handler,
    cf_disconnect_handler=cf_disconnect_handler,
    build_plan_menu=build_plan_menu,
    build_transfer_menu=build_transfer_menu,
    build_toolkit_menu=build_toolkit_menu,
    build_rubika_menu=build_rubika_menu,
    build_files_menu=build_files_menu,
    build_settings_menu=build_settings_menu,
    build_admin_menu=build_admin_menu,
    build_admin_users_menu=build_admin_users_menu,
    build_admin_billing_menu=build_admin_billing_menu,
    build_toolkit_zip_menu=build_toolkit_zip_menu,
    build_admin_maintenance_menu=build_admin_maintenance_menu,
    build_admin_broadcast_menu=build_admin_broadcast_menu,
    build_world_menu=build_world_menu,
    show_world_menu_handler=show_world_menu_handler,
    extra_slash_handlers={
        "/httpheaders": http_headers_handler,
        "/webstatus": website_status_handler,
        "/portcheck": port_check_handler,
        "/subnet": subnet_calc_handler,
        "/blacklist": blacklist_check_handler,
        "/sslcheck": ssl_check_handler,
        "/world_weather": world_weather_handler,
        "/world_calendar": world_calendar_handler,
        "/world_currency": world_currency_handler,
        "/world_alerts": world_alerts_handler,
        "/world_markets": world_markets_handler,
        "/world_gold": world_gold_handler,
        "/world_usd": world_usd_handler,
        "/world_eur": world_eur_handler,
        "/world_gbp": world_gbp_handler,
        "/world_jpy": world_jpy_handler,
        "/world_majors": world_majors_handler,
        "/calc_percent": calc_percent_handler,
        "/calc_loan": calc_loan_handler,
        "/calc_deposit": calc_deposit_handler,
        "/calc_rial": calc_rial_handler,
        "/calc_words": calc_words_handler,
        "/calc_unit": calc_unit_handler,
        "/calc_base": calc_base_handler,
        "/calc_binary": calc_binary_handler,
        "/calc_fuel": calc_fuel_handler,
        "/calc_plate": calc_plate_handler,
        "/calc_nid": calc_nid_handler,
        "/calc_datediff": calc_datediff_handler,
        "/calc_dateconv": calc_dateconv_handler,
        "/calc_random": calc_random_handler,
        "/calc_mean": calc_mean_handler,
        "/calc_power": calc_power_handler,
        "/calc_sqrt": calc_sqrt_handler,
        "/calc_fact": calc_fact_handler,
        "/calc_prime": calc_prime_handler,
        "/calc_ielts": calc_ielts_handler,
        "/calc_cig": calc_cig_handler,
        "/calc_rect": calc_rect_handler,
        "/calc_square": calc_square_handler,
        "/calc_case": calc_case_handler,
        "/calc_wordcount": calc_wordcount_handler,
        "/world_quake": world_quake_handler,
        "/world_time": world_time_handler,
        "/world_age": world_age_handler,
        "/world_rss": world_rss_handler,
        "/world_rss_list": world_rss_list_handler,
        "/show_feed_menu": show_feed_menu_handler,
        "/feed_add": feed_add_handler,
        "/feeds": world_rss_list_handler,
        "/feed_help": feed_help_handler,
        "/admin_stats": admin_stats_handler,
        "/admin_service_status": admin_service_status_handler,
        "/admin_tail_logs": admin_tail_logs_handler,
        "/admin_job_help": admin_job_help_handler,
        "/show_admin_broadcast_menu": show_admin_broadcast_menu_handler,
        "/admin_broadcast_seg_all": lambda c, m: admin_broadcast_seg_handler(c, m, "all"),
        "/admin_broadcast_seg_known": lambda c, m: admin_broadcast_seg_handler(c, m, "known"),
        "/admin_broadcast_seg_new7": lambda c, m: admin_broadcast_seg_handler(c, m, "new7"),
        "/admin_broadcast_seg_guest": lambda c, m: admin_broadcast_seg_handler(c, m, "guest"),
        "/admin_broadcast_seg_free": lambda c, m: admin_broadcast_seg_handler(c, m, "free"),
        "/admin_broadcast_seg_pro": lambda c, m: admin_broadcast_seg_handler(c, m, "pro"),
        "/admin_broadcast_seg_star": lambda c, m: admin_broadcast_seg_handler(c, m, "star"),
        "/admin_broadcast_seg_expiring7": lambda c, m: admin_broadcast_seg_handler(c, m, "expiring7"),
        "/admin_broadcast_seg_expired": lambda c, m: admin_broadcast_seg_handler(c, m, "expired"),
        "/admin_broadcast_seg_inactive30": lambda c, m: admin_broadcast_seg_handler(c, m, "inactive30"),
        "/plan_compare": plan_compare_handler,
        "/password": password_handler,
        "/revdns": reverse_dns_handler,
        "/urlexpand": url_expand_handler,
        "/timestamp": timestamp_handler,
        "/lorem": lorem_handler,
        "/maclookup": mac_lookup_handler,
        "/emailcheck": email_check_handler,
    },
    show_feed_menu_handler=show_feed_menu_handler,
)

async def _save_drive_sa_file(user_id: int, local_path: Path) -> tuple[bool, str]:
    return await save_drive_sa_from_downloaded_file(PROVIDER_CONNECT_DEPS, user_id, local_path)


RUBIKA_WIZARD_DEPS = RubikaWizardDeps(
    tr=tr,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    get_user_key=get_user_key,
    load_users=load_users,
    save_users=save_users,
    log_event=log_event,
    persist_rubika_session=_persist_rubika_session_prefs,
    rubika_send_code=rubika_send_code,
    rubika_sign_in=rubika_sign_in,
    deep_find_phone_hash=_deep_find_phone_hash,
    deep_find_status=_deep_find_status,
)

ZIP_BATCH_WIZARD_DEPS = ZipBatchWizardDeps(
    tr=tr,
    safe_filename=safe_filename,
    safe_delete_user_message=safe_delete_user_message,
    edit_wizard=edit_wizard,
    set_state_preserving_menu=set_state_preserving_menu,
    clear_state=clear_state,
    clear_batch=clear_batch,
    load_settings=load_settings,
    make_bundle_zip_local=make_bundle_zip_local,
    effective_max_file_bytes=effective_max_file_bytes,
    effective_max_mb_display=effective_max_mb_display,
    fmt_mb_bytes=fmt_mb_bytes,
    gate_quota=gate_quota,
    get_user_session=get_user_session,
    pretty_size=pretty_size,
    queue_or_confirm=queue_or_confirm,
)

ZIP_PASSWORD_DEPS = ZipPasswordPromptDeps(
    get_waiting_for_password=_zip_password_waiting,
    set_waiting_for_password=_set_zip_password_waiting,
    tr=tr,
    load_settings=load_settings,
    save_settings=save_settings,
)

SAFEMODE_COMMAND_DEPS = SafeModeCommandDeps(
    tr=tr,
    load_settings=load_settings,
    save_settings=save_settings,
    set_waiting_for_zip_password=_set_zip_password_waiting,
)

LINK_DIRECT_HANDLER_DEPS = LinkDirectHandlerDeps(
    tr=tr,
    base_dir=BASE_DIR,
    download_dir=DOWNLOAD_DIR,
    queue=queue,
    extract_first_url=extract_first_url,
    get_menu_section=get_effective_menu_section,
    get_user_session=get_user_session,
    load_settings=load_settings,
    effective_max_file_bytes=effective_max_file_bytes,
    effective_max_mb_display=effective_max_mb_display,
    fmt_mb_bytes=fmt_mb_bytes,
    pretty_size=pretty_size,
    gate_quota=gate_quota,
    queue_or_confirm=queue_or_confirm,
    push_task_direct=push_task_direct,
    log_event=log_event,
)


async def _link_dest_callback_route(client: Client, callback_query, dest: str) -> bool:
    return await handle_link_dest_callback(LINK_DIRECT_HANDLER_DEPS, client, callback_query, dest)


INLINE_MENU_DEPS = InlineMenuDeps(
    tr=tr,
    admin_ids=frozenset(ADMIN_IDS),
    miniapp_base_url=MINIAPP_BASE_URL,
    get_direct_mode_target=get_direct_mode_target,
    set_direct_mode_target=set_direct_mode_target,
    set_state_preserving_menu=set_state_preserving_menu,
    direct_mode_handler=direct_mode_handler,
    netstatus_handler=netstatus_handler,
    plan_handler=plan_handler,
    usage_handler=usage_handler,
    purchase_handler=purchase_handler,
    help_handler=help_handler,
    my_id_handler=my_id_handler,
    world_deps=WORLD_COMMAND_DEPS,
    feed_reader_deps=FEED_READER_DEPS,
    show_rubika_menu_handler=show_rubika_menu_handler,
    show_bale_menu_handler=show_bale_menu_handler,
    show_drive_menu_handler=show_drive_menu_handler,
    show_files_menu_handler=show_files_menu_handler,
    show_link_direct_menu_handler=show_link_direct_menu_handler,
    admin_handler=admin_handler,
    plan_compare_handler=plan_compare_handler,
    show_feed_menu_handler=show_feed_menu_handler,
    calc_kit_deps=CALC_KIT_DEPS,
    show_transfer_menu_handler=show_transfer_menu_handler,
    show_toolkit_menu_handler=show_toolkit_menu_handler,
    show_world_menu_handler=show_world_menu_handler,
    show_plan_menu_handler=show_plan_menu_handler,
    show_settings_menu_handler=show_settings_menu_handler,
)


async def _media_dest_callback_route(client: Client, callback_query, dest: str) -> bool:
    from v2.handlers.media_handler import _download_and_queue

    user_id = callback_query.from_user.id

    async def _queue_after_dest_pick(client, message, user_id, **kwargs):
        await _download_and_queue(client, message, user_id, deps=MEDIA_HANDLER_DEPS, **kwargs)

    mdest = MediaDestHandlerDeps(
        tr=tr,
        base_dir=BASE_DIR,
        queue=queue,
        get_user_session=get_user_session,
        get_direct_mode_target=get_direct_mode_target,
        get_menu_section=get_effective_menu_section,
        download_and_queue_media=_queue_after_dest_pick,
    )
    return await handle_media_dest_callback(mdest, client, callback_query, dest)


async def _imenu_callback_route(client: Client, callback_query, key: str) -> bool:
    return await dispatch_inline_menu_callback(INLINE_MENU_DEPS, client, callback_query, key)


async def _feed_callback_route(
    client: Client, callback_query, action: str, feed_id: int
) -> bool:
    return await handle_feed_callback(FEED_READER_DEPS, client, callback_query, action, feed_id)


async def _cf_menu_callback_route(client: Client, callback_query, action: str) -> bool:
    return await dispatch_cf_menu_callback(CLOUDFLARE_COMMAND_DEPS, client, callback_query, action)


async def _drive_auth_callback_route(client: Client, callback_query, action: str) -> bool:
    return await dispatch_drive_auth_callback(PROVIDER_CONNECT_DEPS, client, callback_query, action)


def google_oauth_http_callback(telegram_user_id: int, code: str) -> tuple[bool, str]:
    """Called from mini-app HTTP thread after Google redirects with ?code=&state=."""
    ok, err = connect_drive_with_auth_code(
        BASE_DIR,
        telegram_user_id,
        code,
        queue.upsert_drive_oauth_path,
    )
    if not ok:
        return False, err

    async def _notify() -> None:
        await notify_oauth_success(
            app,
            telegram_user_id,
            tr,
            set_state_preserving_menu=set_state_preserving_menu,
            clear_state=clear_state,
        )

    try:
        import asyncio

        asyncio.run_coroutine_threadsafe(_notify(), app.loop)
    except Exception:
        pass
    return True, ""



async def _cta_callback_route(client: Client, callback_query, action: str) -> bool:
    await callback_query.answer()
    msg = callback_query.message
    msg.from_user = callback_query.from_user
    if action == "rubika_connect":
        await rubika_connect_handler(client, msg)
    elif action == "bale_connect":
        await bale_connect_handler(client, msg)
    elif action == "drive_connect":
        await drive_connect_handler(client, msg)
    elif action == "cf_connect":
        await cf_connect_handler(client, msg)
    elif action == "direct_menu":
        uid = callback_query.from_user.id
        set_menu_section(uid, MenuSection.SETTINGS)
        await msg.reply_text(
            tr(uid, "settings_menu_title"),
            reply_markup=build_settings_menu(uid),
            parse_mode=None,
        )
    elif action == "transfer_menu":
        await show_transfer_menu_handler(client, msg)
    elif action == "netstatus":
        await netstatus_handler(client, msg)
    elif action == "purchase":
        await purchase_handler(client, msg)
    return True


async def _calc_mode_callback_route(client: Client, callback_query, tool: str, mode: str) -> bool:
    from v2.handlers.calc_kit_commands import handle_calc_mode_callback
    return await handle_calc_mode_callback(CALC_KIT_DEPS, client, callback_query, tool, mode)


async def _fx_from_callback_route(client: Client, callback_query, code: str) -> bool:
    uid = callback_query.from_user.id
    state = get_state(uid)
    amount = state.get("amount")
    if not amount:
        await callback_query.answer("amount?", show_alert=True)
        return True
    set_state_preserving_menu(uid, {"step": "await_currency_to", "amount": amount, "from_code": code.upper()})
    await callback_query.answer()
    await callback_query.message.reply_text(tr(uid, "currency_ask_to"), parse_mode=None)
    return True


CALLBACK_ROUTE_DEPS = CallbackRouteDeps(
    tr=tr,
    get_state=get_state,
    set_lang=set_lang,
    set_menu_section_main=lambda user_id: set_menu_section(user_id, MenuSection.MAIN),
    build_main_menu=build_main_menu,
    queue_manage_handler=queue_manage_handler,
    clear_queue_handler=clear_queue_handler,
    get_user_session=get_user_session,
    queue_count_by_session=queue.queue_count_by_session,
    count_tasks_for_user=queue.count_tasks_for_user,
    failed_count=failed_count,
    recent_failed_detail_text=recent_failed_detail_text,
    recent_jobs_summary=recent_jobs_summary,
    gate_quota=gate_quota,
    queue_push_task=queue.push_task,
    clear_state=clear_state,
    log_event=log_event,
    handle_link_dest_callback=_link_dest_callback_route,
    handle_link_quality_callback=lambda c, cq, q: handle_link_quality_callback(LINK_DIRECT_HANDLER_DEPS, c, cq, q),
    handle_media_dest_callback=_media_dest_callback_route,
    dispatch_inline_menu_callback=_imenu_callback_route,
    handle_feed_callback=_feed_callback_route,
    handle_fx_quick_callback=lambda c, cq, a, fc, tc: handle_fx_quick_callback(
        WORLD_COMMAND_DEPS, c, cq, a, fc, tc
    ),
    dispatch_cf_menu_callback=_cf_menu_callback_route,
    handle_cf_dns_zone_callback=lambda c, cq, zid: handle_cf_dns_zone_callback(
        CLOUDFLARE_COMMAND_DEPS, c, cq, zid
    ),
    handle_cf_dns_add_zone_callback=lambda c, cq, zid: handle_cf_dns_add_zone_callback(
        CLOUDFLARE_COMMAND_DEPS, c, cq, zid
    ),
    handle_cf_dns_del_zone_callback=lambda c, cq, zid: handle_cf_dns_del_zone_callback(
        CLOUDFLARE_COMMAND_DEPS, c, cq, zid
    ),
    handle_cf_dns_delete_callback=lambda c, cq, rid: handle_cf_dns_delete_callback(
        CLOUDFLARE_COMMAND_DEPS, c, cq, rid
    ),
    handle_ssh_op_callback=lambda c, cq, op, sid: handle_ssh_op_callback(
        SSH_WIZARD_DEPS, c, cq, op, sid
    ),
    dispatch_drive_auth_callback=_drive_auth_callback_route,
    handle_cta_callback=_cta_callback_route,
    handle_calc_mode_callback=_calc_mode_callback_route,
    handle_fx_from_callback=_fx_from_callback_route,
    handle_fx_calc_callback=lambda c, cq, p: handle_fx_calc_callback(WORLD_COMMAND_DEPS, c, cq, p),
    handle_ssh_auth_callback=lambda c, cq, m: handle_ssh_auth_callback(SSH_WIZARD_DEPS, c, cq, m),
    handle_clear_chat_callback=lambda c, cq, a: handle_clear_chat_callback(CLEAR_CHAT_DEPS, c, cq, a),
    handle_alert_kind_callback=lambda c, cq, k: handle_alert_kind_callback(ALERT_COMMAND_DEPS, c, cq, k),
    handle_alert_schedule_callback=lambda c, cq, s: handle_alert_schedule_callback(ALERT_COMMAND_DEPS, c, cq, s),
    handle_alert_hour_callback=lambda c, cq, h: handle_alert_hour_callback(ALERT_COMMAND_DEPS, c, cq, h),
    handle_alert_spike_callback=lambda c, cq, s: handle_alert_spike_callback(ALERT_COMMAND_DEPS, c, cq, s),
    handle_alert_manage_callback=lambda c, cq, a, i, e=None: handle_alert_manage_callback(
        ALERT_COMMAND_DEPS, c, cq, a, i, e
    ),
    handle_market_page_callback=lambda c, cq, b, p: handle_market_page_callback(
        WORLD_COMMAND_DEPS, c, cq, b, p
    ),
    handle_quake_mag_callback=lambda c, cq, m: handle_quake_mag_callback(
        WORLD_COMMAND_DEPS, c, cq, m
    ),
    handle_alert_quake_mag_callback=lambda c, cq, m: handle_alert_quake_mag_callback(
        ALERT_COMMAND_DEPS, c, cq, m
    ),
)


DIRECT_MODE_TEXT_DEPS = DirectModeTextDeps(
    tr=tr,
    get_direct_mode_target=get_direct_mode_target,
    get_user_session=get_user_session,
    extract_first_url=extract_first_url,
    gate_quota=gate_quota,
    push_task=queue.push_task,
    queue_count_by_session=queue.queue_count_by_session,
    handle_link_direct_for_direct_mode=lambda msg, uid, url, dest: handle_link_direct_for_direct_mode(
        LINK_DIRECT_HANDLER_DEPS, msg, uid, url, dest
    ),
    log_event=log_event,
)

DIRECT_URL_HINT_DEPS = DirectUrlHintDeps(
    tr=tr,
    extract_first_url=extract_first_url,
    is_direct_url=is_direct_url,
)

TEXT_ENTRY_DEPS = TextEntryDeps(
    tr=tr,
    get_state=get_state,
    set_menu_section=set_menu_section,
    build_plan_menu=build_plan_menu,
    resolve_reply_button_route=menu_engine.resolve_reply_button_route,
    dispatch_reply_keyboard_route=dispatch_reply_keyboard_route,
    reply_route_deps=REPLY_ROUTE_DEPS,
    clear_state=clear_state,
    toolkit_network_light_enabled=TOOLKIT_NETWORK_LIGHT,
    toolkit_quota_try=_toolkit_quota_try,
    toolkit_quota_commit=_toolkit_quota_commit,
    enqueue_rubika_text_message=enqueue_rubika_text_message,
    dispatch_rubika_connect_wizard=dispatch_rubika_connect_wizard,
    rubika_wizard_deps=RUBIKA_WIZARD_DEPS,
    dispatch_provider_connect_wizard=dispatch_provider_connect_wizard,
    provider_connect_wizard_deps=PROVIDER_CONNECT_DEPS,
    dispatch_cloudflare_wizard=dispatch_cloudflare_wizard,
    cloudflare_command_deps=CLOUDFLARE_COMMAND_DEPS,
    dispatch_admin_wizard=dispatch_admin_wizard,
    admin_command_deps=ADMIN_COMMAND_DEPS,
    dispatch_admin_ops_wizard=dispatch_admin_ops_wizard,
    admin_ops_deps=ADMIN_OPS_DEPS,
    set_state_preserving_menu=set_state_preserving_menu,
    dispatch_zip_batch_wizard=dispatch_zip_batch_wizard,
    zip_batch_wizard_deps=ZIP_BATCH_WIZARD_DEPS,
    handle_zip_password_text=handle_zip_password_text,
    zip_password_deps=ZIP_PASSWORD_DEPS,
    handle_direct_mode_plain_text=handle_direct_mode_plain_text,
    direct_mode_text_deps=DIRECT_MODE_TEXT_DEPS,
    handle_direct_url_sendlink_hint=handle_direct_url_sendlink_hint,
    direct_url_hint_deps=DIRECT_URL_HINT_DEPS,
    handle_link_direct_text=handle_link_direct_text,
    link_direct_deps=LINK_DIRECT_HANDLER_DEPS,
    build_main_menu=build_main_menu,
    dispatch_world_wizard=dispatch_world_wizard,
    dispatch_calc_wizard=dispatch_calc_wizard,
    dispatch_alert_wizard=dispatch_alert_wizard,
    alert_command_deps=ALERT_COMMAND_DEPS,
    calc_kit_deps=CALC_KIT_DEPS,
    dispatch_feed_wizard=dispatch_feed_wizard,
    feed_reader_deps=FEED_READER_DEPS,
    dispatch_toolkit_net_extra_wizard=dispatch_toolkit_net_extra_wizard,
    toolkit_net_extra_deps=TOOLKIT_NET_EXTRA_DEPS,
    dispatch_ssh_wizard=dispatch_ssh_wizard,
    ssh_wizard_deps=SSH_WIZARD_DEPS,
    world_command_deps=WORLD_COMMAND_DEPS,
    toolkit_utility_light_enabled=TOOLKIT_UTILITY_LIGHT,
    get_direct_mode_target=get_direct_mode_target,
    set_direct_mode_target=set_direct_mode_target,
)

MEDIA_HANDLER_DEPS = MediaHandlerDeps(
    tr=tr,
    base_dir=BASE_DIR,
    queue=queue,
    get_user_session=get_user_session,
    get_menu_section=get_effective_menu_section,
    get_direct_mode_target=get_direct_mode_target,
    get_bale_credentials=queue.get_bale_credentials,
    get_state=get_state,
    set_state_preserving_menu=set_state_preserving_menu,
    save_drive_sa_file=_save_drive_sa_file,
    get_ssh_server=queue.get_ssh_server,
    ssh_wizard_deps=SSH_WIZARD_DEPS,
    get_media=get_media,
    build_download_filename=build_download_filename,
    download_dir=DOWNLOAD_DIR,
    download_progress=download_progress,
    effective_max_file_bytes=effective_max_file_bytes,
    effective_max_mb_display=effective_max_mb_display,
    fmt_mb_bytes=fmt_mb_bytes,
    load_settings=load_settings,
    get_batch=get_batch,
    set_batch=set_batch,
    pretty_size=pretty_size,
    queue_or_confirm=queue_or_confirm,
    push_task_direct=push_task_direct,
    log_event=log_event,
)


def _touch_user_activity(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    try:
        queue.record_user_activity(
            user.id,
            first_name=user.first_name or "",
            username=user.username or "",
        )
    except Exception as e:
        log_event(
            "record_user_activity_failed",
            user_id=user.id,
            error=str(e),
        )


async def text_handler(client: Client, message: Message):
    _touch_user_activity(message)
    uid = message.from_user.id if message.from_user else 0
    section = get_effective_menu_section(uid) if uid else None
    mapped = menu_engine.resolve_reply_button_route(
        message.text or "", uid, tr, menu_section=section
    )
    log_interaction(
        "user_text",
        user_id=uid,
        chat_id=message.chat.id if message.chat else None,
        text=message.text or "",
        menu_section=section,
        mapped_route=mapped,
        message_id=message.id,
    )
    await handle_text_entry(TEXT_ENTRY_DEPS, client, message)


async def media_handler(client: Client, message: Message):
    _touch_user_activity(message)
    await handle_media_message(MEDIA_HANDLER_DEPS, client, message)


register_handlers(app)


def clear_old_status():
    try:
        if STATUS_FILE.exists():
            STATUS_FILE.unlink()
    except Exception:
        pass

if __name__ == "__main__":
    from v2.bot.startup import run_bot

    run_bot()
