"""Mini App alert management API helpers (Pro alerts + free digest)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

JsonFn = Callable[..., tuple[int, bytes]]


def _uid_from_auth(auth_detail: str, q: Callable[[str], str]) -> int | None:
    if auth_detail == "open":
        raw = q("uid") or q("user_id")
        return int(raw) if raw.isdigit() else None
    try:
        return int(auth_detail)
    except ValueError:
        return None


def _is_paid_uid(uid: int) -> bool:
    try:
        from user_entitlements import resolved_limits

        return resolved_limits(uid).tier in ("pro", "star")
    except Exception:
        return False


def _serialize_alert(row: dict[str, Any]) -> dict[str, Any]:
    from v2.alerts.store import quake_min_mag

    kind = row.get("kind") or ""
    out: dict[str, Any] = {
        "id": int(row["id"]),
        "kind": kind,
        "asset": row.get("asset") or "",
        "schedule": row.get("schedule") or "daily",
        "hour_tehran": int(row.get("hour_tehran") or 9),
        "enabled": bool(row.get("enabled")),
        "spike_pct": row.get("spike_pct"),
        "min_mag": row.get("min_mag"),
        "muted_until": float(row.get("muted_until") or 0),
        "trigger": row.get("trigger") or "schedule",
    }
    if kind == "quake":
        out["min_mag"] = quake_min_mag(row)
    return out


def _run_coro(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def handle_alerts_action(
    action: str,
    *,
    q: Callable[[str], str],
    auth_detail: str,
    json_response: JsonFn,
) -> tuple[int, bytes] | None:
    """Return JSON response bytes for alert actions, or None if action unknown."""
    if not action.startswith("alerts_"):
        return None

    from v2.alerts import free_digest, store
    from v2.alerts.poller import compose_alert_body, schedule_label
    from v2.core.msg_format import strip_html

    uid = _uid_from_auth(auth_detail, q)
    if uid is None:
        return json_response(False, error="missing_user", http=401)

    if action == "alerts_free_get":
        sub = free_digest.get_sub(uid)
        lang = q("lang") or "fa"
        return json_response(
            True,
            data={
                "sub": dict(sub) if sub else None,
                "summary": free_digest.summarize_sub(sub, lang=lang),
                "paid": _is_paid_uid(uid),
            },
        )

    if action == "alerts_free_set":
        kind = (q("kind") or "fx").lower()
        asset = q("asset") or q("city")
        ok, err = free_digest.set_sub(uid, kind=kind, asset=asset)
        if not ok:
            return json_response(False, error=err)
        sub = free_digest.get_sub(uid)
        return json_response(True, data={"sub": dict(sub) if sub else None})

    if action == "alerts_free_off":
        free_digest.disable_sub(uid)
        return json_response(True, data={"enabled": False})

    if not _is_paid_uid(uid):
        return json_response(False, error="paid_only", http=403)

    if action == "alerts_list":
        rows = [_serialize_alert(r) for r in store.list_alerts(uid)]
        return json_response(True, data={"alerts": rows, "paid": True})

    if action == "alerts_toggle":
        aid_s = q("id")
        if not aid_s.isdigit():
            return json_response(False, error="bad_id")
        new_val = store.toggle_enabled(uid, int(aid_s))
        if new_val is None:
            return json_response(False, error="not_found", http=404)
        return json_response(True, data={"enabled": new_val})

    if action == "alerts_delete":
        aid_s = q("id")
        if not aid_s.isdigit():
            return json_response(False, error="bad_id")
        ok = store.delete_alert(uid, int(aid_s))
        if not ok:
            return json_response(False, error="not_found", http=404)
        return json_response(True, data={"deleted": True})

    if action == "alerts_mute":
        aid_s = q("id")
        hours_s = q("hours") or "24"
        if not aid_s.isdigit():
            return json_response(False, error="bad_id")
        try:
            hours = float(hours_s)
        except ValueError:
            hours = 24.0
        ok = store.mute_alert(uid, int(aid_s), hours=hours)
        if not ok:
            return json_response(False, error="not_found", http=404)
        return json_response(True, data={"muted_hours": hours})

    if action == "alerts_test":
        aid_s = q("id")
        if not aid_s.isdigit():
            return json_response(False, error="bad_id")
        row = store.get_alert(uid, int(aid_s))
        if not row:
            return json_response(False, error="not_found", http=404)
        lang = "en" if (q("lang") or "").lower() == "en" else "fa"
        body, _price, _spike = _run_coro(
            compose_alert_body(row, force_schedule=True, lang=lang)
        )
        if not body:
            return json_response(False, error="empty")
        return json_response(
            True,
            text=strip_html(body),
            data={"html": body, "label": schedule_label(row, lang=lang)},
        )

    return json_response(False, error="unknown_action", http=404)
