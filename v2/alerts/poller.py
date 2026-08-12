"""Background poller for alert subscriptions."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from v2.alerts import store
from v2.core.msg_format import escape, send_formatted
from v2.toolkit import fx_light
from v2.toolkit.fx_calculator import _rial_of
from v2.toolkit.weather_light import recent_earthquakes, weather_report

log = logging.getLogger("tele2rub.alerts")

TierCheckFn = Callable[[int], bool]
_TEHRAN = ZoneInfo("Asia/Tehran")


def _quiet_bounds() -> tuple[int, int]:
    try:
        start = max(0, min(23, int((os.getenv("ALERT_QUIET_START_TEHRAN") or "23").strip())))
    except ValueError:
        start = 23
    try:
        end = max(0, min(23, int((os.getenv("ALERT_QUIET_END_TEHRAN") or "7").strip())))
    except ValueError:
        end = 7
    return start, end


def in_quiet_hours(now: Optional[datetime] = None) -> bool:
    """True during [start, end) wrapping midnight (default 23→07 Tehran)."""
    start, end = _quiet_bounds()
    if start == end:
        return False
    h = (now or datetime.now(_TEHRAN)).hour
    if start < end:
        return start <= h < end
    return h >= start or h < end


def schedule_label(row: dict[str, Any], *, lang: str = "fa") -> str:
    sched = (row.get("schedule") or "daily").lower()
    hour = row.get("hour_tehran")
    if hour is None:
        hour = row.get("_hour_tehran", 9)
    hour = int(hour)
    if lang == "en":
        names = {"hourly": "hourly", "daily": "daily", "weekly": "weekly"}
        base = names.get(sched, sched)
        if sched in ("daily", "weekly"):
            return f"{base} {hour:02d}:00 Tehran"
        return base
    names = {"hourly": "ساعتی", "daily": "روزانه", "weekly": "هفتگی"}
    base = names.get(sched, sched)
    if sched in ("daily", "weekly"):
        return f"{base} {hour:02d}:۰۰ تهران"
    return base


async def compose_alert_body(
    row: dict[str, Any],
    *,
    force_schedule: bool = False,
) -> tuple[str, Optional[float], bool]:
    """Build alert HTML body. Returns (body, price, is_spike)."""
    kind = row.get("kind") or ""
    asset = (row.get("asset") or "").strip()
    spike = row.get("spike_pct")
    schedule_due = bool(row.get("_schedule_due")) or force_schedule
    body = ""
    price: Optional[float] = None
    force_spike = False

    if kind in ("fx", "gold"):
        code = asset.upper() or ("USD" if kind == "fx" else "SEKEE")
        ok, rial = await asyncio.to_thread(_rial_of, 1.0, code)
        if not ok:
            return "", None, False
        price = float(rial)
        last = row.get("last_price")
        if last is not None and spike is not None and float(last) > 0 and not force_schedule:
            pct = abs(price - float(last)) / float(last) * 100.0
            if pct >= float(spike):
                force_spike = True
                body = (
                    f"<b>🚨 جهش {escape(code)}</b>\n"
                    f"تغییر ≈ {pct:.2f}% (آستانه {float(spike):g}%)\n"
                    f"قیمت ≈ {price:,.0f} ریال"
                )
        if (schedule_due or force_schedule) and not body:
            body = (
                f"<b>🔔 گزارش {escape(code)}</b>\n"
                f"قیمت ≈ {price:,.0f} ریال\n"
                f"{escape(schedule_label(row))}"
            )
    elif kind == "weather":
        if not schedule_due and not force_schedule:
            return "", None, False
        city = asset or "Tehran"
        ok, w = await asyncio.to_thread(weather_report, city, lang="fa")
        if not ok:
            return "", None, False
        body = f"<b>🌤 آب‌وهوای زمان‌بندی‌شده — {escape(city)}</b>\n\n{w}"
    elif kind == "quake":
        if not schedule_due and not force_schedule and spike is None:
            return "", None, False
        min_mag = float(spike) if spike is not None else 4.5
        ok, q = await asyncio.to_thread(
            recent_earthquakes, lang="fa", min_mag=min_mag
        )
        if not ok:
            return "", None, False
        if asset and asset not in q and not schedule_due and not force_schedule:
            return "", None, False
        body = (
            f"<b>🌍 زلزله (حداقل {escape(f'{min_mag:g}')} ریشتر)</b>\n"
            f"فیلتر مکان: {escape(asset or 'همه')}\n\n"
            f"{escape(q)}"
        )
    else:
        return "", None, False

    return body, price, force_spike


async def process_alerts_once(
    app: Any,
    *,
    is_paid: TierCheckFn,
    tr: Optional[Callable[..., str]] = None,
) -> int:
    """Evaluate due/spike alerts; return number of messages sent."""
    sent = 0
    due = store.due_alerts()
    if not due:
        return 0

    quiet = in_quiet_hours()

    try:
        await asyncio.to_thread(fx_light.get_irr_rate_bundle, force_refresh=False)
    except Exception:
        pass

    for row in due:
        uid = int(row["user_id"])
        if not is_paid(uid):
            continue
        if row.get("_muted"):
            continue
        aid = int(row["id"])
        schedule_due = bool(row.get("_schedule_due"))

        try:
            body, price, force_spike = await compose_alert_body(row)
        except Exception as e:
            log.warning("alert eval failed id=%s: %s", aid, e)
            continue

        if not body:
            continue
        if quiet and schedule_due and not force_spike:
            # Defer scheduled sends during quiet hours; spikes still fire.
            continue
        if not schedule_due and not force_spike:
            continue

        try:
            await send_formatted(app, uid, body)
            store.mark_sent(aid, price=price)
            sent += 1
        except Exception as e:
            log.warning("alert send failed uid=%s: %s", uid, e)
    return sent


async def alert_poll_loop(app: Any, *, is_paid: TierCheckFn, interval: float = 120.0) -> None:
    await asyncio.sleep(15)
    while True:
        try:
            n = await process_alerts_once(app, is_paid=is_paid)
            if n:
                log.info("alerts sent=%s", n)
        except Exception:
            log.exception("alert_poll_loop error")
        await asyncio.sleep(interval)
