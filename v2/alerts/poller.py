"""Background poller for alert subscriptions."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from v2.alerts import store
from v2.core.msg_format import escape, italic, join, kv, send_formatted, title
from v2.toolkit import fx_light
from v2.toolkit.fx_calculator import _rial_of
from v2.toolkit.iran_quake_geo import place_matches_asset, summarize_quake_asset
from v2.toolkit.market_board import asset_label
from v2.toolkit.weather_light import fetch_earthquake_events, weather_report

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
    start, end = _quiet_bounds()
    if start == end:
        return False
    h = (now or datetime.now(_TEHRAN)).hour
    if start < end:
        return start <= h < end
    return h >= start or h < end


def schedule_label(row: dict[str, Any], *, lang: str = "fa") -> str:
    trigger = (row.get("_trigger") or row.get("trigger") or "schedule").lower()
    hour = int(row.get("hour_tehran") if row.get("hour_tehran") is not None else row.get("_hour_tehran", 9))
    if trigger == "spike":
        sp = row.get("spike_pct")
        if lang == "en":
            return f"spike ≥{float(sp):g}%" if sp is not None else "spike"
        return f"جهش ≥{float(sp):g}٪" if sp is not None else "جهش آنی"
    if trigger == "event":
        return "on event" if lang == "en" else "آنی روی رخداد"
    sched = (row.get("schedule") or "daily").lower()
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


def followup_keyboard(row: dict[str, Any], *, lang: str = "fa") -> InlineKeyboardMarkup:
    kind = (row.get("kind") or "").lower()
    aid = int(row.get("id") or 0)
    if lang == "en":
        view = {
            "fx": ("📈 Markets", "imenu:usd"),
            "gold": ("🥇 Gold board", "imenu:gold"),
            "weather": ("🌤 Weather", "imenu:weather"),
            "quake": ("🌍 Quakes", "imenu:quake"),
        }
        mute24, mute7, unmute = "🔇 24h", "🔇 7d", "🔔 Unmute"
        manage = "⚙️ Manage"
    else:
        view = {
            "fx": ("📈 بازار ارز", "imenu:usd"),
            "gold": ("🥇 تابلو طلا", "imenu:gold"),
            "weather": ("🌤 آب‌وهوا", "imenu:weather"),
            "quake": ("🌍 زلزله", "imenu:quake"),
        }
        mute24, mute7, unmute = "🔇 ۲۴س", "🔇 ۷روز", "🔔 لغو سکوت"
        manage = "⚙️ مدیریت"

    rows: list[list[InlineKeyboardButton]] = []
    if kind in view:
        label, cb = view[kind]
        rows.append([InlineKeyboardButton(label, callback_data=cb)])
    if aid:
        rows.append([InlineKeyboardButton(manage, callback_data=f"alertm:{aid}")])
        muted = float(row.get("muted_until") or 0) > time.time()
        if muted:
            rows.append(
                [InlineKeyboardButton(unmute, callback_data=f"alertmute:{aid}:0")]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(mute24, callback_data=f"alertmute:{aid}:24"),
                    InlineKeyboardButton(mute7, callback_data=f"alertmute:{aid}:168"),
                ]
            )
    return InlineKeyboardMarkup(rows)


async def compose_alert_body(
    row: dict[str, Any],
    *,
    force_schedule: bool = False,
    force_spike: bool = False,
    lang: str = "fa",
    event: Optional[dict[str, Any]] = None,
) -> tuple[str, Optional[float], bool]:
    """Build alert HTML card. Returns (body, price, is_spike)."""
    kind = row.get("kind") or ""
    asset = (row.get("asset") or "").strip()
    spike = row.get("spike_pct")
    trigger = (row.get("_trigger") or row.get("trigger") or "schedule").lower()
    schedule_due = bool(row.get("_schedule_due")) or force_schedule
    body = ""
    price: Optional[float] = None
    is_spike = False
    sched = schedule_label(row, lang=lang)
    name = asset_label(asset, lang=lang) if asset and kind in ("fx", "gold") else asset

    if kind in ("fx", "gold"):
        code = asset.upper() or ("USD" if kind == "fx" else "SEKEE")
        name = asset_label(code, lang=lang)
        ok, rial = await asyncio.to_thread(_rial_of, 1.0, code)
        if not ok:
            return "", None, False
        price = float(rial)
        last = row.get("last_price")
        want_spike = (trigger == "spike" or force_spike) and not force_schedule
        if (
            want_spike
            and last is not None
            and spike is not None
            and float(last) > 0
        ):
            pct = abs(price - float(last)) / float(last) * 100.0
            if pct >= float(spike) or force_spike:
                is_spike = True
                if lang == "en":
                    body = join(
                        title("🚨", f"Spike — {name}"),
                        kv("Change", f"{pct:.2f}% (threshold {float(spike):g}%)"),
                        kv("Price", f"{price:,.0f} IRR"),
                    )
                else:
                    body = join(
                        title("🚨", f"جهش — {name}"),
                        kv("تغییر", f"{pct:.2f}% (آستانه {float(spike):g}%)"),
                        kv("قیمت", f"{price:,.0f} ریال"),
                    )
        if (schedule_due or (force_schedule and trigger == "schedule")) and not body:
            if lang == "en":
                body = join(
                    title("🔔", f"Daily — {name}"),
                    kv("Price", f"{price:,.0f} IRR"),
                    kv("Schedule", sched),
                )
            else:
                body = join(
                    title("🔔", f"روزانه — {name}"),
                    kv("قیمت", f"{price:,.0f} ریال"),
                    kv("زمان‌بندی", sched),
                )
        # For spike-only test without last_price baseline:
        if force_schedule and trigger == "spike" and not body:
            if lang == "en":
                body = join(
                    title("🧪", f"Spike alert test — {name}"),
                    kv("Price", f"{price:,.0f} IRR"),
                    kv("Threshold", f"{float(spike):g}%" if spike is not None else "—"),
                )
            else:
                body = join(
                    title("🧪", f"تست هشدار جهش — {name}"),
                    kv("قیمت", f"{price:,.0f} ریال"),
                    kv("آستانه", f"{float(spike):g}%" if spike is not None else "—"),
                )
    elif kind == "weather":
        if not schedule_due and not force_schedule:
            return "", None, False
        city = asset or "Tehran"
        ok, w = await asyncio.to_thread(weather_report, city, lang=lang)
        if not ok:
            return "", None, False
        head = (
            title("🌤", f"Scheduled weather — {city}")
            if lang == "en"
            else title("🌤", f"آب‌وهوای زمان‌بندی‌شده — {city}")
        )
        body = join(head, italic(sched), w)
    elif kind == "quake":
        if event:
            mag = float(event.get("mag") or 0)
            place = event.get("place") or "?"
            when = event.get("when") or "—"
            depth = event.get("depth_km")
            depth_s = f"{depth:.0f} km" if isinstance(depth, (int, float)) else "—"
            filt = summarize_quake_asset(asset, lang=lang)
            if lang == "en":
                body = join(
                    title("🌍", f"Earthquake M{mag:.1f}"),
                    kv("Place", place),
                    kv("When", when),
                    kv("Depth", depth_s),
                    kv("Your filter", filt),
                )
            else:
                body = join(
                    title("🌍", f"زلزله M{mag:.1f}"),
                    kv("مکان", place),
                    kv("زمان", when),
                    kv("عمق", depth_s),
                    kv("فیلتر شما", filt),
                )
        elif force_schedule:
            filt = summarize_quake_asset(asset, lang=lang)
            min_mag = store.quake_min_mag(row)
            if lang == "en":
                body = join(
                    title("🧪", "Quake alert test"),
                    kv("Filter", filt),
                    kv("Min magnitude", f"{min_mag:g}"),
                    italic("Live events are sent immediately when they match."),
                )
            else:
                body = join(
                    title("🧪", "تست هشدار زلزله"),
                    kv("فیلتر", filt),
                    kv("حداقل شدت", f"{min_mag:g}"),
                    italic("وقتی زلزلهٔ مطابق فیلتر رخ دهد، همان لحظه ارسال می‌شود."),
                )
        else:
            return "", None, False
    else:
        return "", None, False

    return body, price, is_spike


async def process_alerts_once(
    app: Any,
    *,
    is_paid: TierCheckFn,
    tr: Optional[Callable[..., str]] = None,
    get_lang: Optional[Callable[[int], str]] = None,
) -> int:
    sent = 0
    due = store.due_alerts()
    if not due:
        return 0

    quiet = in_quiet_hours()

    try:
        await asyncio.to_thread(fx_light.get_irr_rate_bundle, force_refresh=False)
    except Exception:
        pass

    # Prefetch quake events once if any event alerts
    quake_events: list[dict[str, Any]] = []
    need_quake = any((r.get("_trigger") or r.get("trigger")) == "event" or r.get("kind") == "quake" for r in due)
    if need_quake:
        ok_q, quake_events = await asyncio.to_thread(fetch_earthquake_events, min_mag=3.5, limit=40)
        if not ok_q:
            quake_events = []

    for row in due:
        uid = int(row["user_id"])
        if not is_paid(uid):
            continue
        if row.get("_muted"):
            continue
        aid = int(row["id"])
        trigger = (row.get("_trigger") or row.get("trigger") or "schedule").lower()
        lang = "fa"
        if get_lang:
            try:
                lang = "en" if get_lang(uid) == "en" else "fa"
            except Exception:
                lang = "fa"

        try:
            if trigger == "event" or (row.get("kind") == "quake" and trigger != "schedule"):
                min_mag = store.quake_min_mag(row)
                seen = set(store.parse_event_ids(row.get("last_event_ids") or ""))
                # First run: seed seen without notifying (avoid backlog spam)
                if not seen and float(row.get("last_sent_at") or 0) <= 0:
                    seed = [e["id"] for e in quake_events if float(e.get("mag") or 0) >= min_mag][:40]
                    store.mark_sent(aid, event_ids=seed)
                    continue
                matched = []
                for ev in quake_events:
                    if float(ev.get("mag") or 0) < min_mag:
                        continue
                    if ev["id"] in seen:
                        continue
                    if not place_matches_asset(str(ev.get("place") or ""), row.get("asset") or ""):
                        continue
                    matched.append(ev)
                if not matched:
                    continue
                if quiet:
                    continue
                new_ids = list(seen)
                for ev in matched[:3]:
                    body, _p, _s = await compose_alert_body(row, lang=lang, event=ev)
                    if not body:
                        continue
                    kb = followup_keyboard(row, lang=lang)
                    await send_formatted(app, uid, body, reply_markup=kb)
                    new_ids.append(ev["id"])
                    sent += 1
                store.mark_sent(aid, event_ids=new_ids)
                continue

            body, price, is_spike = await compose_alert_body(row, lang=lang)
            if not body:
                # Still update last_price baseline for spike alerts so next poll can fire
                if trigger == "spike" and price is not None and row.get("last_price") is None:
                    store.mark_sent(aid, price=price)
                continue
            schedule_due = bool(row.get("_schedule_due"))
            if quiet and schedule_due and not is_spike:
                continue
            if trigger == "schedule" and not schedule_due:
                continue
            if trigger == "spike" and not is_spike:
                # Keep baseline fresh without notifying
                if price is not None:
                    store.mark_sent(aid, price=price)
                continue

            kb = followup_keyboard(row, lang=lang)
            await send_formatted(app, uid, body, reply_markup=kb)
            store.mark_sent(aid, price=price)
            sent += 1
        except Exception as e:
            log.warning("alert eval/send failed id=%s: %s", aid, e)
    return sent


async def alert_poll_loop(
    app: Any,
    *,
    is_paid: TierCheckFn,
    interval: float = 120.0,
    get_lang: Optional[Callable[[int], str]] = None,
) -> None:
    await asyncio.sleep(15)
    while True:
        try:
            n = await process_alerts_once(app, is_paid=is_paid, get_lang=get_lang)
            if n:
                log.info("alerts sent=%s", n)
        except Exception:
            log.exception("alert_poll_loop error")
        await asyncio.sleep(interval)
