"""
Per-Telegram-user plan tiers, usage meters (day/month), and parallel job limits.
Uses the same SQLite file as the task queue. Successful uploads increment usage in rub.py.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

from queue_db import DB_FILE, QUEUE_DIR

PROCESSING_FILE = QUEUE_DIR / "processing.json"

DISABLE_USAGE_LIMITS = os.getenv("DISABLE_USAGE_LIMITS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

DEFAULT_TIER_FOR_NEW_USER = "free"

TIER_LIMITS: dict[str, dict[str, int]] = {
    "guest": {
        "quota_day_mb": 100,
        "quota_month_mb": 500,
        "max_file_mb": 50,
        "max_parallel": 1,
    },
    "free": {
        "quota_day_mb": 500,
        "quota_month_mb": 5000,
        "max_file_mb": 500,
        "max_parallel": 2,
    },
    "pro": {
        "quota_day_mb": 5000,
        "quota_month_mb": 50000,
        "max_file_mb": 2048,
        "max_parallel": 5,
    },
}


@dataclass
class ResolvedLimits:
    tier: str
    quota_day_mb: int
    quota_month_mb: int
    max_file_mb: int
    max_parallel: int
    expires_at: int


def _parse_env_max_file_mb() -> Optional[int]:
    raw = (os.getenv("MAX_FILE_MB") or "").strip()
    if not raw or raw == "0":
        return None
    try:
        mb = int(raw)
        if mb <= 0:
            return None
        return mb
    except ValueError:
        return None


class UsageTables:
    """SQLite: user_entitlements + usage_ledger."""

    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_entitlements (
                    user_id INTEGER PRIMARY KEY,
                    tier TEXT NOT NULL DEFAULT 'free',
                    expires_at INTEGER NOT NULL DEFAULT 0,
                    bonus_month_mb INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_ledger (
                    user_id INTEGER NOT NULL,
                    bucket TEXT NOT NULL,
                    bytes_total INTEGER NOT NULL DEFAULT 0,
                    jobs INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, bucket)
                )
                """
            )
            conn.commit()


_usage_singleton: Optional[UsageTables] = None


def usage_store() -> UsageTables:
    global _usage_singleton
    if _usage_singleton is None:
        _usage_singleton = UsageTables()
    return _usage_singleton


def _day_key(ts: Optional[float] = None) -> str:
    t = time.gmtime((ts or time.time()))
    return f"d:{t.tm_year:04d}{t.tm_mon:02d}{t.tm_mday:02d}"


def _month_key(ts: Optional[float] = None) -> str:
    t = time.gmtime((ts or time.time()))
    return f"m:{t.tm_year:04d}{t.tm_mon:02d}"


def _effective_tier(row: Optional[sqlite3.Row]) -> str:
    if not row:
        return DEFAULT_TIER_FOR_NEW_USER
    tier = (row["tier"] or DEFAULT_TIER_FOR_NEW_USER).strip().lower()
    if tier not in TIER_LIMITS:
        tier = DEFAULT_TIER_FOR_NEW_USER
    exp = int(row["expires_at"] or 0)
    if tier == "pro" and exp > 0 and int(time.time()) > exp:
        return "free"
    return tier


def get_entitlement_row(user_id: int) -> Optional[sqlite3.Row]:
    store = usage_store()
    with store._connect() as conn:
        return conn.execute(
            "SELECT * FROM user_entitlements WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()


def resolved_limits(user_id: int) -> ResolvedLimits:
    row = get_entitlement_row(user_id)
    tier = _effective_tier(row)
    base = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    bonus = int(row["bonus_month_mb"] or 0) if row else 0
    exp = int(row["expires_at"] or 0) if row else 0
    return ResolvedLimits(
        tier=tier,
        quota_day_mb=base["quota_day_mb"],
        quota_month_mb=base["quota_month_mb"] + max(0, bonus),
        max_file_mb=base["max_file_mb"],
        max_parallel=base["max_parallel"],
        expires_at=exp,
    )


def get_usage_snapshot(user_id: int) -> dict[str, Any]:
    store = usage_store()
    dk, mk = _day_key(), _month_key()
    with store._connect() as conn:
        drow = conn.execute(
            "SELECT bytes_total, jobs FROM usage_ledger WHERE user_id = ? AND bucket = ?",
            (int(user_id), dk),
        ).fetchone()
        mrow = conn.execute(
            "SELECT bytes_total, jobs FROM usage_ledger WHERE user_id = ? AND bucket = ?",
            (int(user_id), mk),
        ).fetchone()
    day_b = int(drow["bytes_total"] or 0) if drow else 0
    day_j = int(drow["jobs"] or 0) if drow else 0
    month_b = int(mrow["bytes_total"] or 0) if mrow else 0
    month_j = int(mrow["jobs"] or 0) if mrow else 0
    lim = resolved_limits(user_id)
    return {
        "tier": lim.tier,
        "expires_at": lim.expires_at,
        "day_bytes": day_b,
        "month_bytes": month_b,
        "day_jobs": day_j,
        "month_jobs": month_j,
        "quota_day_mb": lim.quota_day_mb,
        "quota_month_mb": lim.quota_month_mb,
        "max_file_mb": lim.max_file_mb,
        "max_parallel": lim.max_parallel,
    }


def record_successful_upload_bytes(user_id: int, byte_count: int) -> None:
    if DISABLE_USAGE_LIMITS or byte_count <= 0:
        return
    store = usage_store()
    b = int(byte_count)
    dk, mk = _day_key(), _month_key()
    with store._lock:
        with store._connect() as conn:
            for bucket in (dk, mk):
                conn.execute(
                    """
                    INSERT INTO usage_ledger (user_id, bucket, bytes_total, jobs)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(user_id, bucket) DO UPDATE SET
                      bytes_total = usage_ledger.bytes_total + excluded.bytes_total,
                      jobs = usage_ledger.jobs + 1
                    """,
                    (int(user_id), bucket, b),
                )
            conn.commit()


def set_user_tier(user_id: int, tier: str, expires_at: int = 0) -> None:
    tier = tier.strip().lower()
    if tier not in TIER_LIMITS:
        tier = "free"
    store = usage_store()
    now = int(time.time())
    uid = int(user_id)
    with store._lock:
        with store._connect() as conn:
            row = conn.execute(
                "SELECT bonus_month_mb FROM user_entitlements WHERE user_id = ?",
                (uid,),
            ).fetchone()
            bonus = int(row["bonus_month_mb"] or 0) if row else 0
            conn.execute(
                """
                INSERT INTO user_entitlements (user_id, tier, expires_at, bonus_month_mb, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  tier = excluded.tier,
                  expires_at = excluded.expires_at,
                  updated_at = excluded.updated_at
                """,
                (uid, tier, int(expires_at), bonus, now),
            )
            conn.commit()


def add_bonus_month_mb(user_id: int, mb: int) -> None:
    if mb == 0:
        return
    store = usage_store()
    now = int(time.time())
    with store._lock:
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_entitlements (user_id, tier, expires_at, bonus_month_mb, updated_at)
                VALUES (?, 'free', 0, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  bonus_month_mb = bonus_month_mb + excluded.bonus_month_mb,
                  updated_at = excluded.updated_at
                """,
                (int(user_id), int(mb), now),
            )
            conn.commit()


def processing_matches_user(telegram_user_id: int) -> bool:
    if not PROCESSING_FILE.exists():
        return False
    try:
        data = json.loads(PROCESSING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False
    uid = data.get("telegram_user_id")
    if uid is None:
        uid = data.get("chat_id")
    try:
        return int(uid or 0) == int(telegram_user_id)
    except (TypeError, ValueError):
        return False


def parallel_job_count(telegram_user_id: int, queue) -> int:
    n = queue.count_tasks_for_user(int(telegram_user_id))
    if processing_matches_user(telegram_user_id):
        n += 1
    return n


def effective_max_file_bytes(user_id: int) -> Optional[int]:
    """
    Hard cap for one queued file (bytes). None = no cap from tier/env combo.
    """
    env_cap = _parse_env_max_file_mb()
    if DISABLE_USAGE_LIMITS:
        if env_cap is None:
            return None
        return env_cap * 1024 * 1024
    tier_mb = resolved_limits(user_id).max_file_mb
    if env_cap is None:
        return tier_mb * 1024 * 1024
    return min(env_cap * 1024 * 1024, tier_mb * 1024 * 1024)


def can_enqueue(
    user_id: int,
    job_bytes_estimate: int,
    queue,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Returns (ok, reason_code, detail) — reason_code for i18n key suffix or literal.
    """
    detail: dict[str, Any] = {"limits": resolved_limits(user_id).__dict__}
    detail.update(get_usage_snapshot(user_id))

    if DISABLE_USAGE_LIMITS:
        return True, "ok", detail

    lim = resolved_limits(user_id)
    env_cap = _parse_env_max_file_mb()
    tier_cap_mb = lim.max_file_mb
    caps_mb = [tier_cap_mb]
    if env_cap is not None:
        caps_mb.append(env_cap)
    eff_mb = min(caps_mb)
    if job_bytes_estimate > eff_mb * 1024 * 1024:
        detail["max_mb"] = eff_mb
        detail["need_mb"] = f"{job_bytes_estimate / (1024 * 1024):.1f}"
        return False, "quota_file_cap", detail

    par = parallel_job_count(user_id, queue)
    if par >= lim.max_parallel:
        detail["parallel"] = par
        detail["max_parallel"] = lim.max_parallel
        return False, "quota_parallel", detail

    snap = get_usage_snapshot(user_id)
    day_b = int(snap["day_bytes"])
    month_b = int(snap["month_bytes"])
    day_limit = lim.quota_day_mb * 1024 * 1024
    month_limit = lim.quota_month_mb * 1024 * 1024

    if day_b + job_bytes_estimate > day_limit:
        detail["remain_day_mb"] = max(0, (day_limit - day_b) / (1024 * 1024))
        detail["need_mb"] = f"{job_bytes_estimate / (1024 * 1024):.1f}"
        return False, "quota_day", detail

    if month_b + job_bytes_estimate > month_limit:
        detail["remain_month_mb"] = max(0, (month_limit - month_b) / (1024 * 1024))
        detail["need_mb"] = f"{job_bytes_estimate / (1024 * 1024):.1f}"
        return False, "quota_month", detail

    return True, "ok", detail


def estimate_task_bytes(task: dict) -> int:
    """Best-effort bytes counted against quota (successful completion)."""
    t = task.get("type")
    if t == "text_message":
        return min(4096, len((task.get("text") or "").encode("utf-8")))
    if t == "local_file":
        return int(task.get("file_size") or 0)
    if t == "direct_url":
        return int(task.get("file_size") or 0)
    if t == "bundle_local_files":
        files = task.get("files") or []
        total = 0
        for p in files:
            try:
                fp = Path(p)
                if fp.exists():
                    total += fp.stat().st_size
            except OSError:
                pass
        return total
    return 0
