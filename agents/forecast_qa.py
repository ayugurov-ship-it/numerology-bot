"""Детерминированный контроль фактической части астрологического прогноза."""

from __future__ import annotations

import re
from typing import Any


_PLANETS = (
    "Солнце", "Луна", "Меркурий", "Венера", "Марс",
    "Юпитер", "Сатурн", "Уран", "Нептун", "Плутон",
)
_SIGNS = (
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
)
_ASPECTS = ("соединени", "секстил", "квадрат", "тригон", "оппозиц")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _known_aspects(plan: dict[str, Any]) -> set[tuple[str, str, str]]:
    result = set()
    for a in plan.get("aspects", []):
        result.add((a["first"], a["second"], a["aspect"]))
        result.add((a["second"], a["first"], a["aspect"]))
    return result


def validate_forecast(text: str, plan: dict[str, Any], period: str) -> dict[str, Any]:
    """Проверяет наиболее опасные ошибки без дополнительного вызова LLM."""
    issues: list[str] = []
    known = _known_aspects(plan)

    # 1. Если модель называет аспект, проверяем пару планет в том же предложении.
    for sentence in _sentences(text):
        lower = sentence.lower()
        if not any(a in lower for a in _ASPECTS):
            continue
        mentioned = [p for p in _PLANETS if p.lower() in lower]
        if len(mentioned) >= 2:
            found = False
            for i, first in enumerate(mentioned):
                for second in mentioned[i + 1:]:
                    for aspect_name in ("соединение", "секстиль", "квадрат", "тригон", "оппозиция"):
                        if aspect_name[:5] in lower:
                            if any(
                                key[0] == first and key[1] == second and key[2] == aspect_name
                                for key in known
                            ):
                                found = True
                                break
                    if found:
                        break
                if found:
                    break
            if not found:
                issues.append(f"Неподтверждённый аспект: {sentence[:180]}")

    # 2. Проверяем явные утверждения вида «планета в знаке».
    positions = plan.get("positions", {})
    for sentence in _sentences(text):
        for planet in _PLANETS:
            pattern = rf"{planet}[^.!?]{{0,45}}\bв\s+({'|'.join(_SIGNS)})\b"
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if not match:
                continue
            claimed = match.group(1)
            actual = positions.get(planet, {}).get("sign")
            if actual and claimed.lower() != actual.lower():
                issues.append(
                    f"Неверное положение {planet}: заявлено {claimed}, "
                    f"расчёт показывает {actual}."
                )

    # 3. Луна и дата: прогноз «завтра» не должен выдавать сегодня как основной день.
    if period == "tomorrow" and re.search(r"\bсегодня\b", text.lower()):
        issues.append("В прогнозе на завтра обнаружено «сегодня».")

    # 4. Запрещаем категорические обещания результата.
    if re.search(
        r"\b(точно произойд[её]т|неизбежно|гарантированно|гарантирует|"
        r"обязательно получите|обязательно произойд[её]т)\b",
        text.lower(),
    ):
        issues.append("Категоричное предсказание результата.")

    return {
        "pass": not issues,
        "issues": issues,
        "checked_aspects": len(known) // 2,
        "period": period,
    }
