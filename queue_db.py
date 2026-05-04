import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent
QUEUE_DIR = BASE_DIR / "queue"
DB_FILE = QUEUE_DIR / "queue.sqlite3"

QUEUE_DIR.mkdir(parents=True, exist_ok=True)


class QueueDB:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate_tasks_table(self, conn):
        rows = conn.execute("PRAGMA table_info(tasks)").fetchall()
        cols = {r[1] for r in rows}
        if "telegram_user_id" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN telegram_user_id INTEGER")

    def _migrate_v2_user_prefs_lang(self, conn):
        try:
            rows = conn.execute("PRAGMA table_info(v2_user_prefs)").fetchall()
        except sqlite3.OperationalError:
            return
        if not rows:
            return
        cols = {r[1] for r in rows}
        if "lang" not in cols:
            conn.execute("ALTER TABLE v2_user_prefs ADD COLUMN lang TEXT")

    def _migrate_v2_user_prefs_direct_mode(self, conn):
        try:
            rows = conn.execute("PRAGMA table_info(v2_user_prefs)").fetchall()
        except sqlite3.OperationalError:
            return
        if not rows:
            return
        cols = {r[1] for r in rows}
        if "direct_mode" not in cols:
            conn.execute("ALTER TABLE v2_user_prefs ADD COLUMN direct_mode INTEGER")

    def _migrate_v2_user_prefs_rubika_session(self, conn):
        try:
            rows = conn.execute("PRAGMA table_info(v2_user_prefs)").fetchall()
        except sqlite3.OperationalError:
            return
        if not rows:
            return
        cols = {r[1] for r in rows}
        if "rubika_session" not in cols:
            conn.execute("ALTER TABLE v2_user_prefs ADD COLUMN rubika_session TEXT")

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE,
                    payload TEXT NOT NULL,
                    status_message_id INTEGER,
                    rubika_session TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )
            self._migrate_tasks_table(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deleted_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    status_message_id INTEGER,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cancelled_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_user_prefs (
                    telegram_user_id INTEGER PRIMARY KEY,
                    menu_section TEXT NOT NULL,
                    lang TEXT,
                    direct_mode INTEGER,
                    rubika_session TEXT,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            self._migrate_v2_user_prefs_lang(conn)
            self._migrate_v2_user_prefs_direct_mode(conn)
            self._migrate_v2_user_prefs_rubika_session(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_user_state_mirror (
                    telegram_user_id INTEGER PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_batch_session_mirror (
                    telegram_user_id INTEGER PRIMARY KEY,
                    batch_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    gateway TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'IRR',
                    authority TEXT,
                    ref_id TEXT,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    raw_json TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_v2_payments_user ON v2_payments(telegram_user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_v2_payments_status ON v2_payments(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_v2_payments_authority ON v2_payments(authority)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_toolkit_daily (
                    telegram_user_id INTEGER NOT NULL,
                    day_ymd TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (telegram_user_id, day_ymd)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_v2_toolkit_daily_day ON v2_toolkit_daily(day_ymd)"
            )
            conn.commit()

    def get_direct_mode(self, telegram_user_id: int) -> Optional[bool]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT direct_mode FROM v2_user_prefs WHERE telegram_user_id = ? LIMIT 1",
                (int(telegram_user_id),),
            ).fetchone()
        if not row or row["direct_mode"] is None:
            return None
        return bool(int(row["direct_mode"]))

    def upsert_direct_mode(self, telegram_user_id: int, enabled: bool) -> None:
        """Mirror direct_mode for v2 migration (dual-write with users.json)."""
        val = 1 if enabled else 0
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM v2_user_prefs WHERE telegram_user_id = ? LIMIT 1",
                    (int(telegram_user_id),),
                ).fetchone()
                if row:
                    conn.execute(
                        """
                        UPDATE v2_user_prefs
                        SET direct_mode = ?, updated_at = ?
                        WHERE telegram_user_id = ?
                        """,
                        (val, now, int(telegram_user_id)),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO v2_user_prefs (telegram_user_id, menu_section, direct_mode, updated_at)
                        VALUES (?, 'main', ?, ?)
                        """,
                        (int(telegram_user_id), val, now),
                    )
                conn.commit()

    def all_tasks(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM tasks ORDER BY id ASC").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def push_task(self, task: dict) -> dict:
        with self._lock:
            task = dict(task)
            task.setdefault("job_id", str(int(time.time() * 1000)))
            created_at = int(time.time())
            uid = task.get("telegram_user_id")
            if uid is not None:
                uid = int(uid)
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (job_id, payload, status_message_id, rubika_session, created_at, telegram_user_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(task["job_id"]),
                        json.dumps(task, ensure_ascii=False),
                        int(task.get("status_message_id") or 0),
                        task.get("rubika_session"),
                        created_at,
                        uid,
                    ),
                )
                conn.commit()
            return task

    def pop_first_task(self) -> Optional[dict]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, payload FROM tasks ORDER BY id ASC LIMIT 1"
                ).fetchone()
                if not row:
                    return None
                conn.execute("DELETE FROM tasks WHERE id = ?", (row["id"],))
                conn.commit()
                return json.loads(row["payload"])

    def remove_task(self, job_id=None, message_id=None) -> Optional[dict]:
        with self._lock:
            with self._connect() as conn:
                row = None
                if job_id:
                    row = conn.execute(
                        "SELECT id, payload FROM tasks WHERE job_id = ? LIMIT 1",
                        (str(job_id),),
                    ).fetchone()
                elif message_id:
                    row = conn.execute(
                        "SELECT id, payload FROM tasks WHERE status_message_id = ? LIMIT 1",
                        (int(message_id),),
                    ).fetchone()
                if not row:
                    return None
                payload = json.loads(row["payload"])
                conn.execute("DELETE FROM tasks WHERE id = ?", (row["id"],))
                conn.commit()
                return payload

    def remove_tasks_by_session(self, rubika_session: str) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, payload FROM tasks WHERE rubika_session = ?",
                    (rubika_session,),
                ).fetchall()
                ids = [r["id"] for r in rows]
                if ids:
                    conn.executemany("DELETE FROM tasks WHERE id = ?", [(i,) for i in ids])
                    conn.commit()
                return [json.loads(r["payload"]) for r in rows]

    def mark_deleted(self, task: dict):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO deleted_jobs (job_id, status_message_id, created_at) VALUES (?, ?, ?)",
                (
                    str(task.get("job_id", "")),
                    int(task.get("status_message_id") or 0),
                    int(time.time()),
                ),
            )
            conn.commit()

    def was_deleted(self, job_id=None, message_id=None) -> bool:
        with self._connect() as conn:
            if job_id:
                row = conn.execute(
                    "SELECT 1 FROM deleted_jobs WHERE job_id = ? LIMIT 1",
                    (str(job_id),),
                ).fetchone()
                return bool(row)
            if message_id:
                row = conn.execute(
                    "SELECT 1 FROM deleted_jobs WHERE status_message_id = ? LIMIT 1",
                    (int(message_id),),
                ).fetchone()
                return bool(row)
            return False

    def cancel_job(self, job_id: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO cancelled_jobs (job_id, created_at) VALUES (?, ?)",
                (str(job_id), int(time.time())),
            )
            conn.commit()

    def is_cancelled(self, job_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM cancelled_jobs WHERE job_id = ? LIMIT 1",
                (str(job_id),),
            ).fetchone()
            return bool(row)

    def queue_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS c FROM tasks").fetchone()
            return int(row["c"] if row else 0)

    def queue_count_by_session(self, rubika_session: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS c FROM tasks WHERE rubika_session = ?",
                (rubika_session,),
            ).fetchone()
            return int(row["c"] if row else 0)

    def count_tasks_for_user(self, telegram_user_id: int) -> int:
        """Pending queue rows owned by this Telegram user (parallel job limit)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS c FROM tasks WHERE telegram_user_id = ?",
                (int(telegram_user_id),),
            ).fetchone()
            return int(row["c"] if row else 0)

    def cancelled_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS c FROM cancelled_jobs").fetchone()
            return int(row["c"] if row else 0)

    def deleted_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS c FROM deleted_jobs").fetchone()
            return int(row["c"] if row else 0)

    def upsert_menu_section(self, telegram_user_id: int, menu_section: str) -> None:
        """Mirror reply-keyboard menu section for v2 migration (dual-write with user_states.json)."""
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO v2_user_prefs (telegram_user_id, menu_section, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(telegram_user_id) DO UPDATE SET
                        menu_section = excluded.menu_section,
                        updated_at = excluded.updated_at
                    """,
                    (int(telegram_user_id), str(menu_section), now),
                )
                conn.commit()

    def get_menu_section(self, telegram_user_id: int) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT menu_section FROM v2_user_prefs WHERE telegram_user_id = ? LIMIT 1",
                (int(telegram_user_id),),
            ).fetchone()
            if not row:
                return None
            return str(row["menu_section"]) if row["menu_section"] is not None else None

    def delete_v2_user_prefs(self, telegram_user_id: int) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM v2_user_prefs WHERE telegram_user_id = ?",
                    (int(telegram_user_id),),
                )
                conn.commit()

    def get_lang(self, telegram_user_id: int) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT lang FROM v2_user_prefs WHERE telegram_user_id = ? LIMIT 1",
                (int(telegram_user_id),),
            ).fetchone()
            if not row or row["lang"] is None:
                return None
            return str(row["lang"])

    def upsert_lang(self, telegram_user_id: int, lang: str) -> None:
        """Mirror UI language for v2 migration (dual-write with users.json)."""
        if lang not in ("fa", "en"):
            lang = "fa"
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM v2_user_prefs WHERE telegram_user_id = ? LIMIT 1",
                    (int(telegram_user_id),),
                ).fetchone()
                if row:
                    conn.execute(
                        """
                        UPDATE v2_user_prefs
                        SET lang = ?, updated_at = ?
                        WHERE telegram_user_id = ?
                        """,
                        (lang, now, int(telegram_user_id)),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO v2_user_prefs (telegram_user_id, menu_section, lang, updated_at)
                        VALUES (?, 'main', ?, ?)
                        """,
                        (int(telegram_user_id), lang, now),
                    )
                conn.commit()

    def get_rubika_session(self, telegram_user_id: int) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rubika_session FROM v2_user_prefs WHERE telegram_user_id = ? LIMIT 1",
                (int(telegram_user_id),),
            ).fetchone()
        if not row or row["rubika_session"] is None:
            return None
        s = str(row["rubika_session"]).strip()
        return s or None

    def upsert_rubika_session(self, telegram_user_id: int, session_name: str) -> None:
        """Mirror linked Rubika session name for v2 migration (dual-write with users.json)."""
        name = (session_name or "").strip()
        if not name:
            return
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM v2_user_prefs WHERE telegram_user_id = ? LIMIT 1",
                    (int(telegram_user_id),),
                ).fetchone()
                if row:
                    conn.execute(
                        """
                        UPDATE v2_user_prefs
                        SET rubika_session = ?, updated_at = ?
                        WHERE telegram_user_id = ?
                        """,
                        (name, now, int(telegram_user_id)),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO v2_user_prefs (telegram_user_id, menu_section, rubika_session, updated_at)
                        VALUES (?, 'main', ?, ?)
                        """,
                        (int(telegram_user_id), name, now),
                    )
                conn.commit()

    def get_user_state_mirror(self, telegram_user_id: int) -> Optional[dict]:
        """Shadow copy of ``user_states.json`` entry for migration / recovery."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM v2_user_state_mirror WHERE telegram_user_id = ? LIMIT 1",
                (int(telegram_user_id),),
            ).fetchone()
        if not row:
            return None
        raw = row["state_json"]
        if raw is None or not str(raw).strip():
            return None
        try:
            out = json.loads(str(raw))
        except json.JSONDecodeError:
            return None
        return out if isinstance(out, dict) else None

    def upsert_user_state_mirror(self, telegram_user_id: int, state: dict) -> None:
        now = int(time.time())
        payload = json.dumps(dict(state), ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO v2_user_state_mirror (telegram_user_id, state_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(telegram_user_id) DO UPDATE SET
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (int(telegram_user_id), payload, now),
                )
                conn.commit()

    def delete_user_state_mirror(self, telegram_user_id: int) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM v2_user_state_mirror WHERE telegram_user_id = ?",
                    (int(telegram_user_id),),
                )
                conn.commit()

    def get_batch_session_mirror(self, telegram_user_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT batch_json FROM v2_batch_session_mirror WHERE telegram_user_id = ? LIMIT 1",
                (int(telegram_user_id),),
            ).fetchone()
        if not row:
            return None
        raw = row["batch_json"]
        if raw is None or not str(raw).strip():
            return None
        try:
            out = json.loads(str(raw))
        except json.JSONDecodeError:
            return None
        return out if isinstance(out, dict) else None

    def upsert_batch_session_mirror(self, telegram_user_id: int, batch: dict) -> None:
        now = int(time.time())
        payload = json.dumps(dict(batch), ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO v2_batch_session_mirror (telegram_user_id, batch_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(telegram_user_id) DO UPDATE SET
                        batch_json = excluded.batch_json,
                        updated_at = excluded.updated_at
                    """,
                    (int(telegram_user_id), payload, now),
                )
                conn.commit()

    def delete_batch_session_mirror(self, telegram_user_id: int) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM v2_batch_session_mirror WHERE telegram_user_id = ?",
                    (int(telegram_user_id),),
                )
                conn.commit()

    def insert_v2_payment(
        self,
        telegram_user_id: int,
        gateway: str,
        amount: int,
        *,
        currency: str = "IRR",
        authority: Optional[str] = None,
        ref_id: Optional[str] = None,
        status: str = "initiated",
        raw_json: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> int:
        """Insert one payment row; returns ``id``. See ``v2.billing`` for lifecycle constants."""
        now = int(time.time())
        raw = json.dumps(raw_json, ensure_ascii=False) if raw_json is not None else None
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO v2_payments (
                        telegram_user_id, gateway, amount, currency,
                        authority, ref_id, status, idempotency_key, raw_json,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(telegram_user_id),
                        str(gateway),
                        int(amount),
                        (currency or "IRR").strip() or "IRR",
                        authority,
                        ref_id,
                        str(status),
                        idempotency_key,
                        raw,
                        now,
                        now,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)

    def update_v2_payment_status(
        self,
        payment_id: int,
        status: str,
        *,
        ref_id: Optional[str] = None,
        raw_patch: Optional[dict] = None,
    ) -> None:
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                merged_raw: Optional[str] = None
                if raw_patch is not None:
                    base: dict = {}
                    row = conn.execute(
                        "SELECT raw_json FROM v2_payments WHERE id = ? LIMIT 1",
                        (int(payment_id),),
                    ).fetchone()
                    if row and row["raw_json"]:
                        try:
                            parsed = json.loads(str(row["raw_json"]))
                            if isinstance(parsed, dict):
                                base = parsed
                        except json.JSONDecodeError:
                            pass
                    base = {**base, **raw_patch}
                    merged_raw = json.dumps(base, ensure_ascii=False)

                if ref_id is not None and merged_raw is not None:
                    conn.execute(
                        """
                        UPDATE v2_payments
                        SET status = ?, ref_id = ?, raw_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (str(status), str(ref_id), merged_raw, now, int(payment_id)),
                    )
                elif ref_id is not None:
                    conn.execute(
                        """
                        UPDATE v2_payments
                        SET status = ?, ref_id = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (str(status), str(ref_id), now, int(payment_id)),
                    )
                elif merged_raw is not None:
                    conn.execute(
                        """
                        UPDATE v2_payments
                        SET status = ?, raw_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (str(status), merged_raw, now, int(payment_id)),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE v2_payments
                        SET status = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (str(status), now, int(payment_id)),
                    )
                conn.commit()

    def get_v2_payment_by_id(self, payment_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM v2_payments WHERE id = ? LIMIT 1",
                (int(payment_id),),
            ).fetchone()
        return dict(row) if row else None

    def get_v2_payment_by_idempotency_key(self, key: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM v2_payments WHERE idempotency_key = ? LIMIT 1",
                (str(key),),
            ).fetchone()
        return dict(row) if row else None

    def list_v2_payments_for_user(self, telegram_user_id: int, *, limit: int = 15) -> list[dict]:
        lim = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, gateway, amount, currency, authority, ref_id, status,
                       idempotency_key, created_at, updated_at
                FROM v2_payments
                WHERE telegram_user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(telegram_user_id), lim),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_v2_payments_by_status(self, status: str, *, limit: int = 100) -> list[dict]:
        lim = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM v2_payments
                WHERE status = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (str(status), lim),
            ).fetchall()
        return [dict(r) for r in rows]

    def toolkit_daily_get_count(self, telegram_user_id: int) -> int:
        """UTC-day toolkit hit count (no write)."""
        day = time.strftime("%Y%m%d", time.gmtime())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT hit_count FROM v2_toolkit_daily
                    WHERE telegram_user_id = ? AND day_ymd = ?
                    """,
                    (int(telegram_user_id), day),
                ).fetchone()
        return int(row["hit_count"]) if row else 0

    def toolkit_daily_increment_if_under_cap(self, telegram_user_id: int, *, daily_limit: int) -> None:
        """Increment UTC-day counter if ``hit_count < daily_limit``. No-op if ``daily_limit`` <= 0."""
        lim = int(daily_limit)
        if lim <= 0:
            return
        day = time.strftime("%Y%m%d", time.gmtime())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT hit_count FROM v2_toolkit_daily
                    WHERE telegram_user_id = ? AND day_ymd = ?
                    """,
                    (int(telegram_user_id), day),
                ).fetchone()
                cur = int(row["hit_count"]) if row else 0
                if cur >= lim:
                    return
                newc = cur + 1
                conn.execute(
                    """
                    INSERT INTO v2_toolkit_daily (telegram_user_id, day_ymd, hit_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(telegram_user_id, day_ymd) DO UPDATE SET
                        hit_count = excluded.hit_count
                    """,
                    (int(telegram_user_id), day, newc),
                )
                conn.commit()

