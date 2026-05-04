"""Menu rendering helpers for incremental v2 extraction."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from pyrogram.types import KeyboardButton, ReplyKeyboardMarkup

Translator = Callable[[int, str], str]

# Maps trimmed lowercase reply text -> pseudo-route consumed by telebot text_handler.
_REPLY_BUTTON_ROUTE_MAP: Dict[str, str] = {
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


def resolve_reply_button_route(text: str) -> Optional[str]:
    """Return internal route token for a reply-keyboard label, or None."""
    return _REPLY_BUTTON_ROUTE_MAP.get(text.strip().lower())


def _reply(rows: List[List[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(label) for label in row] for row in rows],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_main_menu(user_id: int, tr: Translator, is_admin: bool) -> ReplyKeyboardMarkup:
    rows: List[List[str]] = [
        [tr(user_id, "btn_main_plan_section")],
        [tr(user_id, "btn_main_connection"), tr(user_id, "btn_main_files")],
        [tr(user_id, "btn_main_settings"), tr(user_id, "btn_main_help")],
        [tr(user_id, "btn_main_net"), tr(user_id, "btn_main_queue")],
    ]
    if is_admin:
        rows.append([tr(user_id, "btn_main_admin")])
    return _reply(rows)


def build_plan_menu(user_id: int, tr: Translator) -> ReplyKeyboardMarkup:
    rows = [
        ["/plan", "/usage"],
        ["/queue", "/purchase"],
        [tr(user_id, "btn_back_main")],
    ]
    return _reply(rows)


def build_rubika_menu(user_id: int, tr: Translator) -> ReplyKeyboardMarkup:
    rows = [
        [tr(user_id, "btn_rub_connect"), tr(user_id, "btn_rub_status")],
        [tr(user_id, "btn_back_main")],
    ]
    return _reply(rows)


def build_files_menu(user_id: int, tr: Translator) -> ReplyKeyboardMarkup:
    rows = [
        [tr(user_id, "btn_main_plan_section")],
        [tr(user_id, "btn_zip_start"), tr(user_id, "btn_zip_end")],
        [tr(user_id, "btn_send_content")],
        [tr(user_id, "btn_queue"), tr(user_id, "btn_clear_all")],
        [tr(user_id, "btn_back_main")],
    ]
    return _reply(rows)


def build_settings_menu(user_id: int, tr: Translator) -> ReplyKeyboardMarkup:
    rows = [
        [tr(user_id, "btn_direct_on"), tr(user_id, "btn_direct_off")],
        [tr(user_id, "btn_back_main")],
    ]
    return _reply(rows)


def build_admin_menu(user_id: int, tr: Translator) -> ReplyKeyboardMarkup:
    rows = [
        [tr(user_id, "btn_main_plan_section")],
        [tr(user_id, "btn_admin_panel"), "/admin", "/version"],
        [tr(user_id, "btn_back_main")],
    ]
    return _reply(rows)
