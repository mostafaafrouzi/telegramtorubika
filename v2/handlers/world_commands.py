"""Weather, calendar, currency, earthquakes, timezone, age."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from v2.toolkit.calendar_light import age_report, calendar_report
from v2.core.msg_format import edit_formatted, reply_formatted, reply_html, reply_plain, strip_html
from v2.toolkit.fx_calculator import calculate_report
from v2.toolkit import fx_recent
from v2.toolkit.fx_light import currency_convert, market_quotes_report
from v2.toolkit.market_board import board_page_count
from v2.toolkit.timezone_light import timezone_report
from v2.toolkit.weather_light import air_quality_report, recent_earthquakes, weather_report

# Re-export feed background helpers for older imports.
from v2.handlers.feed_reader_commands import (  # noqa: F401
    maybe_send_daily_digest,
    poll_rss_pushes,
)

TranslateFn = Callable[..., str]
LogEventFn = Callable[..., None]
QuotaTryFn = Callable[[int], tuple[bool, str]]
QuotaCommitFn = Callable[[int], None]


@dataclass(frozen=True)
class WorldCommandDeps:
    tr: TranslateFn
    queue: Any
    get_state: Callable[[int], dict]
    set_state_preserving_menu: Callable[..., None]
    clear_state: Callable[[int], None]
    extract_first_url: Callable[[str], Optional[str]]
    get_lang: Callable[[int], str] = lambda _uid: "fa"
    log_event: LogEventFn = lambda *a, **k: None
    set_menu_section: Callable[..., None] | None = None
    world_quota_try: QuotaTryFn | None = None
    world_quota_commit: QuotaCommitFn | None = None


def _lang(deps: WorldCommandDeps, user_id: int) -> str:
    try:
        return "en" if deps.get_lang(user_id) == "en" else "fa"
    except Exception:
        return "fa"


async def _guard_world(deps: WorldCommandDeps, uid: int, message: Message) -> bool:
    from v2.core.upgrade_cta import buy_pro_keyboard

    if not deps.world_quota_try:
        return True
    ok, msg = deps.world_quota_try(uid)
    if ok:
        return True
    await message.reply_text(
        msg or deps.tr(uid, "world_quota_exceeded", used="?", limit="?"),
        reply_markup=buy_pro_keyboard(uid, deps.tr),
        parse_mode=None,
    )
    return False


def _commit_world(deps: WorldCommandDeps, uid: int) -> None:
    if deps.world_quota_commit:
        try:
            deps.world_quota_commit(uid)
        except Exception:
            pass


async def handle_markets(
    deps: WorldCommandDeps,
    client: Any,
    message: Message,
    *,
    board: str = "",
    edit: bool = False,
    page: int = 0,
) -> None:
    uid = message.from_user.id
    if not await _guard_world(deps, uid, message):
        return
    section = (board or "").strip().lower()
    if not section:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            section = parts[1].strip().lower()
        else:
            section = "hub"
    ok, body = await asyncio.to_thread(
        market_quotes_report, lang=_lang(deps, uid), section=section, page=page
    )
    if ok:
        _commit_world(deps, uid)
        board_cb = section if section in ("gold", "usd", "eur", "gbp", "jpy", "majors", "hub") else "hub"
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    deps.tr(uid, "btn_world_currency"), callback_data="imenu:currency"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 تازه‌سازی" if _lang(deps, uid) != "en" else "🔄 Refresh",
                    callback_data=f"imenu:{board_cb}"
                    if board_cb != "majors"
                    else f"mktpage:majors:{page}",
                )
            ],
        ]
        if board_cb == "majors":
            pages = board_page_count("majors")
            nav: list[InlineKeyboardButton] = []
            if page > 0:
                nav.append(
                    InlineKeyboardButton("◀️", callback_data=f"mktpage:majors:{page - 1}")
                )
            if page + 1 < pages:
                nav.append(
                    InlineKeyboardButton("▶️", callback_data=f"mktpage:majors:{page + 1}")
                )
            if nav:
                rows.insert(1, nav)
        kb = InlineKeyboardMarkup(rows)
        if edit:
            try:
                await edit_formatted(message, body, reply_markup=kb)
            except MessageNotModified:
                pass
            except Exception:
                await reply_formatted(message, body, reply_markup=kb)
            return
        await reply_formatted(message, body, reply_markup=kb)
        return
    err = deps.tr(uid, "world_error", detail=body)
    if edit:
        try:
            await edit_formatted(message, strip_html(err))
            return
        except Exception:
            pass
    await reply_plain(message, err)


async def handle_calendar(deps: WorldCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    if not await _guard_world(deps, uid, message):
        return
    body = await asyncio.to_thread(calendar_report, lang=_lang(deps, uid))
    _commit_world(deps, uid)
    await message.reply_text(body, parse_mode=None)  # plain calendar is fine


async def handle_earthquakes(
    deps: WorldCommandDeps,
    client: Any,
    message: Message,
    *,
    min_mag: float | None = None,
    pick: bool = False,
) -> None:
    uid = message.from_user.id
    if pick or min_mag is None:
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("≥ ۴", callback_data="quake:4"),
                    InlineKeyboardButton("≥ ۴.۵", callback_data="quake:4.5"),
                    InlineKeyboardButton("≥ ۵", callback_data="quake:5"),
                ],
                [
                    InlineKeyboardButton("≥ ۵.۵", callback_data="quake:5.5"),
                    InlineKeyboardButton("≥ ۶", callback_data="quake:6"),
                    InlineKeyboardButton("همه (≥۳)", callback_data="quake:3"),
                ],
            ]
        )
        await reply_plain(message, deps.tr(uid, "quake_pick_mag"), reply_markup=kb)
        return
    if not await _guard_world(deps, uid, message):
        return
    ok, body = await asyncio.to_thread(
        recent_earthquakes, lang=_lang(deps, uid), min_mag=float(min_mag)
    )
    if ok:
        _commit_world(deps, uid)
    await reply_formatted(
        message,
        body if ok else deps.tr(uid, "world_error", detail=body),
    )


async def dispatch_world_wizard(
    message: Message,
    user_id: int,
    text: str,
    deps: WorldCommandDeps,
) -> bool:
    """Text steps for weather / currency / timezone / age. Returns True if consumed."""
    state = deps.get_state(user_id)
    step = state.get("step")
    lang = _lang(deps, user_id)

    if step == "await_weather_city":
        city = text.strip()
        if not city:
            await message.reply_text(deps.tr(user_id, "weather_ask_city"), parse_mode=None)
            return True
        if not await _guard_world(deps, user_id, message):
            deps.clear_state(user_id)
            return True
        ok, body = await asyncio.to_thread(weather_report, city, lang=lang)
        ok2, aq = await asyncio.to_thread(air_quality_report, city, lang=lang)
        parts = [body if ok else deps.tr(user_id, "world_error", detail=body)]
        if ok2:
            parts.append("────────")
            parts.append(aq)
        if ok:
            _commit_world(deps, user_id)
        deps.clear_state(user_id)
        body = "\n\n".join(parts)
        await reply_formatted(message, body)
        return True

    if step == "await_fx_calc":
        raw = text.strip()
        if not raw:
            await reply_plain(message, deps.tr(user_id, "fx_calc_ask"))
            return True
        if not await _guard_world(deps, user_id, message):
            deps.clear_state(user_id)
            return True
        ok, body = await asyncio.to_thread(calculate_report, raw, lang=lang)
        if ok:
            _commit_world(deps, user_id)
            fx_recent.push(user_id, raw)
            # keep wizard open for another conversion
            deps.set_state_preserving_menu(user_id, {"step": "await_fx_calc"})
            kb = _fx_calc_keyboard(deps, user_id)
            await reply_html(message, body, reply_markup=kb)
        else:
            await reply_plain(message, deps.tr(user_id, "world_error", detail=body))
        return True

    if step == "await_currency_amount":
        # Free-form calculator path when text looks like amount+unit
        raw = text.strip()
        if any(ch.isalpha() or "\u0600" <= ch <= "\u06FF" for ch in raw):
            if not await _guard_world(deps, user_id, message):
                deps.clear_state(user_id)
                return True
            ok, body = await asyncio.to_thread(calculate_report, raw, lang=lang)
            if ok:
                _commit_world(deps, user_id)
                deps.set_state_preserving_menu(user_id, {"step": "await_fx_calc"})
                await reply_html(message, body)
            else:
                await reply_plain(message, deps.tr(user_id, "world_error", detail=body))
            return True
        amount_s = raw
        try:
            float(amount_s.replace(",", "").replace("٬", ""))
        except ValueError:
            await reply_plain(message, deps.tr(user_id, "currency_bad_amount"))
            return True
        await _after_currency_amount(deps, user_id, amount_s, message)
        return True

    if step == "await_currency_from":
        fc = text.strip().upper()
        if not fc:
            await message.reply_text(deps.tr(user_id, "currency_ask_from"), parse_mode=None)
            return True
        deps.set_state_preserving_menu(
            user_id, {"step": "await_currency_to", "amount": state.get("amount"), "from_code": fc}
        )
        await message.reply_text(deps.tr(user_id, "currency_ask_to"), parse_mode=None)
        return True

    if step == "await_currency_to":
        amount_s = str(state.get("amount") or "").strip()
        fc = str(state.get("from_code") or "").strip().upper()
        tc = text.strip().upper()
        try:
            amount = float(amount_s.replace(",", ""))
        except ValueError:
            await message.reply_text(deps.tr(user_id, "currency_bad_amount"), parse_mode=None)
            return True
        if not tc:
            await message.reply_text(deps.tr(user_id, "currency_ask_to"), parse_mode=None)
            return True
        if not await _guard_world(deps, user_id, message):
            deps.clear_state(user_id)
            return True
        ok, body = await asyncio.to_thread(currency_convert, amount, fc, tc, lang=lang)
        if ok:
            _commit_world(deps, user_id)
        deps.clear_state(user_id)
        await reply_formatted(
            message, body if ok else deps.tr(user_id, "world_error", detail=body)
        )
        return True

    if step == "await_currency_pair":
        # Back-compat: "USD IRR" still accepted
        amount_s = str(state.get("amount") or text).strip()
        try:
            amount = float(amount_s.replace(",", ""))
        except ValueError:
            await message.reply_text(deps.tr(user_id, "currency_bad_amount"), parse_mode=None)
            return True
        parts = text.strip().split()
        if len(parts) == 1 and parts[0].isalpha():
            deps.set_state_preserving_menu(
                user_id, {"step": "await_currency_to", "amount": amount_s, "from_code": parts[0].upper()}
            )
            await message.reply_text(deps.tr(user_id, "currency_ask_to"), parse_mode=None)
            return True
        if len(parts) < 2:
            deps.set_state_preserving_menu(user_id, {"step": "await_currency_from", "amount": amount_s})
            await message.reply_text(deps.tr(user_id, "currency_ask_from"), parse_mode=None)
            return True
        if not await _guard_world(deps, user_id, message):
            deps.clear_state(user_id)
            return True
        ok, body = await asyncio.to_thread(currency_convert, amount, parts[0], parts[1], lang=lang)
        if ok:
            _commit_world(deps, user_id)
        deps.clear_state(user_id)
        await reply_formatted(
            message, body if ok else deps.tr(user_id, "world_error", detail=body)
        )
        return True

    if step == "await_timezone_place":
        place = text.strip()
        if not place:
            await message.reply_text(deps.tr(user_id, "timezone_ask_place"), parse_mode=None)
            return True
        if not await _guard_world(deps, user_id, message):
            deps.clear_state(user_id)
            return True
        ok, body = await asyncio.to_thread(timezone_report, place, lang=lang)
        if ok:
            _commit_world(deps, user_id)
        deps.clear_state(user_id)
        await reply_formatted(
            message, body if ok else deps.tr(user_id, "world_error", detail=body)
        )
        return True

    if step == "await_age_date":
        raw = text.strip()
        if not raw:
            await message.reply_text(deps.tr(user_id, "age_ask_date"), parse_mode=None)
            return True
        if not await _guard_world(deps, user_id, message):
            deps.clear_state(user_id)
            return True
        ok, body = await asyncio.to_thread(age_report, raw, lang=lang)
        if ok:
            _commit_world(deps, user_id)
        deps.clear_state(user_id)
        await reply_formatted(
            message, body if ok else deps.tr(user_id, "world_error", detail=body)
        )
        return True

    return False


async def start_weather_wizard(deps: WorldCommandDeps, message: Message) -> None:
    uid = message.from_user.id
    deps.set_state_preserving_menu(uid, {"step": "await_weather_city"})
    await message.reply_text(deps.tr(uid, "weather_ask_city"), parse_mode=None)


def _fx_calc_keyboard(deps: WorldCommandDeps, uid: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("۱۰۰٬۰۰۰ تومان", callback_data="fxcalc:100000 IRT"),
            InlineKeyboardButton("۱ دلار", callback_data="fxcalc:1 USD"),
        ],
        [
            InlineKeyboardButton("۱ یورو", callback_data="fxcalc:1 EUR"),
            InlineKeyboardButton("۱ سکه امامی", callback_data="fxcalc:1 SEKEE"),
        ],
        [
            InlineKeyboardButton("۱ گرم طلا", callback_data="fxcalc:1 GOLD18"),
            InlineKeyboardButton("۱۰٬۰۰۰٬۰۰۰ ریال", callback_data="fxcalc:10000000 IRR"),
        ],
    ]
    recent = fx_recent.list_recent(uid, limit=4)
    if recent:
        rows.append(
            [
                InlineKeyboardButton(f"⏱ {q[:28]}", callback_data=f"fxcalc:{q[:60]}")
                for q in recent[:2]
            ]
        )
        if len(recent) > 2:
            rows.append(
                [
                    InlineKeyboardButton(f"⏱ {q[:28]}", callback_data=f"fxcalc:{q[:60]}")
                    for q in recent[2:4]
                ]
            )
    return InlineKeyboardMarkup(rows)


async def start_currency_wizard(deps: WorldCommandDeps, message: Message) -> None:
    from v2.core.menu_sections import MenuSection

    uid = message.from_user.id
    deps.set_state_preserving_menu(uid, {"step": "await_fx_calc"})
    kb = _fx_calc_keyboard(deps, uid)
    if deps.set_menu_section:
        deps.set_menu_section(uid, MenuSection.WORLD)
    await reply_plain(message, deps.tr(uid, "fx_calc_ask"), reply_markup=kb)


# After amount, go to from-code (not combined pair)
async def _after_currency_amount(deps: WorldCommandDeps, user_id: int, amount_s: str, message: Message) -> None:
    deps.set_state_preserving_menu(user_id, {"step": "await_currency_from", "amount": amount_s})
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("USD", callback_data="fxfrom:USD"),
                InlineKeyboardButton("EUR", callback_data="fxfrom:EUR"),
                InlineKeyboardButton("IRR", callback_data="fxfrom:IRR"),
            ]
        ]
    )
    await message.reply_text(deps.tr(user_id, "currency_ask_from"), reply_markup=kb, parse_mode=None)


async def start_timezone_wizard(deps: WorldCommandDeps, message: Message) -> None:
    uid = message.from_user.id
    deps.set_state_preserving_menu(uid, {"step": "await_timezone_place"})
    await message.reply_text(deps.tr(uid, "timezone_ask_place"), parse_mode=None)


async def start_age_wizard(deps: WorldCommandDeps, message: Message) -> None:
    uid = message.from_user.id
    deps.set_state_preserving_menu(uid, {"step": "await_age_date"})
    await message.reply_text(deps.tr(uid, "age_ask_date"), parse_mode=None)


async def handle_fx_quick_callback(
    deps: WorldCommandDeps,
    client: Any,
    callback_query: Any,
    amount_s: str,
    fc: str,
    tc: str,
) -> bool:
    uid = callback_query.from_user.id
    try:
        amount = float(amount_s)
    except ValueError:
        await callback_query.answer("bad amount", show_alert=True)
        return True
    if deps.world_quota_try:
        ok_q, msg = deps.world_quota_try(uid)
        if not ok_q:
            await callback_query.answer(msg[:180] if msg else "quota", show_alert=True)
            return True
    await callback_query.answer()
    lang = _lang(deps, uid)
    ok, body = await asyncio.to_thread(currency_convert, amount, fc, tc, lang=lang)
    if ok:
        _commit_world(deps, uid)
    deps.clear_state(uid)
    msg = callback_query.message
    if ok and "<b>" in body:
        await reply_html(msg, body)
    else:
        await reply_plain(msg, body if ok else deps.tr(uid, "world_error", detail=body))
    return True


async def handle_market_page_callback(
    deps: WorldCommandDeps,
    client: Any,
    callback_query: Any,
    board: str,
    page: int,
) -> bool:
    await callback_query.answer()
    await handle_markets(
        deps,
        client,
        callback_query.message,
        board=board,
        edit=True,
        page=page,
    )
    return True


async def handle_quake_mag_callback(
    deps: WorldCommandDeps,
    client: Any,
    callback_query: Any,
    mag_s: str,
) -> bool:
    await callback_query.answer()
    try:
        mag = float(mag_s)
    except ValueError:
        mag = 4.5
    await handle_earthquakes(
        deps, client, callback_query.message, min_mag=mag, pick=False
    )
    return True


async def handle_fx_calc_callback(
    deps: WorldCommandDeps,
    client: Any,
    callback_query: Any,
    payload: str,
) -> bool:
    uid = callback_query.from_user.id
    if deps.world_quota_try:
        ok_q, msg = deps.world_quota_try(uid)
        if not ok_q:
            await callback_query.answer(msg[:180] if msg else "quota", show_alert=True)
            return True
    await callback_query.answer()
    lang = _lang(deps, uid)
    ok, body = await asyncio.to_thread(calculate_report, payload, lang=lang)
    if ok:
        _commit_world(deps, uid)
        fx_recent.push(uid, payload)
        deps.set_state_preserving_menu(uid, {"step": "await_fx_calc"})
        await reply_html(
            callback_query.message, body, reply_markup=_fx_calc_keyboard(deps, uid)
        )
    else:
        await reply_plain(
            callback_query.message,
            deps.tr(uid, "world_error", detail=body),
        )
    return True
