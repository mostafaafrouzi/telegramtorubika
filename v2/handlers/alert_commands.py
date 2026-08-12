"""Alert wizard: picker-based FX/gold, event quakes, clearer list management."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from v2.alerts import free_digest, store
from v2.alerts.poller import compose_alert_body, followup_keyboard, schedule_label
from v2.core.menu_sections import MenuSection
from v2.core.miniapp_urls import miniapp_page_url
from v2.core.msg_format import reply_plain, send_formatted
from v2.core.upgrade_cta import buy_pro_keyboard
from v2.toolkit.iran_quake_geo import (
    CITIES,
    PROVINCES,
    encode_quake_asset,
    label as geo_label,
    summarize_quake_asset,
)
from v2.toolkit.market_board import asset_label, fx_alert_codes, gold_alert_codes

TranslateFn = Callable[..., str]
IsPaidFn = Callable[[int], bool]


@dataclass(frozen=True)
class AlertCommandDeps:
    tr: TranslateFn
    set_menu_section: Callable[[int, MenuSection], None]
    set_state_preserving_menu: Callable[..., None]
    clear_state: Callable[[int], None]
    get_state: Callable[[int], dict]
    is_paid_user: IsPaidFn
    get_lang: Callable[[int], str] = lambda _uid: "fa"
    miniapp_base_url: str = ""


def _lang(deps: AlertCommandDeps, uid: int) -> str:
    try:
        return "en" if deps.get_lang(uid) == "en" else "fa"
    except Exception:
        return "fa"


def _miniapp_btn(deps: AlertCommandDeps, uid: int) -> InlineKeyboardButton | None:
    url = miniapp_page_url(deps.miniapp_base_url, "alerts.html")
    if not url:
        return None
    return InlineKeyboardButton(deps.tr(uid, "alerts_btn_miniapp"), web_app=WebAppInfo(url=url))


def _free_kb(deps: AlertCommandDeps, uid: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(deps.tr(uid, "alerts_free_btn_fx"), callback_data="alertfree:fx"),
            InlineKeyboardButton(
                deps.tr(uid, "alerts_free_btn_weather"), callback_data="alertfree:weather"
            ),
        ],
        [InlineKeyboardButton(deps.tr(uid, "alerts_free_btn_off"), callback_data="alertfree:off")],
    ]
    rows.extend(buy_pro_keyboard(uid, deps.tr).inline_keyboard)
    b = _miniapp_btn(deps, uid)
    if b:
        rows.append([b])
    return InlineKeyboardMarkup(rows)


def _main_kb(deps: AlertCommandDeps, uid: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(deps.tr(uid, "alerts_kind_fx"), callback_data="alertkind:fx"),
            InlineKeyboardButton(deps.tr(uid, "alerts_kind_gold"), callback_data="alertkind:gold"),
        ],
        [
            InlineKeyboardButton(
                deps.tr(uid, "alerts_kind_weather"), callback_data="alertkind:weather"
            ),
            InlineKeyboardButton(
                deps.tr(uid, "alerts_kind_quake"), callback_data="alertkind:quake"
            ),
        ],
        [InlineKeyboardButton(deps.tr(uid, "alerts_btn_list"), callback_data="alertkind:list")],
    ]
    b = _miniapp_btn(deps, uid)
    if b:
        rows.append([b])
    return InlineKeyboardMarkup(rows)


def _format_alert_card(r: dict[str, Any], *, lang: str) -> str:
    kind = r.get("kind") or ""
    on = "✅" if r.get("enabled") else "⏸"
    trigger = (r.get("trigger") or "schedule").lower()
    if kind in ("fx", "gold"):
        title = asset_label(str(r.get("asset") or ""), lang=lang)
    elif kind == "quake":
        title = summarize_quake_asset(str(r.get("asset") or ""), lang=lang)
    else:
        title = r.get("asset") or kind
    mode = schedule_label(r, lang=lang)
    muted = " · 🔇" if float(r.get("muted_until") or 0) > time.time() else ""
    icon = {"fx": "💵", "gold": "🥇", "weather": "🌤", "quake": "🌍"}.get(kind, "🔔")
    return f"{on} {icon} #{r['id']} · {title}\n   {mode}{muted}"


def _list_kb(rows: list[dict[str, Any]], uid: int, tr: TranslateFn) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    for r in rows[:15]:
        aid = int(r["id"])
        kb.append(
            [
                InlineKeyboardButton(
                    tr(uid, "alerts_btn_manage_id", id=aid), callback_data=f"alertm:{aid}"
                )
            ]
        )
    kb.append([InlineKeyboardButton(tr(uid, "alerts_btn_new"), callback_data="alertkind:menu")])
    return InlineKeyboardMarkup(kb)


def _manage_kb(r: dict[str, Any], uid: int, tr: TranslateFn) -> InlineKeyboardMarkup:
    aid = int(r["id"])
    en = bool(r.get("enabled"))
    muted = float(r.get("muted_until") or 0) > time.time()
    rows = [
        [
            InlineKeyboardButton(
                tr(uid, "alerts_btn_disable") if en else tr(uid, "alerts_btn_enable"),
                callback_data=f"alerttog:{aid}",
            ),
            InlineKeyboardButton(tr(uid, "alerts_btn_test"), callback_data=f"alerttest:{aid}"),
        ],
    ]
    if muted:
        rows.append(
            [InlineKeyboardButton(tr(uid, "alerts_btn_unmute"), callback_data=f"alertmute:{aid}:0")]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    tr(uid, "alerts_btn_mute_24h"), callback_data=f"alertmute:{aid}:24"
                ),
                InlineKeyboardButton(
                    tr(uid, "alerts_btn_mute_7d"), callback_data=f"alertmute:{aid}:168"
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(tr(uid, "alerts_btn_delete"), callback_data=f"alertdel:{aid}"),
            InlineKeyboardButton(tr(uid, "alerts_btn_back_list"), callback_data="alertkind:list"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def _reply_list(
    deps: AlertCommandDeps, message: Message, uid: int, *, edit: bool = False
) -> None:
    rows = store.list_alerts(uid)
    if not rows:
        text = deps.tr(uid, "alerts_empty")
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(deps.tr(uid, "alerts_btn_new"), callback_data="alertkind:menu")]]
        )
    else:
        lang = _lang(deps, uid)
        lines = [deps.tr(uid, "alerts_list_title"), ""]
        for r in rows[:15]:
            lines.append(_format_alert_card(r, lang=lang))
            lines.append("")
        if len(rows) > 15:
            lines.append(f"… +{len(rows) - 15}")
        text = "\n".join(lines).rstrip()
        kb = _list_kb(rows, uid, deps.tr)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode=None)
            return
        except Exception:
            pass
    await reply_plain(message, text, reply_markup=kb)


async def _reply_manage(
    deps: AlertCommandDeps, message: Message, uid: int, alert_id: int, *, edit: bool = True
) -> None:
    row = store.get_alert(uid, alert_id)
    if not row:
        await reply_plain(message, deps.tr(uid, "alerts_not_found"))
        return
    lang = _lang(deps, uid)
    text = deps.tr(uid, "alerts_manage_title") + "\n\n" + _format_alert_card(row, lang=lang)
    kb = _manage_kb(row, uid, deps.tr)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode=None)
            return
        except Exception:
            pass
    await reply_plain(message, text, reply_markup=kb)


def _chunk_buttons(
    items: list[InlineKeyboardButton], per_row: int = 2
) -> list[list[InlineKeyboardButton]]:
    return [items[i : i + per_row] for i in range(0, len(items), per_row)]


def _asset_picker_kb(
    deps: AlertCommandDeps,
    uid: int,
    *,
    kind: str,
    selected: set[str],
    lang: str,
) -> InlineKeyboardMarkup:
    codes = fx_alert_codes() if kind == "fx" else gold_alert_codes()
    btns: list[InlineKeyboardButton] = []
    for code in codes:
        mark = "✅ " if code in selected else ""
        btns.append(
            InlineKeyboardButton(
                f"{mark}{asset_label(code, lang=lang)}",
                callback_data=f"alertsel:{code}",
            )
        )
    rows = _chunk_buttons(btns, 2)
    rows.append(
        [
            InlineKeyboardButton(
                deps.tr(uid, "alerts_btn_done_pick", n=len(selected)),
                callback_data="alertsel:done",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(deps.tr(uid, "alerts_btn_cancel"), callback_data="alertkind:menu")]
    )
    return InlineKeyboardMarkup(rows)


def _geo_picker_kb(
    deps: AlertCommandDeps,
    uid: int,
    *,
    mode: str,
    selected: set[str],
    lang: str,
    page: int = 0,
) -> InlineKeyboardMarkup:
    table = PROVINCES if mode == "province" else CITIES
    ids = list(table.keys())
    page_size = 12
    start = page * page_size
    chunk = ids[start : start + page_size]
    btns: list[InlineKeyboardButton] = []
    for gid in chunk:
        mark = "✅ " if gid in selected else ""
        btns.append(
            InlineKeyboardButton(
                f"{mark}{geo_label(mode, gid, lang=lang)}",
                callback_data=f"alertgeo:{mode}:{gid}",
            )
        )
    rows = _chunk_buttons(btns, 2)
    nav: list[InlineKeyboardButton] = []
    if start > 0:
        nav.append(
            InlineKeyboardButton("◀️", callback_data=f"alertgeopage:{mode}:{page - 1}")
        )
    if start + page_size < len(ids):
        nav.append(
            InlineKeyboardButton("▶️", callback_data=f"alertgeopage:{mode}:{page + 1}")
        )
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                deps.tr(uid, "alerts_btn_done_pick", n=len(selected)),
                callback_data="alertgeo:done",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _hour_kb() -> InlineKeyboardMarkup:
    hours = (7, 8, 9, 12, 18, 21)
    row = [InlineKeyboardButton(f"{h:02d}:00", callback_data=f"alerthour:{h}") for h in hours]
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
                InlineKeyboardButton("۳٪", callback_data="alertspike:3"),
                InlineKeyboardButton("۱۰٪", callback_data="alertspike:10"),
            ],
        ]
    )


async def start_alert_wizard(deps: AlertCommandDeps, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.WORLD)
    if not deps.is_paid_user(uid):
        sub = free_digest.get_sub(uid)
        status = free_digest.summarize_sub(sub, lang=_lang(deps, uid))
        await reply_plain(
            message,
            deps.tr(uid, "alerts_free_intro", status=status),
            reply_markup=_free_kb(deps, uid),
        )
        return
    await reply_plain(
        message, deps.tr(uid, "alerts_pick_kind"), reply_markup=_main_kb(deps, uid)
    )


async def handle_alert_kind_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, kind: str
) -> bool:
    uid = callback_query.from_user.id
    await callback_query.answer()
    if not deps.is_paid_user(uid):
        await start_alert_wizard(deps, callback_query.message)
        return True
    if kind == "menu":
        await start_alert_wizard(deps, callback_query.message)
        return True
    if kind == "list":
        await _reply_list(deps, callback_query.message, uid, edit=True)
        return True
    if kind in ("fx", "gold"):
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        deps.tr(uid, "alerts_mode_daily"),
                        callback_data=f"alertmode:{kind}:schedule",
                    )
                ],
                [
                    InlineKeyboardButton(
                        deps.tr(uid, "alerts_mode_spike"),
                        callback_data=f"alertmode:{kind}:spike",
                    )
                ],
            ]
        )
        await reply_plain(callback_query.message, deps.tr(uid, "alerts_ask_mode"), reply_markup=kb)
        return True
    if kind == "quake":
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        deps.tr(uid, "alerts_quake_pick_province"),
                        callback_data="alertqtype:province",
                    )
                ],
                [
                    InlineKeyboardButton(
                        deps.tr(uid, "alerts_quake_pick_city"),
                        callback_data="alertqtype:city",
                    )
                ],
                [
                    InlineKeyboardButton(
                        deps.tr(uid, "alerts_quake_pick_both"),
                        callback_data="alertqtype:both",
                    )
                ],
            ]
        )
        await reply_plain(
            callback_query.message, deps.tr(uid, "alerts_quake_ask_geo"), reply_markup=kb
        )
        return True
    if kind == "weather":
        deps.set_state_preserving_menu(
            uid, {"step": "await_alert_asset", "alert_kind": "weather", "alert_trigger": "schedule"}
        )
        await reply_plain(callback_query.message, deps.tr(uid, "alerts_ask_weather_city"))
        return True
    return True


async def handle_alert_mode_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, payload: str
) -> bool:
    uid = callback_query.from_user.id
    await callback_query.answer()
    parts = payload.split(":")
    if len(parts) != 2:
        return True
    kind, trigger = parts[0], parts[1]
    lang = _lang(deps, uid)
    deps.set_state_preserving_menu(
        uid,
        {
            "step": "await_alert_pick_assets",
            "alert_kind": kind,
            "alert_trigger": trigger,
            "alert_selected": [],
        },
    )
    await reply_plain(
        callback_query.message,
        deps.tr(uid, "alerts_ask_pick_assets"),
        reply_markup=_asset_picker_kb(deps, uid, kind=kind, selected=set(), lang=lang),
    )
    return True


async def handle_alert_sel_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, code: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    if state.get("step") != "await_alert_pick_assets":
        await callback_query.answer()
        return True
    selected = set(state.get("alert_selected") or [])
    kind = str(state.get("alert_kind") or "fx")
    lang = _lang(deps, uid)
    if code == "done":
        if not selected:
            await callback_query.answer(deps.tr(uid, "alerts_pick_at_least_one"), show_alert=True)
            return True
        await callback_query.answer()
        trigger = str(state.get("alert_trigger") or "schedule")
        deps.set_state_preserving_menu(
            uid,
            {
                "step": "await_alert_hour" if trigger == "schedule" else "await_alert_spike",
                "alert_kind": kind,
                "alert_trigger": trigger,
                "alert_selected": list(selected),
            },
        )
        if trigger == "schedule":
            await reply_plain(
                callback_query.message,
                deps.tr(uid, "alerts_ask_hour"),
                reply_markup=_hour_kb(),
            )
        else:
            await reply_plain(
                callback_query.message,
                deps.tr(uid, "alerts_ask_spike"),
                reply_markup=_spike_kb(),
            )
        return True
    if code in selected:
        selected.discard(code)
    else:
        selected.add(code)
    deps.set_state_preserving_menu(
        uid,
        {
            **state,
            "step": "await_alert_pick_assets",
            "alert_selected": list(selected),
        },
    )
    await callback_query.answer("✅" if code in selected else "➖")
    try:
        await callback_query.message.edit_reply_markup(
            _asset_picker_kb(deps, uid, kind=kind, selected=selected, lang=lang)
        )
    except Exception:
        pass
    return True


async def handle_alert_qtype_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, qtype: str
) -> bool:
    uid = callback_query.from_user.id
    await callback_query.answer()
    lang = _lang(deps, uid)
    if qtype == "both":
        # Start with provinces, then cities
        deps.set_state_preserving_menu(
            uid,
            {
                "step": "await_alert_pick_geo",
                "alert_kind": "quake",
                "alert_trigger": "event",
                "alert_geo_mode": "province",
                "alert_geo_next": "city",
                "alert_provinces": [],
                "alert_cities": [],
                "alert_geo_page": 0,
            },
        )
        mode = "province"
    else:
        deps.set_state_preserving_menu(
            uid,
            {
                "step": "await_alert_pick_geo",
                "alert_kind": "quake",
                "alert_trigger": "event",
                "alert_geo_mode": qtype,
                "alert_geo_next": "",
                "alert_provinces": [],
                "alert_cities": [],
                "alert_geo_page": 0,
            },
        )
        mode = qtype
    await reply_plain(
        callback_query.message,
        deps.tr(uid, "alerts_quake_pick_list"),
        reply_markup=_geo_picker_kb(
            deps, uid, mode=mode, selected=set(), lang=lang, page=0
        ),
    )
    return True


async def handle_alert_geo_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, payload: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    if state.get("step") != "await_alert_pick_geo":
        await callback_query.answer()
        return True
    lang = _lang(deps, uid)
    if payload == "done":
        mode = str(state.get("alert_geo_mode") or "province")
        provinces = list(state.get("alert_provinces") or [])
        cities = list(state.get("alert_cities") or [])
        selected = provinces if mode == "province" else cities
        nxt = str(state.get("alert_geo_next") or "")
        if nxt == "city":
            if not provinces and not cities:
                await callback_query.answer(
                    deps.tr(uid, "alerts_pick_at_least_one"), show_alert=True
                )
                return True
            await callback_query.answer()
            deps.set_state_preserving_menu(
                uid,
                {
                    **state,
                    "step": "await_alert_pick_geo",
                    "alert_geo_mode": "city",
                    "alert_geo_next": "",
                    "alert_geo_page": 0,
                },
            )
            await reply_plain(
                callback_query.message,
                deps.tr(uid, "alerts_quake_pick_cities_next"),
                reply_markup=_geo_picker_kb(
                    deps, uid, mode="city", selected=set(cities), lang=lang, page=0
                ),
            )
            return True
        if not provinces and not cities:
            await callback_query.answer(deps.tr(uid, "alerts_pick_at_least_one"), show_alert=True)
            return True
        await callback_query.answer()
        deps.set_state_preserving_menu(
            uid,
            {
                "step": "await_alert_quake_mag",
                "alert_kind": "quake",
                "alert_trigger": "event",
                "alert_provinces": provinces,
                "alert_cities": cities,
            },
        )
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("≥ ۳.۵", callback_data="alertqmag:3.5"),
                    InlineKeyboardButton("≥ ۴", callback_data="alertqmag:4"),
                    InlineKeyboardButton("≥ ۴.۵", callback_data="alertqmag:4.5"),
                ],
                [
                    InlineKeyboardButton("≥ ۵", callback_data="alertqmag:5"),
                    InlineKeyboardButton("≥ ۵.۵", callback_data="alertqmag:5.5"),
                ],
            ]
        )
        await reply_plain(
            callback_query.message, deps.tr(uid, "alerts_ask_quake_mag"), reply_markup=kb
        )
        return True

    parts = payload.split(":", 1)
    if len(parts) != 2:
        await callback_query.answer()
        return True
    mode, gid = parts
    provinces = set(state.get("alert_provinces") or [])
    cities = set(state.get("alert_cities") or [])
    bucket = provinces if mode == "province" else cities
    if gid in bucket:
        bucket.discard(gid)
    else:
        bucket.add(gid)
    if mode == "province":
        provinces = bucket
    else:
        cities = bucket
    page = int(state.get("alert_geo_page") or 0)
    deps.set_state_preserving_menu(
        uid,
        {
            **state,
            "step": "await_alert_pick_geo",
            "alert_provinces": list(provinces),
            "alert_cities": list(cities),
        },
    )
    await callback_query.answer("✅" if gid in bucket else "➖")
    try:
        await callback_query.message.edit_reply_markup(
            _geo_picker_kb(
                deps,
                uid,
                mode=mode,
                selected=bucket,
                lang=lang,
                page=page,
            )
        )
    except Exception:
        pass
    return True


async def handle_alert_geopage_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, payload: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    await callback_query.answer()
    parts = payload.split(":")
    if len(parts) != 2:
        return True
    mode, page_s = parts
    try:
        page = max(0, int(page_s))
    except ValueError:
        page = 0
    selected = set(
        (state.get("alert_provinces") if mode == "province" else state.get("alert_cities")) or []
    )
    deps.set_state_preserving_menu(uid, {**state, "alert_geo_page": page, "step": "await_alert_pick_geo"})
    try:
        await callback_query.message.edit_reply_markup(
            _geo_picker_kb(
                deps,
                uid,
                mode=mode,
                selected=selected,
                lang=_lang(deps, uid),
                page=page,
            )
        )
    except Exception:
        pass
    return True


async def _save_multi_market(
    deps: AlertCommandDeps,
    message: Message,
    uid: int,
    *,
    kind: str,
    trigger: str,
    codes: list[str],
    hour: int = 9,
    spike: Optional[float] = None,
) -> None:
    ok_n = 0
    fail = ""
    last_id = 0
    for code in codes:
        if store.count_user(uid) >= 20:
            fail = "limit"
            break
        ok, err, aid = store.add_alert(
            uid,
            kind=kind,
            asset=code,
            schedule="daily" if trigger == "schedule" else "none",
            spike_pct=spike if trigger == "spike" else None,
            hour_tehran=hour,
            trigger=trigger,
        )
        if ok:
            ok_n += 1
            last_id = aid
            # Seed last_price for spike alerts so next move can fire
            if trigger == "spike":
                try:
                    from v2.toolkit.fx_calculator import _rial_of
                    import asyncio

                    pok, rial = await asyncio.to_thread(_rial_of, 1.0, code)
                    if pok:
                        store.mark_sent(aid, price=float(rial))
                except Exception:
                    pass
        else:
            fail = err
    deps.clear_state(uid)
    if ok_n:
        await reply_plain(
            message,
            deps.tr(uid, "alerts_added_multi", n=ok_n),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            deps.tr(uid, "alerts_btn_list"), callback_data="alertkind:list"
                        )
                    ]
                ]
            ),
        )
    else:
        await reply_plain(message, deps.tr(uid, "alerts_add_fail", detail=fail or "error"))


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
    kind = str(state.get("alert_kind") or "fx")
    if kind == "weather":
        ok, err, aid = store.add_alert(
            uid,
            kind="weather",
            asset=str(state.get("alert_asset") or "Tehran"),
            schedule="daily",
            hour_tehran=hour,
            trigger="schedule",
        )
        deps.clear_state(uid)
        if not ok:
            await reply_plain(callback_query.message, deps.tr(uid, "alerts_add_fail", detail=err))
            return True
        await reply_plain(
            callback_query.message,
            deps.tr(uid, "alerts_added_ok"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            deps.tr(uid, "alerts_btn_test"), callback_data=f"alerttest:{aid}"
                        ),
                        InlineKeyboardButton(
                            deps.tr(uid, "alerts_btn_list"), callback_data="alertkind:list"
                        ),
                    ]
                ]
            ),
        )
        return True
    codes = list(state.get("alert_selected") or [])
    await _save_multi_market(
        deps,
        callback_query.message,
        uid,
        kind=kind,
        trigger="schedule",
        codes=codes,
        hour=hour,
    )
    return True


async def handle_alert_spike_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, spike_s: str
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    await callback_query.answer()
    if state.get("step") != "await_alert_spike":
        return True
    try:
        spike = float(spike_s)
    except ValueError:
        await reply_plain(callback_query.message, deps.tr(uid, "alerts_ask_spike"), reply_markup=_spike_kb())
        return True
    codes = list(state.get("alert_selected") or [])
    kind = str(state.get("alert_kind") or "fx")
    await _save_multi_market(
        deps,
        callback_query.message,
        uid,
        kind=kind,
        trigger="spike",
        codes=codes,
        spike=spike,
    )
    return True


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
        mag = 4.0
    asset = encode_quake_asset(
        provinces=list(state.get("alert_provinces") or []),
        cities=list(state.get("alert_cities") or []),
    )
    ok, err, aid = store.add_alert(
        uid,
        kind="quake",
        asset=asset,
        schedule="event",
        min_mag=mag,
        trigger="event",
    )
    deps.clear_state(uid)
    if not ok:
        await reply_plain(callback_query.message, deps.tr(uid, "alerts_add_fail", detail=err))
        return True
    await reply_plain(
        callback_query.message,
        deps.tr(uid, "alerts_quake_added_ok", mag=f"{mag:g}"),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        deps.tr(uid, "alerts_btn_test"), callback_data=f"alerttest:{aid}"
                    ),
                    InlineKeyboardButton(
                        deps.tr(uid, "alerts_btn_list"), callback_data="alertkind:list"
                    ),
                ]
            ]
        ),
    )
    return True


async def dispatch_alert_wizard(
    deps: AlertCommandDeps, message: Message, user_id: int, text: str
) -> bool:
    state = deps.get_state(user_id)
    step = state.get("step")
    if step == "await_free_weather_city":
        city = text.strip()
        if not city:
            await reply_plain(message, deps.tr(user_id, "alerts_ask_weather_city"))
            return True
        ok, err = free_digest.set_sub(user_id, kind="weather", asset=city)
        deps.clear_state(user_id)
        if not ok:
            await reply_plain(message, deps.tr(user_id, "alerts_add_fail", detail=err))
            return True
        await reply_plain(
            message,
            deps.tr(user_id, "alerts_free_weather_ok", city=city),
            reply_markup=_free_kb(deps, user_id),
        )
        return True
    if step == "await_alert_asset" and state.get("alert_kind") == "weather":
        city = text.strip()
        if not city:
            await reply_plain(message, deps.tr(user_id, "alerts_ask_weather_city"))
            return True
        deps.set_state_preserving_menu(
            user_id,
            {
                "step": "await_alert_hour",
                "alert_kind": "weather",
                "alert_asset": city,
                "alert_trigger": "schedule",
            },
        )
        await reply_plain(
            message, deps.tr(user_id, "alerts_ask_hour"), reply_markup=_hour_kb()
        )
        return True
    return False


async def handle_alert_free_callback(
    deps: AlertCommandDeps, client: Any, callback_query: Any, action: str
) -> bool:
    uid = callback_query.from_user.id
    await callback_query.answer()
    if action == "fx":
        ok, err = free_digest.set_sub(uid, kind="fx", asset="USD")
        if not ok:
            await reply_plain(callback_query.message, deps.tr(uid, "alerts_add_fail", detail=err))
            return True
        await reply_plain(
            callback_query.message,
            deps.tr(uid, "alerts_free_fx_ok"),
            reply_markup=_free_kb(deps, uid),
        )
        return True
    if action == "weather":
        deps.set_state_preserving_menu(uid, {"step": "await_free_weather_city"})
        await reply_plain(callback_query.message, deps.tr(uid, "alerts_ask_weather_city"))
        return True
    if action == "off":
        free_digest.disable_sub(uid)
        await reply_plain(
            callback_query.message,
            deps.tr(uid, "alerts_free_off_ok"),
            reply_markup=_free_kb(deps, uid),
        )
        return True
    await start_alert_wizard(deps, callback_query.message)
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
    if action == "m":
        await callback_query.answer()
        if not deps.is_paid_user(uid):
            await callback_query.answer(deps.tr(uid, "alerts_paid_only"), show_alert=True)
            return True
        await _reply_manage(deps, callback_query.message, uid, alert_id, edit=True)
        return True

    if not deps.is_paid_user(uid):
        await callback_query.answer(deps.tr(uid, "alerts_paid_only"), show_alert=True)
        return True

    if action == "del":
        ok = store.delete_alert(uid, alert_id)
        await callback_query.answer(deps.tr(uid, "alerts_deleted" if ok else "alerts_not_found"))
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
        await _reply_manage(deps, callback_query.message, uid, alert_id, edit=True)
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
        body = callback_query.message.text or ""
        if body.startswith(list_title):
            await _reply_list(deps, callback_query.message, uid, edit=True)
        else:
            await _reply_manage(deps, callback_query.message, uid, alert_id, edit=True)
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
