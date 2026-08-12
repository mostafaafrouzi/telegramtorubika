"""Independent free-market boards (gold / USD / majors) with day + snapshot deltas."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from v2.core import msg_format as mf

_SNAP_DB = Path(__file__).resolve().parents[2] / "queue" / "market_snapshots.sqlite3"

PROVIDER_LABEL_FA = "بازار آزاد ایران"
PROVIDER_LABEL_EN = "Iran free market"


@dataclass(frozen=True)
class Quote:
    code: str
    price: float
    unit: str  # IRR | USD
    d: Optional[float] = None
    dp: Optional[float] = None
    dt: str = ""
    ts: str = ""
    high: Optional[float] = None
    low: Optional[float] = None


_LABELS_FA = {
    "USD": "دلار آمریکا",
    "EUR": "یورو",
    "GBP": "پوند",
    "JPY": "ین ژاپن",
    "AED": "درهم امارات",
    "TRY": "لیر ترکیه",
    "CNY": "یوآن چین",
    "CAD": "دلار کانادا",
    "CHF": "فرانک سوئیس",
    "AUD": "دلار استرالیا",
    "SAR": "ریال سعودی",
    "SEK": "کرون سوئد",
    "NOK": "کرون نروژ",
    "NZD": "دلار نیوزیلند",
    "KRW": "وون کره",
    "INR": "روپیه هند",
    "IQD": "دینار عراق",
    "RUB": "روبل روسیه",
    "USDT": "تتر",
    "XAU_OZ": "انس طلا",
    "XAG_OZ": "انس نقره",
    "MESGHAL": "مثقال طلا",
    "GOLD18": "طلای ۱۸ عیار (گرم)",
    "SEKEE": "سکه امامی",
    "SEKEB": "سکه بهار آزادی",
    "NIM": "نیم سکه",
    "ROB": "ربع سکه",
    "GERAMI": "سکه گرمی",
}
_LABELS_EN = {
    "USD": "US Dollar",
    "EUR": "Euro",
    "GBP": "Pound",
    "JPY": "Yen",
    "AED": "UAE Dirham",
    "TRY": "Turkish Lira",
    "CNY": "Yuan",
    "CAD": "Canadian Dollar",
    "CHF": "Swiss Franc",
    "AUD": "Australian Dollar",
    "SAR": "Saudi Riyal",
    "SEK": "Swedish Krona",
    "NOK": "Norwegian Krone",
    "NZD": "NZ Dollar",
    "KRW": "Korean Won",
    "INR": "Indian Rupee",
    "IQD": "Iraqi Dinar",
    "RUB": "Ruble",
    "USDT": "Tether",
    "XAU_OZ": "Gold ounce",
    "XAG_OZ": "Silver ounce",
    "MESGHAL": "Gold mesghal",
    "GOLD18": "18k gold /g",
    "SEKEE": "Emami coin",
    "SEKEB": "Bahar Azadi",
    "NIM": "Half coin",
    "ROB": "Quarter coin",
    "GERAMI": "Gram coin",
}

BOARDS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "gold": ("🥇 طلا و سکه", "🥇 Gold & coins", ("XAU_OZ", "XAG_OZ", "MESGHAL", "GOLD18", "SEKEE", "SEKEB", "NIM", "ROB", "GERAMI")),
    "usd": ("💵 دلار آمریکا", "💵 US Dollar", ("USD", "USDT")),
    "eur": ("💶 یورو", "💶 Euro", ("EUR",)),
    "gbp": ("💷 پوند", "💷 Pound", ("GBP",)),
    "jpy": ("💴 ین ژاپن", "💴 Yen", ("JPY",)),
    "majors": (
        "🌍 ارزهای مهم",
        "🌍 Major FX",
        ("AED", "TRY", "CNY", "CAD", "CHF", "AUD", "SAR", "SEK", "NOK", "NZD", "KRW", "INR", "IQD", "RUB"),
    ),
}


def parse_quote_node(code: str, node: Any, *, unit: str) -> Optional[Quote]:
    if not isinstance(node, dict):
        return None
    from v2.toolkit.fx_light import _parse_price

    p = _parse_price(node.get("p") or node.get("price"))
    if not p or p <= 0:
        return None
    return Quote(
        code=code,
        price=float(p),
        unit=unit,
        d=_parse_price(node.get("d")),
        dp=_parse_price(node.get("dp")),
        dt=str(node.get("dt") or ""),
        ts=str(node.get("ts") or node.get("t_en") or node.get("t") or ""),
        high=_parse_price(node.get("h")),
        low=_parse_price(node.get("l")),
    )


def _ensure_snap_db() -> sqlite3.Connection:
    _SNAP_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_SNAP_DB), timeout=15)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshots (
            code TEXT NOT NULL,
            day TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT 'IRR',
            PRIMARY KEY (code, day)
        )
        """
    )
    conn.commit()
    return conn


def record_snapshots(quotes: dict[str, Quote]) -> None:
    if not quotes:
        return
    day = time.strftime("%Y-%m-%d", time.gmtime())
    try:
        conn = _ensure_snap_db()
        with conn:
            for q in quotes.values():
                conn.execute(
                    "INSERT OR REPLACE INTO market_snapshots(code, day, price, unit) VALUES (?,?,?,?)",
                    (q.code, day, q.price, q.unit),
                )
        conn.close()
    except Exception:
        pass


def _price_on(code: str, days_ago: int) -> Optional[float]:
    target = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days_ago * 86400))
    try:
        conn = _ensure_snap_db()
        row = conn.execute(
            "SELECT price FROM market_snapshots WHERE code=? AND day<=? ORDER BY day DESC LIMIT 1",
            (code, target),
        ).fetchone()
        conn.close()
        return float(row[0]) if row else None
    except Exception:
        return None


def _hist_line(q: Quote, *, lang: str) -> str:
    parts: list[str] = []
    for days, label_fa, label_en in (
        (7, "هفته", "week"),
        (30, "ماه", "month"),
        (365, "سال", "year"),
    ):
        old = _price_on(q.code, days)
        if not old or old <= 0:
            continue
        pct = ((q.price - old) / old) * 100.0
        arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "─")
        lab = label_en if lang == "en" else label_fa
        parts.append(f"{lab} {arrow} {pct:+.2f}%")
    if not parts:
        return ""
    label = "Longer" if lang == "en" else "بلندمدت"
    return mf.kv(label, " · ".join(parts))


_PAGE_SIZE = 6


def board_page_count(board: str) -> int:
    meta = BOARDS.get((board or "").lower())
    if not meta:
        return 1
    n = len(meta[2])
    return max(1, (n + _PAGE_SIZE - 1) // _PAGE_SIZE)


def format_board(
    board: str,
    quotes: dict[str, Quote],
    *,
    lang: str = "fa",
    fetched_at: float = 0.0,
    page: int = 0,
) -> str:
    meta = BOARDS.get((board or "").lower())
    if not meta:
        return ""
    title_fa, title_en, codes = meta
    title = title_en if lang == "en" else title_fa
    labels = _LABELS_EN if lang == "en" else _LABELS_FA
    provider = PROVIDER_LABEL_EN if lang == "en" else PROVIDER_LABEL_FA
    pages = board_page_count(board)
    page = max(0, min(int(page or 0), pages - 1))
    # Paginate only crowded boards (majors); others stay single-page
    if (board or "").lower() == "majors" and pages > 1:
        start = page * _PAGE_SIZE
        codes = codes[start : start + _PAGE_SIZE]
        title = f"{title} ({page + 1}/{pages})"
    blocks = [
        mf.title("", title),
        mf.italic(provider),
    ]
    from v2.toolkit.fx_light import _fmt_ts

    if fetched_at:
        blocks.append(mf.updated_line(_fmt_ts(fetched_at, lang), lang=lang))
    for code in codes:
        q = quotes.get(code)
        if not q:
            continue
        name = labels.get(code, code)
        blocks.append(mf.section(name))
        if q.unit == "USD":
            blocks.append(
                mf.kv(
                    "Price" if lang == "en" else "قیمت",
                    f"{q.price:,.2f} USD",
                    icon="💵",
                )
            )
        else:
            toman = q.price / 10.0
            if lang == "en":
                price_txt = f"{q.price:,.0f} rial ≈ {toman:,.0f} toman"
            else:
                price_txt = f"{q.price:,.0f} ریال ≈ {toman:,.0f} تومان"
            blocks.append(mf.kv("Price" if lang == "en" else "قیمت", price_txt, icon="💰"))
        ch = mf.change_line(q.d, q.dp, q.dt, lang=lang)
        if ch:
            blocks.append(ch)
        hist = _hist_line(q, lang=lang)
        if hist:
            blocks.append(hist)
        if q.ts:
            blocks.append(
                mf.kv(
                    "Asset time" if lang == "en" else "زمان نرخ",
                    q.ts,
                    icon="🕒",
                )
            )
    tip = (
        "Use FX calculator from Markets & weather menu"
        if lang == "en"
        else "برای تبدیل از منوی بازار و آب‌وهوا → ماشین‌حساب ارز استفاده کن"
    )
    blocks.append("")
    blocks.append(mf.italic(tip))
    return mf.join(*blocks)


def hub_text(*, lang: str = "fa") -> str:
    if lang == "en":
        return mf.join(
            mf.title("🏛", "Market boards"),
            mf.italic(PROVIDER_LABEL_EN),
            mf.line("Pick a board: Gold, USD, EUR, GBP, JPY, or Majors"),
        )
    return mf.join(
        mf.title("🏛", "تابلوهای بازار"),
        mf.italic(PROVIDER_LABEL_FA),
        mf.line("یک تابلو را انتخاب کن: طلا، دلار، یورو، پوند، ین یا ارزهای مهم"),
    )


def asset_label(code: str, *, lang: str = "fa") -> str:
    labels = _LABELS_EN if lang == "en" else _LABELS_FA
    return labels.get(code, code)


def fx_alert_codes() -> tuple[str, ...]:
    return (
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "USDT",
        "AED",
        "TRY",
        "CNY",
        "CAD",
        "CHF",
        "AUD",
        "SAR",
        "SEK",
        "NOK",
        "NZD",
        "KRW",
        "INR",
        "IQD",
        "RUB",
    )


def gold_alert_codes() -> tuple[str, ...]:
    return BOARDS["gold"][2]
