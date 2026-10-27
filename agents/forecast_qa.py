"""Детерминированная проверка фактов, дат и нумерологических показателей прогноза."""
from __future__ import annotations

import re
from datetime import date, timedelta
from itertools import combinations
from typing import Any

_PLANET_PATTERNS = {
    "Солнце": r"солнц(?:е|а|у|ем)",
    "Луна": r"лун(?:а|ы|е|у|ой|ою)",
    "Меркурий": r"меркур(?:ий|ия|ию|ием|ии)",
    "Венера": r"венер(?:а|ы|е|у|ой|ою)",
    "Марс": r"марс(?:а|у|ом|е)?",
    "Юпитер": r"юпитер(?:а|у|ом|е)?",
    "Сатурн": r"сатурн(?:а|у|ом|е)?",
    "Уран": r"уран(?:а|у|ом|е)?",
    "Нептун": r"нептун(?:а|у|ом|е)?",
    "Плутон": r"плутон(?:а|у|ом|е)?",
}
_PLANETS = tuple(_PLANET_PATTERNS)
_ASPECT_PATTERNS = {
    "соединение": r"соедин\w*",
    "секстиль": r"секстил\w*",
    "квадрат": r"квадрат\w*",
    "тригон": r"тригон\w*",
    "оппозиция": r"оппозиц\w*",
}
_SIGNS = (
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
)
_SIGN_FORMS = {
    "Овен": ("Овен", "Овна", "Овне", "Овном"),
    "Телец": ("Телец", "Тельца", "Тельце", "Тельцом"),
    "Близнецы": ("Близнецы", "Близнецов", "Близнецах"),
    "Рак": ("Рак", "Рака", "Раке", "Раком"),
    "Лев": ("Лев", "Льва", "Льве", "Львом"),
    "Дева": ("Дева", "Девы", "Деве", "Деву"),
    "Весы": ("Весы", "Весов", "Весах"),
    "Скорпион": ("Скорпион", "Скорпиона", "Скорпионе", "Скорпионом"),
    "Стрелец": ("Стрелец", "Стрельца", "Стрельце", "Стрельцом"),
    "Козерог": ("Козерог", "Козерога", "Козероге", "Козерогом"),
    "Водолей": ("Водолей", "Водолея", "Водолее", "Водолеем"),
    "Рыбы": ("Рыбы", "Рыб", "Рыбах"),
}
_SIGN_INDEX = {name: i for i, name in enumerate(_SIGNS)}
_SIGN_TO_CANONICAL = {
    form.lower(): sign for sign, forms in _SIGN_FORMS.items() for form in forms
}
_SIGN_FORM_PATTERN = "|".join(
    re.escape(form)
    for form in sorted(_SIGN_TO_CANONICAL, key=len, reverse=True)
)
_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _mentioned_planets(text: str) -> list[str]:
    return [
        planet for planet, pattern in _PLANET_PATTERNS.items()
        if re.search(rf"\b(?:{pattern})\b", text, flags=re.IGNORECASE)
    ]


def _period_bounds(plan: dict[str, Any]) -> tuple[date | None, date | None]:
    values = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", str(plan.get("date", "")))
    if not values:
        return None, None
    try:
        first = date(int(values[0][2]), int(values[0][1]), int(values[0][0]))
        last = date(int(values[-1][2]), int(values[-1][1]), int(values[-1][0]))
        return first, last
    except ValueError:
        return None, None


def _year_for_month(month: int, first: date, last: date) -> int:
    if last.year > first.year and month < first.month:
        return last.year
    return first.year


def _make_date(day: int, month: int, year: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _date_mentions(text: str, plan: dict[str, Any]) -> list[set[date]]:
    """Возвращает датированные упоминания: точные даты и диапазоны с названиями месяцев."""
    first, last = _period_bounds(plan)
    if not first or not last:
        return []
    mentions: list[set[date]] = []

    # Формат 27.10.2026 или 27.10. Если это десятичное число/орб, день 0 будет пропущен.
    for match in re.finditer(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", text):
        day, month = int(match.group(1)), int(match.group(2))
        if not 1 <= day <= 31 or not 1 <= month <= 12:
            continue
        year = int(match.group(3)) if match.group(3) else _year_for_month(month, first, last)
        parsed = _make_date(day, month, year)
        if parsed:
            mentions.append({parsed})

    month_pattern = "|".join(_MONTHS)
    # Диапазоны: «01–07 ноября», «20-23 ноября».
    range_pattern = rf"\b(\d{{1,2}})\s*[-‑–—]\s*(\d{{1,2}})\s+({month_pattern})\b"
    for match in re.finditer(range_pattern, text, flags=re.IGNORECASE):
        start_day, end_day = int(match.group(1)), int(match.group(2))
        month_name = match.group(3).lower()
        month = _MONTHS[month_name]
        year = _year_for_month(month, first, last)
        dates = {
            parsed
            for day in range(start_day, end_day + 1)
            if (parsed := _make_date(day, month, year)) is not None
        }
        if dates:
            mentions.append(dates)

    # Одиночные даты: «25 ноября».
    single_pattern = rf"\b(\d{{1,2}})\s+({month_pattern})\b"
    for match in re.finditer(single_pattern, text, flags=re.IGNORECASE):
        day, month_name = int(match.group(1)), match.group(2).lower()
        month = _MONTHS[month_name]
        year = _year_for_month(month, first, last)
        parsed = _make_date(day, month, year)
        if parsed:
            mentions.append({parsed})

    # «В 25-й день», «на 3-й день» — точная дата внутри периода.
    for match in re.finditer(
        r"\b(?:в|на|к)\s+(\d{1,2})\s*[-‑–—]?\s*(?:й|ый|ой|го)?\s+(?:день|число)\b",
        text,
        flags=re.IGNORECASE,
    ):
        parsed = _make_date(int(match.group(1)), first.month, first.year)
        if parsed:
            mentions.append({parsed})

    # Упоминания частей месяца без конкретного числа.
    part_ranges = (
        (r"\b(?:в начале|начало|первая треть|первой трети)\b", 0, 1),
        (r"\b(?:в середине|середина|вторая треть|второй трети)\b", 1, 2),
        (r"\b(?:в конце|конец|последняя треть|последней трети)\b", 2, 3),
    )
    total_days = (last - first).days + 1
    for pattern, lower_part, upper_part in part_ranges:
        if re.search(pattern, text, flags=re.IGNORECASE):
            lo = lower_part * total_days // 3
            hi = upper_part * total_days // 3
            mentions.append({
                first + timedelta(days=offset)
                for offset in range(lo, min(hi, total_days) if upper_part < 3 else total_days)
            })
    return mentions


def _date_constraint(text: str, plan: dict[str, Any]) -> set[date] | None:
    """Для проверки аспекта предпочитает точную дату, затем указанный диапазон."""
    first, last = _period_bounds(plan)
    if not first or not last:
        return None

    exact: set[date] = set()
    for match in re.finditer(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", text):
        day, month = int(match.group(1)), int(match.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            year = int(match.group(3)) if match.group(3) else _year_for_month(month, first, last)
            parsed = _make_date(day, month, year)
            if parsed:
                exact.add(parsed)
    for match in re.finditer(
        r"\b(?:в|на|к)\s+(\d{1,2})\s*[-‑–—]?\s*(?:й|ый|ой|го)?\s+(?:день|число)\b",
        text,
        flags=re.IGNORECASE,
    ):
        parsed = _make_date(int(match.group(1)), first.month, first.year)
        if parsed:
            exact.add(parsed)
    if exact:
        return exact

    mentions = _date_mentions(text, plan)
    if mentions:
        # Если указано несколько дат, объединяем упомянутые дни; для диапазона это весь диапазон.
        return set().union(*mentions)
    return None


def _aspect_records(plan: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in plan.get("aspects", []):
        if all(key in item for key in ("first", "second", "aspect")):
            records.append({
                "first": item["first"],
                "second": item["second"],
                "aspect": item["aspect"],
                "date": plan.get("date"),
            })

    for event in plan.get("events", []):
        value = str(event.get("text", ""))
        for first, first_pattern in _PLANET_PATTERNS.items():
            for second, second_pattern in _PLANET_PATTERNS.items():
                if first == second:
                    continue
                for aspect_name, aspect_pattern in _ASPECT_PATTERNS.items():
                    pattern = rf"\b(?:{first_pattern})\s+{aspect_pattern}\s+(?:{second_pattern})\b"
                    if re.search(pattern, value, flags=re.IGNORECASE):
                        records.append({
                            "first": first,
                            "second": second,
                            "aspect": aspect_name,
                            "date": event.get("date"),
                        })
    # Удаляем дубликаты, сохраняя различия по дате.
    unique = {}
    for record in records:
        key = (record["first"], record["second"], record["aspect"], record.get("date"))
        unique[key] = record
    return list(unique.values())


def _transition_records(plan: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for event in plan.get("events", []):
        value = str(event.get("text", ""))
        if "→" not in value or ":" not in value:
            continue
        planet, rest = value.split(":", 1)
        match = re.search(r"([А-Яа-яЁё]+)\s*→\s*([А-Яа-яЁё]+)", rest)
        if not match:
            continue
        from_sign = _SIGN_TO_CANONICAL.get(match.group(1).lower())
        to_sign = _SIGN_TO_CANONICAL.get(match.group(2).lower())
        if from_sign and to_sign and planet.strip() in _PLANETS:
            records.append({
                "planet": planet.strip(),
                "from_sign": from_sign,
                "to_sign": to_sign,
                "date": event.get("date"),
            })
    return records


def validate_forecast(text: str, plan: dict[str, Any], period: str) -> dict[str, Any]:
    """Проверяет соответствие аспектов, дат, переходов и нумерологии расчётным данным."""
    issues: list[str] = []
    aspect_records = _aspect_records(plan)
    transition_records = _transition_records(plan)

    # 1. Аспект должен быть рассчитан для нужной пары планет и, если названа дата,
    # именно на эту дату или в указанный диапазон.
    for sentence in _sentences(text):
        mentioned_aspects = [
            name for name, pattern in _ASPECT_PATTERNS.items()
            if re.search(pattern, sentence, flags=re.IGNORECASE)
        ]
        planets = _mentioned_planets(sentence)
        if not mentioned_aspects or len(planets) < 2:
            continue

        constraint = _date_constraint(sentence, plan)
        for aspect in mentioned_aspects:
            pair_records = [
                record for record in aspect_records
                if record["aspect"] == aspect
                and record["first"] in planets
                and record["second"] in planets
            ]
            if not pair_records:
                issues.append(
                    f"Неподтверждённый аспект/пара планет: {sentence[:180]}"
                )
                continue
            if constraint is not None:
                matching_dates = set()
                for record in pair_records:
                    raw_date = record.get("date")
                    parsed = None
                    if isinstance(raw_date, str):
                        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", raw_date)
                        if match:
                            parsed = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
                    if parsed:
                        matching_dates.add(parsed)
                if matching_dates and not matching_dates.intersection(constraint):
                    issues.append(
                        f"Аспект заявлен не на ту дату/период: {sentence[:180]}"
                    )
                elif not matching_dates and period in {"week", "month"}:
                    issues.append(
                        f"Для датированного аспекта нет даты в расчётных событиях: {sentence[:180]}"
                    )

    # 2. Проверяем явные положения планет по дневному расчёту.
    positions = plan.get("positions", {})
    for sentence in _sentences(text):
        for planet, planet_pattern in _PLANET_PATTERNS.items():
            pattern = rf"\b(?:{planet_pattern})[^.!?]{{0,45}}\bв\s+({_SIGN_FORM_PATTERN})\b"
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if not match:
                continue
            claimed = _SIGN_TO_CANONICAL.get(match.group(1).lower(), match.group(1))
            actual = positions.get(planet, {}).get("sign")
            if actual and claimed.lower() != actual.lower():
                issues.append(
                    f"Неверное положение {planet}: заявлено {match.group(1)}, расчёт показывает {actual}."
                )

    # 3. Даты и диапазоны в тексте должны попадать в прогнозируемый период.
    first, last = _period_bounds(plan)
    if first and last:
        seen_outside = set()
        for sentence in _sentences(text):
            for mention in _date_mentions(sentence, plan):
                for mentioned_date in mention:
                    if not first <= mentioned_date <= last:
                        seen_outside.add(mentioned_date.strftime("%d.%m.%Y"))
        for value in sorted(seen_outside):
            issues.append(f"Дата {value} находится вне прогнозируемого периода {plan.get('date')}.")

    # 4. Проверяем переходы знаков Луны, названные как конкретные события.
    for sentence in _sentences(text):
        lower = sentence.lower()
        if not re.search(r"\bлун\w*\b", lower):
            continue
        if not re.search(r"переход|переходит|меняет знак|меняет знаки|движется|затем в", lower):
            continue

        pair_pattern = rf"\b(?:с|со|из)\s+({_SIGN_FORM_PATTERN})\s+в\s+({_SIGN_FORM_PATTERN})\b"
        for match in re.finditer(pair_pattern, sentence, flags=re.IGNORECASE):
            from_sign = _SIGN_TO_CANONICAL.get(match.group(1).lower())
            to_sign = _SIGN_TO_CANONICAL.get(match.group(2).lower())
            if not from_sign or not to_sign:
                continue
            candidates = [
                event for event in transition_records
                if event["planet"] == "Луна"
                and event["from_sign"] == from_sign
                and event["to_sign"] == to_sign
            ]
            constraint = _date_constraint(sentence, plan)
            if not candidates:
                issues.append(
                    f"Неподтверждённый переход Луны {from_sign} → {to_sign}: {sentence[:160]}"
                )
            elif constraint is not None:
                candidate_dates = set()
                for event in candidates:
                    raw_date = event.get("date")
                    if isinstance(raw_date, str):
                        date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", raw_date)
                        if date_match:
                            candidate_dates.add(date(int(date_match.group(3)), int(date_match.group(2)), int(date_match.group(1))))
                if candidate_dates and not candidate_dates.intersection(constraint):
                    issues.append(f"Переход Луны указан не на ту дату: {sentence[:160]}")

        # Отлавливаем явно обратную последовательность знаков Луны (например, Лев → Рак).
        if re.search(r"меняет знак|меняет знаки|переход|переходит|затем в", lower):
            hits = []
            for match in re.finditer(rf"\b({_SIGN_FORM_PATTERN})\b", sentence, flags=re.IGNORECASE):
                sign = _SIGN_TO_CANONICAL.get(match.group(1).lower())
                if sign:
                    hits.append((match.start(), sign))
            hits.sort()
            signs = [sign for _, sign in hits]
            for previous, current in zip(signs, signs[1:]):
                step = (_SIGN_INDEX[current] - _SIGN_INDEX[previous]) % 12
                if step >= 7:
                    issues.append(
                        f"Последовательность знаков Луны выглядит обратной ({previous} → {current}): {sentence[:160]}"
                    )
                    break

    # 5. Завтра не должно описываться как сегодня.
    if period == "tomorrow" and re.search(r"\bсегодня\b", text.lower()):
        issues.append("В прогнозе на завтра обнаружено «сегодня».")

    # 6. Фаза Луны в дневном прогнозе должна соответствовать расчёту.
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
        alias for aliases in phase_aliases.values()
        for alias in aliases if alias in text.lower()
    ]
    if moon_phase and mentioned_phases:
        allowed = phase_aliases.get(moon_phase, (moon_phase.lower(),))
        if not any(alias in allowed for alias in mentioned_phases):
            issues.append(
                f"Фаза Луны не совпадает с расчётом: заявлено {mentioned_phases[0]}, расчёт показывает {moon_phase}."
            )

    # 7. Не смешиваем число жизненного пути с числом недели/месяца/личного дня.
    life_number = plan.get("life_number")
    if life_number is not None:
        life_patterns = (
            r"(?:число\s+жизненного\s+пути|число\s+пути)\D{0,20}(\d{1,2})",
            r"жизненная\s+дорога\D{0,30}(\d{1,2})",
        )
        for pattern in life_patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                if int(match.group(1)) != int(life_number):
                    issues.append(
                        f"Число жизненного пути подменено: в профиле {life_number}, в тексте {match.group(1)}."
                    )

    period_number = plan.get("period_number")
    label = plan.get("period_number_label")
    if period_number is not None and label:
        number_section = re.search(
            r"(?:🎯|🔢)\s*(.*?)(?=\n\s*(?:✨|$)|$)", text, flags=re.DOTALL
        )
        section = number_section.group(1) if number_section else ""
        label_pattern = rf"{re.escape(str(label))}\s*[:—-]?\s*(\d+)"
        number_match = re.search(label_pattern, section, flags=re.IGNORECASE)
        if not number_match:
            issues.append(
                f"В нумерологическом разделе должно быть явно указано «{label} {period_number}»."
            )
        elif int(number_match.group(1)) != int(period_number):
            issues.append(
                f"Неверное {label}: заявлено {number_match.group(1)}, расчёт показывает {period_number}."
            )

    # 8. Запрещаем категорические обещания результата.
    if re.search(
        r"\b(точно произойд[её]т|неизбежно|гарантированно|гарантирует|"
        r"обязательно получите|обязательно произойд[её]т)\b",
        text.lower(),
    ):
        issues.append("Категоричное предсказание результата.")

    return {
        "pass": not issues,
        "issues": issues,
        "checked_aspects": len(aspect_records),
        "period": period,
    }
