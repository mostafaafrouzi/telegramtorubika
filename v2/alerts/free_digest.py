"""Opt-in free daily digest (one per user): FX market brief or weather."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from v2.core.msg_format import italic, join, send_formatted, title
from v2.toolkit.fx_light import market_digest_brief
from v2.toolkit.weather_light import weather_report

_DB = Path(__file__).resolve().parents[2] / "queue" / "free_digest.sqlite3"
_TEHRAN = ZoneInfo("Asia/Tehran")
KINDS = frozenset({"fx", "weather"})

TranslateFn = Callable[..., str]
LogEventFn = Callable[..., None]


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB))
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS free_digest_subs (
            user_id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            asset TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            hour_tehran INTEGER NOT NULL DEFAULT 9,
            last_sent_day TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        )
        """
    )
    return c


def _default_hour() -> int:
    try:
        return max(
            0,
            min(
                23,
                int(
                    (
                        os.getenv("FREE_DIGEST_HOUR_TEHRAN")
                        or os.getenv("MARKET_DIGEST_HOUR_TEHRAN")
                        or "9"
                    ).strip()
                ),
            ),
        )
    except ValueError:
        return 9


def get_sub(user_id: int) -> Optional[dict[str, Any]]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM free_digest_subs WHERE user_id=?", (int(user_id),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_sub(
    user_id: int,
    *,
    kind: str,
    asset: str = "",
    hour_tehran: Optional[int] = None,
) -> tuple[bool, str]:
    kind = (kind or "").lower().strip()
    if kind not in KINDS:
        return False, "bad_kind"
    hour = _default_hour() if hour_tehran is None else max(0, min(23, int(hour_tehran)))
    asset_s = (asset or "").strip()[:120]
    if kind == "fx":
        asset_s = asset_s or "USD"
    if kind == "weather" and not asset_s:
        return False, "need_city"
    conn = _conn()
    with conn:
        conn.execute(
            """
            INSERT INTO free_digest_subs
            (user_id, kind, asset, enabled, hour_tehran, last_sent_day, created_at)
            VALUES (?,?,?,1,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              kind=excluded.kind,
              asset=excluded.asset,
              enabled=1,
              hour_tehran=excluded.hour_tehran
            """,
            (int(user_id), kind, asset_s, hour, "", time.time()),
        )
    conn.close()
    return True, "ok"


def disable_sub(user_id: int) -> bool:
    conn = _conn()
    with conn:
        cur = conn.execute(
            "UPDATE free_digest_subs SET enabled=0 WHERE user_id=?",
            (int(user_id),),
        )
    conn.close()
    return cur.rowcount > 0


def delete_sub(user_id: int) -> bool:
    conn = _conn()
    with conn:
        cur = conn.execute(
            "DELETE FROM free_digest_subs WHERE user_id=?", (int(user_id),)
        )
    conn.close()
    return cur.rowcount > 0


def list_due(now: Optional[datetime] = None) -> list[dict[str, Any]]:
    tehran = now or datetime.now(_TEHRAN)
    day_key = tehran.strftime("%Y-%m-%d")
    hour = tehran.hour
    conn = _conn()
    rows = conn.execute(
        """
        SELECT * FROM free_digest_subs
        WHERE enabled=1 AND hour_tehran=? AND last_sent_day!=?
        """,
        (hour, day_key),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_sent(user_id: int, day_key: str) -> None:
    conn = _conn()
    with conn:
        conn.execute(
            "UPDATE free_digest_subs SET last_sent_day=? WHERE user_id=?",
            (day_key, int(user_id)),
        )
    conn.close()


def _enabled_env() -> bool:
    raw = (os.getenv("FREE_DIGEST_ENABLE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


async def maybe_send_free_digests(
    client: Any,
    *,
    get_lang: Callable[[int], str] | None = None,
    log_event: LogEventFn | None = None,
) -> int:
    """Send due free digests; return count sent."""
    if not _enabled_env():
        return 0
    log = log_event or (lambda *a, **k: None)
    try:
        tehran = datetime.now(_TEHRAN)
    except Exception:
        return 0
    day_key = tehran.strftime("%Y-%m-%d")
    due = list_due(tehran)
    sent = 0
    for row in due[:100]:
        uid = int(row["user_id"])
        kind = row.get("kind") or "fx"
        asset = (row.get("asset") or "").strip()
        lang = "fa"
        if get_lang:
            try:
                lang = "en" if get_lang(uid) == "en" else "fa"
            except Exception:
                lang = "fa"
        body = ""
        try:
            if kind == "weather":
                city = asset or "Tehran"
                ok, w = weather_report(city, lang=lang)
                if not ok:
                    continue
                head = (
                    title("🌤", f"Free daily weather — {city}")
                    if lang == "en"
                    else title("🌤", f"آب‌وهوای رایگان روزانه — {city}")
                )
                tip = (
                    italic("Upgrade for Pro alerts: /world_alerts")
                    if lang == "en"
                    else italic("برای هشدار پیشرفته Pro: /world_alerts")
                )
                body = join(head, w, tip)
            else:
                ok, body = market_digest_brief(lang=lang)
                if not ok:
                    continue
        except Exception as e:
            log("free_digest_build_failed", user_id=uid, error=str(e)[:200])
            continue
        try:
            await send_formatted(client, uid, body)
            mark_sent(uid, day_key)
            sent += 1
            log("free_digest_sent", user_id=uid, kind=kind)
        except Exception as e:
            log("free_digest_failed", user_id=uid, error=str(e)[:200])
        if sent and sent % 10 == 0:
            time.sleep(0.2)
    return sent


def summarize_sub(row: Optional[dict[str, Any]], *, lang: str = "fa") -> str:
    if not row or not row.get("enabled"):
        return "off" if lang == "en" else "غیرفعال"
    kind = row.get("kind") or "fx"
    hour = int(row.get("hour_tehran") or 9)
    asset = row.get("asset") or ""
    if lang == "en":
        if kind == "weather":
            return f"weather · {asset or 'Tehran'} · {hour:02d}:00 Tehran"
        return f"market brief · {hour:02d}:00 Tehran"
    if kind == "weather":
        return f"آب‌وهوا · {asset or 'Tehran'} · {hour:02d}:۰۰ تهران"
    return f"خلاصه بازار · {hour:02d}:۰۰ تهران"
