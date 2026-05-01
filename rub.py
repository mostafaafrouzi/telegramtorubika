import os
import re
import json
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from rubpy import Client as RubikaClient
import requests
import pyzipper
from urllib.parse import urlparse
import threading

from queue_db import QueueDB

load_dotenv()

SESSION = os.getenv("RUBIKA_SESSION", "rubika_session").strip()

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
QUEUE_DIR = BASE_DIR / "queue"
PROCESSING_FILE = QUEUE_DIR / "processing.json"
FAILED_FILE = QUEUE_DIR / "failed.jsonl"
STATUS_FILE = QUEUE_DIR / "status.jsonl"
URL_DIR = DOWNLOAD_DIR / "url"
NETWORK_FILE = QUEUE_DIR / "network.json"
WORKER_LOG_FILE = QUEUE_DIR / "worker_events.jsonl"

MAX_RETRIES = 5
UPLOAD_TIMEOUT = 1800
TARGET = "me"
DEFAULT_PART_SIZE_MB = int(os.getenv("DEFAULT_PART_SIZE_MB", "1900"))
SAFE_REQUIRED_EXTS = {
    ".heic", ".heif", ".flac", ".mkv", ".m4b", ".7z", ".rar", ".tar", ".xz"
}

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_DIR.mkdir(parents=True, exist_ok=True)
URL_DIR.mkdir(parents=True, exist_ok=True)
queue_db = QueueDB()
TARGET_GUID_CACHE_FILE = QUEUE_DIR / "targets.json"


def worker_log(event: str, **kwargs):
    payload = {
        "ts": int(time.time()),
        "event": event,
        **kwargs,
    }
    try:
        with open(WORKER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def safe_filename(name: Optional[str]) -> str:
    name = (name or "file").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = name.rstrip(". ")
    return name[:200] or "file"

def pretty_size(size) -> str:
    size = float(size or 0)
    units = ["B", "KB", "MB", "GB"]

    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f} {units[index]}"

def get_per_attempt_timeout(file_path: str) -> int:
    size_mb = Path(file_path).stat().st_size / (1024 * 1024)

    if size_mb < 100:
        return 180
    elif size_mb < 500:
        return 420
    elif size_mb < 1000:
        return 720
    else:
        return 1200
    
def eta_text(seconds) -> str:
    if not seconds or seconds <= 0:
        return "نامشخص"

    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def push_status(task: dict, text: str, status: str = "working", percent: float | None = None):
    payload = {
        "chat_id": task.get("chat_id"),
        "message_id": task.get("status_message_id"),
        "status": status,
        "text": text,
        "percent": percent,
        "time": time.time(),
    }

    with open(STATUS_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def set_network_mode(mode: str, reason: str = ""):
    data = {
        "mode": mode,
        "reason": reason,
        "updated_at": int(time.time()),
    }
    NETWORK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_global_network_available() -> bool:
    try:
        resp = requests.get("https://github.com", timeout=8)
        return resp.status_code < 500
    except Exception:
        return False


def requires_global_network(task_type: str) -> bool:
    return task_type in {"direct_url"}


def requeue_task(task: dict) -> dict:
    clone = dict(task)
    clone.pop("job_id", None)
    clone["requeued_at"] = int(time.time())
    return queue_db.push_task(clone)

def is_cancelled(task: dict) -> bool:
    job_id = str(task.get("job_id", ""))
    if not job_id:
        return False
    return queue_db.is_cancelled(job_id)

def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    index = 1

    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def has_session(session_name: str) -> bool:
    candidates = [
        Path(session_name),
        Path(f"{session_name}.session"),
        Path(f"{session_name}.sqlite"),
    ]
    return any(path.exists() for path in candidates)


def send_document(file_path: str, caption: str = "", session_name: Optional[str] = None):
    client = RubikaClient(name=(session_name or SESSION))

    try:
        try:
            client.start()
        except EOFError:
            raise RuntimeError("Rubika session is not authorized. Reconnect in bot with /rubika_connect")
        me = client.get_me()
        target_guid = getattr(getattr(me, "user", None), "user_guid", None) or TARGET
        return client.send_document(
            target_guid,
            file_path,
            caption=caption or ""
        )
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

def send_with_timeout(file_path, caption, timeout, session_name: Optional[str] = None):
    result = {}
    error = {}

    def target():
        try:
            result["data"] = send_document(file_path, caption, session_name=session_name)
        except Exception as e:
            error["err"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise RuntimeError("آپلود بیشتر از حد مجاز طول کشید و لغو شد.")

    if "err" in error:
        raise error["err"]

    return result.get("data")

def send_with_retry(file_path: str, caption: str = "", task: dict | None = None, session_name: Optional[str] = None):
    last_error = None
    start_time = time.time()

    for attempt in range(1, MAX_RETRIES + 1):

        if time.time() - start_time > UPLOAD_TIMEOUT:
            raise RuntimeError("آپلود بیشتر از حد مجاز طول کشید و لغو شد.")

        if task and is_cancelled(task):
            raise RuntimeError("ارسال لغو شد.")

        try:
            if task:
                push_status(
                    task,
                    f"🔼 در حال آپلود در روبیکا...\n\n"
                    f"🔴 تلاش {attempt} از {MAX_RETRIES}\n\n"
                    f"برای لغو ارسال:\n"
                    f"`/del {task.get('job_id')}`",
                    "uploading"
                )

            elapsed = time.time() - start_time
            remaining = UPLOAD_TIMEOUT - elapsed

            if remaining <= 0:
                raise RuntimeError("آپلود بیشتر از ۳۰ دقیقه طول کشید و لغو شد.")

            per_attempt = min(get_per_attempt_timeout(file_path), remaining)

            return send_with_timeout(file_path, caption, per_attempt, session_name=session_name)

        except Exception as e:
            last_error = e
            error_text = str(e).lower()

            transient = any(
                key in error_text
                for key in [
                    "502", "503", "bad gateway", "timeout",
                    "cannot connect", "connection reset",
                    "temporarily unavailable",
                    "error uploading chunk",
                    "unexpected mimetype",
                ]
            )

            if transient and attempt < MAX_RETRIES:

                if task and is_cancelled(task):
                    raise RuntimeError("ارسال لغو شد.")

                if task:
                    push_status(
                        task,
                        f"ارتباط با روبیکا ناپایدار بود...\n"
                        f"دوباره تلاش می‌کنم ({attempt + 1})",
                        "uploading"
                    )

                time.sleep(3)
                continue

    raise last_error if last_error else RuntimeError("Upload failed.")

def download_url(task: dict) -> Path:
    url = task.get("url", "").strip()
    if not url:
        raise RuntimeError("URL خالیه")

    push_status(task, "در حال دانلود ...", "downloading", 0)

    try:
        resp = requests.get(url, stream=True, timeout=(10, 60), allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError("لینک جواب نداد")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("مشکل شبکه")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "نامشخص"
        raise RuntimeError(f"دانلود انجام نشد. کد خطا: {code}")
    
    cd = resp.headers.get("content-disposition", "")
    match = re.findall(r'filename="(.+?)"', cd)
    name = match[0] if match else Path(urlparse(url).path).name
    name = safe_filename(name or f"file_{int(time.time())}")
    if "." not in name:
        name += ".bin"

    target = unique_path(URL_DIR / name)
    total = int(resp.headers.get("content-length") or 0)
    downloaded, last_update, started = 0, 0, time.time()

    with open(target, "wb") as f:
        for chunk in resp.iter_content(1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if now - last_update < 3 and downloaded < total:
                continue
            last_update = now

            speed = downloaded / max(now - started, 1)
            eta = (total - downloaded) / speed if total and speed else None
            percent = downloaded * 100 / total if total else None

            text = f"داره دانلود میکنه...\n\n{pretty_size(downloaded)}"
            if total:
                text += f" از {pretty_size(total)}"
            text += f"\nسرعت: {pretty_size(speed)}/s"
            if eta:
                text += f"\nمونده: {eta_text(eta)}"

            push_status(task, text, "downloading", percent)

    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("فایل دانلود نشد")

    task["file_name"] = target.name
    task["file_size"] = target.stat().st_size
    return target

def make_zip_with_password(file_path: Path, password: str) -> Path:
    zip_path = unique_path(file_path.with_suffix(file_path.suffix + ".zip"))

    with pyzipper.AESZipFile(
        zip_path,
        "w",
        compression=pyzipper.ZIP_STORED,
        encryption=pyzipper.WZ_AES,
    ) as zip_file:
        zip_file.setpassword(password.encode("utf-8"))
        zip_file.write(file_path, arcname=file_path.name)

    return zip_path


def make_bundle_zip(file_paths: list[Path], zip_name: str, password: str = "") -> Path:
    zip_base = safe_filename(zip_name or f"bundle_{int(time.time())}")
    zip_path = unique_path(DOWNLOAD_DIR / f"{zip_base}.zip")
    if password:
        with pyzipper.AESZipFile(
            zip_path,
            "w",
            compression=pyzipper.ZIP_STORED,
            encryption=pyzipper.WZ_AES,
        ) as zip_file:
            zip_file.setpassword(password.encode("utf-8"))
            for file_path in file_paths:
                zip_file.write(file_path, arcname=file_path.name)
    else:
        with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_STORED) as zip_file:
            for file_path in file_paths:
                zip_file.write(file_path, arcname=file_path.name)
    return zip_path


def split_file_parts(file_path: Path, part_size_mb: int) -> list[Path]:
    part_size = max(1, part_size_mb) * 1024 * 1024
    if file_path.stat().st_size <= part_size:
        return [file_path]
    parts: list[Path] = []
    with open(file_path, "rb") as src:
        index = 1
        while True:
            chunk = src.read(part_size)
            if not chunk:
                break
            part_path = file_path.with_name(f"{file_path.stem}.part{index:03d}{file_path.suffix}")
            with open(part_path, "wb") as dst:
                dst.write(chunk)
            parts.append(part_path)
            index += 1
    return parts


def send_text_message(text: str, session_name: Optional[str] = None):
    client = RubikaClient(name=(session_name or SESSION))
    try:
        try:
            client.start()
        except EOFError:
            raise RuntimeError("Rubika session is not authorized. Reconnect in bot with /rubika_connect")
        me = client.get_me()
        target_guid = getattr(getattr(me, "user", None), "user_guid", None) or TARGET
        return client.send_message(target_guid, text)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

def pop_first_task():
    return queue_db.pop_first_task()


def save_processing(task: dict) -> None:
    with open(PROCESSING_FILE, "w", encoding="utf-8") as file:
        json.dump(task, file, ensure_ascii=False, indent=2)


def clear_processing() -> None:
    if PROCESSING_FILE.exists():
        PROCESSING_FILE.unlink()


def append_failed(task: dict, error: str) -> None:
    payload = {"task": task, "error": error}
    with open(FAILED_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")

def process_task(task: dict):
    task_started_at = time.time()
    task_type = task.get("type")
    caption = task.get("caption", "")
    safe_mode = task.get("safe_mode", False)
    zip_password = task.get("zip_password", "")
    chat_id = task.get("chat_id")

    def wl(event: str, **extra):
        worker_log(event, chat_id=chat_id, **extra)

    session_name = task.get("rubika_session") or SESSION
    wl(
        "task_started",
        job_id=task.get("job_id"),
        task_type=task_type,
        session=session_name,
    )
    part_size_mb = int(task.get("part_size_mb") or DEFAULT_PART_SIZE_MB)
    if requires_global_network(task_type):
        if not is_global_network_available():
            set_network_mode("degraded", "global_internet_unreachable")
            raise RuntimeError("اینترنت بین‌الملل در دسترس نیست. این کار در حالت degraded متوقف شد.")
        set_network_mode("normal", "")

    local_path: Path | None = None

    if task_type == "local_file":
        local_path = Path(task.get("path", ""))

        if not local_path.exists():
            raise RuntimeError("Local file not found.")

    elif task_type == "direct_url":
        wl("phase", job_id=task.get("job_id"), phase="download_url_started")
        local_path = download_url(task)
        wl(
            "phase",
            job_id=task.get("job_id"),
            phase="download_url_done",
            file_name=local_path.name if local_path else "",
            file_size=local_path.stat().st_size if local_path and local_path.exists() else 0,
        )
    elif task_type == "text_message":
        send_text_message(task.get("text", ""), session_name=session_name)
        push_status(task, "متن/لینک با موفقیت در روبیکا ارسال شد.", "done")
        wl(
            "task_done",
            job_id=task.get("job_id"),
            task_type=task_type,
            duration_ms=int((time.time() - task_started_at) * 1000),
        )
        return
    elif task_type == "bundle_local_files":
        files = [Path(p) for p in task.get("files", []) if Path(p).exists()]
        if not files:
            raise RuntimeError("فایلی برای ساخت bundle پیدا نشد.")
        push_status(task, "در حال ساخت zip گروهی ...", "processing")
        zip_password = task.get("zip_password", "") if task.get("safe_mode") else ""
        zip_started_at = time.time()
        bundle = make_bundle_zip(files, task.get("zip_name", "bundle"), zip_password)
        wl(
            "phase",
            job_id=task.get("job_id"),
            phase="bundle_zip_done",
            zip_name=bundle.name,
            zip_size=bundle.stat().st_size if bundle.exists() else 0,
            duration_ms=int((time.time() - zip_started_at) * 1000),
        )
        for src in files:
            try:
                src.unlink()
            except Exception:
                pass
        split_started_at = time.time()
        parts = split_file_parts(bundle, part_size_mb)
        wl(
            "phase",
            job_id=task.get("job_id"),
            phase="split_done",
            parts=len(parts),
            duration_ms=int((time.time() - split_started_at) * 1000),
        )
        try:
            for idx, part in enumerate(parts, start=1):
                push_status(
                    task,
                    f"ارسال پارت {idx} از {len(parts)} به روبیکا ...",
                    "uploading",
                )
                part_started_at = time.time()
                send_with_retry(str(part), caption="", task=task, session_name=session_name)
                wl(
                    "phase",
                    job_id=task.get("job_id"),
                    phase="upload_part_done",
                    part_index=idx,
                    part_name=part.name,
                    part_size=part.stat().st_size if part.exists() else 0,
                    duration_ms=int((time.time() - part_started_at) * 1000),
                )
            push_status(task, "همه پارت‌ها با موفقیت در روبیکا ارسال شدند.", "done")
            wl(
                "task_done",
                job_id=task.get("job_id"),
                task_type=task_type,
                parts=len(parts),
                duration_ms=int((time.time() - task_started_at) * 1000),
            )
        finally:
            for part in parts:
                try:
                    if part.exists():
                        part.unlink()
                except Exception:
                    pass
            try:
                if bundle.exists():
                    bundle.unlink()
            except Exception:
                pass
        return

    else:
        raise RuntimeError("Unknown task type.")

    extension = local_path.suffix.lower() if local_path else ""
    force_safe = extension in SAFE_REQUIRED_EXTS
    if force_safe and not safe_mode:
        safe_mode = True
        zip_password = zip_password or "SAFE_MODE"

    if safe_mode and zip_password:
        push_status(task, "در حال تبدیل به فایل zip ...", "processing")
        zip_started_at = time.time()
        try:
            zipped = make_zip_with_password(local_path, zip_password)
        finally:
            try:
                if local_path.exists():
                    local_path.unlink()
            except Exception:
                pass

        send_path = zipped
        wl(
            "phase",
            job_id=task.get("job_id"),
            phase="safe_zip_done",
            zip_name=send_path.name if send_path else "",
            zip_size=send_path.stat().st_size if send_path and send_path.exists() else 0,
            duration_ms=int((time.time() - zip_started_at) * 1000),
        )

    else:
        send_path = local_path

    split_started_at = time.time()
    send_parts = split_file_parts(send_path, part_size_mb)
    wl(
        "phase",
        job_id=task.get("job_id"),
        phase="split_done",
        parts=len(send_parts),
        duration_ms=int((time.time() - split_started_at) * 1000),
    )

    try:
        if is_cancelled(task):
            raise RuntimeError("ارسال لغو شد.")
        for idx, part in enumerate(send_parts, start=1):
            part_caption = caption if idx == 1 else f"{caption}\npart {idx}/{len(send_parts)}"
            part_started_at = time.time()
            send_with_retry(str(part), part_caption, task, session_name=session_name)
            wl(
                "phase",
                job_id=task.get("job_id"),
                phase="upload_part_done",
                part_index=idx,
                part_name=part.name,
                part_size=part.stat().st_size if part.exists() else 0,
                duration_ms=int((time.time() - part_started_at) * 1000),
            )

        push_status(
            task,
            "فایل با موفقیت در روبیکا آپلود شد.",
            "done"
        )
        wl(
            "task_done",
            job_id=task.get("job_id"),
            task_type=task_type,
            parts=len(send_parts),
            duration_ms=int((time.time() - task_started_at) * 1000),
        )

    finally:
        try:
            for part in send_parts:
                if part.exists():
                    part.unlink()
            if send_path and send_path.exists():
                send_path.unlink()
        except Exception:
            pass

def worker_loop():
    # Multi-user mode: do not force a global Rubika login on startup.
    # Each user connects Rubika from Telegram bot flow and tasks carry per-user session.
    print("Rubika worker started.")

    while True:
        task = pop_first_task()

        if not task:
            time.sleep(0.2)
            continue

        save_processing(task)

        try:
            process_task(task)
        except Exception as e:
            err = str(e)
            worker_log(
                "task_failed",
                chat_id=task.get("chat_id"),
                job_id=task.get("job_id"),
                task_type=task.get("type"),
                error=err,
            )
            if "global_internet_unreachable" in err or "اینترنت بین‌الملل در دسترس نیست" in err:
                new_task = requeue_task(task)
                worker_log(
                    "task_requeued",
                    chat_id=task.get("chat_id"),
                    job_id=task.get("job_id"),
                    new_job_id=new_task.get("job_id"),
                    reason="global_network_unreachable",
                )
                push_status(
                    task,
                    "اینترنت بین‌الملل قطع است. کار حذف نشد و دوباره در صف قرار گرفت.",
                    "queued",
                )
                push_status(
                    new_task,
                    f"کار به‌صورت خودکار retry شد.\nشناسه جدید: `{new_task.get('job_id')}`",
                    "queued",
                )
                time.sleep(5)
            else:
                append_failed(task, err)
                push_status(task, f"خطا: {err}", "failed")
        finally:
            clear_processing()

if __name__ == "__main__":
    worker_loop()
