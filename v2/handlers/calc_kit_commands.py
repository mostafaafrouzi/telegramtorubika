"""Kitset-inspired calculators with multi-step wizards (no format-string dumps)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from v2.core.menu_sections import MenuSection
from v2.core.msg_format import reply_formatted, reply_html, reply_plain
from v2.toolkit import calc_kit_light as ck
from v2.toolkit.calendar_light import add_days, convert_date, date_diff
from v2.toolkit.iran_info_light import national_id_city, plate_lookup
from v2.toolkit.text_utils_light import payload_after_command

TranslateFn = Callable[..., str]
QuotaTryFn = Callable[[int], tuple[bool, str]]
QuotaCommitFn = Callable[[int], None]

# tool -> ordered field names for multi-step wizards
_STEPS: dict[str, tuple[str, ...]] = {
    "loan": ("principal", "rate", "months"),
    "deposit": ("principal", "rate", "months"),
    "fuel": ("distance", "consumption", "price"),
    "cig": ("per_day", "pack_price", "pack_size", "days"),
    "ielts": ("listening", "reading", "writing", "speaking"),
    "unit": ("kind", "amount", "frm", "to"),
    "datediff": ("date1", "date2"),
    "power": ("base", "exp"),
    "rect": ("width", "height"),
    "base": ("value", "from_base", "to_base"),
    "random": ("count", "lo", "hi"),
    "rial": ("amount", "dest"),
    "binary": ("mode", "payload"),
    "case": ("mode", "text"),
    "percent": ("mode", "a", "b"),
    "bmi": ("weight", "height_cm"),
    "compound": ("principal", "rate", "months"),
    "linear": ("a", "b"),
    "quadratic": ("a", "b", "c"),
    "add_days": ("date", "days"),
    "pct_error": ("actual", "measured"),
}

_SINGLE = frozenset(
    {
        "words",
        "sqrt",
        "fact",
        "prime",
        "square",
        "plate",
        "nid",
        "dateconv",
        "wordcount",
        "mean",
        "log",
        "digits",
    }
)


@dataclass(frozen=True)
class CalcKitDeps:
    tr: TranslateFn
    set_menu_section: Callable[[int, MenuSection], None]
    set_state_preserving_menu: Callable[[int, dict], None]
    clear_state: Callable[[int], None]
    get_state: Callable[[int], dict]
    toolkit_quota_try: QuotaTryFn
    toolkit_quota_commit: QuotaCommitFn
    toolkit_utility_light_enabled: bool = True


async def _quota(deps: CalcKitDeps, uid: int, message: Message) -> bool:
    ok, msg = deps.toolkit_quota_try(uid)
    if ok:
        return True
    await message.reply_text(msg or deps.tr(uid, "toolkit_quota_exceeded"), parse_mode=None)
    return False


def _ask_key(tool: str, field: str) -> str:
    return f"calc_ask_{tool}_{field}"


def _ask_text(deps: CalcKitDeps, uid: int, tool: str, field: str) -> str:
    key = _ask_key(tool, field)
    try:
        text = deps.tr(uid, key)
        if text and text != key:
            return text
    except Exception:
        pass
    # Fallbacks
    fa = {
        ("loan", "principal"): "مبلغ اصل وام را بفرست (عدد):",
        ("loan", "rate"): "نرخ سود سالانه را به درصد بفرست:",
        ("loan", "months"): "تعداد ماه‌های بازپرداخت را بفرست:",
        ("deposit", "principal"): "مبلغ سپرده را بفرست:",
        ("deposit", "rate"): "نرخ سود سالانه (٪) را بفرست:",
        ("deposit", "months"): "مدت به ماه را بفرست:",
        ("cig", "per_day"): "چند نخ در روز مصرف می‌کنی؟",
        ("cig", "pack_price"): "قیمت یک پاکت را بفرست:",
        ("cig", "pack_size"): "تعداد نخ در هر پاکت؟ (پیش‌فرض ۲۰ — عدد بفرست یا `-`)",
        ("cig", "days"): "برای چند روز حساب کنم؟ (پیش‌فرض ۳۶۵ — عدد یا `-`)",
        ("fuel", "distance"): "مسافت سفر به کیلومتر را بفرست:",
        ("fuel", "consumption"): "مصرف خودرو (لیتر در ۱۰۰ کیلومتر) را بفرست:",
        ("fuel", "price"): "قیمت هر لیتر سوخت را بفرست:",
        ("ielts", "listening"): "نمره Listening را بفرست (۰ تا ۹، گام ۰٫۵):",
        ("ielts", "reading"): "نمره Reading را بفرست:",
        ("ielts", "writing"): "نمره Writing را بفرست:",
        ("ielts", "speaking"): "نمره Speaking را بفرست:",
        ("unit", "kind"): "نوع تبدیل را بفرست: length / weight / volume / speed / data / temp / area",
        ("unit", "amount"): "مقدار را بفرست:",
        ("unit", "frm"): "واحد مبدأ را بفرست:",
        ("unit", "to"): "واحد مقصد را بفرست:",
        ("datediff", "date1"): "تاریخ اول را بفرست (YYYY/MM/DD):",
        ("datediff", "date2"): "تاریخ دوم را بفرست (YYYY/MM/DD):",
        ("power", "base"): "پایه توان را بفرست:",
        ("power", "exp"): "توان را بفرست:",
        ("rect", "width"): "عرض مستطیل را بفرست:",
        ("rect", "height"): "طول مستطیل را بفرست:",
        ("base", "value"): "عدد را بفرست:",
        ("base", "from_base"): "مبنا مبدأ (۲ تا ۳۶) را بفرست:",
        ("base", "to_base"): "مبنا مقصد (۲ تا ۳۶) را بفرست:",
        ("random", "count"): "چند عدد تصادفی می‌خواهی؟ (۱ تا ۵۰)",
        ("random", "lo"): "حداقل را بفرست:",
        ("random", "hi"): "حداکثر را بفرست:",
        ("rial", "amount"): "مبلغ را بفرست:",
        ("rial", "dest"): "به چه واحدی تبدیل شود؟ `toman` یا `rial` (یا دکمه زیر)",
        ("binary", "mode"): "حالت را بفرست: `to` (متن→باینری) یا `from` (باینری→متن)",
        ("binary", "payload"): "متن یا رشتهٔ باینری را بفرست:",
        ("case", "mode"): "حالت: upper / lower / title",
        ("case", "text"): "متن انگلیسی را بفرست:",
        ("percent", "mode"): "نوع محاسبه را بفرست: of / chg / inc / dec",
        ("percent", "a"): "عدد اول را بفرست:",
        ("percent", "b"): "عدد دوم را بفرست:",
        ("bmi", "weight"): "وزن به کیلوگرم را بفرست:",
        ("bmi", "height_cm"): "قد به سانتی‌متر را بفرست:",
        ("compound", "principal"): "مبلغ سپرده را بفرست:",
        ("compound", "rate"): "نرخ سالانه (٪) را بفرست:",
        ("compound", "months"): "مدت به ماه را بفرست:",
        ("linear", "a"): "ضریب a را بفرست (ax + b = 0):",
        ("linear", "b"): "ضریب b را بفرست:",
        ("quadratic", "a"): "ضریب a را بفرست (ax² + bx + c = 0):",
        ("quadratic", "b"): "ضریب b را بفرست:",
        ("quadratic", "c"): "ضریب c را بفرست:",
        ("add_days", "date"): "تاریخ شروع را بفرست (YYYY/MM/DD):",
        ("add_days", "days"): "چند روز اضافه/کم شود؟ (عدد منفی برای عقب):",
        ("pct_error", "actual"): "مقدار واقعی را بفرست:",
        ("pct_error", "measured"): "مقدار اندازه‌گیری‌شده را بفرست:",
    }
    return fa.get((tool, field), f"{tool}/{field}:")


async def _reply_result(deps: CalcKitDeps, message: Message, ok: bool, body: str) -> None:
    uid = message.from_user.id
    if ok:
        deps.toolkit_quota_commit(uid)
        await reply_formatted(message, body)
    else:
        await reply_plain(message, deps.tr(uid, "calc_error", detail=body))


def _eval_from_fields(tool: str, fields: dict[str, str]) -> tuple[bool, str]:
    t = tool.lower()
    if t == "loan":
        nums = [ck._parse_num(fields.get("principal", "")), ck._parse_num(fields.get("rate", "")), ck._parse_num(fields.get("months", ""))]
        if any(n is None for n in nums):
            return False, "عدد نامعتبر"
        return ck.loan_emi(nums[0], nums[1], int(nums[2]))  # type: ignore[arg-type]
    if t == "deposit":
        nums = [ck._parse_num(fields.get("principal", "")), ck._parse_num(fields.get("rate", "")), ck._parse_num(fields.get("months", ""))]
        if any(n is None for n in nums):
            return False, "عدد نامعتبر"
        return ck.deposit_interest(nums[0], nums[1], int(nums[2]))  # type: ignore[arg-type]
    if t == "compound":
        nums = [ck._parse_num(fields.get("principal", "")), ck._parse_num(fields.get("rate", "")), ck._parse_num(fields.get("months", ""))]
        if any(n is None for n in nums):
            return False, "عدد نامعتبر"
        return ck.compound_deposit(nums[0], nums[1], int(nums[2]))  # type: ignore[arg-type]
    if t == "fuel":
        nums = [ck._parse_num(fields.get("distance", "")), ck._parse_num(fields.get("consumption", "")), ck._parse_num(fields.get("price", ""))]
        if any(n is None for n in nums):
            return False, "عدد نامعتبر"
        return ck.fuel_cost(nums[0], nums[1], nums[2])  # type: ignore[arg-type]
    if t == "cig":
        per = ck._parse_num(fields.get("per_day", ""))
        price = ck._parse_num(fields.get("pack_price", ""))
        if per is None or price is None:
            return False, "عدد نامعتبر"
        ps_raw = (fields.get("pack_size") or "-").strip()
        days_raw = (fields.get("days") or "-").strip()
        pack = 20 if ps_raw in ("", "-", "–") else int(ck._parse_num(ps_raw) or 20)
        days = 365 if days_raw in ("", "-", "–") else int(ck._parse_num(days_raw) or 365)
        return ck.cigarette_cost(per, price, pack_size=pack, days=days)
    if t == "ielts":
        nums = [ck._parse_num(fields.get(k, "")) for k in ("listening", "reading", "writing", "speaking")]
        if any(n is None for n in nums):
            return False, "نمره نامعتبر"
        return ck.ielts_overall(nums[0], nums[1], nums[2], nums[3])  # type: ignore[arg-type]
    if t == "unit":
        amount = ck._parse_num(fields.get("amount", ""))
        if amount is None:
            return False, "مقدار نامعتبر"
        return ck.convert_unit(fields.get("kind", ""), amount, fields.get("frm", ""), fields.get("to", ""))
    if t == "datediff":
        return date_diff(fields.get("date1", ""), fields.get("date2", ""), lang="fa")
    if t == "power":
        a, b = ck._parse_num(fields.get("base", "")), ck._parse_num(fields.get("exp", ""))
        if a is None or b is None:
            return False, "عدد نامعتبر"
        return ck.math_power(a, b)
    if t == "rect":
        a, b = ck._parse_num(fields.get("width", "")), ck._parse_num(fields.get("height", ""))
        if a is None or b is None:
            return False, "عدد نامعتبر"
        return ck.rect_metrics(a, b)
    if t == "base":
        try:
            return ck.base_convert(fields.get("value", ""), int(fields.get("from_base", "")), int(fields.get("to_base", "")))
        except ValueError:
            return False, "مبنا نامعتبر"
    if t == "random":
        nums = [ck._parse_num(fields.get(k, "")) for k in ("count", "lo", "hi")]
        if any(n is None for n in nums):
            return False, "عدد نامعتبر"
        return ck.random_numbers(int(nums[0]), nums[1], nums[2])  # type: ignore[arg-type]
    if t == "rial":
        amount = ck._parse_num(fields.get("amount", ""))
        if amount is None:
            return False, "عدد نامعتبر"
        return ck.rial_toman(amount, to=fields.get("dest", "toman"))
    if t == "binary":
        return ck.binary_text(fields.get("mode", ""), fields.get("payload", ""))
    if t == "case":
        return ck.english_case(fields.get("text", ""), fields.get("mode", ""))
    if t == "percent":
        mode = (fields.get("mode") or "of").lower()
        a, b = ck._parse_num(fields.get("a", "")), ck._parse_num(fields.get("b", ""))
        if a is None or b is None:
            return False, "عدد نامعتبر"
        if mode in ("chg", "change"):
            return ck.percent_change(a, b)
        if mode == "inc":
            return ck.apply_percent(a, b, mode="inc")
        if mode == "dec":
            return ck.apply_percent(a, b, mode="dec")
        if mode == "of":
            return ck.apply_percent(a, b, mode="of")
        return ck.percent_of(a, b)
    if t == "bmi":
        w, h = ck._parse_num(fields.get("weight", "")), ck._parse_num(fields.get("height_cm", ""))
        if w is None or h is None:
            return False, "عدد نامعتبر"
        return ck.bmi(w, h)
    if t == "linear":
        a, b = ck._parse_num(fields.get("a", "")), ck._parse_num(fields.get("b", ""))
        if a is None or b is None:
            return False, "عدد نامعتبر"
        return ck.linear_eq(a, b)
    if t == "quadratic":
        a, b, c = (
            ck._parse_num(fields.get("a", "")),
            ck._parse_num(fields.get("b", "")),
            ck._parse_num(fields.get("c", "")),
        )
        if a is None or b is None or c is None:
            return False, "عدد نامعتبر"
        return ck.quadratic_eq(a, b, c)
    if t == "add_days":
        days = ck._parse_num(fields.get("days", ""))
        if days is None:
            return False, "تعداد روز نامعتبر"
        return add_days(fields.get("date", ""), int(days), lang="fa")
    if t == "pct_error":
        a, b = ck._parse_num(fields.get("actual", "")), ck._parse_num(fields.get("measured", ""))
        if a is None or b is None:
            return False, "عدد نامعتبر"
        return ck.percent_error(a, b)
    return False, "unknown_tool"


def _eval_calc(tool: str, payload: str) -> tuple[bool, str]:
    """Power-user one-shot path (slash with args)."""
    parts = ck.parse_calc_args(payload)
    t = (tool or "").lower()
    if t in _STEPS and parts:
        keys = _STEPS[t]
        fields = {keys[i]: parts[i] for i in range(min(len(keys), len(parts)))}
        # defaults for optional cig fields
        if t == "cig":
            fields.setdefault("pack_size", "20")
            fields.setdefault("days", "365")
        return _eval_from_fields(t, fields)
    if t == "words":
        n = ck._parse_num(parts[0]) if parts else None
        if n is None or not float(n).is_integer():
            return False, "یک عدد صحیح بفرست"
        return ck.number_to_persian_words(int(n))
    if t == "sqrt":
        n = ck._parse_num(parts[0]) if parts else None
        return (False, "عدد بفرست") if n is None else ck.math_sqrt(n)
    if t == "fact":
        n = ck._parse_num(parts[0]) if parts else None
        if n is None or not float(n).is_integer():
            return False, "عدد صحیح بفرست"
        return ck.math_factorial(int(n))
    if t == "prime":
        n = ck._parse_num(parts[0]) if parts else None
        if n is None or not float(n).is_integer():
            return False, "عدد صحیح بفرست"
        return ck.is_prime(int(n))
    if t == "square":
        n = ck._parse_num(parts[0]) if parts else None
        return (False, "ضلع را بفرست") if n is None else ck.square_metrics(n)
    if t == "plate":
        return plate_lookup(parts[0] if parts else payload)
    if t == "nid":
        return national_id_city(parts[0] if parts else payload)
    if t == "dateconv":
        return convert_date(parts[0] if parts else payload, lang="fa")
    if t == "wordcount":
        return ck.word_count(payload)
    if t == "mean":
        nums = []
        for p in parts:
            n = ck._parse_num(p)
            if n is None:
                return False, "اعداد نامعتبر"
            nums.append(n)
        return ck.math_mean(nums)
    if t == "log":
        n = ck._parse_num(parts[0]) if parts else None
        base = ck._parse_num(parts[1]) if len(parts) > 1 else 10.0
        if n is None or base is None:
            return False, "عدد بفرست"
        return ck.math_log(n, base)
    if t == "pct_error":
        if len(parts) < 2:
            return False, "مقدار واقعی و اندازه‌گیری‌شده"
        a, b = ck._parse_num(parts[0]), ck._parse_num(parts[1])
        if a is None or b is None:
            return False, "عدد نامعتبر"
        return ck.percent_error(a, b)
    if t == "linear":
        if len(parts) < 2:
            return False, "a و b را بفرست (ax + b = 0)"
        a, b = ck._parse_num(parts[0]), ck._parse_num(parts[1])
        if a is None or b is None:
            return False, "عدد نامعتبر"
        return ck.linear_eq(a, b)
    if t == "quadratic":
        if len(parts) < 3:
            return False, "a b c را بفرست"
        a, b, c = ck._parse_num(parts[0]), ck._parse_num(parts[1]), ck._parse_num(parts[2])
        if a is None or b is None or c is None:
            return False, "عدد نامعتبر"
        return ck.quadratic_eq(a, b, c)
    if t == "add_days":
        if len(parts) < 2:
            return False, "تاریخ و تعداد روز"
        days = ck._parse_num(parts[1])
        if days is None:
            return False, "تعداد روز نامعتبر"
        return add_days(parts[0], int(days), lang="fa")
    if t == "digits":
        return ck.convert_digits(payload)
    return False, "unknown_tool"


async def start_calc_tool(deps: CalcKitDeps, message: Message, tool: str) -> None:
    uid = message.from_user.id
    if not deps.toolkit_utility_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_utility_disabled"), parse_mode=None)
        return
    tool = (tool or "").lower()
    deps.set_menu_section(uid, MenuSection.TOOLKIT_CALC)
    if tool in _SINGLE:
        deps.set_state_preserving_menu(uid, {"step": f"await_calc_{tool}", "calc_tool": tool, "calc_fields": {}})
        hints = {
            "words": "یک عدد صحیح بفرست:",
            "sqrt": "یک عدد بفرست:",
            "fact": "یک عدد صحیح ۰ تا ۲۰۰ بفرست:",
            "prime": "یک عدد صحیح بفرست:",
            "square": "ضلع مربع را بفرست:",
            "plate": "کد دو رقمی پلاک را بفرست (مثلاً ۲۲):",
            "nid": "حداقل ۳ رقم اول کد ملی را بفرست:",
            "dateconv": "تاریخ را بفرست (YYYY/MM/DD شمسی یا میلادی):",
            "wordcount": "متن را بفرست:",
            "mean": "اعداد را با فاصله بفرست:",
            "log": "عدد و در صورت نیاز مبنا را بفرست (مثال: ۱۰۰ یا ۱۰۰ ۲):",
            "digits": "متن دارای عدد را بفرست (ارقام فارسی↔انگلیسی):",
        }
        await message.reply_text(hints.get(tool, "مقدار را بفرست:"), parse_mode=None)
        return
    steps = _STEPS.get(tool)
    if not steps:
        await message.reply_text("ابزار ناشناخته", parse_mode=None)
        return
    field0 = steps[0]
    state = {"step": f"await_calc_{tool}_{field0}", "calc_tool": tool, "calc_fields": {}, "calc_field": field0}
    kb = None
    if tool == "rial" and field0 == "amount":
        pass
    if tool == "percent" and field0 == "mode":
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("٪ از", callback_data="calcmode:percent:of"),
                    InlineKeyboardButton("تغییر", callback_data="calcmode:percent:chg"),
                ],
                [
                    InlineKeyboardButton("افزایش", callback_data="calcmode:percent:inc"),
                    InlineKeyboardButton("کاهش", callback_data="calcmode:percent:dec"),
                ],
            ]
        )
    if tool == "rial" and field0 == "dest":
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("→ تومان", callback_data="calcmode:rial:toman"),
                    InlineKeyboardButton("→ ریال", callback_data="calcmode:rial:rial"),
                ]
            ]
        )
    deps.set_state_preserving_menu(uid, state)
    await message.reply_text(_ask_text(deps, uid, tool, field0), reply_markup=kb, parse_mode=None)


async def run_calc_command(deps: CalcKitDeps, message: Message, tool: str) -> None:
    uid = message.from_user.id
    if not deps.toolkit_utility_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_utility_disabled"), parse_mode=None)
        return
    payload = payload_after_command(message.text or "").strip()
    if not payload:
        await start_calc_tool(deps, message, tool)
        return
    if not await _quota(deps, uid, message):
        return
    ok, body = await asyncio.to_thread(_eval_calc, tool, payload)
    await _reply_result(deps, message, ok, body)


async def dispatch_calc_wizard(
    deps: CalcKitDeps,
    message: Message,
    user_id: int,
    text: str,
) -> bool:
    state = deps.get_state(user_id)
    step = str(state.get("step") or "")
    if not step.startswith("await_calc_"):
        return False
    tool = str(state.get("calc_tool") or "")
    payload = (text or "").strip()
    if not payload:
        await start_calc_tool(deps, message, tool or "percent")
        return True

    # Single-field tools
    if tool in _SINGLE or (tool and f"await_calc_{tool}" == step and tool not in _STEPS):
        if not await _quota(deps, user_id, message):
            deps.clear_state(user_id)
            return True
        ok, body = await asyncio.to_thread(_eval_calc, tool, payload)
        if not ok:
            await message.reply_text(body, parse_mode=None)
            return True
        deps.clear_state(user_id)
        await _reply_result(deps, message, True, body)
        return True

    steps = _STEPS.get(tool) or ()
    field = str(state.get("calc_field") or "")
    fields = dict(state.get("calc_fields") or {})
    # optional skips
    if tool == "cig" and field in ("pack_size", "days") and payload in ("-", "–", "پیش‌فرض", "default"):
        fields[field] = "-"
    else:
        fields[field] = payload
    try:
        idx = list(steps).index(field)
    except ValueError:
        deps.clear_state(user_id)
        return True
    if idx + 1 < len(steps):
        nxt = steps[idx + 1]
        # rial: after amount ask dest with buttons
        kb = None
        if tool == "rial" and nxt == "dest":
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("→ تومان", callback_data="calcmode:rial:toman"),
                        InlineKeyboardButton("→ ریال", callback_data="calcmode:rial:rial"),
                    ]
                ]
            )
        deps.set_state_preserving_menu(
            user_id,
            {
                "step": f"await_calc_{tool}_{nxt}",
                "calc_tool": tool,
                "calc_fields": fields,
                "calc_field": nxt,
            },
        )
        await message.reply_text(_ask_text(deps, user_id, tool, nxt), reply_markup=kb, parse_mode=None)
        return True

    if not await _quota(deps, user_id, message):
        deps.clear_state(user_id)
        return True
    ok, body = await asyncio.to_thread(_eval_from_fields, tool, fields)
    if not ok:
        # keep state on error — re-ask last field
        await message.reply_text(body + "\n" + _ask_text(deps, user_id, tool, field), parse_mode=None)
        return True
    deps.clear_state(user_id)
    await _reply_result(deps, message, True, body)
    return True


async def handle_calc_mode_callback(
    deps: CalcKitDeps,
    client: Any,
    callback_query: Any,
    tool: str,
    mode: str,
) -> bool:
    uid = callback_query.from_user.id
    state = deps.get_state(uid)
    if str(state.get("calc_tool") or "") != tool:
        await callback_query.answer()
        await start_calc_tool(deps, callback_query.message, tool)
        return True
    fields = dict(state.get("calc_fields") or {})
    steps = _STEPS.get(tool) or ()
    if not steps:
        await callback_query.answer()
        return True
    fields[steps[0] if tool != "rial" else "dest"] = mode
    if tool == "percent":
        fields["mode"] = mode
        nxt = "a"
        deps.set_state_preserving_menu(
            uid,
            {"step": f"await_calc_percent_{nxt}", "calc_tool": "percent", "calc_fields": fields, "calc_field": nxt},
        )
        await callback_query.answer()
        await callback_query.message.reply_text(_ask_text(deps, uid, "percent", nxt), parse_mode=None)
        return True
    if tool == "rial":
        fields["dest"] = mode
        if "amount" not in fields:
            deps.set_state_preserving_menu(
                uid,
                {"step": "await_calc_rial_amount", "calc_tool": "rial", "calc_fields": fields, "calc_field": "amount"},
            )
            await callback_query.answer()
            await callback_query.message.reply_text(_ask_text(deps, uid, "rial", "amount"), parse_mode=None)
            return True
        if not await _quota(deps, uid, callback_query.message):
            deps.clear_state(uid)
            await callback_query.answer()
            return True
        ok, body = await asyncio.to_thread(_eval_from_fields, "rial", fields)
        deps.clear_state(uid)
        await callback_query.answer()
        await _reply_result(deps, callback_query.message, ok, body)
        return True
    await callback_query.answer()
    return True
