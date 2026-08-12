"""SQLite store for paid market/weather/quake alert subscriptions."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

_DB = Path(__file__).resolve().parents[2] / "queue" / "alert_subscriptions.sqlite3"

KINDS = frozenset({"fx", "gold", "weather", "quake"})
SCHEDULES = frozenset({"hourly", "daily", "weekly"})
_TEHRAN = ZoneInfo("Asia/Tehran")


def _default_hour() -> int:
    try:
        return max(0, min(23, int((os.getenv("ALERT_DEFAULT_HOUR_TEHRAN") or "9").strip())))
    except ValueError:
        return 9


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB))
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            asset TEXT NOT NULL DEFAULT '',
            schedule TEXT NOT NULL DEFAULT 'daily',
            spike_pct REAL,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_sent_at REAL NOT NULL DEFAULT 0,
            last_price REAL,
            created_at REAL NOT NULL
        )
        """
    )
    cols = {r[1] for r in c.execute("PRAGMA table_info(alert_subscriptions)")}
    if "hour_tehran" not in cols:
        c.execute(
            "ALTER TABLE alert_subscriptions ADD COLUMN hour_tehran INTEGER NOT NULL DEFAULT 9"
        )
    if "muted_until" not in cols:
        c.execute(
            "ALTER TABLE alert_subscriptions ADD COLUMN muted_until REAL NOT NULL DEFAULT 0"
        )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_alerts_user ON alert_subscriptions(user_id, enabled)"
    )
    return c


def count_user(user_id: int) -> int:
    conn = _conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM alert_subscriptions WHERE user_id=? AND enabled=1",
        (int(user_id),),
    ).fetchone()[0]
    conn.close()
    return int(n)


def add_alert(
    user_id: int,
    *,
    kind: str,
    asset: str,
    schedule: str = "daily",
    spike_pct: Optional[float] = None,
    hour_tehran: Optional[int] = None,
) -> tuple[bool, str, int]:
    kind = (kind or "").lower().strip()
    schedule = (schedule or "daily").lower().strip()
    if kind not in KINDS:
        return False, "bad_kind", 0
    if schedule not in SCHEDULES:
        return False, "bad_schedule", 0
    if count_user(user_id) >= 20:
        return False, "limit", 0
    hour = _default_hour() if hour_tehran is None else max(0, min(23, int(hour_tehran)))
    conn = _conn()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO alert_subscriptions
            (user_id, kind, asset, schedule, spike_pct, enabled, last_sent_at,
             created_at, hour_tehran, muted_until)
            VALUES (?,?,?,?,?,1,0,?,?,0)
            """,
            (
                int(user_id),
                kind,
                (asset or "").strip()[:120],
                schedule,
                float(spike_pct) if spike_pct is not None else None,
                time.time(),
                hour,
            ),
        )
        aid = int(cur.lastrowid or 0)
    conn.close()
    return True, "ok", aid


def list_alerts(user_id: int) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM alert_subscriptions WHERE user_id=? ORDER BY id DESC",
        (int(user_id),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alert(user_id: int, alert_id: int) -> Optional[dict[str, Any]]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM alert_subscriptions WHERE id=? AND user_id=?",
        (int(alert_id), int(user_id)),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_alert(user_id: int, alert_id: int) -> bool:
    conn = _conn()
    with conn:
        cur = conn.execute(
            "DELETE FROM alert_subscriptions WHERE id=? AND user_id=?",
            (int(alert_id), int(user_id)),
        )
    conn.close()
    return cur.rowcount > 0


def set_enabled(user_id: int, alert_id: int, enabled: bool) -> bool:
    conn = _conn()
    with conn:
        cur = conn.execute(
            "UPDATE alert_subscriptions SET enabled=? WHERE id=? AND user_id=?",
            (1 if enabled else 0, int(alert_id), int(user_id)),
        )
    conn.close()
    return cur.rowcount > 0


def toggle_enabled(user_id: int, alert_id: int) -> Optional[bool]:
    row = get_alert(user_id, alert_id)
    if not row:
        return None
    new_val = not bool(row.get("enabled"))
    set_enabled(user_id, alert_id, new_val)
    return new_val


def mute_alert(user_id: int, alert_id: int, hours: float = 24.0) -> bool:
    until = time.time() + max(0.0, float(hours)) * 3600.0
    conn = _conn()
    with conn:
        cur = conn.execute(
            "UPDATE alert_subscriptions SET muted_until=? WHERE id=? AND user_id=?",
            (until, int(alert_id), int(user_id)),
        )
    conn.close()
    return cur.rowcount > 0


def _tehran_now(ts: Optional[float] = None) -> datetime:
    if ts is None:
        return datetime.now(_TEHRAN)
    return datetime.fromtimestamp(float(ts), _TEHRAN)


def due_alerts(now: Optional[float] = None) -> list[dict[str, Any]]:
    now = now or time.time()
    tehran = _tehran_now(now)
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM alert_subscriptions WHERE enabled=1"
    ).fetchall()
    conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        muted_until = float(d.get("muted_until") or 0)
        d["_muted"] = muted_until > now
        last = float(d.get("last_sent_at") or 0)
        sched = d.get("schedule") or "daily"
        hour = d.get("hour_tehran")
        if hour is None:
            hour = _default_hour()
        else:
            hour = int(hour)
        d["_hour_tehran"] = hour

        if sched == "hourly":
            schedule_due = (now - last) >= 3600
            interval = 3600
        elif sched == "weekly":
            interval = 604800
            last_dt = _tehran_now(last) if last > 0 else None
            same_iso_week = (
                last_dt is not None
                and last_dt.isocalendar()[:2] == tehran.isocalendar()[:2]
            )
            schedule_due = (tehran.hour == hour) and not same_iso_week and (
                last <= 0 or (now - last) >= 6 * 86400
            )
        else:  # daily
            interval = 86400
            last_dt = _tehran_now(last) if last > 0 else None
            already_today = last_dt is not None and last_dt.date() == tehran.date()
            schedule_due = (tehran.hour == hour) and not already_today

        d["_interval"] = interval
        d["_schedule_due"] = schedule_due
        out.append(d)
    return out


def mark_sent(alert_id: int, *, price: Optional[float] = None) -> None:
    conn = _conn()
    with conn:
        if price is None:
            conn.execute(
                "UPDATE alert_subscriptions SET last_sent_at=? WHERE id=?",
                (time.time(), int(alert_id)),
            )
        else:
            conn.execute(
                "UPDATE alert_subscriptions SET last_sent_at=?, last_price=? WHERE id=?",
                (time.time(), float(price), int(alert_id)),
            )
    conn.close()
