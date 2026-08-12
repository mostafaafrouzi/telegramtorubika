"""SQLite store for paid market/weather/quake alert subscriptions."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

_DB = Path(__file__).resolve().parents[2] / "queue" / "alert_subscriptions.sqlite3"

KINDS = frozenset({"fx", "gold", "weather", "quake"})
SCHEDULES = frozenset({"hourly", "daily", "weekly", "event", "none"})
TRIGGERS = frozenset({"schedule", "spike", "event"})
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
    if "min_mag" not in cols:
        c.execute("ALTER TABLE alert_subscriptions ADD COLUMN min_mag REAL")
        c.execute(
            """
            UPDATE alert_subscriptions
            SET min_mag = spike_pct, spike_pct = NULL
            WHERE kind = 'quake' AND spike_pct IS NOT NULL
              AND (min_mag IS NULL)
            """
        )
    if "trigger" not in cols:
        c.execute(
            "ALTER TABLE alert_subscriptions ADD COLUMN trigger TEXT NOT NULL DEFAULT 'schedule'"
        )
        # Migrate: fx/gold with spike_pct → both behaviors approximated as spike+schedule
        c.execute(
            """
            UPDATE alert_subscriptions
            SET trigger = 'spike'
            WHERE kind IN ('fx','gold') AND spike_pct IS NOT NULL
              AND schedule = 'hourly'
            """
        )
        c.execute(
            """
            UPDATE alert_subscriptions
            SET trigger = 'event', schedule = 'event'
            WHERE kind = 'quake'
            """
        )
    if "last_event_ids" not in cols:
        c.execute(
            "ALTER TABLE alert_subscriptions ADD COLUMN last_event_ids TEXT NOT NULL DEFAULT ''"
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
    min_mag: Optional[float] = None,
    hour_tehran: Optional[int] = None,
    trigger: str = "schedule",
) -> tuple[bool, str, int]:
    kind = (kind or "").lower().strip()
    schedule = (schedule or "daily").lower().strip()
    trigger = (trigger or "schedule").lower().strip()
    if kind not in KINDS:
        return False, "bad_kind", 0
    if schedule not in SCHEDULES:
        return False, "bad_schedule", 0
    if trigger not in TRIGGERS:
        return False, "bad_trigger", 0
    if count_user(user_id) >= 20:
        return False, "limit", 0
    hour = _default_hour() if hour_tehran is None else max(0, min(23, int(hour_tehran)))
    spike_val = float(spike_pct) if spike_pct is not None else None
    mag_val = float(min_mag) if min_mag is not None else None
    if kind == "quake":
        trigger = "event"
        schedule = "event"
        if mag_val is None and spike_val is not None:
            mag_val = spike_val
        spike_val = None
    elif trigger == "spike":
        schedule = "none"
    elif trigger == "schedule":
        spike_val = None
        if schedule in ("event", "none"):
            schedule = "daily"
    conn = _conn()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO alert_subscriptions
            (user_id, kind, asset, schedule, spike_pct, enabled, last_sent_at,
             created_at, hour_tehran, muted_until, min_mag, trigger, last_event_ids)
            VALUES (?,?,?,?,?,1,0,?,?,0,?,?, '')
            """,
            (
                int(user_id),
                kind,
                (asset or "").strip()[:800],
                schedule,
                spike_val,
                time.time(),
                hour,
                mag_val,
                trigger,
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
    until = 0.0 if float(hours) <= 0 else time.time() + float(hours) * 3600.0
    conn = _conn()
    with conn:
        cur = conn.execute(
            "UPDATE alert_subscriptions SET muted_until=? WHERE id=? AND user_id=?",
            (until, int(alert_id), int(user_id)),
        )
    conn.close()
    return cur.rowcount > 0


def unmute_alert(user_id: int, alert_id: int) -> bool:
    return mute_alert(user_id, alert_id, hours=0)


def quake_min_mag(row: dict[str, Any], default: float = 4.0) -> float:
    if row.get("min_mag") is not None:
        try:
            return float(row["min_mag"])
        except (TypeError, ValueError):
            pass
    if (row.get("kind") or "") == "quake" and row.get("spike_pct") is not None:
        try:
            return float(row["spike_pct"])
        except (TypeError, ValueError):
            pass
    return float(default)


def parse_event_ids(raw: str) -> list[str]:
    s = (raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            return [str(x) for x in json.loads(s)]
        except json.JSONDecodeError:
            pass
    return [x for x in s.split(",") if x]


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
        trigger = (d.get("trigger") or "schedule").lower()
        # Legacy quake rows
        if (d.get("kind") or "") == "quake" and trigger == "schedule":
            trigger = "event"
        d["_trigger"] = trigger
        hour = d.get("hour_tehran")
        if hour is None:
            hour = _default_hour()
        else:
            hour = int(hour)
        d["_hour_tehran"] = hour

        if sched in ("event", "none") or trigger in ("spike", "event"):
            schedule_due = False
            interval = 0
        elif sched == "hourly":
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
        else:
            interval = 86400
            last_dt = _tehran_now(last) if last > 0 else None
            already_today = last_dt is not None and last_dt.date() == tehran.date()
            schedule_due = (tehran.hour == hour) and not already_today

        # Legacy: schedule trigger with spike_pct still allows spike
        d["_interval"] = interval
        d["_schedule_due"] = schedule_due and trigger == "schedule"
        d["_allow_spike"] = trigger == "spike" or (
            trigger == "schedule" and d.get("spike_pct") is not None and sched not in ("event", "none")
        )
        # Actually user wants SEPARATE modes - schedule alerts never spike, spike never schedule
        if trigger == "schedule":
            d["_allow_spike"] = False
            d["_schedule_due"] = schedule_due
        elif trigger == "spike":
            d["_allow_spike"] = True
            d["_schedule_due"] = False
        elif trigger == "event":
            d["_allow_spike"] = False
            d["_schedule_due"] = False
            d["_event_due"] = True
        out.append(d)
    return out


def mark_sent(
    alert_id: int,
    *,
    price: Optional[float] = None,
    event_ids: Optional[list[str]] = None,
) -> None:
    conn = _conn()
    with conn:
        if event_ids is not None:
            # Keep last ~40 ids
            merged = list(dict.fromkeys(event_ids))[-40:]
            blob = json.dumps(merged, ensure_ascii=False)
            if price is None:
                conn.execute(
                    "UPDATE alert_subscriptions SET last_sent_at=?, last_event_ids=? WHERE id=?",
                    (time.time(), blob, int(alert_id)),
                )
            else:
                conn.execute(
                    """
                    UPDATE alert_subscriptions
                    SET last_sent_at=?, last_price=?, last_event_ids=? WHERE id=?
                    """,
                    (time.time(), float(price), blob, int(alert_id)),
                )
        elif price is None:
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
