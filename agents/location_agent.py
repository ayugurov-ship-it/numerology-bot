"""Надёжное определение места рождения.

Это детерминированный агент: нормализует пользовательский ввод, строит
варианты запроса, использует несколько геокодеров и не передаёт в расчёт
непроверенные координаты.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import aiohttp
from timezonefinder import TimezoneFinder


tf = TimezoneFinder()
_CACHE: dict[str, dict[str, Any]] = {}

# Частые русские варианты, которые геокодеры понимают по-разному.
_REPLACEMENTS = {
    "рф": "россия",
    "россия федерация": "россия",
    "каз": "казахстан",
    "узунагач": "узынагаш",
    "узинагач": "узынагаш",
    "джамбульский": "жамбылский",
    "джамбул": "жамбыл",
    "алма-атинской": "алматинской",
    "алмаатинской": "алматинской",
}

_PREFIXES = (
    "село", "с.", "деревня", "д.", "посёлок", "поселок", "п.",
    "город", "г.", "район", "р-н", "область", "обл.",
)


@dataclass
class LocationCandidate:
    display_name: str
    latitude: float
    longitude: float
    timezone: str
    score: float
    source: str


def normalize_place(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").strip().lower()
    value = value.replace("ё", "е")
    value = re.sub(r"[(),;]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    for src, dst in _REPLACEMENTS.items():
        value = re.sub(rf"(?<![а-яa-z]){re.escape(src)}(?![а-яa-z])", dst, value)
    return value.strip(" .,-")


def _variants(text: str) -> list[str]:
    original = " ".join((text or "").strip().split())
    normalized = normalize_place(original)
    variants: list[str] = []
    for value in (original, normalized):
        if value and value not in variants:
            variants.append(value)

    # Убираем служебные типы населённых пунктов, но сохраняем географические
    # уточнения пользователя.
    stripped = normalized
    for prefix in _PREFIXES:
        stripped = re.sub(rf"(?<![а-яa-z]){re.escape(prefix)}(?=\s|$)", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ,.-")
    if stripped and stripped not in variants:
        variants.append(stripped)

    # Отдельно полезен запрос без районных уточнений: геокодер часто лучше
    # находит маленький населённый пункт, а затем мы проверяем страну/регион.
    parts = [p.strip(" ,.-") for p in normalized.split(",") if p.strip(" ,.-")]
    if len(parts) >= 2:
        short = ", ".join(parts[:2])
        if short not in variants:
            variants.append(short)

    return variants[:4]


def _tokens(text: str) -> set[str]:
    return {
        x for x in re.split(r"[^a-zа-я0-9]+", normalize_place(text))
        if len(x) >= 2
    }


def _score(query: str, item: dict[str, Any]) -> float:
    display = item.get("display_name", "")
    address = item.get("address") or {}
    q_tokens = _tokens(query)
    d_tokens = _tokens(display)
    overlap = len(q_tokens & d_tokens) / max(1, len(q_tokens))
    similarity = SequenceMatcher(None, normalize_place(query), normalize_place(display)).ratio()

    # Учитываем отдельные поля адреса: для запроса с районом/страной это
    # надёжнее, чем сравнение только с display_name.
    address_text = " ".join(str(v) for v in address.values())
    a_tokens = _tokens(address_text)
    address_overlap = len(q_tokens & a_tokens) / max(1, len(q_tokens))

    score = 0.50 * overlap + 0.25 * address_overlap + 0.25 * similarity
    if item.get("type") in {"city", "town", "village", "municipality"}:
        score += 0.03
    return min(score, 1.0)


def _timezone(lat: float, lon: float) -> str | None:
    return tf.timezone_at(lat=lat, lng=lon) or tf.certain_timezone_at(lat=lat, lng=lon)


async def _nominatim(session: aiohttp.ClientSession, query: str) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 5,
        "addressdetails": 1,
        "accept-language": "ru,en",
    }
    headers = {
        "User-Agent": "soulcode-gurov-bot/2.0 (natal location agent)",
        "Accept": "application/json",
    }
    try:
        async with session.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
        ) as resp:
            if resp.status != 200:
                return []
            payload = await resp.json(content_type=None)
            return payload if isinstance(payload, list) else []
    except Exception:
        return []


async def _photon(session: aiohttp.ClientSession, query: str) -> list[dict[str, Any]]:
    try:
        async with session.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 5, "lang": "ru"},
            headers={"User-Agent": "soulcode-gurov-bot/2.0"},
        ) as resp:
            if resp.status != 200:
                return []
            payload = await resp.json(content_type=None)
            features = payload.get("features", []) if isinstance(payload, dict) else []
            result = []
            for feature in features:
                props = feature.get("properties") or {}
                coords = (feature.get("geometry") or {}).get("coordinates") or []
                if len(coords) < 2:
                    continue
                result.append({
                    "display_name": ", ".join(
                        str(x) for x in (
                            props.get("name"), props.get("city"),
                            props.get("state"), props.get("country")
                        ) if x
                    ),
                    "lat": coords[1],
                    "lon": coords[0],
                    "address": props,
                    "type": props.get("type"),
                })
            return result
    except Exception:
        return []


def _candidate(query: str, item: dict[str, Any], source: str) -> LocationCandidate | None:
    try:
        lat = float(item["lat"])
        lon = float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    tz = _timezone(lat, lon)
    if not tz:
        return None
    return LocationCandidate(
        display_name=item.get("display_name") or query,
        latitude=lat,
        longitude=lon,
        timezone=tz,
        score=_score(query, item),
        source=source,
    )


async def resolve_location(place: str) -> dict[str, Any]:
    """Возвращает только проверенную геолокацию или понятную ошибку."""
    key = normalize_place(place)
    if not key:
        raise ValueError("Пустое место рождения.")

    cached = _CACHE.get(key)
    if cached:
        return dict(cached)

    variants = _variants(place)
    candidates: list[LocationCandidate] = []
    timeout = aiohttp.ClientTimeout(total=4, connect=2, sock_read=3)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Не бомбим публичный Nominatim параллельными запросами.
        for query in variants:
            results = await _nominatim(session, query)
            for item in results:
                c = _candidate(query, item, "nominatim")
                if c:
                    candidates.append(c)
            if candidates and max(c.score for c in candidates) >= 0.82:
                break

        # Если Nominatim не дал уверенного результата, пробуем другой
        # геокодер. Это существенно снижает зависимость от одного сервиса.
        best = max(candidates, key=lambda c: c.score, default=None)
        if best is None or best.score < 0.68:
            for query in variants[:2]:
                results = await _photon(session, query)
                for item in results:
                    c = _candidate(query, item, "photon")
                    if c:
                        candidates.append(c)
                if candidates and max(c.score for c in candidates) >= 0.82:
                    break

    if not candidates:
        raise ValueError("Не удалось определить координаты этого места.")

    # Дедупликация по координатам.
    unique: dict[tuple[float, float], LocationCandidate] = {}
    for c in candidates:
        key_coord = (round(c.latitude, 4), round(c.longitude, 4))
        if key_coord not in unique or c.score > unique[key_coord].score:
            unique[key_coord] = c

    ranked = sorted(unique.values(), key=lambda x: x.score, reverse=True)
    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None

    # Не выбираем молча случайное место при реально неоднозначном ответе.
    if best.score < 0.58:
        raise ValueError("Место не удалось определить достаточно точно. Укажите населённый пункт и страну.")
    if second and best.score < 0.72 and best.score - second.score < 0.07:
        raise ValueError(
            "Найдено несколько похожих мест. Укажите населённый пункт и страну точнее."
        )

    result = {
        "query": place,
        "display_name": best.display_name,
        "latitude": best.latitude,
        "longitude": best.longitude,
        "timezone": best.timezone,
        "confidence": round(best.score, 3),
        "source": best.source,
    }
    _CACHE[key] = result
    return dict(result)
