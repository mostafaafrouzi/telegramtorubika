"""Weather, air quality, sun times via Open-Meteo (no API key)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import requests

# Re-export for older imports
from v2.toolkit.fx_light import currency_convert  # noqa: F401

_WMO_FA = {
    0: "آسمان صاف",
    1: "عمدتاً صاف",
    2: "نیمه‌ابری",
    3: "ابری",
    45: "مه",
    48: "مه یخ‌زده",
    51: "باران‌ریزه سبک",
    53: "باران‌ریزه",
    55: "باران‌ریزه شدید",
    61: "باران سبک",
    63: "باران",
    65: "باران شدید",
    71: "برف سبک",
    73: "برف",
    75: "برف شدید",
    80: "رگبار سبک",
    81: "رگبار",
    82: "رگبار شدید",
    95: "رعدوبرق",
    96: "رعدوبرق با تگرگ",
    99: "رعدوبرق شدید با تگرگ",
}

_WMO_EN = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Slight showers",
    81: "Showers",
    82: "Violent showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}


def wmo_label(code: Optional[int], *, lang: str = "fa") -> str:
    if code is None:
        return "?"
    table = _WMO_EN if lang == "en" else _WMO_FA
    return table.get(int(code), f"code {code}")


def _aqi_band(aqi: Optional[float], *, lang: str = "fa") -> str:
    if aqi is None:
        return "?"
    try:
        n = float(aqi)
    except (TypeError, ValueError):
        return "?"
    if lang == "en":
        bands = (
            (50, "Good"),
            (100, "Moderate"),
            (150, "Unhealthy for sensitive"),
            (200, "Unhealthy"),
            (300, "Very unhealthy"),
            (9999, "Hazardous"),
        )
    else:
        bands = (
            (50, "خوب"),
            (100, "متوسط"),
            (150, "ناسالم برای حساس‌ها"),
            (200, "ناسالم"),
            (300, "بسیار ناسالم"),
            (9999, "خطرناک"),
        )
    for limit, label in bands:
        if n <= limit:
            return label
    return bands[-1][1]


def _geocode(city: str, *, lang: str = "fa") -> tuple[bool, float, float, str]:
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "fa" if lang != "en" else "en"},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return False, 0.0, 0.0, "city_not_found"
        row = results[0]
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        label = row.get("name") or city
        country = row.get("country") or ""
        if country:
            label = f"{label}, {country}"
        return True, lat, lon, label
    except Exception as e:
        return False, 0.0, 0.0, str(e)[:300]


def _fmt_sun(iso_s: str) -> str:
    if not iso_s:
        return "—"
    try:
        if "T" in iso_s:
            return iso_s.split("T", 1)[1][:5]
        return iso_s[:16]
    except Exception:
        return iso_s


def weather_report(city: str, *, lang: str = "fa", forecast_days: int = 3) -> tuple[bool, str]:
    ok, lat, lon, label = _geocode(city, lang=lang)
    if not ok:
        return False, label
    days = max(1, min(int(forecast_days), 5))
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,weather_code",
                "timezone": "auto",
                "forecast_days": days,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        cur = data.get("current") or {}
        daily = data.get("daily") or {}
        temp = cur.get("temperature_2m")
        hum = cur.get("relative_humidity_2m")
        wind = cur.get("wind_speed_10m")
        code = cur.get("weather_code")
        cond = wmo_label(code, lang=lang)
        tmax = (daily.get("temperature_2m_max") or [None])[0]
        tmin = (daily.get("temperature_2m_min") or [None])[0]
        sunrise = _fmt_sun((daily.get("sunrise") or [""])[0])
        sunset = _fmt_sun((daily.get("sunset") or [""])[0])
        uv = (daily.get("uv_index_max") or [None])[0]

        from v2.core import msg_format as mf

        if lang == "en":
            blocks = [
                mf.title("🌤", f"Weather — {label}"),
                mf.section("Now"),
                mf.kv("Temp", f"{temp}°C · {cond}"),
                mf.kv("Humidity / Wind", f"{hum}% · {wind} km/h"),
                mf.section("Today"),
                mf.kv("Range / UV", f"{tmin}–{tmax}°C · UV {uv}"),
                mf.kv("Sun", f"{sunrise} → {sunset}"),
            ]
        else:
            blocks = [
                mf.title("🌤", f"آب‌وهوا — {label}"),
                mf.section("الان"),
                mf.kv("دما", f"{temp}°C · {cond}"),
                mf.kv("رطوبت / باد", f"{hum}% · {wind} کیلومتر/ساعت"),
                mf.section("امروز"),
                mf.kv("بازه / UV", f"{tmin}–{tmax}°C · UV {uv}"),
                mf.kv("خورشید", f"{sunrise} → {sunset}"),
            ]

        dates = daily.get("time") or []
        dmax = daily.get("temperature_2m_max") or []
        dmin = daily.get("temperature_2m_min") or []
        dcodes = daily.get("weather_code") or []
        if len(dates) > 1:
            blocks.append(mf.section("📅 Forecast" if lang == "en" else "📅 پیش‌بینی"))
            for i in range(1, min(len(dates), days)):
                d = dates[i]
                try:
                    d_short = datetime.fromisoformat(d).strftime("%m-%d")
                except Exception:
                    d_short = d
                lo = dmin[i] if i < len(dmin) else "?"
                hi = dmax[i] if i < len(dmax) else "?"
                cond_d = wmo_label(dcodes[i] if i < len(dcodes) else None, lang=lang)
                blocks.append(mf.line(f"{d_short} · {lo}–{hi}°C · {cond_d}"))
        return True, mf.join(*blocks)
    except Exception as e:
        return False, str(e)[:400]


def air_quality_report(city: str, *, lang: str = "fa") -> tuple[bool, str]:
    ok, lat, lon, label = _geocode(city, lang=lang)
    if not ok:
        return False, label
    try:
        r = requests.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "pm10,pm2_5,us_aqi",
                "timezone": "auto",
            },
            timeout=15,
        )
        r.raise_for_status()
        cur = r.json().get("current") or {}
        aqi = cur.get("us_aqi")
        band = _aqi_band(aqi, lang=lang)
        pm25 = cur.get("pm2_5")
        pm10 = cur.get("pm10")
        if lang == "en":
            tip = "Tip: limit outdoor exercise if AQI is unhealthy."
            return True, (
                f"🫁 Air quality — {label}\n"
                f"\n"
                f"• US AQI: {aqi} ({band})\n"
                f"• PM2.5: {pm25} µg/m³\n"
                f"• PM10: {pm10} µg/m³\n"
                f"\n"
                f"{tip}"
            )
        tip = "نکته: در وضعیت ناسالم فعالیت سنگین بیرون را کم کن."
        return True, (
            f"🫁 کیفیت هوا — {label}\n"
            f"\n"
            f"• شاخص US AQI: {aqi} ({band})\n"
            f"• ذرات PM2.5: {pm25} میکروگرم/مترمکعب\n"
            f"• ذرات PM10: {pm10} میکروگرم/مترمکعب\n"
            f"\n"
            f"{tip}"
        )
    except Exception as e:
        return False, str(e)[:400]


def fetch_earthquake_events(
    *,
    min_mag: float = 4.0,
    limit: int = 40,
) -> tuple[bool, list[dict[str, Any]]]:
    """Return recent USGS events as dicts: id, mag, place, when, lat, lon, depth_km."""
    try:
        r = requests.get(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
            timeout=15,
        )
        r.raise_for_status()
        feats = r.json().get("features") or []
        out: list[dict[str, Any]] = []
        for f in feats:
            p = f.get("properties") or {}
            g = (f.get("geometry") or {}).get("coordinates") or []
            try:
                mag = float(p.get("mag") or 0)
            except (TypeError, ValueError):
                continue
            if mag < float(min_mag):
                continue
            eid = str(f.get("id") or p.get("code") or "")
            if not eid:
                continue
            ts = p.get("time")
            when = "—"
            if ts:
                try:
                    when = datetime.utcfromtimestamp(int(ts) / 1000).strftime(
                        "%Y-%m-%d %H:%M UTC"
                    )
                except Exception:
                    when = str(ts)
            lon = g[0] if len(g) >= 1 else None
            lat = g[1] if len(g) >= 2 else None
            depth = g[2] if len(g) >= 3 else None
            out.append(
                {
                    "id": eid,
                    "mag": mag,
                    "place": p.get("place") or "?",
                    "when": when,
                    "lat": lat,
                    "lon": lon,
                    "depth_km": depth,
                    "ts": int(ts) if ts else 0,
                }
            )
            if len(out) >= limit:
                break
        out.sort(key=lambda x: float(x.get("ts") or 0), reverse=True)
        return True, out
    except Exception as e:
        return False, [{"error": str(e)[:400]}]


def recent_earthquakes(limit: int = 8, *, min_mag: float = 4.5, lang: str = "fa") -> tuple[bool, str]:
    ok, events = fetch_earthquake_events(min_mag=min_mag, limit=limit)
    if not ok:
        err = events[0].get("error") if events else "error"
        return False, str(err)
    if not events:
        return True, (
            f"No M≥{min_mag} quakes in the last 24 hours."
            if lang == "en"
            else f"زلزلهٔ M≥{min_mag} در ۲۴ ساعت اخیر ثبت نشد."
        )
    header = (
        f"🌍 Earthquakes — last 24h (M≥{min_mag})"
        if lang == "en"
        else f"🌍 زلزله‌ها — ۲۴ ساعت اخیر (M≥{min_mag})"
    )
    lines = [header, ""]
    depth_lbl = "depth" if lang == "en" else "عمق"
    for ev in events:
        depth = ev.get("depth_km")
        depth_s = f"{depth:.0f} km" if isinstance(depth, (int, float)) else "—"
        lines.append(f"• M{ev['mag']:.1f} — {ev['place']}")
        lines.append(f"  {ev['when']} · {depth_lbl} {depth_s}")
        lines.append("")
    return True, "\n".join(lines).rstrip()
