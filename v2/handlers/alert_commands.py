"""Multi-step wizard for paid alert subscriptions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from v2.alerts import store
from v2.alerts.poller import compose_alert_body, followup_keyboard, schedule_label
from v2.alerts.store import quake_min_mag
from v2.core.menu_sections import MenuSection
from v2.core.msg_format import reply_plain, send_formatted
from v2.core.upgrade_cta import buy_pro_keyboard

TranslateFn = Callable[..., str]
IsPaidFn = Callable[[int], bool]

_KIND_FA = {"fx": "💵 ارز", "gold": "🥇 طلا", "weather": "🌤 آب‌وهوا", "quake": "🌍 زلزله"}
_KIND_EN = {"fx": "💵 FX", "gold": "🥇 Gold", "weather": "🌤 Weather", "quake": "🌍 Quake"}


@dataclass(frozen=True)
class AlertCommandDeps:
    tr: TranslateFn
    set_menu_section: Callable[[int, MenuSection], None]
    set_state_preserving_menu: Callable[..., None]
    clear_state: Callable[[int], None]
    get_state: Callable[[int], dict]
    is_paid_user: IsPaidFn
    get_lang: Callable[[int], str] = lambda _uid: "fa"


def _lang(deps: AlertCommandDeps, uid: int) -> str:
    try:
        return "en" if deps.get_lang(uid) == "en" else "fa"
    except Exception:
        return "fa"


def _schedule_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ساعتی", callback_data="alertsch:hourly"),
                InlineKeyboardButton("روزانه", callback_data="alertsch:daily"),
                InlineKeyboardButton("هفتگی", callback_data="alertsch:weekly"),
            ]
        ]
    )


def _hour_kb() -> InlineKeyboardMarkup:
    hours = (7, 8, 9, 12, 18, 21)
    row = [
        InlineKeyboardButton(f"{h:02d}:00", callback_data=f"alerthour:{h}") for h in hours
    ]
    return InlineKeyboardMarkup([row[:3], row[3:]])


def _spike_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("۱٪", callback_data="alertspike:1"),
                InlineKeyboardButton("۲٪", callback_data="alertspike:2"),
                InlineKeyboardButton("۵٪", callback_data="alertspike:5"),
            ],
            [
                InlineKeyboardButton("بدون جهش", callback_data="alertspike:none"),
                InlineKeyboardButton("سفارشی…", callback_data="alertspike:custom"),
            ],
        ]
    )


def _quake_mag_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("≥ ۴", callback_data="alertqmag:4"),
                InlineKeyboardButton("≥ ۴.۵", callback_data="alertqmag:4.5"),
                InlineKeyboardButton("≥ ۵", callback_data="alertqmag:5"),
            ],
            [
                InlineKeyboardButton("≥ ۵.۵", callback_data="alertqmag:5.5"),
                InlineKeyboardButton("≥ ۶", callback_data="alertqmag:6"),
            ],
        ]
    )


def _saved_kb(alert_id: int, uid: int, tr: TranslateFn) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr(uid, "alerts_btn_test"), callback_data=f"alerttest:{alert_id}"
                ),
                InlineKeyboardButton(
                    tr(uid, "alerts_btn_list"), callback_data="alertkind:list"
                ),
            ]
        ]
    )


def _format_alert_line(r: dict[str, Any], *, lang: str) -> str:
    kind = r.get("kind") or ""
    label = (_KIND_EN if lang == "en" else _KIND_FA).get(kind, kind)
    on = "✅" if r.get("enabled") else "⏸"
    asset = r.get("asset") or "-"
    sched = schedule_label(r, lang=lang)
    extra = ""
    if kind == "quake":
        extra = f" · ≥{quake_min_mag(r):g}"
    elif r.get("spike_pct") is not None:
        extra = f" · ≥{float(r['spike_pct']):g}%"
    muted = float(r.get("muted_until") or 0)
    mute_s = " · 🔇" if muted > time.time() else ""
    return f"{on} #{r['id']} · {label} · {asset} · {sched}{extra}{mute_s}"


def _list_keyboard(rows: list[dict[str, Any]], uid: int, tr: TranslateFn) -> InlineKeyboardMarkup:
    kb_rows: list[list[InlineKeyboardButton]] = []
    for r in rows[:10]:
        aid = int(r["id"])
        en = bool(r.get("enabled"))
        tog = tr(uid, "alerts_btn_disable") if en else tr(uid, "alerts_btn_enable")
        muted = float(r.get("muted_until") or 0) > time.time()
        kb_rows.append(
            [
                InlineKeyboardButton(tog, callback_data=f"alerttog:{aid}"),
                InlineKeyboardButton(
                    tr(uid, "alerts_btn_test"), callback_data=f"alerttest:{aid}"
                ),
                InlineKeyboardButton(
                    tr(uid, "alerts_btn_delete"), callback_data=f"alertdel:{aid}"
                ),
            ]
        )
        if muted:
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        tr(uid, "alerts_btn_unmute"), callback_data=f"alertmute:{aid}:0"
                    )
                ]
            )
        else:
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        tr(uid, "alerts_btn_mute_24h"), callback_data=f"alertmute:{aid}:24"
                    ),
                    InlineKeyboardButton(
                        tr(uid, "alerts_btn_mute_7d"), callback_data=f"alertmute:{aid}:168"
                    ),
                ]
            )
    kb_rows.append(
        [InlineKeyboardButton(tr(uid, "alerts_btn_new"), callback_data="alertkind:menu")]
    )
    return InlineKeyboardMarkup(kb_rows)


async def _reply_list(deps: AlertCommandDeps, message: Message, uid: int, *, edit: bool = False) -> None:
    rows = store.list_alerts(uid)
    if not rows:
        text = deps.tr(uid, "alerts_empty")
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(deps.tr(uid, "alerts_btn_new"), callback_data="alertkind:menu")]]
        )
    else:
        lang = _lang(deps, uid)
        lines = [deps.tr(uid, "alerts_list_title")]
        for r in rows[:10]:
            lines.append(_format_alert_line(r, lang=lang))
        if len(rows) > 10:
            lines.append(f"… +{len(rows) - 10}")
        text = "\n".join(lines)
        kb = _list_keyboard(rows, uid, deps.tr)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode=None)
            return
        except Exception:
            pass
    await reply_plain(message, text, reply_markup=kb)


async def _after_save(
    deps: AlertCommandDeps,
    message: Message,
    uid: int,
    *,
    ok: bool,
    err: str,
    aid: int,
    ok_key: str = "alerts_added_ok",
    **fmt: Any,
) -> None:
    deps.clear_state(uid)
    if not ok:
        await reply_plain(message, deps.tr(uid, "alerts_add_fail", detail=err))
        return
    await reply_plain(
        message,
        deps.tr(uid, ok_key, **fmt),
        reply_markup=_saved_kb(aid, uid, deps.tr) if aid else None,
    )


async def start_alert_wizard(deps: AlertCommandDeps, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.WORLD)
    if not deps.is_paid_user(uid):
        await reply_plain(
            message,
            deps.tr(uid, "alerts_paid_only"),
            reply_markup=buy_pro_keyboard(uid, deps.tr),
        )
        return
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💵 ارز", callback_data="alertkind:fx"),
                InlineKeyboardButton("🥇 طلا", callback_data="alertkind:gold"),
            ],
            [
                InlineKeyboardButton("🌤 آب‌وهوا", callback_data="alertkind:weather"),
                InlineKeyboardButton("🌍 زلزله", callback_data="alertkind:quake"),
            ],
            [InlineKeyboardButton("📋 لیست هشدارها", callback_data="alertkind:list")],
        ]
    )
    await reply_plain(message, deps.tr(uid, "alerts_pick_kind"), reply_markup=kb)


async def handle_alert_kind_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, kind: str
) -> bool:
    uid = callback_query.from_user.id
    await callback_query.answer()
    if not deps.is_paid_user(uid):
        await reply_plain(
            callback_query.message,
            deps.tr(uid, "alerts_paid_only"),
            reply_markup=buy_pro_keyboard(uid, deps.tr),
        )
        return True
    if kind == "menu":
        await start_alert_wizard(deps, callback_query.message)
        return True
    if kind == "list":
        await _reply_list(deps, callback_query.message, uid, edit=True)
        return True
    if kind == "quake":
        deps.set_state_preserving_menu(
            uid,
            {
                "step": "await_alert_schedule",
                "alert_kind": "quake",
                "alert_asset": "",
            },
        )
        await reply_plain(
            callback_query.message, deps.tr(uid, "alerts_ask_schedule"), reply_markup=_schedule_kb()
        )
        return True
    deps.set_state_preserving_menu(
        uid, {"step": "await_alert_asset", "alert_kind": kind}
    )
    hint = {
        "fx": "alerts_ask_fx_asset",
        "gold": "alerts_ask_gold_asset",
        "weather": "alerts_ask_weather_city",
        "quake": "alerts_ask_quake_city",
    }.get(kind, "alerts_ask_fx_asset")
    await reply_plain(callback_query.message, deps.tr(uid, hint))
    return True


def _advance_after_schedule(
    deps: AlertCommandDeps, uid: int, *, kind: str, asset: str, schedule: str
) -> tuple[str, Optional[InlineKeyboardMarkup], dict]:
    """Return (prompt_key, keyboard, next_state) after schedule pick."""
    base = {
        "alert_kind": kind,
        "alert_asset": asset,
        "alert_schedule": schedule,
        "alert_hour": 9,
    }
    if schedule in ("daily", "weekly"):
        state = {**base, "step": "await_alert_hour"}
        return "alerts_ask_hour", _hour_kb(), state
    return _advance_after_hour(deps, uid, state={**base, "alert_hour": 9})


def _advance_after_hour(
    deps: AlertCommandDeps, uid: int, *, state: dict
) -> tuple[str, Optional[InlineKeyboardMarkup], dict]:
    kind = str(state.get("alert_kind") or "fx")
    base = {
        "alert_kind": kind,
        "alert_asset": state.get("alert_asset") or "",
        "alert_schedule": state.get("alert_schedule") or "daily",
        "alert_hour": int(state.get("alert_hour") or 9),
    }
    if kind == "quake":
        st = {**base, "step": "await_alert_quake_mag"}
        return "alerts_ask_quake_mag", _quake_mag_kb(), st
    if kind == "weather":
        st = {**base, "step": "await_alert_finalize_weather"}
        return "", None, st
    st = {**base, "step": "await_alert_spike"}
    return "alerts_ask_spike", _spike_kb(), st


async def _maybe_finalize_weather(
    deps: AlertCommandDeps, message: Message, uid: int, state: dict
) -> bool:
    if state.get("step") != "await_alert_finalize_weather":
        return False
    ok, err, aid = store.add_alert(
        uid,
        kind="weather",
        asset=str(state.get("alert_asset") or "Tehran"),
        schedule=str(state.get("alert_schedule") or "daily"),
        spike_pct=None,
        hour_tehran=int(state.get("alert_hour") or 9),
    )
    await _after_save(deps, message, uid, ok=ok, err=err, aid=aid)
    return True


async def handle_alert_schedule_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, schedule: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    await callback_query.answer()
    if state.get("step") != "await_alert_schedule":
        return True
    kind = str(state.get("alert_kind") or "fx")
    asset = str(state.get("alert_asset") or "")
    key, kb, nxt = _advance_after_schedule(
        deps, uid, kind=kind, asset=asset, schedule=schedule
    )
    deps.set_state_preserving_menu(uid, nxt)
    if await _maybe_finalize_weather(deps, callback_query.message, uid, nxt):
        return True
    if key:
        await reply_plain(callback_query.message, deps.tr(uid, key), reply_markup=kb)
    return True


async def handle_alert_hour_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, hour_s: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    await callback_query.answer()
    if state.get("step") != "await_alert_hour":
        return True
    try:
        hour = max(0, min(23, int(hour_s)))
    except ValueError:
        hour = 9
    merged = {
        **state,
        "alert_hour": hour,
    }
    key, kb, nxt = _advance_after_hour(deps, uid, state=merged)
    deps.set_state_preserving_menu(uid, nxt)
    if await _maybe_finalize_weather(deps, callback_query.message, uid, nxt):
        return True
    if key:
        await reply_plain(callback_query.message, deps.tr(uid, key), reply_markup=kb)
    return True


async def handle_alert_spike_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, spike_s: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    await callback_query.answer()
    if state.get("step") != "await_alert_spike":
        return True
    if spike_s == "custom":
        deps.set_state_preserving_menu(
            uid, {**state, "step": "await_alert_spike_custom"}
        )
        await reply_plain(callback_query.message, deps.tr(uid, "alerts_ask_spike_custom"))
        return True
    spike: Optional[float] = None
    if spike_s != "none":
        try:
            spike = float(spike_s)
        except ValueError:
            await reply_plain(callback_query.message, deps.tr(uid, "alerts_ask_spike"))
            return True
    ok, err, aid = store.add_alert(
        uid,
        kind=str(state.get("alert_kind") or "fx"),
        asset=str(state.get("alert_asset") or ""),
        schedule=str(state.get("alert_schedule") or "daily"),
        spike_pct=spike,
        hour_tehran=int(state.get("alert_hour") or 9),
    )
    await _after_save(deps, callback_query.message, uid, ok=ok, err=err, aid=aid)
    return True


async def dispatch_alert_wizard(
    deps: AlertCommandDeps, message: Message, user_id: int, text: str
) -> bool:
    state = deps.get_state(user_id)
    step = state.get("step")
    if step == "await_alert_asset":
        asset = text.strip()
        if not asset:
            await reply_plain(message, deps.tr(user_id, "alerts_ask_fx_asset"))
            return True
        deps.set_state_preserving_menu(
            user_id,
            {
                "step": "await_alert_schedule",
                "alert_kind": state.get("alert_kind"),
                "alert_asset": asset,
            },
        )
        await reply_plain(
            message, deps.tr(user_id, "alerts_ask_schedule"), reply_markup=_schedule_kb()
        )
        return True
    if step == "await_alert_spike_custom":
        raw = text.strip().replace("%", "")
        spike = None
        if raw not in ("-", "—", "no", "خیر", "0"):
            try:
                spike = float(raw.replace(",", "."))
            except ValueError:
                await reply_plain(message, deps.tr(user_id, "alerts_ask_spike_custom"))
                return True
        ok, err, aid = store.add_alert(
            user_id,
            kind=str(state.get("alert_kind") or "fx"),
            asset=str(state.get("alert_asset") or ""),
            schedule=str(state.get("alert_schedule") or "daily"),
            spike_pct=spike,
            hour_tehran=int(state.get("alert_hour") or 9),
        )
        await _after_save(deps, message, user_id, ok=ok, err=err, aid=aid)
        return True
    if step == "await_alert_spike":
        # Legacy text path: still accept typed % while buttons are primary.
        raw = text.strip().replace("%", "")
        spike = None
        if raw not in ("-", "—", "no", "خیر", "0"):
            try:
                spike = float(raw.replace(",", "."))
            except ValueError:
                await reply_plain(
                    message, deps.tr(user_id, "alerts_ask_spike"), reply_markup=_spike_kb()
                )
                return True
        ok, err, aid = store.add_alert(
            user_id,
            kind=str(state.get("alert_kind") or "fx"),
            asset=str(state.get("alert_asset") or ""),
            schedule=str(state.get("alert_schedule") or "daily"),
            spike_pct=spike,
            hour_tehran=int(state.get("alert_hour") or 9),
        )
        await _after_save(deps, message, user_id, ok=ok, err=err, aid=aid)
        return True
    return False


async def handle_alert_quake_mag_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, mag_s: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    await callback_query.answer()
    if state.get("step") != "await_alert_quake_mag":
        return True
    try:
        mag = float(mag_s)
    except ValueError:
        mag = 4.5
    ok, err, aid = store.add_alert(
        uid,
        kind="quake",
        asset=str(state.get("alert_asset") or ""),
        schedule=str(state.get("alert_schedule") or "daily"),
        min_mag=mag,
        hour_tehran=int(state.get("alert_hour") or 9),
    )
    await _after_save(
        deps,
        callback_query.message,
        uid,
        ok=ok,
        err=err,
        aid=aid,
        ok_key="alerts_quake_added_ok",
        mag=f"{mag:g}",
    )
    return True


async def handle_alert_manage_callback(
    deps: AlertCommandDeps,
    client: Any,
    callback_query: Any,
    action: str,
    alert_id: int,
    extra: str | None = None,
) -> bool:
    uid = callback_query.from_user.id
    if not deps.is_paid_user(uid):
        await callback_query.answer(deps.tr(uid, "alerts_paid_only"), show_alert=True)
        return True

    if action == "del":
        ok = store.delete_alert(uid, alert_id)
        await callback_query.answer(
            deps.tr(uid, "alerts_deleted" if ok else "alerts_not_found")
        )
        await _reply_list(deps, callback_query.message, uid, edit=True)
        return True

    if action == "tog":
        new_val = store.toggle_enabled(uid, alert_id)
        if new_val is None:
            await callback_query.answer(deps.tr(uid, "alerts_not_found"), show_alert=True)
            return True
        await callback_query.answer(
            deps.tr(uid, "alerts_enabled" if new_val else "alerts_disabled")
        )
        await _reply_list(deps, callback_query.message, uid, edit=True)
        return True

    if action == "mute":
        try:
            hours = float(extra) if extra is not None else 24.0
        except ValueError:
            hours = 24.0
        ok = store.mute_alert(uid, alert_id, hours=hours)
        if not ok:
            await callback_query.answer(deps.tr(uid, "alerts_not_found"), show_alert=True)
            return True
        if hours <= 0:
            await callback_query.answer(deps.tr(uid, "alerts_unmuted"))
        elif hours >= 168:
            await callback_query.answer(deps.tr(uid, "alerts_muted_7d"))
        else:
            await callback_query.answer(deps.tr(uid, "alerts_muted_24h"))
        list_title = deps.tr(uid, "alerts_list_title")
        body = callback_query.message.text or callback_query.message.caption or ""
        if body.startswith(list_title) or list_title in body[:120]:
            await _reply_list(deps, callback_query.message, uid, edit=True)
        else:
            row = store.get_alert(uid, alert_id)
            if row:
                try:
                    await callback_query.message.edit_reply_markup(
                        followup_keyboard(row, lang=_lang(deps, uid))
                    )
                except Exception:
                    pass
        return True

    if action == "test":
        row = store.get_alert(uid, alert_id)
        if not row:
            await callback_query.answer(deps.tr(uid, "alerts_not_found"), show_alert=True)
            return True
        await callback_query.answer(deps.tr(uid, "alerts_test_sending"))
        lang = _lang(deps, uid)
        try:
            body, _price, _spike = await compose_alert_body(
                row, force_schedule=True, lang=lang
            )
            if not body:
                await reply_plain(
                    callback_query.message, deps.tr(uid, "alerts_test_fail", detail="empty")
                )
                return True
            prefix = deps.tr(uid, "alerts_test_prefix")
            kb = followup_keyboard(row, lang=lang)
            await send_formatted(client, uid, f"<i>{prefix}</i>\n\n{body}", reply_markup=kb)
        except Exception as e:
            await reply_plain(
                callback_query.message,
                deps.tr(uid, "alerts_test_fail", detail=str(e)[:120]),
            )
        return True

    await callback_query.answer()
    return True
