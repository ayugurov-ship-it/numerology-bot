"""Проверки результата натального расчёта до передачи его в ИИ."""
from __future__ import annotations

from typing import Any

EXPECTED_PLANETS = {
    "Солнце", "Луна", "Меркурий", "Венера", "Марс",
    "Юпитер", "Сатурн", "Уран", "Нептун", "Плутон",
}
VALID_ASPECTS = {"соединение", "секстиль", "квадрат", "тригон", "оппозиция"}


def validate_natal_chart(chart: dict[str, Any], birth_time_known: bool) -> list[str]:
    errors: list[str] = []
    planets = chart.get("planets")

    if not isinstance(planets, dict):
        return ["Отсутствует блок planets."]
    missing = EXPECTED_PLANETS - set(planets)
    extra = set(planets) - EXPECTED_PLANETS
    if missing:
        errors.append("Отсутствуют планеты: " + ", ".join(sorted(missing)))
    if extra:
        errors.append("Обнаружены неизвестные объекты: " + ", ".join(sorted(extra)))

    for name in EXPECTED_PLANETS & set(planets):
        p = planets[name]
        try:
            lon = float(p["longitude"])
            if not 0 <= lon < 360:
                errors.append(f"{name}: долгота вне диапазона 0..360.")
            degree = float(p["degree"])
            if not 0 <= degree < 30:
                errors.append(f"{name}: градус знака вне диапазона 0..30.")
        except (KeyError, TypeError, ValueError):
            errors.append(f"{name}: повреждены координаты.")

        if not isinstance(p.get("retrograde"), bool):
            errors.append(f"{name}: некорректный признак ретроградности.")

    aspects = chart.get("aspects")
    if not isinstance(aspects, list):
        errors.append("Отсутствует список аспектов.")
    else:
        seen: set[tuple[str, str, str]] = set()
        for aspect in aspects:
            first = aspect.get("first")
            second = aspect.get("second")
            kind = aspect.get("aspect")
            key = tuple(sorted((str(first), str(second)))) + (str(kind),)
            if first not in planets or second not in planets:
                errors.append("Аспект ссылается на неизвестную планету.")
            if kind not in VALID_ASPECTS:
                errors.append(f"Неизвестный аспект: {kind}.")
            try:
                orb = float(aspect["orb"])
                if orb < 0 or orb > 8:
                    errors.append("Недопустимый орбис аспекта.")
            except (KeyError, TypeError, ValueError):
                errors.append("Аспект без корректного орбиса.")
            if key in seen:
                errors.append("Дублирующийся аспект.")
            seen.add(key)

    houses = chart.get("houses")
    angles = chart.get("angles")
    if birth_time_known:
        if not isinstance(houses, list) or len(houses) != 12:
            errors.append("Для известного времени должно быть ровно 12 домов.")
        if not isinstance(angles, dict) or not angles.get("ascendant") or not angles.get("mc"):
            errors.append("Для известного времени отсутствуют ASC/MC.")
        for name, p in planets.items():
            if p.get("house") is None or not 1 <= int(p["house"]) <= 12:
                errors.append(f"{name}: некорректный номер дома.")
    else:
        if houses:
            errors.append("При неизвестном времени дома не должны рассчитываться.")
        if angles:
            errors.append("При неизвестном времени ASC/MC не должны рассчитываться.")

    return list(dict.fromkeys(errors))
