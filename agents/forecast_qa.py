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
_SIGN_FORMS = {
    "Овен": ("Овен", "Овне"),
    "Телец": ("Телец", "Тельце"),
    "Близнецы": ("Близнецы", "Близнецах"),
    "Рак": ("Рак", "Раке"),
    "Лев": ("Лев", "Льве"),
    "Дева": ("Дева", "Деве"),
    "Весы": ("Весы", "Весах"),
    "Скорпион": ("Скорпион", "Скорпионе"),
    "Стрелец": ("Стрелец", "Стрельце"),
    "Козерог": ("Козерог", "Козероге"),
    "Водолей": ("Водолей", "Водолее"),
    "Рыбы": ("Рыбы", "Рыбах"),
}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _known_aspects(plan: dict[str, Any]) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()

    def add(first: str, second: str, aspect: str) -> None:
        result.add((first, second, aspect))
        result.add((second, first, aspect))

    for item in plan.get("aspects", []):
        if all(key in item for key in ("first", "second", "aspect")):
            add(item["first"], item["second"], item["aspect"])

    # Для недельных/месячных планов аспекты хранятся в списке событий текстом.
    for event in plan.get("events", []):
        value = event.get("text", "")
        for first in _PLANETS:
            for second in _PLANETS:
                if first == second:
                    continue
                for aspect in ("соединение", "секстиль", "квадрат", "тригон", "оппозиция"):
                    if re.search(
                        rf"\b{re.escape(first)}\s+{aspect}\s+{re.escape(second)}\b",
                        value,
                        flags=re.IGNORECASE,
                    ):
                        add(first, second, aspect)
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
            form_to_sign = {
                form.lower(): sign
                for sign, forms in _SIGN_FORMS.items()
                for form in forms
            }
            forms_pattern = "|".join(
                re.escape(form) for forms in _SIGN_FORMS.values() for form in forms
            )
            pattern = rf"{planet}[^.!?]{{0,45}}\bв\s+({forms_pattern})\b"
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if not match:
                continue
            claimed = form_to_sign.get(match.group(1).lower(), match.group(1))
            actual = positions.get(planet, {}).get("sign")
            if actual and claimed.lower() != actual.lower():
                issues.append(
                    f"Неверное положение {planet}: заявлено {match.group(1)}, "
                    f"расчёт показывает {actual}."
                )

    # 3. Проверяем даты, явно названные в тексте, на попадание в прогнозируемый период.
    date_range = plan.get("date", "")
    parsed_range = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", date_range)
    if parsed_range:
        from datetime import date
        try:
            start_date = date(*map(int, reversed(parsed_range[0])))
            end_date = date(*map(int, reversed(parsed_range[-1])))
            for match in re.finditer(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", text):
                day, month = int(match.group(1)), int(match.group(2))
                year = int(match.group(3)) if match.group(3) else (end_date.year if month < start_date.month and end_date.year > start_date.year else start_date.year)
                try:
                    mentioned_date = date(year, month, day)
                except ValueError:
                    issues.append(f"Некорректная календарная дата: {match.group(0)}.")
                    continue
                if not (start_date <= mentioned_date <= end_date):
                    issues.append(f"Дата {match.group(0)} находится вне прогнозируемого периода {date_range}.")
        except (ValueError, TypeError):
            pass

    # 4. Прогноз «завтра» не должен выдавать сегодня как основной день.
    if period == "tomorrow" and re.search(r"\bсегодня\b", text.lower()):
        issues.append("В прогнозе на завтра обнаружено «сегодня».")

    # 5. Для дневного прогноза проверяем названную фазу Луны.
    moon_phase = plan.get("moon", {}).get("phase")
    phase_aliases = {
        "новолуние": ("новолуние", "новолунии"),
        "растущий серп": ("растущий серп", "растущего серпа"),
        "первая четверть": ("первая четверть", "первой четверти"),
        "растущая Луна": ("растущая луна", "растущей луне", "растущую луну"),
        "полнолуние": ("полнолуние", "полнолунии"),
        "убывающая Луна": ("убывающая луна", "убывающей луне", "убывающую луну"),
        "последняя четверть": ("последняя четверть", "последней четверти"),
        "убывающий серп": ("убывающий серп", "убывающего серпа"),
    }
    mentioned_phases = [
        alias
        for aliases in phase_aliases.values()
        for alias in aliases
        if alias in text.lower()
    ]
    if moon_phase and mentioned_phases:
        allowed = phase_aliases.get(moon_phase, (moon_phase.lower(),))
        if not any(alias in allowed for alias in mentioned_phases):
            issues.append(
                f"Фаза Луны не совпадает с расчётом: заявлено {mentioned_phases[0]}, "
                f"расчёт показывает {moon_phase}."
            )

    # 6. Запрещаем категорические обещания результата.
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
