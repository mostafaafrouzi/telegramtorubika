"""Background poller for alert subscriptions."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from v2.alerts import store
from v2.core.msg_format import escape, send_formatted
from v2.toolkit import fx_light
from v2.toolkit.fx_calculator import _rial_of
from v2.toolkit.weather_light import recent_earthquakes, weather_report

log = logging.getLogger("tele2rub.alerts")

TierCheckFn = Callable[[int], bool]


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

    # Refresh market rates once per cycle
    try:
        await asyncio.to_thread(fx_light.get_irr_rate_bundle, force_refresh=False)
    except Exception:
        pass

    for row in due:
        uid = int(row["user_id"])
        if not is_paid(uid):
            continue
        kind = row.get("kind") or ""
        asset = (row.get("asset") or "").strip()
        spike = row.get("spike_pct")
        schedule_due = bool(row.get("_schedule_due"))
        aid = int(row["id"])
        body = ""
        price: Optional[float] = None
        force_spike = False

        try:
            if kind in ("fx", "gold"):
                code = asset.upper() or ("USD" if kind == "fx" else "SEKEE")
                ok, rial = await asyncio.to_thread(_rial_of, 1.0, code)
                if not ok:
                    continue
                price = float(rial)
                last = row.get("last_price")
                if last is not None and spike is not None and float(last) > 0:
                    pct = abs(price - float(last)) / float(last) * 100.0
                    if pct >= float(spike):
                        force_spike = True
                        body = (
                            f"<b>🚨 جهش {escape(code)}</b>\n"
                            f"تغییر ≈ {pct:.2f}% (آستانه {float(spike):g}%)\n"
                            f"قیمت ≈ {price:,.0f} ریال"
                        )
                if schedule_due and not body:
                    body = (
                        f"<b>🔔 گزارش {escape(code)}</b>\n"
                        f"قیمت ≈ {price:,.0f} ریال ({escape(row.get('schedule'))})"
                    )
            elif kind == "weather":
                if not schedule_due:
                    continue
                city = asset or "Tehran"
                ok, w = await asyncio.to_thread(weather_report, city, lang="fa")
                if not ok:
                    continue
                body = f"<b>🌤 آب‌وهوای زمان‌بندی‌شده — {escape(city)}</b>\n\n{w}"
            elif kind == "quake":
                if not schedule_due and spike is None:
                    continue
                min_mag = float(spike) if spike is not None else 4.5
                ok, q = await asyncio.to_thread(
                    recent_earthquakes, lang="fa", min_mag=min_mag
                )
                if not ok:
                    continue
                # Optional place filter in asset text
                if asset and asset not in q and not schedule_due:
                    continue
                body = (
                    f"<b>🌍 زلزله (حداقل {escape(f'{min_mag:g}')} ریشتر)</b>\n"
                    f"فیلتر مکان: {escape(asset or 'همه')}\n\n"
                    f"{escape(q)}"
                )
            else:
                continue
        except Exception as e:
            log.warning("alert eval failed id=%s: %s", aid, e)
            continue

        if not body:
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
