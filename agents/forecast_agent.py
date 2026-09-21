"""Детерминированный отбор астрологических факторов для прогноза.

Расчёт выполняется Swiss Ephemeris в forecast_engine.py.
Этот модуль НЕ интерпретирует и НЕ генерирует текст: он выбирает,
какие рассчитанные факторы передать языковой модели.
"""

from __future__ import annotations

from typing import Any


_PLANET_PRIORITY = {
    "Плутон": 2,
    "Нептун": 2,
    "Уран": 3,
    "Сатурн": 4,
    "Юпитер": 5,
    "Марс": 6,
    "Венера": 6,
    "Меркурий": 7,
    "Солнце": 9,
    "Луна": 10,
}

_ASPECT_PRIORITY = {
    "соединение": 9,
    "оппозиция": 8,
    "квадрат": 8,
    "тригон": 6,
    "секстиль": 5,
}


def _aspect_priority(item: dict[str, Any]) -> float:
    first = _PLANET_PRIORITY.get(item["first"], 1)
    second = _PLANET_PRIORITY.get(item["second"], 1)
    base = _ASPECT_PRIORITY.get(item["aspect"], 1)
    # Чем точнее аспект, тем выше приоритет.
    orb_bonus = max(0.0, 3.0 - float(item.get("orb", 3.0)))
    return base + max(first, second) * 0.5 + orb_bonus


def build_forecast_plan(
    sky: dict[str, Any],
    period: str,
    zodiac_name: str,
    life_number: int | None,
    personal_day: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Возвращает компактный, проверяемый набор факторов для интерпретации."""
    positions = sky.get("positions", {})
    aspects = list(sky.get("aspects", []))
    ingresses = list(sky.get("ingresses", []))

    ranked_aspects = sorted(aspects, key=_aspect_priority, reverse=True)

    ranked_ingresses = sorted(
        ingresses,
        key=lambda x: (
            _PLANET_PRIORITY.get(x.get("planet", ""), 1),
            x.get("local_time", "99:99"),
        ),
        reverse=True,
    )

    selected_aspects = ranked_aspects[:4]
    selected_ingresses = ranked_ingresses[:3]

    moon = positions.get("Луна", {})
    sun = positions.get("Солнце", {})

    selected_positions = {}
    for planet in ("Солнце", "Луна", "Меркурий", "Венера", "Марс", "Юпитер"):
        if planet in positions:
            p = positions[planet]
            selected_positions[planet] = {
                "sign": p["sign"],
                "degree": p["degree"],
                "retrograde": p["retrograde"],
            }

    plan = {
        "period": period,
        "zodiac": zodiac_name,
        "life_number": life_number,
        "personal_day": personal_day,
        "date": sky.get("date"),
        "timezone": sky.get("timezone"),
        "moon": {
            "sign": moon.get("sign"),
            "degree": moon.get("degree"),
            "phase": sky.get("phase", {}).get("name"),
            "illumination_percent": sky.get("phase", {}).get("illumination_percent"),
        },
        "sun": {
            "sign": sun.get("sign"),
            "degree": sun.get("degree"),
        },
        "positions": selected_positions,
        "aspects": selected_aspects,
        "ingresses": selected_ingresses,
        "source": "Swiss Ephemeris / Moshier fallback",
    }

    # Для дня важно отличать положение планеты от отношения между планетами.
    # Поэтому явно маркируем эти сущности и не даём модели смешивать их.
    plan["interpretation_rules"] = [
        "Положение планеты в знаке само по себе не является аспектом.",
        "Напряжение между двумя планетами можно утверждать только при наличии рассчитанного аспекта.",
        "Каждый названный аспект должен присутствовать в списке aspects.",
        "Луна и её фаза являются отдельным фактором дня.",
        "Не превращать астрологический фактор в гарантированное событие.",
    ]
    return plan


def render_forecast_context(plan: dict[str, Any]) -> str:
    """Человекочитаемый, но структурированный блок для LLM."""
    lines = [
        "РАССЧИТАННЫЙ ПЛАН ПРОГНОЗА. ИСПОЛЬЗУЙ ТОЛЬКО ЭТИ ФАКТЫ.",
        f"Дата: {plan.get('date')}",
        f"Период: {plan.get('period')}",
        f"Знак пользователя: {plan.get('zodiac')}",
        f"Число жизненного пути: {plan.get('life_number')}",
        "",
        "ПОЛОЖЕНИЯ (это НЕ аспекты):",
    ]

    for planet, p in plan.get("positions", {}).items():
        retro = " ℞" if p.get("retrograde") else ""
        lines.append(f"- {planet}: {p.get('degree')}° {p.get('sign')}{retro}")

    moon = plan.get("moon", {})
    lines.extend([
        "",
        "ЛУНА:",
        f"- знак: {moon.get('sign')}",
        f"- фаза: {moon.get('phase')}",
        f"- освещённость: {moon.get('illumination_percent')}%",
        "",
        "РАССЧИТАННЫЕ АСПЕКТЫ:",
    ])
    for a in plan.get("aspects", []):
        lines.append(
            f"- {a['first']} — {a['aspect']} — {a['second']} "
            f"(орб {a.get('orb')}°)"
        )

    lines.extend(["", "ПЕРЕХОДЫ В ТЕЧЕНИЕ СУТОК:"])
    for i in plan.get("ingresses", []):
        lines.append(
            f"- {i['planet']}: {i['from_sign']} → {i['to_sign']} "
            f"в {i['local_time']} по {plan.get('timezone')}"
        )

    if plan.get("personal_day"):
        pd = plan["personal_day"]
        lines.extend([
            "",
            "НУМЕРОЛОГИЯ:",
            f"- личный год: {pd['personal_year']}",
            f"- личный месяц: {pd['personal_month']}",
            f"- личный день: {pd['personal_day']}",
        ])

    lines.extend(["", "ПРАВИЛА ФАКТИЧЕСКОЙ ТОЧНОСТИ:"])
    lines.extend(f"- {rule}" for rule in plan["interpretation_rules"])
    return "\n".join(lines)
