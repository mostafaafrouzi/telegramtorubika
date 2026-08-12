"""Free limited daily market digest (gold/USD); advanced alerts stay paid-only."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from v2.core.msg_format import send_formatted
from v2.toolkit.fx_light import market_digest_brief

_DB = Path(__file__).resolve().parents[2] / "queue" / "market_digest.sqlite3"
TranslateFn = Callable[..., str]
LogEventFn = Callable[..., None]


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB))
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS market_digest_sent (
            user_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            PRIMARY KEY (user_id, day_key)
        )
        """
    )
    return c


def _enabled() -> bool:
    raw = (os.getenv("MARKET_DIGEST_ENABLE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _hour_tehran() -> int:
    try:
        return max(0, min(23, int((os.getenv("MARKET_DIGEST_HOUR_TEHRAN") or "9").strip())))
    except ValueError:
        return 9


def _was_sent(user_id: int, day_key: str) -> bool:
    conn = _conn()
    row = conn.execute(
        "SELECT 1 FROM market_digest_sent WHERE user_id=? AND day_key=?",
        (int(user_id), day_key),
    ).fetchone()
    conn.close()
    return bool(row)


def _mark(user_id: int, day_key: str) -> None:
    conn = _conn()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO market_digest_sent(user_id, day_key) VALUES (?,?)",
            (int(user_id), day_key),
        )
    conn.close()


async def maybe_send_market_digest(
    client: Any,
    *,
    list_user_ids: Callable[[], list[int]],
    tr: TranslateFn,
    get_lang: Callable[[int], str] | None = None,
    log_event: LogEventFn | None = None,
) -> None:
    if not _enabled():
        return
    log = log_event or (lambda *a, **k: None)
    try:
        tehran = datetime.now(ZoneInfo("Asia/Tehran"))
    except Exception:
        return
    if tehran.hour != _hour_tehran():
        return
    day_key = tehran.strftime("%Y-%m-%d")
    try:
        uids = list_user_ids()
    except Exception:
        return
    # Cap free blast per cycle
    sent = 0
    for uid in uids[:500]:
        if _was_sent(uid, day_key):
            continue
        lang = "fa"
        if get_lang:
            try:
                lang = "en" if get_lang(uid) == "en" else "fa"
            except Exception:
                lang = "fa"
        ok, body = market_digest_brief(lang=lang)
        if not ok:
            continue
        try:
            await send_formatted(client, uid, body)
            _mark(uid, day_key)
            sent += 1
            log("market_digest_sent", user_id=uid)
        except Exception as e:
            log("market_digest_failed", user_id=uid, error=str(e)[:200])
        if sent >= 80:
            break
        # tiny pause
        if sent and sent % 10 == 0:
            time.sleep(0.2)
