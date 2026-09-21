"""Расчёт реального астрологического фона для ежедневных/периодических гороскопов.
Только расчёты: интерпретация выполняется через Groq.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from math import cos, radians
from zoneinfo import ZoneInfo
from typing import Any

import swisseph as swe

ZODIAC = [
    ("Овен", "♈", "огонь"),
    ("Телец", "♉", "земля"),
    ("Близнецы", "♊", "воздух"),
    ("Рак", "♋", "вода"),
    ("Лев", "♌", "огонь"),
    ("Дева", "♍", "земля"),
    ("Весы", "♎", "воздух"),
    ("Скорпион", "♏", "вода"),
    ("Стрелец", "♐", "огонь"),
    ("Козерог", "♑", "земля"),
    ("Водолей", "♒", "воздух"),
    ("Рыбы", "♓", "вода"),
]

PLANETS = [
    ("Солнце", swe.SUN),
    ("Луна", swe.MOON),
    ("Меркурий", swe.MERCURY),
    ("Венера", swe.VENUS),
    ("Марс", swe.MARS),
    ("Юпитер", swe.JUPITER),
    ("Сатурн", swe.SATURN),
    ("Уран", swe.URANUS),
    ("Нептун", swe.NEPTUNE),
    ("Плутон", swe.PLUTO),
]

MAJOR_ASPECTS = [
    ("соединение", 0, 6.0),
    ("секстиль", 60, 4.0),
    ("квадрат", 90, 5.0),
    ("тригон", 120, 5.0),
    ("оппозиция", 180, 6.0),
]


def _zodiac(longitude: float) -> dict[str, Any]:
    longitude %= 360.0
    index = int(longitude // 30)
    degree = longitude - index * 30
    name, emoji, element = ZODIAC[index]
    return {
        "sign": name,
        "emoji": emoji,
        "element": element,
        "degree": round(degree, 4),
        "formatted": f"{int(degree)}°{int(round((degree % 1) * 60)):02d}′ {name}",
    }


def _jd_for_local(dt: datetime) -> float:
    utc = dt.astimezone(ZoneInfo("UTC"))
    hour = utc.hour + utc.minute / 60 + utc.second / 3600
    return swe.julday(utc.year, utc.month, utc.day, hour)


def _calc(jd: float, body: int):
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    try:
        result = swe.calc_ut(jd, body, flags)
        if isinstance(result, tuple) and len(result) >= 2 and result[0]:
            return result[0]
    except Exception:
        pass
    result = swe.calc_ut(jd, body, swe.FLG_MOSEPH | swe.FLG_SPEED)
    return result[0]


def _positions(local_dt: datetime) -> dict[str, dict[str, Any]]:
    jd = _jd_for_local(local_dt)
    result = {}
    for name, body in PLANETS:
        values = _calc(jd, body)
        lon = float(values[0]) % 360.0
        pos = _zodiac(lon)
        result[name] = {
            **pos,
            "longitude": round(lon, 6),
            "retrograde": float(values[3]) < 0,
            "speed_longitude": round(float(values[3]), 6),
        }
    return result


def _angular_distance(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)


def _signed_separation(moon_lon: float, sun_lon: float) -> float:
    return (moon_lon - sun_lon) % 360.0


def _phase(moon_lon: float, sun_lon: float, moon_speed: float, sun_speed: float) -> dict[str, Any]:
    separation = _signed_separation(moon_lon, sun_lon)
    illumination = (1 - cos(radians(separation))) / 2
    relative_speed = moon_speed - sun_speed
    if separation < 22.5 or separation >= 337.5:
        name = "новолуние"
    elif separation < 67.5:
        name = "растущий серп"
    elif separation < 112.5:
        name = "первая четверть"
    elif separation < 157.5:
        name = "растущая Луна"
    elif separation < 202.5:
        name = "полнолуние"
    elif separation < 247.5:
        name = "убывающая Луна"
    elif separation < 292.5:
        name = "последняя четверть"
    elif separation < 337.5:
        name = "убывающий серп"
    else:
        name = "новолуние"
    return {
        "name": name,
        "illumination_percent": round(illumination * 100, 1),
        "separation": round(separation, 2),
        "waxing": relative_speed > 0,
    }


def _find_ingress(start: datetime, planet: str, body: int, start_sign: str) -> dict[str, Any] | None:
    # Ищем переход по часам и уточняем его бинарным поиском.
    previous = start
    previous_lon = _positions(previous)[planet]["longitude"]
    for h in range(1, 25):
        current = start + timedelta(hours=h)
        current_lon = _positions(current)[planet]["longitude"]
        if _zodiac(current_lon)["sign"] != start_sign:
            lo, hi = previous, current
            for _ in range(12):
                mid = lo + (hi - lo) / 2
                if _zodiac(_positions(mid)[planet]["longitude"])["sign"] == start_sign:
                    lo = mid
                else:
                    hi = mid
            return {
                "planet": planet,
                "from_sign": start_sign,
                "to_sign": _zodiac(_positions(hi)[planet]["longitude"])["sign"],
                "local_time": hi.strftime("%H:%M"),
            }
        previous = current
        previous_lon = current_lon
    return None


def calculate_daily_sky(date_str: str, timezone_name: str = "Europe/Moscow") -> dict[str, Any]:
    local_date = datetime.strptime(date_str, "%d.%m.%Y").date()
    start = datetime.combine(local_date, datetime.min.time(), tzinfo=ZoneInfo(timezone_name))
    noon = start + timedelta(hours=12)
    end = start + timedelta(hours=23, minutes=59)

    positions = _positions(noon)
    phase = _phase(
        positions["Луна"]["longitude"],
        positions["Солнце"]["longitude"],
        positions["Луна"]["speed_longitude"],
        positions["Солнце"]["speed_longitude"],
    )

    aspects = []
    names = list(positions.keys())
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            diff = _angular_distance(positions[first]["longitude"], positions[second]["longitude"])
            for aspect, exact, orb in MAJOR_ASPECTS:
                actual_orb = abs(diff - exact)
                if actual_orb <= orb:
                    aspects.append({
                        "first": first,
                        "second": second,
                        "aspect": aspect,
                        "orb": round(actual_orb, 2),
                    })
                    break
    aspects.sort(key=lambda x: x["orb"])

    ingresses = []
    for planet, body in PLANETS:
        start_sign = positions[planet]["sign"]
        ingress = _find_ingress(start, planet, body, start_sign)
        if ingress:
            ingresses.append(ingress)

    return {
        "date": date_str,
        "timezone": timezone_name,
        "positions": positions,
        "phase": phase,
        "aspects": aspects[:8],
        "ingresses": ingresses,
        "calculation_time": noon.isoformat(),
        "ephemeris": "Swiss Ephemeris / Moshier fallback",
    }


def calculate_personal_day(birth_date_str: str, target_date_str: str) -> dict[str, int]:
    birth = datetime.strptime(birth_date_str, "%d.%m.%Y")
    target = datetime.strptime(target_date_str, "%d.%m.%Y")

    def reduce(value: int) -> int:
        while value > 9 and value not in (11, 22, 33):
            value = sum(int(d) for d in str(value))
        return value

    personal_year = reduce(birth.day + birth.month + sum(int(d) for d in str(target.year)))
    personal_month = reduce(personal_year + target.month)
    personal_day = reduce(personal_month + target.day)
    return {
        "personal_year": personal_year,
        "personal_month": personal_month,
        "personal_day": personal_day,
    }


def build_period_sky_summary(
    start_date: str,
    end_date: str,
    timezone_name: str = "Europe/Moscow",
    max_events: int = 14,
) -> list[dict[str, Any]]:
    start = datetime.strptime(start_date, "%d.%m.%Y").date()
    end = datetime.strptime(end_date, "%d.%m.%Y").date()
    events = []
    seen_aspects = set()

    current = start
    while current <= end:
        day = calculate_daily_sky(current.strftime("%d.%m.%Y"), timezone_name)
        for ingress in day["ingresses"]:
            events.append({
                "date": day["date"],
                "type": "переход",
                "text": f'{ingress["planet"]}: {ingress["from_sign"]} → {ingress["to_sign"]} в {ingress["local_time"]}',
            })
        for aspect in day["aspects"]:
            key = (aspect["first"], aspect["second"], aspect["aspect"])
            if key not in seen_aspects and aspect["orb"] <= 1.5:
                seen_aspects.add(key)
                events.append({
                    "date": day["date"],
                    "type": "аспект",
                    "text": f'{aspect["first"]} {aspect["aspect"]} {aspect["second"]} (орб {aspect["orb"]}°)',
                })
        current += timedelta(days=1)

    return events[:max_events]
