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
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (job_id, payload, status_message_id, rubika_session, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(task["job_id"]),
                        json.dumps(task, ensure_ascii=False),
                        int(task.get("status_message_id") or 0),
                        task.get("rubika_session"),
                        created_at,
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

    def cancelled_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS c FROM cancelled_jobs").fetchone()
            return int(row["c"] if row else 0)

    def deleted_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS c FROM deleted_jobs").fetchone()
            return int(row["c"] if row else 0)

