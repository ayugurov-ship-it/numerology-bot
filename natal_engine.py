"""Расчёт полной натальной карты на базе Swiss Ephemeris.

Движок отвечает только за расчёты. Интерпретация выполняется отдельно через Groq.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import swisseph as swe
from timezonefinder import TimezoneFinder


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

ASPECTS = [
    ("соединение", 0, 8),
    ("секстиль", 60, 5),
    ("квадрат", 90, 7),
    ("тригон", 120, 7),
    ("оппозиция", 180, 8),
]

tf = TimezoneFinder()


def zodiac_position(longitude: float) -> dict[str, Any]:
    longitude %= 360.0
    index = int(longitude // 30)
    degree = longitude - index * 30
    deg = int(degree)
    minutes = int(round((degree - deg) * 60))
    if minutes == 60:
        deg += 1
        minutes = 0
    if deg == 30:
        deg = 0
        index = (index + 1) % 12
    name, emoji, element = ZODIAC[index]
    return {
        "sign": name,
        "emoji": emoji,
        "element": element,
        "degree": round(degree, 4),
        "formatted": f"{deg}°{minutes:02d}′ {name}",
    }


def house_for_longitude(longitude: float, cusps: tuple[float, ...]) -> int:
    lon = longitude % 360.0
    # cusps[0] = 1-й дом, ..., cusps[11] = 12-й дом
    for i in range(12):
        start = cusps[i] % 360.0
        end = cusps[(i + 1) % 12] % 360.0
        if i == 11:
            end += 360.0
        test = lon
        if test < start:
            test += 360.0
        if start <= test < end:
            return i + 1
    return 12


def angular_distance(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)


async def geocode_place(place: str) -> dict[str, Any]:
    """Находит координаты места рождения через несколько вариантов запроса."""
    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        "User-Agent": "soulcode-gurov-bot/1.0 (natal chart)",
        "Accept-Language": "ru,en",
    }
    cleaned = place.strip()
    variants = [cleaned]

    # Помогаем с запросами вида «село ..., район ..., страна».
    simplified = cleaned
    for prefix in ("село ", "деревня ", "посёлок ", "поселок ", "г. "):
        simplified = simplified.replace(prefix, "")
    if simplified != cleaned:
        variants.append(simplified)

    # Частая форма названия Узынагаша встречается с разным написанием.
    if "узунагач" in cleaned.lower() or "узинагач" in cleaned.lower():
        variants.extend([
            "Узынагаш, Казахстан",
            "Узынагаш, Жамбылский район, Алматинская область, Казахстан",
        ])

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        data = []
        for query in dict.fromkeys(variants):
            params = {
                "q": query,
                "format": "jsonv2",
                "limit": 3,
                "addressdetails": 1,
            }
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    continue
                candidate = await resp.json(content_type=None)
                if candidate:
                    data = candidate
                    break

    if not data:
        raise ValueError("Место рождения не найдено. Укажите населённый пункт и страну.")
    item = data[0]
    lat = float(item["lat"])
    lon = float(item["lon"])
    timezone = tf.timezone_at(lat=lat, lng=lon)
    if not timezone:
        timezone = tf.certain_timezone_at(lat=lat, lng=lon)
    if not timezone:
        raise ValueError("Не удалось определить часовой пояс места рождения.")
    return {
        "query": place,
        "display_name": item.get("display_name", place),
        "latitude": lat,
        "longitude": lon,
        "timezone": timezone,
    }


def _calc_planet(jd_ut: float, body: int):
    """Сначала Swiss Ephemeris, затем встроенный Moshier без файлов .se1."""
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    try:
        values, retflag = swe.calc_ut(jd_ut, body, flags)
        if values:
            return values, retflag
    except Exception:
        pass
    return swe.calc_ut(jd_ut, body, swe.FLG_MOSEPH | swe.FLG_SPEED)

def _calculate_aspects(planets: dict[str, Any]) -> list[dict[str, Any]]:
    aspects = []
    names = list(planets.keys())
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            diff = angular_distance(planets[first]["longitude"], planets[second]["longitude"])
            for aspect_name, exact, orb in ASPECTS:
                actual_orb = abs(diff - exact)
                if actual_orb <= orb:
                    aspects.append({
                        "first": first,
                        "second": second,
                        "aspect": aspect_name,
                        "exact_degree": exact,
                        "orb": round(actual_orb, 2),
                    })
                    break
    return aspects


def calculate_natal_chart_without_time(
    date_str: str,
    latitude: float,
    longitude: float,
    timezone_name: str,
    place_display_name: str | None = None,
) -> dict[str, Any]:
    """Рассчитывает карту без времени. Планеты берутся на местный полдень.
    Асцендент и дома намеренно не рассчитываются."""
    local_dt = datetime.strptime(date_str, "%d.%m.%Y").replace(
        hour=12, minute=0, tzinfo=ZoneInfo(timezone_name)
    )
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    hour = utc_dt.hour + utc_dt.minute / 60
    jd_ut = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour)
    swe.set_ephe_path("")

    planets = {}
    for name, body in PLANETS:
        values, _ = _calc_planet(jd_ut, body)
        lon = float(values[0])
        pos = zodiac_position(lon)
        planets[name] = {
            **pos,
            "longitude": round(lon, 6),
            "latitude": round(float(values[1]), 6),
            "distance_au": round(float(values[2]), 8),
            "speed_longitude": round(float(values[3]), 6),
            "retrograde": float(values[3]) < 0,
            "house": None,
        }

    # Проверяем Луну в начале и конце местных суток. Если знак меняется,
    # не выдаём ложную точность.
    moon_signs = set()
    for local_hour in (0, 23.999):
        check_local = local_dt.replace(hour=0) if local_hour == 0 else local_dt.replace(hour=23, minute=59, second=56)
        check_utc = check_local.astimezone(ZoneInfo("UTC"))
        check_jd = swe.julday(
            check_utc.year, check_utc.month, check_utc.day,
            check_utc.hour + check_utc.minute / 60 + check_utc.second / 3600
        )
        moon_values, _ = _calc_planet(check_jd, swe.MOON)
        moon_signs.add(zodiac_position(float(moon_values[0]))["sign"])

    planets["Луна"]["time_uncertainty"] = len(moon_signs) > 1
    planets["Луна"]["possible_signs"] = sorted(moon_signs)

    return {
        "calculation": {
            "local_datetime": local_dt.isoformat(),
            "utc_datetime": utc_dt.isoformat(),
            "timezone": timezone_name,
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
            "place": place_display_name or "",
            "zodiac": "tropical",
            "house_system": None,
            "ephemeris": "Swiss Ephemeris / Moshier fallback",
            "birth_time_known": False,
        },
        "angles": {},
        "planets": planets,
        "houses": [],
        "aspects": _calculate_aspects(planets),
    }


def calculate_natal_chart(
    date_str: str,
    birth_time: str,
    latitude: float,
    longitude: float,
    timezone_name: str,
    place_display_name: str | None = None,
) -> dict[str, Any]:
    """Рассчитывает тропическую натальную карту, дома Плацидуса."""
    if not birth_time:
        raise ValueError("Для полной натальной карты необходимо точное время рождения.")

    local_dt = datetime.strptime(
        f"{date_str} {birth_time}", "%d.%m.%Y %H:%M"
    ).replace(tzinfo=ZoneInfo(timezone_name))
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

    # Swiss Ephemeris принимает UT в часах.
    hour = utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600
    jd_ut = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour)

    swe.set_ephe_path("")
    cusps_raw, ascmc = swe.houses_ex(jd_ut, latitude, longitude, b"P")
    cusps = tuple(cusps_raw[:12])

    planets: dict[str, Any] = {}
    for name, body in PLANETS:
        values, _ = _calc_planet(jd_ut, body)
        lon = float(values[0])
        pos = zodiac_position(lon)
        planets[name] = {
            **pos,
            "longitude": round(lon, 6),
            "latitude": round(float(values[1]), 6),
            "distance_au": round(float(values[2]), 8),
            "speed_longitude": round(float(values[3]), 6),
            "retrograde": float(values[3]) < 0,
            "house": house_for_longitude(lon, cusps),
        }

    houses = []
    for i, cusp in enumerate(cusps, start=1):
        pos = zodiac_position(float(cusp))
        houses.append({
            "house": i,
            "longitude": round(float(cusp), 6),
            "sign": pos["sign"],
            "degree": pos["degree"],
            "formatted": pos["formatted"],
        })

    angles = {
        "ascendant": {
            **zodiac_position(float(ascmc[0])),
            "longitude": round(float(ascmc[0]), 6),
        },
        "mc": {
            **zodiac_position(float(ascmc[1])),
            "longitude": round(float(ascmc[1]), 6),
        },
    }

    aspects = []
    names = list(planets.keys())
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            diff = angular_distance(
                planets[first]["longitude"], planets[second]["longitude"]
            )
            for aspect_name, exact, orb in ASPECTS:
                actual_orb = abs(diff - exact)
                if actual_orb <= orb:
                    aspects.append({
                        "first": first,
                        "second": second,
                        "aspect": aspect_name,
                        "exact_degree": exact,
                        "orb": round(actual_orb, 2),
                    })
                    break

    return {
        "calculation": {
            "local_datetime": local_dt.isoformat(),
            "utc_datetime": utc_dt.isoformat(),
            "timezone": timezone_name,
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
            "place": place_display_name or "",
            "zodiac": "tropical",
            "house_system": "Placidus",
            "ephemeris": "Swiss Ephemeris / Moshier fallback",
        },
        "angles": angles,
        "planets": planets,
        "houses": houses,
        "aspects": aspects,
    }
