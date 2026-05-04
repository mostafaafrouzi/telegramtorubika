"""Process entry: start client, background tasks, idle loop.

Uses lazy import of ``telebot`` so ``register_handlers(app)`` runs after handler
functions are defined (see ``v2.bot.register_handlers``).
"""

from __future__ import annotations

from pyrogram import idle


def run_bot() -> None:
    import telebot as tb

    tb.sync_v2_ephemeral_mirrors_from_json()
    if getattr(tb, "V2_EPHEMERAL_READ_PRIMARY_SQLITE", False):
        tb.log_event("v2_ephemeral_read_mode", primary="sqlite")
    tb.clear_old_status()
    tb.app.start()
    tb.app.loop.create_task(tb.status_watcher())
    tb.app.loop.create_task(tb.maybe_broadcast_update())
    tb.app.loop.create_task(tb.payment_reconcile_loop())
    idle()
    tb.app.stop()
