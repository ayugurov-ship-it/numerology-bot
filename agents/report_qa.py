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
    claims = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        low = sentence.lower()
        found_aspect = next((a for a in ASPECT_WORDS if a in low), None)
        if not found_aspect:
            continue
        found_planets = [p for p in PLANETS if p.lower() in low]
        # A sentence with two planet names and an aspect is treated as a factual claim.
        if len(found_planets) >= 2:
            claims.append((found_planets[0], found_planets[1], found_aspect, sentence.strip()))
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
