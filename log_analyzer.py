import argparse
import json
import time
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def fmt_ms(ms) -> str:
    try:
        ms_int = int(ms)
    except Exception:
        return "n/a"
    if ms_int < 1000:
        return f"{ms_int}ms"
    sec = ms_int / 1000
    return f"{sec:.2f}s"


def main():
    parser = argparse.ArgumentParser(description="Analyze TelegramToRubika job logs by job_id")
    parser.add_argument("--job-id", required=True, help="Job ID to analyze")
    parser.add_argument(
        "--queue-dir",
        default="queue",
        help="Queue directory containing bot_events.jsonl and worker_events.jsonl",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Print a one-line short summary",
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow worker log in real-time for this job_id",
    )
    args = parser.parse_args()

    queue_dir = Path(args.queue_dir)
    bot_file = queue_dir / "bot_events.jsonl"
    worker_file = queue_dir / "worker_events.jsonl"
    job_id = str(args.job_id)

    bot_rows = [r for r in read_jsonl(bot_file) if str(r.get("job_id", "")) == job_id]
    worker_rows = [r for r in read_jsonl(worker_file) if str(r.get("job_id", "")) == job_id]

    task_done = next((r for r in worker_rows if r.get("event") == "task_done"), None)
    task_failed = next((r for r in worker_rows if r.get("event") == "task_failed"), None)
    requeued = next((r for r in worker_rows if r.get("event") == "task_requeued"), None)

    if task_done:
        status = "DONE"
    elif task_failed:
        status = "FAILED"
    elif bot_rows or worker_rows:
        status = "IN_PROGRESS_OR_UNKNOWN"
    else:
        status = "NOT_FOUND"

    summary = {
        "job_id": job_id,
        "status": status,
        "bot_log_file": str(bot_file),
        "worker_log_file": str(worker_file),
        "events": {
            "bot_count": len(bot_rows),
            "worker_count": len(worker_rows),
        },
        "timing": {
            "total_duration_ms": task_done.get("duration_ms") if task_done else None,
        },
        "parts": task_done.get("parts") if task_done else None,
        "error": task_failed.get("error") if task_failed else None,
        "requeued_new_job_id": requeued.get("new_job_id") if requeued else None,
        "bot_events": bot_rows,
        "worker_events": worker_rows,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.brief:
        duration = summary["timing"]["total_duration_ms"]
        brief_parts = [
            f"job_id={job_id}",
            f"status={status}",
            f"duration_ms={duration if duration is not None else 'n/a'}",
            f"parts={summary.get('parts', 'n/a')}",
            f"requeued_new_job_id={summary.get('requeued_new_job_id') or 'n/a'}",
            f"error={summary.get('error') or 'n/a'}",
        ]
        print(" | ".join(brief_parts))
        return

    if args.follow:
        print(f"Following worker log for job_id={job_id} ...")
        print(f"File: {worker_file}")

        # Start from current end of file to show new events only.
        if not worker_file.exists():
            worker_file.parent.mkdir(parents=True, exist_ok=True)
            worker_file.touch()

        terminal_events = {"task_done", "task_failed", "task_requeued"}
        with open(worker_file, "r", encoding="utf-8") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if str(row.get("job_id", "")) != job_id:
                    continue

                event = row.get("event", "unknown")
                msg = f"ts={row.get('ts')} event={event}"
                if "phase" in row:
                    msg += f" phase={row.get('phase')}"
                if "duration_ms" in row:
                    msg += f" duration={fmt_ms(row.get('duration_ms'))}"
                if "error" in row:
                    msg += f" error={row.get('error')}"
                print(msg)

                if event in terminal_events:
                    print("Reached terminal event. Follow mode stopped.")
                    return

    print(f"Job ID: {job_id}")
    print(f"Bot log file: {bot_file}")
    print(f"Worker log file: {worker_file}")
    print("")

    if not bot_rows and not worker_rows:
        print("No events found for this job_id.")
        return

    if bot_rows:
        print("Bot Events:")
        for row in bot_rows:
            print(
                f"- ts={row.get('ts')} event={row.get('event')} "
                f"task_type={row.get('task_type', 'n/a')} direct_mode={row.get('direct_mode', 'n/a')}"
            )
        print("")

    if worker_rows:
        print("Worker Events:")
        for row in worker_rows:
            event = row.get("event")
            line = f"- ts={row.get('ts')} event={event}"
            if "phase" in row:
                line += f" phase={row.get('phase')}"
            if "duration_ms" in row:
                line += f" duration={fmt_ms(row.get('duration_ms'))}"
            if "parts" in row:
                line += f" parts={row.get('parts')}"
            if "part_index" in row:
                line += f" part_index={row.get('part_index')}"
            if "error" in row:
                line += f" error={row.get('error')}"
            print(line)
        print("")

    print("Summary:")
    if task_done:
        print(
            f"- Status: DONE (total duration: {fmt_ms(task_done.get('duration_ms'))}, "
            f"parts={task_done.get('parts', 'n/a')})"
        )
    elif task_failed:
        print(f"- Status: FAILED ({task_failed.get('error', 'unknown error')})")
    else:
        print("- Status: IN_PROGRESS_OR_UNKNOWN")

    if requeued:
        print(f"- Requeued as new job_id: {requeued.get('new_job_id')}")


if __name__ == "__main__":
    main()
