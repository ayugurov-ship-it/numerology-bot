"""Проверка готового натального отчёта до отправки пользователю.

Первый уровень QA — только детерминированные проверки. Он не доверяет
самооценке модели и сверяет текст с рассчитанной картой.
"""
from __future__ import annotations

import re
from typing import Any

ASPECT_WORDS = ("соединение", "секстиль", "квадрат", "тригон", "оппозиция")
PLANETS = (
    "Солнце", "Луна", "Меркурий", "Венера", "Марс",
    "Юпитер", "Сатурн", "Уран", "Нептун", "Плутон",
)
FORBIDDEN_WORDS = ("карма", "вселенная", "потоки")


def _aspect_claims(text: str):
    """Извлекает только явно связанные пары, а не все планеты из предложения.

    Старый алгоритм брал первые две планеты в целом предложении. Из-за этого
    фраза вроде «пятой дом (Сатурн) и тригоном Венера–Уран» ошибочно
    превращалась в «Венера–Сатурн». Сначала ищем явную пару через тире,
    затем — конструкцию «тригон Венера–Уран».
    """
    claims = []
    planet = "|".join(re.escape(p) for p in PLANETS)

    patterns = [
        re.compile(
            rf"(?P<a>{planet})\s*[-—–]\s*(?P<asp>соединени\w*|секстил\w*|квадрат\w*|тригон\w*|оппозиц\w*)\s*[-—–]\s*(?P<b>{planet})",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<asp>соединени\w*|секстил\w*|квадрат\w*|тригон\w*|оппозиц\w*)\s+(?P<a>{planet})\s*[-—–]\s*(?P<b>{planet})",
            re.IGNORECASE,
        ),
    ]

    aspect_map = {
        "соединение": "соединение",
        "соединением": "соединение",
        "соединением": "соединение",
        "секстиль": "секстиль",
        "секстилем": "секстиль",
        "квадрат": "квадрат",
        "квадратом": "квадрат",
        "тригон": "тригон",
        "тригоном": "тригон",
        "оппозиция": "оппозиция",
        "оппозицией": "оппозиция",
    }

    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                asp_raw = match.group("asp").lower()
                asp = next((v for k, v in aspect_map.items() if asp_raw.startswith(k)), None)
                if asp:
                    claims.append((match.group("a"), match.group("b"), asp, sentence.strip()))
    return claims


def validate_report_text(text: str, chart: dict[str, Any], birth_time_known: bool) -> list[str]:
    errors: list[str] = []
    if not text or len(text.strip()) < 500:
        errors.append("Отчёт слишком короткий или пустой.")

    low = text.lower()

    for word in FORBIDDEN_WORDS:
        if word in low:
            errors.append(f"Запрещённая эзотерическая формулировка: {word}.")

    if not birth_time_known:
        # Mentions that merely explain absence of houses/ASC are allowed.
        dangerous_patterns = [
            r"\bасцендент\b[^.\n]{0,100}(?:находится|расположен|в|восходящ)",
            r"\b(?:asc|mc)\b",
            r"\b(?:\d{1,2}|1[0-2])-й\s+дом\b",
            r"\b(?:\d{1,2}|1[0-2])\s+дом\b",
            r"планет[аы]?[^.\n]{0,80}\bдом(?:а|е|ом)?\b",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, low):
                errors.append("В отчёте использованы ASC/MC/дома при неизвестном времени рождения.")
                break

    planets = chart.get("planets", {})
    valid_aspects = {
        (min(a["first"], a["second"]), max(a["first"], a["second"]), a["aspect"])
        for a in chart.get("aspects", [])
    }

    for first, second, aspect, sentence in _aspect_claims(text):
        key = (min(first, second), max(first, second), aspect)
        if key not in valid_aspects:
            errors.append(
                f"Придуманный или неподтверждённый аспект: {first} — {aspect} — {second}. "
                f"Фраза: {sentence[:180]}"
            )

    moon = planets.get("Луна", {})
    if moon.get("time_uncertainty") and len(moon.get("possible_signs", [])) > 1:
        possible = [s.lower() for s in moon["possible_signs"]]
        both_signs_present = all(re.search(rf"\b{re.escape(sign)}\b", low) for sign in possible)
        uncertainty_near_moon = re.search(
            r"луна[^.\n]{0,220}(?:возможн|неопредел|может|или)",
            low,
        )
        if both_signs_present and not uncertainty_near_moon:
            errors.append(
                "Луна трактуется как однозначная, хотя без времени рождения возможны "
                + " и ".join(moon["possible_signs"]) + "."
            )


    # The report must not claim houses if the engine returned none.
    if not chart.get("houses") and re.search(r"\b(?:\d{1,2}|1[0-2])-й\s+дом\b", low):
        errors.append("Упомянут конкретный дом, хотя дома не рассчитаны.")

    return list(dict.fromkeys(errors))
