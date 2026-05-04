"""Central Pyrogram handler registration (replaces @app.on_message / @app.on_callback_query).

Import ``telebot`` only inside ``register_handlers`` so the module finishes loading
before handlers are resolved (avoids circular import).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

if TYPE_CHECKING:
    from pyrogram import Client

# Commands handled by dedicated handlers; must stay aligned with ``text_handler`` logic in telebot.
_TEXT_EXCLUDED_COMMANDS = [
    "start",
    "menu",
    "lang",
    "help",
    "loghelp",
    "version",
    "rubika_status",
    "rubika_connect",
    "directmode",
    "netstatus",
    "admin",
    "safemode",
    "del",
    "delall",
    "newbatch",
    "done",
    "sendtext",
    "sendlink",
    "queue",
    "usage",
    "plan",
    "purchase",
    "dns",
    "myip",
    "ping",
    "md5",
    "sha256",
    "b64e",
    "b64d",
    "admin_tier",
    "admin_bonus",
    "admin_clear_prefs",
    "admin_clear_state_mirrors",
    "admin_payment_lookup",
    "admin_payment_status",
    "admin_reconcile_billing",
    "cleanup_downloads",
]

_MEDIA_FILTER = filters.private & (
    filters.document
    | filters.video
    | filters.audio
    | filters.voice
    | filters.photo
    | filters.animation
    | filters.video_note
    | filters.sticker
)


def register_handlers(app: Client, *, group: int = 0) -> None:
    import telebot as tb

    priv = filters.private
    cmd = filters.command

    def mh(callback, flt):
        app.add_handler(MessageHandler(callback, flt), group)

    mh(tb.start_handler, priv & cmd("start"))
    mh(tb.menu_handler, priv & cmd("menu"))
    mh(tb.lang_handler, priv & cmd("lang"))
    mh(tb.help_handler, priv & cmd("help"))
    mh(tb.log_help_handler, priv & cmd("loghelp"))
    mh(tb.version_handler, priv & cmd("version"))
    mh(tb.rubika_status_handler, priv & cmd("rubika_status"))
    mh(tb.rubika_connect_handler, priv & cmd("rubika_connect"))
    mh(tb.direct_mode_handler, priv & cmd("directmode"))
    mh(tb.netstatus_handler, priv & cmd("netstatus"))
    mh(tb.admin_handler, priv & cmd("admin"))
    mh(tb.usage_handler, priv & cmd("usage"))
    mh(tb.plan_handler, priv & cmd("plan"))
    mh(tb.purchase_handler, priv & cmd("purchase"))
    mh(tb.dns_lookup_handler, priv & cmd("dns"))
    mh(tb.my_ip_handler, priv & cmd("myip"))
    mh(tb.tcp_ping_handler, priv & cmd("ping"))
    mh(tb.md5_handler, priv & cmd("md5"))
    mh(tb.sha256_handler, priv & cmd("sha256"))
    mh(tb.b64_encode_handler, priv & cmd("b64e"))
    mh(tb.b64_decode_handler, priv & cmd("b64d"))
    mh(tb.admin_tier_handler, priv & cmd("admin_tier"))
    mh(tb.admin_bonus_handler, priv & cmd("admin_bonus"))
    mh(tb.admin_clear_prefs_handler, priv & cmd("admin_clear_prefs"))
    mh(tb.admin_clear_state_mirrors_handler, priv & cmd("admin_clear_state_mirrors"))
    mh(tb.admin_payment_lookup_handler, priv & cmd("admin_payment_lookup"))
    mh(tb.admin_payment_status_handler, priv & cmd("admin_payment_status"))
    mh(tb.admin_reconcile_billing_handler, priv & cmd("admin_reconcile_billing"))
    mh(tb.cleanup_downloads_handler, priv & cmd("cleanup_downloads"))
    mh(tb.safemode_handler, priv & cmd("safemode"))
    mh(tb.clear_queue_handler, priv & cmd("delall"))
    mh(tb.new_batch_handler, priv & cmd("newbatch"))
    mh(tb.done_batch_handler, priv & cmd("done"))
    mh(tb.send_text_handler, priv & cmd("sendtext"))
    mh(tb.send_link_handler, priv & cmd("sendlink"))
    mh(tb.queue_manage_handler, priv & cmd("queue"))
    mh(tb.delete_one_handler, priv & cmd("del"))
    mh(
        tb.text_handler,
        priv & filters.text & ~cmd(_TEXT_EXCLUDED_COMMANDS),
    )
    mh(tb.media_handler, _MEDIA_FILTER)

    app.add_handler(CallbackQueryHandler(tb.callback_handler), group)
