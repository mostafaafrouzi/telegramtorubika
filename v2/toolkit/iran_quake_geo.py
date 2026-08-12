"""Iran provinces/cities for earthquake place-string matching (USGS)."""

from __future__ import annotations

from typing import Any

# id -> (FA label, English/search aliases used in USGS place text)
PROVINCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "tehran": ("تهران", ("Tehran", "تهران")),
    "alborz": ("البرز", ("Alborz", "Karaj", "البرز", "کرج")),
    "isfahan": ("اصفهان", ("Isfahan", "Esfahan", "اصفهان")),
    "fars": ("فارس", ("Fars", "Shiraz", "فارس", "شیراز")),
    "razavi": ("خراسان رضوی", ("Razavi Khorasan", "Mashhad", "خراسان رضوی", "مشهد")),
    "south_khorasan": ("خراسان جنوبی", ("South Khorasan", "Birjand", "خراسان جنوبی")),
    "north_khorasan": ("خراسان شمالی", ("North Khorasan", "Bojnurd", "خراسان شمالی")),
    "khuzestan": ("خوزستان", ("Khuzestan", "Ahvaz", "خوزستان", "اهواز")),
    "east_az": ("آذربایجان شرقی", ("East Azerbaijan", "Tabriz", "آذربایجان شرقی", "تبریز")),
    "west_az": ("آذربایجان غربی", ("West Azerbaijan", "Urmia", "آذربایجان غربی", "ارومیه")),
    "ardabil": ("اردبیل", ("Ardabil", "اردبیل")),
    "gilan": ("گیلان", ("Gilan", "Rasht", "گیلان", "رشت")),
    "mazandaran": ("مازندران", ("Mazandaran", "Sari", "مازندران", "ساری")),
    "golestan": ("گلستان", ("Golestan", "Gorgan", "گلستان", "گرگان")),
    "kerman": ("کرمان", ("Kerman", "کرمان")),
    "hormozgan": ("هرمزگان", ("Hormozgan", "Bandar Abbas", "هرمزگان", "بندرعباس")),
    "sistan": ("سیستان و بلوچستان", ("Sistan", "Baluchestan", "Zahedan", "سیستان", "زاهدان")),
    "bushehr": ("بوشهر", ("Bushehr", "بوشهر")),
    "kermanshah": ("کرمانشاه", ("Kermanshah", "کرمانشاه")),
    "kurdistan": ("کردستان", ("Kurdistan", "Sanandaj", "کردستان", "سنندج")),
    "lorestan": ("لرستان", ("Lorestan", "Khorramabad", "لرستان")),
    "hamadan": ("همدان", ("Hamadan", "Hamedan", "همدان")),
    "markazi": ("مرکزی", ("Markazi", "Arak", "مرکزی", "اراک")),
    "qazvin": ("قزوین", ("Qazvin", "قزوین")),
    "qom": ("قم", ("Qom", "قم")),
    "semnan": ("سمنان", ("Semnan", "سمنان")),
    "yazd": ("یزد", ("Yazd", "یزد")),
    "zanjan": ("زنجان", ("Zanjan", "زنجان")),
    "ilam": ("ایلام", ("Ilam", "ایلام")),
    "chaharmahal": ("چهارمحال و بختیاری", ("Chaharmahal", "Bakhtiari", "Shahrekord", "چهارمحال")),
    "kohgiluyeh": ("کهگیلویه و بویراحمد", ("Kohgiluyeh", "Boyer-Ahmad", "Yasuj", "کهگیلویه")),
}

CITIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "tehran_city": ("تهران", ("Tehran", "تهران")),
    "karaj": ("کرج", ("Karaj", "کرج")),
    "mashhad": ("مشهد", ("Mashhad", "مشهد")),
    "isfahan_city": ("اصفهان", ("Isfahan", "Esfahan", "اصفهان")),
    "shiraz": ("شیراز", ("Shiraz", "شیراز")),
    "tabriz": ("تبریز", ("Tabriz", "تبریز")),
    "ahvaz": ("اهواز", ("Ahvaz", "Ahwaz", "اهواز")),
    "qom_city": ("قم", ("Qom", "قم")),
    "kermanshah_city": ("کرمانشاه", ("Kermanshah", "کرمانشاه")),
    "urmia": ("ارومیه", ("Urmia", "Orumiyeh", "ارومیه")),
    "rasht": ("رشت", ("Rasht", "رشت")),
    "zahedan": ("زاهدان", ("Zahedan", "زاهدان")),
    "kerman_city": ("کرمان", ("Kerman", "کرمان")),
    "hamadan_city": ("همدان", ("Hamadan", "Hamedan", "همدان")),
    "yazd_city": ("یزد", ("Yazd", "یزد")),
    "ardabil_city": ("اردبیل", ("Ardabil", "اردبیل")),
    "bandar_abbas": ("بندرعباس", ("Bandar Abbas", "بندرعباس")),
    "bushehr_city": ("بوشهر", ("Bushehr", "بوشهر")),
    "sari": ("ساری", ("Sari", "ساری")),
    "gorgan": ("گرگان", ("Gorgan", "گرگان")),
    "sanandaj": ("سنندج", ("Sanandaj", "سنندج")),
    "khorramabad": ("خرم‌آباد", ("Khorramabad", "خرم")),
    "arak": ("اراک", ("Arak", "اراک")),
    "qazvin_city": ("قزوین", ("Qazvin", "قزوین")),
    "zanjan_city": ("زنجان", ("Zanjan", "زنجان")),
    "semnan_city": ("سمنان", ("Semnan", "سمنان")),
    "birjand": ("بیرجند", ("Birjand", "بیرجند")),
    "bojnurd": ("بجنورد", ("Bojnurd", "بجنورد")),
    "ilam_city": ("ایلام", ("Ilam", "ایلام")),
    "yasuj": ("یاسوج", ("Yasuj", "یاسوج")),
    "shahr_kord": ("شهرکرد", ("Shahrekord", "Shahr-e Kord", "شهرکرد")),
}


def province_ids() -> list[str]:
    return list(PROVINCES.keys())


def city_ids() -> list[str]:
    return list(CITIES.keys())


def label(kind: str, gid: str, *, lang: str = "fa") -> str:
    table = PROVINCES if kind == "province" else CITIES
    row = table.get(gid)
    if not row:
        return gid
    fa, aliases = row
    if lang == "en":
        return aliases[0] if aliases else gid
    return fa


def match_place(place: str, *, provinces: list[str], cities: list[str]) -> bool:
    """True if USGS place string matches any selected province/city aliases."""
    text = (place or "").strip()
    if not text:
        return False
    low = text.lower()
    for pid in provinces or []:
        row = PROVINCES.get(pid)
        if not row:
            continue
        for a in row[1]:
            if a.lower() in low or a in text:
                return True
    for cid in cities or []:
        row = CITIES.get(cid)
        if not row:
            continue
        for a in row[1]:
            if a.lower() in low or a in text:
                return True
    return False


def parse_quake_asset(asset: str) -> dict[str, list[str]]:
    import json

    raw = (asset or "").strip()
    if not raw:
        return {"provinces": [], "cities": []}
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            return {
                "provinces": [str(x) for x in (data.get("provinces") or [])],
                "cities": [str(x) for x in (data.get("cities") or [])],
            }
        except json.JSONDecodeError:
            pass
    # Legacy plain city name → treat as free-text city filter via cities list sentinel
    return {"provinces": [], "cities": [], "legacy": [raw]}  # type: ignore[dict-item]


def encode_quake_asset(*, provinces: list[str], cities: list[str]) -> str:
    import json

    return json.dumps(
        {"provinces": list(provinces), "cities": list(cities)},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def summarize_quake_asset(asset: str, *, lang: str = "fa") -> str:
    data = parse_quake_asset(asset)
    parts: list[str] = []
    for pid in data.get("provinces") or []:
        parts.append(label("province", pid, lang=lang))
    for cid in data.get("cities") or []:
        parts.append(label("city", cid, lang=lang))
    legacy = data.get("legacy") or []
    parts.extend(str(x) for x in legacy)
    if not parts:
        return "—" if lang == "en" else "—"
    return "، ".join(parts) if lang != "en" else ", ".join(parts)


def place_matches_asset(place: str, asset: str) -> bool:
    data = parse_quake_asset(asset)
    legacy = data.get("legacy") or []
    if legacy:
        low = (place or "").lower()
        return any(str(t).lower() in low or str(t) in (place or "") for t in legacy)
    prov = data.get("provinces") or []
    cities = data.get("cities") or []
    if not prov and not cities:
        return True  # no filter = all (legacy empty)
    return match_place(place, provinces=prov, cities=cities)
