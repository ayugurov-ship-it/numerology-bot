from pathlib import Path
import py_compile

from calendar_patch import patch as calendar_patch

MAIN = Path("main.py")


def patch_groq():
    source = MAIN.read_text(encoding="utf-8")

    old_budget = '        "max_completion_tokens": 1500,'
    new_budget = '        "max_completion_tokens": 4096,'
    if old_budget in source:
        source = source.replace(old_budget, new_budget, 1)

    reasoning_block = (
        '        "reasoning_effort": "low",\n'
        '        "include_reasoning": False'
    )
    if reasoning_block not in source:
        needle = '        "max_completion_tokens": 4096,\n'
        replacement = (
            '        "max_completion_tokens": 4096,\n'
            '        "reasoning_effort": "low",\n'
            '        "include_reasoning": False\n'
        )
        if needle not in source:
            raise RuntimeError("Groq request block not found")
        source = source.replace(needle, replacement, 1)

    old_response = '''            result = await resp.json()
            return result["choices"][0]["message"]["content"].strip()
'''
    new_response = '''            result = await resp.json()
            choice = (result.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""

            if not content.strip():
                logger.error(
                    "GROQ API EMPTY CONTENT: finish_reason=%s usage=%s message_keys=%s",
                    choice.get("finish_reason"),
                    result.get("usage"),
                    list(message.keys()),
                )
                raise RuntimeError(
                    "Groq returned empty content "
                    f"(finish_reason={choice.get("finish_reason")})"
                )

            logger.info(
                "GROQ OK: model=%s finish_reason=%s content_chars=%s",
                result.get("model", MODEL_NAME),
                choice.get("finish_reason"),
                len(content.strip()),
            )
            return content.strip()
'''
    if old_response in source:
        source = source.replace(old_response, new_response, 1)

    MAIN.write_text(source, encoding="utf-8")
    py_compile.compile(str(MAIN), doraise=True)


FORECAST_PATCH_MARKER = "# === FORECAST AGENT PIPELINE V1 ==="


def patch_forecast_pipeline():
    source = MAIN.read_text(encoding="utf-8")
    if FORECAST_PATCH_MARKER in source:
        py_compile.compile(str(MAIN), doraise=True)
        return

    # The existing application keeps the Telegram handlers in main.py.
    # We inject a replacement function after all original definitions, before
    # the uvicorn entry point. Runtime handler dispatch resolves the global
    # horoscope_handler name to this replacement.
    import_line = (
        "from agents.forecast_agent import build_forecast_plan, render_forecast_context\n"
        "from agents.forecast_qa import validate_forecast\n"
    )
    import_needle = "from agents.forecast_engine import calculate_daily_sky, calculate_personal_day, build_period_sky_summary\n"
    if import_line not in source:
        if import_needle not in source:
            raise RuntimeError("Forecast engine import not found in main.py")
        source = source.replace(import_needle, import_needle + import_line, 1)

    injected = r'''
# === FORECAST AGENT PIPELINE V1 ===
async def horoscope_handler(m: Message, date_str: str, last_action: str):
    """Профессиональный прогноз: расчёт -> отбор факторов -> LLM -> детерминированный QA."""
    user_id = m.from_user.id

    h_type = last_action.split("_", 1)[1] if "_" in last_action else "today"
    if h_type not in {"today", "tomorrow", "week", "month"}:
        h_type = "today"

    type_names = {
        "today": "сегодня",
        "tomorrow": "завтра",
        "week": "неделю",
        "month": "месяц",
    }
    period_display = type_names[h_type]
    tz_name = "Europe/Moscow"
    today = datetime.now(ZoneInfo(tz_name)).date()

    if h_type == "today":
        start = end = today
    elif h_type == "tomorrow":
        start = end = today + timedelta(days=1)
    elif h_type == "week":
        start = today
        end = today + timedelta(days=6)
    else:
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)

    date_description = (
        start.strftime("%d.%m.%Y")
        if start == end
        else f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}"
    )

    await m.answer(f"🔮 Создаю гороскоп на {period_display}...")

    storage.stats["horoscopes"] = storage.stats.get("horoscopes", 0) + 1
    await storage.save_all()

    life_number = NumerologyFeatures.calculate_life_path_number(date_str)
    zodiac = get_zodiac_sign(date_str)
    zodiac_name = zodiac["name"] if zodiac else "не определён"
    zodiac_emoji = zodiac["emoji"] if zodiac else "🔮"
    zodiac_element = zodiac["element"] if zodiac else "не определена"

    start_str = start.strftime("%d.%m.%Y")
    end_str = end.strftime("%d.%m.%Y")

    if h_type in {"today", "tomorrow"}:
        sky = calculate_daily_sky(start_str, tz_name)
        personal_day = calculate_personal_day(date_str, start_str)
        plan = build_forecast_plan(
            sky=sky,
            period=h_type,
            zodiac_name=zodiac_name,
            life_number=life_number,
            personal_day=personal_day,
        )
        context = render_forecast_context(plan)
        number_label = "личный день"
        number_value = personal_day["personal_day"]
    else:
        events = build_period_sky_summary(start_str, end_str, tz_name, max_events=12)
        plan = {
            "period": h_type,
            "date": date_description,
            "zodiac": zodiac_name,
            "life_number": life_number,
            "events": events,
            "source": "Swiss Ephemeris / Moshier fallback",
        }
        context = (
            "РАССЧИТАННЫЕ СОБЫТИЯ ПЕРИОДА. ИСПОЛЬЗУЙ ТОЛЬКО ИХ.\n"
            + "\n".join(f"- {e['date']}: {e['text']}" for e in events)
        )
        if h_type == "week":
            number_value = NumerologyFeatures.calculate_period_number(start_str, end_str)
            number_label = "число недели"
        else:
            number_value = NumerologyFeatures.calculate_month_period_number(start_str)
            number_label = "число месяца"

    if h_type in {"today", "tomorrow"}:
        prompt = f"""
Ты — редактор персонального астрологического прогноза.

Период: {period_display} ({date_description})
Дата рождения: {date_str}
Знак: {zodiac_name} (стихия: {zodiac_element})
Число жизненного пути: {life_number if life_number else "не определено"}

{context}

КРИТИЧЕСКИЕ ПРАВИЛА:
1. Положение планеты в знаке — это только положение. Оно НЕ является аспектом.
2. Называть аспект можно только в точной паре планет, которая есть в блоке «РАССЧИТАННЫЕ АСПЕКТЫ».
3. Не соединяйте два независимых положения словами «создают напряжение», если между ними нет рассчитанного аспекта.
4. Луна должна быть отдельной частью прогноза: знак + фаза.
5. Если есть переход планеты в другой знак, используйте его как отдельное событие и не смешивайте с аспектом.
6. Не утверждайте неизбежные события. Используйте «может», «вероятно», «стоит обратить внимание».
7. Нумерология — вспомогательный слой. Не заменяйте ею астрологические факторы.
8. Не используйте слово «сегодня» в прогнозе на завтра, кроме явного сравнения «в отличие от сегодня».
9. Не добавляйте факты, которых нет в расчётном блоке.
10. Это развлекательная интерпретация, а не научное предсказание.

Формат — только эти эмодзи-разделители, без текстовых заголовков:
🌅 — главный фон дня, 2–3 предложения.
🌙 — Луна: знак, фаза и эмоциональный ритм, 2 предложения.
💼 — работа и дела, 2–3 предложения.
💬 — отношения и общение, 2 предложения.
⚡ — одна зона напряжения и практичный способ её снизить.
🔢 — {number_label} {number_value}: практическое применение.
💡 — один практический шаг на {period_display}.
✨ — итог одним предложением.

Объём: 170–220 слов.
Обращение только на «вы».
Не используй англицизмы, транслитерацию, слова «карма», «вселенная», «потоки».
"""
    elif h_type == "week":
        prompt = f"""
Ты — редактор персонального астрологического прогноза на неделю {date_description}.
Дата рождения: {date_str}
Знак: {zodiac_name} (стихия: {zodiac_element})
Число жизненного пути: {life_number if life_number else "не определено"}

{context}

Используй только рассчитанные события. Не придумывай транзиты, аспекты и даты.
Разделяй положение планеты и аспект: положение само по себе не означает напряжение или гармонию.
Если событие не подтверждено расчётом, не называй его.
Не обещай конкретный результат. Используй вероятностные формулировки.

Формат — только эмодзи-разделители:
🌟 — главный вектор недели, 2–3 предложения.
📅 — начало недели.
📅 — середина недели.
📅 — конец недели.
💼 — работа и деньги.
💬 — отношения и общение.
⚡ — один повторяющийся риск и способ его снизить.
💡 — одна стратегия недели.
🎯 — число недели {number_value}.
✨ — итог недели.

Объём: 220–270 слов. Только литературный русский, обращение на «вы».
Не используй англицизмы, транслитерацию, слова «карма», «вселенная», «потоки».
"""
    else:
        prompt = f"""
Ты — редактор персонального астрологического прогноза на месяц {date_description}.
Дата рождения: {date_str}
Знак: {zodiac_name} (стихия: {zodiac_element})
Число жизненного пути: {life_number if life_number else "не определено"}

{context}

Используй только рассчитанные события. Не придумывай транзиты, аспекты и даты.
Разделяй положение планеты и аспект: положение само по себе не означает напряжение или гармонию.
Не обещай конкретные результаты и не делай категоричных предсказаний.

Формат — только эмодзи-разделители:
🌟 — главный вектор месяца.
📅 — первая треть месяца.
📅 — вторая треть месяца.
📅 — последняя треть месяца.
💼 — работа и деньги.
💬 — отношения и общение.
⚡ — системный риск и способ его снизить.
💡 — одна стратегия месяца.
🎯 — число месяца {number_value}.
✨ — итог месяца.

Объём: 240–290 слов. Только литературный русский, обращение на «вы».
Не используй англицизмы, транслитерацию, слова «карма», «вселенная», «потоки».
"""

    response = await ask_groq(prompt, "horoscope")

    if h_type in {"today", "tomorrow"}:
        qa = validate_forecast(response, plan, h_type)
        if not qa["pass"]:
            logger.warning("FORECAST QA FAIL: period=%s issues=%s", h_type, qa["issues"])
            repair_prompt = f"""
Исправьте следующий астрологический прогноз без переписывания с нуля.
Уберите ТОЛЬКО фактические ошибки, перечисленные ниже.
РАСЧЁТНЫЕ ДАННЫЕ:
{context}

ОШИБКИ QA:
{chr(10).join("- " + x for x in qa["issues"])}

ТЕКСТ:
{response}

Верните только исправленный текст в том же формате эмодзи-разделителей.
Не добавляйте новых астрологических фактов.
"""
            try:
                repaired = await ask_groq(repair_prompt, "horoscope")
                repaired_qa = validate_forecast(repaired, plan, h_type)
                if repaired_qa["pass"]:
                    response = repaired
                    logger.info("FORECAST QA PASS after repair")
                else:
                    logger.error("FORECAST QA FAIL after repair: %s", repaired_qa["issues"])
            except Exception:
                logger.exception("FORECAST repair failed; keeping first response")
        else:
            logger.info("FORECAST QA PASS: period=%s", h_type)

    final_text = f"""
🔮 *Ваш гороскоп* 🔮
*{zodiac_emoji} {zodiac_name} | Число пути: {life_number}*

{response}
"""
    await safe_reply(m, final_text, reply_markup=main_menu(user_id))
    await PersonalizationEngine.update_user_profile(
        user_id,
        "horoscope_generated",
        {"date": date_str, "period": h_type, "forecast_qa": "passed_or_logged"},
        birth_date=date_str
    )


def _forecast_patch_marker():
    return
'''

    marker = 'if __name__ == "__main__":'
    if marker not in source:
        raise RuntimeError("main entry point not found in main.py")
    source = source.replace(marker, injected + "

" + marker, 1)

    MAIN.write_text(source, encoding="utf-8")
    py_compile.compile(str(MAIN), doraise=True)


if __name__ == "__main__":
    calendar_patch()
    patch_groq()
    patch_forecast_pipeline()
    print("Forecast agent/QA pipeline enabled")
